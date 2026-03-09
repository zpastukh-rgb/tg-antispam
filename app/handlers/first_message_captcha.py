# app/handlers/first_message_captcha.py
"""Капча на первое сообщение: отправляется только в личку пользователю, не в общий чат."""

from __future__ import annotations

import logging
from typing import Set, Tuple

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.db.session import get_session
from app.db.models import Chat, Rule

router = Router()
logger = logging.getLogger(__name__)

# Пользователи, прошедшие капчу в чате (chat_id, user_id). In-memory, сбрасывается при рестарте.
_CAPTCHA_PASSED: Set[Tuple[int, int]] = set()

CB_CAPTCHA_FIRST_OK = "captcha:first_ok:"


def _captcha_passed(chat_id: int, user_id: int) -> bool:
    return (chat_id, user_id) in _CAPTCHA_PASSED


def _set_captcha_passed(chat_id: int, user_id: int) -> None:
    _CAPTCHA_PASSED.add((chat_id, user_id))


async def check_first_message_captcha(message: Message) -> bool:
    """
    Если включена капча на первое сообщение и пользователь не проходил:
    удаляем сообщение в чате и шлём капчу только в личку (видна только ему).
    Returns True если сообщение обработано капчей (в модерацию не передавать), False иначе.
    """
    if not message.from_user:
        return False
    chat_id = message.chat.id
    user_id = message.from_user.id

    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
        if not chat_row or not getattr(chat_row, "is_active", True):
            return False
        rule = await session.get(Rule, chat_id)
        if not rule or not getattr(rule, "first_message_captcha_enabled", False):
            return False

    if _captcha_passed(chat_id, user_id):
        return False

    # Удаляем сообщение из группы (чтобы не было видно всем)
    try:
        await message.delete()
    except Exception:
        pass

    # Капча только в личку — видна только текущему пользователю
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я не бот", callback_data=f"{CB_CAPTCHA_FIRST_OK}{chat_id}")],
        ])
        await message.bot.send_message(
            user_id,
            "😈 Подтверди, что ты не бот: нажми кнопку ниже. После этого сможешь писать в чат.",
            reply_markup=kb,
        )
    except Exception as e:
        logger.warning("first_message_captcha send_dm user_id=%s chat_id=%s: %s", user_id, chat_id, e)
    return True  # Обработано капчей, в модерацию не передавать


@router.callback_query(F.data.startswith(CB_CAPTCHA_FIRST_OK))
async def on_captcha_passed(cb: CallbackQuery):
    """Пользователь нажал «Я не бот» — помечаем прохождение, капча была только ему в личку."""
    await cb.answer()
    try:
        chat_id = int(cb.data[len(CB_CAPTCHA_FIRST_OK):])
    except (ValueError, TypeError):
        return
    user_id = cb.from_user.id if cb.from_user else 0
    if not user_id:
        return
    _set_captcha_passed(chat_id, user_id)
    try:
        await cb.message.edit_text("✅ Готово. Можешь писать в чат.")
    except Exception:
        pass
