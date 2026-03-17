# app/services/global_antispam.py
"""Антиспам база пользователей: общая для бота по всем группам."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GlobalAntispamUser


async def is_in_global_antispam(session: AsyncSession, user_id: int) -> bool:
    """Проверить, есть ли user_id в глобальной антиспам базе."""
    row = await session.get(GlobalAntispamUser, user_id)
    return row is not None


async def add_to_global_antispam(session: AsyncSession, user_id: int, reason: str | None = None) -> bool:
    """Добавить в базу. Возвращает True если добавлен, False если уже был."""
    if await session.get(GlobalAntispamUser, user_id):
        return False
    session.add(GlobalAntispamUser(user_id=user_id, reason=(reason or "").strip() or None))
    await session.commit()
    return True


async def remove_from_global_antispam(session: AsyncSession, user_id: int) -> bool:
    """Удалить из базы. Возвращает True если удалён."""
    row = await session.get(GlobalAntispamUser, user_id)
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def list_global_antispam(session: AsyncSession, limit: int = 500) -> list[dict]:
    """Список записей: [{ user_id, reason, created_at }, ...]."""
    res = await session.execute(
        select(GlobalAntispamUser).order_by(GlobalAntispamUser.created_at.desc()).limit(limit)
    )
    rows = res.scalars().all()
    return [
        {"user_id": r.user_id, "reason": r.reason or "", "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]
