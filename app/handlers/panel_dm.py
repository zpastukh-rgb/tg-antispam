from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict
from collections import OrderedDict

from aiogram import Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButtonRequestChat,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, or_

from app.db.session import get_session
from app.db.models import Chat, Rule, UserContext, ChatManager
from app.services.user_service import get_or_create_user, can_add_chat, TARIFF_CHAT_LIMITS


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
CB_CHAT_PAGE = "p:chat_page:"
CB_SET_CHAT = "p:set_chat:"      # выбор чата из списка → экран управления группой

CB_BACK = "p:back"

# Внутри Защита
CB_FILTERS = "p:filters"
CB_PUNISH = "p:punish"
CB_NEWBIE = "p:newbie"
CB_STOPWORDS = "p:stopwords"
CB_RAID = "p:raid"
CB_BACK_TO_CHAT = "p:back_chat"  # назад к экрану «Управление группой»
CB_PUBLIC_ALERTS = "p:public_alerts"
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
CB_CONNECT_PICK_MODAL = "p:connect_pick_modal"   # открыть модалку выбора чата
CB_CONNECT_CONFIRM_PREFIX = "p:connect_confirm:"
CONNECT_REQUEST_ID = 0x7E17  # request_id для KeyboardButtonRequestChat

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


def _kb_main() -> InlineKeyboardMarkup:
    """Главное меню: 3 кнопки (ТЗ правки). Защита и Отчёты — только внутри выбранного чата."""
    b = InlineKeyboardBuilder()
    b.button(text="📂 Подключённые чаты", callback_data=CB_CHATS)
    b.button(text="💳 Тариф и оплата", callback_data=CB_BILLING)
    b.button(text="➕ Подключить чат", callback_data=CB_CONNECT)
    b.adjust(1)
    return b.as_markup()


def _kb_protection() -> InlineKeyboardMarkup:
    """Вложенное меню Защита: Фильтры, Наказания, Новички, Стоп-слова, Публичные сообщения, Анти-рейд."""
    b = InlineKeyboardBuilder()
    b.button(text="⚙ Фильтры", callback_data=CB_FILTERS)
    b.button(text="🔨 Наказания", callback_data=CB_PUNISH)
    b.button(text="👶 Новички", callback_data=CB_NEWBIE)
    b.button(text="🧠 Стоп-слова", callback_data=CB_STOPWORDS)
    b.button(text="📢 Публичные сообщения", callback_data=CB_PUBLIC_ALERTS)
    b.button(text="🚨 Анти-рейд", callback_data=CB_RAID)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def _kb_public_alerts(rule: Rule) -> InlineKeyboardMarkup:
    """Настройки публичных сообщений Guardian (раз в N удалений)."""
    on_off = "ВКЛ" if getattr(rule, "public_alerts_enabled", False) else "ВЫКЛ"
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
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
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
    """Внутри выбранного чата: Защита, Отчёты, Сменить чат, Назад."""
    b = InlineKeyboardBuilder()
    b.button(text="🛡 Защита", callback_data=CB_PROTECTION)
    b.button(text="🧾 Отчёты", callback_data=CB_REPORTS)
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


def _kb_filters(rule: Rule) -> InlineKeyboardMarkup:
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
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)

    b.adjust(2, 2)
    return b.as_markup()


def _kb_punish(rule: Rule) -> InlineKeyboardMarkup:
    mode = _human_mode(rule.action_mode)
    mute_min = int(rule.mute_minutes or 30)

    b = InlineKeyboardBuilder()

    b.button(text=f"😈 Режим: {mode}", callback_data=CB_MODE)
    b.button(text=f"🔇 Мут: {mute_min}м", callback_data=CB_SET_MUTE_MIN)

    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)

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
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_reports(rule: Rule) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    b.button(
        text=f"🧾 Отчёты: {'ВКЛ' if rule.log_enabled else 'ВЫКЛ'}",
        callback_data=CB_TOGGLE_REPORTS,
    )
    b.button(text="📍 Куда слать", callback_data=CB_PICK_REPORTS_CHAT)

    b.button(text="🧾 Как работает", callback_data=CB_REPORTS_HELP)
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)

    b.adjust(2, 2)
    return b.as_markup()


def _kb_stopwords_stub() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=CB_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_raid_stub() -> InlineKeyboardMarkup:
    """Анти-рейд: заглушка (тариф PRO)."""
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=CB_BACK_TO_CHAT)
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
        tariff_label = (user.tariff or "FREE").upper()
        sub_until = _format_subscription_until(user.subscription_until)
        txt = (
            "😈 *AntiSpam Guardian*\n\n"
            f"Тариф: *{tariff_label}*  |  Подключено: *{len(chats)} из {user.chat_limit}*\n"
            f"Подписка до: *{sub_until}*\n\n"
            "_Настройки чатов — в разделе *Подключённые чаты*._"
        )
        return txt, _kb_main()


def _back_code(back_to: str) -> str:
    """Код для пагинации списка чатов."""
    if back_to == CB_CHATS:
        return "c"
    if back_to == CB_BACK_TO_CHAT:
        return "b"
    return "m"


async def render_pick_chat(
    bot, user_id: int, page: int = 0, back_to: str = CB_MAIN
) -> InlineKeyboardMarkup:
    """Список чатов для выбора. back_to — куда ведёт кнопка «Назад» (CB_CHATS, CB_BACK_TO_CHAT, CB_MAIN)."""
    PAGE_SIZE = 10
    code = _back_code(back_to)

    async with await get_session() as session:
        chats = await _managed_chats(session, user_id)

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

    for ch in chunk:
        title = (ch.title or "").strip() or str(ch.id)
        b.button(text=f"🛡 {title}", callback_data=f"{CB_SET_CHAT}{ch.id}")

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
                "😈 *Нет лог-чатов.*\n\n"
                "1) Создай группу для логов\n"
                "2) Добавь туда бота, дай права\n"
                "3) В той группе напиши: /setlog\n"
                "4) Вернись сюда и выбери её.",
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
    return "🧾 *Куда слать отчёты?*\nТолько лог-чаты (где был /setlog):", b.as_markup()


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

@router.message(Command("panel"))
async def panel_cmd(message: Message):
    if message.chat.type != "private":
        await message.answer("😈 Панель только в личке. Напиши */panel*.", parse_mode="Markdown")
        return
    if not message.from_user:
        return
    # Сброс кэша, чтобы всегда открывался главный экран (5 кнопок), а не вложенное меню
    _cache_clear(message.from_user.id)
    await show_panel(message.bot, message.from_user.id)


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


@router.callback_query(F.data == CB_PROTECTION)
async def cb_protection(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
    title = (getattr(chat_row, "title", None) or "").strip() if chat_row else str(chat_id)
    if not title:
        title = await _get_chat_title(cb.bot, chat_id)
    txt = f"🛡 *Защита*\n\nЧат: *{title}*\n\nФильтры, наказания, новички, стоп-слова, анти-рейд."
    await _edit_or_send(cb, txt, _kb_protection())


@router.callback_query(F.data == CB_RAID)
async def cb_raid(cb: CallbackQuery):
    await cb.answer()
    txt = (
        "🚨 *Анти-рейд*\n\n"
        "Защита от массового входа ботов и рейдов.\n\n"
        "🔒 Доступно на тарифе *PRO*.\n"
        "Повысь тариф в разделе *Тариф и оплата*."
    )
    await _edit_or_send(cb, txt, _kb_raid_stub())


@router.callback_query(F.data == CB_PUBLIC_ALERTS)
async def cb_public_alerts(cb: CallbackQuery):
    """📢 Публичные сообщения Guardian — раз в N удалений (ТЗ ПРАВКИ 2)."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_off = "ВКЛ" if getattr(rule, "public_alerts_enabled", False) else "ВЫКЛ"
    every = getattr(rule, "public_alerts_every_n", 5)
    interval_sec = getattr(rule, "public_alerts_min_interval_sec", 300)
    interval_min = interval_sec // 60
    txt = (
        "📢 *Публичные сообщения Guardian*\n\n"
        f"Сейчас: *{on_off}*\n"
        f"Частота: каждые *{every}* удалений\n"
        f"Минимальный интервал: *{interval_min}* мин\n\n"
        "_Короткие реплики в чат раз в N удалений — участники видят, что бот работает._"
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
        rule.public_alerts_enabled = True
        await session.commit()
    txt = "📢 Публичные сообщения: *ВКЛ*. Раз в N удалений бот будет писать короткую реплику в чат."
    await _edit_or_send(cb, txt, _kb_public_alerts(rule))


@router.callback_query(F.data == CB_PUBLIC_ALERTS_OFF)
async def cb_public_alerts_off(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.public_alerts_enabled = False
        await session.commit()
    txt = "📢 Публичные сообщения: *ВЫКЛ*."
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
    on_off = "ВКЛ" if getattr(rule, "public_alerts_enabled", False) else "ВЫКЛ"
    txt = f"📢 Частота: каждые *{n}* удалений. Сейчас: *{on_off}*."
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
    tariff = (user.tariff or "FREE").upper()
    sub_until = _format_subscription_until(user.subscription_until)
    limit = user.chat_limit
    txt = (
        "💳 *Тариф и оплата*\n\n"
        f"Тариф: *{tariff}*\n"
        f"Подключено чатов: *{count} из {limit}*\n"
        f"Подписка до: *{sub_until}*\n\n"
        "_Оплата и смена тарифа — в следующих версиях._"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=CB_MAIN)
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
    """Управление всеми группами (массовые настройки)."""
    await cb.answer()
    txt = (
        "🌐 *Управление всеми группами*\n\n"
        "Выбранные действия применятся ко всем подключённым чатам."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🛡 Защита для всех", callback_data="p:protection_all")  # заглушка
    kb.button(text="🧾 Отчёты для всех", callback_data="p:reports_all")  # заглушка
    kb.button(text="⬅️ Назад", callback_data=CB_CHATS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


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
    parts = cb.data.split(":")
    try:
        page = int(parts[2]) if len(parts) >= 3 else 0
    except (ValueError, IndexError):
        page = 0
    code = parts[3] if len(parts) >= 4 and len(parts[3]) == 1 else "m"
    back_to = CB_CHATS if code == "c" else (CB_BACK_TO_CHAT if code == "b" else CB_MAIN)
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=page, back_to=back_to)
    await _edit_or_send(cb, "😈 *Выбор чата*\nВыбери, кого защищаем:", kb)


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
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)

    txt = (
        "🧹 *Фильтры*\n\n"
        "Тут ты говоришь боту:\n"
        "что резать, а что пропускать.\n\n"
        "Без разговоров — только тумблеры 😈"
    )
    await _edit_or_send(cb, txt, _kb_filters(rule))


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
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)

    txt = (
        "🧾 *Отчёты модерации*\n\n"
        "Отчёты — это журнал зачистки:\n"
        "кто, что, за что и какое наказание.\n\n"
        "Хочешь красиво — заведи отдельную группу «Отчёты».\n"
        "Потом нажми *📍 Куда слать*."
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
            await cb.answer("Выбери лог-чат из списка (где был /setlog) 😈", show_alert=True)
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
        "1) Создай отдельную группу для логов\n"
        "2) Добавь туда бота, дай права\n"
        "3) В той группе напиши: /setlog\n"
        "4) Вернись в панель → *Куда слать* → выбери эту группу.\n\n"
        "😈 Я не болтаю. Я фиксирую наказания."
    )
    await _edit_or_send(cb, txt, _kb_back_to_main())


# =========================================================
# CONNECT (инструкция без метаний)
# =========================================================

def _kb_connect_request_chat() -> ReplyKeyboardMarkup:
    """Кнопка «Выбрать группу» — открывает нативную модалку Telegram (все группы, где уже есть бот)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📋 Выбрать группу из списка Telegram",
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
    await cb.message.answer(
        "Нажми кнопку ниже — откроется список твоих групп, где уже есть бот. Выбери группу для подключения.",
        reply_markup=_kb_connect_request_chat(),
    )


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


@router.message(F.chat.type == "private", F.chat_shared)
async def on_chat_shared(message: Message):
    """Пользователь выбрал группу в нативной модалке Telegram — подключаем чат."""
    if not message.chat_shared or message.chat_shared.request_id != CONNECT_REQUEST_ID:
        return
    if not message.from_user:
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
