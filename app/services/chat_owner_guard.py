# app/services/chat_owner_guard.py
"""Синхронизация владельца кабинета Guard с creator группы и отзыв доступа при потере админки."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.enums import ChatMemberStatus
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, ChatManager
from app.services.group_connect_actor import telegram_user_is_chat_creator
from app.services.telegram_bot_api import (
    tg_resolve_group_creator_id,
    tg_user_is_group_admin,
)

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)


async def resolve_group_creator_id(bot: Bot | None, chat_id: int) -> int | None:
    """Creator группы по Telegram API (aiogram или HTTP)."""
    cid = int(chat_id)
    if bot is not None:
        try:
            members = await bot.get_chat_administrators(cid)
            for member in members:
                if member.status == ChatMemberStatus.CREATOR:
                    return int(member.user.id)
        except Exception as e:
            logger.debug("resolve_group_creator_id aiogram chat=%s: %s", cid, e)
    return await tg_resolve_group_creator_id(cid)


async def user_is_group_admin(bot: Bot | None, chat_id: int, user_id: int) -> bool:
    uid = int(user_id)
    if uid <= 0:
        return False
    if bot is not None:
        try:
            m = await bot.get_chat_member(int(chat_id), uid)
            return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
        except Exception as e:
            logger.debug("user_is_group_admin aiogram chat=%s user=%s: %s", chat_id, uid, e)
    return await tg_user_is_group_admin(int(chat_id), uid)


async def apply_chat_owner_on_connect(
    bot: Bot,
    chat_row: Chat,
    resolved_owner_id: int,
) -> tuple[bool, str | None]:
    """
    При подключении: owner = creator (resolved_owner_id).
    Если в БД другой владелец — creator забирает чат (в т.ч. когда is_active=True).
    """
    rid = int(resolved_owner_id or 0)
    if rid <= 0:
        return False, "owner"
    cid = int(chat_row.id)
    ow = int(getattr(chat_row, "owner_user_id", 0) or 0)
    if ow in (0, rid):
        chat_row.owner_user_id = rid
        return True, None
    if await telegram_user_is_chat_creator(bot, cid, rid):
        chat_row.owner_user_id = rid
        return True, None
    return False, "owner"



async def transfer_chat_owner_to_creator_if_needed(
    bot: Bot | None,
    chat_row: Chat,
) -> tuple[int, bool]:
    """Если creator ≠ owner в БД — переписываем owner_user_id. Returns (owner_id, changed)."""
    cid = int(chat_row.id)
    current = int(getattr(chat_row, "owner_user_id", 0) or 0)
    creator_id = await resolve_group_creator_id(bot, cid)
    if creator_id and creator_id > 0 and creator_id != current:
        chat_row.owner_user_id = int(creator_id)
        logger.info("guard owner transfer chat=%s from=%s to creator=%s", cid, current, creator_id)
        return int(creator_id), True
    return current, False


async def revoke_guard_access_on_admin_loss(
    bot: Bot | None,
    session: AsyncSession,
    chat_id: int,
    user_id: int,
) -> None:
    """
    Пользователь потерял админку / вышел из группы:
    - делегат → удалить ChatManager;
    - owner без админки → передать creator, если найден.
    """
    uid = int(user_id)
    cid = int(chat_id)
    if uid <= 0 or cid == 0:
        return
    chat_row = await session.get(Chat, cid)
    if not chat_row or bool(getattr(chat_row, "is_log_chat", False)):
        return

    owner_id = int(getattr(chat_row, "owner_user_id", 0) or 0)
    if uid != owner_id:
        await session.execute(
            delete(ChatManager).where(ChatManager.chat_id == cid, ChatManager.user_id == uid),
        )
        return

    if await user_is_group_admin(bot, cid, uid):
        return

    creator_id = await resolve_group_creator_id(bot, cid)
    if creator_id and creator_id > 0 and creator_id != owner_id:
        chat_row.owner_user_id = int(creator_id)
        logger.info(
            "guard owner transfer on demotion chat=%s from=%s to creator=%s",
            cid,
            owner_id,
            creator_id,
        )


async def sync_accessible_chat_ownership(
    session: AsyncSession,
    viewer_user_id: int,
    chats: list[Chat],
) -> None:
    """
    При загрузке списка чатов:
    - owner в БД ≠ creator в TG → creator;
    - owner/delegat без TG-админки → отзыв доступа.
    """
    vid = int(viewer_user_id)
    dirty = False
    for chat_row in chats:
        cid = int(getattr(chat_row, "id", 0) or 0)
        if cid == 0:
            continue
        _, changed = await transfer_chat_owner_to_creator_if_needed(None, chat_row)
        dirty = dirty or changed
        owner_id = int(getattr(chat_row, "owner_user_id", 0) or 0)
        if owner_id == vid:
            if not await user_is_group_admin(None, cid, vid):
                dirty = True
        elif vid != owner_id:
            if not await user_is_group_admin(None, cid, vid):
                res = await session.execute(
                    delete(ChatManager).where(ChatManager.chat_id == cid, ChatManager.user_id == vid),
                )
                if res.rowcount:
                    dirty = True
    if dirty:
        await session.commit()
