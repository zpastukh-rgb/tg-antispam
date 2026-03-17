# app/services/chat_cleanup.py
"""Очистка от удалённых аккаунтов: учёт участников и проверка через getChatMember."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatSeenMember


# Признаки удалённого аккаунта в Telegram (first_name)
DELETED_ACCOUNT_NAMES = ("deleted account", "удалённый аккаунт", "deleted", "account deleted")


def _is_deleted_user_first_name(first_name: str | None) -> bool:
    if not first_name:
        return False
    fn = (first_name or "").strip().lower()
    return any(marker in fn for marker in DELETED_ACCOUNT_NAMES)


async def record_seen_member(session: AsyncSession, chat_id: int, user_id: int) -> None:
    """Записать, что пользователь виделся в чате (для последующей очистки от удалённых)."""
    try:
        row = await session.get(ChatSeenMember, (chat_id, user_id))
        now = datetime.now(timezone.utc)
        if row:
            row.last_seen_at = now
        else:
            session.add(ChatSeenMember(chat_id=chat_id, user_id=user_id, last_seen_at=now))
        await session.commit()
    except Exception:
        await session.rollback()


async def get_seen_member_ids(session: AsyncSession, chat_id: int, limit: int = 5000) -> list[int]:
    """Список user_id, которых видели в чате (для проверки на удалённые)."""
    res = await session.execute(
        select(ChatSeenMember.user_id).where(ChatSeenMember.chat_id == chat_id).limit(limit)
    )
    return [r[0] for r in res.all()]


async def remove_seen_member(session: AsyncSession, chat_id: int, user_id: int) -> None:
    """Удалить из учёта (после выхода или кика)."""
    row = await session.get(ChatSeenMember, (chat_id, user_id))
    if row:
        await session.delete(row)
        await session.commit()


async def clean_deleted_accounts(bot, session: AsyncSession, chat_id: int) -> tuple[int, int]:
    """
    Проверить участников чата на удалённые аккаунты и исключить их из группы.
    Returns: (kicked_count, checked_count).
    """
    from app.handlers.moderation import is_admin

    user_ids = await get_seen_member_ids(session, chat_id)
    kicked = 0
    for uid in user_ids:
        try:
            mem = await bot.get_chat_member(chat_id, uid)
            status = getattr(mem, "status", None)
            if status in ("left", "kicked"):
                await remove_seen_member(session, chat_id, uid)
                continue
            user = getattr(mem, "user", None)
            if not user:
                continue
            first_name = getattr(user, "first_name", None)
            if not _is_deleted_user_first_name(first_name):
                continue
            if await is_admin(bot, chat_id, uid):
                continue
            await bot.ban_chat_member(chat_id, uid)
            kicked += 1
            await remove_seen_member(session, chat_id, uid)
        except Exception:
            continue
    return kicked, len(user_ids)
