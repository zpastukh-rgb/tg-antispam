"""Авто-подтверждение заявок на вступление в канал/группу."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatJoinRequest

from app.db.models import Chat, Rule
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = Router(name="join_requests")


@router.chat_join_request()
async def on_chat_join_request(event: ChatJoinRequest, bot: Bot) -> None:
    chat_id = int(event.chat.id)
    user_id = int(event.from_user.id) if event.from_user else 0
    if user_id <= 0:
        return

    async with await get_session() as session:
        chat = await session.get(Chat, chat_id)
        if not chat or chat.is_log_chat or not bool(getattr(chat, "is_active", True)):
            return
        rule = await session.get(Rule, chat_id)
        if not rule or not bool(getattr(rule, "auto_approve_join_requests", False)):
            return

    try:
        await bot.approve_chat_join_request(chat_id, user_id)
    except TelegramForbiddenError:
        logger.warning(
            "auto_approve join forbidden chat=%s user=%s (bot needs invite/admin rights?)",
            chat_id,
            user_id,
        )
    except TelegramBadRequest as e:
        logger.warning("auto_approve join bad request chat=%s user=%s: %s", chat_id, user_id, e)
