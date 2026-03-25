# app/handlers/first_message_captcha.py
"""Капча на первое сообщение: отправляется только в личку пользователю, не в общий чат.
КАПЧА НА ПАУЗЕ — весь код закомментирован, оставлены заглушки для импортов."""

from __future__ import annotations

# import logging
# from typing import Set, Tuple

from aiogram import Router

# from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
# from app.db.session import get_session
# from app.db.models import Chat, Rule

router = Router()
# logger = logging.getLogger(__name__)

# # Пользователи, прошедшие капчу в чате (chat_id, user_id). In-memory, сбрасывается при рестарте.
# _CAPTCHA_PASSED: Set[Tuple[int, int]] = set()

# CB_CAPTCHA_FIRST_OK = "captcha:first_ok:"


def _captcha_passed(chat_id: int, user_id: int) -> bool:
    """Заглушка: капча на паузе — считаем что не проходил."""
    return False
    # return (chat_id, user_id) in _CAPTCHA_PASSED


# def _set_captcha_passed(chat_id: int, user_id: int) -> None:
#     _CAPTCHA_PASSED.add((chat_id, user_id))


# def _captcha_keyboard(chat_id: int) -> InlineKeyboardMarkup:
#     return InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(text="✅ Я не бот", callback_data=f"{CB_CAPTCHA_FIRST_OK}{chat_id}")],
#     ])


async def send_captcha_dm(bot, user_id: int, chat_id: int) -> bool:
    """Заглушка: капча на паузе — не отправляем."""
    return False
    # try:
    #     await bot.send_message(
    #         user_id,
    #         "😈 Подтверди, что ты не бот: нажми кнопку ниже. После этого сможешь писать в чат.",
    #         reply_markup=_captcha_keyboard(chat_id),
    #     )
    #     return True
    # except Exception as e:
    #     logger.warning("send_captcha_dm user_id=%s chat_id=%s: %s", user_id, chat_id, e)
    #     return False


async def send_captcha_fallback_instruction(bot, chat_id: int, user_id: int, user_mention: str) -> bool:
    """Заглушка: капча на паузе — не отправляем."""
    return False
    # try:
    #     me = await bot.get_me()
    #     username = getattr(me, "username", None) or "bot"
    #     await bot.send_message(
    #         chat_id,
    #         f"😈 {user_mention}, откройте бота в личку (@{username}) и нажмите Start — там подтверждение.",
    #         parse_mode="HTML",
    #     )
    #     return True
    # except Exception as e:
    #     logger.warning("send_captcha_fallback_instruction chat_id=%s user_id=%s: %s", chat_id, user_id, e)
    #     return False


async def check_first_message_captcha(message) -> bool:
    """Заглушка: капча на паузе — не проверяем, всегда False (в модерацию передаём)."""
    return False
    # if not message.from_user:
    #     return False
    # chat_id = message.chat.id
    # user_id = message.from_user.id
    #
    # async with await get_session() as session:
    #     chat_row = await session.get(Chat, chat_id)
    #     if not chat_row or not getattr(chat_row, "is_active", True):
    #         return False
    #     rule = await session.get(Rule, chat_id)
    #     if not rule or not getattr(rule, "first_message_captcha_enabled", False):
    #         return False
    #
    # if _captcha_passed(chat_id, user_id):
    #     return False
    #
    # try:
    #     await message.delete()
    # except Exception:
    #     pass
    #
    # try:
    #     kb = InlineKeyboardMarkup(inline_keyboard=[
    #         [InlineKeyboardButton(text="✅ Я не бот", callback_data=f"{CB_CAPTCHA_FIRST_OK}{chat_id}")],
    #     ])
    #     await message.bot.send_message(
    #         user_id,
    #         "😈 Подтверди, что ты не бот: нажми кнопку ниже. После этого сможешь писать в чат.",
    #         reply_markup=kb,
    #     )
    # except Exception as e:
    #     logger.warning("first_message_captcha send_dm user_id=%s chat_id=%s: %s", user_id, chat_id, e)
    # return True


# @router.callback_query(F.data.startswith(CB_CAPTCHA_FIRST_OK))
# async def on_captcha_passed(cb: CallbackQuery):
#     await cb.answer()
#     try:
#         chat_id = int(cb.data[len(CB_CAPTCHA_FIRST_OK):])
#     except (ValueError, TypeError):
#         return
#     user_id = cb.from_user.id if cb.from_user else 0
#     if not user_id:
#         return
#     _set_captcha_passed(chat_id, user_id)
#     try:
#         await cb.message.edit_text("✅ Готово. Можешь писать в чат.")
#     except Exception:
#         pass
