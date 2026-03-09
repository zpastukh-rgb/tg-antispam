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
from aiogram.types import Message, ChatPermissions
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select

from app.db.session import get_session
from app.db.models import Chat, Rule, StopWord, WhitelistDomain, WhitelistUser
from app.services.public_alerts import maybe_send_public_alert

router = Router()
logger = logging.getLogger(__name__)

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
# - Newbie: LRU+TTL вместо бесконечного dict (фикс RAM на сотнях чатов)
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
# ✅ FIX RAM + SPEED: Newbie memory (LRU + TTL)
# =========================================================
NEWBIE_LRU: "OrderedDict[Tuple[int, int], datetime]" = OrderedDict()
NEWBIE_LRU_MAX = 200_000
NEWBIE_TTL = timedelta(days=2)

def _newbie_cleanup(now: datetime) -> None:
    while NEWBIE_LRU:
        _k, ts = next(iter(NEWBIE_LRU.items()))
        if now - ts <= NEWBIE_TTL:
            break
        NEWBIE_LRU.popitem(last=False)

def _newbie_seen(chat_id: int, user_id: int) -> datetime:
    now = datetime.now(timezone.utc)
    _newbie_cleanup(now)

    key = (chat_id, user_id)
    if key not in NEWBIE_LRU:
        NEWBIE_LRU[key] = now

    NEWBIE_LRU.move_to_end(key)

    while len(NEWBIE_LRU) > NEWBIE_LRU_MAX:
        NEWBIE_LRU.popitem(last=False)

    return NEWBIE_LRU[key]

def _is_newbie(chat_id: int, user_id: int, window_min: int) -> bool:
    if window_min <= 0:
        return False
    first_seen = _newbie_seen(chat_id, user_id)
    return (datetime.now(timezone.utc) - first_seen) <= timedelta(minutes=window_min)


# =========================================================
# ✅ TTL caches (DB load fix for big scale)
# =========================================================
CACHE_TTL = 60  # seconds

_STOPWORDS_CACHE: Dict[int, Tuple[float, Set[str]]] = {}
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

def stopword_hit(text_norm: str, stopwords: Set[str]) -> Optional[str]:
    if not stopwords:
        return None
    toks = token_set(text_norm)
    for w in stopwords:
        ww = (w or "").strip().lower().replace("ё", "е")
        if ww and ww in toks:
            return ww
    return None

def find_links(text: str) -> List[str]:
    return [m.group(1) for m in URL_RE.finditer(text or "")]

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

    # do not touch admins
    if user and await is_admin(message.bot, chat_id, user_id):
        return Verdict(False, "admin_skip", "", "delete", log_it=False)

    # do not touch whitelisted users
    if user and await whitelist_user(session, chat_id, user_id):
        return Verdict(False, "whitelist_user", "", "delete", log_it=False)

    text = message.text or message.caption or ""
    text_norm = normalize(text)

    # base action
    action = (getattr(rule, "action_mode", "delete") or "delete").lower()
    if action not in ("delete", "mute", "ban"):
        action = "delete"

    mute_min = int(getattr(rule, "mute_minutes", 30) or 30)
    mute_min = max(1, min(1440, mute_min))

    # toggles
    filter_links = bool(getattr(rule, "filter_links", True))
    filter_mentions = bool(getattr(rule, "filter_mentions", True))
    anti_edit = bool(getattr(rule, "anti_edit", True))
    newbie_enabled = bool(getattr(rule, "newbie_enabled", True))
    newbie_window = int(getattr(rule, "newbie_minutes", 10) or 10)
    newbie_window = max(0, min(1440, newbie_window))
    log_enabled = bool(getattr(rule, "log_enabled", True))

    newbie = newbie_enabled and _is_newbie(chat_id, user_id, newbie_window)

    # -------------------------------------------------
    # 1) stopwords
    # -------------------------------------------------
    stopwords = await load_stopwords(session, chat_id)
    hit = stopword_hit(text_norm, stopwords)
    if hit:
        if newbie and action == "delete":
            return Verdict(
                True, "stopword_newbie", hit, "mute",
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=f"newbie окно {newbie_window} мин" + (" | anti-edit" if edited else ""),
            )
        return Verdict(
            True, "stopword", hit, action,
            mute_minutes=mute_min,
            log_it=log_enabled,
            log_extra=("anti-edit" if edited else ""),
        )

    # -------------------------------------------------
    # 2) links
    # -------------------------------------------------
    if filter_links:
        links = find_links(text)
        if links:
            domains = extract_domains(text)

            allowed = False
            for d in domains:
                if d == "tg://":
                    continue
                if await whitelist_domain(session, chat_id, d):
                    allowed = True
                    break

            if not allowed:
                if newbie and action == "delete":
                    return Verdict(
                        True, "link_newbie", links[0], "mute",
                        mute_minutes=mute_min,
                        log_it=log_enabled,
                        log_extra=f"newbie окно {newbie_window} мин" + (" | anti-edit" if edited else ""),
                    )
                return Verdict(
                    True, "link", links[0], action,
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
            if newbie and action == "delete":
                return Verdict(
                    True, "mention_newbie", mentions[0], "mute",
                    mute_minutes=mute_min,
                    log_it=log_enabled,
                    log_extra=f"newbie окно {newbie_window} мин" + (" | anti-edit" if edited else ""),
                )

            return Verdict(
                True, "mention", mentions[0], action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )

    # -------------------------------------------------
    # 4) anti-edit (сам факт правки — не преступление)
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
    "link": "🔗 ссылка",
    "link_newbie": "🔗 ссылка (новичок)",
    "mention": "🏷 упоминание",
    "mention_newbie": "🏷 упоминание (новичок)",
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
    except Exception as e:
        logger.warning(f"[log send failed] chat={message.chat.id} -> log_chat={log_chat_id}: {e}")


# =========================================================
# Pipeline
# =========================================================
async def pipeline(message: Message, *, edited: bool = False) -> None:
    # если сообщение от имени канала/чата — from_user может быть None
    if not message.from_user and not getattr(message, "sender_chat", None):
        return
    if not (message.text or message.caption):
        return

    async with await get_session() as session:
        try:
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
        except Exception as e:
            logger.exception(f"[pipeline error] chat={message.chat.id} msg={message.message_id}: {e}")


# =========================================================
# Handlers
# =========================================================

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def on_message(message: Message):
    if message.text and message.text.startswith("/"):
        return
    await pipeline(message, edited=False)

@router.edited_message(F.chat.type.in_({"group", "supergroup"}))
async def on_edit(message: Message):
    await pipeline(message, edited=True)
