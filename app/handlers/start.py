from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from collections import OrderedDict

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

# =========================================================
# CALLBACK KEYS
# =========================================================

CB_CONNECT = "st:connect"
CB_PANEL = "st:panel"
CB_RULES = "st:rules"
CB_BACK = "st:back"

# =========================================================
# LRU + TTL CACHE
# ---------------------------------------------------------
# Не создаём новые сообщения при каждом /start
# Редактируем одно и то же.
# Это снижает нагрузку Telegram API и память.
# =========================================================

START_MSG_CACHE: "OrderedDict[int, Tuple[int, datetime]]" = OrderedDict()

CACHE_MAX = 2000
CACHE_TTL = timedelta(days=3)


def _cache_set(user_id: int, msg_id: int):

    now = datetime.now(timezone.utc)

    START_MSG_CACHE[user_id] = (msg_id, now)
    START_MSG_CACHE.move_to_end(user_id)

    # очистка старых
    for uid in list(START_MSG_CACHE.keys()):

        _, ts = START_MSG_CACHE[uid]

        if now - ts > CACHE_TTL:
            START_MSG_CACHE.pop(uid, None)

    # ограничение размера
    while len(START_MSG_CACHE) > CACHE_MAX:
        START_MSG_CACHE.popitem(last=False)


def _cache_get(user_id: int) -> Optional[int]:

    item = START_MSG_CACHE.get(user_id)

    if not item:
        return None

    msg_id, ts = item
    now = datetime.now(timezone.utc)

    if now - ts > CACHE_TTL:
        START_MSG_CACHE.pop(user_id, None)
        return None

    START_MSG_CACHE.move_to_end(user_id)

    return msg_id


# =========================================================
# TEXTS
# =========================================================

START_TEXT = (
    "😈 *AntiSpam Guardian*\n\n"
    "Я не разговариваю.\n"
    "Я *удаляю спам.*\n\n"
    "⚡ *Подключение занимает 30 секунд:*\n\n"
    "1️⃣ Добавь меня в группу\n"
    "2️⃣ Дай админку: ✅ *Удалять сообщения*\n"
    "3️⃣ Напиши в группе:\n"
    "`/check`\n\n"
    "🧨 После этого чат появится в панели."
)

CONNECT_TEXT = (
    "➕ *Подключение защиты*\n\n"
    "Сделай 3 шага:\n\n"
    "1️⃣ Добавь бота в группу\n\n"
    "2️⃣ Дай права администратора:\n"
    "✅ удалять сообщения\n"
    "➕ желательно банить участников\n\n"
    "3️⃣ В группе напиши:\n"
    "`/check`\n\n"
    "После этого чат появится в панели управления."
)

RULES_TEXT = (
    "📜 *Что умеет AntiSpam Guardian*\n\n"
    "🔗 удаляет ссылки\n"
    "🏷 режет массовые @упоминания\n"
    "🧨 блокирует стоп-слова\n"
    "✏️ ловит редактирование сообщений\n"
    "👶 защищает от новых аккаунтов\n"
    "🤖 удаляет спам-ботов\n"
    "🧾 ведёт журнал действий\n\n"
    "⚙️ Всё настраивается в панели."
)

# =========================================================
# KEYBOARDS
# =========================================================


def start_kb():

    kb = InlineKeyboardBuilder()

    kb.button(
        text="➕ Подключить защиту",
        callback_data=CB_CONNECT,
    )

    kb.button(
        text="🧨 Панель управления",
        callback_data=CB_PANEL,
    )

    kb.button(
        text="📜 Что я умею",
        callback_data=CB_RULES,
    )

    kb.adjust(1)

    return kb.as_markup()


def back_kb():

    kb = InlineKeyboardBuilder()

    kb.button(
        text="⬅️ Назад",
        callback_data=CB_BACK,
    )

    return kb.as_markup()


# =========================================================
# SAFE SEND / EDIT
# =========================================================

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

    m = await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=kb,
    )

    _cache_set(message.from_user.id, m.message_id)


# =========================================================
# START
# =========================================================

@router.message(CommandStart())
async def cmd_start(message: Message):

    if message.chat.type != "private":
        return

    await _edit_or_send(message, START_TEXT, start_kb())


# =========================================================
# CALLBACKS
# =========================================================


@router.callback_query(F.data == CB_BACK)
async def cb_back(cb: CallbackQuery):

    await cb.answer()

    await cb.message.edit_text(
        START_TEXT,
        parse_mode="Markdown",
        reply_markup=start_kb(),
    )


@router.callback_query(F.data == CB_CONNECT)
async def cb_connect(cb: CallbackQuery):

    await cb.answer()

    await cb.message.edit_text(
        CONNECT_TEXT,
        parse_mode="Markdown",
        reply_markup=back_kb(),
    )


@router.callback_query(F.data == CB_RULES)
async def cb_rules(cb: CallbackQuery):

    await cb.answer()

    await cb.message.edit_text(
        RULES_TEXT,
        parse_mode="Markdown",
        reply_markup=back_kb(),
    )


@router.callback_query(F.data == CB_PANEL)
async def cb_panel(cb: CallbackQuery):

    await cb.answer()

    # импорт внутри чтобы не было circular import
    from app.handlers.panel_dm import show_panel

    await show_panel(cb.bot, cb.from_user.id)
