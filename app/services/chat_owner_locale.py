"""Язык владельца чата (Mini App / бота) для публичных сообщений Guard в группе."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, User
from app.i18n import DEFAULT_LOCALE, normalize_locale


async def owner_locale_for_chat(session: AsyncSession, chat_id: int) -> str:
    q = await session.execute(
        select(User.language)
        .select_from(Chat)
        .join(User, User.telegram_id == Chat.owner_user_id)
        .where(Chat.id == int(chat_id))
        .limit(1)
    )
    raw = q.scalar_one_or_none()
    if raw is None:
        return DEFAULT_LOCALE
    return normalize_locale(str(raw))


async def user_locale(session: AsyncSession, telegram_id: int) -> str:
    q = await session.execute(
        select(User.language).where(User.telegram_id == int(telegram_id)).limit(1)
    )
    raw = q.scalar_one_or_none()
    if raw is None:
        return DEFAULT_LOCALE
    return normalize_locale(str(raw))
