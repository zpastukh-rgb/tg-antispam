from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from collections import OrderedDict

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ChatType, ChatMemberStatus

from app.db.session import get_session
from app.db.models import Chat, Rule
from app.services.user_service import get_or_create_user, can_add_chat

router = Router()
logger = logging.getLogger(__name__)

# =========================================================
# CALLBACK KEYS
# =========================================================

CB_START = "ob:start"
CB_ADD_CHAT = "ob:add_chat"
CB_LOGS = "ob:logs"
CB_TEST = "ob:test"
CB_PANEL = "ob:open_panel"

# =========================================================
# CACHE
# =========================================================

ONBOARD_MSG_CACHE: "OrderedDict[int, Tuple[int, datetime]]" = OrderedDict()

CACHE_MAX = 2000
CACHE_TTL = timedelta(days=3)


def _cache_set(user_id: int, msg_id: int):

    now = datetime.now(timezone.utc)

    ONBOARD_MSG_CACHE[user_id] = (msg_id, now)
    ONBOARD_MSG_CACHE.move_to_end(user_id)

    for uid in list(ONBOARD_MSG_CACHE.keys()):

        _, ts = ONBOARD_MSG_CACHE[uid]

        if now - ts > CACHE_TTL:
            ONBOARD_MSG_CACHE.pop(uid, None)

    while len(ONBOARD_MSG_CACHE) > CACHE_MAX:
        ONBOARD_MSG_CACHE.popitem(last=False)


def _cache_get(user_id: int) -> Optional[int]:

    item = ONBOARD_MSG_CACHE.get(user_id)

    if not item:
        return None

    msg_id, ts = item
    now = datetime.now(timezone.utc)

    if now - ts > CACHE_TTL:
        ONBOARD_MSG_CACHE.pop(user_id, None)
        return None

    ONBOARD_MSG_CACHE.move_to_end(user_id)

    return msg_id


async def _edit_or_send(message: Message, text: str, kb):

    msg_id = _cache_get(message.from_user.id)

    if msg_id:

        try:

            await message.bot.edit_message_text(
                text=text,
                chat_id=message.from_user.id,
                message_id=msg_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return

        except Exception:
            pass

    m = await message.answer(text, parse_mode="Markdown", reply_markup=kb)

    _cache_set(message.from_user.id, m.message_id)


# =========================================================
# KEYBOARDS
# =========================================================

def kb_start():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Подключить защиту",
                    callback_data=CB_ADD_CHAT,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧨 Панель управления",
                    callback_data=CB_PANEL,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧾 Как включить отчёты",
                    callback_data=CB_LOGS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧪 Проверить работу",
                    callback_data=CB_TEST,
                )
            ],
        ]
    )


def kb_back():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=CB_START,
                )
            ]
        ]
    )


# =========================================================
# START SCREEN
# =========================================================

async def render_start(message: Message):

    text = (
        "😈 *AntiSpam Guardian*\n\n"
        "Я защищаю Telegram-чаты от:\n\n"
        "• спама\n"
        "• ссылок\n"
        "• рейдов\n"
        "• ботов\n\n"
        "Выбери действие:"
    )

    await _edit_or_send(message, text, kb_start())


@router.callback_query(F.data == CB_START)
async def cb_start(cb: CallbackQuery):

    await cb.answer()

    await render_start(cb.message)


# =========================================================
# ADD CHAT
# =========================================================

@router.callback_query(F.data == CB_ADD_CHAT)
async def cb_add_chat(cb: CallbackQuery):

    await cb.answer()

    text = (
        "➕ *Подключение защиты*\n\n"
        "1️⃣ Добавь бота в группу\n\n"
        "2️⃣ Дай права администратора:\n"
        "✅ Удалять сообщения\n"
        "➕ желательно банить участников\n\n"
        "3️⃣ В группе напиши:\n"
        "`/check`\n\n"
        "После этого чат появится в панели."
    )

    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


# =========================================================
# LOGS
# =========================================================

@router.callback_query(F.data == CB_LOGS)
async def cb_logs(cb: CallbackQuery):

    await cb.answer()

    text = (
        "🧾 *Отчёты модерации*\n\n"
        "Лучше использовать отдельную группу.\n\n"
        "1️⃣ Создай группу (например AntiSpam Logs)\n"
        "2️⃣ Добавь туда бота\n"
        "3️⃣ Дай админ-права\n\n"
        "После этого выбери эту группу\n"
        "в панели управления."
    )

    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


# =========================================================
# TEST
# =========================================================

@router.callback_query(F.data == CB_TEST)
async def cb_test(cb: CallbackQuery):

    await cb.answer()

    text = (
        "🧪 *Проверка бота*\n\n"
        "В защищаемом чате отправь:\n\n"
        "🔗 ссылку\n"
        "`https://t.me/test`\n\n"
        "🏷 упоминание\n"
        "`@username`\n\n"
        "Если включён Anti-edit:\n"
        "1️⃣ отправь текст\n"
        "2️⃣ отредактируй\n"
        "3️⃣ добавь ссылку"
    )

    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


# =========================================================
# PANEL
# =========================================================

@router.callback_query(F.data == CB_PANEL)
async def cb_panel(cb: CallbackQuery):

    await cb.answer()

    from app.handlers.panel_dm import show_panel

    await show_panel(cb.bot, cb.from_user.id)


# =========================================================
# /SETLOG
# =========================================================

@router.message(Command(commands=["setlog"], ignore_mention=True))
async def setlog_command(message: Message):
    """ТЗ Отчёты: /setlog убран — подсказка про панель."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not message.from_user:
        return
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(
        "Подключение чата отчётов теперь делается через панель.\n"
        "Откройте настройки группы и нажмите: *Подключить чат отчётов*.",
        parse_mode="Markdown",
    )


# =========================================================
# /CHECK
# =========================================================

@router.message(Command(commands=["check"], ignore_mention=True))
async def check_command(message: Message):
    """ТЗ ЧЕККК: /check только как fallback — подсказка про панель."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not message.from_user:
        return

    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        "Подключение групп теперь делается через панель.\n"
        "Открой личный чат с ботом и нажми: *➕ Добавить группу* (или *➕ Подключить чат*).",
        parse_mode="Markdown",
    )
