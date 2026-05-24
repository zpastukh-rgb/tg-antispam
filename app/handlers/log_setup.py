from __future__ import annotations

import logging
import os

from aiogram import Router, F
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.types import ChatMemberUpdated, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select

from app.db.session import get_session
from app.db.models import Chat, Rule
from app.services.group_connect_actor import resolve_guard_connect_actor_for_group
from app.services.telegram_notify import send_user_dm, send_disconnect_comeback_dm

router = Router()
logger = logging.getLogger(__name__)

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


async def _try_bind_pending_reports_chat(bot, chat_id: int, chat_title: str, user_id: int) -> bool:
    """
    Фолбэк для сценария, когда пользователь нажал «подключить чат отчётов»,
    но затем добавил бота в группу вручную (без chat_shared).
    """
    try:
        from app.handlers import panel_dm as _panel_dm
        reports_title = (chat_title or "").strip() or str(chat_id)
        async with await get_session() as session:
            # Только явная запись из сценария «подключить чат отчётов» (/start reportschat_…
            # или кнопка в панели). Нельзя подставлять selected_chat_id: это текущий открытый
            # чат в Mini App и при добавлении новой защищаемой группы давало ложную привязку
            # «чат отчётов» к только что добавленной группе.
            protected_chat_id = _panel_dm._pending_reports_for.get(int(user_id))
            if not protected_chat_id:
                return False
            if int(protected_chat_id) == int(chat_id):
                return False
            _panel_dm._mark_reports_chat_guard(int(chat_id))
            chat_row = await session.get(Chat, int(protected_chat_id))
            if chat_row:
                chat_row.log_chat_id = int(chat_id)
            log_chat_row = await session.get(Chat, int(chat_id))
            if not log_chat_row:
                session.add(
                    Chat(
                        id=int(chat_id),
                        title=reports_title,
                        owner_user_id=int(user_id),
                        is_log_chat=True,
                        is_active=False,
                    )
                )
            else:
                log_chat_row.title = reports_title
                log_chat_row.owner_user_id = int(user_id)
                log_chat_row.is_log_chat = True
                log_chat_row.is_active = False
            await session.commit()
        _panel_dm._pending_reports_for.pop(int(user_id), None)
        # Не пишем в сам лог-чат: при ссылке startgroup=reportschat_ туда же уйдёт ответ из start.py — получалось 2 сообщения подряд.
        try:
            await bot.send_message(
                int(user_id),
                "✅ Чат отчётов привязан. Служебные логи модерации будут приходить в выбранную группу.",
            )
        except Exception:
            pass
        return True
    except Exception as e:
        logger.warning("bind pending reports failed chat=%s user=%s: %s", chat_id, user_id, e)
        return False


def _reports_startapp_link(bot_username: str) -> str | None:
    uname = (bot_username or "").strip().lstrip("@")
    if not uname:
        return None
    short_name = (os.getenv("MINI_APP_SHORT_NAME") or os.getenv("WEBAPP_SHORT_NAME") or "").strip().strip("/")
    if short_name:
        return f"https://t.me/{uname}/{short_name}?startapp=reports"
    return f"https://t.me/{uname}?startapp=reports"


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


async def _handle_my_chat_member_channel(update: ChatMemberUpdated) -> None:
    """Канал: регистрируем для рассылки из Mini App (не в лимите защищаемых групп)."""
    chat = update.chat
    if not update.from_user:
        return
    uid = int(update.from_user.id)
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    if old_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR) and new_status in (
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    ):
        try:
            async with await get_session() as session:
                row = await session.get(Chat, chat.id)
                if row and str(getattr(row, "chat_kind", "") or "") == "channel":
                    row.is_active = False
                    await session.commit()
        except Exception:
            pass
        return
    bot_admin = new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    added = old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED) and new_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    )
    if not (bot_admin and added):
        return
    uid = int(update.from_user.id)
    try:
        from app.services.group_connect_actor import actor_may_connect_chat_as_owner

        if not await actor_may_connect_chat_as_owner(update.bot, chat.id, uid):
            try:
                await update.bot.send_message(
                    uid,
                    "ℹ️ Подключить канал в Guard может только владелец (создатель) канала. "
                    "Попросите владельца добавить бота через кабинет или ссылку с правами администратора.",
                )
            except Exception:
                pass
            return
    except Exception:
        return
    try:
        async with await get_session() as session:
            row = await session.get(Chat, chat.id)
            if not row:
                row = Chat(
                    id=chat.id,
                    title=chat.title or "",
                    owner_user_id=uid,
                    is_active=True,
                    is_log_chat=False,
                    chat_kind="channel",
                )
                session.add(row)
            else:
                row.title = chat.title or row.title or ""
                row.owner_user_id = uid
                row.is_active = True
                row.is_log_chat = False
                row.chat_kind = "channel"
            rule = await session.get(Rule, chat.id)
            if not rule:
                session.add(Rule(chat_id=chat.id))
            await session.commit()
        title = (chat.title or "канал").replace("<", "")
        try:
            await update.bot.send_message(
                uid,
                f"📣 Канал «{title}» добавлен для рассылки в Mini App (Рассылка → в каналы), пока бот администратор канала.",
            )
        except Exception:
            pass
    except Exception:
        pass


@router.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated):

    chat = update.chat

    if chat.type == ChatType.CHANNEL:
        await _handle_my_chat_member_channel(update)
        return

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
                owner_uid = None
                protected_title = None
                removed_from_protected = False
                if chat_row:
                    owner_uid = chat_row.owner_user_id
                    protected_title = (chat_row.title or "").strip() or str(chat.id)
                    was_log_chat = bool(chat_row.is_log_chat)
                    chat_row.is_active = False
                    if not was_log_chat:
                        chat_row.is_log_chat = False
                # Найти защищаемые чаты, у которых log_chat_id == этот чат — уведомить владельцев
                res = await session.execute(
                    select(Chat).where(Chat.log_chat_id == chat.id)
                )
                affected = list(res.scalars().all())
                removed_from_protected = bool(chat_row is not None and not bool(getattr(chat_row, "is_log_chat", False)) and len(affected) == 0)
                for row in affected:
                    row.log_chat_id = None
                    try:
                        reports_url = None
                        try:
                            me = await update.bot.get_me()
                            reports_url = _reports_startapp_link(me.username or "")
                        except Exception:
                            reports_url = None
                        await update.bot.send_message(
                            row.owner_user_id,
                            "⚠ Чат отчётов больше недоступен. Похоже, бот был удалён или потерял права.\n"
                            "Подключите новый чат отчётов в панели: *Отчёты* → *➕ Подключить чат отчётов*.",
                            parse_mode="Markdown",
                            reply_markup=(
                                InlineKeyboardMarkup(
                                    inline_keyboard=[
                                        [InlineKeyboardButton(text="📊 Открыть Отчёты", url=reports_url)]
                                    ]
                                )
                                if reports_url
                                else None
                            ),
                        )
                    except Exception:
                        pass
                await session.commit()
                if removed_from_protected and owner_uid:
                    try:
                        await send_disconnect_comeback_dm(int(owner_uid), int(chat.id), protected_title)
                    except Exception:
                        pass
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
            from app.services.chat_owner_guard import (
                resolve_group_creator_id,
                transfer_chat_owner_to_creator_if_needed,
            )

            owner_uid, _, _ = await resolve_guard_connect_actor_for_group(
                update.bot, chat.id, update.from_user
            )
            owner_uid = int(owner_uid or 0)
            async with await get_session() as session:
                chat_row = await session.get(Chat, chat.id)
                if not chat_row:
                    chat_row = Chat(
                        id=chat.id,
                        title=chat.title or "",
                        owner_user_id=owner_uid,
                        is_active=False,
                        is_log_chat=False,
                    )
                    session.add(chat_row)
                else:
                    chat_row.title = chat.title or chat_row.title or ""
                    prev_active = bool(getattr(chat_row, "is_active", False))
                    if not prev_active:
                        chat_row.owner_user_id = owner_uid
                    elif owner_uid > 0:
                        creator_id = await resolve_group_creator_id(update.bot, chat.id)
                        if creator_id and creator_id == owner_uid:
                            await transfer_chat_owner_to_creator_if_needed(update.bot, chat_row)
                await session.commit()
        except Exception:
            pass
        # Привязку чата отчётов по pending делаем только после выдачи админки (ниже),
        # чтобы не выходить из обработчика раньше удаления служебных сообщений и единообразно сценария member→admin.

    # ТЗ ЧЕККК: когда бот назначен админом — удаляем сообщение «назначьте админом», если было
    _promote_msg_ids = getattr(on_my_chat_member, "_promote_msg_ids", {})
    if bot_is_admin and chat.id in _promote_msg_ids:
        try:
            await update.bot.delete_message(chat.id, _promote_msg_ids[chat.id])
        except Exception:
            pass
        del _promote_msg_ids[chat.id]

    # Для лог-чатов/чатов отчётов не включаем защиту автоматически.
    if bot_is_admin and await _skip_protection_prompt(chat.id, update.from_user.id):
        return

    # Если юзер запускал сценарий «подключить чат отчётов», то при выдаче админки тоже
    # считаем этот чат лог-чатом и не ведём дальше в поток «защищаемых».
    if bot_is_admin and await _try_bind_pending_reports_chat(update.bot, chat.id, chat.title or "", update.from_user.id):
        return

    if bot_is_admin:
        actor_id = int(update.from_user.id)
        try:
            from app.services.group_connect_actor import actor_may_connect_chat_as_owner

            if not await actor_may_connect_chat_as_owner(update.bot, chat.id, actor_id):
                try:
                    await update.bot.send_message(
                        actor_id,
                        "ℹ️ Подключить защиту может только владелец (создатель) группы. "
                        "Попросите владельца открыть Guard и добавить бота с правами администратора.",
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass
        # После выдачи админки подключаем защиту автоматически:
        # - skip для лог-чатов/чатов отчётов уже обработан выше;
        # - _try_bind_pending_reports_chat тоже отрабатывает выше и делает ранний return.
        # Это возвращает ожидаемое поведение для Free: группа сразу появляется в панели,
        # а приветствия уходят в группу и в личку владельцу кабинета Guard.
        try:
            from app.handlers.panel_dm import connect_chat_after_bot_added

            owner_uid, owner_un, owner_fn = await resolve_guard_connect_actor_for_group(
                update.bot, chat.id, update.from_user
            )
            if int(owner_uid or 0) > 0:
                ok, fail = await connect_chat_after_bot_added(
                    update.bot,
                    int(chat.id),
                    (chat.title or "").strip() or str(chat.id),
                    int(owner_uid),
                    username=owner_un,
                    first_name=owner_fn,
                )
                if not ok and fail == "limit":
                    try:
                        await send_user_dm(
                            update.bot,
                            int(owner_uid),
                            "❌ Достигнут лимит подключённых чатов по тарифу. "
                            "Откройте панель → «Тариф и оплата» или отключите лишние группы.",
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        return

    if not added:
        return

    # ТЗ ЧЕККК: бот в группе, но не админ — просим назначить (но не в чате отчётов)
    if not await _is_admin(update.bot, chat.id, update.from_user.id):
        return
    try:
        async with await get_session() as session:
            chat_row = await session.get(Chat, chat.id)
            # Для новых/неподключённых чатов не спамим подсказкой про админа.
            if not chat_row or not bool(getattr(chat_row, "is_active", False)):
                return
    except Exception:
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
            log_chat_row.is_active = False
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
