from __future__ import annotations

import re
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple
from collections import OrderedDict
from sqlalchemy import select, func, delete

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.texts.bot_intro import START_INTRO_TEXT
from app.db.models import User, ChatManagerInvite, ChatManager

router = Router()
logger = logging.getLogger(__name__)


async def _referral_bind_would_cycle(session, new_user_tg_id: int, ref_user: User) -> bool:
    """Если новый пользователь уже выше реферера в дереве, привязка ref_* создаст цикл (U→…→R→U)."""
    cur: User | None = ref_user
    seen: set[int] = set()
    for _ in range(64):
        if not cur:
            return False
        p = getattr(cur, "referred_by_tg_id", None)
        if not p:
            return False
        pt = int(p)
        if pt == int(new_user_tg_id):
            return True
        if pt in seen:
            return True
        seen.add(pt)
        row = await session.execute(select(User).where(User.telegram_id == pt).limit(1))
        cur = row.scalar_one_or_none()
    return True
TRIAL_PREVIEW_CMD = (os.getenv("TRIAL_WARNING_PREVIEW_COMMAND") or "guard_trial_preview_48291").strip().lower()
EXPIRED_PREVIEW_CMD = (os.getenv("EXPIRED_WARNING_PREVIEW_COMMAND") or "guard_expired_preview").strip().lower()


def _is_trial_preview_command(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    # Разрешаем: /cmd, /cmd@BotName и cmd (без слеша).
    lowered = raw.lower()
    if lowered.startswith("/"):
        lowered = lowered[1:]
    lowered = lowered.split()[0]
    if "@" in lowered:
        lowered = lowered.split("@", 1)[0]
    return lowered == TRIAL_PREVIEW_CMD


def _is_expired_preview_command(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if lowered.startswith("/"):
        lowered = lowered[1:]
    lowered = lowered.split()[0]
    if "@" in lowered:
        lowered = lowered.split("@", 1)[0]
    return lowered == EXPIRED_PREVIEW_CMD

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
LAST_START_HANDLED_AT: "OrderedDict[int, datetime]" = OrderedDict()

CACHE_MAX = 2000
CACHE_TTL = timedelta(days=3)
START_DEDUP_WINDOW = timedelta(seconds=5)


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


def _should_skip_duplicate_start(user_id: int) -> bool:
    now = datetime.now(timezone.utc)
    last = LAST_START_HANDLED_AT.get(user_id)
    LAST_START_HANDLED_AT[user_id] = now
    LAST_START_HANDLED_AT.move_to_end(user_id)
    while len(LAST_START_HANDLED_AT) > CACHE_MAX:
        LAST_START_HANDLED_AT.popitem(last=False)
    if not last:
        return False
    return (now - last) < START_DEDUP_WINDOW


# =========================================================
# TEXTS
# =========================================================

START_TEXT = START_INTRO_TEXT

CONNECT_TEXT = (
    "➕ *Подключение защиты*\n\n"
    "Сделай 2 шага:\n\n"
    "1️⃣ Добавь бота в группу\n\n"
    "2️⃣ Дай права администратора:\n"
    "✅ удалять сообщения\n"
    "➕ желательно банить участников\n\n"
    "После этого группа появится в мини-приложении автоматически."
)

RULES_TEXT = (
    "📜 *Guard*\n\n"
    "Инструкция и описание функций находятся в приложении под знаком *i*."
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


def _mini_app_chats_startapp_link(bot_username: str) -> str:
    uname = (bot_username or "").strip().lstrip("@")
    short_name = (os.getenv("MINI_APP_SHORT_NAME") or os.getenv("WEBAPP_SHORT_NAME") or "").strip().strip("/")
    if short_name:
        return f"https://t.me/{uname}/{short_name}?startapp=chats"
    return f"https://t.me/{uname}?startapp=chats"


async def _activate_pending_manager_invites(message: Message) -> int:
    if not message.from_user:
        return 0
    uid = int(message.from_user.id)
    uname = (getattr(message.from_user, "username", None) or "").strip().lower()
    from app.db.session import get_session
    connected = 0
    async with await get_session() as session:
        invites = (
            await session.execute(
                select(ChatManagerInvite).where(
                    (ChatManagerInvite.target_telegram_id == uid)
                    | (
                        ChatManagerInvite.target_telegram_id.is_(None)
                        & (func.lower(ChatManagerInvite.target_username) == uname)
                    )
                )
            )
        ).scalars().all()
        for inv in invites:
            existing = (
                await session.execute(
                    select(ChatManager).where(
                        ChatManager.chat_id == int(inv.chat_id),
                        ChatManager.user_id == uid,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(ChatManager(chat_id=int(inv.chat_id), user_id=uid, added_by=int(inv.owner_user_id)))
            inv.target_telegram_id = uid
            if uname:
                inv.target_username = uname
            inv.connected_user_id = uid
            inv.status = "connected"
            connected += 1
        # чистим дубли sent/connecting для уже подключенного id
        if connected > 0:
            await session.execute(
                delete(ChatManagerInvite).where(
                    ChatManagerInvite.target_telegram_id == uid,
                    ChatManagerInvite.status.in_(("sent", "connecting")),
                )
            )
        await session.commit()
    return connected


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


def _group_start_payload(message: Message) -> str | None:
    """Аргумент deep links в группе: /start connect, /start@Bot connect (startgroup=…)."""
    t = (message.text or "").strip()
    if not t:
        return None
    m = re.match(r"^/start(?:@[A-Za-z0-9_]+)?\s+(\S+)", t)
    if not m:
        return None
    return m.group(1).strip().lower()


def _is_plain_group_start(message: Message) -> bool:
    t = (message.text or "").strip()
    return bool(re.match(r"^/start(?:@[A-Za-z0-9_]+)?\s*$", t, re.I))


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


async def _send_welcome_banner_if_any(bot, chat_id: int) -> None:
    """Дублирующее фото после /start; по умолчанию выкл. Картинка до «Старт» — через BotFather Description Picture."""
    from aiogram.types import FSInputFile
    from app.texts.bot_intro import WELCOME_BANNER_PATH, WELCOME_BANNER_CAPTION

    if not WELCOME_BANNER_PATH.is_file():
        return
    try:
        await bot.send_photo(
            chat_id,
            FSInputFile(WELCOME_BANNER_PATH),
            caption=WELCOME_BANNER_CAPTION,
        )
    except Exception:
        pass


@router.message(CommandStart())
async def cmd_start(message: Message):
    """ТЗ Меню: /start открывает главную панель. Deep link addgroup — кнопка «добавить в группу + выдать права»."""

    # ?startgroup= payloads приходят В ГРУППУ, не в личку
    if message.chat.type != "private":
        if not message.from_user:
            return
        payload = _group_start_payload(message)
        # В некоторых клиентах в группе прилетает просто /start@bot без payload.
        # Для UX «одна кнопка» трактуем это как connect.
        if payload is None and _is_plain_group_start(message):
            payload = "connect"
        if payload:
            # ?startgroup=reportschat_CHATID → эта группа становится чатом отчётов для CHATID
            if payload.startswith("reportschat_"):
                try:
                    protected_chat_id = int(payload.split("_", 1)[1])
                except (ValueError, IndexError):
                    return
                from app.db.session import get_session
                from app.api.service import user_can_access_chat
                from app.db.models import Chat
                uid = message.from_user.id
                reports_chat_id = message.chat.id
                reports_title = (message.chat.title or "").strip() or str(reports_chat_id)
                try:
                    async with await get_session() as session:
                        if not await user_can_access_chat(session, uid, protected_chat_id):
                            return
                        chat_row = await session.get(Chat, protected_chat_id)
                        if chat_row:
                            chat_row.log_chat_id = reports_chat_id
                        log_chat_row = await session.get(Chat, reports_chat_id)
                        if not log_chat_row:
                            log_chat_row = Chat(
                                id=reports_chat_id,
                                title=reports_title,
                                owner_user_id=uid,
                                is_log_chat=True,
                                is_active=False,
                            )
                            session.add(log_chat_row)
                        else:
                            log_chat_row.title = reports_title
                            log_chat_row.is_log_chat = True
                            log_chat_row.is_active = False
                        await session.commit()
                    protected_title = ""
                    try:
                        async with await get_session() as session:
                            cr = await session.get(Chat, protected_chat_id)
                            protected_title = (cr.title or "").strip() if cr else ""
                    except Exception:
                        pass
                    await message.answer(
                        f"✅ Чат отчётов подключён.\n"
                        f"Сюда будут приходить отчёты для «{protected_title or protected_chat_id}».",
                    )
                except Exception:
                    pass
                return
            # ?startgroup=connect → автоматически подключаем группу к защите
            if payload == "connect":
                try:
                    from aiogram.enums import ChatMemberStatus
                    from app.handlers.panel_dm import connect_chat_after_bot_added
                    from app.services.group_connect_actor import (
                        actor_may_init_group_connect_from_group,
                        resolve_guard_connect_actor_for_group,
                    )

                    chat_id = message.chat.id
                    chat_title = (message.chat.title or "").strip() or str(chat_id)
                    me = await message.bot.get_me()
                    m = await message.bot.get_chat_member(chat_id, me.id)
                    if m.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                        await message.answer(
                            "Чтобы включить защиту, назначьте меня администратором в этой группе."
                        )
                        return
                    if not await actor_may_init_group_connect_from_group(message.bot, chat_id, message):
                        await message.answer(
                            "Подключить защиту из группы может только *администратор* "
                            "или сообщение *от привязанного канала* (если группа — обсуждение канала).\n\n"
                            "Если включено «анонимное сообщение» не от канала — выключите анонимность для админов "
                            "или отправьте /start с личного Telegram (создатель группы).",
                            parse_mode="Markdown",
                        )
                        return
                    # Кабинет Guard — у создателя группы (см. resolve…).
                    uid, owner_un, owner_fn = await resolve_guard_connect_actor_for_group(
                        message.bot, chat_id, message.from_user
                    )
                    if int(uid or 0) <= 0:
                        await message.answer(
                            "Не удалось определить создателя группы для привязки к Guard. "
                            "Откройте панель из лички с ботом или попробуйте снова после выдачи боту прав администратора."
                        )
                        return
                    ok, fail = await connect_chat_after_bot_added(
                        message.bot,
                        chat_id,
                        chat_title,
                        uid,
                        username=owner_un,
                        first_name=owner_fn,
                    )
                    if ok:
                        return
                    if fail == "limit":
                        await message.answer(
                            "❌ Достигнут лимит подключённых чатов по тарифу.\n"
                            "Откройте панель → «Тариф и оплата» или отключите лишние группы в «Подключённые чаты»."
                        )
                    elif fail == "owner":
                        await message.answer(
                            "ℹ️ Эта группа в Guard уже подключена к другому кабинету (не к создателю этой группы).\n\n"
                            "Если нужна передача прав — только владелец текущего кабинета: раздел *Админы и доступы*.",
                            parse_mode="Markdown",
                        )
                    elif fail == "log":
                        await message.answer(
                            "ℹ️ Эта группа используется как чат отчётов или недоступна для защиты. См. сообщения в личке."
                        )
                    else:
                        await message.answer(
                            "Не удалось включить защиту. Откройте панель из личного чата с ботом или повторите позже."
                        )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("startgroup=connect error: %s", e)
                    await message.answer(
                        "Не удалось включить защиту. Откройте панель из личного чата с ботом или повторите позже."
                    )
                return
        return
    if not message.from_user:
        return
    if _should_skip_duplicate_start(message.from_user.id):
        return

    args = (message.text or "").strip().split()
    plain_start_only = len(args) == 1 and bool(
        re.match(r"^/start(?:@[A-Za-z0-9_]+)?$", (args[0] or "").strip(), re.I)
    )
    # Deep link из Mini App: t.me/bot?start=cleandeleted_CHATID — запуск очистки от удалённых в группе
    # Реферальный deep link: /start ref_<telegram_id>
    if len(args) >= 2 and (args[1] or "").lower().startswith("ref_"):
        try:
            ref_tg_id = int((args[1] or "").split("_", 1)[1])
        except Exception:
            ref_tg_id = 0
        if ref_tg_id and message.from_user and ref_tg_id != message.from_user.id:
            try:
                from app.db.session import get_session
                from app.services.user_service import get_or_create_user
                async with await get_session() as session:
                    user = await get_or_create_user(
                        session,
                        message.from_user.id,
                        username=getattr(message.from_user, "username", None),
                        first_name=getattr(message.from_user, "first_name", None),
                    )
                    ref_row = await session.execute(select(User).where(User.telegram_id == ref_tg_id))
                    ref_user = ref_row.scalar_one_or_none()
                    # Привязываем реферера только один раз.
                    if not getattr(user, "referred_by_tg_id", None):
                        if ref_user and not await _referral_bind_would_cycle(
                            session, int(message.from_user.id), ref_user
                        ):
                            user.referred_by_tg_id = ref_tg_id
                            ref_user.ref_invited_count = int(getattr(ref_user, "ref_invited_count", 0) or 0) + 1
                            await session.commit()
                    if ref_user:
                        ref_user.ref_start_count = int(getattr(ref_user, "ref_start_count", 0) or 0) + 1
                        await session.commit()
            except Exception:
                pass

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

    # Deep link из Mini App: t.me/bot?start=reportschat или reportschat_<chat_id>
    if len(args) >= 2:
        m = re.match(r"^reportschat(?:_(-?\d+))?$", (args[1] or "").strip(), re.I)
        if m:
            try:
                from app.db.session import get_session
                from app.api.service import get_selected_chat_id, user_can_access_chat
                from app.handlers import panel_dm
                uid = message.from_user.id
                selected: int | None = None
                async with await get_session() as session:
                    if m.group(1) is not None:
                        selected = int(m.group(1))
                        if not await user_can_access_chat(session, uid, selected):
                            await message.answer(
                                "Нет доступа к этой группе. Открой *Отчёты* в панели для нужного чата.",
                                parse_mode="Markdown",
                            )
                            return
                    else:
                        selected = await get_selected_chat_id(session, uid)
                if not selected:
                    await message.answer(
                        "Сначала выберите группу в приложении: *Подключённые чаты* → *Отчёты*, "
                        "либо *Выбрать* у нужной группы, затем снова «Подключить чат отчётов».",
                        parse_mode="Markdown",
                    )
                else:
                    panel_dm._pending_reports_for[uid] = selected
                    me = await message.bot.get_me()
                    username = me.username or "bot"
                    pick_url = f"https://t.me/{username}?startgroup=reportschat_{selected}"
                    await message.answer("\u2063", reply_markup=ReplyKeyboardRemove())
                    kb = InlineKeyboardBuilder()
                    kb.button(text="📋 Выбрать чат отчётов", url=pick_url)
                    kb.adjust(1)
                    await message.answer(
                        "⬅️ *Управляй Guard через кнопку «Меню» сверху.*\n\n"
                        "Кнопка под полем ввода отключена.\n"
                        "Нажми кнопку ниже и выбери группу для отчётов.",
                        parse_mode="Markdown",
                        reply_markup=kb.as_markup(),
                    )
            except Exception:
                await message.answer(
                    "Не удалось открыть выбор чата отчётов. Открой раздел *Отчёты* в приложении и попробуйте снова.",
                    parse_mode="Markdown",
                )
            return

    # Deep link из Mini App: t.me/bot?start=addgroup — Reply-кнопка (выбор группы + права) + инлайн на случай превью
    if len(args) >= 2 and args[1].lower() == "addgroup":
        try:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            from app.handlers.panel_dm import _kb_connect_request_chat_with_admin
            me = await message.bot.get_me()
            username = me.username or "bot"
            add_url = f"https://t.me/{username}?start=addgroup"
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
    connected_shared_cabinets = 0
    try:
        from app.db.session import get_session
        from app.services.user_service import (
            get_or_create_user,
            TARIFF_CHAT_LIMITS,
            TARIFF_GROUP_LIMITS,
            TARIFF_CHANNEL_LIMITS,
        )
        from app.db.models import Tariff
        from datetime import datetime, timezone
        async with await get_session() as session:
            user = await get_or_create_user(
                session,
                message.from_user.id,
                username=getattr(message.from_user, "username", None),
                first_name=getattr(message.from_user, "first_name", None),
            )
            if getattr(user, "first_start_at", None) is None:
                now = datetime.now(timezone.utc)
                user.first_start_at = now
                # Первый старт: выдаём 3 дня полного Premium автоматически.
                user.tariff = Tariff.PREMIUM.value
                user.chat_limit = TARIFF_CHAT_LIMITS[Tariff.PREMIUM.value]
                user.group_limit = TARIFF_GROUP_LIMITS[Tariff.PREMIUM.value]
                user.channel_limit = TARIFF_CHANNEL_LIMITS[Tariff.PREMIUM.value]
                user.subscription_until = now + timedelta(days=3)
                user.subscription_source = "trial"
                await session.commit()
    except Exception:
        pass
    try:
        connected_shared_cabinets = await _activate_pending_manager_invites(message)
    except Exception as e:
        logger.warning("activate pending manager invites failed user=%s: %s", getattr(message.from_user, "id", None), e)
    if plain_start_only and os.getenv("WELCOME_BANNER_AFTER_START", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        await _send_welcome_banner_if_any(message.bot, message.chat.id)
    try:
        from app.handlers.panel_dm import show_panel
        await show_panel(message.bot, message.from_user.id)
    except Exception:
        await _edit_or_send(message, START_TEXT, start_kb())
    if connected_shared_cabinets > 0:
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            me = await message.bot.get_me()
            await message.answer(
                f"✅ Вас добавили админом в кабинет(ы): *{connected_shared_cabinets}*.\n"
                "Откройте общий кабинет и переключитесь на вкладку *Доступы*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🚀 Открыть общий кабинет", url=_mini_app_chats_startapp_link(me.username or "bot"))]
                    ]
                ),
            )
        except Exception:
            pass


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


@router.message(F.chat.type == "private", F.text)
async def cmd_preview_commands(message: Message):
    """Служебные предпросмотры уведомлений: trial/expired."""
    is_trial = _is_trial_preview_command(message.text)
    is_expired = _is_expired_preview_command(message.text)
    if not is_trial and not is_expired:
        return
    if not message.from_user:
        return
    try:
        if is_trial:
            from app.services.reminders import send_trial_warning_preview_guard
            await send_trial_warning_preview_guard(
                message.bot,
                message.from_user.id,
                display_name=getattr(message.from_user, "first_name", None),
            )
        else:
            from app.services.reminders import send_expired_warning_preview
            await send_expired_warning_preview(
                message.bot,
                message.chat.id,
                display_name=getattr(message.from_user, "first_name", None),
            )
    except Exception as e:
        await message.answer(f"Не удалось отправить предпросмотр: {e}")
