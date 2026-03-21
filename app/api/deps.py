# app/api/deps.py
"""Зависимости API: сессия БД."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Сессия БД для запроса."""
    try:
        session = await get_session()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    async with session:
        yield session
