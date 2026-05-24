"""Детекция флуда: повтор текста и массовая отправка сообщений (текст + медиа)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FloodRateEvent, FloodTextEvent

_MIN_TEXT_LEN = 8
_STRICT_BURST_WINDOW_SEC = 10
_STRICT_BURST_THRESHOLD = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_flood_mode(raw: str | None) -> str:
    v = str(raw or "").strip().lower()
    if v in ("strict", "строгий", "строг"):
        return "strict"
    return "soft"


def normalize_flood_action(raw: str | None) -> str:
    v = str(raw or "").strip().lower()
    if v in ("ban", "mute", "delete"):
        return v
    if "бан" in v:
        return "ban"
    if "мут" in v or "заглуш" in v:
        return "mute"
    if "удал" in v:
        return "delete"
    return "mute"


def _normalize_flood_text(text: str) -> str:
    t = (text or "").strip().lower().replace("ё", "е")
    t = re.sub(r"\s+", " ", t)
    return t


def _text_hash(norm: str) -> str:
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


async def _record_rate_event(session: AsyncSession, chat_id: int, user_id: int) -> None:
    session.add(
        FloodRateEvent(
            chat_id=int(chat_id),
            user_id=int(user_id),
            created_at=_now(),
        )
    )


async def _check_rate_burst(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
    *,
    window_sec: int,
    threshold: int,
) -> bool:
    since = _now() - timedelta(seconds=window_sec)
    q = await session.execute(
        select(func.count()).select_from(FloodRateEvent).where(
            FloodRateEvent.chat_id == int(chat_id),
            FloodRateEvent.user_id == int(user_id),
            FloodRateEvent.created_at >= since,
        )
    )
    return int(q.scalar() or 0) >= threshold


async def _check_rate_window(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
    *,
    window_minutes: int,
    threshold: int,
) -> bool:
    since = _now() - timedelta(minutes=window_minutes)
    q = await session.execute(
        select(func.count()).select_from(FloodRateEvent).where(
            FloodRateEvent.chat_id == int(chat_id),
            FloodRateEvent.user_id == int(user_id),
            FloodRateEvent.created_at >= since,
        )
    )
    return int(q.scalar() or 0) >= threshold


async def _check_duplicate_text(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
    text: str,
    rule: Any,
    *,
    threshold_override: int | None = None,
) -> bool:
    norm = _normalize_flood_text(text)
    if len(norm) < _MIN_TEXT_LEN:
        return False

    threshold = threshold_override
    if threshold is None:
        threshold = max(2, min(20, int(getattr(rule, "mech_filter_flood_threshold", 3) or 3)))
    window = max(1, min(60, int(getattr(rule, "mech_filter_flood_window_minutes", 5) or 5)))
    since = _now() - timedelta(minutes=window)
    th = _text_hash(norm)

    session.add(
        FloodTextEvent(
            chat_id=int(chat_id),
            user_id=int(user_id),
            text_norm_hash=th,
            created_at=_now(),
        )
    )

    q = await session.execute(
        select(func.count()).select_from(FloodTextEvent).where(
            FloodTextEvent.chat_id == int(chat_id),
            FloodTextEvent.user_id == int(user_id),
            FloodTextEvent.text_norm_hash == th,
            FloodTextEvent.created_at >= since,
        )
    )
    cnt = int(q.scalar() or 0)

    cutoff = _now() - timedelta(hours=6)
    await session.execute(
        delete(FloodTextEvent).where(
            FloodTextEvent.chat_id == int(chat_id),
            FloodTextEvent.created_at < cutoff,
        )
    )
    await session.execute(
        delete(FloodRateEvent).where(
            FloodRateEvent.chat_id == int(chat_id),
            FloodRateEvent.created_at < cutoff,
        )
    )

    return cnt >= threshold


async def check_flood(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
    rule: Any,
    *,
    text: str = "",
    has_media_msg: bool = False,
) -> tuple[bool, str]:
    """
    Проверка флуда. Возвращает (сработало, kind): duplicate | rate | "".
    soft — только повтор одного текста; strict — текст + медиа, всплески и повторы.
    """
    if not bool(getattr(rule, "mech_filter_flood_enabled", False)):
        return False, ""
    if user_id <= 0:
        return False, ""

    mode = normalize_flood_mode(getattr(rule, "mech_filter_flood_mode", "soft"))
    has_content = bool((text or "").strip()) or has_media_msg

    if mode == "strict" and has_content:
        await _record_rate_event(session, chat_id, user_id)
        if await _check_rate_burst(
            session,
            chat_id,
            user_id,
            window_sec=_STRICT_BURST_WINDOW_SEC,
            threshold=_STRICT_BURST_THRESHOLD,
        ):
            return True, "rate"

        base_thr = max(2, min(20, int(getattr(rule, "mech_filter_flood_threshold", 3) or 3)))
        window = max(1, min(60, int(getattr(rule, "mech_filter_flood_window_minutes", 5) or 5)))
        sustained_thr = max(_STRICT_BURST_THRESHOLD, base_thr + 2)
        if await _check_rate_window(
            session,
            chat_id,
            user_id,
            window_minutes=window,
            threshold=sustained_thr,
        ):
            return True, "rate"

    dup_thr = max(2, min(20, int(getattr(rule, "mech_filter_flood_threshold", 3) or 3)))
    if mode == "strict":
        dup_thr = max(2, dup_thr - 1)

    if (text or "").strip():
        if await _check_duplicate_text(
            session,
            chat_id,
            user_id,
            text,
            rule,
            threshold_override=dup_thr,
        ):
            return True, "duplicate"

    return False, ""


# Обратная совместимость для тестов
async def check_and_record_flood(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
    text: str,
    rule: Any,
) -> bool:
    hit, _ = await check_flood(session, chat_id, user_id, rule, text=text, has_media_msg=False)
    return hit
