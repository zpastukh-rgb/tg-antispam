# app/services/user_service.py
"""Сервис пользователя: создание, тариф, лимит чатов."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Chat, Tariff

# Лимит чатов по тарифу: бесплатный — 3 группы, PRO — 5, BUSINESS — 20
TARIFF_CHAT_LIMITS = {
    Tariff.FREE.value: 3,
    Tariff.PRO.value: 5,
    Tariff.BUSINESS.value: 20,
}


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Получить или создать пользователя. По умолчанию FREE, chat_limit=3."""
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = res.scalar_one_or_none()
    if user:
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        await session.commit()
        await session.refresh(user)
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        tariff=Tariff.FREE.value,
        chat_limit=TARIFF_CHAT_LIMITS[Tariff.FREE.value],
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def count_protected_chats(session: AsyncSession, telegram_id: int) -> int:
    """Количество защищаемых чатов пользователя (владелец или менеджер)."""
    from app.db.models import ChatManager
    from sqlalchemy import or_

    sub = select(ChatManager.chat_id).where(ChatManager.user_id == telegram_id).subquery()
    res = await session.execute(
        select(Chat)
        .where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            or_(
                Chat.owner_user_id == telegram_id,
                Chat.id.in_(select(sub.c.chat_id)),
            ),
        )
    )
    return len(list(res.scalars().all()))


async def can_add_chat(session: AsyncSession, telegram_id: int) -> tuple[bool, int, int]:
    """
    Можно ли подключить ещё один чат.
    Returns: (can_add, current_count, limit).
    """
    user = await get_or_create_user(session, telegram_id)
    count = await count_protected_chats(session, telegram_id)
    limit = user.chat_limit
    return (count < limit, count, limit)
