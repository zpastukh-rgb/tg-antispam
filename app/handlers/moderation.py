# app/handlers/moderation.py
from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from aiogram import Router, F
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message, ChatPermissions, ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import delete, select

from app.db.session import get_session
from app.db.models import Chat, Rule, StopWord, WhitelistDomain, WhitelistUser, ModerationLog, ProfanityWord, NewMember
from app.services.public_alerts import maybe_send_public_alert
from app.services.chat_cleanup import record_seen_member as record_seen_member_cleanup
from app.services.global_antispam import is_in_global_antispam

router = Router()
logger = logging.getLogger(__name__)


def _should_run_moderation_pipeline(message: Message) -> bool:
    """Команды (/...) обрабатываются другими роутерами; иначе catch-all moderation перехватывает апдейт до panel."""
    chunk = (message.text or message.caption or "").lstrip()
    return not chunk.startswith("/")

# =========================================================
# 😈 AntiSpam Guardian — MODERATION CORE (Step A "железобетон")
# =========================================================
# Архитектура:
#   evaluate() -> apply_action() -> send_log()
#   + Safe guards: никаких падений из-за 1 сообщения
#
# Важное:
# - Anti-edit: edited_message прогоняем через тот же evaluate()
# - Whitelist: users + domains
# - Новичок: поля newbie_* в Rule; эскалация «delete→mute» для фильтров снята — срабатывает выбранный action_mode
# - Кэш: TTL-кэш для stopwords/whitelist (разгружает БД)
# =========================================================


# =========================================================
# REGEX (строго, но без паранойи)
# =========================================================
URL_RE = re.compile(
    r"""(?ix)
    \b(
        (?:https?://|tg://|www\.)[^\s<>{}\[\]|\\^`"]+
        |
        t\.me/[^\s<>{}\[\]|\\^`"]+
    )\b
    """
)
MENTION_RE = re.compile(r"(?<!\w)@[\w\d_]{4,}")


# =========================================================
# ✅ Режим тишины: время входа в чат (LRU + TTL)
# =========================================================
SILENCE_JOIN_LRU: "OrderedDict[Tuple[int, int], datetime]" = OrderedDict()
SILENCE_JOIN_MAX = 200_000
SILENCE_JOIN_TTL = timedelta(days=2)


def _silence_join_cleanup(now: datetime) -> None:
    while SILENCE_JOIN_LRU:
        _k, ts = next(iter(SILENCE_JOIN_LRU.items()))
        if now - ts <= SILENCE_JOIN_TTL:
            break
        SILENCE_JOIN_LRU.popitem(last=False)


def _silence_join_record(chat_id: int, user_id: int) -> None:
    """Записать время входа пользователя в чат (для режима тишины)."""
    now = datetime.now(timezone.utc)
    _silence_join_cleanup(now)
    key = (chat_id, user_id)
    SILENCE_JOIN_LRU[key] = now
    SILENCE_JOIN_LRU.move_to_end(key)
    while len(SILENCE_JOIN_LRU) > SILENCE_JOIN_MAX:
        SILENCE_JOIN_LRU.popitem(last=False)


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _silence_join_at_db(session, chat_id: int, user_id: int) -> Optional[datetime]:
    res = await session.execute(
        select(NewMember.joined_at).where(
            NewMember.chat_id == chat_id,
            NewMember.user_id == user_id,
        ).limit(1)
    )
    row = res.first()
    if not row or row[0] is None:
        return None
    return _naive_utc(row[0])


async def _silence_remaining_restrict_minutes(
    session, chat_id: int, user_id: int, silence_minutes: int
) -> Optional[int]:
    """
    Остаток окна тишины в минутах для restrict (или None — не в окне / нет записи о входе).
    Учитывает БД (устойчиво к перезапуску бота) и LRU как запасной путь.
    """
    if silence_minutes <= 0:
        return None
    join_at = await _silence_join_at_db(session, chat_id, user_id)
    if join_at is None:
        key = (chat_id, user_id)
        if key not in SILENCE_JOIN_LRU:
            return None
        join_at = _naive_utc(SILENCE_JOIN_LRU[key])
    now = datetime.now(timezone.utc)
    window = timedelta(minutes=silence_minutes)
    if now - join_at > window:
        return None
    remaining = window - (now - join_at)
    rm = max(1, int((remaining.total_seconds() + 59) // 60))
    return min(rm, silence_minutes)


async def upsert_member_join_for_silence(session, chat_id: int, user_id: int) -> None:
    """Зафиксировать время входа в чат (режим тишины), одна строка на пару chat+user."""
    now = datetime.now(timezone.utc)
    res = await session.execute(
        select(NewMember).where(NewMember.chat_id == chat_id, NewMember.user_id == user_id).limit(1)
    )
    row = res.scalar_one_or_none()
    if row:
        row.joined_at = now
    else:
        session.add(NewMember(chat_id=chat_id, user_id=user_id, joined_at=now))


async def delete_member_join_marker(session, chat_id: int, user_id: int) -> None:
    await session.execute(
        delete(NewMember).where(NewMember.chat_id == chat_id, NewMember.user_id == user_id)
    )


# =========================================================
# ✅ Антинакрутка: буфер входов по чатам для детекции массового входа
# =========================================================
# chat_id -> [(user_id, join_time), ...], храним только за последние window_minutes
_ANTINAKRUTKA_JOINS: Dict[int, List[Tuple[int, datetime]]] = {}
_ANTINAKRUTKA_MAX_LIST = 500  # макс. записей на чат


def _antinakrutka_add_join(chat_id: int, user_id: int, window_minutes: int) -> List[Tuple[int, datetime]]:
    """Добавить вход, обрезать старые, вернуть текущий список за окно."""
    now = datetime.now(timezone.utc)
    window = timedelta(minutes=max(1, min(60, window_minutes)))
    if chat_id not in _ANTINAKRUTKA_JOINS:
        _ANTINAKRUTKA_JOINS[chat_id] = []
    lst = _ANTINAKRUTKA_JOINS[chat_id]
    lst.append((user_id, now))
    # оставить только за окно
    lst[:] = [(uid, t) for uid, t in lst if now - t <= window]
    if len(lst) > _ANTINAKRUTKA_MAX_LIST:
        lst[:] = lst[-_ANTINAKRUTKA_MAX_LIST:]
    return lst


def _antinakrutka_clear(chat_id: int) -> None:
    """Сбросить буфер после срабатывания."""
    _ANTINAKRUTKA_JOINS.pop(chat_id, None)


# =========================================================
# ✅ TTL caches (DB load fix for big scale)
# =========================================================
CACHE_TTL = 60  # seconds

_STOPWORDS_CACHE: Dict[int, Tuple[float, Set[str]]] = {}
_PROFANITY_CACHE: Tuple[float, Set[str]] = (0.0, set())  # (ts, words) глобальный список мата
_WLUSER_CACHE: "OrderedDict[Tuple[int, int], Tuple[float, bool]]" = OrderedDict()
_WLDOM_CACHE: "OrderedDict[Tuple[int, str], Tuple[float, bool]]" = OrderedDict()

_CACHE_MAX = 200_000  # ограничитель памяти

def _cache_prune(d: "OrderedDict", now: float, ttl: float) -> None:
    # TTL с головы
    while d:
        _k, (ts, _v) = next(iter(d.items()))
        if now - ts <= ttl:
            break
        d.popitem(last=False)
    # LRU cap
    while len(d) > _CACHE_MAX:
        d.popitem(last=False)


# =========================================================
# Verdict
# =========================================================
@dataclass
class Verdict:
    should_act: bool
    reason: str
    details: str
    action: str  # delete|mute|ban
    mute_minutes: int = 0
    log_it: bool = True
    log_extra: str = ""


# =========================================================
# Text helpers
# =========================================================
def normalize(text: str) -> str:
    return (text or "").strip().lower().replace("ё", "е")

def token_set(text_norm: str) -> Set[str]:
    return {t for t in re.split(r"[^a-zа-я0-9_]+", text_norm) if t}


def _text_without_urls_for_stopwords(text: str) -> str:
    """Убирает URL из текста (замена на пробел), чтобы стоп-слова не срабатывали на части ссылок."""
    if not text:
        return ""
    return URL_RE.sub(" ", text)


def stopword_hit(text_norm: str, stopwords: Set[str], text_without_urls_norm: Optional[str] = None) -> Optional[str]:
    """Проверка стоп-слов. Если передан text_without_urls_norm — используем его (ссылки не участвуют)."""
    if not stopwords:
        return None
    base = (text_without_urls_norm if text_without_urls_norm is not None else text_norm)
    toks = token_set(base)
    for w in stopwords:
        ww = (w or "").strip().lower().replace("ё", "е")
        if ww and ww in toks:
            return ww
    return None


def profanity_hit(text_norm: str, profanity_words: Set[str], text_without_urls_norm: Optional[str] = None) -> Optional[str]:
    """Проверка на мат (по токенам, без учёта текста внутри URL)."""
    if not profanity_words:
        return None
    base = (text_without_urls_norm if text_without_urls_norm is not None else text_norm)
    toks = token_set(base)
    for w in profanity_words:
        ww = (w or "").strip().lower().replace("ё", "е")
        if ww and ww in toks:
            return ww
    return None


def find_links(text: str) -> List[str]:
    return [m.group(1) for m in URL_RE.finditer(text or "")]


def _slice_utf16(s: str, offset: int, length: int) -> str:
    """Срез строки по смещению и длине в UTF-16 code units (Telegram API)."""
    if not s or length <= 0:
        return ""
    try:
        enc = s.encode("utf-16-le")
        start = offset * 2
        end = min((offset + length) * 2, len(enc))
        if start >= len(enc):
            return ""
        return enc[start:end].decode("utf-16-le", errors="replace")
    except Exception:
        return ""


def find_links_in_message(message: Message) -> List[str]:
    """Все ссылки в сообщении: из текста (regex) и из entities (url, text_link)."""
    text = message.text or ""
    caption = message.caption or ""
    links: List[str] = []
    seen: Set[str] = set()

    for raw in find_links(text) + find_links(caption):
        r = (raw or "").strip()
        if r and r not in seen:
            seen.add(r)
            links.append(r)

    for content, entities in [(text, getattr(message, "entities", None)), (caption, getattr(message, "caption_entities", None))]:
        if not entities:
            continue
        # content может быть пустым для caption_entities при только подписи к фото
        content = content or ""
        for e in entities:
            t = getattr(e, "type", None)
            if t is not None and hasattr(t, "value"):
                t = t.value
            t = str(t) if t is not None else ""
            if t == "url":
                part = _slice_utf16(content, getattr(e, "offset", 0), getattr(e, "length", 0))
                if part and part not in seen:
                    seen.add(part)
                    links.append(part)
            elif t == "text_link":
                url = getattr(e, "url", None)
                if url and (url not in seen):
                    seen.add(url)
                    links.append(url)

    return links


def _domain_from_url(raw: str) -> Optional[str]:
    s = (raw or "").strip().lower()
    if not s:
        return None

    if s.startswith("tg://"):
        return "tg://"

    if s.startswith("t.me/"):
        return "t.me"

    if s.startswith("www."):
        s = "http://" + s
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "http://" + s

    try:
        u = urlparse(s)
        dom = (u.netloc or "").lower()
        if dom.startswith("www."):
            dom = dom[4:]
        return dom or None
    except Exception:
        return None

def extract_domains(text: str) -> Set[str]:
    out: Set[str] = set()
    for m in URL_RE.finditer(text or ""):
        dom = _domain_from_url(m.group(1))
        if dom:
            out.add(dom)
    return out


def extract_domains_from_links(links: List[str]) -> Set[str]:
    """Домены из списка URL (для whitelist после find_links_in_message)."""
    out: Set[str] = set()
    for raw in links or []:
        dom = _domain_from_url(raw)
        if dom:
            out.add(dom)
    return out


# ❗️старый find_mentions(text) больше не нужен — ловим через entities + regex fallback
def find_mentions_from_entities(message: Message) -> List[str]:
    out: List[str] = []

    def _scan(text: str, ents) -> None:
        if not text or not ents:
            return
        for e in ents:
            et = getattr(e, "type", None)
            if et == "mention":
                out.append(text[e.offset : e.offset + e.length])
            elif et == "text_mention":
                u = getattr(e, "user", None)
                if u:
                    out.append(f"id:{u.id}")  # <-- как ты просил

    _scan(message.text or "", getattr(message, "entities", None))
    _scan(message.caption or "", getattr(message, "caption_entities", None))
    return out

def find_mentions_any(message: Message) -> List[str]:
    ent = find_mentions_from_entities(message)
    if ent:
        return ent
    text = (message.text or message.caption or "")
    return [m.group(0) for m in MENTION_RE.finditer(text)]


def has_media(message: Message) -> bool:
    """Сообщение содержит медиа: фото, видео, стикер, документ, голос, и т.д."""
    return bool(
        getattr(message, "photo", None)
        or getattr(message, "video", None)
        or getattr(message, "sticker", None)
        or getattr(message, "document", None)
        or getattr(message, "animation", None)
        or getattr(message, "voice", None)
        or getattr(message, "video_note", None)
        or getattr(message, "audio", None)
    )


def has_buttons(message: Message) -> bool:
    """Сообщение содержит инлайн- или reply-клавиатуру."""
    rm = getattr(message, "reply_markup", None)
    if not rm:
        return False
    return bool(
        getattr(rm, "inline_keyboard", None)
        or getattr(rm, "keyboard", None)
    )


# =========================================================
# Telegram helpers (roles)
# =========================================================
async def is_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


# =========================================================
# DB helpers
# =========================================================
async def get_rule(session, chat_id: int) -> Rule:
    rule = await session.get(Rule, chat_id)
    if rule:
        if not getattr(rule, "action_mode", None):
            rule.action_mode = "delete"
        if getattr(rule, "mute_minutes", None) is None:
            rule.mute_minutes = 30
        if getattr(rule, "newbie_minutes", None) is None:
            rule.newbie_minutes = 10
        await session.commit()
        return rule

    rule = Rule(
        chat_id=chat_id,
        filter_links=True,
        filter_mentions=True,
        action_mode="delete",
        mute_minutes=30,
        anti_edit=True,
        newbie_enabled=True,
        newbie_minutes=10,
        log_enabled=True,
    )
    session.add(rule)
    await session.commit()
    return rule

async def load_stopwords(session, chat_id: int) -> Set[str]:
    now = time.time()
    cached = _STOPWORDS_CACHE.get(chat_id)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    res = await session.execute(select(StopWord.word).where(StopWord.chat_id == chat_id))
    words = {str(w).strip().lower().replace("ё", "е") for (w,) in res.all() if w}
    _STOPWORDS_CACHE[chat_id] = (now, words)
    return words


async def load_profanity_words(session) -> Set[str]:
    """Глобальный список матерных слов (общая таблица profanity_words)."""
    global _PROFANITY_CACHE
    now = time.time()
    if _PROFANITY_CACHE[0] and now - _PROFANITY_CACHE[0] < CACHE_TTL:
        return _PROFANITY_CACHE[1]
    res = await session.execute(select(ProfanityWord.word))
    words = {str(w).strip().lower().replace("ё", "е") for (w,) in res.all() if w}
    _PROFANITY_CACHE = (now, words)
    return words


async def whitelist_user(session, chat_id: int, user_id: int) -> bool:
    now = time.time()
    key = (chat_id, user_id)

    cached = _WLUSER_CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        _WLUSER_CACHE.move_to_end(key)
        return cached[1]

    res = await session.execute(
        select(WhitelistUser.id).where(
            WhitelistUser.chat_id == chat_id,
            WhitelistUser.user_id == user_id,
        )
    )
    ok = res.first() is not None

    _WLUSER_CACHE[key] = (now, ok)
    _WLUSER_CACHE.move_to_end(key)
    _cache_prune(_WLUSER_CACHE, now, CACHE_TTL)
    return ok

async def whitelist_domain(session, chat_id: int, domain: str) -> bool:
    dom = (domain or "").strip().lower()
    if dom.startswith("www."):
        dom = dom[4:]

    now = time.time()
    key = (chat_id, dom)

    cached = _WLDOM_CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        _WLDOM_CACHE.move_to_end(key)
        return cached[1]

    res = await session.execute(
        select(WhitelistDomain.id).where(
            WhitelistDomain.chat_id == chat_id,
            WhitelistDomain.domain == dom,
        )
    )
    ok = res.first() is not None

    _WLDOM_CACHE[key] = (now, ok)
    _WLDOM_CACHE.move_to_end(key)
    _cache_prune(_WLDOM_CACHE, now, CACHE_TTL)
    return ok


# =========================================================
# Decision Engine (single source of truth)
# =========================================================
async def evaluate(session, message: Message, *, edited: bool = False) -> Verdict:
    # only groups
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return Verdict(False, "not_group", "", "delete", log_it=False)


    user = message.from_user
    sender_chat = getattr(message, "sender_chat", None)

    # если нет ни пользователя ни sender_chat — пропускаем
    if not user and not sender_chat:
        return Verdict(False, "no_actor", "", "delete", log_it=False)

    chat_id = message.chat.id
    user_id = user.id if user else 0

    # chat must be active
    chat_row = await session.get(Chat, chat_id)
    if not chat_row or not bool(getattr(chat_row, "is_active", True)):
        return Verdict(False, "inactive", "", "delete", log_it=False)

    rule = await get_rule(session, chat_id)
    try:
        await session.refresh(rule)  # свежие данные из БД (настройки из Mini App)
    except Exception:
        pass

    # главный выключатель антиспама: если ВЫКЛ — не фильтруем
    if not bool(getattr(rule, "master_anti_spam", True)):
        return Verdict(False, "master_off", "", "delete", log_it=False)

    # do not touch admins
    if user and await is_admin(message.bot, chat_id, user_id):
        return Verdict(False, "admin_skip", "", "delete", log_it=False)

    # do not touch whitelisted users
    if user and await whitelist_user(session, chat_id, user_id):
        return Verdict(False, "whitelist_user", "", "delete", log_it=False)

    text = message.text or message.caption or ""
    text_norm = normalize(text)
    # Для стоп-слов не учитываем текст внутри URL (чтобы «разрешено» для ссылок не ломалось из-за слов в ссылке)
    text_for_stopwords_norm = normalize(_text_without_urls_for_stopwords(text))

    # base action
    action = (getattr(rule, "action_mode", "delete") or "delete").lower()
    if action not in ("delete", "mute", "ban"):
        action = "delete"

    mute_min = int(getattr(rule, "mute_minutes", 30) or 30)
    mute_min = max(1, min(1440, mute_min))

    # Ссылки: единственный источник истины — filter_links_mode; "allow" = не трогаем ссылки
    _links_mode_raw = getattr(rule, "filter_links_mode", None)
    _links_mode = str(_links_mode_raw).strip().lower() if _links_mode_raw is not None else ""
    if "allow" in _links_mode:
        _links_mode = "allow"
    _legacy_filter_links = getattr(rule, "filter_links", True)
    if _links_mode == "allow":
        filter_links = False
    elif _links_mode in ("forbid", "captcha"):
        filter_links = True
    elif _legacy_filter_links is False:
        filter_links = False
    else:
        filter_links = True
    filter_mentions = bool(getattr(rule, "filter_mentions", True))
    _media_mode = getattr(rule, "filter_media_mode", "allow")
    filter_media = _media_mode in ("forbid", "captcha")
    _buttons_mode = getattr(rule, "filter_buttons_mode", "allow")
    filter_buttons = _buttons_mode in ("forbid", "captcha")
    anti_edit = bool(getattr(rule, "anti_edit", True))
    log_enabled = bool(getattr(rule, "log_enabled", True))
    silence_minutes = int(getattr(rule, "silence_minutes", 0) or 0)
    silence_minutes = max(0, min(10080, silence_minutes))  # до 7 суток

    # -------------------------------------------------
    # 0) Режим тишины: после входа N минут — ограничение (время входа в БД + LRU)
    # -------------------------------------------------
    if silence_minutes > 0 and user:
        silence_rem = await _silence_remaining_restrict_minutes(session, chat_id, user_id, silence_minutes)
        if silence_rem is not None:
            return Verdict(
                True,
                "silence",
                f"режим тишины ({silence_minutes} мин)",
                "mute",
                mute_minutes=silence_rem,
                log_it=log_enabled,
                log_extra=f"тишина, осталось ~{silence_rem} мин из {silence_minutes}",
            )

    # -------------------------------------------------
    # 1) stopwords (без учёта токенов внутри URL)
    # -------------------------------------------------
    stopwords = await load_stopwords(session, chat_id)
    hit = stopword_hit(text_norm, stopwords, text_without_urls_norm=text_for_stopwords_norm)
    if hit:
        return Verdict(
            True, "stopword", hit, action,
            mute_minutes=mute_min,
            log_it=log_enabled,
            log_extra=("anti-edit" if edited else ""),
        )

    # -------------------------------------------------
    # 1b) Мат (filter_profanity_enabled, общая таблица profanity_words)
    # -------------------------------------------------
    if getattr(rule, "filter_profanity_enabled", False):
        profanity_set = await load_profanity_words(session)
        hit_prof = profanity_hit(text_norm, profanity_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_prof:
            return Verdict(
                True, "profanity", hit_prof, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )

    # -------------------------------------------------
    # 2) links (текст + entities: url, text_link). При "allow" блок не выполняется.
    # -------------------------------------------------
    if not filter_links:
        pass  # ссылки разрешены — не проверяем
    else:
        links = find_links_in_message(message)
        if links:
            domains = extract_domains_from_links(links)

            allowed = False
            for d in domains:
                if d == "tg://":
                    continue
                if await whitelist_domain(session, chat_id, d):
                    allowed = True
                    break

            if not allowed:
                # Ещё раз: при "allow" ссылки не наказываем
                if _links_mode == "allow":
                    pass
                else:
                    # Капча на паузе: режим "captcha" обрабатываем как обычное действие (delete/mute/ban)
                    # from app.handlers.first_message_captcha import _captcha_passed as captcha_passed_check
                    # if _links_mode == "captcha" and user and captcha_passed_check(chat_id, user_id):
                    #     pass
                    link_action = action  # капча на паузе — не "captcha", всегда action
                    return Verdict(
                        True, "link", links[0], link_action,
                        mute_minutes=mute_min,
                        log_it=log_enabled,
                        log_extra=("anti-edit" if edited else ""),
                    )

    # -------------------------------------------------
    # 3) mentions
    # -------------------------------------------------
    if filter_mentions:
        mentions = find_mentions_any(message)
        if mentions:
            return Verdict(
                True, "mention", mentions[0], action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )

    # -------------------------------------------------
    # 4) media / стикеры (filter_media_mode: forbid | captcha). Капча на паузе — captcha как action
    # -------------------------------------------------
    if filter_media and has_media(message):
        # from app.handlers.first_message_captcha import _captcha_passed as captcha_passed_check
        # if _media_mode == "captcha" and user and captcha_passed_check(chat_id, user_id):
        #     pass
        media_action = action  # капча на паузе: "captcha" -> action (delete/mute/ban)
        return Verdict(
            True, "media", "медиа/стикер", media_action,
            mute_minutes=mute_min,
            log_it=log_enabled,
            log_extra=("anti-edit" if edited else ""),
        )

    # -------------------------------------------------
    # 5) сообщения с кнопками (filter_buttons_mode: forbid | captcha). Капча на паузе — captcha как action
    # -------------------------------------------------
    if filter_buttons and has_buttons(message):
        # from app.handlers.first_message_captcha import _captcha_passed as captcha_passed_check
        # if _buttons_mode == "captcha" and user and captcha_passed_check(chat_id, user_id):
        #     pass
        buttons_action = action  # капча на паузе: "captcha" -> action (delete/mute/ban)
        return Verdict(
            True, "buttons", "сообщение с кнопками", buttons_action,
            mute_minutes=mute_min,
            log_it=log_enabled,
            log_extra=("anti-edit" if edited else ""),
        )

    # -------------------------------------------------
    # 6) anti-edit (сам факт правки — не преступление)
    # Если после правки появилось нарушение — оно уже отработало выше.
    # -------------------------------------------------
    if edited and anti_edit:
        return Verdict(False, "edited_clean", "", "delete", log_it=False)

    return Verdict(False, "clean", "", "delete", log_it=False)


# =========================================================
# Actions (delete / mute / ban)
# =========================================================
async def _try_delete(message: Message) -> bool:
    try:
        await message.delete()
        return True
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    except Exception:
        return False

async def _try_mute(message: Message, minutes: int) -> bool:
    until = datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes))
    try:
        await message.bot.restrict_chat_member(
            message.chat.id,
            message.from_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        return True
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    except Exception:
        return False

async def _try_ban(message: Message) -> bool:
    try:
        await message.bot.ban_chat_member(message.chat.id, message.from_user.id)
        return True
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    except Exception:
        return False

async def apply_action(message: Message, v: Verdict) -> Tuple[bool, str, bool]:
    """
    returns: (ok_action, action_label_for_log, deleted_ok)
    """
    deleted_ok = await _try_delete(message)

    if v.action == "delete":
        return deleted_ok, "delete", deleted_ok

    # Капча на паузе — блок не вызывается (в evaluate не возвращаем action "captcha")
    # if v.action == "captcha":
    #     from app.handlers.first_message_captcha import send_captcha_dm, send_captcha_fallback_instruction
    #     if message.from_user:
    #         ok = await send_captcha_dm(message.bot, message.from_user.id, message.chat.id)
    #         if not ok:
    #             mention = f"<a href=\"tg://user?id={message.from_user.id}\">{message.from_user.full_name}</a>"
    #             await send_captcha_fallback_instruction(
    #                 message.bot, message.chat.id, message.from_user.id, mention
    #             )
    #     return True, "капча", deleted_ok

    if v.action == "mute":
        ok = await _try_mute(message, v.mute_minutes)
        return ok, f"mute {v.mute_minutes}m", deleted_ok

    if v.action == "ban":
        ok = await _try_ban(message)
        return ok, "ban", deleted_ok

    return False, "unknown", deleted_ok


# =========================================================
# Log keyboard (unban / unmute)
# =========================================================
def log_keyboard(action: str, chat_id: int, user_id: int):
    b = InlineKeyboardBuilder()

    if action == "ban":
        b.button(text="✅ Разбанить", callback_data=f"log:unban:{chat_id}:{user_id}")

    if action == "mute":
        b.button(text="🔊 Размутить", callback_data=f"log:unmute:{chat_id}:{user_id}")

    b.adjust(1)
    return b.as_markup()


# =========================================================
# Logging
# =========================================================
_REASON_HUMAN = {
    "stopword": "🧨 стоп-слово",
    "stopword_newbie": "🧨 стоп-слово (новичок)",
    "profanity": "🚫 мат",
    "profanity_newbie": "🚫 мат (новичок)",
    "link": "🔗 ссылка",
    "link_newbie": "🔗 ссылка (новичок)",
    "mention": "🏷 упоминание",
    "mention_newbie": "🏷 упоминание (новичок)",
    "media": "🖼 медиа/стикер",
    "media_newbie": "🖼 медиа/стикер (новичок)",
    "buttons": "🔘 сообщение с кнопками",
    "buttons_newbie": "🔘 сообщение с кнопками (новичок)",
    "silence": "🔇 режим тишины",
    "edited_clean": "✏️ edit (чисто)",
}

async def send_log(
    session,
    message: Message,
    v: Verdict,
    *,
    action_label: str,
    ok_action: bool,
    deleted_ok: bool,
) -> None:
    if not v.log_it:
        return

    chat_row = await session.get(Chat, message.chat.id)
    if not chat_row:
        return

    rule = await get_rule(session, message.chat.id)
    if not bool(getattr(rule, "log_enabled", True)):
        return

    log_chat_id = getattr(chat_row, "log_chat_id", None)
    if not log_chat_id:
        return

    user = message.from_user
    if not user:
        return

    src = (message.text or message.caption or "")
    src = (src[:500] + "…") if len(src) > 500 else src

    who = f"@{user.username}" if user.username else user.full_name
    reason_h = _REASON_HUMAN.get(v.reason, v.reason)

    extra_parts: List[str] = []
    if v.log_extra:
        extra_parts.append(v.log_extra)

    if not deleted_ok:
        extra_parts.append("⚠️ не смог удалить (нет права Delete messages)")

    if v.action in ("mute", "ban") and not ok_action:
        extra_parts.append("⚠️ не смог наказать (нет права Ban/Restrict или лимит Telegram)")

    extra = " | ".join(extra_parts)

    txt = (
        "😈 *AntiSpam Guardian — отчёт*\n"
        f"Чат: *{message.chat.title or message.chat.id}*\n"
        f"Кто: *{who}* (`{user.id}`)\n"
        f"Причина: *{reason_h}* → `{v.details}`\n"
        f"Действие: *{action_label}*\n"
    )

    if extra:
        txt += f"\n_{extra}_\n"

    if src:
        txt += f"\nТекст:\n`{src}`\n"

    try:
        await message.bot.send_message(
            int(log_chat_id),
            txt,
            parse_mode="Markdown",
            reply_markup=log_keyboard(v.action, message.chat.id, user.id),
        )
        # ТЗ Автоотчёты: пишем в moderation_logs для дайджеста раз в сутки
        session.add(ModerationLog(
            chat_id=message.chat.id,
            user_id=user.id,
            action=v.action,
            reason=v.reason,
            message_text=(message.text or message.caption or "")[:2000],
        ))
    except Exception as e:
        logger.warning(f"[log send failed] chat={message.chat.id} -> log_chat={log_chat_id}: {e}")


# =========================================================
# Pipeline
# =========================================================
async def pipeline(message: Message, *, edited: bool = False) -> None:
    # если сообщение от имени канала/чата — from_user может быть None
    if not message.from_user and not getattr(message, "sender_chat", None):
        return
    # обрабатываем сообщения с текстом, подписью, медиа или кнопками (иначе стикеры/фото без подписи не проверяются)
    if not (message.text or message.caption or has_media(message) or has_buttons(message)):
        return

    # Капча на паузе
    # from app.handlers.first_message_captcha import check_first_message_captcha
    # if await check_first_message_captcha(message):
    #     return

    async with await get_session() as session:
        try:
            if message.from_user:
                from app.services.chat_cleanup import record_seen_member as record_seen_member_cleanup
                await record_seen_member_cleanup(session, message.chat.id, message.from_user.id)
            v = await evaluate(session, message, edited=edited)
            if not v.should_act:
                return

            ok_action, action_label, deleted_ok = await apply_action(message, v)
            await send_log(
                session,
                message,
                v,
                action_label=action_label,
                ok_action=ok_action,
                deleted_ok=deleted_ok,
            )
            if deleted_ok:
                rule = await get_rule(session, message.chat.id)
                await maybe_send_public_alert(
                    message.bot, message.chat.id, rule, v.reason, v.action, session
                )
            # ТЗ Напоминания: активность чата для Guardian-сообщений раз в 3 дня
            chat_row = await session.get(Chat, message.chat.id)
            if chat_row:
                from datetime import datetime, timezone
                chat_row.last_activity_at = datetime.now(timezone.utc)
            await session.commit()
        except Exception as e:
            logger.exception(f"[pipeline error] chat={message.chat.id} msg={message.message_id}: {e}")


# =========================================================
# Handlers
# =========================================================

@router.chat_member(F.chat.type.in_({"group", "supergroup"}))
async def on_chat_member(event: ChatMemberUpdated):
    """Вход: запись времени в БД (тишина) + LRU; выход — сброс. Антинакрутка."""
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    chat_id = event.chat.id
    bot = event.bot

    leave_user = getattr(event.old_chat_member, "user", None)
    join_user = getattr(event.new_chat_member, "user", None)

    if old in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    ) and new in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        if leave_user:
            try:
                async with await get_session() as session:
                    await delete_member_join_marker(session, chat_id, leave_user.id)
                    await session.commit()
                SILENCE_JOIN_LRU.pop((chat_id, leave_user.id), None)
            except Exception as e:
                logger.exception("on_chat_member leave: %s", e)
        return

    if old not in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        return
    if new not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        return
    user = join_user
    if not user:
        return
    user_id = user.id
    try:
        async with await get_session() as session:
            chat_row = await session.get(Chat, chat_id)
            if not chat_row or not getattr(chat_row, "is_active", True):
                return
            await record_seen_member_cleanup(session, chat_id, user_id)

            rule = await get_rule(session, chat_id)
            if bool(getattr(rule, "use_global_antispam_db", False)):
                if await is_in_global_antispam(session, user_id):
                    try:
                        await bot.ban_chat_member(chat_id, user_id)
                    except Exception as e:
                        logger.debug("global_antispam kick %s: %s", user_id, e)
                    return
            await upsert_member_join_for_silence(session, chat_id, user_id)
            _silence_join_record(chat_id, user_id)
            await session.commit()

            enabled = bool(getattr(rule, "antinakrutka_enabled", False))
            if not enabled:
                return
            threshold = max(2, min(100, int(getattr(rule, "antinakrutka_joins_threshold", 10) or 10)))
            window_min = max(1, min(60, int(getattr(rule, "antinakrutka_window_minutes", 5) or 5)))
            action = (getattr(rule, "antinakrutka_action", None) or "alert").strip().lower()
            restrict_min = max(1, min(1440, int(getattr(rule, "antinakrutka_restrict_minutes", 30) or 30)))

            joins_list = _antinakrutka_add_join(chat_id, user_id, window_min)
            if len(joins_list) < threshold:
                return

            # Срабатывание: массовый вход
            chat_title = (event.chat.title or "").strip() or str(chat_id)
            log_chat_id = getattr(chat_row, "log_chat_id", None)
            alert_text = (
                f"⚠ *Антинакрутка*\n\n"
                f"Обнаружен массовый вход в чат *{chat_title}*.\n"
                f"За последние *{window_min}* мин вступило *{len(joins_list)}* участников (порог {threshold})."
            )
            if log_chat_id:
                try:
                    await bot.send_message(log_chat_id, alert_text, parse_mode="Markdown")
                except Exception as e:
                    logger.warning("antinakrutka log send: %s", e)
            try:
                await bot.send_message(chat_id, alert_text, parse_mode="Markdown")
            except Exception as e:
                logger.debug("antinakrutka chat send: %s", e)

            if action == "alert_restrict":
                until = datetime.now(timezone.utc) + timedelta(minutes=restrict_min)
                for uid, _ in joins_list:
                    if uid == user_id or await is_admin(bot, chat_id, uid):
                        continue
                    try:
                        await bot.restrict_chat_member(
                            chat_id,
                            uid,
                            permissions=ChatPermissions(can_send_messages=False),
                            until_date=until,
                        )
                    except Exception as e:
                        logger.debug("antinakrutka restrict %s: %s", uid, e)

            _antinakrutka_clear(chat_id)
    except Exception as e:
        logger.exception("on_chat_member: %s", e)


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.func(_should_run_moderation_pipeline),
)
async def on_message(message: Message):
    await pipeline(message, edited=False)

@router.edited_message(
    F.chat.type.in_({"group", "supergroup"}),
    F.func(_should_run_moderation_pipeline),
)
async def on_edit(message: Message):
    await pipeline(message, edited=True)
