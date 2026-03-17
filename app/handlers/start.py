from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
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
CB_ADDGROUP = "st:addgroup"

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
        text="➕ Добавить бота в группу",
        callback_data=CB_ADDGROUP,
    )

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

ADDGROUP_TEXT = (
    "➕ *Добавить бота в группу*\n\n"
    "Нажмите *кнопку под полем ввода* — откроется выбор группы, затем Telegram предложит выдать боту права администратора.\n"
)

# Путь к скриншотам (положите addgroup_step1.png и addgroup_step2.png в static/ в корне проекта)
_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
ADDGROUP_SCREENSHOTS = (
    (_STATIC_DIR / "addgroup_step1.png", "1️⃣ Нажмите *кнопку под полем ввода* — откроется выбор группы."),
    (_STATIC_DIR / "addgroup_step2.png", "2️⃣ Выберите группу и выдайте боту права администратора."),
)


async def _send_addgroup_screenshots(bot, chat_id: int) -> None:
    """Отправить 2 скриншота-подсказки, если файлы есть."""
    from aiogram.types import FSInputFile
    for path, caption in ADDGROUP_SCREENSHOTS:
        if not path.exists():
            continue
        try:
            await bot.send_photo(
                chat_id,
                FSInputFile(path),
                caption=caption,
                parse_mode="Markdown",
            )
        except Exception:
            pass


@router.message(CommandStart())
async def cmd_start(message: Message):
    """ТЗ Меню: /start открывает главную панель. Deep link addgroup — кнопка «добавить в группу + выдать права»."""
    if message.chat.type != "private":
        return
    if not message.from_user:
        return

    args = (message.text or "").strip().split()
    # Deep link из Mini App: t.me/bot?start=cleandeleted_CHATID — запуск очистки от удалённых в группе
    if len(args) >= 2 and args[1].lower().startswith("cleandeleted_"):
        try:
            chat_id = int(args[1].split("_", 1)[1])
        except (ValueError, IndexError):
            chat_id = 0
        if chat_id and message.from_user:
            from app.db.session import get_session
            from app.api.service import user_can_access_chat
            from app.services.chat_cleanup import clean_deleted_accounts
            async with await get_session() as session:
                if await user_can_access_chat(session, message.from_user.id, chat_id):
                    try:
                        kicked, checked = await clean_deleted_accounts(message.bot, session, chat_id)
                        await message.answer(
                            f"🧹 *Очистка от удалённых*\n\nПроверено: {checked}\nИсключено удалённых аккаунтов: {kicked}",
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        await message.answer(f"Ошибка при очистке: {e}")
                else:
                    await message.answer("Нет доступа к этой группе.")
        return

    # Deep link из Mini App: t.me/bot?start=reportschat — выбор чата отчётов (для выбранной в панели группы)
    if len(args) >= 2 and args[1].lower() == "reportschat":
        try:
            from app.db.session import get_session
            from app.api.service import get_selected_chat_id
            from app.handlers import panel_dm
            async with await get_session() as session:
                selected = await get_selected_chat_id(session, message.from_user.id)
            if not selected:
                await message.answer(
                    "Сначала выберите чат в панели: *Подключённые чаты* → нажмите «Выбрать» у нужной группы, "
                    "затем снова нажмите «Подключить чат отчётов» в разделе Отчёты.",
                    parse_mode="Markdown",
                )
            else:
                panel_dm._pending_reports_for[message.from_user.id] = selected
                await message.answer(
                    "Нажми кнопку ниже — выбери группу, куда слать отчёты. Если бота там ещё нет — добавь его в ту группу и выбери снова.",
                    reply_markup=panel_dm._kb_connect_reports_chat(),
                )
        except Exception:
            await message.answer("Не удалось открыть выбор чата отчётов. Выберите чат в панели и попробуйте снова.")
        return

    # Deep link из Mini App: t.me/bot?start=addgroup — Reply-кнопка (выбор группы + права) + инлайн на случай превью
    if len(args) >= 2 and args[1].lower() == "addgroup":
        try:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            from app.handlers.panel_dm import _kb_connect_request_chat_with_admin
            me = await message.bot.get_me()
            username = me.username or "bot"
            add_url = f"https://t.me/{username}?start=addgroup"
            add_simple_url = f"https://t.me/{username}?startgroup"
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Выбрать группу и выдать права", url=add_url)],
            ])
            # Сначала сообщение с Reply-кнопкой (под полем ввода); под текстом — инлайн (видна в превью)
            await message.answer(
                ADDGROUP_TEXT,
                parse_mode="Markdown",
                reply_markup=_kb_connect_request_chat_with_admin(),
            )
            await _send_addgroup_screenshots(message.bot, message.chat.id)
        except Exception:
            await message.answer(ADDGROUP_TEXT, parse_mode="Markdown")
        return

    # ТЗ Напоминания: при первом /start записываем время для напоминаний (12ч, 24ч, 3д)
    try:
        from app.db.session import get_session
        from app.services.user_service import get_or_create_user
        from datetime import datetime, timezone
        async with await get_session() as session:
            user = await get_or_create_user(
                session,
                message.from_user.id,
                username=getattr(message.from_user, "username", None),
                first_name=getattr(message.from_user, "first_name", None),
            )
            if getattr(user, "first_start_at", None) is None:
                user.first_start_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception:
        pass
    try:
        from app.handlers.panel_dm import show_panel, _cache_clear
        _cache_clear(message.from_user.id)
        await show_panel(message.bot, message.from_user.id)
    except Exception:
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


async def _send_addgroup_keyboard(bot, user_id: int):
    """Отправить сообщение с Reply-кнопкой «выбор группы + выдача прав» (видна в обычном чате)."""
    from app.handlers.panel_dm import _kb_connect_request_chat_with_admin
    await bot.send_message(
        user_id,
        ADDGROUP_TEXT,
        parse_mode="Markdown",
        reply_markup=_kb_connect_request_chat_with_admin(),
    )
    await _send_addgroup_screenshots(bot, user_id)


@router.callback_query(F.data == CB_ADDGROUP)
async def cb_addgroup(cb: CallbackQuery):
    """По нажатию «Добавить бота в группу» — сразу показываем Reply-кнопку в этом чате (без ссылки)."""
    await cb.answer()
    if not cb.from_user:
        return
    try:
        await _send_addgroup_keyboard(cb.bot, cb.from_user.id)
    except Exception:
        await cb.message.answer(ADDGROUP_TEXT, parse_mode="Markdown")


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
    if not cb.from_user:
        return
    await cb.answer()

    try:
        from app.handlers.panel_dm import show_panel
        await show_panel(cb.bot, cb.from_user.id)
    except Exception as e:
        try:
            await cb.message.answer(
                f"❌ Не удалось открыть панель. Напиши /panel или попробуй позже.\n\nОшибка: {e!r}"
            )
        except Exception:
            pass
