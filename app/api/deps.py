# app/api/deps.py
"""Зависимости API: сессия БД."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Сессия БД для запроса."""
    session = await get_session()
    async with session:
        yield session
