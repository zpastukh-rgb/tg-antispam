from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict
from collections import OrderedDict

from aiogram import Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButtonRequestChat,
    ChatAdministratorRights,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, or_, func

from app.db.session import get_session
from app.db.models import Chat, Rule, UserContext, ChatManager, StopWord
from app.services.user_service import get_or_create_user, can_add_chat, TARIFF_CHAT_LIMITS
from app.texts.guardian_billing import (
    PREMIUM_DESCRIPTION,
    PREMIUM_PLANS,
    PREMIUM_ACTIVATED,
    PREMIUM_FEATURE_BLOCK,
    BUTTON_OPEN_SUBSCRIPTION,
    CMD_PREMIUM_RESPONSE,
    REMINDER_PREMIUM_WEEKLY,
    REMINDER_PREMIUM_SOFT,
    SPAM_DELETED_WITH_PREMIUM_HINT,
    NEWBIE_MODE_ACTIVATED,
    ANTIRAID_ACTIVATED,
    SUBSCRIPTION_EXPIRED,
)


router = Router()

# =========================================================
# 😈 AntiSpam Guardian — ПАНЕЛЬ (PRO)
# ---------------------------------------------------------
# • Inline UI (2 колонки) + подменю
# • одно сообщение (edit вместо спама)
# • selected_chat_id хранится в БД (UserContext)
# • защита памяти на 200–300 чатов: LRU + TTL cache
# • pending-ввод минут (mute/newbie) тоже с TTL
# =========================================================


# =========================================================
# 1) LRU + TTL CACHE (архитектурный фикс утечки памяти)
# ---------------------------------------------------------
# У каждого user_id запоминаем message_id панели
# и редактируем его, а не плодим новые сообщения.
# =========================================================

PANEL_MSG_CACHE: "OrderedDict[int, Tuple[int, datetime]]" = OrderedDict()
CACHE_MAX = 3000
CACHE_TTL = timedelta(days=3)


def _cache_set(user_id: int, msg_id: int) -> None:
    now = datetime.now(timezone.utc)
    PANEL_MSG_CACHE[user_id] = (msg_id, now)
    PANEL_MSG_CACHE.move_to_end(user_id)

    # TTL cleanup
    for uid in list(PANEL_MSG_CACHE.keys()):
        _mid, ts = PANEL_MSG_CACHE[uid]
        if now - ts > CACHE_TTL:
            PANEL_MSG_CACHE.pop(uid, None)

    # LRU cap
    while len(PANEL_MSG_CACHE) > CACHE_MAX:
        PANEL_MSG_CACHE.popitem(last=False)


def _cache_get(user_id: int) -> Optional[int]:
    item = PANEL_MSG_CACHE.get(user_id)
    if not item:
        return None

    msg_id, ts = item
    now = datetime.now(timezone.utc)

    if now - ts > CACHE_TTL:
        PANEL_MSG_CACHE.pop(user_id, None)
        return None

    PANEL_MSG_CACHE.move_to_end(user_id)
    return msg_id


def _cache_clear(user_id: int) -> None:
    """Сброс кэша панели (чтобы /panel всегда показывал главный экран)."""
    PANEL_MSG_CACHE.pop(user_id, None)


# =========================================================
# 2) Pending input (минуты) — TTL чтобы не залипало
# =========================================================

@dataclass
class Pending:
    kind: str  # "mute_minutes" | "newbie_minutes"
    chat_id: int
    expires_at: datetime


PENDING: Dict[int, Pending] = {}
PENDING_TTL = timedelta(minutes=7)


def _pending_set(user_id: int, kind: str, chat_id: int) -> None:
    PENDING[user_id] = Pending(
        kind=kind,
        chat_id=chat_id,
        expires_at=datetime.now(timezone.utc) + PENDING_TTL,
    )


def _pending_get(user_id: int) -> Optional[Pending]:
    p = PENDING.get(user_id)
    if not p:
        return None
    if datetime.now(timezone.utc) > p.expires_at:
        PENDING.pop(user_id, None)
        return None
    return p


def _pending_clear(user_id: int) -> None:
    PENDING.pop(user_id, None)


# =========================================================
# CALLBACK KEYS
# =========================================================

CB_MAIN = "p:main"
CB_PROTECTION = "p:protection"   # внутри выбранного чата
CB_REPORTS = "p:reports"

# Подключённые чаты: выбор режима (ТЗ правки)
CB_CHATS = "p:chats"             # раздел "Подключённые чаты"
CB_CHATS_ONE = "p:chats_one"     # управление одной группой
CB_CHATS_ALL = "p:chats_all"    # управление всеми группами
CB_CHATS_LIST = "p:chats_list"
CB_CHATS_LOGS = "p:chats_logs"
CB_PICK_CHAT = "p:pick_chat"     # сменить чат (внутри управления чатом)
CB_BILLING = "p:billing"
CB_PLAN = "p:plan:"           # p:plan:1, p:plan:3, ... p:plan:24
CB_PLAN_COMPARE = "p:plan:compare"
CB_CHAT_PAGE = "p:chat_page:"
CB_SET_CHAT = "p:set_chat:"      # выбор чата из списка → экран управления группой

CB_BACK = "p:back"

# Внутри Защита (ТЗ доработка: Назад из подразделов ведёт в Защита)
CB_BACK_TO_PROTECTION = "p:back_protection"
CB_FILTERS = "p:filters"
CB_PUNISH = "p:punish"
CB_NEWBIE = "p:newbie"
CB_STOPWORDS = "p:stopwords"
CB_RAID = "p:raid"
CB_ANTINAKRUTKA = "p:antinakrutka"
CB_ANTINAKRUTKA_TOGGLE = "p:antinakr_t"
CB_ANTINAKRUTKA_THRESH = "p:antinakr_th:"
CB_ANTINAKRUTKA_WINDOW = "p:antinakr_win:"
CB_ANTINAKRUTKA_ACTION = "p:antinakr_act:"
CB_ANTINAKRUTKA_RESTRICT = "p:antinakr_r:"
CB_BACK_TO_CHAT = "p:back_chat"  # назад к экрану «Управление группой»
CB_CLEAN_DELETED = "p:clean_deleted"
CB_GLOBAL_ANTISPAM = "p:global_antispam"
CB_GLOBAL_ANTISPAM_TOGGLE = "p:ga_toggle"
CB_GLOBAL_ANTISPAM_ADD = "p:ga_add"
CB_PROFANITY = "p:profanity"
CB_PROFANITY_TOGGLE = "p:prof_toggle"
CB_PROFANITY_ADD = "p:prof_add"
CB_PROFANITY_DEL = "p:prof_del:"  # + index
CB_PROMO_ENTER = "p:promo_enter"
CB_COPY_SETTINGS = "p:copy_settings"
CB_COPY_TARGET = "p:copy_target:"  # + chat_id
CB_PUBLIC_ALERTS = "p:public_alerts"
# Капча на первое сообщение (ТЗ доработка Защита)
CB_CAPTCHA_FIRST = "p:captcha_first"
CB_CAPTCHA_FIRST_ON = "p:captcha_first_on"
CB_CAPTCHA_FIRST_OFF = "p:captcha_first_off"
# Подразделы Фильтров
CB_FILTER_LINKS = "p:fl_links"
CB_FILTER_MEDIA = "p:fl_media"
CB_FILTER_BUTTONS = "p:fl_buttons"
CB_FILTER_ALL_CAPTCHA = "p:fl_all_captcha"
CB_FILTER_JOIN_MSG = "p:fl_join"
CB_FILTER_SILENCE = "p:fl_silence"
CB_FILTER_SPAM = "p:fl_spam"
# Режимы фильтра: allow / captcha / forbid
CB_FILTER_SET = "p:fl_set:"  # + mode (allow|captcha|forbid) + key (links|media|buttons)
CB_FILTER_ALL_CAPTCHA_TIME = "p:fl_cap:"   # + minutes
CB_FILTER_JOIN_TOGGLE = "p:fl_join_t"
CB_FILTER_SILENCE_TIME = "p:fl_sil:"       # + minutes
CB_FILTER_SPAM_TOGGLE = "p:fl_spam_t"
CB_PUBLIC_ALERTS_ON = "p:pa_on"
CB_PUBLIC_ALERTS_OFF = "p:pa_off"
CB_PUBLIC_ALERTS_EVERY_5 = "p:pa_every:5"
CB_PUBLIC_ALERTS_EVERY_10 = "p:pa_every:10"
CB_PUBLIC_ALERTS_INT_2 = "p:pa_int:120"
CB_PUBLIC_ALERTS_INT_5 = "p:pa_int:300"
CB_PUBLIC_ALERTS_INT_10 = "p:pa_int:600"

# Тумблеры/настройки
CB_TOGGLE_LINKS = "p:t_links"
CB_TOGGLE_MENTIONS = "p:t_mentions"
CB_TOGGLE_ANTIEDIT = "p:t_antiedit"

CB_MODE = "p:mode"
CB_SET_MUTE_MIN = "p:set_mute"
CB_SET_NEWBIE_MIN = "p:set_newbie_min"
CB_TOGGLE_NEWBIE = "p:t_newbie"

# Отчёты
CB_TOGGLE_REPORTS = "p:t_reports"
CB_PICK_REPORTS_CHAT = "p:pick_reports_chat"
CB_SET_REPORTS_CHAT = "p:set_reports_chat:"
CB_CLEAR_REPORTS_CHAT = "p:clear_reports_chat"
CB_REPORTS_HELP = "p:reports_help"

# Подключение
CB_CONNECT = "p:connect"
CB_ADDGROUP = "p:addgroup"  # кнопка «добавить в группу + выдать права» — Reply-клавиатура
CB_CONNECT_PICK_MODAL = "p:connect_pick_modal"   # открыть модалку выбора чата
CB_CONNECT_CONFIRM_PREFIX = "p:connect_confirm:"
CONNECT_REQUEST_ID = 0x7E17  # request_id для KeyboardButtonRequestChat
CB_CONNECT_REPORTS = "p:connect_reports"  # Подключить чат отчётов (ТЗ)
REPORTS_REQUEST_ID = 0x7E18  # request_id для выбора чата отчётов

# user_id -> protected chat_id (для какого чата настраиваем чат отчётов)
_pending_reports_for: Dict[int, int] = {}
# user_id -> True (ожидаем ввод user_id для добавления в антиспам базу)
_pending_antispam_add: Dict[int, bool] = {}
_pending_profanity_add: Dict[int, bool] = {}
_pending_promo: Dict[int, bool] = {}
_profanity_list_cache: Dict[int, List[str]] = {}  # user_id -> list of words for delete by index

# Отмена ввода
CB_CANCEL = "p:cancel"


# =========================================================
# HELPERS (DB / titles / safe edits)
# =========================================================

def _human_mode(mode: str) -> str:
    mode = (mode or "delete").lower()
    if mode == "ban":
        return "🚫 Вышвырнуть"
    if mode == "mute":
        return "🔇 Притушить"
    return "🧹 Снести"


def _next_mode(mode: str) -> str:
    mode = (mode or "delete").lower()
    if mode == "delete":
        return "mute"
    if mode == "mute":
        return "ban"
    return "delete"


async def _get_chat_title(bot, chat_id: int) -> str:
    try:
        c = await bot.get_chat(chat_id)
        return (c.title or str(chat_id)).strip()
    except Exception:
        return str(chat_id)


async def _get_or_create_user_ctx(session, user_id: int) -> UserContext:
    ctx = await session.get(UserContext, user_id)
    if not ctx:
        ctx = UserContext(user_id=user_id, selected_chat_id=None)
        session.add(ctx)
        await session.commit()
    return ctx


async def _get_selected_chat(session, user_id: int) -> Optional[int]:
    ctx = await _get_or_create_user_ctx(session, user_id)
    return int(ctx.selected_chat_id) if ctx.selected_chat_id else None


async def _set_selected_chat(session, user_id: int, chat_id: Optional[int]) -> None:
    ctx = await _get_or_create_user_ctx(session, user_id)
    ctx.selected_chat_id = chat_id
    await session.commit()


async def _managed_chats(session, user_id: int) -> List[Chat]:
    """
    Только защищаемые чаты (не лог-чаты):
    owner_user_id == user_id или менеджер через ChatManager.
    """
    sub = select(ChatManager.chat_id).where(ChatManager.user_id == user_id).subquery()
    res = await session.execute(
        select(Chat)
        .where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            or_(
                Chat.owner_user_id == user_id,
                Chat.id.in_(select(sub.c.chat_id)),
            ),
        )
        .order_by(Chat.id.asc())
    )
    return list(res.scalars().all())


async def _user_log_chats(session, user_id: int) -> List[Chat]:
    """Лог-чаты пользователя (где был выполнен /setlog)."""
    res = await session.execute(
        select(Chat)
        .where(
            Chat.is_log_chat == True,  # noqa: E712
            Chat.owner_user_id == user_id,
        )
        .order_by(Chat.id.asc())
    )
    return list(res.scalars().all())


async def _pending_chats(session, user_id: int) -> List[Chat]:
    """Чаты, куда пользователь добавил бота, но ещё не подключил к защите (is_active=False)."""
    res = await session.execute(
        select(Chat)
        .where(
            Chat.owner_user_id == user_id,
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == False,  # noqa: E712
        )
        .order_by(Chat.id.desc())
    )
    return list(res.scalars().all())


async def _get_or_create_rule(session, chat_id: int) -> Rule:
    rule = await session.get(Rule, chat_id)
    if rule:
        # страховка от None
        if not getattr(rule, "action_mode", None):
            rule.action_mode = "delete"
        if getattr(rule, "mute_minutes", None) is None:
            rule.mute_minutes = 30
        if getattr(rule, "newbie_minutes", None) is None:
            rule.newbie_minutes = 10
        if getattr(rule, "filter_links", None) is None:
            rule.filter_links = True
        if getattr(rule, "filter_mentions", None) is None:
            rule.filter_mentions = True
        if getattr(rule, "anti_edit", None) is None:
            rule.anti_edit = True
        if getattr(rule, "newbie_enabled", None) is None:
            rule.newbie_enabled = True
        if getattr(rule, "log_enabled", None) is None:
            rule.log_enabled = True
        if getattr(rule, "public_alerts_enabled", None) is None:
            rule.public_alerts_enabled = False
        if getattr(rule, "public_alerts_every_n", None) is None:
            rule.public_alerts_every_n = 5
        if getattr(rule, "public_alerts_min_interval_sec", None) is None:
            rule.public_alerts_min_interval_sec = 300
        await session.commit()
        return rule

    rule = Rule(
        chat_id=chat_id,
        filter_links=True,
        filter_mentions=True,
        action_mode="delete",
        mute_minutes=30,
        anti_edit=True,
        newbie_enabled=True,
        newbie_minutes=10,
        log_enabled=True,
        public_alerts_enabled=False,
        public_alerts_every_n=5,
        public_alerts_min_interval_sec=300,
        guardian_messages_enabled=True,
        auto_reports_enabled=True,
    )
    session.add(rule)
    await session.commit()
    return rule


async def _edit_panel(bot, user_id: int, text: str, kb: InlineKeyboardMarkup) -> None:
    msg_id = _cache_get(user_id)
    if msg_id:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=user_id,
                message_id=msg_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return
        except Exception:
            pass

    m = await bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=kb)
    _cache_set(user_id, m.message_id)


async def _edit_or_send(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        _cache_set(cb.from_user.id, cb.message.message_id)
    except Exception:
        await _edit_panel(cb.bot, cb.from_user.id, text, kb)


async def _get_selected_or_alert(cb: CallbackQuery) -> Optional[int]:
    async with await get_session() as session:
        sel = await _get_selected_chat(session, cb.from_user.id)
        if sel:
            return sel
    await cb.answer("Сначала выбери чат 😈", show_alert=True)
    return None


# =========================================================
# KEYBOARDS (2 колонки + понятные кнопки)
# =========================================================

def _kb_back_to_main() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


def _kb_cancel() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✖️ Отмена", callback_data=CB_CANCEL)
    b.adjust(1)
    return b.as_markup()


ADDGROUP_PANEL_TEXT = (
    "➕ *Добавить бота в группу*\n\n"
    "Нажми *кнопку под полем ввода* — откроется выбор группы, затем Telegram предложит выдать боту права администратора."
)

def _kb_main() -> InlineKeyboardMarkup:
    """Главное меню: Подключённые чаты, Тариф, Подключить чат, Добавить бота в группу."""
    b = InlineKeyboardBuilder()
    b.button(text="📂 Подключённые чаты", callback_data=CB_CHATS)
    b.button(text="💳 Тариф и оплата", callback_data=CB_BILLING)
    b.button(text="➕ Добавить бота в группу", callback_data=CB_ADDGROUP)
    b.button(text="➕ Подключить чат", callback_data=CB_CONNECT)
    b.adjust(1)
    return b.as_markup()


def _kb_protection() -> InlineKeyboardMarkup:
    """ТЗ доработка Защита: Капча, Фильтры, Наказания, Новички, Стоп-слова, Публичные сообщения, Анти-рейд. Назад → управление группой."""
    b = InlineKeyboardBuilder()
    b.button(text="⚙ Фильтры", callback_data=CB_FILTERS)
    b.button(text="🔨 Наказания", callback_data=CB_PUNISH)
    b.button(text="👶 Новички", callback_data=CB_NEWBIE)
    b.button(text="🧠 Стоп-слова", callback_data=CB_STOPWORDS)
    b.button(text="📢 Публичные сообщения", callback_data=CB_PUBLIC_ALERTS)
    b.button(text="🚨 Анти-рейд", callback_data=CB_RAID)
    b.button(text="📈 Антинакрутка", callback_data=CB_ANTINAKRUTKA)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
    b.adjust(1, 1, 2, 2, 1, 1, 1)
    return b.as_markup()


def _kb_public_alerts(rule: Rule) -> InlineKeyboardMarkup:
    """Настройки Guardian сообщения (ТЗ): общий переключатель + раз в N удалений."""
    on_off = "ВКЛ" if getattr(rule, "guardian_messages_enabled", True) else "ВЫКЛ"
    every = getattr(rule, "public_alerts_every_n", 5)
    interval_sec = getattr(rule, "public_alerts_min_interval_sec", 300)
    interval_min = interval_sec // 60
    b = InlineKeyboardBuilder()
    b.button(text=f"✅ Включить" if on_off != "ВКЛ" else "❌ Отключить", callback_data=CB_PUBLIC_ALERTS_ON if on_off != "ВКЛ" else CB_PUBLIC_ALERTS_OFF)
    b.button(text=f"🔁 Каждые 5 удалений", callback_data=CB_PUBLIC_ALERTS_EVERY_5)
    b.button(text=f"🔁 Каждые 10 удалений", callback_data=CB_PUBLIC_ALERTS_EVERY_10)
    b.button(text="⏱ Интервал 2 мин", callback_data=CB_PUBLIC_ALERTS_INT_2)
    b.button(text="⏱ Интервал 5 мин", callback_data=CB_PUBLIC_ALERTS_INT_5)
    b.button(text="⏱ Интервал 10 мин", callback_data=CB_PUBLIC_ALERTS_INT_10)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_chats_modes() -> InlineKeyboardMarkup:
    """Подключённые чаты: выбор режима — одна группа / все группы (ТЗ правки)."""
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Управление одной группой", callback_data=CB_CHATS_ONE)
    b.button(text="🌐 Управление всеми группами", callback_data=CB_CHATS_ALL)
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


def _kb_chat_manage() -> InlineKeyboardMarkup:
    """Внутри выбранного чата: Защита, Отчёты, Очистка, Антиспам база, Перенос настроек, Сменить чат, Назад."""
    b = InlineKeyboardBuilder()
    b.button(text="🛡 Защита", callback_data=CB_PROTECTION)
    b.button(text="🧾 Отчёты", callback_data=CB_REPORTS)
    b.button(text="🧹 Очистить от удалённых", callback_data=CB_CLEAN_DELETED)
    b.button(text="📋 Антиспам база", callback_data=CB_GLOBAL_ANTISPAM)
    b.button(text="🚫 Фильтр мата", callback_data=CB_PROFANITY)
    b.button(text="📤 Перенести настройки", callback_data=CB_COPY_SETTINGS)
    b.button(text="🔄 Сменить чат", callback_data=CB_PICK_CHAT)
    b.button(text="⬅️ Назад", callback_data=CB_CHATS_ONE)
    b.adjust(1)
    return b.as_markup()


def _kb_chats() -> InlineKeyboardMarkup:
    """Подменю Чаты (старый: список + лог-чаты) — для совместимости."""
    b = InlineKeyboardBuilder()
    b.button(text="🛡 Подключённые чаты", callback_data=CB_CHATS_LIST)
    b.button(text="🔄 Сменить чат", callback_data=CB_PICK_CHAT)
    b.button(text="📍 Лог-чаты", callback_data=CB_CHATS_LOGS)
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


def _filter_policy_label(mode: str) -> str:
    if mode == "forbid":
        return "ЗАПРЕЩЕНЫ"
    if mode == "captcha":
        return "ПРОВЕРЯЮ КАПЧЕЙ"
    return "РАЗРЕШЕНЫ"


def _kb_filters_main(rule: Rule, chat_title: str) -> InlineKeyboardMarkup:
    """ТЗ доработка: главный экран Фильтры — 8 подпунктов, Назад → Защита."""
    b = InlineKeyboardBuilder()
    b.button(text="🔗 Ссылки", callback_data=CB_FILTER_LINKS)
    b.button(text="🖼 Медиа / стикеры", callback_data=CB_FILTER_MEDIA)
    b.button(text="🔘 Сообщения с кнопками", callback_data=CB_FILTER_BUTTONS)
    b.button(text="👥 Сообщения «вступил в группу»", callback_data=CB_FILTER_JOIN_MSG)
    b.button(text="🔇 Режим тишины", callback_data=CB_FILTER_SILENCE)
    b.button(text="🛡 Защита от спама", callback_data=CB_FILTER_SPAM)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_filter_policy(rule: Rule, key: str) -> InlineKeyboardMarkup:
    """Клавиатура для Ссылки/Медиа/Кнопки: Разрешить, Проверять капчей, Запретить. Назад → Фильтры."""
    mode = getattr(rule, f"filter_{key}_mode", "allow") if key != "links" else getattr(rule, "filter_links_mode", "forbid")
    if key == "links" and not getattr(rule, "filter_links_mode", None):
        mode = "forbid" if rule.filter_links else "allow"
    b = InlineKeyboardBuilder()
    b.button(text="✅ Разрешить", callback_data=f"{CB_FILTER_SET}allow:{key}")
    b.button(text="🚫 Запретить", callback_data=f"{CB_FILTER_SET}forbid:{key}")
    b.button(text="⬅️ Назад", callback_data=CB_FILTERS)
    b.adjust(1)
    return b.as_markup()


def _kb_filter_all_captcha(rule: Rule) -> InlineKeyboardMarkup:
    """Проверка всех сообщений капчей: интервалы по времени, Назад → Фильтры."""
    CAPTCHA_OPTIONS = [(10, "10 минут"), (60, "1 час"), (120, "2 часа"), (180, "3 часа"), (240, "4 часа"),
                       (360, "6 часов"), (480, "8 часов"), (600, "10 часов"), (720, "12 часов"), (1440, "24 часа")]
    b = InlineKeyboardBuilder()
    for minutes, label in CAPTCHA_OPTIONS:
        b.button(text=label, callback_data=f"{CB_FILTER_ALL_CAPTCHA_TIME}{minutes}")
    b.button(text="❌ Отключить", callback_data=f"{CB_FILTER_ALL_CAPTCHA_TIME}0")
    b.button(text="⬅️ Назад", callback_data=CB_FILTERS)
    b.adjust(2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()


def _kb_filter_join(rule: Rule) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Удалять", callback_data=f"{CB_FILTER_JOIN_TOGGLE}:1")
    b.button(text="📌 Оставлять", callback_data=f"{CB_FILTER_JOIN_TOGGLE}:0")
    b.button(text="⬅️ Назад", callback_data=CB_FILTERS)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_filter_silence(rule: Rule) -> InlineKeyboardMarkup:
    SILENCE_OPTIONS = [(10, "10 минут"), (60, "1 час"), (120, "2 часа"), (180, "3 часа"), (240, "4 часа"),
                       (360, "6 часов"), (480, "8 часов"), (600, "10 часов"), (720, "12 часов"), (1440, "24 часа")]
    b = InlineKeyboardBuilder()
    for minutes, label in SILENCE_OPTIONS:
        b.button(text=label, callback_data=f"{CB_FILTER_SILENCE_TIME}{minutes}")
    b.button(text="❌ Отключить", callback_data=f"{CB_FILTER_SILENCE_TIME}0")
    b.button(text="⬅️ Назад", callback_data=CB_FILTERS)
    b.adjust(2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()


def _kb_filter_spam(rule: Rule) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Включить", callback_data=f"{CB_FILTER_SPAM_TOGGLE}:1")
    b.button(text="❌ Отключить", callback_data=f"{CB_FILTER_SPAM_TOGGLE}:0")
    b.button(text="⬅️ Назад", callback_data=CB_FILTERS)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_filters(rule: Rule) -> InlineKeyboardMarkup:
    """Старый экран фильтров (тумблеры) — для CB_TOGGLE_* после изменения, Назад → Защита."""
    b = InlineKeyboardBuilder()
    b.button(
        text=f"🔗 Ссылки: {'РЕЖУ' if rule.filter_links else 'НЕ'}",
        callback_data=CB_TOGGLE_LINKS,
    )
    b.button(
        text=f"🏷 @: {'РЕЖУ' if rule.filter_mentions else 'НЕ'}",
        callback_data=CB_TOGGLE_MENTIONS,
    )
    b.button(
        text=f"✏️ Anti-edit: {'ВКЛ' if rule.anti_edit else 'ВЫКЛ'}",
        callback_data=CB_TOGGLE_ANTIEDIT,
    )
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(2, 2)
    return b.as_markup()


def _kb_punish(rule: Rule) -> InlineKeyboardMarkup:
    mode = _human_mode(rule.action_mode)
    mute_min = int(rule.mute_minutes or 30)

    b = InlineKeyboardBuilder()

    b.button(text=f"😈 Режим: {mode}", callback_data=CB_MODE)
    b.button(text=f"🔇 Мут: {mute_min}м", callback_data=CB_SET_MUTE_MIN)

    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)

    b.adjust(2, 1)
    return b.as_markup()


def _kb_newbie(rule: Rule) -> InlineKeyboardMarkup:
    newbie_on = bool(rule.newbie_enabled)
    newbie_min = int(rule.newbie_minutes or 10)

    b = InlineKeyboardBuilder()
    b.button(
        text=f"👶 Новичок: {'ВКЛ' if newbie_on else 'ВЫКЛ'}",
        callback_data=CB_TOGGLE_NEWBIE,
    )
    b.button(
        text=f"⏱ Окно: {newbie_min}м",
        callback_data=CB_SET_NEWBIE_MIN,
    )
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_reports(rule: Rule) -> InlineKeyboardMarkup:
    """ТЗ Отчёты: чат отчётов (не «лог»), кнопка «Подключить чат отчётов»."""
    b = InlineKeyboardBuilder()
    b.button(text="➕ Подключить чат отчётов", callback_data=CB_CONNECT_REPORTS)
    b.button(
        text=f"🧾 Отчёты: {'ВКЛ' if rule.log_enabled else 'ВЫКЛ'}",
        callback_data=CB_TOGGLE_REPORTS,
    )
    b.button(text="🔄 Сменить чат отчётов", callback_data=CB_PICK_REPORTS_CHAT)
    b.button(text="🚫 Не слать отчёты", callback_data=CB_CLEAR_REPORTS_CHAT)
    b.button(text="🧾 Как работает", callback_data=CB_REPORTS_HELP)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
    b.adjust(1, 2, 2, 1)
    return b.as_markup()


def _kb_stopwords_stub() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=CB_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_raid_stub() -> InlineKeyboardMarkup:
    """Анти-рейд: заглушка (Guardian Premium). Кнопка «Открыть подписку» + Назад."""
    b = InlineKeyboardBuilder()
    b.button(text=BUTTON_OPEN_SUBSCRIPTION, callback_data=CB_BILLING)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_antinakrutka(rule: Rule) -> InlineKeyboardMarkup:
    """Антинакрутка: вкл/выкл, порог, окно, действие; мут — только при «оповещение + мут»."""
    on_off = "ВКЛ" if getattr(rule, "antinakrutka_enabled", False) else "ВЫКЛ"
    act = (getattr(rule, "antinakrutka_action", None) or "alert").strip().lower()
    if act not in ("alert", "alert_restrict"):
        act = "alert"
    b = InlineKeyboardBuilder()
    b.button(text=f"{'❌ Выключить' if on_off == 'ВКЛ' else '✅ Включить'}", callback_data=CB_ANTINAKRUTKA_TOGGLE)
    for n in (5, 10, 15, 20):
        b.button(text=f"Порог {n}", callback_data=f"{CB_ANTINAKRUTKA_THRESH}{n}")
    for m in (3, 5, 10):
        b.button(text=f"Окно {m}м", callback_data=f"{CB_ANTINAKRUTKA_WINDOW}{m}")
    b.button(text="Только оповещение", callback_data=f"{CB_ANTINAKRUTKA_ACTION}alert")
    b.button(text="Оповещение + мут", callback_data=f"{CB_ANTINAKRUTKA_ACTION}alert_restrict")
    if act == "alert_restrict":
        for r in (15, 30, 60):
            b.button(text=f"Мут {r}м", callback_data=f"{CB_ANTINAKRUTKA_RESTRICT}{r}")
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)
    if act == "alert_restrict":
        b.adjust(1, 4, 3, 2, 3, 1)
    else:
        b.adjust(1, 4, 3, 2, 1)
    return b.as_markup()


def _kb_premium_plans(back_callback: str = CB_MAIN) -> InlineKeyboardMarkup:
    """Клавиатура выбора периода подписки (Guardian Premium) и ввод промокода."""
    b = InlineKeyboardBuilder()
    for months, label, _price, _savings in PREMIUM_PLANS:
        first_line = label.split("\n")[0].strip()
        b.button(text=first_line, callback_data=f"{CB_PLAN}{months}")
    b.button(text="🎁 Ввести промокод", callback_data=CB_PROMO_ENTER)
    b.button(text="⬅️ Назад", callback_data=back_callback)
    b.adjust(1)
    return b.as_markup()


# =========================================================
# RENDER SCREENS
# =========================================================

def _format_subscription_until(until) -> str:
    if until is None:
        return "—"
    if hasattr(until, "strftime"):
        return until.strftime("%d.%m.%Y")
    return str(until)


async def render_main(bot, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Главный экран: только 3 кнопки (ТЗ правки). Защита/Отчёты — внутри Подключённые чаты."""
    async with await get_session() as session:
        user = await get_or_create_user(session, user_id)
        chats = await _managed_chats(session, user_id)
        t = (user.tariff or "free").lower()
        tariff_label = "PREMIUM" if t in ("premium", "pro", "business") else "FREE"
        sub_until = _format_subscription_until(user.subscription_until)
        txt = (
            "😈 *AntiSpam Guardian* на страже порядка.\n\n"
            "Я защищаю чаты от:\n"
            "• спама\n• рейдов\n• мусорных ссылок\n• ботов\n\n"
            f"Тариф: *{tariff_label}*\n"
            f"Подключено чатов: *{len(chats)} / {user.chat_limit}*\n"
            f"Подписка до: *{sub_until}*\n\n"
            "_Выберите действие:_"
        )
        return txt, _kb_main()


def _back_code(back_to: str, copy_mode: bool = False) -> str:
    """Код для пагинации списка чатов. copy_mode=True добавляет :copy для режима переноса настроек."""
    if back_to == CB_CHATS:
        return "c"
    if back_to == CB_CHATS_ALL:
        return "a"
    if back_to == CB_BACK_TO_CHAT:
        return "b" + (":copy" if copy_mode else "")
    return "m"


async def render_pick_chat(
    bot, user_id: int, page: int = 0, back_to: str = CB_MAIN, copy_mode: bool = False, exclude_chat_id: int | None = None
) -> InlineKeyboardMarkup:
    """Список чатов для выбора. copy_mode=True — кнопки ведут на CB_COPY_TARGET. exclude_chat_id — не показывать (для переноса)."""
    PAGE_SIZE = 10
    code = _back_code(back_to, copy_mode)
    prefix = CB_COPY_TARGET if copy_mode else CB_SET_CHAT

    async with await get_session() as session:
        chats = await _managed_chats(session, user_id)
    if exclude_chat_id is not None:
        chats = [c for c in chats if c.id != exclude_chat_id]

    b = InlineKeyboardBuilder()

    if not chats:
        b.button(text="➕ Подключить чат", callback_data=CB_CONNECT)
        b.button(text="⬅️ Назад", callback_data=back_to)
        b.adjust(1)
        return b.as_markup()

    total = len(chats)
    max_page = (total - 1) // PAGE_SIZE
    page = max(0, min(page, max_page))

    chunk = chats[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    titles_to_update: Dict[int, str] = {}

    for ch in chunk:
        title = (ch.title or "").strip()
        if not title:
            try:
                tg_chat = await bot.get_chat(ch.id)
                title = (tg_chat.title or "").strip() or str(ch.id)
                titles_to_update[ch.id] = title
            except Exception:
                title = str(ch.id)
        b.button(text=f"🛡 {title}", callback_data=f"{prefix}{ch.id}")

    if titles_to_update:
        async with await get_session() as session:
            for cid, t in titles_to_update.items():
                chat_row = await session.get(Chat, cid)
                if chat_row:
                    chat_row.title = t
            await session.commit()

    if max_page > 0:
        nav = InlineKeyboardBuilder()
        if page > 0:
            nav.button(text="⬅️", callback_data=f"{CB_CHAT_PAGE}{page-1}:{code}")
        nav.button(text=f"📄 {page+1}/{max_page+1}", callback_data="noop:0")
        if page < max_page:
            nav.button(text="➡️", callback_data=f"{CB_CHAT_PAGE}{page+1}:{code}")
        for btn_row in nav.export():
            for btn in btn_row:
                b.add(btn)

    b.button(text="⬅️ Назад", callback_data=back_to)
    b.adjust(1)
    return b.as_markup()


async def render_pick_reports_chat(bot, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Куда слать отчёты — только лог-чаты (где был /setlog)."""
    async with await get_session() as session:
        selected = await _get_selected_chat(session, user_id)
        if not selected:
            return "😈 Сначала выбери защищаемый чат.", _kb_back_to_main()

        log_chats = await _user_log_chats(session, user_id)
        if not log_chats:
            return (
                "😈 *Нет чатов отчётов.*\n\n"
                "Нажми *➕ Подключить чат отчётов* — выбери группу, куда слать отчёты.",
                _kb_back_to_main(),
            )

        chat_items = [(ch.id, (ch.title or "").strip() or str(ch.id)) for ch in log_chats]

    b = InlineKeyboardBuilder()
    b.button(text="🚫 Не слать отчёты (снять)", callback_data=CB_CLEAR_REPORTS_CHAT)

    for chat_id, title in chat_items:
        if title == str(chat_id):
            title = await _get_chat_title(bot, chat_id)
        b.button(text=f"📍 {title}", callback_data=f"{CB_SET_REPORTS_CHAT}{chat_id}")

    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
    b.adjust(1)
    return "🧾 *Сменить чат отчётов*\nВыбери, куда слать отчёты:", b.as_markup()


# Кэш chat_id, для которых уже отправили приветствие (защита от двойного my_chat_member)
_WELCOME_SENT_AT: Dict[int, float] = {}
_WELCOME_SENT_TTL = 60  # секунд


def _purge_old_welcome_sent() -> None:
    now = time.monotonic()
    to_del = [cid for cid, t in _WELCOME_SENT_AT.items() if now - t > _WELCOME_SENT_TTL]
    for cid in to_del:
        del _WELCOME_SENT_AT[cid]


async def connect_chat_after_bot_added(
    bot, chat_id: int, chat_title: str, user_id: int, username: str | None, first_name: str | None
) -> bool:
    """ТЗ ЧЕККК: после добавления бота как админа — подключить чат, приветствие в группу, сообщение в личку. Returns True если подключили."""
    # Защита от двойного приветствия: проверка в самом начале (до любых await)
    _purge_old_welcome_sent()
    if chat_id in _WELCOME_SENT_AT:
        return True
    try:
        already_connected = False
        async with await get_session() as session:
            await get_or_create_user(session, user_id, username=username, first_name=first_name)
            can_add, current_count, limit = await can_add_chat(session, user_id)
            if not can_add:
                try:
                    await bot.send_message(
                        user_id,
                        f"❌ Лимит чатов: {current_count} из {limit}. Повысь тариф: 💳 Тариф и оплата.",
                    )
                except Exception:
                    pass
                return False

            chat_row = await session.get(Chat, chat_id)
            rule = await session.get(Rule, chat_id)
            # Чат уже подключён (повторный my_chat_member) — не дублируем приветствие
            if chat_row and chat_row.is_active and rule is not None:
                already_connected = True
                chat_row.title = chat_title
                chat_row.owner_user_id = user_id
                await _set_selected_chat(session, user_id, chat_id)
                await session.commit()
                return True

            # Защита от гонки: только один поток отправляет приветствие (проверка + установка без await между ними)
            _purge_old_welcome_sent()
            if chat_id in _WELCOME_SENT_AT:
                return True
            _WELCOME_SENT_AT[chat_id] = time.monotonic()

            if not chat_row:
                chat_row = Chat(
                    id=chat_id,
                    title=chat_title,
                    owner_user_id=user_id,
                    is_active=True,
                    is_log_chat=False,
                )
                session.add(chat_row)
            else:
                chat_row.title = chat_title
                chat_row.owner_user_id = user_id
                chat_row.is_active = True
                chat_row.is_log_chat = False

            if not rule:
                rule = Rule(
                    chat_id=chat_id,
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

            await _set_selected_chat(session, user_id, chat_id)
            await session.commit()

        title_esc = (chat_title or "Чат").replace("*", "\\*")
        welcome = (
            "😈 AntiSpam Guardian на месте.\n\n"
            f"Группа *«{title_esc}»* теперь под защитой.\n\n"
            "Я слежу за порядком:\n• режу спам\n• давлю подозрительные ссылки\n"
            "• останавливаю мусор, рейды и лишний шум\n\n"
            "_Что важно:_\n1. Не спамить.\n2. Не кидать ссылки без необходимости.\n"
            "3. Не устраивать помойку в чате.\n4. Не лезть с враждой, оскорблениями и провокациями.\n\n"
            "Нормальным людям — спокойно общаться.\nСпамерам — будет больно.\n\n_Админ управляет защитой._"
        )
        await bot.send_message(chat_id, welcome, parse_mode="Markdown")

        me = await bot.get_me()
        panel_url = f"https://t.me/{me.username}?start=panel"
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        await bot.send_message(
            user_id,
            f"✅ *Группа подключена.*\n\nГруппа: *{title_esc}*\n\nНастрой защиту в панели.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙ Открыть настройки", url=panel_url)]
            ]),
        )
        return True
    except Exception:
        return False


async def render_chat_manage(bot, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Экран «Управление группой» для выбранного чата (Защита, Отчёты, Сменить чат)."""
    async with await get_session() as session:
        selected = await _get_selected_chat(session, user_id)
        if not selected:
            return await render_main(bot, user_id)
        chat_row = await session.get(Chat, selected)
    title = (getattr(chat_row, "title", None) or "").strip() if chat_row else ""
    if not title:
        title = await _get_chat_title(bot, selected)
    txt = (
        "😈 *Управление группой*\n\n"
        f"Группа: *{title}*\n\n"
        "_Что делаем?_"
    )
    return txt, _kb_chat_manage()


# =========================================================
# SHOW PANEL
# =========================================================

async def show_panel(bot, user_id: int) -> None:
    import logging
    logger = logging.getLogger(__name__)
    try:
        text, kb = await render_main(bot, user_id)
        await _edit_panel(bot, user_id, text, kb)
    except Exception as e:
        logger.exception("show_panel error: %s", e)
        try:
            err_text = str(e).lower()
            hint = ""
            if "users" in err_text or "is_log_chat" in err_text or "does not exist" in err_text:
                hint = "\n\n_Подсказка: если БД старая — выполни миграцию: migrations/001_add_user_and_is_log_chat.sql_"
            await bot.send_message(
                user_id,
                f"❌ Не удалось открыть панель.{hint}\n\nОшибка: {e!r}\n\nПопробуй /panel ещё раз.",
                parse_mode="Markdown",
            )
        except Exception:
            pass


# =========================================================
# COMMAND
# =========================================================

CMD_PRIVATE_ONLY = "Эта команда работает только в личном чате с ботом."


@router.message(Command("panel"))
async def panel_cmd(message: Message):
    if message.chat.type != "private":
        await message.answer("😈 Панель только в личке. Напиши */panel*.", parse_mode="Markdown")
        return
    if not message.from_user:
        return
    _cache_clear(message.from_user.id)
    await show_panel(message.bot, message.from_user.id)


# ТЗ: Меню команд Telegram (синяя кнопка) — /group, /groups, /buy, /support
@router.message(Command("group"))
async def cmd_group(message: Message):
    if message.chat.type != "private":
        await message.answer(CMD_PRIVATE_ONLY)
        return
    if not message.from_user:
        return
    _cache_clear(message.from_user.id)
    kb = await render_pick_chat(message.bot, message.from_user.id, page=0, back_to=CB_CHATS)
    txt = "😈 *Управление одной группой*\n\nВыбери группу:"
    await _edit_panel(message.bot, message.from_user.id, txt, kb)


@router.message(Command("groups"))
async def cmd_groups(message: Message):
    if message.chat.type != "private":
        await message.answer(CMD_PRIVATE_ONLY)
        return
    if not message.from_user:
        return
    _cache_clear(message.from_user.id)
    txt = (
        "🌐 *Управление всеми группами*\n\n"
        "Выбранные действия применятся ко всем подключённым чатам."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🛡 Защита для всех", callback_data="p:protection_all")
    kb.button(text="🧾 Отчёты для всех", callback_data="p:reports_all")
    kb.button(text="⬅️ Назад", callback_data=CB_MAIN)
    kb.adjust(1)
    await _edit_panel(message.bot, message.from_user.id, txt, kb.as_markup())


async def _send_premium_screen(bot, user_id: int, back_callback: str = CB_MAIN) -> None:
    """Показать экран Guardian Premium: описание + кнопки периодов подписки."""
    txt = CMD_PREMIUM_RESPONSE
    kb = _kb_premium_plans(back_callback=back_callback)
    await _edit_panel(bot, user_id, txt, kb)


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    if message.chat.type != "private":
        await message.answer(CMD_PRIVATE_ONLY)
        return
    if not message.from_user:
        return
    _cache_clear(message.from_user.id)
    await _send_premium_screen(message.bot, message.from_user.id)


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    """Команда /premium — тот же экран, что и тариф/подписка."""
    if message.chat.type != "private":
        return
    if not message.from_user:
        return
    _cache_clear(message.from_user.id)
    await _send_premium_screen(message.bot, message.from_user.id)


@router.message(
    F.chat.type == "private",
    F.text.func(lambda t: (t or "").strip().lower() == "тариф"),
)
async def cmd_text_tariff(message: Message):
    """Ответ на текст «тариф» — экран Guardian Premium."""
    if not message.from_user:
        return
    _cache_clear(message.from_user.id)
    await _send_premium_screen(message.bot, message.from_user.id)


async def _try_delete_quiet(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    Command(commands=["addantispam"], ignore_mention=True),
    F.reply_to_message,
)
async def cmd_addantispam_group(message: Message):
    """В группе: ответьте на сообщение пользователя и отправьте /addantispam — автор будет добавлен в антиспам базу."""
    if not message.from_user or not message.reply_to_message or not message.reply_to_message.from_user:
        return
    target = message.reply_to_message.from_user
    if target.is_bot:
        await message.reply("Добавлять ботов в антиспам базу нельзя.")
        return
    try:
        mem = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    except TelegramBadRequest:
        await message.reply("Не удалось проверить ваши права в группе. Проверьте, что бот — администратор.")
        return
    except Exception as e:
        await message.reply(f"Не удалось выполнить команду: {e}")
        return

    if mem.status == ChatMemberStatus.CREATOR:
        pass
    elif mem.status == ChatMemberStatus.ADMINISTRATOR:
        if not getattr(mem, "can_restrict_members", False):
            await message.reply(
                "Добавлять в антиспам базу могут только администраторы с правом *ограничивать участников*.",
                parse_mode="Markdown",
            )
            return
    else:
        await message.reply("Только *администратор* группы может добавить пользователя в антиспам базу.", parse_mode="Markdown")
        return

    from app.api.service import user_can_access_chat
    from app.services.global_antispam import add_to_global_antispam
    async with await get_session() as session:
        if not await user_can_access_chat(session, message.from_user.id, message.chat.id):
            await message.reply("Эта группа не подключена к вашему аккаунту. Управление — в боте в личке.")
            return
        added = await add_to_global_antispam(session, target.id, reason=f"из группы {message.chat.id}")
    if added:
        bot_reply = await message.reply(
            f"✅ Пользователь {target.id} добавлен в антиспам базу. При включённой проверке он будет исключаться при входе в ваши группы."
        )
        await _try_delete_quiet(message.bot, message.chat.id, message.message_id)
        await _try_delete_quiet(message.bot, bot_reply.chat.id, bot_reply.message_id)
    else:
        await message.reply(f"Пользователь {target.id} уже был в антиспам базе.")


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    Command(commands=["addantispam"], ignore_mention=True),
    ~F.reply_to_message,
)
async def cmd_addantispam_group_no_reply(message: Message):
    """Подсказка, если /addantispam без ответа на сообщение."""
    await message.reply(
        "Чтобы добавить пользователя в *антиспам базу*, ответьте *на его сообщение* в группе "
        "и отправьте команду /addantispam.\n\n"
        "Команду может использовать только *администратор* группы, подключённой к боту.",
        parse_mode="Markdown",
    )


@router.message(Command("support"))
async def cmd_support(message: Message):
    if message.chat.type != "private":
        await message.answer(CMD_PRIVATE_ONLY)
        return
    txt = (
        "😈 *AntiSpam Guardian* слушает.\n\n"
        "Контакт техподдержки: @pastukh_viscera\n\n"
        "_Перед тем как писать:_\n"
        "• убедитесь, что вопрос нельзя решить через панель\n"
        "• опишите проблему сразу подробно\n"
        "• по возможности приложите скриншот\n\n"
        "Сообщения вида «Привет» / «Не работает» игнорируются."
    )
    await message.answer(txt, parse_mode="Markdown")


# =========================================================
# CALLBACKS: NAV
# =========================================================

@router.callback_query(F.data == "noop:0")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data == CB_MAIN)
async def cb_main(cb: CallbackQuery):
    await cb.answer()
    await show_panel(cb.bot, cb.from_user.id)


async def _render_protection_screen(bot, user_id: int, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура экрана Защита: перечислены все текущие настройки раздела."""
    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
        rule = await _get_or_create_rule(session, chat_id)
        # количество стоп-слов для чата
        r = await session.execute(select(func.count()).select_from(StopWord).where(StopWord.chat_id == chat_id))
        stopwords_count = r.scalar() or 0

    title = (getattr(chat_row, "title", None) or "").strip() if chat_row else str(chat_id)
    if not title:
        title = await _get_chat_title(bot, chat_id)

    # Текущие значения настроек раздела «Защита»
    cap_first = "ВКЛ" if getattr(rule, "first_message_captcha_enabled", False) else "ВЫКЛ"
    links_mode = _get_filter_links_mode(rule)
    links_label = _filter_policy_label(links_mode)
    media_mode = getattr(rule, "filter_media_mode", "allow")
    media_label = _filter_policy_label(media_mode)
    buttons_mode = getattr(rule, "filter_buttons_mode", "allow")
    buttons_label = _filter_policy_label(buttons_mode)
    all_captcha_m = getattr(rule, "all_captcha_minutes", 0) or 0
    all_captcha = "ВЫКЛ" if all_captcha_m == 0 else f"на {all_captcha_m} мин"
    join_msg = "Удалять" if getattr(rule, "delete_join_messages", True) else "Оставлять"
    silence_m = getattr(rule, "silence_minutes", 0) or 0
    silence = "ВЫКЛ" if silence_m == 0 else f"{silence_m} мин"
    anti_spam = "ВКЛ" if getattr(rule, "master_anti_spam", True) else "ВЫКЛ"
    punish_mode = _human_mode(getattr(rule, "action_mode", "delete"))
    mute_m = int(rule.mute_minutes or 30)
    newbie_on = "ВКЛ" if rule.newbie_enabled else "ВЫКЛ"
    newbie_m = int(rule.newbie_minutes or 10)
    stopwords_str = f"{stopwords_count} слов" if stopwords_count else "не настроены"
    guardian = "ВКЛ" if getattr(rule, "guardian_messages_enabled", True) else "ВЫКЛ"
    every_n = getattr(rule, "public_alerts_every_n", 5)
    interval_sec = getattr(rule, "public_alerts_min_interval_sec", 300)
    interval_min = interval_sec // 60

    txt = (
        f"🛡 *Защита*\n\nЧат: *{title}*\n\n"
        "*Текущие настройки раздела:*\n"
        f"• 🔗 Ссылки: *{links_label}*\n"
        f"• 🖼 Медиа / стикеры: *{media_label}*\n"
        f"• 🔘 Кнопки: *{buttons_label}*\n"
        f"• 👥 Сообщения «вступил в группу»: *{join_msg}*\n"
        f"• 🔇 Режим тишины: *{silence}*\n"
        f"• 🛡 Защита от спама: *{anti_spam}*\n"
        f"• 😈 Наказания: *{punish_mode}*, мут *{mute_m}* мин\n"
        f"• 👶 Новички: *{newbie_on}*, окно *{newbie_m}* мин\n"
        f"• 🧠 Стоп-слова: *{stopwords_str}*\n"
        f"• 📢 Guardian сообщения: *{guardian}*, раз в *{every_n}* удалений, интервал *{interval_min}* мин\n"
        "• 🚨 Анти-рейд: Guardian Premium\n"
        f"• 📈 Антинакрутка: *{'ВКЛ' if getattr(rule, 'antinakrutka_enabled', False) else 'ВЫКЛ'}*\n"
        f"• 📋 Антиспам база (при входе): *{'ВКЛ' if getattr(rule, 'use_global_antispam_db', False) else 'ВЫКЛ'}*\n"
        f"• 🚫 Фильтр мата: *{'ВКЛ' if getattr(rule, 'filter_profanity_enabled', False) else 'ВЫКЛ'}*\n\n"
        "_Выберите пункт ниже для изменения._"
    )
    return txt, _kb_protection()


@router.callback_query(F.data == CB_PROTECTION)
async def cb_protection(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    txt, kb = await _render_protection_screen(cb.bot, cb.from_user.id, chat_id)
    await _edit_or_send(cb, txt, kb)


@router.callback_query(F.data == CB_BACK_TO_PROTECTION)
async def cb_back_to_protection(cb: CallbackQuery):
    """ТЗ доработка: из любого подраздела Защиты Назад ведёт в экран Защита."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    txt, kb = await _render_protection_screen(cb.bot, cb.from_user.id, chat_id)
    await _edit_or_send(cb, txt, kb)


@router.callback_query(F.data == CB_CAPTCHA_FIRST)
async def cb_captcha_first(cb: CallbackQuery):
    """🧩 Капча на первое сообщение — ТЗ доработка Защита."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_off = "ВКЛ" if getattr(rule, "first_message_captcha_enabled", False) else "ВЫКЛ"
    txt = f"🧩 *Капча на первое сообщение*\n\nТекущее состояние: *{on_off}*"
    b = InlineKeyboardBuilder()
    b.button(text="✅ Включить", callback_data=CB_CAPTCHA_FIRST_ON)
    b.button(text="❌ Отключить", callback_data=CB_CAPTCHA_FIRST_OFF)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(2, 1)
    await _edit_or_send(cb, txt, b.as_markup())


@router.callback_query(F.data == CB_CAPTCHA_FIRST_ON)
async def cb_captcha_first_on(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.first_message_captcha_enabled = True
        await session.commit()
    await cb_captcha_first(cb)


@router.callback_query(F.data == CB_CAPTCHA_FIRST_OFF)
async def cb_captcha_first_off(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.first_message_captcha_enabled = False
        await session.commit()
    await cb_captcha_first(cb)


@router.callback_query(F.data == CB_RAID)
async def cb_raid(cb: CallbackQuery):
    await cb.answer()
    txt = "🚨 *Анти-рейд*\n\n" + PREMIUM_FEATURE_BLOCK
    await _edit_or_send(cb, txt, _kb_raid_stub())


@router.callback_query(F.data == CB_ANTINAKRUTKA)
async def cb_antinakrutka(cb: CallbackQuery):
    """📈 Антинакрутка: оповещение и реакция на массовый вход."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_off = "ВКЛ" if getattr(rule, "antinakrutka_enabled", False) else "ВЫКЛ"
    th = int(getattr(rule, "antinakrutka_joins_threshold", 10) or 10)
    win = int(getattr(rule, "antinakrutka_window_minutes", 5) or 5)
    act = getattr(rule, "antinakrutka_action", "alert") or "alert"
    rmin = int(getattr(rule, "antinakrutka_restrict_minutes", 30) or 30)
    mute_line = f"Мут при рейде: *{rmin}* мин\n" if act == "alert_restrict" else ""
    txt = (
        "📈 *Антинакрутка*\n\n"
        "Оповещение и реакция на массовый вход в группу или чат комментариев канала.\n\n"
        f"Состояние: *{on_off}*\n"
        f"Порог: *{th}* участников за *{win}* мин\n"
        f"Действие: *{'оповещение + мут' if act == 'alert_restrict' else 'только оповещение'}*\n"
        f"{mute_line}\n"
        "_Выберите параметры ниже._"
    )
    await _edit_or_send(cb, txt, _kb_antinakrutka(rule))


@router.callback_query(F.data == CB_ANTINAKRUTKA_TOGGLE)
async def cb_antinakrutka_toggle(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.antinakrutka_enabled = not getattr(rule, "antinakrutka_enabled", False)
        await session.commit()
    await cb_antinakrutka(cb)


@router.callback_query(F.data.startswith(CB_ANTINAKRUTKA_THRESH))
@router.callback_query(F.data.startswith(CB_ANTINAKRUTKA_WINDOW))
@router.callback_query(F.data.startswith(CB_ANTINAKRUTKA_ACTION))
@router.callback_query(F.data.startswith(CB_ANTINAKRUTKA_RESTRICT))
async def cb_antinakrutka_set(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    data = cb.data
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        if CB_ANTINAKRUTKA_THRESH in data:
            try:
                n = int(data.split(":")[-1])
                rule.antinakrutka_joins_threshold = max(2, min(100, n))
            except (ValueError, IndexError):
                pass
        elif CB_ANTINAKRUTKA_WINDOW in data:
            try:
                n = int(data.split(":")[-1])
                rule.antinakrutka_window_minutes = max(1, min(60, n))
            except (ValueError, IndexError):
                pass
        elif CB_ANTINAKRUTKA_ACTION in data:
            val = "alert_restrict" if "alert_restrict" in data else "alert"
            rule.antinakrutka_action = val
        elif CB_ANTINAKRUTKA_RESTRICT in data:
            try:
                n = int(data.split(":")[-1])
                rule.antinakrutka_restrict_minutes = max(1, min(1440, n))
            except (ValueError, IndexError):
                pass
        await session.commit()
    await cb_antinakrutka(cb)


@router.callback_query(F.data == CB_PUBLIC_ALERTS)
async def cb_public_alerts(cb: CallbackQuery):
    """📢 Guardian сообщения (ТЗ Напоминания): вкл/выкл + раз в N удалений, не чаще 72ч/30мин."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_off = "ВКЛ" if getattr(rule, "guardian_messages_enabled", True) else "ВЫКЛ"
    every = getattr(rule, "public_alerts_every_n", 5)
    interval_sec = getattr(rule, "public_alerts_min_interval_sec", 300)
    interval_min = interval_sec // 60
    txt = (
        "📢 *Guardian сообщения*\n\n"
        f"Сейчас: *{on_off}*\n"
        f"После каждых *{every}* удалений — короткая реплика в чат.\n"
        f"Минимальный интервал: *{interval_min}* мин\n"
        f"Раз в 3 дня — сообщение в группе (если чат активен).\n\n"
        "_По умолчанию включены. Можно отключить._"
    )
    await _edit_or_send(cb, txt, _kb_public_alerts(rule))


@router.callback_query(F.data == CB_PUBLIC_ALERTS_ON)
async def cb_public_alerts_on(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.guardian_messages_enabled = True
        rule.public_alerts_enabled = True
        await session.commit()
    txt = "📢 Guardian сообщения: *ВКЛ*. Раз в N удалений — реплика в чат; раз в 3 дня — сообщение в группе."
    await _edit_or_send(cb, txt, _kb_public_alerts(rule))


@router.callback_query(F.data == CB_PUBLIC_ALERTS_OFF)
async def cb_public_alerts_off(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.guardian_messages_enabled = False
        rule.public_alerts_enabled = False
        await session.commit()
    txt = "📢 Guardian сообщения: *ВЫКЛ*. Сообщения в группе и после удалений отключены."
    await _edit_or_send(cb, txt, _kb_public_alerts(rule))


@router.callback_query(F.data.startswith("p:pa_every:"))
async def cb_public_alerts_every(cb: CallbackQuery):
    await cb.answer()
    try:
        n = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        n = 5
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.public_alerts_every_n = n
        await session.commit()
    on_off = "ВКЛ" if getattr(rule, "guardian_messages_enabled", True) else "ВЫКЛ"
    txt = f"📢 Частота: каждые *{n}* удалений. Guardian сообщения: *{on_off}*."
    await _edit_or_send(cb, txt, _kb_public_alerts(rule))


@router.callback_query(F.data.startswith("p:pa_int:"))
async def cb_public_alerts_interval(cb: CallbackQuery):
    await cb.answer()
    try:
        sec = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        sec = 300
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.public_alerts_min_interval_sec = sec
        await session.commit()
    min_val = sec // 60
    txt = f"📢 Минимальный интервал между сообщениями: *{min_val}* мин."
    await _edit_or_send(cb, txt, _kb_public_alerts(rule))


@router.callback_query(F.data == CB_BILLING)
async def cb_billing(cb: CallbackQuery):
    await cb.answer()
    async with await get_session() as session:
        user = await get_or_create_user(session, cb.from_user.id)
        count = len(await _managed_chats(session, cb.from_user.id))
    t = (user.tariff or "free").lower()
    tariff_label = "PREMIUM" if t in ("premium", "pro", "business") else "FREE"
    sub_until = _format_subscription_until(user.subscription_until)
    limit = user.chat_limit
    txt = (
        "🛡 *Guardian Premium*\n\n"
        f"Тариф: *{tariff_label}*\n"
        f"Подключено чатов: *{count} / {limit}*\n"
        f"Подписка до: *{sub_until}*\n\n"
        + PREMIUM_DESCRIPTION
    )
    kb = _kb_premium_plans(back_callback=CB_MAIN)
    await _edit_or_send(cb, txt, kb)


@router.callback_query(F.data == CB_PROMO_ENTER)
async def cb_promo_enter(cb: CallbackQuery):
    """Запрос ввода промокода (Premium / тест на 3 дня)."""
    await cb.answer()
    _pending_promo[cb.from_user.id] = True
    await cb.message.answer(
        "🎁 Отправь *промокод* одним сообщением (например TRIAL3 для теста Premium на 3 дня). Отмена: /cancel",
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith(CB_PLAN))
async def cb_plan_select(cb: CallbackQuery):
    """Выбор периода подписки (1, 3, 6, 12, 24 мес). Пока заглушка оплаты."""
    await cb.answer()
    if cb.data == CB_PLAN_COMPARE:
        await _send_premium_screen(cb.bot, cb.from_user.id)
        return
    try:
        months = int(cb.data.replace(CB_PLAN, ""))
    except ValueError:
        return
    plan_label = next((p[1].split("\n")[0] for p in PREMIUM_PLANS if p[0] == months), f"{months} мес")
    txt = (
        f"💳 *{plan_label}*\n\n"
        "Оплата будет подключена в следующей версии.\n"
        "Сейчас можно оформить подписку через @pastukh_viscera."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ К тарифам", callback_data=CB_BILLING)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == CB_CHATS)
async def cb_chats_menu(cb: CallbackQuery):
    """Подключённые чаты: выбор режима — одна группа / все группы (ТЗ правки)."""
    await cb.answer()
    txt = "📂 *Подключённые чаты*\n\nВыбери режим:"
    await _edit_or_send(cb, txt, _kb_chats_modes())


@router.callback_query(F.data == CB_CHATS_ONE)
async def cb_chats_one(cb: CallbackQuery):
    """Управление одной группой: список чатов, Back → выбор режима."""
    await cb.answer()
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_CHATS)
    await _edit_or_send(cb, "😈 *Управление одной группой*\n\nВыбери чат:", kb)


@router.callback_query(F.data == CB_CHATS_ALL)
async def cb_chats_all(cb: CallbackQuery):
    """Управление всеми группами: выбор чата для защиты или отчётов."""
    await cb.answer()
    txt = (
        "🌐 *Управление всеми группами*\n\n"
        "Выбери действие — откроется список чатов для настройки."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🛡 Защита для всех", callback_data="p:protection_all")
    kb.button(text="🧾 Отчёты для всех", callback_data="p:reports_all")
    kb.button(text="⬅️ Назад", callback_data=CB_CHATS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == "p:protection_all")
async def cb_protection_all(cb: CallbackQuery):
    """Защита для всех: выбор чата из списка → экран управления защитой."""
    await cb.answer()
    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
    if not chats:
        txt = "🛡 Нет подключённых чатов. Добавь бота в группу и подключи её в разделе *Подключить группу*."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data=CB_CHATS_ALL)
        kb.adjust(1)
        await _edit_or_send(cb, txt, kb.as_markup())
        return
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_CHATS_ALL)
    await _edit_or_send(cb, "🛡 *Защита для всех*\n\nВыбери чат для настройки защиты:", kb)


@router.callback_query(F.data == "p:reports_all")
async def cb_reports_all(cb: CallbackQuery):
    """Отчёты для всех: выбор чата из списка → экран отчётов для этого чата."""
    await cb.answer()
    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
    if not chats:
        txt = "🧾 Нет подключённых чатов. Добавь бота в группу и подключи её в разделе *Подключить группу*."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data=CB_CHATS_ALL)
        kb.adjust(1)
        await _edit_or_send(cb, txt, kb.as_markup())
        return
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_CHATS_ALL)
    await _edit_or_send(cb, "🧾 *Отчёты для всех*\n\nВыбери чат для настройки отчётов:", kb)


@router.callback_query(F.data == CB_CHATS_LIST)
async def cb_chats_list(cb: CallbackQuery):
    await cb.answer()
    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
    if not chats:
        txt = "🛡 *Подключённые чаты*\n\nПока нет. Жми *➕ Подключить чат* в главном меню."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data=CB_CHATS)
        kb.adjust(1)
        await _edit_or_send(cb, txt, kb.as_markup())
        return
    lines = [f"• { (c.title or '').strip() or str(c.id) }" for c in chats[:50]]
    txt = "🛡 *Подключённые чаты*\n\n" + "\n".join(lines)
    if len(chats) > 50:
        txt += f"\n…и ещё {len(chats) - 50}"
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=CB_CHATS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == CB_CHATS_LOGS)
async def cb_chats_logs(cb: CallbackQuery):
    await cb.answer()
    async with await get_session() as session:
        log_chats = await _user_log_chats(session, cb.from_user.id)
    if not log_chats:
        txt = (
            "📍 *Лог-чаты*\n\n"
            "Пока нет. Чтобы добавить:\n"
            "1) Создай группу для логов\n"
            "2) Добавь бота, дай права\n"
            "3) В той группе напиши: /setlog"
        )
    else:
        lines = [f"• {(c.title or '').strip() or str(c.id)}" for c in log_chats[:50]]
        txt = "📍 *Лог-чаты*\n\n" + "\n".join(lines)
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=CB_CHATS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == CB_PICK_CHAT)
async def cb_pick_chat(cb: CallbackQuery):
    """Сменить чат — список с возвратом в «Управление группой»."""
    await cb.answer()
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_BACK_TO_CHAT)
    await _edit_or_send(cb, "😈 *Сменить чат*\nВыбери чат:", kb)


@router.callback_query(F.data.startswith(CB_CHAT_PAGE))
async def cb_chat_page(cb: CallbackQuery):
    await cb.answer()
    rest = cb.data[len(CB_CHAT_PAGE):].strip()
    parts = rest.split(":")
    try:
        page = int(parts[0]) if parts else 0
    except (ValueError, IndexError):
        page = 0
    code = ":".join(parts[1:]) if len(parts) > 1 else "m"
    copy_mode = "copy" in code
    if code.startswith("c"):
        back_to = CB_CHATS
    elif code.startswith("a"):
        back_to = CB_CHATS_ALL
    elif code.startswith("b"):
        back_to = CB_BACK_TO_CHAT
    else:
        back_to = CB_MAIN
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=page, back_to=back_to, copy_mode=copy_mode)
    msg_text = cb.message.text or "😈 *Выбор чата*\nВыбери, кого защищаем:"
    await _edit_or_send(cb, msg_text, kb)


@router.callback_query(F.data.startswith(CB_SET_CHAT))
async def cb_set_chat(cb: CallbackQuery):
    """Выбор чата из списка → экран «Управление группой» (ТЗ правки)."""
    await cb.answer()
    try:
        chat_id = int(cb.data.split(":")[-1])
    except Exception:
        await cb.answer("Кривые данные 😈", show_alert=True)
        return

    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
        if chat_id not in {c.id for c in chats}:
            await cb.answer("Не твой чат. Не трогай 😈", show_alert=True)
            return
        await _set_selected_chat(session, cb.from_user.id, chat_id)

    text, kb = await render_chat_manage(cb.bot, cb.from_user.id)
    await _edit_or_send(cb, text, kb)


@router.callback_query(F.data == CB_CLEAN_DELETED)
async def cb_clean_deleted(cb: CallbackQuery):
    """Очистка группы от удалённых аккаунтов."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    from app.services.chat_cleanup import clean_deleted_accounts
    try:
        async with await get_session() as session:
            kicked, checked = await clean_deleted_accounts(cb.bot, session, chat_id)
        title = await _get_chat_title(cb.bot, chat_id)
        text = (
            f"🧹 *Очистка от удалённых*\n\n"
            f"Чат: *{title}*\n"
            f"Проверено участников: *{checked}*\n"
            f"Исключено удалённых аккаунтов: *{kicked}*"
        )
    except Exception as e:
        text = f"😈 Ошибка при очистке: {e}"
    await _edit_or_send(cb, text, _kb_chat_manage())


@router.callback_query(F.data == CB_GLOBAL_ANTISPAM)
async def cb_global_antispam(cb: CallbackQuery):
    """Экран антиспам базы: переключатель использования в чате + список + добавить."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    from app.services.global_antispam import list_global_antispam, is_in_global_antispam
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        use_db = bool(getattr(rule, "use_global_antispam_db", False))
        items = await list_global_antispam(session, limit=30)
    on_off = "ВКЛ" if use_db else "ВЫКЛ"
    txt = (
        f"📋 *Антиспам база*\n\n"
        f"Общая база пользователей по всем группам бота. При включении проверка при *вступлении* в этот чат.\n\n"
        f"• Использовать в этом чате: *{on_off}*\n"
        f"• Записей в базе: *{len(items)}*\n\n"
        f"_Как добавить без ID:_ в группе ответьте на сообщение пользователя и отправьте /addantispam — бот добавит его в базу."
    )
    if items:
        lines = []
        for i, row in enumerate(items[:15], 1):
            uid = row.get("user_id", "")
            reason = (row.get("reason") or "").strip() or "—"
            lines.append(f"  {i}. `{uid}` — {reason[:40]}")
        txt += "\n\n" + "\n".join(lines)
    b = InlineKeyboardBuilder()
    b.button(text=f"{'❌ Выключить' if use_db else '✅ Включить'} в этом чате", callback_data=CB_GLOBAL_ANTISPAM_TOGGLE)
    b.button(text="➕ Добавить по ID", callback_data=CB_GLOBAL_ANTISPAM_ADD)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
    b.adjust(1)
    await _edit_or_send(cb, txt, b.as_markup())


@router.callback_query(F.data == CB_GLOBAL_ANTISPAM_TOGGLE)
async def cb_global_antispam_toggle(cb: CallbackQuery):
    """Вкл/выкл использование глобальной антиспам базы в выбранном чате."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.use_global_antispam_db = not getattr(rule, "use_global_antispam_db", False)
        await session.commit()
    await cb_global_antispam(cb)


@router.callback_query(F.data == CB_GLOBAL_ANTISPAM_ADD)
async def cb_global_antispam_add(cb: CallbackQuery):
    """Запросить ввод user_id для добавления в антиспам базу."""
    await cb.answer()
    _pending_antispam_add[cb.from_user.id] = True
    await cb.message.answer(
        "📋 Отправь *user_id* (число) пользователя для добавления в антиспам базу.\n"
        "Например: `123456789`\n\n"
        "Либо в группе: ответь на сообщение пользователя и отправь /addantispam — бот добавит его по автору ответа.\n"
        "Отмена: /cancel",
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith(CB_COPY_TARGET))
async def cb_copy_target(cb: CallbackQuery):
    """Перенос настроек: выбран целевой чат."""
    await cb.answer()
    raw = cb.data[len(CB_COPY_TARGET):].strip()
    if not raw:
        return
    try:
        target_chat_id = int(raw)
    except ValueError:
        return
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id or chat_id == target_chat_id:
        await cb.answer("Выбери другой чат как цель.", show_alert=True)
        return
    from app.api.service import user_can_access_chat, copy_rule_to_chat
    async with await get_session() as session:
        ok = await user_can_access_chat(session, cb.from_user.id, target_chat_id)
        if not ok:
            await cb.answer("Нет доступа к целевому чату.", show_alert=True)
            return
        try:
            await copy_rule_to_chat(session, chat_id, target_chat_id)
        except ValueError as e:
            await cb.answer(str(e), show_alert=True)
            return
    title_src = await _get_chat_title(cb.bot, chat_id)
    title_dst = await _get_chat_title(cb.bot, target_chat_id)
    text = f"📤 *Настройки перенесены*\n\nИз *{title_src}* в *{title_dst}*."
    await _edit_or_send(cb, text, _kb_chat_manage())


@router.callback_query(F.data == CB_PROFANITY)
async def cb_profanity(cb: CallbackQuery):
    """Экран «Фильтр мата»: вкл/выкл в чате, список слов, добавить."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    from app.api.service import list_profanity
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        use_prof = bool(getattr(rule, "filter_profanity_enabled", False))
        items = await list_profanity(session, limit=25)
    txt = (
        f"🚫 *Фильтр мата*\n\n"
        f"Сообщения с матерными словами из списка удаляются или наказываются по правилам чата.\n\n"
        f"• В этом чате: *{'ВКЛ' if use_prof else 'ВЫКЛ'}*\n"
        f"• Слов в базе: *{len(items)}*"
    )
    words_list = [str((row.get("word") or "").strip()) for row in items if (row.get("word") or "").strip()]
    _profanity_list_cache[cb.from_user.id] = words_list
    if words_list:
        lines = [f"  • `{w}`" for w in words_list[:15]]
        txt += "\n\n" + "\n".join(lines)
    b = InlineKeyboardBuilder()
    b.button(text=f"{'❌ Выключить' if use_prof else '✅ Включить'} в этом чате", callback_data=CB_PROFANITY_TOGGLE)
    b.button(text="➕ Добавить слово", callback_data=CB_PROFANITY_ADD)
    for i, w in enumerate(words_list[:10]):
        b.button(text=f"🗑 {w[:18]}", callback_data=f"{CB_PROFANITY_DEL}{i}")
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
    b.adjust(1)
    await _edit_or_send(cb, txt, b.as_markup())


@router.callback_query(F.data == CB_PROFANITY_TOGGLE)
async def cb_profanity_toggle(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.filter_profanity_enabled = not getattr(rule, "filter_profanity_enabled", False)
        await session.commit()
    await cb_profanity(cb)


@router.callback_query(F.data == CB_PROFANITY_ADD)
async def cb_profanity_add(cb: CallbackQuery):
    await cb.answer()
    _pending_profanity_add[cb.from_user.id] = True
    await cb.message.answer(
        "🚫 Отправь *слово* для добавления в фильтр мата (одним сообщением). Отмена: /cancel",
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith(CB_PROFANITY_DEL))
async def cb_profanity_del(cb: CallbackQuery):
    await cb.answer()
    raw = cb.data[len(CB_PROFANITY_DEL):].strip()
    try:
        idx = int(raw)
    except ValueError:
        return
    words_list = _profanity_list_cache.get(cb.from_user.id, [])
    if idx < 0 or idx >= len(words_list):
        await cb_profanity(cb)
        return
    word = words_list[idx]
    from app.api.service import remove_profanity
    async with await get_session() as session:
        removed = await remove_profanity(session, word)
    if removed:
        await cb.answer("Слово удалено из фильтра", show_alert=True)
    await cb_profanity(cb)


@router.callback_query(F.data == CB_COPY_SETTINGS)
async def cb_copy_settings(cb: CallbackQuery):
    """Перенести настройки: выбор целевого чата."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    title = await _get_chat_title(cb.bot, chat_id)
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_BACK_TO_CHAT, copy_mode=True, exclude_chat_id=chat_id)
    await _edit_or_send(
        cb,
        f"📤 *Перенос настроек*\n\nВыбери чат, *в который* перенести настройки из *{title}*:",
        kb,
    )


@router.callback_query(F.data == CB_BACK_TO_CHAT)
async def cb_back_to_chat(cb: CallbackQuery):
    """Назад к экрану «Управление группой» для выбранного чата."""
    await cb.answer()
    text, kb = await render_chat_manage(cb.bot, cb.from_user.id)
    await _edit_or_send(cb, text, kb)


# =========================================================
# CALLBACKS: SECTIONS
# =========================================================

@router.callback_query(F.data == CB_FILTERS)
async def cb_filters(cb: CallbackQuery):
    """ТЗ доработка: главный экран Фильтры — подпункты, Назад → Защита."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    title = ""
    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
        title = (getattr(chat_row, "title", None) or "").strip() if chat_row else ""
    if not title:
        title = await _get_chat_title(cb.bot, chat_id)
    txt = (
        f"⚙ *Фильтры группы «{title}»*\n\n"
        "Здесь настраиваются основные ограничения:\n"
        "• ссылки\n• медиа\n• кнопки\n• капча для всех сообщений\n"
        "• системные сообщения о входе\n• режим тишины\n• защита от спама"
    )
    await _edit_or_send(cb, txt, _kb_filters_main(rule, title))


def _get_filter_links_mode(rule: Rule) -> str:
    mode = getattr(rule, "filter_links_mode", None)
    if mode in ("allow", "captcha", "forbid"):
        return mode
    return "forbid" if rule.filter_links else "allow"


@router.callback_query(F.data == CB_FILTER_LINKS)
async def cb_filter_links(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mode = _get_filter_links_mode(rule)
    txt = f"🔗 *Ссылки*\n\nТекущее состояние: *{_filter_policy_label(mode)}*"
    await _edit_or_send(cb, txt, _kb_filter_policy(rule, "links"))


@router.callback_query(F.data == CB_FILTER_MEDIA)
async def cb_filter_media(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mode = getattr(rule, "filter_media_mode", "allow")
    txt = f"🖼 *Медиа / стикеры*\n\nТекущее состояние: *{_filter_policy_label(mode)}*"
    await _edit_or_send(cb, txt, _kb_filter_policy(rule, "media"))


@router.callback_query(F.data == CB_FILTER_BUTTONS)
async def cb_filter_buttons(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mode = getattr(rule, "filter_buttons_mode", "allow")
    txt = f"🔘 *Сообщения с кнопками*\n\nТекущее состояние: *{_filter_policy_label(mode)}*"
    await _edit_or_send(cb, txt, _kb_filter_policy(rule, "buttons"))


@router.callback_query(F.data.startswith(CB_FILTER_SET))
async def cb_filter_set_policy(cb: CallbackQuery):
    await cb.answer()
    parts = cb.data.split(":")
    if len(parts) < 4:
        return
    mode, key = parts[2], parts[3]
    if mode not in ("allow", "captcha", "forbid") or key not in ("links", "media", "buttons"):
        return
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        if key == "links":
            rule.filter_links_mode = mode
            rule.filter_links = mode == "forbid"
        elif key == "media":
            rule.filter_media_mode = mode
        else:
            rule.filter_buttons_mode = mode
        await session.commit()
    if key == "links":
        await cb_filter_links(cb)
    elif key == "media":
        await cb_filter_media(cb)
    else:
        await cb_filter_buttons(cb)


@router.callback_query(F.data == CB_FILTER_ALL_CAPTCHA)
async def cb_filter_all_captcha(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mins = getattr(rule, "all_captcha_minutes", 0) or 0
    state = "ВЫКЛ" if mins == 0 else f"включена на {mins} мин"
    txt = f"🧩 *Проверка всех сообщений капчей*\n\nТекущее состояние: *{state}*"
    await _edit_or_send(cb, txt, _kb_filter_all_captcha(rule))


@router.callback_query(F.data.startswith(CB_FILTER_ALL_CAPTCHA_TIME))
async def cb_filter_all_captcha_time(cb: CallbackQuery):
    await cb.answer()
    try:
        mins = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        mins = 0
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.all_captcha_minutes = max(0, mins)
        await session.commit()
    await cb_filter_all_captcha(cb)


@router.callback_query(F.data == CB_FILTER_JOIN_MSG)
async def cb_filter_join_msg(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    delete_ = getattr(rule, "delete_join_messages", True)
    state = "УДАЛЯЮ" if delete_ else "ОСТАВЛЯЮ"
    txt = f"👥 *Служебные сообщения о входе в группу*\n\nТекущее состояние: *{state}*"
    await _edit_or_send(cb, txt, _kb_filter_join(rule))


@router.callback_query(F.data.startswith(CB_FILTER_JOIN_TOGGLE))
async def cb_filter_join_toggle(cb: CallbackQuery):
    await cb.answer()
    try:
        val = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        val = 1
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.delete_join_messages = bool(val)
        await session.commit()
    await cb_filter_join_msg(cb)


@router.callback_query(F.data == CB_FILTER_SILENCE)
async def cb_filter_silence(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mins = getattr(rule, "silence_minutes", 0) or 0
    state = "ВЫКЛ" if mins == 0 else f"включён на {mins} мин"
    txt = f"🔇 *Режим тишины*\n\nТекущее состояние: *{state}*"
    await _edit_or_send(cb, txt, _kb_filter_silence(rule))


@router.callback_query(F.data.startswith(CB_FILTER_SILENCE_TIME))
async def cb_filter_silence_time(cb: CallbackQuery):
    await cb.answer()
    try:
        mins = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        mins = 0
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.silence_minutes = max(0, mins)
        await session.commit()
    await cb_filter_silence(cb)


@router.callback_query(F.data == CB_FILTER_SPAM)
async def cb_filter_spam(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_ = getattr(rule, "master_anti_spam", True)
    state = "ВКЛ" if on_ else "ВЫКЛ"
    txt = f"🛡 *Защита от спама*\n\nТекущее состояние: *{state}*"
    await _edit_or_send(cb, txt, _kb_filter_spam(rule))


@router.callback_query(F.data.startswith(CB_FILTER_SPAM_TOGGLE))
async def cb_filter_spam_toggle(cb: CallbackQuery):
    await cb.answer()
    try:
        val = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        val = 1
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.master_anti_spam = bool(val)
        await session.commit()
    await cb_filter_spam(cb)


@router.callback_query(F.data == CB_PUNISH)
async def cb_punish(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)

    txt = (
        "⚙️ *Наказания*\n\n"
        "Выбирай, как именно мы *воспитываем* спамеров:\n"
        "— снести сообщение\n"
        "— притушить (мут)\n"
        "— вышвырнуть (бан)\n\n"
        "_Нежно не будет. Но без мата._ 😈"
    )
    await _edit_or_send(cb, txt, _kb_punish(rule))


@router.callback_query(F.data == CB_NEWBIE)
async def cb_newbie_menu(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)

    txt = (
        "👶 *Новичок-режим*\n\n"
        "Если включено — новичков первые N минут держим на коротком поводке.\n"
        "Это защищает от налётов и ботов.\n\n"
        "Выставь окно — и всё."
    )
    await _edit_or_send(cb, txt, _kb_newbie(rule))


@router.callback_query(F.data == CB_REPORTS)
async def cb_reports_menu(cb: CallbackQuery):
    """ТЗ Отчёты: экран с группой, чатом отчётов и кнопками."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        chat_row = await session.get(Chat, chat_id)
    group_title = (getattr(chat_row, "title", None) or "").strip() if chat_row else ""
    if not group_title:
        group_title = await _get_chat_title(cb.bot, chat_id)
    reports_chat_id = getattr(chat_row, "log_chat_id", None) if chat_row else None
    reports_where = "не выбран"
    if reports_chat_id:
        try:
            reports_where = (await cb.bot.get_chat(reports_chat_id)).title or str(reports_chat_id)
        except Exception:
            reports_where = str(reports_chat_id)
    state = "ВКЛ" if rule.log_enabled else "ВЫКЛ"
    txt = (
        "🧾 *Отчёты*\n\n"
        f"Группа: *{group_title}*\n"
        f"Чат отчётов: *{reports_where}*\n"
        f"Сейчас: *{state}*\n\n"
        "_Подключи или смени чат отчётов — кнопками ниже._"
    )
    await _edit_or_send(cb, txt, _kb_reports(rule))


@router.callback_query(F.data == CB_STOPWORDS)
async def cb_stopwords(cb: CallbackQuery):
    await cb.answer()
    txt = (
        "🧠 *Стоп-слова*\n\n"
        "Этот раздел включим, когда таблица stopwords будет в БД.\n"
        "Панель уже готова под это.\n\n"
        "😈 Скажешь — подключим без боли."
    )
    await _edit_or_send(cb, txt, _kb_stopwords_stub())


# =========================================================
# CALLBACKS: TOGGLES / SETTINGS
# =========================================================

@router.callback_query(F.data == CB_TOGGLE_LINKS)
async def cb_toggle_links(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.filter_links = not bool(rule.filter_links)
        rule.filter_links_mode = "forbid" if rule.filter_links else "allow"
        await session.commit()

    await cb_filters(cb)


@router.callback_query(F.data == CB_TOGGLE_MENTIONS)
async def cb_toggle_mentions(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.filter_mentions = not bool(rule.filter_mentions)
        await session.commit()

    await cb_filters(cb)


@router.callback_query(F.data == CB_TOGGLE_ANTIEDIT)
async def cb_toggle_antiedit(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.anti_edit = not bool(rule.anti_edit)
        await session.commit()

    await cb_filters(cb)


@router.callback_query(F.data == CB_MODE)
async def cb_mode(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.action_mode = _next_mode(rule.action_mode)
        await session.commit()

    await cb_punish(cb)


@router.callback_query(F.data == CB_SET_MUTE_MIN)
async def cb_set_mute_min(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    _pending_set(cb.from_user.id, "mute_minutes", chat_id)

    txt = (
        "🔇 *Мут — время*\n\n"
        "Кидай одним сообщением число минут *1..1440*.\n"
        "_Пример:_ `30`\n\n"
        "😈 Просто число. Без лирики."
    )
    await _edit_or_send(cb, txt, _kb_cancel())


@router.callback_query(F.data == CB_TOGGLE_NEWBIE)
async def cb_toggle_newbie(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.newbie_enabled = not bool(rule.newbie_enabled)
        await session.commit()

    await cb_newbie_menu(cb)


@router.callback_query(F.data == CB_SET_NEWBIE_MIN)
async def cb_set_newbie_min(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    _pending_set(cb.from_user.id, "newbie_minutes", chat_id)

    txt = (
        "👶 *Новичок — окно*\n\n"
        "Кидай одним сообщением число минут *1..1440*.\n"
        "_Пример:_ `10`"
    )
    await _edit_or_send(cb, txt, _kb_cancel())


# =========================================================
# CALLBACKS: REPORTS (куда слать)
# =========================================================

@router.callback_query(F.data == CB_TOGGLE_REPORTS)
async def cb_toggle_reports(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.log_enabled = not bool(rule.log_enabled)
        await session.commit()

    await cb_reports_menu(cb)


@router.callback_query(F.data == CB_CONNECT_REPORTS)
async def cb_connect_reports(cb: CallbackQuery):
    """ТЗ Отчёты: открыть выбор чата отчётов (модалка Telegram)."""
    protected_chat_id = await _get_selected_or_alert(cb)
    if not protected_chat_id:
        return
    await cb.answer()
    _pending_reports_for[cb.from_user.id] = protected_chat_id
    try:
        await cb.message.answer(
            "Нажми кнопку ниже — выбери группу, куда слать отчёты. Если бота там ещё нет — добавь его в ту группу и выбери снова.",
            reply_markup=_kb_connect_reports_chat(),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("cb_connect_reports answer failed: %s", e)
        try:
            await cb.message.answer(
                "Не удалось показать кнопку выбора. Убедись, что бот добавлен в группу для отчётов, затем попробуй снова из раздела *Отчёты*.",
                parse_mode="Markdown",
            )
        except Exception:
            pass


@router.callback_query(F.data == CB_PICK_REPORTS_CHAT)
async def cb_pick_reports_chat(cb: CallbackQuery):
    await cb.answer()
    txt, kb = await render_pick_reports_chat(cb.bot, cb.from_user.id)
    await _edit_or_send(cb, txt, kb)


@router.callback_query(F.data == CB_CLEAR_REPORTS_CHAT)
async def cb_clear_reports_chat(cb: CallbackQuery):
    await cb.answer()
    selected = await _get_selected_or_alert(cb)
    if not selected:
        return

    async with await get_session() as session:
        chat_row = await session.get(Chat, selected)
        if chat_row:
            chat_row.log_chat_id = None
            await session.commit()

    await cb_reports_menu(cb)


@router.callback_query(F.data.startswith(CB_SET_REPORTS_CHAT))
async def cb_set_reports_chat(cb: CallbackQuery):
    await cb.answer()
    selected = await _get_selected_or_alert(cb)
    if not selected:
        return

    try:
        reports_chat_id = int(cb.data.split(":")[-1])
    except Exception:
        await cb.answer("Кривые данные 😈", show_alert=True)
        return

    async with await get_session() as session:
        # разрешать только лог-чаты пользователя (где был /setlog)
        log_chats = await _user_log_chats(session, cb.from_user.id)
        allowed_log_ids = {c.id for c in log_chats}
        if reports_chat_id not in allowed_log_ids:
            await cb.answer("Выбери чат отчётов из списка 😈", show_alert=True)
            return

        chat_row = await session.get(Chat, selected)
        if chat_row:
            chat_row.log_chat_id = reports_chat_id
            await session.commit()

    await cb_reports_menu(cb)


@router.callback_query(F.data == CB_REPORTS_HELP)
async def cb_reports_help(cb: CallbackQuery):
    await cb.answer()
    txt = (
        "🧾 *Отчёты — это журнал зачистки*\n\n"
        "Туда я шлю:\n"
        "• кого вынес\n"
        "• за что\n"
        "• что сделал (удалил/мут/бан)\n\n"
        "*Как настроить:*\n"
        "Нажми *➕ Подключить чат отчётов* и выбери группу — туда пойдут отчёты.\n\n"
        "😈 Я не болтаю. Я фиксирую наказания."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=CB_REPORTS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


# =========================================================
# CONNECT (инструкция без метаний)
# =========================================================

# ТЗ ЧЕККК: права бота при добавлении через выбор чата (минимально нужные для защиты)
BOT_ADMIN_RIGHTS = ChatAdministratorRights(
    is_anonymous=False,
    can_manage_chat=True,
    can_delete_messages=True,
    can_manage_video_chats=False,
    can_restrict_members=True,
    can_promote_members=False,
    can_change_info=True,
    can_invite_users=True,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_pin_messages=True,
)
# Для модалки «назначить админа»: права пользователя в чате (superset прав бота) — без этого клиент может не показать диалог
USER_ADMIN_RIGHTS_FOR_REQUEST = ChatAdministratorRights(
    is_anonymous=False,
    can_manage_chat=True,
    can_delete_messages=True,
    can_manage_video_chats=False,
    can_restrict_members=True,
    can_promote_members=False,
    can_change_info=True,
    can_invite_users=True,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_pin_messages=True,
)


def _kb_connect_reports_chat() -> ReplyKeyboardMarkup:
    """ТЗ Отчёты: выбор чата для отчётов — только группы, где бот уже есть (чтобы туда слать отчёты)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📋 Выбрать чат отчётов",
                    request_chat=KeyboardButtonRequestChat(
                        request_id=REPORTS_REQUEST_ID,
                        chat_is_channel=False,
                        bot_is_member=True,
                        request_title=True,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _kb_connect_request_chat() -> ReplyKeyboardMarkup:
    """Выбор группы: показываем чаты, где бот уже есть (bot_is_member=True — лучше работает в клиентах)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📋 Выбрать группу",
                    request_chat=KeyboardButtonRequestChat(
                        request_id=CONNECT_REQUEST_ID,
                        chat_is_channel=False,
                        bot_is_member=True,
                        request_title=True,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _kb_connect_request_chat_with_admin() -> ReplyKeyboardMarkup:
    """Добавить бота в группу и сразу выдать права: Telegram откроет выбор группы и модалку назначения админа."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📋 Выбрать группу",
                    request_chat=KeyboardButtonRequestChat(
                        request_id=CONNECT_REQUEST_ID,
                        chat_is_channel=False,
                        request_title=True,
                        user_administrator_rights=USER_ADMIN_RIGHTS_FOR_REQUEST,
                        bot_administrator_rights=BOT_ADMIN_RIGHTS,
                        bot_is_member=False,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.callback_query(F.data == CB_ADDGROUP)
async def cb_addgroup(cb: CallbackQuery):
    """Показать Reply-кнопку «выбор группы + выдача прав»; если не отображается — даём ссылку в инлайне."""
    await cb.answer()
    if not cb.from_user:
        return
    import logging
    log = logging.getLogger(__name__)
    # Пробуем отправить сообщение с Reply-клавиатурой (синяя кнопка под полем ввода)
    try:
        await cb.bot.send_message(
            cb.from_user.id,
            ADDGROUP_PANEL_TEXT,
            parse_mode="Markdown",
            reply_markup=_kb_connect_request_chat_with_admin(),
        )
    except Exception as e:
        log.warning("cb_addgroup: reply keyboard send failed: %s", e, exc_info=True)
        await cb.message.answer(ADDGROUP_PANEL_TEXT, parse_mode="Markdown")
    # Всегда добавляем инлайн-кнопку: если синяя кнопка не показывается (клиент/превью), пользователь может нажать ссылку
    try:
        from aiogram.types import InlineKeyboardButton
        me = await cb.bot.get_me()
        username = me.username or "bot"
        add_url = f"https://t.me/{username}?startgroup"
        fallback_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить бота в группу (затем выдайте права вручную)", url=add_url)],
        ])
        await cb.bot.send_message(
            cb.from_user.id,
            "Если синей кнопки под полем ввода нет — нажмите кнопку ниже: откроется выбор группы. По этой ссылке права админа нужно будет выдать боту вручную в группе. Модалка «назначить админа» показывается только при нажатии синей кнопки под полем ввода.",
            reply_markup=fallback_kb,
        )
    except Exception as e:
        log.warning("cb_addgroup: fallback inline send failed: %s", e)


@router.callback_query(F.data == CB_CONNECT)
async def cb_connect(cb: CallbackQuery):
    """ТЗ: подключение — выбор группы из списка или нативная модалка Telegram."""
    await cb.answer()
    async with await get_session() as session:
        pending = await _pending_chats(session, cb.from_user.id)

    txt = (
        "➕ *Подключить чат*\n\n"
        "• Нажми *«Выбрать группу из списка»* — откроется модалка Telegram со списком групп, где уже есть бот.\n"
        "• Или выбери группу из списка ниже (куда ты уже добавлял бота)."
    )
    b = InlineKeyboardBuilder()
    b.button(text="📋 Выбрать группу из списка Telegram", callback_data=CB_CONNECT_PICK_MODAL)
    if pending:
        for ch in pending[:20]:
            title = (ch.title or "").strip() or str(ch.id)
            if len(title) > 35:
                title = title[:32] + "…"
            b.button(text=f"🛡 {title}", callback_data=f"{CB_CONNECT_CONFIRM_PREFIX}{ch.id}")
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)
    b.adjust(1)
    await _edit_or_send(cb, txt, b.as_markup())


@router.callback_query(F.data == CB_CONNECT_PICK_MODAL)
async def cb_connect_pick_modal(cb: CallbackQuery):
    """Отправляем сообщение с Reply-кнопкой — по нажатию откроется нативная модалка выбора чата."""
    await cb.answer()
    try:
        await cb.message.answer(
            "Нажми кнопку ниже — откроется список твоих групп, где уже есть бот. Выбери группу для подключения.",
            reply_markup=_kb_connect_request_chat(),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("cb_connect_pick_modal reply keyboard failed: %s", e)
        try:
            await cb.message.answer(
                "Кнопка «Выбрать группу» в этом клиенте может не открываться. "
                "Добавь бота в нужную группу как админа, затем вернись сюда и выбери группу *из списка под сообщением выше* — там появятся чаты, куда ты уже добавлял бота.",
                parse_mode="Markdown",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith(CB_CONNECT_CONFIRM_PREFIX))
async def cb_connect_confirm(cb: CallbackQuery):
    """Подключить выбранную группу к защите (без /check в группе)."""
    await cb.answer()
    try:
        chat_id = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка данных 😈", show_alert=True)
        return

    bot = cb.bot
    user_id = cb.from_user.id

    try:
        chat = await bot.get_chat(chat_id)
        if chat.type not in ("group", "supergroup"):
            await cb.answer("Только группы 😈", show_alert=True)
            return
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await cb.answer("Только админ группы может подключить чат 😈", show_alert=True)
            return
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
        if bot_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await cb.answer("Сначала выдай боту админку с правом удалять сообщения 😈", show_alert=True)
            return
        if not getattr(bot_member, "can_delete_messages", False):
            await cb.answer("Дай боту право «Удалять сообщения» 😈", show_alert=True)
            return
    except Exception as e:
        await cb.answer("Не удалось проверить чат 😈", show_alert=True)
        return

    try:
        async with await get_session() as session:
            await get_or_create_user(session, user_id, username=cb.from_user.username, first_name=cb.from_user.first_name)
            can_add, current_count, limit = await can_add_chat(session, user_id)
            if not can_add:
                try:
                    await bot.send_message(
                        user_id,
                        f"❌ Лимит чатов: {current_count} из {limit}. Повысь тариф в панели: 💳 Тариф и оплата.",
                    )
                except Exception:
                    pass
                return

            chat_row = await session.get(Chat, chat_id)
            if not chat_row:
                chat_row = Chat(
                    id=chat_id,
                    title=chat.title,
                    owner_user_id=user_id,
                    is_active=True,
                    is_log_chat=False,
                )
                session.add(chat_row)
            else:
                chat_row.title = chat.title
                chat_row.owner_user_id = user_id
                chat_row.is_active = True
                chat_row.is_log_chat = False

            rule = await session.get(Rule, chat_id)
            if not rule:
                rule = Rule(
                    chat_id=chat_id,
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

            await _set_selected_chat(session, user_id, chat_id)
            await session.commit()

        title_esc = (chat.title or "Чат").replace("*", "\\*")
        welcome = (
            "😈 AntiSpam Guardian на месте.\n\n"
            f"Группа *«{title_esc}»* теперь под защитой.\n\n"
            "Я слежу за порядком:\n• режу спам\n• давлю подозрительные ссылки\n"
            "• останавливаю мусор, рейды и лишний шум\n\n"
            "_Что важно:_\n1. Не спамить.\n2. Не кидать ссылки без необходимости.\n"
            "3. Не устраивать помойку в чате.\n4. Не лезть с враждой, оскорблениями и провокациями.\n\n"
            "Нормальным людям — спокойно общаться.\nСпамерам — будет больно.\n\n_Админ управляет защитой._"
        )
        try:
            await bot.send_message(chat_id, welcome, parse_mode="Markdown")
        except Exception:
            pass

        try:
            await cb.message.edit_text("✅ Группа подключена к защите. Управление — в панели.", reply_markup=_kb_back_to_main())
        except Exception:
            await _edit_panel(bot, user_id, "✅ Группа подключена. Открой панель: /panel", _kb_back_to_main())
    except Exception:
        await cb.answer(
            "Ошибка базы данных. Примените миграции (миграция 008). См. DEPLOY-RAILWAY.md.",
            show_alert=True,
        )


@router.message(F.chat.type == "private", F.text)
async def on_private_text_antispam_add(message: Message):
    """Ввод: промокод, слово для мата, user_id для антиспам базы."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if user_id in _pending_profanity_add:
        _pending_profanity_add.pop(user_id, None)
        if text.lower() in ("/cancel", "отмена", "cancel"):
            await message.answer("Отменено.")
            return
        if not text or len(text) > 64:
            await message.answer("Отправь одно слово (до 64 символов) или /cancel")
            return
        from app.api.service import add_profanity
        async with await get_session() as session:
            added = await add_profanity(session, text)
        await message.answer(f"✅ Слово «{text[:30]}» {'добавлено' if added else 'уже было'} в фильтр мата.")
        return

    if user_id in _pending_promo:
        _pending_promo.pop(user_id, None)
        if text.lower() in ("/cancel", "отмена", "cancel"):
            await message.answer("Отменено.")
            return
        from app.api.service import apply_promo_code
        async with await get_session() as session:
            ok, msg = await apply_promo_code(session, user_id, text)
        await message.answer(msg if ok else f"❌ {msg}")
        return

    if user_id not in _pending_antispam_add:
        return
    if text.lower() in ("/cancel", "отмена", "cancel"):
        _pending_antispam_add.pop(message.from_user.id, None)
        await message.answer("Отменено.")
        return
    if not text.isdigit():
        await message.answer("Отправь user_id числом (например 123456789) или /cancel")
        return
    from app.services.global_antispam import add_to_global_antispam
    uid = int(text)
    async with await get_session() as session:
        added = await add_to_global_antispam(session, uid, reason=None)
    _pending_antispam_add.pop(message.from_user.id, None)
    await message.answer(f"✅ Пользователь `{uid}` {'добавлен' if added else 'уже был'} в антиспам базу.", parse_mode="Markdown")


@router.message(F.chat.type == "private", F.chat_shared)
async def on_chat_shared(message: Message):
    """Пользователь выбрал чат в модалке: подключение группы (CONNECT) или чат отчётов (REPORTS)."""
    if not message.chat_shared or not message.from_user:
        return

    request_id = message.chat_shared.request_id
    user_id = message.from_user.id

    # ТЗ Отчёты: выбор чата отчётов для выбранной защищаемой группы
    if request_id == REPORTS_REQUEST_ID:
        protected_chat_id = _pending_reports_for.pop(user_id, None)
        if not protected_chat_id:
            await message.answer("Сессия истекла. Зайди в Отчёты и нажми «Подключить чат отчётов» снова.", reply_markup=ReplyKeyboardRemove())
            return
        reports_chat_id = message.chat_shared.chat_id
        reports_title = (message.chat_shared.title or "").strip() or str(reports_chat_id)
        try:
            async with await get_session() as session:
                chat_row = await session.get(Chat, protected_chat_id)
                if chat_row:
                    chat_row.log_chat_id = reports_chat_id
                log_chat_row = await session.get(Chat, reports_chat_id)
                if not log_chat_row:
                    log_chat_row = Chat(
                        id=reports_chat_id,
                        title=reports_title,
                        owner_user_id=user_id,
                        is_log_chat=True,
                        is_active=False,
                    )
                    session.add(log_chat_row)
                else:
                    log_chat_row.title = reports_title
                    log_chat_row.is_log_chat = True
                    log_chat_row.owner_user_id = user_id
                await session.commit()

            protected_title = ""
            try:
                async with await get_session() as session:
                    cr = await session.get(Chat, protected_chat_id)
                    protected_title = (cr.title or "").strip() if cr else ""
            except Exception:
                pass
            if not protected_title:
                protected_title = await _get_chat_title(message.bot, protected_chat_id)
            title_esc = protected_title.replace("*", "\\*")

            msg_text = (
                "😈 *AntiSpam Guardian* подключил чат отчётов.\n\n"
                "Теперь сюда будут прилетать отчёты из группы:\n"
                f"*«{title_esc}»*\n\n"
                "Я буду присылать:\n"
                "• удаления сообщений\n• муты\n• баны\n• разбаны\n• размуты\n• подозрительную активность\n\n"
                "_Это рабочий журнал администраторов. Участников здесь не трогаю — только отчёты._"
            )
            me = await message.bot.get_me()
            panel_url = f"https://t.me/{me.username}?start=panel"
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            await message.bot.send_message(
                reports_chat_id,
                msg_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⚙ Открыть панель управления", url=panel_url)]
                ]),
            )
        except Exception:
            pass
        await message.answer("✅ Чат отчётов подключён.", reply_markup=ReplyKeyboardRemove())
        return

    if request_id != CONNECT_REQUEST_ID:
        return

    chat_id = message.chat_shared.chat_id
    bot = message.bot
    user_id = message.from_user.id

    try:
        chat = await bot.get_chat(chat_id)
        if chat.type not in ("group", "supergroup"):
            await message.answer("Только группы можно подключить 😈", reply_markup=ReplyKeyboardRemove())
            return
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.answer("Только админ группы может подключить чат 😈", reply_markup=ReplyKeyboardRemove())
            return
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
        if bot_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.answer("Сначала выдай боту админку с правом удалять сообщения 😈", reply_markup=ReplyKeyboardRemove())
            return
        if not getattr(bot_member, "can_delete_messages", False):
            await message.answer("Дай боту право «Удалять сообщения» 😈", reply_markup=ReplyKeyboardRemove())
            return
    except Exception:
        await message.answer("Не удалось проверить чат 😈", reply_markup=ReplyKeyboardRemove())
        return

    try:
        async with await get_session() as session:
            await get_or_create_user(session, user_id, username=message.from_user.username, first_name=message.from_user.first_name)
            can_add, current_count, limit = await can_add_chat(session, user_id)
            if not can_add:
                await message.answer(
                    f"❌ Лимит чатов: {current_count} из {limit}. Повысь тариф в панели: 💳 Тариф и оплата.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return

            chat_row = await session.get(Chat, chat_id)
            if not chat_row:
                chat_row = Chat(
                    id=chat_id,
                    title=chat.title,
                    owner_user_id=user_id,
                    is_active=True,
                    is_log_chat=False,
                )
                session.add(chat_row)
            else:
                chat_row.title = chat.title
                chat_row.owner_user_id = user_id
                chat_row.is_active = True
                chat_row.is_log_chat = False

            rule = await session.get(Rule, chat_id)
            if not rule:
                rule = Rule(
                    chat_id=chat_id,
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

            await _set_selected_chat(session, user_id, chat_id)
            await session.commit()

        title_esc = (chat.title or "Чат").replace("*", "\\*")
        welcome = (
            "😈 AntiSpam Guardian на месте.\n\n"
            f"Группа *«{title_esc}»* теперь под защитой.\n\n"
            "Я слежу за порядком:\n• режу спам\n• давлю подозрительные ссылки\n"
            "• останавливаю мусор, рейды и лишний шум\n\n"
            "_Что важно:_\n1. Не спамить.\n2. Не кидать ссылки без необходимости.\n"
            "3. Не устраивать помойку в чате.\n4. Не лезть с враждой, оскорблениями и провокациями.\n\n"
            "Нормальным людям — спокойно общаться.\nСпамерам — будет больно.\n\n_Админ управляет защитой._"
        )
        try:
            await bot.send_message(chat_id, welcome, parse_mode="Markdown")
        except Exception:
            pass

        await message.answer(
            "✅ Группа подключена к защите. Управление — в панели.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        await message.answer(
            "Ошибка базы данных. Администратору нужно применить миграцию 008 (см. DEPLOY-RAILWAY.md).",
            reply_markup=ReplyKeyboardRemove(),
        )


# =========================================================
# CANCEL pending input
# =========================================================

@router.callback_query(F.data == CB_CANCEL)
async def cb_cancel(cb: CallbackQuery):
    await cb.answer("Отменил 😈")
    _pending_clear(cb.from_user.id)
    await show_panel(cb.bot, cb.from_user.id)


# =========================================================
# Pending input handler (private)
# =========================================================

@router.message()
async def pending_input_handler(message: Message):
    if message.chat.type != "private" or not message.from_user:
        return

    p = _pending_get(message.from_user.id)
    if not p:
        return

    raw = (message.text or "").strip()
    if not raw:
        return

    try:
        value = int(raw)
    except Exception:
        await _edit_panel(
            message.bot,
            message.from_user.id,
            "❌ Нужно число.\n\n_Пример:_ `30`",
            _kb_cancel(),
        )
        return

    if value < 1 or value > 1440:
        await _edit_panel(
            message.bot,
            message.from_user.id,
            "❌ Дай число *1..1440*.\n\n_Пример:_ `30`",
            _kb_cancel(),
        )
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, p.chat_id)
        if p.kind == "mute_minutes":
            rule.mute_minutes = value
        elif p.kind == "newbie_minutes":
            rule.newbie_minutes = value
        await session.commit()

    _pending_clear(message.from_user.id)
    await show_panel(message.bot, message.from_user.id)
