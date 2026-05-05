# app/handlers/moderation.py
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from aiogram import Router, F
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import DeleteMessage
from aiogram.types import Message, ChatPermissions, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, WebAppInfo, ReplyParameters
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import delete, select, func, desc, text

from app.db.session import get_session
from app.db.ensure_defaults import (
    DEFAULT_ADS_ROOTS,
    DEFAULT_CASINO_ROOTS,
    DEFAULT_INSULT_ROOTS,
    DEFAULT_JOBS_ROOTS,
    DEFAULT_NAZI_ROOTS,
    DEFAULT_PROFANITY_ROOTS,
    DEFAULT_RACISM_ROOTS,
    DEFAULT_VULGAR_ROOTS,
)
from app.moderation_lexicon import root_matches_token
from app.db.models import (
    Chat,
    Rule,
    User,
    StopWord,
    WhitelistDomain,
    WhitelistUser,
    WhitelistSenderChat,
    LinkBlacklist,
    ModerationLog,
    ProfanityWord,
    NewMember,
    MemberLeft,
    ChatActivityEvent,
    ChatSpikeAlert,
    ChatReputationWord,
    ChatReputationScore,
    ChatReputationEvent,
)
from app.services.public_alerts import maybe_send_public_alert
from app.services.global_bad_urls import get_effective_global_bad_url_patterns
from app.services.admin_roles import is_full_admin_user as _is_full_admin_user_role
from app.services.chat_cleanup import record_seen_member as record_seen_member_cleanup
from app.services.global_antispam import is_in_global_antispam
from app.services.spam_spike_notify import SPAM_MODERATION_REASONS, trigger_spam_spike_for_chat
from app.services.telegram_notify import send_user_dm
from app.services.group_connect_actor import is_post_as_linked_channel_in_discussion
from app.services.telegram_bot_api import (
    tg_pin_chat_message,
    tg_send_message,
    tg_try_delete_pin_service_messages,
)
from app.services.diagnostics_incidents import (
    record_bot_delete_message_failed,
    record_moderation_restrict_failed,
)

router = Router()
logger = logging.getLogger(__name__)
REPUTATION_DEFAULT_WORDS: tuple[str, ...] = (
    "спасибо", "thank", "thanks", "tnx", "благодарю", "благодарствую", "++", "+1", "👍", "🤝", "рахмет",
)
REPUTATION_PAIR_COOLDOWN = timedelta(hours=6)


def _welcome_media_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "welcome-media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _welcome_keyboard_from_json(raw: str | None) -> InlineKeyboardMarkup | None:
    if not raw:
        return None
    try:
        rows = json.loads(str(raw))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    kb_rows: list[list[InlineKeyboardButton]] = []
    for row in rows[:6]:
        if not isinstance(row, list):
            continue
        out_row: list[InlineKeyboardButton] = []
        for btn in row[:4]:
            if not isinstance(btn, dict):
                continue
            text = str(btn.get("text") or "").strip()[:64]
            if not text:
                continue
            url = str(btn.get("url") or "").strip()[:512]
            # Для приветствия в группах оставляем только URL-кнопки:
            # web_app/callback у части чатов дают BUTTON_TYPE_INVALID.
            if url:
                out_row.append(InlineKeyboardButton(text=text, url=url))
        if out_row:
            kb_rows.append(out_row)
    if not kb_rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

# Редкий лог: чат в БД, но не подключён (is_active=False) — модерация не работает.
_INACTIVE_CHAT_LOG_TS: Dict[int, float] = {}
_INACTIVE_CHAT_LOG_TTL_SEC = 3600.0
# Чат -> временная серия модераций delete/mute/ban для immediate spike-check.
_WELCOME_RATE_LRU: Dict[int, deque[float]] = {}
_RULES_COMMENT_THREAD_STATE: Dict[tuple, dict] = {}


def _debug_admin_ids() -> set[int]:
    out: set[int] = set()
    for part in (os.getenv("ADMIN_TELEGRAM_IDS") or "").split(","):
        p = (part or "").strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except Exception:
            continue
    return out


def _rules_keyboard_from_json(raw: str | None) -> InlineKeyboardMarkup | None:
    if not raw:
        return None
    try:
        rows = json.loads(str(raw))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    kb_rows: list[list[InlineKeyboardButton]] = []
    for row in rows[:8]:
        if not isinstance(row, list):
            continue
        out_row: list[InlineKeyboardButton] = []
        for btn in row[:6]:
            if not isinstance(btn, dict):
                continue
            text = str(btn.get("text") or "").strip()[:64]
            if not text:
                continue
            url = str(btn.get("url") or "").strip()[:512]
            wu = str(btn.get("web_app_url") or "").strip()[:512]
            cb = str(btn.get("callback_data") or "").strip()[:64]
            if url:
                out_row.append(InlineKeyboardButton(text=text, url=url))
            elif wu and (wu.startswith("https://") or wu.startswith("http://")):
                out_row.append(InlineKeyboardButton(text=text, web_app=WebAppInfo(url=wu)))
            elif cb:
                out_row.append(InlineKeyboardButton(text=text, callback_data=cb))
        if out_row:
            kb_rows.append(out_row)
    if not kb_rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def _rules_media_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "rules-media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _should_apply_rules_in_channel_comment_thread(message: Message) -> bool:
    """
    Правила для «комментов канала» должны срабатывать в треде поста, а не в «Общем» топике форума.

    Эвристика:
    - у форум-обсуждений General topic обычно thread_id=1;
    - треды постов — thread_id>1 (или thread_id=1, но есть явный контекст комментария к посту канала);
    - для не-форума message_thread_id обычно не используется как «топик», поэтому не режем по thread_id=1.
    - в связанном обсуждении без топиков ответ на пост канала может иметь thread_id=0 — тогда ориентируемся на _is_channel_comment_context.
    """
    chat = getattr(message, "chat", None)
    is_forum = bool(getattr(chat, "is_forum", False))
    thread_id = int(getattr(message, "message_thread_id", 0) or 0)

    if _is_channel_comment_context(message):
        if is_forum and thread_id == 1:
            return False
        return True

    if thread_id <= 0:
        return False
    if is_forum:
        if thread_id == 1:
            return False
        return True
    return True


def _is_rules_channel_discussion_anchor(message: Message) -> bool:
    """
    «Якорь» обсуждения поста канала: копия поста в группе без обычного from_user.
    Без обработки таких сообщений правила никогда не отправятся, пока кто-то не напишет в тред.
    """
    if not _is_channel_comment_context(message):
        return False
    if bool(getattr(message, "is_automatic_forward", False)):
        return True
    sc = getattr(message, "sender_chat", None)
    if sc and str(getattr(sc, "type", "") or "").lower() == "channel":
        return True
    return False


def _rules_comment_thread_state_key(message: Message, chat_id: int, thread_id: int) -> Optional[tuple]:
    """Стабильный ключ «один раз на обсуждение поста»: топик или якорь reply_to."""
    if thread_id > 0:
        return (chat_id, "tid", thread_id)
    r = getattr(message, "reply_to_message", None)
    rid = int(getattr(r, "message_id", 0) or 0) if r else 0
    if rid > 0:
        return (chat_id, "reply", rid)
    # Копия поста канала в обсуждении (часто без reply_to и с thread_id=0)
    if _is_rules_channel_discussion_anchor(message):
        mid = int(getattr(message, "message_id", 0) or 0)
        if mid > 0:
            return (chat_id, "anchor", mid)
    return None


async def _maybe_handle_channel_comment_rules(message: Message) -> None:
    chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
    if chat_id == 0:
        return
    if message.from_user and bool(getattr(message.from_user, "is_bot", False)):
        return
    # Обычные сообщения — только от людей; якорь поста канала в обсуждении — без from_user.
    if not message.from_user and not _is_rules_channel_discussion_anchor(message):
        return
    thread_id = int(getattr(message, "message_thread_id", 0) or 0)
    if not _should_apply_rules_in_channel_comment_thread(message):
        return
    # В обычном linked-discussion thread_id может быть 0 — отвечаем на сообщение, чтобы остаться в цепочке комментария к посту.
    send_thread_id = thread_id if thread_id > 0 else None
    reply_anchor_id = int(getattr(message, "message_id", 0) or 0)
    async with await get_session() as session:
        rule = await get_rule(session, chat_id)
        if not bool(getattr(rule, "rules_channel_enabled", False)):
            return
        text_value = str(getattr(rule, "rules_channel_text", "") or "").strip()
        if not text_value:
            return
        key = _rules_comment_thread_state_key(message, chat_id, thread_id)
        if key is None:
            return
        now = datetime.now(timezone.utc)
        state = _RULES_COMMENT_THREAD_STATE.get(key) or {}
        blocked_until = state.get("blocked_until")
        if isinstance(blocked_until, datetime) and blocked_until > now:
            return
        expires_at = state.get("expires_at")
        rules_message_id = int(state.get("rules_message_id", 0) or 0)
        # Отправляем "первый комментарий с правилами" только один раз на тред.
        # После истечения окна удаления не переотправляем снова на каждое новое сообщение.
        if not state:
            markup = _rules_keyboard_from_json(getattr(rule, "rules_channel_buttons_json", None))
            try:
                send_kw = dict(chat_id=chat_id, parse_mode="HTML", reply_markup=markup)
                if send_thread_id is not None:
                    send_kw["message_thread_id"] = send_thread_id
                elif reply_anchor_id > 0:
                    send_kw["reply_parameters"] = ReplyParameters(message_id=reply_anchor_id)
                rel = str(getattr(rule, "rules_channel_photo_path", "") or "").strip()
                photo_file_id = str(getattr(rule, "rules_channel_photo_file_id", "") or "").strip()
                sent = None
                fp = None
                if rel:
                    pp = (_rules_media_root() / rel).resolve()
                    root = _rules_media_root().resolve()
                    if pp.exists() and pp.is_file() and (root in pp.parents or pp == root):
                        fp = pp
                if photo_file_id or fp is not None:
                    def _source():
                        return photo_file_id if photo_file_id else FSInputFile(str(fp))
                    source_name = "file_id" if photo_file_id else str(fp)
                    try:
                        sent = await message.bot.send_photo(
                            photo=_source(),
                            caption=text_value,
                            **send_kw,
                        )
                    except (TelegramBadRequest, TelegramForbiddenError) as e:
                        logger.warning(
                            "rules_channel_comment_send_photo_failed chat=%s thread=%s src=%s err=%s",
                            chat_id,
                            thread_id,
                            source_name,
                            e,
                        )
                        try:
                            sent = await message.bot.send_photo(
                                chat_id=chat_id,
                                photo=_source(),
                                message_thread_id=send_thread_id if send_thread_id is not None else None,
                                reply_parameters=None if send_thread_id is not None else (ReplyParameters(message_id=reply_anchor_id) if reply_anchor_id > 0 else None),
                            )
                            sent = await message.bot.send_message(
                                text=text_value,
                                disable_web_page_preview=True,
                                **send_kw,
                            )
                        except Exception:
                            sent = None
                if sent is None:
                    sent = await message.bot.send_message(
                        text=text_value,
                        disable_web_page_preview=True,
                        **send_kw,
                    )
            except TelegramRetryAfter as e:
                retry_sec = max(1, int(getattr(e, "retry_after", 0) or 0))
                _RULES_COMMENT_THREAD_STATE[key] = {
                    "expires_at": now,
                    "rules_message_id": 0,
                    "blocked_until": now + timedelta(seconds=retry_sec + 1),
                }
                logger.warning(
                    "rules_channel_comment_send_retry_after chat=%s thread=%s retry=%ss",
                    chat_id,
                    thread_id,
                    retry_sec,
                )
                return
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                logger.warning(
                    "rules_channel_comment_send_failed chat=%s thread=%s err=%s",
                    chat_id,
                    thread_id,
                    e,
                )
                return
            except Exception as e:
                _RULES_COMMENT_THREAD_STATE[key] = {
                    "expires_at": now,
                    "rules_message_id": 0,
                    "blocked_until": now + timedelta(seconds=15),
                }
                logger.exception(
                    "rules_channel_comment_send_failed chat=%s thread=%s err=%s",
                    chat_id,
                    thread_id,
                    e,
                )
                return
            rules_message_id = int(getattr(sent, "message_id", 0) or 0)
            try:
                ttl = max(0, min(600, int(getattr(rule, "rules_channel_delete_window_sec", 0) or 0)))
            except Exception:
                ttl = 0
            _RULES_COMMENT_THREAD_STATE[key] = {
                "expires_at": now + timedelta(seconds=ttl) if ttl > 0 else now,
                "rules_message_id": rules_message_id,
            }
            if len(_RULES_COMMENT_THREAD_STATE) > 3000:
                stale_keys = [k for k, v in _RULES_COMMENT_THREAD_STATE.items() if (v.get("expires_at") or now) <= now]
                for k in stale_keys[:1000]:
                    _RULES_COMMENT_THREAD_STATE.pop(k, None)
        state = _RULES_COMMENT_THREAD_STATE.get(key) or {}
        expires_at = state.get("expires_at")
        if not isinstance(expires_at, datetime) or expires_at <= now:
            return
        if int(getattr(message, "message_id", 0) or 0) == int(state.get("rules_message_id", 0) or 0):
            return
        # Никогда не удаляем якорь обсуждения поста канала (иначе схлопывается тред),
        # даже если он пришёл как from_user=777000.
        if _is_rules_channel_discussion_anchor(message):
            return
        fu = message.from_user
        if not fu:
            return
        if int(getattr(fu, "id", 0) or 0) == 777000:
            return
        if bool(getattr(fu, "is_bot", False)):
            return
        if await is_admin(message.bot, chat_id, int(fu.id)):
            return
        try:
            await message.delete()
        except Exception:
            pass


async def _send_spike_debug(bot, text: str, extra_ids: list[int] | None = None) -> None:
    if str(os.getenv("SPAM_SPIKE_DEBUG_DM", "0")).strip().lower() not in ("1", "true", "yes", "on"):
        return
    targets = set(_debug_admin_ids())
    for x in (extra_ids or []):
        try:
            xid = int(x or 0)
        except Exception:
            xid = 0
        if xid > 0:
            targets.add(xid)
    for aid in sorted(targets):
        try:
            await bot.send_message(int(aid), text)
        except Exception:
            try:
                await send_user_dm(int(aid), text, parse_mode="Markdown")
            except Exception:
                pass


def _should_run_moderation_pipeline(message: Message) -> bool:
    """Команды (/...) обрабатываются другими роутерами; иначе catch-all moderation перехватывает апдейт до panel."""
    chunk = (message.text or message.caption or "").lstrip()
    return not chunk.startswith("/")


def _bool_or_default(value, default: bool) -> bool:
    """
    Безопасная булева интерпретация:
    - None -> default
    - True/False -> как есть
    """
    if value is None:
        return default
    return bool(value)

# =========================================================
# 😈 AntiSpam Guard — MODERATION CORE (Step A "железобетон")
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


async def _in_newbie_period(session, chat_id: int, user_id: int, newbie_minutes: int) -> bool:
    """Первые N минут после входа (та же отметка входа, что и для режима тишины)."""
    if newbie_minutes <= 0:
        return False
    join_at = await _silence_join_at_db(session, chat_id, user_id)
    if join_at is None:
        key = (chat_id, user_id)
        if key not in SILENCE_JOIN_LRU:
            return False
        join_at = _naive_utc(SILENCE_JOIN_LRU[key])
    now = datetime.now(timezone.utc)
    return now - join_at <= timedelta(minutes=newbie_minutes)


_NB_FILTER_REASONS = frozenset(
    {
        "stopword",
        "profanity",
        "jobs",
        "casino",
        "link",
        "link_blacklist",
        "global_bad_url",
        "mention",
        "media",
        "buttons",
    }
)


def _with_newbie_reason(reason: str, in_newbie_window: bool) -> str:
    if in_newbie_window and reason in _NB_FILTER_REASONS:
        return f"{reason}_newbie"
    return reason


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
_REPUTATION_WORDS_CACHE: Dict[int, Tuple[float, Set[str]]] = {}


def invalidate_stopwords_cache(chat_id: int) -> None:
    """Сброс кэша после изменения стоп-слов (иначе до ~60 с действуют старые данные)."""
    try:
        _STOPWORDS_CACHE.pop(int(chat_id), None)
    except Exception:
        pass


def invalidate_reputation_words_cache(chat_id: int) -> None:
    try:
        _REPUTATION_WORDS_CACHE.pop(int(chat_id), None)
    except Exception:
        pass


def invalidate_whitelist_cache(chat_id: int) -> None:
    """Сброс TTL-кэша whitelist после правок из Mini App / команд."""
    cid = int(chat_id)
    for k in list(_WLDOM_CACHE.keys()):
        if k[0] == cid:
            _WLDOM_CACHE.pop(k, None)
    for k in list(_WLUSER_CACHE.keys()):
        if k[0] == cid:
            _WLUSER_CACHE.pop(k, None)
    for k in list(_WLSENDER_CACHE.keys()):
        if k[0] == cid:
            _WLSENDER_CACHE.pop(k, None)
    _WL_PAT_CACHE.pop(cid, None)
    _LINK_BL_CACHE.pop(cid, None)


_PROFANITY_CACHE: Tuple[float, Set[str]] = (0.0, set())  # (ts, words) глобальный список мата
_WLUSER_CACHE: "OrderedDict[Tuple[int, int], Tuple[float, bool]]" = OrderedDict()
_WLDOM_CACHE: "OrderedDict[Tuple[int, str], Tuple[float, bool]]" = OrderedDict()
_WLSENDER_CACHE: "OrderedDict[Tuple[int, str], Tuple[float, bool]]" = OrderedDict()
_WL_PAT_CACHE: Dict[int, Tuple[float, Tuple[str, ...]]] = {}
_LINK_BL_CACHE: Dict[int, Tuple[float, Tuple[str, ...]]] = {}

_CACHE_MAX = 200_000  # ограничитель памяти

def _cache_prune(d: "OrderedDict", now: float, ttl: float) -> None:
    # TTL с головы
    while d:
        _k, (ts, _v) = next(iter(d.items()))
        if now - ts <= ttl:
            break
        d.popitem(last=False)


def _welcome_rate_allowed(chat_id: int, max_per_min: int) -> bool:
    limit = int(max_per_min or 0)
    if limit <= 0:
        return True
    now_ts = time.time()
    q = _WELCOME_RATE_LRU.get(int(chat_id))
    if q is None:
        q = deque()
        _WELCOME_RATE_LRU[int(chat_id)] = q
    while q and now_ts - q[0] > 60.0:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now_ts)
    # простая зачистка памяти
    if len(_WELCOME_RATE_LRU) > 2000:
        stale = [cid for cid, dq in _WELCOME_RATE_LRU.items() if not dq or now_ts - dq[-1] > 3600]
        for cid in stale[:500]:
            _WELCOME_RATE_LRU.pop(cid, None)
    return True
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
    action: str  # delete|mute|ban|observe
    mute_minutes: int = 0
    log_it: bool = True
    log_extra: str = ""


# =========================================================
# Text helpers
# =========================================================
def normalize(text: str) -> str:
    return (text or "").strip().lower().replace("ё", "е")


def _normalize_reputation_word(value: str) -> str:
    return normalize(value)[:64]


def _text_has_reputation_trigger(text_value: str, trigger_words: set[str]) -> bool:
    raw = normalize(text_value)
    if not raw:
        return False
    compact = re.sub(r"\s+", " ", raw)
    for w in trigger_words:
        if not w:
            continue
        if w in ("++", "+1"):
            if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", compact):
                return True
            continue
        if any(ch in w for ch in "👍🤝"):
            if w in compact:
                return True
            continue
        if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", compact):
            return True
    return False


async def _reputation_target_user_id(session, message: Message) -> int | None:
    actor_id = int(getattr(getattr(message, "from_user", None), "id", 0) or 0)
    if actor_id <= 0:
        return None
    rep = getattr(message, "reply_to_message", None)
    if rep and getattr(rep, "from_user", None):
        rid = int(getattr(rep.from_user, "id", 0) or 0)
        if rid > 0 and rid != actor_id and not bool(getattr(rep.from_user, "is_bot", False)):
            return rid
    raw_text = str(getattr(message, "text", "") or getattr(message, "caption", "") or "")
    mention_matches = re.findall(r"(?<!\w)@([A-Za-z0-9_]{5,32})", raw_text)
    if not mention_matches:
        return None
    seen: set[str] = set()
    ordered = []
    for uname in mention_matches:
        u = str(uname or "").strip().lower()
        if not u or u in seen:
            continue
        seen.add(u)
        ordered.append(u)
    if not ordered:
        return None
    from app.services.pii_user_store import pii_map_username_lowers_to_telegram_ids, pii_storage_enabled

    if pii_storage_enabled():
        by_username = await pii_map_username_lowers_to_telegram_ids(ordered)
    else:
        q = await session.execute(
            select(User.telegram_id, User.username).where(func.lower(User.username).in_(ordered))
        )
        by_username = {}
        for tg_id, username in q.all():
            k = str(username or "").strip().lower()
            if k and int(tg_id or 0) > 0:
                by_username[k] = int(tg_id)
    for uname in ordered:
        uid = int(by_username.get(uname, 0) or 0)
        if uid > 0 and uid != actor_id:
            return uid
    return None

def _normalize_action_mode(raw: str | None) -> str:
    """
    Нормализует режим наказания из БД/UI к delete|mute|ban|observe.
    Защищает от нестандартных строк вроде "мут", "mute + delete", "бан".
    """
    v = normalize(str(raw or ""))
    if "observe" in v or "замеч" in v or "наблюд" in v or "log_only" in v or "logonly" in v.replace(" ", ""):
        return "observe"
    if "ban" in v or "бан" in v:
        return "ban"
    if "mute" in v or "мут" in v:
        return "mute"
    if "delete" in v or "удал" in v:
        return "delete"
    return "delete"


_SPAM_CHAR_MAP = str.maketrans({
    # Латиница -> кириллица (частые визуальные подмены)
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у", "k": "к", "m": "м", "t": "т", "b": "в", "h": "н",
    "@": "а",
    "$": "с",
    "0": "о",
    "1": "и",
    "3": "з",
    "4": "а",
    "5": "с",
    "6": "б",
    "7": "т",
    "8": "в",
    "9": "д",
})


def normalize_spam_text(text: str) -> str:
    """Нормализация обходов: з@р@б0т0к, л.с, bиo и т.п."""
    t = normalize(text).translate(_SPAM_CHAR_MAP)
    # Убираем частые разделители для склейки «л.с», «в_био», «з-а-р-а-б».
    t = re.sub(r"[.\-_/\\|*]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


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
        if not ww:
            continue
        # Фраза из нескольких слов — ищем подстроку в нормализованном тексте (как для «мат»-фраз).
        if " " in ww:
            if ww in base:
                return ww
            continue
        if ww in toks:
            return ww
    return None


def profanity_hit(text_norm: str, profanity_words: Set[str], text_without_urls_norm: Optional[str] = None) -> Optional[str]:
    """Проверка по словарю корней/слов: мат + спам-тематики (по токенам, без URL)."""
    if not profanity_words:
        return None
    base = (text_without_urls_norm if text_without_urls_norm is not None else text_norm)
    base_loose = normalize_spam_text(base)
    toks = token_set(base)
    toks_loose = token_set(base_loose)
    for w in profanity_words:
        ww = (w or "").strip().lower().replace("ё", "е")
        if not ww:
            continue
        ww_loose = normalize_spam_text(ww)
        # Явная фраза (с пробелом) — ищем подстроку в нормализованном тексте.
        if " " in ww:
            if ww in base or ww_loose in base_loose:
                return ww
            continue
        # Очень короткие шаблоны держим строже.
        if len(ww) <= 2:
            if ww in toks or ww_loose in toks_loose:
                return ww
            continue
        # Корень: токен целиком / префикс / (осторожно) подстрока — см. root_matches_token и moderation_lexicon.
        for t in toks:
            if root_matches_token(ww, t):
                return ww
        # «bet» после normalize_spam_text на корне даёт «вет»; root_matches_token("вет", t)
        # использует подстроку и режет «рассвет», «исоветская» (1→и), «…совет…» и т.д.
        if ww in ("bet", "бет"):
            for t in toks_loose:
                if root_matches_token("bet", t) or root_matches_token("бет", t):
                    return ww
                if t == "вет":
                    return ww
            continue
        for t in toks_loose:
            if root_matches_token(ww_loose, t):
                return ww
    return None


_MONEY_RE = re.compile(
    r"(?ix)\b(?:\d{2,6}\s*(?:k|к|\+|к\+|тыс|тысяч|р|руб|рублей|\$|usd|доллар(?:ов|а)?)|"
    r"\d{2,6}\s*[–-]\s*\d{2,6}\s*(?:\$|usd|доллар(?:ов|а)?|р|руб(?:лей)?)|"
    r"(?:от|до|минимум)\s*\d{2,6})\b"
)

_EARN_RE = re.compile(r"(?iu)\b(?:заработ(?:ок|ать|аю|аем|аете|ывать|ывай|аешь|аете|али|ка|ку|ком)|подзаработ)\w*\b")


def jobs_offer_hit(text_norm: str, text_without_urls_norm: Optional[str] = None) -> Optional[str]:
    """
    Эвристика для «мутных подработок»: ловим связки
    (контакт в профиль/лс) + (обещание дохода) + (суммы/валюта) и частые шаблоны рекрутинга.
    """
    base = (text_without_urls_norm if text_without_urls_norm is not None else text_norm) or ""
    compact = normalize_spam_text(base)
    squashed = compact.replace(" ", "")
    if not compact:
        return None

    contact_cues = (
        "в био", "в профиле", "в профиль", "в личке", "в лс", "пиши в личку", "пиши мне",
        "отпишитесь", "смотри био", "смотри в био", "смотри описание", "за деталями", "в л.с", "био",
    )
    income_cues = (
        "заработ", "заработок", "заработать", "зарабатывать", "подзаработ", "доход", "выплаты",
        "без влож", "без трат", "пассивный доход",
        "пару людей", "пару халтур", "халтур", "подработка", "занятость", "график", "схема",
    )
    risky_templates = (
        "хочешь зарабатывать", "твой заработок начинается", "время менять жизнь",
        "можно делать от", "рабочий вариант", "осталось пару мест",
    )

    has_contact = any(c in compact for c in contact_cues) or any(c.replace(" ", "") in squashed for c in contact_cues)
    has_income = any(c in compact for c in income_cues) or any(c.replace(" ", "") in squashed for c in income_cues)
    has_money = bool(_MONEY_RE.search(compact)) or bool(_MONEY_RE.search(squashed))
    has_template = any(t in compact for t in risky_templates) or any(t.replace(" ", "") in squashed for t in risky_templates)
    has_earn_re = bool(_EARN_RE.search(compact)) or bool(_EARN_RE.search(squashed))

    # Базовый скоринг, чтобы не банить обычные бытовые фразы с одним словом «работа».
    score = int(has_contact) + int(has_income) + int(has_money) + int(has_template) + int(has_earn_re)
    if score >= 2 and (has_contact or has_money):
        return "jobs_offer_pattern"
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

    # Fallback: если regex/entities не сработали, но ссылка явно видна в сыром тексте.
    if not links:
        merged = f"{text}\n{caption}".strip()
        if merged:
            for token in re.split(r"\s+", merged):
                t = token.strip(" \t\r\n<>[](){}\"'.,!?;:")
                tl = t.lower()
                if (
                    tl.startswith("http://")
                    or tl.startswith("https://")
                    or tl.startswith("www.")
                    or "t.me/" in tl
                    or tl.startswith("tg://")
                ):
                    if t and t not in seen:
                        seen.add(t)
                        links.append(t)

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


def _entity_type_name(entity) -> str:
    t = getattr(entity, "type", None)
    if t is None:
        return ""
    if hasattr(t, "value"):
        return str(t.value)
    return str(t)


# ❗️старый find_mentions(text) больше не нужен — ловим через entities + regex fallback
def find_mentions_from_entities(message: Message) -> List[str]:
    out: List[str] = []

    def _scan(text: str, ents) -> None:
        if not ents:
            return
        content = text or ""
        for e in ents:
            et = _entity_type_name(e)
            off = int(getattr(e, "offset", 0) or 0)
            ln = int(getattr(e, "length", 0) or 0)
            if et == "mention":
                part = _slice_utf16(content, off, ln)
                if part:
                    out.append(part)
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
        filter_profanity_enabled=True,
        filter_jobs_enabled=True,
        filter_casino_enabled=True,
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


async def load_reputation_words(session, chat_id: int) -> Set[str]:
    now = time.time()
    cached = _REPUTATION_WORDS_CACHE.get(chat_id)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]
    res = await session.execute(select(ChatReputationWord.word).where(ChatReputationWord.chat_id == chat_id))
    custom = {_normalize_reputation_word(str(w or "")) for (w,) in res.all() if str(w or "").strip()}
    words = set(REPUTATION_DEFAULT_WORDS) | {w for w in custom if w}
    _REPUTATION_WORDS_CACHE[chat_id] = (now, words)
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


def _builtin_words(items: tuple[str, ...]) -> Set[str]:
    return {str(w).strip().lower().replace("ё", "е") for w in items if w}


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


async def whitelist_sender_chat_username(session, chat_id: int, username: str) -> bool:
    uname = str(username or "").strip().lstrip("@").lower()
    if not uname:
        return False
    now = time.time()
    key = (chat_id, uname)
    cached = _WLSENDER_CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        _WLSENDER_CACHE.move_to_end(key)
        return cached[1]
    res = await session.execute(
        select(WhitelistSenderChat.id).where(
            WhitelistSenderChat.chat_id == chat_id,
            WhitelistSenderChat.channel_username == uname,
        )
    )
    ok = res.first() is not None
    _WLSENDER_CACHE[key] = (now, ok)
    _WLSENDER_CACHE.move_to_end(key)
    _cache_prune(_WLSENDER_CACHE, now, CACHE_TTL)
    return ok


# =========================================================
# Decision Engine (single source of truth)
# =========================================================
def _is_channel_comment_context(message: Message) -> bool:
    """Сообщение в контексте комментария к посту канала (обсуждение канала)."""
    try:
        r = message.reply_to_message
        if r and getattr(r, "sender_chat", None):
            if str(getattr(r.sender_chat, "type", "") or "").lower() == "channel":
                return True
        if bool(getattr(message, "is_automatic_forward", False)):
            return True
        fo = getattr(message, "forward_origin", None)
        if fo is not None:
            tn = type(fo).__name__
            if "Channel" in tn:
                return True
        # Копия поста в официальном обсуждении: sender_chat = канал, id совпадает с linked_chat супергруппы.
        # Без этого якорь режется стоп-словами/ссылками по подписи поста — тред схлопывается вместе с правилами.
        ch = getattr(message, "chat", None)
        sc = getattr(message, "sender_chat", None)
        if ch and sc and str(getattr(ch, "type", "") or "").lower() in ("supergroup", "group"):
            link_id = int(getattr(ch, "linked_chat_id", 0) or 0)
            lc = getattr(ch, "linked_chat", None)
            if not link_id and lc:
                link_id = int(getattr(lc, "id", 0) or 0)
            scid = int(getattr(sc, "id", 0) or 0)
            st = str(getattr(sc, "type", "") or "").lower()
            if link_id > 0 and scid == link_id and "channel" in st:
                return True
    except Exception:
        pass
    return False


def _link_filter_scope_skips_message(message: Message, rule: Rule) -> bool:
    """
    channel_comments_only: не режем ссылки в «Общем» топике форума (id 1), режем в тредах постов
    и при явном ответе на пост канала. Без топиков (обычное обсуждение) — не отличить «болталку»,
    поэтому ссылки фильтруем везде (как раньше).
    """
    scope = str(getattr(rule, "filter_links_scope", None) or "all").strip().lower()
    if scope != "channel_comments_only":
        return False
    if _is_channel_comment_context(message):
        return False
    chat = message.chat
    if getattr(chat, "is_forum", False):
        tid = getattr(message, "message_thread_id", None)
        if tid is None or int(tid) == 1:
            return True
        return False
    return False


_LINK_MODES = frozenset(
    {
        "allow",
        "captcha",
        "forbid",
        "delete_all",
        "telegram_only",
        "smart",
        "open_blacklist",
        "allow_except_global",
    }
)


def _should_check_global_bad_urls(rule: Rule) -> bool:
    if bool(getattr(rule, "use_global_bad_urls", False)):
        return True
    if str(getattr(rule, "filter_links_mode", "") or "").strip().lower() == "allow_except_global":
        return True
    return False


def _link_flat_for_match(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = s.replace("https://", "").replace("http://", "")
    s = s.replace("www.", "")
    return s


def _link_allowed_by_trusted_pattern(raw: str, dom: Optional[str], patterns: Tuple[str, ...]) -> bool:
    if not patterns:
        return False
    flat = _link_flat_for_match(raw)
    raw_l = (raw or "").lower()
    d = (dom or "").lower()
    for pat in patterns:
        p = (pat or "").strip().lower()
        if not p:
            continue
        if "/" in p or p.startswith("t.me+"):
            if p in flat or p in raw_l:
                return True
        else:
            if d and (d == p or d.endswith("." + p)):
                return True
            if p in flat and (flat == p or flat.startswith(p + "/")):
                return True
    return False


def _url_hit_blacklist(raw: str, patterns: Tuple[str, ...]) -> Optional[str]:
    r = (raw or "").lower()
    if not r:
        return None
    for p in patterns:
        pat = (p or "").strip().lower()
        if pat and pat in r:
            return pat
    return None


def _is_telegram_link_url(raw: str, dom: Optional[str]) -> bool:
    d = (dom or "").lower()
    if d in ("t.me", "telegram.me", "telegram.dog"):
        return True
    return (raw or "").lower().startswith("tg://")


async def _smart_telegram_link_ok(bot, chat_id: int, raw: str, chat_row: Optional[Chat], user_id: int) -> bool:
    if not chat_row:
        return False
    un = (getattr(chat_row, "username", None) or "").strip().lstrip("@").lower()
    if not un:
        return False
    flat = _link_flat_for_match(raw)
    if flat == f"t.me/{un}" or flat.startswith(f"t.me/{un}/"):
        return True
    if flat == f"telegram.me/{un}" or flat.startswith(f"telegram.me/{un}/"):
        return True
    m = re.search(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([a-z0-9_]{2,64})\b", (raw or "").lower())
    if not m:
        return False
    handle = m.group(1)
    if handle.startswith("+"):
        return False
    if handle == un:
        return True
    if user_id <= 0:
        return False
    try:
        target = await bot.get_chat(f"@{handle}")
        tid = int(target.id)
        mem = await bot.get_chat_member(chat_id, tid)
        st = getattr(mem, "status", "")
        if hasattr(st, "value"):
            st = st.value
        return str(st).lower() in ("member", "administrator", "creator", "restricted")
    except Exception:
        return False


async def _load_trusted_patterns(session, chat_id: int) -> Tuple[str, ...]:
    now = time.time()
    c = _WL_PAT_CACHE.get(chat_id)
    if c and now - c[0] < CACHE_TTL:
        return c[1]
    res = await session.execute(
        select(WhitelistDomain.domain)
        .where(WhitelistDomain.chat_id == chat_id)
        .order_by(WhitelistDomain.domain.asc())
    )
    patterns = tuple(str(r[0]).strip().lower() for r in res.all() if r[0])
    _WL_PAT_CACHE[chat_id] = (now, patterns)
    return patterns


async def _load_blacklist_patterns(session, chat_id: int) -> Tuple[str, ...]:
    now = time.time()
    c = _LINK_BL_CACHE.get(chat_id)
    if c and now - c[0] < CACHE_TTL:
        return c[1]
    res = await session.execute(
        select(LinkBlacklist.pattern)
        .where(LinkBlacklist.chat_id == chat_id)
        .order_by(LinkBlacklist.pattern.asc())
    )
    patterns = tuple(str(r[0]).strip().lower() for r in res.all() if r[0])
    _LINK_BL_CACHE[chat_id] = (now, patterns)
    return patterns


async def _apply_link_policy(
    session,
    message: Message,
    chat_id: int,
    user: Optional[object],
    links: List[str],
    *,
    links_mode: str,
    newbie_win: bool,
    action: str,
    mute_min: int,
    log_enabled: bool,
    edited: bool,
) -> Optional[Verdict]:
    """Возвращает Verdict если сообщение надо наказать за ссылки; иначе None."""
    user_id = int(getattr(user, "id", 0) or 0) if user else 0
    trusted = await _load_trusted_patterns(session, chat_id)
    chat_db = await session.get(Chat, chat_id)

    log_x = ("anti-edit" if edited else "")
    link_action = action

    def _hit(msg: str, act: str, rsn: str) -> Verdict:
        return Verdict(
            True,
            _with_newbie_reason(rsn, newbie_win),
            msg,
            act,
            mute_minutes=mute_min,
            log_it=log_enabled,
            log_extra=log_x,
        )

    mode = (links_mode or "forbid").lower()
    if mode == "allow":
        return None
    if mode in ("open_blacklist", "allow_except_global"):
        return None

    if mode == "delete_all":
        return _hit(links[0], link_action, "link")

    if mode == "telegram_only":
        for raw in links:
            dom = _domain_from_url(raw)
            if _is_telegram_link_url(raw, dom):
                return _hit(raw, link_action, "link")
        return None

    if mode == "smart":
        for raw in links:
            dom = _domain_from_url(raw)
            if not _is_telegram_link_url(raw, dom):
                continue
            ok = await _smart_telegram_link_ok(message.bot, chat_id, raw, chat_db, user_id)
            if not ok:
                return _hit(raw, link_action, "link")
        return None

    # forbid / captcha — каждая ссылка должна быть разрешена доверенным шаблоном
    for raw in links:
        dom = _domain_from_url(raw)
        if dom == "tg://":
            continue
        if not _link_allowed_by_trusted_pattern(raw, dom, trusted):
            return _hit(raw, link_action, "link")
    return None


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

    # chat must exist in DB
    chat_row = await session.get(Chat, chat_id)
    if not chat_row:
        try:
            now_ts = time.time()
            last_ts = float(_INACTIVE_CHAT_LOG_TS.get(chat_id, 0.0))
            if now_ts - last_ts >= _INACTIVE_CHAT_LOG_TTL_SEC:
                _INACTIVE_CHAT_LOG_TS[chat_id] = now_ts
                logger.warning(
                    "moderation skip: chat_id=%s нет в таблице chats у этого бота — фильтры не применяются. "
                    "Откройте Mini App → подключите группу или заново добавьте бота админом (это не про тумблер «Guard»).",
                    chat_id,
                )
        except Exception:
            pass
        return Verdict(False, "inactive", "", "delete", log_it=False)
    # Иногда после миграций/лимитов чат может временно остаться с is_active=False,
    # но правила уже настроены и пользователь ожидает, что фильтры работают.
    # Для устойчивости модерации не блокируем обработку только по этому флагу.
    if not _bool_or_default(getattr(chat_row, "is_active", True), True):
        try:
            now_ts = time.time()
            last_ts = float(_INACTIVE_CHAT_LOG_TS.get(chat_id, 0.0))
            if now_ts - last_ts >= _INACTIVE_CHAT_LOG_TTL_SEC:
                _INACTIVE_CHAT_LOG_TS[chat_id] = now_ts
                logger.warning("moderation soft-continue: chat_id=%s has is_active=False, keep filtering enabled", chat_id)
        except Exception:
            pass

    # Жёсткий стоп для Free-лимита: если чат сверх доступных — ставим на паузу сразу в БД и выходим.
    try:
        owner_tid = int(getattr(chat_row, "owner_user_id", 0) or 0)
        if owner_tid > 0:
            owner = (
                await session.execute(select(User).where(User.telegram_id == owner_tid).limit(1))
            ).scalar_one_or_none()
            tariff = str(getattr(owner, "tariff", "") or "").strip().lower() if owner else ""
            sub_until = getattr(owner, "subscription_until", None) if owner else None
            now = datetime.now(timezone.utc)
            if sub_until and sub_until.tzinfo is None:
                sub_until = sub_until.replace(tzinfo=timezone.utc)
            premium_now = tariff in ("premium", "pro", "business") and bool(sub_until and sub_until >= now)
            if not premium_now:
                free_limit = 3
                rows = (
                    await session.execute(
                        select(Chat)
                        .where(
                            Chat.owner_user_id == owner_tid,
                            Chat.is_log_chat == False,  # noqa: E712
                        )
                        .order_by(Chat.created_at.asc(), Chat.id.asc())
                    )
                ).scalars().all()
                row_ids = [int(getattr(r, "id", 0) or 0) for r in rows if int(getattr(r, "id", 0) or 0) > 0]
                rule_ids: set[int] = set()
                if row_ids:
                    rr = await session.execute(select(Rule.chat_id).where(Rule.chat_id.in_(row_ids)))
                    rule_ids = {int(x) for x in rr.scalars().all()}
                connected_rows = [
                    r for r in rows
                    if int(getattr(r, "id", 0) or 0) in rule_ids or bool(getattr(r, "is_active", False))
                ]
                keep_ids = {int(getattr(r, "id", 0) or 0) for r in connected_rows[:free_limit]}
                if int(chat_id) not in keep_ids:
                    # Не выключаем модерацию в runtime. Жёсткое отключение чатов
                    # должно происходить отдельным управляемым процессом, а не в on_message.
                    try:
                        logger.warning(
                            "free-limit runtime hit: chat_id=%s owner=%s not in keep_ids; skip auto-deactivate in moderation",
                            chat_id,
                            owner_tid,
                        )
                    except Exception:
                        pass
    except Exception:
        # Fail-safe: если проверка лимита упала, не блокируем обычную модерацию.
        pass

    rule = await get_rule(session, chat_id)
    try:
        await session.refresh(rule)  # свежие данные из БД (настройки из Mini App)
    except Exception:
        pass

    # главный выключатель антиспама: если ВЫКЛ — не фильтруем
    if not _bool_or_default(getattr(rule, "master_anti_spam", True), True):
        return Verdict(False, "master_off", "", "delete", log_it=False)

    # do not touch admins
    if user and await is_admin(message.bot, chat_id, user_id):
        return Verdict(False, "admin_skip", "", "delete", log_it=False)

    # Копия поста канала в обсуждении (sender_chat, без from_user): это не «обычный спам в группе».
    # Иначе срабатывают стоп-слова / ссылки / мат по подписи поста — удаляется якорь треда комментариев,
    # даже когда filter_channel_posts_enabled ВЫКЛ (тот тумблер — отдельная ветка ниже).
    if not user and sender_chat and _is_channel_comment_context(message):
        return Verdict(False, "channel_discussion_post_skip", "", "delete", log_it=False)

    # Отдельный фильтр сообщений от имени каналов/чатов (sender_chat).
    if sender_chat and bool(getattr(rule, "filter_channel_posts_enabled", False)):
        # Разрешаем связанный канал в обсуждении постов.
        try:
            linked_ok = await is_post_as_linked_channel_in_discussion(message.bot, chat_id, message)
        except Exception:
            linked_ok = False
        # Если не распознали связку через get_chat, не удаляем якорь комментариев к посту канала —
        # иначе Telegram «схлопывает» тред и пропадают все комментарии под постом.
        if not linked_ok and _is_channel_comment_context(message):
            linked_ok = True
        if not linked_ok:
            sc_username = str(getattr(sender_chat, "username", "") or "").strip().lstrip("@").lower()
            if sc_username and await whitelist_sender_chat_username(session, chat_id, sc_username):
                return Verdict(False, "whitelist_sender_chat", "", "delete", log_it=False)
            sc_action = str(getattr(rule, "filter_channel_posts_action", "delete") or "delete").strip().lower()
            if sc_action not in ("delete", "ban"):
                sc_action = "delete"
            return Verdict(
                True,
                "channel_post_actor",
                f"sender_chat:@{sc_username}" if sc_username else f"sender_chat:{int(getattr(sender_chat, 'id', 0) or 0)}",
                sc_action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )

    # do not touch whitelisted users
    if user and await whitelist_user(session, chat_id, user_id):
        return Verdict(False, "whitelist_user", "", "delete", log_it=False)

    text = message.text or message.caption or ""
    text_norm = normalize(text)
    # Для стоп-слов не учитываем текст внутри URL (чтобы «разрешено» для ссылок не ломалось из-за слов в ссылке)
    text_for_stopwords_norm = normalize(_text_without_urls_for_stopwords(text))

    # base action
    action = _normalize_action_mode(getattr(rule, "action_mode", "delete"))

    mute_min = int(getattr(rule, "mute_minutes", 30) or 30)
    mute_min = max(1, min(1440, mute_min))

    # Ссылки: filter_links_mode + legacy filter_links из Mini App
    _links_mode_raw = getattr(rule, "filter_links_mode", None)
    _links_mode = str(_links_mode_raw or "").strip().lower()
    if _links_mode not in _LINK_MODES:
        _links_mode = "forbid"
    # Legacy filter_links + filter_links_mode из Mini App (при «разрешить ссылки» filter_links=False).
    filter_links = _bool_or_default(getattr(rule, "filter_links", True), True)
    filter_mentions = bool(getattr(rule, "filter_mentions", True))
    _media_mode = getattr(rule, "filter_media_mode", "allow")
    filter_media = _media_mode in ("forbid", "captcha")
    _buttons_mode = getattr(rule, "filter_buttons_mode", "allow")
    filter_buttons = _buttons_mode in ("forbid", "captcha")
    anti_edit = bool(getattr(rule, "anti_edit", True))
    log_enabled = bool(getattr(rule, "log_enabled", True))
    silence_minutes = int(getattr(rule, "silence_minutes", 0) or 0)
    silence_minutes = max(0, min(10080, silence_minutes))  # до 7 суток
    newbie_min = int(getattr(rule, "newbie_minutes", 10) or 10)
    newbie_min = max(1, min(10080, newbie_min))
    newbie_win = (
        bool(getattr(rule, "newbie_enabled", False))
        and bool(user)
        and await _in_newbie_period(session, chat_id, user_id, newbie_min)
    )

    # -------------------------------------------------
    # 1) stopwords (без учёта токенов внутри URL) — раньше режима тишины:
    # иначе при тишине срабатывал только мут без удаления, а стоп-слово оставалось в чате.
    # -------------------------------------------------
    stopwords = await load_stopwords(session, chat_id)
    hit = stopword_hit(text_norm, stopwords, text_without_urls_norm=text_for_stopwords_norm)
    if hit:
        return Verdict(
            True, _with_newbie_reason("stopword", newbie_win), hit, action,
            mute_minutes=mute_min,
            log_it=log_enabled,
            log_extra=("anti-edit" if edited else ""),
        )

    # -------------------------------------------------
    # 1a) Ссылки и упоминания — сразу после стоп-слов (до тяжёлых словарей и load_profanity_words):
    # меньше задержка на типичный спам со ссылками / @everyone.
    # -------------------------------------------------
    links_filter_on = filter_links and (_links_mode != "allow")
    links = find_links_in_message(message)
    if links:
        bl_patterns = await _load_blacklist_patterns(session, chat_id)
        for raw in links:
            if _url_hit_blacklist(raw, bl_patterns):
                return Verdict(
                    True,
                    _with_newbie_reason("link_blacklist", newbie_win),
                    raw,
                    "ban",
                    mute_minutes=mute_min,
                    log_it=log_enabled,
                    log_extra=("anti-edit" if edited else ""),
                )
        if _should_check_global_bad_urls(rule):
            own_tid = int(getattr(chat_row, "owner_user_id", 0) or 0)
            owner_row = (
                await session.execute(select(User).where(User.telegram_id == own_tid).limit(1))
            ).scalar_one_or_none() if own_tid > 0 else None
            owner_is_full = bool(owner_row and _is_full_admin_user_role(owner_row, own_tid))
            gp = await get_effective_global_bad_url_patterns(
                session, own_tid, owner_is_full_admin=owner_is_full
            )
            if gp:
                for raw in links:
                    if _url_hit_blacklist(raw, gp):
                        return Verdict(
                            True,
                            _with_newbie_reason("global_bad_url", newbie_win),
                            raw,
                            action,
                            mute_minutes=mute_min,
                            log_it=log_enabled,
                            log_extra=("anti-edit" if edited else ""),
                        )
    if links_filter_on and links and not _link_filter_scope_skips_message(message, rule):
        v_link = await _apply_link_policy(
            session,
            message,
            chat_id,
            user,
            links,
            links_mode=_links_mode,
            newbie_win=newbie_win,
            action=action,
            mute_min=mute_min,
            log_enabled=log_enabled,
            edited=edited,
        )
        if v_link:
            return v_link

    if filter_mentions:
        mentions = find_mentions_any(message)
        if mentions:
            return Verdict(
                True, _with_newbie_reason("mention", newbie_win), mentions[0], action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )

    # -------------------------------------------------
    # 1b) Словарь Guard: мат / мутные подработки / казино-ставки
    # -------------------------------------------------
    # Три независимых тумблера (Mini App). Нельзя трактовать «один ВКЛ» как отключение остальных —
    # раньше из-за этого при ВКЛ только «Мат» переставали ловиться подработки/казино при ВЫКЛ в БД.
    use_profanity = bool(getattr(rule, "filter_profanity_enabled", True))
    use_jobs = bool(getattr(rule, "filter_jobs_enabled", True))
    use_casino = bool(getattr(rule, "filter_casino_enabled", True))
    use_ads = bool(getattr(rule, "filter_ads_enabled", False))
    use_insults = bool(getattr(rule, "filter_insults_enabled", False))
    use_racism = bool(getattr(rule, "filter_racism_enabled", False))
    use_nazi = bool(getattr(rule, "filter_nazi_enabled", False))
    use_vulgar = bool(getattr(rule, "filter_vulgar_enabled", False))

    # Узкие словари проверяем РАНЬШЕ profanity, чтобы конкретные категории
    # (обзывательства/реклама/казино/подработки/расизм/нацизм/пошлость) попадали
    # в свою корзину статистики, а не «съедались» общим матом.
    if use_insults:
        insult_set = _builtin_words(DEFAULT_INSULT_ROOTS)
        hit_insult = profanity_hit(text_norm, insult_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_insult:
            return Verdict(
                True, _with_newbie_reason("insult", newbie_win), hit_insult, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )
    if use_racism:
        racism_set = _builtin_words(DEFAULT_RACISM_ROOTS)
        hit_racism = profanity_hit(text_norm, racism_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_racism:
            return Verdict(
                True, _with_newbie_reason("racism", newbie_win), hit_racism, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )
    if use_nazi:
        nazi_set = _builtin_words(DEFAULT_NAZI_ROOTS)
        hit_nazi = profanity_hit(text_norm, nazi_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_nazi:
            return Verdict(
                True, _with_newbie_reason("nazi", newbie_win), hit_nazi, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )
    if use_vulgar:
        vulgar_set = _builtin_words(DEFAULT_VULGAR_ROOTS)
        hit_vulgar = profanity_hit(text_norm, vulgar_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_vulgar:
            return Verdict(
                True, _with_newbie_reason("vulgar", newbie_win), hit_vulgar, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )
    if use_ads:
        ads_set = _builtin_words(DEFAULT_ADS_ROOTS)
        hit_ads = profanity_hit(text_norm, ads_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_ads:
            return Verdict(
                True, _with_newbie_reason("ads", newbie_win), hit_ads, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )
    if use_casino:
        casino_set = _builtin_words(DEFAULT_CASINO_ROOTS)
        hit_casino = profanity_hit(text_norm, casino_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_casino:
            return Verdict(
                True, _with_newbie_reason("casino", newbie_win), hit_casino, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )
    if use_jobs:
        jobs_set = _builtin_words(DEFAULT_JOBS_ROOTS)
        hit_jobs = profanity_hit(text_norm, jobs_set, text_without_urls_norm=text_for_stopwords_norm)
        if not hit_jobs:
            hit_jobs = jobs_offer_hit(text_norm, text_without_urls_norm=text_for_stopwords_norm)
        if hit_jobs:
            return Verdict(
                True, _with_newbie_reason("jobs", newbie_win), hit_jobs, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )
    if use_profanity:
        # Общий «мат». Объединяем встроенные корни с пользовательским словарём,
        # но обязательно вычитаем все узкие словари, чтобы их попадания шли
        # в свои корзины статистики (insult/racism/nazi/vulgar/ads/casino/jobs).
        mat_set = _builtin_words(DEFAULT_PROFANITY_ROOTS) | (await load_profanity_words(session))
        mat_set = (
            mat_set
            - _builtin_words(DEFAULT_JOBS_ROOTS)
            - _builtin_words(DEFAULT_CASINO_ROOTS)
            - _builtin_words(DEFAULT_ADS_ROOTS)
            - _builtin_words(DEFAULT_INSULT_ROOTS)
            - _builtin_words(DEFAULT_RACISM_ROOTS)
            - _builtin_words(DEFAULT_NAZI_ROOTS)
            - _builtin_words(DEFAULT_VULGAR_ROOTS)
        )
        hit_prof = profanity_hit(text_norm, mat_set, text_without_urls_norm=text_for_stopwords_norm)
        if hit_prof:
            return Verdict(
                True, _with_newbie_reason("profanity", newbie_win), hit_prof, action,
                mute_minutes=mute_min,
                log_it=log_enabled,
                log_extra=("anti-edit" if edited else ""),
            )

    # -------------------------------------------------
    # 0) Режим тишины: после входа N минут — ограничение (после стоп-слов и встроенных словарей)
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
    # 4) media / стикеры (filter_media_mode: forbid | captcha). Капча на паузе — captcha как action
    # -------------------------------------------------
    if filter_media and has_media(message):
        # from app.handlers.first_message_captcha import _captcha_passed as captcha_passed_check
        # if _media_mode == "captcha" and user and captcha_passed_check(chat_id, user_id):
        #     pass
        media_action = action  # капча на паузе: "captcha" -> action (delete/mute/ban)
        return Verdict(
            True, _with_newbie_reason("media", newbie_win), "медиа/стикер", media_action,
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
            True, _with_newbie_reason("buttons", newbie_win), "сообщение с кнопками", buttons_action,
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

    # Диагностика "почему чисто": помогает ловить кейсы, когда UI/настройки не совпадают с ожиданиями.
    # Логируем только сообщения, где есть признаки ссылок или "жёсткого словаря".
    try:
        has_linkish = bool(find_links_in_message(message))
        prof_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_PROFANITY_ROOTS), text_without_urls_norm=text_for_stopwords_norm)
        jobs_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_JOBS_ROOTS), text_without_urls_norm=text_for_stopwords_norm) or jobs_offer_hit(text_norm, text_without_urls_norm=text_for_stopwords_norm)
        casino_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_CASINO_ROOTS), text_without_urls_norm=text_for_stopwords_norm)
        ads_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_ADS_ROOTS), text_without_urls_norm=text_for_stopwords_norm)
        insult_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_INSULT_ROOTS), text_without_urls_norm=text_for_stopwords_norm)
        racism_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_RACISM_ROOTS), text_without_urls_norm=text_for_stopwords_norm)
        nazi_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_NAZI_ROOTS), text_without_urls_norm=text_for_stopwords_norm)
        vulgar_probe = profanity_hit(text_norm, _builtin_words(DEFAULT_VULGAR_ROOTS), text_without_urls_norm=text_for_stopwords_norm)
        if has_linkish or prof_probe or jobs_probe or casino_probe or ads_probe or insult_probe or racism_probe or nazi_probe or vulgar_probe:
            logger.warning(
                "[moderation clean diag] chat=%s user=%s link_mode=%s filter_links=%s action=%s prof_on=%s jobs_on=%s casino_on=%s ads_on=%s insults_on=%s probes(link=%s,prof=%s,jobs=%s,casino=%s,ads=%s,insult=%s) text=%r",
                chat_id,
                user_id,
                _links_mode,
                filter_links,
                action,
                use_profanity,
                use_jobs,
                use_casino,
                use_ads,
                use_insults,
                has_linkish,
                bool(prof_probe),
                bool(jobs_probe),
                bool(casino_probe),
                bool(ads_probe),
                bool(insult_probe),
                (text[:180] + "…") if len(text) > 180 else text,
            )
    except Exception:
        pass
    return Verdict(False, "clean", "", "delete", log_it=False)


# =========================================================
# Actions (delete / mute / ban)
# =========================================================
async def _delete_message_with_thread(message: Message) -> None:
    """deleteMessage: в Bot API только chat_id + message_id (message_id однозначен в чате, в т.ч. в форумах)."""
    await message.bot(
        DeleteMessage(chat_id=message.chat.id, message_id=message.message_id),
    )


async def _try_delete(message: Message) -> bool:
    try:
        await _delete_message_with_thread(message)
        return True
    except TelegramBadRequest as e:
        logger.warning(
            "delete_message failed chat=%s msg=%s thread=%s: %s",
            message.chat.id,
            message.message_id,
            getattr(message, "message_thread_id", None),
            e,
        )
        await record_bot_delete_message_failed(context="moderation", message=message, exc=e)
        return False
    except TelegramForbiddenError as e:
        logger.warning(
            "delete_message forbidden chat=%s msg=%s: %s",
            message.chat.id,
            message.message_id,
            e,
        )
        await record_bot_delete_message_failed(context="moderation", message=message, exc=e)
        return False
    except Exception as e:
        logger.warning(
            "delete_message unexpected chat=%s msg=%s: %s",
            message.chat.id,
            message.message_id,
            e,
        )
        await record_bot_delete_message_failed(context="moderation", message=message, exc=e)
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
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await record_moderation_restrict_failed(message=message, action="mute", exc=e)
        return False
    except Exception as e:
        await record_moderation_restrict_failed(message=message, action="mute", exc=e)
        return False

async def _try_ban(message: Message) -> bool:
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat and not message.from_user:
        scid = int(getattr(sender_chat, "id", 0) or 0)
        if scid == 0:
            return False
        try:
            await message.bot.ban_chat_sender_chat(message.chat.id, scid)
            return True
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            await record_moderation_restrict_failed(
                message=message, action="ban_sender_chat", exc=e, target_telegram_id=None
            )
            return False
        except Exception as e:
            await record_moderation_restrict_failed(
                message=message, action="ban_sender_chat", exc=e, target_telegram_id=None
            )
            return False
    try:
        await message.bot.ban_chat_member(message.chat.id, message.from_user.id)
        return True
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await record_moderation_restrict_failed(message=message, action="ban", exc=e)
        return False
    except Exception as e:
        await record_moderation_restrict_failed(message=message, action="ban", exc=e)
        return False

async def apply_action(message: Message, v: Verdict) -> Tuple[bool, str, bool]:
    """
    returns: (ok_action, action_label_for_log, deleted_ok)
    """
    if v.action == "observe":
        # Только фиксация в логах / отчётах — сообщение не трогаем.
        return True, "👁 Замечено (без удаления)", False

    deleted_ok = await _try_delete(message)

    if v.action == "delete":
        return deleted_ok, "🧹 Удаление", deleted_ok

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
        mm = int(v.mute_minutes)
        mute_lbl = "🔇 Мут 1 день" if mm == 1440 else f"🔇 Мут {mm} мин"
        return ok, mute_lbl, deleted_ok

    if v.action == "ban":
        ok = await _try_ban(message)
        return ok, "⛔ Бан", deleted_ok

    return False, "⚠️ Неизвестное действие", deleted_ok


# =========================================================
# Log keyboard (unban / unmute)
# =========================================================
def log_keyboard(action: str, chat_id: int, user_id: int):
    b = InlineKeyboardBuilder()

    if action == "observe":
        b.adjust(1)
        return b.as_markup()

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
    "jobs": "🕵️ мутные подработки",
    "jobs_newbie": "🕵️ мутные подработки (новичок)",
    "casino": "🎰 казино/ставки",
    "casino_newbie": "🎰 казино/ставки (новичок)",
    "ads": "📢 реклама",
    "ads_newbie": "📢 реклама (новичок)",
    "insult": "👎 обзывательство",
    "insult_newbie": "👎 обзывательство (новичок)",
    "racism": "🚫 расизм",
    "racism_newbie": "🚫 расизм (новичок)",
    "nazi": "⛔ нацизм/фашизм",
    "nazi_newbie": "⛔ нацизм/фашизм (новичок)",
    "vulgar": "🔞 пошлость",
    "vulgar_newbie": "🔞 пошлость (новичок)",
    "link": "🔗 ссылка",
    "link_newbie": "🔗 ссылка (новичок)",
    "mention": "🏷 упоминание",
    "mention_newbie": "🏷 упоминание (новичок)",
    "media": "🖼 медиа/стикер",
    "media_newbie": "🖼 медиа/стикер (новичок)",
    "buttons": "🔘 сообщение с кнопками",
    "buttons_newbie": "🔘 сообщение с кнопками (новичок)",
    "channel_post_actor": "📣 сообщение от имени канала/чата",
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
    user = message.from_user
    if not user:
        return

    chat_row = await session.get(Chat, message.chat.id)
    if not chat_row:
        return

    # Всегда пишем в moderation_logs для статистики Mini App, даже если лог-чат не настроен
    # или отключены уведомления в лог-чат.
    det = str(getattr(v, "details", "") or "").strip()
    session.add(
        ModerationLog(
            chat_id=message.chat.id,
            user_id=user.id,
            action=v.action,
            reason=v.reason,
            detail=(det[:2000] if det else None),
            message_text=(message.text or message.caption or "")[:2000],
        )
    )

    rule = await get_rule(session, message.chat.id)
    if not v.log_it:
        return
    if not bool(getattr(rule, "log_enabled", True)):
        return

    log_chat_id = getattr(chat_row, "log_chat_id", None)
    if not log_chat_id:
        return

    src = (message.text or message.caption or "")
    src = (src[:500] + "…") if len(src) > 500 else src

    who = f"@{user.username}" if user.username else user.full_name
    reason_h = _REASON_HUMAN.get(v.reason, v.reason)

    extra_parts: List[str] = []
    if v.log_extra:
        extra_parts.append(v.log_extra)

    if not deleted_ok and v.action != "observe":
        extra_parts.append("⚠️ не смог удалить (нет права Delete messages)")

    if v.action in ("mute", "ban") and not ok_action:
        extra_parts.append("⚠️ не смог наказать (нет права Ban/Restrict или лимит Telegram)")

    if v.action == "observe":
        extra_parts.append("сообщение в чате не удалялось — режим проверки")

    extra = " | ".join(extra_parts)

    title_s = html.escape(str(message.chat.title or message.chat.id))
    who_s = html.escape(who)
    reason_s = html.escape(str(reason_h))
    details_s = html.escape(str(v.details))
    action_s = html.escape(str(action_label))
    extra_s = html.escape(extra) if extra else ""

    if v.action == "observe":
        header = "👁 <b>Guard — ЗАМЕЧЕНО</b>\n<i>(сообщение оставлено в чате)</i>\n"
    else:
        header = "😈 <b>Guard: Боевое срабатывание</b>\n"

    txt = (
        header
        + f"🏷 <b>Чат:</b> {title_s}\n"
        f"👤 <b>Нарушитель:</b> {who_s} (<code>{user.id}</code>)\n"
        f"🧠 <b>Триггер:</b> {reason_s}\n"
        f"🔎 <b>Деталь:</b> <code>{details_s}</code>\n"
        f"⚔️ <b>Реакция:</b> {action_s}\n"
    )

    if extra_s:
        txt += f"\n<i>{extra_s}</i>\n"

    if src:
        src_s = html.escape(src)
        txt += f"\n💬 <b>Текст:</b>\n<code>{src_s}</code>\n"

    try:
        await message.bot.send_message(
            int(log_chat_id),
            txt,
            parse_mode="HTML",
            reply_markup=log_keyboard(v.action, message.chat.id, user.id),
        )
    except Exception as e:
        logger.warning(f"[log send failed] chat={message.chat.id} -> log_chat={log_chat_id}: {e}")


# =========================================================
# Pipeline
# =========================================================
def _pipeline_skip_channel_discussion_mirror(message: Message) -> bool:
    """
    Зеркало поста канала в обсуждении: НЕ гонять через evaluate().

    Причина бага: у якоря нет from_user, зато есть текст/медиа канала — срабатывали стоп-слова, ссылки,
    filter_channel_posts и т.д., якорь удалялся → Telegram схлопывает тред комментариев (правила пропадают).
    """
    try:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return False
        fu = getattr(message, "from_user", None)
        # В linked discussion Telegram часто присылает зеркало поста канала как from_user=777000.
        # Такие сообщения нельзя пускать в evaluate(): удаление якоря схлопывает весь тред комментариев.
        if fu and int(getattr(fu, "id", 0) or 0) == 777000:
            return True
        if fu:
            return False
        if getattr(message, "new_chat_members", None) or getattr(message, "left_chat_member", None):
            return False
        sc = getattr(message, "sender_chat", None)
        if sc and "channel" in str(getattr(sc, "type", "") or "").lower():
            return True
        if bool(getattr(message, "is_automatic_forward", False)):
            return True
        fo = getattr(message, "forward_origin", None)
        if fo is not None and "Channel" in type(fo).__name__:
            return True
    except Exception:
        return False
    return False


def _rules_group_markup_api_dict(raw_json: str | None) -> dict | None:
    """Inline keyboard для Bot API (sendMessage), как в Mini App /api/chat/.../rules/send."""
    if not raw_json:
        return None
    try:
        rows = json.loads(str(raw_json))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    inline_keyboard: list[list[dict]] = []
    for row in rows[:8]:
        if not isinstance(row, list):
            continue
        out_row: list[dict] = []
        for btn in row[:6]:
            if not isinstance(btn, dict):
                continue
            text_v = str(btn.get("text") or "").strip()[:64]
            if not text_v:
                continue
            url_v = str(btn.get("url") or "").strip()[:512]
            wu_v = str(btn.get("web_app_url") or "").strip()[:512]
            cb_v = str(btn.get("callback_data") or "").strip()[:64]
            if url_v:
                out_row.append({"text": text_v, "url": url_v})
            elif wu_v:
                out_row.append({"text": text_v, "web_app": {"url": wu_v}})
            elif cb_v:
                out_row.append({"text": text_v, "callback_data": cb_v})
        if out_row:
            inline_keyboard.append(out_row)
    if not inline_keyboard:
        return None
    return {"inline_keyboard": inline_keyboard}


def _moderation_punishment_landed(v: Verdict, deleted_ok: bool, ok_action: bool) -> bool:
    """Фактическое наказание применилось (удаление / мут / бан), не режим observe."""
    a = str(v.action or "").strip().lower()
    if a == "observe":
        return False
    if a == "delete":
        return bool(deleted_ok)
    if a in ("mute", "ban"):
        return bool(ok_action)
    return False


async def _try_send_group_rules_autopost(bot, chat_id: int, rule: Rule) -> bool:
    """Отправить шаблон правил группы (как ручная отправка из Mini App), с опциональным удалением «закрепил»."""
    text_value = str(getattr(rule, "rules_group_text", "") or "").strip()
    if not text_value:
        return False
    markup_aiogram = _rules_keyboard_from_json(getattr(rule, "rules_group_buttons_json", None))
    markup_api = _rules_group_markup_api_dict(getattr(rule, "rules_group_buttons_json", None))
    rel = str(getattr(rule, "rules_group_photo_path", "") or "").strip()
    fid = str(getattr(rule, "rules_group_photo_file_id", "") or "").strip()
    try:
        sent = None
        mid = 0
        fp = None
        if rel:
            pp = (_rules_media_root() / rel).resolve()
            root = _rules_media_root().resolve()
            if pp.exists() and pp.is_file() and (root in pp.parents or pp == root):
                fp = pp

        def _photo_source():
            return fid if fid else FSInputFile(str(fp))

        if fid or fp is not None:
            try:
                sent = await bot.send_photo(
                    chat_id=chat_id,
                    photo=_photo_source(),
                    caption=text_value,
                    parse_mode="HTML",
                    reply_markup=markup_aiogram,
                )
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                logger.warning("group_rules_autosend_photo_failed chat=%s err=%s", chat_id, e)
                sent_dict = await tg_send_message(
                    int(chat_id),
                    text_value,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=markup_api,
                )
                sent = sent_dict
            if sent is not None and isinstance(sent, dict):
                mid = int((sent or {}).get("message_id") or 0)
            else:
                mid = int(getattr(sent, "message_id", 0) or 0)
        if sent is None:
            sent_dict = await tg_send_message(
                int(chat_id),
                text_value,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=markup_api,
            )
            if not sent_dict:
                logger.warning("group_rules_autosend_tg_send_failed chat=%s (tg_send_message returned empty)", chat_id)
                return False
            mid = int((sent_dict or {}).get("message_id") or 0)
        else:
            if isinstance(sent, dict):
                mid = int((sent or {}).get("message_id") or 0)
            else:
                mid = int(getattr(sent, "message_id", 0) or 0)
        if bool(getattr(rule, "rules_group_pin_on_send", True)) and mid > 0:
            try:
                await tg_pin_chat_message(int(chat_id), int(mid), disable_notification=True)
            except Exception:
                try:
                    await bot.pin_chat_message(chat_id, mid, disable_notification=True)
                except Exception:
                    pass
            if bool(getattr(rule, "rules_group_delete_pin_notice", False)):
                await tg_try_delete_pin_service_messages(int(chat_id), int(mid))
        return True
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning("group_rules_autosend_failed chat=%s err=%s", chat_id, e)
        return False
    except Exception as e:
        logger.warning("group_rules_autosend_failed chat=%s err=%s", chat_id, e)
        return False


async def _maybe_autosend_group_rules_on_moderation(
    bot,
    session,
    rule: Rule,
    chat_id: int,
    v: Verdict,
    deleted_ok: bool,
    ok_action: bool,
) -> None:
    """После боевого срабатывания модерации — опционально отправить правила в группу (с интервалом N)."""
    try:
        if not bool(getattr(rule, "rules_group_enabled", False)):
            logger.debug(
                "group_rules_autosend_skip chat=%s reason=rules_group_disabled action=%s",
                chat_id,
                getattr(v, "action", None),
            )
            return
        text_value = str(getattr(rule, "rules_group_text", "") or "").strip()
        if not text_value:
            logger.debug(
                "group_rules_autosend_skip chat=%s reason=empty_rules_group_text action=%s",
                chat_id,
                getattr(v, "action", None),
            )
            return
        on_t = bool(getattr(rule, "rules_group_event_on_trigger", False))
        on_p = bool(getattr(rule, "rules_group_event_on_punish", False))
        if not on_t and not on_p:
            logger.debug(
                "group_rules_autosend_skip chat=%s reason=both_event_flags_off action=%s",
                chat_id,
                getattr(v, "action", None),
            )
            return
        n_t = max(1, min(500, int(getattr(rule, "rules_group_event_trigger_every_n", 1) or 1)))
        n_p = max(1, min(500, int(getattr(rule, "rules_group_event_punish_every_n", 1) or 1)))
        acc_t = int(getattr(rule, "rules_group_event_trigger_acc", 0) or 0)
        acc_p = int(getattr(rule, "rules_group_event_punish_acc", 0) or 0)
        old_t, old_p = acc_t, acc_p
        punish_ok = _moderation_punishment_landed(v, deleted_ok, ok_action)
        t_hit = False
        if on_t:
            acc_t += 1
            if acc_t >= n_t:
                t_hit = True
        p_hit = False
        if on_p and punish_ok:
            acc_p += 1
            if acc_p >= n_p:
                p_hit = True
        if not t_hit and not p_hit:
            rule.rules_group_event_trigger_acc = max(0, acc_t)
            rule.rules_group_event_punish_acc = max(0, acc_p)
            logger.debug(
                "group_rules_autosend_wait chat=%s action=%s deleted_ok=%s ok_action=%s punish_ok=%s "
                "acc_trigger=%s/%s acc_punish=%s/%s on_trigger=%s on_punish=%s",
                chat_id,
                getattr(v, "action", None),
                bool(deleted_ok),
                bool(ok_action),
                bool(punish_ok),
                acc_t,
                n_t,
                acc_p,
                n_p,
                on_t,
                on_p,
            )
            return
        logger.info(
            "group_rules_autosend_attempt chat=%s action=%s deleted_ok=%s ok_action=%s punish_ok=%s "
            "t_hit=%s p_hit=%s acc_before_trigger=%s acc_before_punish=%s",
            chat_id,
            getattr(v, "action", None),
            bool(deleted_ok),
            bool(ok_action),
            bool(punish_ok),
            t_hit,
            p_hit,
            old_t,
            old_p,
        )
        ok_send = await _try_send_group_rules_autopost(bot, chat_id, rule)
        if ok_send:
            if t_hit:
                acc_t = 0
            if p_hit:
                acc_p = 0
            logger.info(
                "group_rules_autosend_ok chat=%s trigger_hit=%s punish_hit=%s",
                chat_id,
                t_hit,
                p_hit,
            )
        else:
            acc_t, acc_p = old_t, old_p
            logger.warning(
                "group_rules_autosend_send_failed chat=%s counters_reverted acc_trigger=%s acc_punish=%s",
                chat_id,
                old_t,
                old_p,
            )
        rule.rules_group_event_trigger_acc = max(0, acc_t)
        rule.rules_group_event_punish_acc = max(0, acc_p)
    except Exception as e:
        logger.warning("group_rules_autosend_state chat=%s err=%s", chat_id, e)


async def pipeline(message: Message, *, edited: bool = False) -> None:
    # Жёсткий стоп: зеркало поста канала в linked discussion у Telegram часто приходит как from_user=777000.
    # Никогда не пускаем такие апдейты в evaluate(), иначе удаляется якорь и схлопывается тред комментариев.
    if int(getattr(getattr(message, "from_user", None), "id", 0) or 0) == 777000:
        return
    if _pipeline_skip_channel_discussion_mirror(message):
        return
    # если сообщение от имени канала/чата — from_user может быть None
    if not message.from_user and not getattr(message, "sender_chat", None):
        return
    # Сообщения от любых ботов не гоняем через антиспам: иначе при выключенном privacy
    # бот получает свои же посты (например правила в комментариях) и удаляет их как «ссылки/кнопки».
    if message.from_user and bool(getattr(message.from_user, "is_bot", False)):
        return
    # обрабатываем сообщения с текстом, подписью, медиа или кнопками (иначе стикеры/фото без подписи не проверяются)
    if not (message.text or message.caption or has_media(message) or has_buttons(message)):
        return

    # Капча на паузе
    # from app.handlers.first_message_captcha import check_first_message_captcha
    # if await check_first_message_captcha(message):
    #     return

    try:
        print(
            f"[GUARD TRACE] incoming chat={getattr(message.chat, 'id', None)} user={getattr(getattr(message, 'from_user', None), 'id', None)} "
            f"edited={edited} text={(message.text or message.caption or '')[:120]!r}",
            flush=True,
        )
    except Exception:
        pass

    async with await get_session() as session:
        try:
            if message.from_user:
                from app.services.chat_cleanup import record_seen_member as record_seen_member_cleanup
                await record_seen_member_cleanup(session, message.chat.id, message.from_user.id)
            v = await evaluate(session, message, edited=edited)
            try:
                _suffix = "" if v.should_act else " (без модерации: сообщение не удаляем)"
                print(
                    f"[GUARD TRACE] verdict chat={message.chat.id} user={getattr(message.from_user, 'id', None)} "
                    f"act={v.should_act} reason={v.reason} action={v.action} mute={v.mute_minutes}{_suffix}",
                    flush=True,
                )
            except Exception:
                pass
            if not v.should_act:
                return

            ok_action, action_label, deleted_ok = await apply_action(message, v)
            try:
                print(
                    f"[GUARD TRACE] applied chat={message.chat.id} user={getattr(message.from_user, 'id', None)} "
                    f"label={action_label} ok_action={ok_action} deleted_ok={deleted_ok}",
                    flush=True,
                )
            except Exception:
                pass
            await send_log(
                session,
                message,
                v,
                action_label=action_label,
                ok_action=ok_action,
                deleted_ok=deleted_ok,
            )
            rule_gr = (
                await session.execute(select(Rule).where(Rule.chat_id == int(message.chat.id)).limit(1))
            ).scalar_one_or_none()
            if rule_gr is None:
                rule_gr = await get_rule(session, message.chat.id)
            if bool(getattr(rule_gr, "rules_group_enabled", False)) and (
                bool(getattr(rule_gr, "rules_group_event_on_trigger", False))
                or bool(getattr(rule_gr, "rules_group_event_on_punish", False))
            ):
                logger.debug(
                    "group_rules_autosend_after_act chat=%s action=%s deleted_ok=%s ok_action=%s "
                    "text_len=%s on_trigger=%s on_punish=%s every_n_trigger=%s every_n_punish=%s "
                    "acc_trigger=%s acc_punish=%s",
                    int(message.chat.id),
                    getattr(v, "action", None),
                    bool(deleted_ok),
                    bool(ok_action),
                    len(str(getattr(rule_gr, "rules_group_text", "") or "").strip()),
                    bool(getattr(rule_gr, "rules_group_event_on_trigger", False)),
                    bool(getattr(rule_gr, "rules_group_event_on_punish", False)),
                    int(getattr(rule_gr, "rules_group_event_trigger_every_n", 1) or 1),
                    int(getattr(rule_gr, "rules_group_event_punish_every_n", 1) or 1),
                    int(getattr(rule_gr, "rules_group_event_trigger_acc", 0) or 0),
                    int(getattr(rule_gr, "rules_group_event_punish_acc", 0) or 0),
                )
            await _maybe_autosend_group_rules_on_moderation(
                message.bot,
                session,
                rule_gr,
                int(message.chat.id),
                v,
                deleted_ok,
                ok_action,
            )
            if deleted_ok:
                rule = rule_gr
                await maybe_send_public_alert(
                    message.bot,
                    message.chat.id,
                    rule,
                    v.reason,
                    v.action,
                    session,
                    source_message=message,
                )
                # Реакция без ожидания фонового цикла: после удаления сразу проверяем всплеск.
                if str(v.action or "").lower() in ("delete", "mute", "ban"):
                    try:
                        now_utc = datetime.now(timezone.utc)
                        burst_window_min = max(
                            5,
                            min(180, int(getattr(rule, "spam_spike_window_minutes", 35) or 35)),
                        )
                        burst_delete_count = max(
                            2,
                            min(50, int(getattr(rule, "spam_spike_min_deletes", 15) or 15)),
                        )
                        chat_id_i = int(message.chat.id)
                        since_utc = now_utc - timedelta(minutes=burst_window_min)
                        # Считаем прямо в БД: работает стабильно даже при нескольких воркерах.
                        cnt_q = await session.execute(
                            select(func.count(ModerationLog.id)).where(
                                ModerationLog.chat_id == chat_id_i,
                                ModerationLog.created_at >= since_utc,
                                ModerationLog.reason.in_(list(SPAM_MODERATION_REASONS)),
                                func.lower(ModerationLog.action).in_(("delete", "mute", "ban")),
                            )
                        )
                        streak_count = int(cnt_q.scalar() or 0)
                        # Текущая строка лога может быть без created_at до commit (server_default=now()).
                        # Для immediate-check учитываем её как +1.
                        if streak_count < burst_delete_count:
                            newest_row = (await session.execute(
                                select(ModerationLog.created_at)
                                .where(ModerationLog.chat_id == chat_id_i)
                                .order_by(desc(ModerationLog.id))
                                .limit(1)
                            )).first()
                            newest_created_at = newest_row[0] if newest_row else None
                            if newest_created_at is None:
                                streak_count += 1
                        is_consecutive_spam = streak_count >= burst_delete_count
                        in_time_window = True
                        missing_ts = False
                        alert_active = False
                        last_alert_at_str = "-"
                        expires_at_str = "-"
                        try:
                            alert_row = (
                                await session.execute(
                                    select(ChatSpikeAlert.last_triggered_at, ChatSpikeAlert.expires_at)
                                    .where(ChatSpikeAlert.chat_id == chat_id_i)
                                    .limit(1)
                                )
                            ).first()
                            if alert_row:
                                last_alert_at = alert_row[0]
                                expires_at = alert_row[1]
                                if last_alert_at is not None:
                                    if getattr(last_alert_at, "tzinfo", None) is None:
                                        last_alert_at = last_alert_at.replace(tzinfo=timezone.utc)
                                    last_alert_at_str = last_alert_at.isoformat()
                                if expires_at is not None:
                                    if getattr(expires_at, "tzinfo", None) is None:
                                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                                    expires_at_str = expires_at.isoformat()
                                    alert_active = expires_at > now_utc
                        except Exception:
                            alert_active = False

                        if is_consecutive_spam and in_time_window and not alert_active:
                            dbg = (
                                "DEBUG spike trigger\n"
                                f"chat={chat_id_i}\n"
                                f"user={int(getattr(message.from_user, 'id', 0) or 0)}\n"
                                f"required={burst_delete_count}\n"
                                f"window_min={burst_window_min}\n"
                                f"streak_count={streak_count}\n"
                                f"alert_active={alert_active}\n"
                                f"last_alert_at={last_alert_at_str}\n"
                                f"expires_at={expires_at_str}\n"
                                f"action={str(v.action or '').lower()}\n"
                                f"deleted_ok={bool(deleted_ok)}"
                            )
                            await _send_spike_debug(
                                message.bot,
                                dbg,
                                extra_ids=[int(getattr(message.from_user, "id", 0) or 0)],
                            )
                            await trigger_spam_spike_for_chat(
                                message.bot,
                                session,
                                now_utc,
                                chat_id_i,
                                spam_cnt=burst_delete_count,
                                joins_cnt=0,
                                window_min=burst_window_min,
                            )
                            logger.info(
                                "immediate spike trigger chat=%s consecutive=%s window_min=%s",
                                message.chat.id,
                                burst_delete_count,
                                burst_window_min,
                            )
                        else:
                            logger.debug(
                                "immediate spike check chat=%s consecutive=%s in_window=%s alert_active=%s required=%s window_min=%s last_alert_at=%s expires_at=%s",
                                message.chat.id,
                                is_consecutive_spam,
                                in_time_window,
                                alert_active,
                                burst_delete_count,
                                burst_window_min,
                                last_alert_at_str,
                                expires_at_str,
                            )
                            # Диагностика: покажем, что проверка вообще работает и почему порог не достигнут.
                            if streak_count >= max(1, burst_delete_count - 2):
                                dbg = (
                                    "DEBUG spike check\n"
                                    f"chat={chat_id_i}\n"
                                    f"recent={streak_count}\n"
                                    f"consecutive={is_consecutive_spam}\n"
                                    f"in_window={in_time_window}\n"
                                    f"alert_active={alert_active}\n"
                                    f"last_alert_at={last_alert_at_str}\n"
                                    f"expires_at={expires_at_str}\n"
                                    f"missing_ts={missing_ts}\n"
                                    f"required={burst_delete_count}\n"
                                    f"window_min={burst_window_min}\n"
                                    f"action={str(v.action or '').lower()}\n"
                                    f"deleted_ok={bool(deleted_ok)}"
                                )
                                await _send_spike_debug(
                                    message.bot,
                                    dbg,
                                    extra_ids=[int(getattr(message.from_user, "id", 0) or 0)],
                                )
                    except Exception as e:
                        logger.warning(
                            "immediate spam_spike check failed chat=%s: %s",
                            message.chat.id,
                            e,
                        )
                        await _send_spike_debug(
                            message.bot,
                            "DEBUG spike error\n"
                            f"chat={int(message.chat.id)}\n"
                            f"err={str(e)[:300]}",
                            extra_ids=[int(getattr(message.from_user, "id", 0) or 0)],
                        )
            # ТЗ Напоминания: активность чата для сообщений Guard раз в 3 дня
            chat_row = await session.get(Chat, message.chat.id)
            if chat_row:
                chat_row.last_activity_at = datetime.now(timezone.utc)
            await session.commit()
        except Exception as e:
            logger.exception(f"[pipeline error] chat={message.chat.id} msg={message.message_id}: {e}")


# =========================================================
# Handlers
# =========================================================

def _has_new_chat_members(message: Message) -> bool:
    return bool(message.new_chat_members)


def _has_left_chat_member(message: Message) -> bool:
    return getattr(message, "left_chat_member", None) is not None


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.func(_has_new_chat_members),
)
async def on_join_service_message(message: Message):
    """
    Сервисное «вступил в группу» (new_chat_members). Удаление по rule.delete_join_messages.
    Не проходит через pipeline: там нет текста/медиа, обработчик раньше завершался без действий.
    """
    try:
        async with await get_session() as session:
            chat_row = await session.get(Chat, message.chat.id)
            if not chat_row or not getattr(chat_row, "is_active", True):
                return
            rule = await get_rule(session, message.chat.id)
            if not bool(getattr(rule, "delete_join_messages", True)):
                return
        await _delete_message_with_thread(message)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await record_bot_delete_message_failed(context="join_service", message=message, exc=e)
    except Exception as e:
        logger.debug("on_join_service_message chat=%s: %s", message.chat.id, e)


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.func(_has_left_chat_member),
)
async def on_left_service_message(message: Message):
    """
    Сервисное «покинул группу» (left_chat_member). Удаление по rule.delete_left_messages.
    """
    try:
        async with await get_session() as session:
            chat_row = await session.get(Chat, message.chat.id)
            if not chat_row or not getattr(chat_row, "is_active", True):
                return
            rule = await get_rule(session, message.chat.id)
            if not bool(getattr(rule, "delete_left_messages", True)):
                return
        await _delete_message_with_thread(message)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await record_bot_delete_message_failed(context="left_service", message=message, exc=e)
    except Exception as e:
        logger.debug("on_left_service_message chat=%s: %s", message.chat.id, e)


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
                    if not bool(getattr(leave_user, "is_bot", False)):
                        session.add(MemberLeft(chat_id=chat_id, user_id=int(leave_user.id)))
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

            try:
                from app.handlers.join_captcha import maybe_start_join_captcha

                await maybe_start_join_captcha(bot, session, event.chat, chat_row, rule, user)
            except Exception as jc_err:
                logger.exception("join_captcha start: %s", jc_err)

            # Приветствие новых участников (по настройке конкретного чата).
            try:
                if bool(getattr(rule, "welcome_enabled", False)) and not bool(getattr(user, "is_bot", False)):
                    if bool(getattr(rule, "join_captcha_enabled", False)):
                        raise RuntimeError("welcome_wait_join_captcha")
                    every_n = max(1, min(500, int(getattr(rule, "welcome_every_n_joins", 1) or 1)))
                    total_joins_q = await session.execute(
                        select(func.count(NewMember.id)).where(NewMember.chat_id == int(chat_id))
                    )
                    total_joins = int(total_joins_q.scalar() or 0)
                    if every_n > 1 and (total_joins % every_n) != 0:
                        raise RuntimeError("welcome_every_n_joins_skip")
                    # Режим "молчать при рейде": если за окно уже много входов — приветствия не шлём.
                    silent_on_raid = bool(getattr(rule, "welcome_silent_on_raid", False))
                    raid_threshold = max(2, min(200, int(getattr(rule, "welcome_raid_threshold", 8) or 8)))
                    raid_window_min = max(1, min(60, int(getattr(rule, "welcome_raid_window_minutes", 2) or 2)))
                    if silent_on_raid:
                        since = datetime.now(timezone.utc) - timedelta(minutes=raid_window_min)
                        joins_q = await session.execute(
                            select(func.count(NewMember.id)).where(
                                NewMember.chat_id == int(chat_id),
                                NewMember.joined_at >= since,
                            )
                        )
                        joins_cnt = int(joins_q.scalar() or 0)
                        if joins_cnt >= raid_threshold:
                            raise RuntimeError("welcome_silent_on_raid")
                    # Лимит приветствий в минуту.
                    max_per_min = max(0, min(60, int(getattr(rule, "welcome_max_per_min", 0) or 0)))
                    if not _welcome_rate_allowed(int(chat_id), max_per_min):
                        raise RuntimeError("welcome_rate_limited")
                    raw_text = str(getattr(rule, "welcome_text", "") or "").strip()
                    if raw_text:
                        chat_title = str(getattr(event.chat, "title", "") or "")
                        uname = str(getattr(user, "username", "") or "").lstrip("@")
                        username_display = f"@{uname}" if uname else ""
                        txt = (
                            raw_text
                            .replace("{first_name}", html.escape(str(getattr(user, "first_name", "") or "друг"), quote=False))
                            .replace(
                                "{full_name}",
                                html.escape(
                                    str(getattr(user, "full_name", "") or getattr(user, "first_name", "") or "друг"),
                                    quote=False,
                                ),
                            )
                            .replace("{username}", html.escape(username_display, quote=False))
                            .replace("{chat_title}", html.escape(chat_title, quote=False))
                        )
                        kb = _welcome_keyboard_from_json(getattr(rule, "welcome_buttons_json", None))
                        photo_rel = str(getattr(rule, "welcome_photo_path", "") or "").strip()
                        if photo_rel:
                            fp = (_welcome_media_root() / photo_rel).resolve()
                            root = _welcome_media_root().resolve()
                            if (root in fp.parents or fp == root) and fp.exists() and fp.is_file():
                                await bot.send_photo(
                                    chat_id,
                                    FSInputFile(str(fp)),
                                    caption=txt[:1024],
                                    parse_mode="HTML",
                                    reply_markup=kb,
                                )
                            else:
                                await bot.send_message(chat_id, txt[:4000], parse_mode="HTML", reply_markup=kb)
                        else:
                            await bot.send_message(chat_id, txt[:4000], parse_mode="HTML", reply_markup=kb)
            except Exception as w_err:
                reason = str(w_err or "").strip().lower()
                if reason in (
                    "welcome_every_n_joins_skip",
                    "welcome_silent_on_raid",
                    "welcome_rate_limited",
                    "welcome_wait_join_captcha",
                ):
                    logger.info("welcome skip chat=%s user=%s reason=%s", chat_id, user_id, reason)
                else:
                    logger.warning("welcome send failed chat=%s user=%s err=%s", chat_id, user_id, w_err)

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
            ct = html.escape(chat_title)
            alert_text = (
                f"⚠ <b>Антинакрутка</b>\n\n"
                f"Обнаружен массовый вход в чат <b>{ct}</b>.\n"
                f"За последние <b>{window_min}</b> мин вступило <b>{len(joins_list)}</b> участников (порог {threshold})."
            )
            if log_chat_id:
                try:
                    await bot.send_message(log_chat_id, alert_text, parse_mode="HTML")
                except Exception as e:
                    logger.warning("antinakrutka log send: %s", e)
            try:
                await bot.send_message(chat_id, alert_text, parse_mode="HTML")
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


async def _try_apply_reputation(message: Message) -> None:
    chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
    from_user_id = int(getattr(getattr(message, "from_user", None), "id", 0) or 0)
    if chat_id == 0 or from_user_id == 0:
        return
    text_value = str(message.text or message.caption or "")
    if not text_value.strip():
        return
    try:
        async with await get_session() as session:
            target_user_id = await _reputation_target_user_id(session, message)
            if not target_user_id:
                return
            rule = await get_rule(session, chat_id)
            if not bool(getattr(rule, "reputation_enabled", False)):
                return
            words = await load_reputation_words(session, chat_id)
            if not _text_has_reputation_trigger(text_value, words):
                return
            last_evt_q = await session.execute(
                select(ChatReputationEvent.created_at)
                .where(
                    ChatReputationEvent.chat_id == chat_id,
                    ChatReputationEvent.from_user_id == from_user_id,
                    ChatReputationEvent.to_user_id == target_user_id,
                )
                .order_by(ChatReputationEvent.created_at.desc())
                .limit(1)
            )
            last_evt = last_evt_q.scalar_one_or_none()
            if last_evt is not None:
                last_evt = last_evt if last_evt.tzinfo else last_evt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - last_evt < REPUTATION_PAIR_COOLDOWN:
                    return
            try:
                session.add(
                    ChatReputationEvent(
                        chat_id=chat_id,
                        from_user_id=from_user_id,
                        to_user_id=target_user_id,
                        message_id=int(getattr(message, "message_id", 0) or 0),
                    )
                )
                await session.flush()
            except Exception:
                await session.rollback()
                return
            await session.execute(
                text(
                    """
                    INSERT INTO chat_reputation_scores (chat_id, user_id, score)
                    VALUES (:cid, :uid, 1)
                    ON CONFLICT (chat_id, user_id)
                    DO UPDATE SET
                      score = chat_reputation_scores.score + 1,
                      updated_at = now()
                    """
                ),
                {"cid": chat_id, "uid": target_user_id},
            )
            score_q = await session.execute(
                select(ChatReputationScore.score)
                .where(ChatReputationScore.chat_id == chat_id, ChatReputationScore.user_id == target_user_id)
                .limit(1)
            )
            total_score = int(score_q.scalar_one_or_none() or 0)
            await session.commit()
            mention = f"<a href='tg://user?id={target_user_id}'>пользователю</a>"
            try:
                await message.reply(
                    f"⭐ Guard отметил: + 1 к карме {mention}.\n"
                    f"Баланс участника: <b>{total_score}</b>.\n"
                    f"Команды: <b>/karma</b> · <b>/topkarma</b>",
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception:
                # Если нельзя ответить в тред/топик — пробуем обычным сообщением.
                try:
                    await message.bot.send_message(
                        chat_id,
                        f"⭐ Guard отметил: + 1 к карме {mention}. Баланс участника: <b>{total_score}</b>. Команды: <b>/karma</b> · <b>/topkarma</b>.",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.debug("reputation apply failed chat=%s: %s", chat_id, e)


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.func(lambda m: bool(getattr(m, "new_chat_title", None))),
)
async def on_new_chat_title(message: Message):
    """Синхронизировать название группы в БД при смене названия в Telegram."""
    title = (message.new_chat_title or "").strip()
    if not title:
        return
    title = title[:255]
    try:
        async with await get_session() as session:
            chat_row = await session.get(Chat, message.chat.id)
            if chat_row:
                chat_row.title = title
                await session.commit()
    except Exception as e:
        logger.warning("on_new_chat_title chat=%s: %s", message.chat.id, e)


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.func(_should_run_moderation_pipeline),
    ~F.func(_has_new_chat_members),
)
async def on_message(message: Message):
    # Текстовая капча входа: join_captcha уже обработал/удалил; не гоняем через фильтры (ссылки, стоп-слова…).
    from app.handlers.join_captcha import active_join_text_captcha_row

    if await active_join_text_captcha_row(message):
        return
    await _record_activity_event(message)
    await _maybe_handle_channel_comment_rules(message)
    await pipeline(message, edited=False)
    await _try_apply_reputation(message)


async def _record_activity_event(message: Message) -> None:
    """Лёгкая регистрация события активности (любое сообщение в группе) для аналитики."""
    try:
        chat = getattr(message, "chat", None)
        user = getattr(message, "from_user", None)
        if not chat or not user:
            return
        chat_id = int(getattr(chat, "id", 0) or 0)
        user_id = int(getattr(user, "id", 0) or 0)
        if not chat_id or not user_id:
            return
        if bool(getattr(user, "is_bot", False)):
            return
        async with await get_session() as session:
            session.add(ChatActivityEvent(chat_id=chat_id, user_id=user_id))
            await session.commit()
    except Exception as e:
        logger.debug("activity_event: %s", e)

@router.edited_message(
    F.chat.type.in_({"group", "supergroup"}),
    F.func(_should_run_moderation_pipeline),
    ~F.func(_has_new_chat_members),
)
async def on_edit(message: Message):
    from app.handlers.join_captcha import active_join_text_captcha_row

    if await active_join_text_captcha_row(message):
        return
    await pipeline(message, edited=True)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.regexp(r"^/karma(?:@\w+)?$"))
async def on_karma_command(message: Message):
    user_id = int(getattr(getattr(message, "from_user", None), "id", 0) or 0)
    chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
    if user_id <= 0 or chat_id == 0:
        return
    async with await get_session() as session:
        rule = await get_rule(session, chat_id)
        if not bool(getattr(rule, "reputation_enabled", False)):
            await message.reply("Репутация в этом чате выключена.")
            return
        row = await session.execute(
            select(ChatReputationScore.score)
            .where(ChatReputationScore.chat_id == chat_id, ChatReputationScore.user_id == user_id)
            .limit(1)
        )
        score = int(row.scalar_one_or_none() or 0)
    await message.reply(f"Ваша репутация: {score} кармы.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.regexp(r"^/topkarma(?:@\w+)?$"))
async def on_top_karma_command(message: Message):
    chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
    if chat_id == 0:
        return
    async with await get_session() as session:
        rule = await get_rule(session, chat_id)
        if not bool(getattr(rule, "reputation_enabled", False)):
            await message.reply("Репутация в этом чате выключена.")
            return
        rows = await session.execute(
            select(ChatReputationScore.user_id, ChatReputationScore.score)
            .where(ChatReputationScore.chat_id == chat_id)
            .order_by(ChatReputationScore.score.desc(), ChatReputationScore.updated_at.desc())
            .limit(5)
        )
        top = rows.all()
        uid_list = [int(uid) for uid, _ in top if int(uid or 0) > 0]
        username_map: dict[int, str] = {}
        if uid_list:
            uq = await session.execute(
                select(User.telegram_id, User.username).where(User.telegram_id.in_(uid_list))
            )
            for tid, uname in uq.all():
                username_map[int(tid or 0)] = str(uname or "")
    if not top:
        await message.reply("Пока нет начисленной кармы.")
        return
    lines = ["🏆 Топ кармы:"]
    for idx, (uid, score) in enumerate(top, start=1):
        uname = str(username_map.get(int(uid), "") or "").strip().lstrip("@")
        who = f"@{uname}" if uname else f"id{int(uid)}"
        lines.append(f"{idx}. {who} — {int(score or 0)}")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.regexp(r"^\s*карма\s*$"))
async def on_karma_plain(message: Message):
    await on_karma_command(message)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.regexp(r"^\s*топ\s+кармы\s*$"))
async def on_top_karma_plain(message: Message):
    await on_top_karma_command(message)
