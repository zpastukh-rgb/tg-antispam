# app/services/public_alerts.py
"""Публичные сообщения Guard раз в N срабатываний модерации (ТЗ ПРАВКИ 2)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_owner_locale import owner_locale_for_chat
from app.texts.guard_group_messages import public_alert_pools

REASON_TO_CATEGORY = {
    "stopword": "spam",
    "stopword_newbie": "spam",
    "profanity": "bad_words",
    "profanity_newbie": "bad_words",
    "link": "link",
    "link_newbie": "link",
    "link_blacklist": "link",
    "link_blacklist_newbie": "link",
    "global_bad_url": "link",
    "global_bad_url_newbie": "link",
    "mention": "generic",
    "mention_newbie": "generic",
    "media": "generic",
    "media_newbie": "generic",
    "buttons": "generic",
    "buttons_newbie": "generic",
    "spam": "spam",
    "edited_clean": "generic",
}

_DELETE_COUNTER: dict[int, int] = {}
_LAST_PHRASE_IDX: dict[tuple[int, str, str, str], int] = {}


def _choice_from_pool(pool: list[str], *, chat_id: int = 0, key: tuple[int, str, str, str] | None = None) -> str:
    """
    Случайная фраза: secrets + смещение от id чата, чтобы у разных групп не «билась» одна и та же
    последовательность при одинаковых таймингах, при этом выбор остаётся непредсказуемым.
    """
    n = len(pool)
    if n == 0:
        return ""
    if n == 1:
        return pool[0]
    base = (secrets.randbelow(n) + (abs(int(chat_id or 0)) % n)) % n
    i = base
    if key is not None:
        prev = _LAST_PHRASE_IDX.get(key)
        if prev is not None and prev == i:
            # Избегаем одинаковых подряд в одном чате/категории/стиле.
            shift = 1 + secrets.randbelow(max(1, n - 1))
            i = (i + shift) % n
        _LAST_PHRASE_IDX[key] = i
    return pool[i]


def _style(rule) -> str:
    s = (getattr(rule, "public_alerts_style", None) or "guard").strip().lower()
    return s if s in ("soft", "medium", "guard") else "guard"


def _pick(
    locale: str,
    rule,
    key_soft: str,
    key_med: str,
    key_guard: str,
    *,
    chat_id: int = 0,
    category: str = "generic",
    action: str = "delete",
) -> str:
    st = _style(rule)
    pools = public_alert_pools(locale)
    if st == "soft":
        pool = pools.get(key_soft, [])
    elif st == "medium":
        pool = pools.get(key_med, [])
    else:
        pool = pools.get(key_guard, [])
    if not pool:
        pool = pools.get(key_guard, []) or pools.get(key_med, []) or pools.get(key_soft, [])
    key = (int(chat_id or 0), st, category, action)
    return _choice_from_pool(pool, chat_id=chat_id, key=key)


def _get_phrase(locale: str, rule, reason: str, action: str = "delete", *, chat_id: int = 0) -> str:
    if action == "mute":
        return _pick(
            locale, rule, "mute_soft", "mute_med", "mute_guard", chat_id=chat_id, category="mute", action="mute"
        )
    if action == "ban":
        return _pick(locale, rule, "ban_soft", "ban_med", "ban_guard", chat_id=chat_id, category="ban", action="ban")
    cat = REASON_TO_CATEGORY.get(reason, "generic")
    if cat == "spam":
        return _pick(
            locale, rule, "spam_soft", "spam_med", "spam_guard", chat_id=chat_id, category="spam", action=action
        )
    if cat == "link":
        return _pick(
            locale, rule, "link_soft", "link_med", "link_guard", chat_id=chat_id, category="link", action=action
        )
    if cat == "bad_words":
        return _pick(
            locale, rule, "bad_soft", "bad_med", "bad_guard", chat_id=chat_id, category="bad_words", action=action
        )
    return _pick(locale, rule, "gen_soft", "gen_med", "gen_guard", chat_id=chat_id, category="generic", action=action)


async def maybe_send_public_alert(
    bot,
    chat_id: int,
    rule,
    reason: str,
    action: str,
    session: AsyncSession,
    *,
    source_message: Message | None = None,
) -> None:
    """
    После успешного удаления/наказания: счётчик по чату; при N срабатываниях и паузе — фраза в чат.
    Также нужен guardian_messages_enabled (общий флаг «сообщения Guard»).
    """
    if not getattr(rule, "guardian_messages_enabled", True):
        return
    if not getattr(rule, "public_alerts_enabled", False):
        return
    every_n = max(1, getattr(rule, "public_alerts_every_n", 5))
    min_interval_sec = max(0, getattr(rule, "public_alerts_min_interval_sec", 300))

    count = _DELETE_COUNTER.get(chat_id, 0) + 1
    _DELETE_COUNTER[chat_id] = count

    if count < every_n:
        return

    now = datetime.now(timezone.utc)
    last_sent = getattr(rule, "public_alerts_last_sent_at", None)
    if last_sent:
        delta = (now - last_sent).total_seconds()
        if delta < min_interval_sec:
            return

    locale = await owner_locale_for_chat(session, int(chat_id))
    phrase = _get_phrase(locale, rule, reason, action, chat_id=chat_id)
    send_kwargs: dict = {}
    if source_message is not None:
        try:
            from aiogram.types import ReplyParameters

            r = getattr(source_message, "reply_to_message", None)
            if r and getattr(r, "sender_chat", None):
                st = str(getattr(r.sender_chat, "type", "") or "").lower()
                if st == "channel":
                    send_kwargs["reply_parameters"] = ReplyParameters(message_id=int(r.message_id))
            if "reply_parameters" not in send_kwargs:
                mtid = getattr(source_message, "message_thread_id", None)
                ch = getattr(source_message, "chat", None)
                if mtid is not None and getattr(ch, "is_forum", False):
                    send_kwargs["message_thread_id"] = int(mtid)
        except Exception:
            send_kwargs.clear()
    try:
        await bot.send_message(chat_id, phrase, **send_kwargs)
    except Exception:
        return

    _DELETE_COUNTER[chat_id] = 0
    rule.public_alerts_last_sent_at = now
    await session.commit()
