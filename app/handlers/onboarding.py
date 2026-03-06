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
# /CHECK
# =========================================================

@router.message(Command(commands=["check"], ignore_mention=True))
async def check_command(message: Message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        print("### CHECK STOP: not_group", getattr(message.chat, "id", None), flush=True)
        return

    if not message.from_user:
        print("### CHECK STOP: no_from_user", getattr(message.chat, "id", None), flush=True)
        await message.answer("❌ Не вижу пользователя, который вызвал /check")
        return

    bot = message.bot

    print(
        "### CHECK HIT ###",
        "chat=", message.chat.id,
        "user=", message.from_user.id,
        "text=", message.text,
        flush=True,
    )

    try:
        await message.delete()
    except Exception as e:
        print("### CHECK WARN: delete_failed", repr(e), flush=True)

    # проверка админа, который вызвал /check
    try:
        member = await bot.get_chat_member(
            message.chat.id,
            message.from_user.id,
        )
    except Exception as e:
        print("### CHECK STOP: cannot_get_member", repr(e), flush=True)
        await message.answer("❌ Не смог проверить твои права в чате")
        return

    print("### CHECK member.status =", member.status, flush=True)

    if member.status not in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    ):
        print("### CHECK STOP: caller_not_admin", flush=True)
        await message.answer("❌ Команду /check может вызывать только админ группы")
        return

    # проверка прав бота
    try:
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(
            message.chat.id,
            me.id,
        )
    except Exception as e:
        print("### CHECK STOP: cannot_get_bot_member", repr(e), flush=True)
        await message.answer("❌ Не смог проверить права бота в чате")
        return

    print(
        "### CHECK bot_member.status =",
        bot_member.status,
        "can_delete_messages =",
        getattr(bot_member, "can_delete_messages", None),
        flush=True,
    )

    if bot_member.status not in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    ):
        print("### CHECK STOP: bot_not_admin", flush=True)
        await message.answer(
            "❌ Бот не админ в этой группе\n\n"
            "Выдай ему админку и право:\n"
            "✅ Удалять сообщения"
        )
        return

    if not getattr(bot_member, "can_delete_messages", False):
        print("### CHECK STOP: bot_no_delete_rights", flush=True)
        await message.answer(
            "❌ Дай боту права:\n\n"
            "✅ Удалять сообщения"
        )
        return

    # сохранение чата
    try:
        async with await get_session() as session:
            chat = await session.get(Chat, message.chat.id)

            if not chat:
                chat = Chat(
                    id=message.chat.id,
                    title=message.chat.title,
                    owner_user_id=message.from_user.id,
                    is_active=True,
                )
                session.add(chat)
                print("### CHECK DB: new_chat_added", message.chat.id, flush=True)
            else:
                chat.title = message.chat.title
                chat.owner_user_id = message.from_user.id
                chat.is_active = True
                print("### CHECK DB: chat_exists_updated", message.chat.id, flush=True)

            rule = await session.get(Rule, message.chat.id)

            if not rule:
                rule = Rule(
                    chat_id=message.chat.id,
                    filter_links=True,
                    filter_mentions=True,
                    action_mode="delete",
                    mute_minutes=30,
                    anti_edit=True,
                    newbie_enabled=True,
                    newbie_minutes=10,
                    log_enabled=True,
                )
                session.add(rule)
                print("### CHECK DB: new_rule_added", message.chat.id, flush=True)

            await session.commit()
            print("### CHECK DB: commit_ok", message.chat.id, flush=True)

    except Exception as e:
        print("### CHECK STOP: db_error", repr(e), flush=True)
        await message.answer(f"❌ Ошибка при сохранении чата: {e}")
        return

    # успех
    try:
        bot_username = (await bot.get_me()).username
        panel_url = f"https://t.me/{bot_username}?start=panel"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🧨 Открыть панель",
                        url=panel_url,
                    )
                ]
            ]
        )

        await message.answer(
            "✅ *Чат подключён*\n\n"
            "Теперь я защищаю эту группу.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

        print("### CHECK OK: finished", message.chat.id, flush=True)

    except Exception as e:
        print("### CHECK STOP: success_message_failed", repr(e), flush=True)
        await message.answer("✅ Чат сохранил, но не смог отправить кнопку панели")
