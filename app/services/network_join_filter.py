"""Детекция массового входа одного user_id в разные чаты Guard (аналог «папок»)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NetworkJoinEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def record_network_join(session: AsyncSession, user_id: int, chat_id: int) -> None:
    session.add(
        NetworkJoinEvent(
            user_id=int(user_id),
            chat_id=int(chat_id),
            joined_at=_now(),
        )
    )


async def count_distinct_chats_in_window(
    session: AsyncSession,
    user_id: int,
    window_minutes: int,
) -> int:
    since = _now() - timedelta(minutes=max(1, min(120, int(window_minutes))))
    q = await session.execute(
        select(func.count(func.distinct(NetworkJoinEvent.chat_id))).where(
            NetworkJoinEvent.user_id == int(user_id),
            NetworkJoinEvent.joined_at >= since,
        )
    )
    return int(q.scalar() or 0)


async def is_network_mass_joiner(session: AsyncSession, user_id: int, rule: Any) -> bool:
    if not bool(getattr(rule, "join_filter_network_mass_join", False)):
        return False
    threshold = max(2, min(30, int(getattr(rule, "join_filter_network_join_threshold", 4) or 4)))
    window = max(1, min(120, int(getattr(rule, "join_filter_network_join_window_minutes", 10) or 10)))
    cnt = await count_distinct_chats_in_window(session, int(user_id), window)
    return cnt >= threshold


async def prune_old_network_join_events(session: AsyncSession, *, keep_hours: int = 48) -> None:
    """Удаляет старые события (вызывать периодически или после записи)."""
    cutoff = _now() - timedelta(hours=max(6, int(keep_hours)))
    await session.execute(delete(NetworkJoinEvent).where(NetworkJoinEvent.joined_at < cutoff))
