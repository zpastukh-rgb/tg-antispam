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


async def _skip_protection_prompt(chat_id: int, user_id: int) -> bool:
    """
    Чат журнала отчётов или куда уже ведутся отчёты — не показываем «назначьте админа» / «подключить защиту».
    Пока пользователь выбирает чат отчётов в панели — тоже не мешаем.
    """
    try:
        async with await get_session() as session:
            row = await session.get(Chat, chat_id)
            if row and row.is_log_chat:
                return True
            res = await session.execute(select(Chat.id).where(Chat.log_chat_id == chat_id).limit(1))
            if res.scalar_one_or_none():
                return True
        from app.handlers import panel_dm as _panel_dm

        if user_id in _panel_dm._pending_reports_for:
            return True
    except Exception:
        pass
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

    # ТЗ ЧЕККК + ТЗ Отчёты: бота удалили из группы — is_active = False; если это был чат отчётов — уведомить владельцев
    if old_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR) and new_status in (
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    ):
        try:
            async with await get_session() as session:
                chat_row = await session.get(Chat, chat.id)
                if chat_row:
                    chat_row.is_active = False
                    chat_row.is_log_chat = False
                # Найти защищаемые чаты, у которых log_chat_id == этот чат — уведомить владельцев
                res = await session.execute(
                    select(Chat).where(Chat.log_chat_id == chat.id)
                )
                affected = list(res.scalars().all())
                for row in affected:
                    row.log_chat_id = None
                    try:
                        await update.bot.send_message(
                            row.owner_user_id,
                            "⚠ Чат отчётов больше недоступен. Похоже, бот был удалён или потерял права.\n"
                            "Подключите новый чат отчётов в панели: *Отчёты* → *➕ Подключить чат отчётов*.",
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass
                await session.commit()
        except Exception:
            pass
        return

    # Бот добавлен в группу или повышен до админа
    added = old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED) and new_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    )
    bot_is_admin = new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)

    if not update.from_user:
        return

    title = (chat.title or "эта группа").replace("*", "\\*")

    # ТЗ: при добавлении бота в группу — сохраняем чат в список «ожидающих», чтобы он появился в «Подключить чат»
    if added:
        try:
            async with await get_session() as session:
                chat_row = await session.get(Chat, chat.id)
                if not chat_row:
                    chat_row = Chat(
                        id=chat.id,
                        title=chat.title or "",
                        owner_user_id=update.from_user.id,
                        is_active=False,
                        is_log_chat=False,
                    )
                    session.add(chat_row)
                else:
                    chat_row.title = chat.title or chat_row.title or ""
                    chat_row.owner_user_id = update.from_user.id
                    # не трогаем is_active — подключит пользователь из панели
                await session.commit()
        except Exception:
            pass

    # ТЗ ЧЕККК: когда бот назначен админом — удаляем сообщение «назначьте админом», если было
    _promote_msg_ids = getattr(on_my_chat_member, "_promote_msg_ids", {})
    if bot_is_admin and chat.id in _promote_msg_ids:
        try:
            await update.bot.delete_message(chat.id, _promote_msg_ids[chat.id])
        except Exception:
            pass
        del _promote_msg_ids[chat.id]

    # ТЗ ЧЕККК: когда бот назначен админом — сразу подключаем (приветствие в группу + сообщение в личку)
    if bot_is_admin:
        from app.handlers.panel_dm import connect_chat_after_bot_added
        connected = await connect_chat_after_bot_added(
            update.bot,
            chat.id,
            chat.title or "",
            update.from_user.id,
            getattr(update.from_user, "username", None),
            getattr(update.from_user, "first_name", None),
        )
        if connected:
            return
        if await _skip_protection_prompt(chat.id, update.from_user.id):
            return
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        try:
            await update.bot.send_message(
                update.from_user.id,
                f"😈 *Бот в группе «{title}»*\n\nПодключить эту группу к защите?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Подключить", callback_data=f"p:connect_confirm:{chat.id}")],
                ]),
            )
        except Exception:
            pass
        return

    if not added:
        return

    # ТЗ ЧЕККК: бот в группе, но не админ — просим назначить (но не в чате отчётов)
    if not await _is_admin(update.bot, chat.id, update.from_user.id):
        return
    if await _skip_protection_prompt(chat.id, update.from_user.id):
        return
    try:
        msg = await update.bot.send_message(
            chat.id,
            "Чтобы включить защиту, назначьте меня администратором.",
        )
        if not hasattr(on_my_chat_member, "_promote_msg_ids"):
            on_my_chat_member._promote_msg_ids = {}
        on_my_chat_member._promote_msg_ids[chat.id] = msg.message_id
    except Exception:
        pass


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
            .where(
                Chat.is_active == True,  # noqa: E712
                Chat.is_log_chat == False,  # noqa: E712 — только защищаемые
            )
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

        # зарегистрировать группу L как лог-чат пользователя (чтобы она была в «Куда слать»)
        log_chat_row = await session.get(Chat, log_chat_id)
        if not log_chat_row:
            log_chat_row = Chat(
                id=log_chat_id,
                owner_user_id=cb.from_user.id,
                is_log_chat=True,
                is_active=False,
                title=cb.message.chat.title,
            )
            session.add(log_chat_row)
        else:
            log_chat_row.is_log_chat = True
            log_chat_row.owner_user_id = cb.from_user.id
            log_chat_row.title = cb.message.chat.title

        await session.commit()

        protected_title = chat_row.title or str(protected_chat_id)

    log_title = cb.message.chat.title or str(log_chat_id)

    await cb.message.edit_text(
        "✅ *Готово.*\n\n"
        f"Теперь отчёты для\n"
        f"*{protected_title}*\n"
        f"будут приходить сюда:\n"
        f"*{log_title}*\n\n"
        "Я фиксирую всё. 😈",
        parse_mode="Markdown",
    )
