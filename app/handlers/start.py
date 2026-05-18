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
from aiogram.filters import Command, CommandStart, BaseFilter
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.texts.bot_intro import START_INTRO_TEXT
from app.i18n import t as _i18n_t
from app.services.user_locale import lang_from_update as _lang_from_update, get_user_language as _get_user_lang
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


class _ReminderPreviewDmFilter(BaseFilter):
    """Только TRIAL / EXPIRED preview — чтобы не блокировать любой текст в личке (panel reply-клавиатура и т.п.)."""

    async def __call__(self, message: Message) -> bool:
        txt = getattr(message, "text", None) or ""
        return _is_trial_preview_command(txt) or _is_expired_preview_command(txt)


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


async def _start_text_for(message_or_user) -> str:
    """Локализованный приветственный текст. Берёт язык из БД с TTL-кэшем."""
    try:
        lang = await _lang_from_update(message_or_user)
    except Exception:
        lang = "ru"
    val = _i18n_t(lang, "bot.welcome.intro")
    if not val or val == "bot.welcome.intro":
        return START_INTRO_TEXT
    return val


# Путь к скриншотам (положите addgroup_step1.png и addgroup_step2.png в static/ в корне проекта)
_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def start_kb(lang: str = "ru"):
    st = "bot.start"
    kb = InlineKeyboardBuilder()
    kb.button(text=_i18n_t(lang, f"{st}.btn_add_bot"), callback_data=CB_ADDGROUP)
    kb.button(text=_i18n_t(lang, f"{st}.btn_connect"), callback_data=CB_CONNECT)
    kb.button(text=_i18n_t(lang, f"{st}.btn_panel"), callback_data=CB_PANEL)
    kb.button(text=_i18n_t(lang, f"{st}.btn_rules"), callback_data=CB_RULES)
    kb.adjust(1)
    return kb.as_markup()


def back_kb(lang: str = "ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text=_i18n_t(lang, "bot.start.btn_back"), callback_data=CB_BACK)
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

async def _send_addgroup_screenshots(bot, chat_id: int, lang: str = "ru") -> None:
    """Отправить 2 скриншота-подсказки, если файлы есть."""
    from aiogram.types import FSInputFile
    shots = (
        (_STATIC_DIR / "addgroup_step1.png", _i18n_t(lang, "bot.start.addgroup_step1")),
        (_STATIC_DIR / "addgroup_step2.png", _i18n_t(lang, "bot.start.addgroup_step2")),
    )
    for path, caption in shots:
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


async def _send_welcome_banner_if_any(bot, chat_id: int) -> None:
    """Дублирующее фото после /start; по умолчанию выкл. Картинка до «Старт» — через BotFather Description Picture."""
    from aiogram.types import FSInputFile
    from app.texts.bot_intro import WELCOME_BANNER_PATH, WELCOME_BANNER_CAPTION

    if not WELCOME_BANNER_PATH.is_file():
        return
    try:
        lang = await _get_user_lang(int(chat_id))
    except Exception:
        lang = "ru"
    caption = _i18n_t(lang, "bot.profile.welcome_banner_caption") or WELCOME_BANNER_CAPTION
    try:
        await bot.send_photo(
            chat_id,
            FSInputFile(WELCOME_BANNER_PATH),
            caption=caption,
        )
    except Exception:
        pass


def _format_perms_for_dm_local(perms: dict | None, lang: str) -> str:
    if not perms:
        return _i18n_t(lang, "api.ui.manager_perms_none")
    labels: list[str] = []
    for key in ("protection", "broadcast", "reports", "first_post_settings"):
        if perms.get(key):
            labels.append(_i18n_t(lang, f"api.ui.manager_perm_label_{key}"))
    if not labels:
        return _i18n_t(lang, "api.ui.manager_perms_none")
    return ", ".join(labels)


async def _accept_admin_invite_link(message: Message, token: str, lang: str) -> None:
    """Принять права делегата по ссылке t.me/<bot>?start=admin_invite_<token>.

    Логика:
      1. По token находим ChatManagerInvite. Не нашли / истёк / уже использован — отвечаем соответствующим текстом.
      2. Если получатель — owner чата, нет смысла принимать.
      3. Получатель должен быть админом самой Telegram-группы (как и в API-добавлении делегата).
      4. Создаём/обновляем ChatManager с правами из инвайта, помечаем invite как `connected`.
      5. Отправляем подтверждение в DM (+ кнопку «открыть Mini App»).
    """
    if not token or len(token) < 8:
        await message.answer(_i18n_t(lang, "api.ui.manager_invite_link_unknown"), parse_mode="Markdown")
        return
    if not message.from_user:
        return
    user_id = int(message.from_user.id)

    from app.db.session import get_session
    from app.db.models import Chat

    async with await get_session() as session:
        inv = (
            await session.execute(
                select(ChatManagerInvite).where(ChatManagerInvite.token == token).limit(1)
            )
        ).scalar_one_or_none()
        if not inv:
            await message.answer(
                _i18n_t(lang, "api.ui.manager_invite_link_unknown"),
                parse_mode="Markdown",
            )
            return
        # Истёкшая ссылка — удаляем, чтобы не висела.
        exp = getattr(inv, "expires_at", None)
        if exp is not None and exp <= datetime.now(timezone.utc):
            try:
                await session.execute(
                    delete(ChatManagerInvite).where(ChatManagerInvite.id == int(inv.id))
                )
                await session.commit()
            except Exception:
                pass
            await message.answer(
                _i18n_t(lang, "api.ui.manager_invite_link_expired"),
                parse_mode="Markdown",
            )
            return

        chat = await session.get(Chat, int(inv.chat_id))
        if not chat:
            await message.answer(
                _i18n_t(lang, "api.ui.manager_invite_link_unknown"),
                parse_mode="Markdown",
            )
            return
        chat_title = str(getattr(chat, "title", "") or "") or f"#{int(chat.id)}"
        owner_uid = int(getattr(chat, "owner_user_id", 0) or 0)
        if user_id == owner_uid:
            await message.answer(
                _i18n_t(lang, "api.ui.manager_invite_link_already", chat_title=chat_title),
                parse_mode="Markdown",
            )
            return

        # Уже есть активный ChatManager для этого user/chat? Тогда просто переподтверждаем
        # права из инвайта и сообщаем, что доступ уже выдан.
        existing_mgr = (
            await session.execute(
                select(ChatManager)
                .where(
                    ChatManager.chat_id == int(inv.chat_id),
                    ChatManager.user_id == user_id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        # Получатель должен быть админом Telegram-чата (как и при добавлении через API).
        role: str = ""
        try:
            mem = await message.bot.get_chat_member(int(inv.chat_id), user_id)
            role = str(getattr(mem, "status", "") or "").lower()
        except Exception:
            role = ""
        if role not in ("administrator", "creator"):
            await message.answer(
                _i18n_t(lang, "api.ui.manager_invite_link_need_tg_admin", chat_title=chat_title),
                parse_mode="Markdown",
            )
            return

        perms = {
            "protection": bool(getattr(inv, "can_protection", False)),
            "broadcast": bool(getattr(inv, "can_broadcast", False)),
            "reports": bool(getattr(inv, "can_reports", False)),
            "first_post_settings": bool(getattr(inv, "can_first_post_settings", False)),
        }

        if existing_mgr:
            existing_mgr.can_protection = perms["protection"]
            existing_mgr.can_broadcast = perms["broadcast"]
            existing_mgr.can_reports = perms["reports"]
            existing_mgr.can_first_post_settings = perms["first_post_settings"]
        else:
            session.add(
                ChatManager(
                    chat_id=int(inv.chat_id),
                    user_id=user_id,
                    added_by=owner_uid,
                    can_protection=perms["protection"],
                    can_broadcast=perms["broadcast"],
                    can_reports=perms["reports"],
                    can_first_post_settings=perms["first_post_settings"],
                )
            )

        inv.target_telegram_id = inv.target_telegram_id or user_id
        inv.connected_user_id = user_id
        inv.status = "connected"
        # Записываем в audit-log «инвайт принят по ссылке».
        # Импортируем лениво — чтобы не было циклической зависимости при загрузке модуля.
        try:
            from app.api.routes import record_manager_action  # noqa: WPS433
            await record_manager_action(
                session,
                chat_id=int(inv.chat_id),
                user_id=int(user_id),
                action_kind="manager_invite_accepted",
                target=int(user_id),
                meta={"perms": perms, "via_link": True},
            )
        except Exception as e:
            logger.warning("audit invite_accepted failed: %s", e)
        # Принятый инвайт больше не нужен по ссылке — но сохраняем запись для аудита.
        try:
            await session.commit()
        except Exception as e:
            logger.warning("accept admin_invite commit failed: %s", e)
            await session.rollback()
            await message.answer(
                _i18n_t(lang, "api.ui.manager_invite_link_unknown"),
                parse_mode="Markdown",
            )
            return

    # Подтверждение получателю.
    perms_text = _format_perms_for_dm_local(perms, lang)
    text = _i18n_t(
        lang,
        "api.ui.manager_invite_link_accepted",
        chat_title=chat_title,
        perms=perms_text,
    )
    kb = None
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from app.api.routes import _delegated_chats_webapp_url

        delegated_url = await _delegated_chats_webapp_url()
        if delegated_url:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text=_i18n_t(lang, "api.ui.manager_invite_open_access"),
                        url=delegated_url,
                    )]
                ]
            )
    except Exception:
        kb = None
    try:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            await message.answer(text, parse_mode="Markdown")
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
            lang = await _get_user_lang(
                int(message.from_user.id),
                fallback_tg_language_code=getattr(message.from_user, "language_code", None),
            )
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
                        _i18n_t(lang, "bot.start.group_reports_connected").format(
                            title=protected_title or protected_chat_id
                        ),
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
                        await message.answer(_i18n_t(lang, "bot.start.group_need_bot_admin"))
                        return
                    if not await actor_may_init_group_connect_from_group(message.bot, chat_id, message):
                        await message.answer(
                            _i18n_t(lang, "bot.start.group_actor_denied"),
                            parse_mode="Markdown",
                        )
                        return
                    # Кабинет Guard — у создателя группы (см. resolve…).
                    uid, owner_un, owner_fn = await resolve_guard_connect_actor_for_group(
                        message.bot, chat_id, message.from_user
                    )
                    if int(uid or 0) <= 0:
                        await message.answer(_i18n_t(lang, "bot.start.group_creator_resolve_fail"))
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
                        await message.answer(_i18n_t(lang, "bot.start.group_limit_reached"))
                    elif fail == "owner":
                        await message.answer(
                            _i18n_t(lang, "bot.start.group_owner_conflict"),
                            parse_mode="Markdown",
                        )
                    elif fail == "log":
                        await message.answer(_i18n_t(lang, "bot.start.group_log_conflict"))
                    else:
                        await message.answer(_i18n_t(lang, "bot.start.group_connect_fail"))
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("startgroup=connect error: %s", e)
                    await message.answer(_i18n_t(lang, "bot.start.group_connect_fail"))
                return
        return
    if not message.from_user:
        return

    args = (message.text or "").strip().split()
    plain_start_only = len(args) == 1 and bool(
        re.match(r"^/start(?:@[A-Za-z0-9_]+)?$", (args[0] or "").strip(), re.I)
    )
    # До любых await: маркировка повторного голого /start и лёгкое обновление панели (см. lock в panel_dm._edit_panel).
    if plain_start_only and _should_skip_duplicate_start(message.from_user.id):
        try:
            from app.handlers.panel_dm import show_panel
            await show_panel(message.bot, message.from_user.id, send_quick_reply_keyboard=True)
        except Exception:
            pass
        return

    dm_lang = await _get_user_lang(
        int(message.from_user.id),
        fallback_tg_language_code=getattr(message.from_user, "language_code", None),
    )
    # Deep link «принять права делегата чата»:
    # t.me/<bot>?start=admin_invite_<token>. См. ChatManagerInvite.token.
    if len(args) >= 2 and (args[1] or "").lower().startswith("admin_invite_"):
        try:
            raw = args[1] or ""
            token = raw[len("admin_invite_"):].strip()
            await _accept_admin_invite_link(message, token, dm_lang)
        except Exception as e:
            logger.exception("admin_invite handler error: %s", e)
        return

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
                            _i18n_t(dm_lang, "bot.start.cleanup_done").format(checked=checked, kicked=kicked),
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        await message.answer(
                            _i18n_t(dm_lang, "bot.start.cleanup_error").format(error=e),
                        )
                else:
                    await message.answer(_i18n_t(dm_lang, "bot.start.no_access_chat"))
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
                                _i18n_t(dm_lang, "bot.start.reports_no_access"),
                                parse_mode="Markdown",
                            )
                            return
                    else:
                        selected = await get_selected_chat_id(session, uid)
                if not selected:
                    await message.answer(
                        _i18n_t(dm_lang, "bot.start.reports_select_group_first"),
                        parse_mode="Markdown",
                    )
                else:
                    panel_dm._pending_reports_for[uid] = selected
                    me = await message.bot.get_me()
                    username = me.username or "bot"
                    pick_url = f"https://t.me/{username}?startgroup=reportschat_{selected}"
                    await panel_dm.dm_reply_keyboard_removed_send(message.bot, uid)
                    kb = InlineKeyboardBuilder()
                    kb.button(text=_i18n_t(dm_lang, "bot.start.reports_pick_btn"), url=pick_url)
                    kb.adjust(1)
                    await message.answer(
                        _i18n_t(dm_lang, "bot.start.reports_pick_hint"),
                        parse_mode="Markdown",
                        reply_markup=kb.as_markup(),
                    )
            except Exception:
                await message.answer(
                    _i18n_t(dm_lang, "bot.start.reports_pick_open_fail"),
                    parse_mode="Markdown",
                )
            return

    # Deep link из Mini App: t.me/bot?start=addgroup — Reply-кнопка (выбор группы + права) + инлайн на случай превью
    if len(args) >= 2 and args[1].lower() == "addgroup":
        try:
            from app.handlers.panel_dm import _kb_connect_request_chat_with_admin
            await message.answer(
                _i18n_t(dm_lang, "bot.start.addgroup_text"),
                parse_mode="Markdown",
                reply_markup=_kb_connect_request_chat_with_admin(lang=dm_lang),
            )
            await _send_addgroup_screenshots(message.bot, message.chat.id, dm_lang)
        except Exception:
            await message.answer(_i18n_t(dm_lang, "bot.start.addgroup_text"), parse_mode="Markdown")
        return

    # Первый /start: запоминаем момент для воронки напоминаний (12ч/24ч/3д «нет группы»
    # и серии Premium-trial DM 1..10). Тариф остаётся FREE — триал активируется явно
    # через Mini App (кнопка «Попробовать 10 дней бесплатно»).
    connected_shared_cabinets = 0
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
        await show_panel(message.bot, message.from_user.id, send_quick_reply_keyboard=True)
    except Exception:
        await _edit_or_send(message, await _start_text_for(message), start_kb(dm_lang))
        try:
            from app.handlers.panel_dm import ensure_dm_quick_reply_keyboard

            await ensure_dm_quick_reply_keyboard(message.bot, message.from_user.id)
        except Exception:
            pass
    if connected_shared_cabinets > 0:
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            me = await message.bot.get_me()
            await message.answer(
                _i18n_t(dm_lang, "bot.start.cabinet_added").format(n=connected_shared_cabinets),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=_i18n_t(dm_lang, "bot.start.cabinet_open_btn"),
                                url=_mini_app_chats_startapp_link(me.username or "bot"),
                            )
                        ]
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

    lang = await _lang_from_update(cb)
    await cb.message.edit_text(
        await _start_text_for(cb),
        parse_mode="Markdown",
        reply_markup=start_kb(lang),
    )


async def _send_addgroup_keyboard(bot, user_id: int):
    """Отправить сообщение с Reply-кнопкой «выбор группы + выдача прав» (видна в обычном чате)."""
    from app.handlers.panel_dm import _kb_connect_request_chat_with_admin
    lang = await _get_user_lang(int(user_id))
    await bot.send_message(
        user_id,
        _i18n_t(lang, "bot.start.addgroup_text"),
        parse_mode="Markdown",
        reply_markup=_kb_connect_request_chat_with_admin(lang=lang),
    )
    await _send_addgroup_screenshots(bot, user_id, lang)


@router.callback_query(F.data == CB_ADDGROUP)
async def cb_addgroup(cb: CallbackQuery):
    """По нажатию «Добавить бота в группу» — сразу показываем Reply-кнопку в этом чате (без ссылки)."""
    await cb.answer()
    if not cb.from_user:
        return
    try:
        await _send_addgroup_keyboard(cb.bot, cb.from_user.id)
    except Exception:
        lang = await _get_user_lang(int(cb.from_user.id))
        await cb.message.answer(_i18n_t(lang, "bot.start.addgroup_text"), parse_mode="Markdown")


@router.callback_query(F.data == CB_CONNECT)
async def cb_connect(cb: CallbackQuery):

    await cb.answer()

    lang = await _lang_from_update(cb)
    await cb.message.edit_text(
        _i18n_t(lang, "bot.start.connect_text"),
        parse_mode="Markdown",
        reply_markup=back_kb(lang),
    )


@router.callback_query(F.data == CB_RULES)
async def cb_rules(cb: CallbackQuery):

    await cb.answer()

    lang = await _lang_from_update(cb)
    await cb.message.edit_text(
        _i18n_t(lang, "bot.start.rules_text"),
        parse_mode="Markdown",
        reply_markup=back_kb(lang),
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
            lang = await _lang_from_update(cb)
            await cb.message.answer(
                _i18n_t(lang, "bot.start.panel_open_fail").format(error=repr(e)),
            )
        except Exception:
            pass


@router.message(F.chat.type == "private", _ReminderPreviewDmFilter())
async def cmd_preview_commands(message: Message):
    """Служебные предпросмотры уведомлений: trial/expired."""
    is_trial = _is_trial_preview_command(message.text)
    if not message.from_user:
        return
    try:
        from app.db.session import get_session
        from app.services.chat_owner_locale import user_locale

        async with await get_session() as session:
            preview_loc = await user_locale(session, int(message.from_user.id))
        if is_trial:
            from app.services.reminders import send_trial_warning_preview_guard
            await send_trial_warning_preview_guard(
                message.bot,
                message.from_user.id,
                display_name=getattr(message.from_user, "first_name", None),
                locale=preview_loc,
            )
        else:
            from app.services.reminders import send_expired_warning_preview
            await send_expired_warning_preview(
                message.bot,
                message.chat.id,
                display_name=getattr(message.from_user, "first_name", None),
                locale=preview_loc,
            )
    except Exception as e:
        loc = await _get_user_lang(int(message.from_user.id))
        await message.answer(_i18n_t(loc, "bot.start.preview_fail").format(error=e))
