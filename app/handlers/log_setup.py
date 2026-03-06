from __future__ import annotations

from aiogram import Router, F
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.types import ChatMemberUpdated, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select

from app.db.session import get_session
from app.db.models import Chat

router = Router()

# =========================================================
# CALLBACK KEYS
# =========================================================

CB_LOG_MAKE = "log:make"
CB_LOG_BIND = "log:bind:"
CB_LOG_CANCEL = "log:cancel"

# =========================================================
# HELPERS
# =========================================================


async def _is_admin(bot, chat_id: int, user_id: int) -> bool:

    try:
        m = await bot.get_chat_member(chat_id, user_id)

        return m.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )

    except Exception:

        return False


def _kb_make_logs():

    b = InlineKeyboardBuilder()

    b.button(
        text="🧾 Сделать эту группу отчётами",
        callback_data=CB_LOG_MAKE,
    )

    b.button(
        text="😴 Не нужно",
        callback_data=CB_LOG_CANCEL,
    )

    b.adjust(1)

    return b.as_markup()


# =========================================================
# BOT ADDED TO GROUP
# =========================================================

@router.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated):

    chat = update.chat

    if chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    ):
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    added = (
        old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
        and new_status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
        )
    )

    if not added:
        return

    if not update.from_user:
        return

    # сообщение показываем только если добавил админ

    if not await _is_admin(update.bot, chat.id, update.from_user.id):
        return

    title = chat.title or "эта группа"

    text = (
        "😈 *AntiSpam Guardian на месте.*\n\n"
        f"Вижу новую берлогу: *{title}*\n\n"
        "Сделать эту группу *журналом отчётов*?"
    )

    await update.bot.send_message(
        chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=_kb_make_logs(),
    )


# =========================================================
# CANCEL
# =========================================================

@router.callback_query(F.data == CB_LOG_CANCEL)
async def cb_log_cancel(cb: CallbackQuery):

    await cb.answer("Ок 😴")

    try:

        await cb.message.edit_text(
            "😴 Ладно. Не трогаю.",
            reply_markup=None,
        )

    except Exception:
        pass


# =========================================================
# MAKE LOG GROUP
# =========================================================

@router.callback_query(F.data == CB_LOG_MAKE)
async def cb_log_make(cb: CallbackQuery):

    await cb.answer()

    if not cb.from_user:
        return

    log_chat_id = cb.message.chat.id

    # проверяем админа

    if not await _is_admin(cb.bot, log_chat_id, cb.from_user.id):

        await cb.answer(
            "Только админ может это сделать 😈",
            show_alert=True,
        )

        return

    async with await get_session() as session:

        res = await session.execute(
            select(Chat)
            .where(Chat.is_active == True)  # noqa
            .order_by(Chat.id.asc())
        )

        chats = list(res.scalars().all())

    if not chats:

        await cb.message.edit_text(
            "❌ Нет защищаемых чатов.\n\n"
            "Сначала подключи чат через `/check`.",
            parse_mode="Markdown",
        )

        return

    b = InlineKeyboardBuilder()

    for ch in chats:

        title = ch.title or str(ch.id)

        b.button(
            text=f"🛡 {title}",
            callback_data=f"{CB_LOG_BIND}{ch.id}",
        )

    b.button(
        text="⬅️ Назад",
        callback_data=CB_LOG_CANCEL,
    )

    b.adjust(1)

    await cb.message.edit_text(
        "🧾 *Назначение отчётов*\n\n"
        "Выбери чат, для которого\n"
        "сюда будут приходить отчёты:",
        parse_mode="Markdown",
        reply_markup=b.as_markup(),
    )


# =========================================================
# BIND LOG CHAT
# =========================================================

@router.callback_query(F.data.startswith(CB_LOG_BIND))
async def cb_log_bind(cb: CallbackQuery):

    await cb.answer()

    if not cb.from_user:
        return

    log_chat_id = cb.message.chat.id

    if not await _is_admin(cb.bot, log_chat_id, cb.from_user.id):

        await cb.answer(
            "Только админы 😈",
            show_alert=True,
        )

        return

    try:

        protected_chat_id = int(cb.data.split(":")[-1])

    except Exception:

        await cb.answer("Ошибка данных", show_alert=True)

        return

    async with await get_session() as session:

        chat_row = await session.get(Chat, protected_chat_id)

        if not chat_row:

            await cb.answer("Чат не найден", show_alert=True)

            return

        chat_row.log_chat_id = log_chat_id

        await session.commit()

    log_title = cb.message.chat.title or str(log_chat_id)
    protected_title = chat_row.title or str(protected_chat_id)

    await cb.message.edit_text(
        "✅ *Готово.*\n\n"
        f"Теперь отчёты для\n"
        f"*{protected_title}*\n"
        f"будут приходить сюда:\n"
        f"*{log_title}*\n\n"
        "Я фиксирую всё. 😈",
        parse_mode="Markdown",
    )
