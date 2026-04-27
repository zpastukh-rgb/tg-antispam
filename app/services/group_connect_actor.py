# app/services/group_connect_actor.py
"""Кто считается владельцем кабинета Guard при подключении группы из чата (не путать с отправителем /start)."""

from __future__ import annotations

import logging
from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import Message, User as TgUser

logger = logging.getLogger(__name__)


async def telegram_user_is_chat_creator(bot: Bot, chat_id: int, telegram_user_id: int) -> bool:
    """True, если telegram_user_id — создатель этой группы/супергруппы (по списку админов)."""
    try:
        members = await bot.get_chat_administrators(chat_id)
        for member in members:
            if member.status == ChatMemberStatus.CREATOR and int(member.user.id) == int(telegram_user_id):
                return True
    except Exception as e:
        logger.debug("telegram_user_is_chat_creator failed chat=%s: %s", chat_id, e)
    return False


async def is_post_as_linked_channel_in_discussion(bot: Bot, chat_id: int, message: Message) -> bool:
    """
    Сообщение в группе-обсуждении отправлено от имени привязанного канала (не личный профиль).
    У таких сообщений from_user часто не считается «админом» группы — отдельная проверка.
    """
    sc = getattr(message, "sender_chat", None)
    if not sc:
        return False
    # aiogram: type — ChatType или строка
    st = getattr(sc, "type", None)
    st_s = str(st or "").lower()
    if "channel" not in st_s and st not in (ChatType.CHANNEL, "channel"):
        return False
    scid = int(getattr(sc, "id", 0) or 0)
    if scid <= 0:
        return False
    try:
        discussion = await bot.get_chat(chat_id)
        linked_channel_id = int(getattr(discussion, "linked_chat_id", 0) or 0)
        if linked_channel_id and scid == linked_channel_id:
            return True
    except Exception as e:
        logger.debug("is_post_as_linked_channel_in_discussion (discussion) chat=%s: %s", chat_id, e)
    # Запасной путь: у канала linked_chat_id = id группы-обсуждения (если у супергруппы linked_chat_id не пришёл).
    try:
        chan = await bot.get_chat(scid)
        linked_group_id = int(getattr(chan, "linked_chat_id", 0) or 0)
        return linked_group_id != 0 and linked_group_id == int(chat_id)
    except Exception as e:
        logger.debug("is_post_as_linked_channel_in_discussion (channel) chat=%s: %s", chat_id, e)
    return False


async def actor_may_init_group_connect_from_group(bot: Bot, chat_id: int, message: Message) -> bool:
    """
    Кто может запустить connect из группы:
    - личный Telegram (не бот) в статусе администратор/создатель, или
    - пост от привязанного к этому чату канала (владелец пишет «от канала» в обсуждении).
    """
    fu = message.from_user
    if fu is not None and not bool(getattr(fu, "is_bot", False)):
        try:
            m = await bot.get_chat_member(chat_id, fu.id)
            if m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                return True
        except Exception as e:
            logger.debug("actor_may_init_group_connect member check failed chat=%s: %s", chat_id, e)
    return await is_post_as_linked_channel_in_discussion(bot, chat_id, message)


async def resolve_guard_connect_actor_for_group(
    bot: Bot,
    chat_id: int,
    actor: TgUser | None,
) -> tuple[int, str | None, str | None]:
    """
    Для подключения защищаемой группы из самой группы:
    владелец кабинета = создатель чата (если бот видит админов), иначе — кто нажал (actor).

    Так менеджер может нажать /start, а в Guard привяжется кабинет создателя группы.
    """
    try:
        members = await bot.get_chat_administrators(chat_id)
        for member in members:
            if member.status == ChatMemberStatus.CREATOR:
                u = member.user
                return (
                    int(u.id),
                    getattr(u, "username", None),
                    getattr(u, "first_name", None),
                )
    except Exception as e:
        logger.debug("resolve_guard_connect_actor_for_group failed chat=%s: %s", chat_id, e)
    if actor is None:
        return (0, None, None)
    return (
        int(actor.id),
        getattr(actor, "username", None),
        getattr(actor, "first_name", None),
    )
