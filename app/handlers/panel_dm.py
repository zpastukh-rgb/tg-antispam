from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict
from collections import OrderedDict

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, or_

from app.db.session import get_session
from app.db.models import Chat, Rule, UserContext, ChatManager


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

# Навигация/разделы
CB_FILTERS = "p:filters"
CB_PUNISH = "p:punish"
CB_NEWBIE = "p:newbie"
CB_REPORTS = "p:reports"
CB_STOPWORDS = "p:stopwords"

CB_BACK = "p:back"

# Чаты
CB_PICK_CHAT = "p:pick_chat"
CB_CHAT_PAGE = "p:chat_page:"
CB_SET_CHAT = "p:set_chat:"

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
    Пользователь видит ТОЛЬКО свои чаты:
    - owner_user_id == user_id
    - или он назначен менеджером через ChatManager
    """
    sub = select(ChatManager.chat_id).where(ChatManager.user_id == user_id).subquery()

    res = await session.execute(
        select(Chat)
        .where(
            Chat.is_active == True,  # noqa: E712
            or_(
                Chat.owner_user_id == user_id,
                Chat.id.in_(select(sub.c.chat_id)),
            ),
        )
        .order_by(Chat.id.asc())
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
    b = InlineKeyboardBuilder()

    b.button(text="🧹 Фильтры", callback_data=CB_FILTERS)
    b.button(text="⚙️ Наказания", callback_data=CB_PUNISH)

    b.button(text="👶 Новички", callback_data=CB_NEWBIE)
    b.button(text="🧾 Отчёты", callback_data=CB_REPORTS)

    b.button(text="🧠 Стоп-слова", callback_data=CB_STOPWORDS)
    b.button(text="🔁 Сменить чат", callback_data=CB_PICK_CHAT)

    b.button(text="➕ Подключить чат", callback_data=CB_CONNECT)

    b.adjust(2, 2, 2, 1)
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
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)

    b.adjust(2, 2)
    return b.as_markup()


def _kb_punish(rule: Rule) -> InlineKeyboardMarkup:
    mode = _human_mode(rule.action_mode)
    mute_min = int(rule.mute_minutes or 30)

    b = InlineKeyboardBuilder()

    b.button(text=f"😈 Режим: {mode}", callback_data=CB_MODE)
    b.button(text=f"🔇 Мут: {mute_min}м", callback_data=CB_SET_MUTE_MIN)

    b.button(text="⬅️ Назад", callback_data=CB_MAIN)

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
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)
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
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)

    b.adjust(2, 2)
    return b.as_markup()


def _kb_stopwords_stub() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


# =========================================================
# RENDER SCREENS
# =========================================================

async def render_main(bot, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    async with await get_session() as session:
        chats = await _managed_chats(session, user_id)

        if not chats:
            txt = (
                "😈 *AntiSpam Guardian*\n\n"
                "У тебя пока нет подключённых чатов.\n\n"
                "Жми *➕ Подключить чат*.\n"
                "Я навожу порядок. Спамеры — терпят."
            )
            kb = InlineKeyboardBuilder()
            kb.button(text="➕ Подключить чат", callback_data=CB_CONNECT)
            kb.adjust(1)
            return txt, kb.as_markup()

        selected = await _get_selected_chat(session, user_id)

        allowed = {c.id for c in chats}
        if selected and selected not in allowed:
            selected = None
            await _set_selected_chat(session, user_id, None)

        # автоселект если 1 чат
        if not selected and len(chats) == 1:
            selected = chats[0].id
            await _set_selected_chat(session, user_id, selected)

        # если не выбран — отправим в выбор
        if not selected:
            txt = "😈 Выбери чат для настройки."
            kb = await render_pick_chat(bot, user_id, page=0)
            return txt, kb

        chat_row = await session.get(Chat, selected)
        rule = await _get_or_create_rule(session, selected)

        title = (getattr(chat_row, "title", None) or "").strip() if chat_row else ""
        if not title:
            title = await _get_chat_title(bot, selected)

        reports_on = bool(rule.log_enabled)
        reports_chat_id = getattr(chat_row, "log_chat_id", None) if chat_row else None
        reports_where = "не настроено"
        if reports_chat_id:
            reports_where = await _get_chat_title(bot, int(reports_chat_id))

        txt = (
            "😈 *Панель AntiSpam Guardian*\n\n"
            f"🛡 *Чат:* {title}\n"
            f"🧾 *Отчёты:* {'ВКЛ' if reports_on else 'ВЫКЛ'} → {reports_where}\n\n"
            f"⚙️ *Режим:* {_human_mode(rule.action_mode)}\n"
            f"🔇 *Мут:* {int(rule.mute_minutes or 30)} мин\n"
            f"✏️ *Anti-edit:* {'ВКЛ' if rule.anti_edit else 'ВЫКЛ'}\n"
            f"👶 *Новичок:* {'ВКЛ' if rule.newbie_enabled else 'ВЫКЛ'} (окно {int(rule.newbie_minutes or 10)} мин)\n"
            f"🔗 *Ссылки:* {'РЕЖУ' if rule.filter_links else 'НЕ'}\n"
            f"🏷 *@:* {'РЕЖУ' if rule.filter_mentions else 'НЕ'}\n\n"
            "_Жми кнопки — я обновляю это же сообщение. Без мусора._"
        )
        return txt, _kb_main()


async def render_pick_chat(bot, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    PAGE_SIZE = 10

    async with await get_session() as session:
        chats = await _managed_chats(session, user_id)

    b = InlineKeyboardBuilder()

    if not chats:
        b.button(text="➕ Подключить чат", callback_data=CB_CONNECT)
        b.button(text="⬅️ Назад", callback_data=CB_MAIN)
        b.adjust(1)
        return b.as_markup()

    total = len(chats)
    max_page = (total - 1) // PAGE_SIZE
    page = max(0, min(page, max_page))

    chunk = chats[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    for ch in chunk:
        title = (ch.title or "").strip() or str(ch.id)
        b.button(text=f"🛡 {title}", callback_data=f"{CB_SET_CHAT}{ch.id}")

    # pagination row
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️", callback_data=f"{CB_CHAT_PAGE}{page-1}")
    nav.button(text=f"📄 {page+1}/{max_page+1}", callback_data="noop:0")
    if page < max_page:
        nav.button(text="➡️", callback_data=f"{CB_CHAT_PAGE}{page+1}")

    # добавим навигацию как отдельный ряд
    # (InlineKeyboardBuilder не умеет "вставить ряд", поэтому просто добавим кнопки и adjust)
    for btn_row in nav.export():
        for btn in btn_row:
            b.add(btn)

    b.button(text="⬅️ Назад", callback_data=CB_MAIN)
    b.adjust(1, 1, 1, 1, 1, 1, 3, 1)  # чат-кнопки по 1, потом ряд пагинации 3, потом назад
    return b.as_markup()


async def render_pick_reports_chat(bot, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    async with await get_session() as session:
        selected = await _get_selected_chat(session, user_id)
        if not selected:
            return "😈 Сначала выбери чат.", _kb_back_to_main()

        chats = await _managed_chats(session, user_id)
        if not chats:
            return "😈 Нет доступных чатов.", _kb_back_to_main()

    b = InlineKeyboardBuilder()
    b.button(text="🚫 Не слать отчёты (снять)", callback_data=CB_CLEAR_REPORTS_CHAT)

    for ch in chats:
        title = (ch.title or "").strip() or await _get_chat_title(bot, ch.id)
        b.button(text=f"📍 {title}", callback_data=f"{CB_SET_REPORTS_CHAT}{ch.id}")

    b.button(text="⬅️ Назад", callback_data=CB_REPORTS)
    b.adjust(1)
    return "🧾 *Куда слать отчёты?*\nВыбери чат/группу:", b.as_markup()


# =========================================================
# SHOW PANEL
# =========================================================

async def show_panel(bot, user_id: int) -> None:
    text, kb = await render_main(bot, user_id)
    await _edit_panel(bot, user_id, text, kb)


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


@router.callback_query(F.data == CB_PICK_CHAT)
async def cb_pick_chat(cb: CallbackQuery):
    await cb.answer()
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0)
    await _edit_or_send(cb, "😈 *Выбор чата*\nВыбери, кого защищаем:", kb)


@router.callback_query(F.data.startswith(CB_CHAT_PAGE))
async def cb_chat_page(cb: CallbackQuery):
    await cb.answer()
    try:
        page = int(cb.data.split(":")[-1])
    except Exception:
        page = 0
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=page)
    await _edit_or_send(cb, "😈 *Выбор чата*\nВыбери, кого защищаем:", kb)


@router.callback_query(F.data.startswith(CB_SET_CHAT))
async def cb_set_chat(cb: CallbackQuery):
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

    await show_panel(cb.bot, cb.from_user.id)


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
        # безопасность: только из "твоих" чатов
        chats = await _managed_chats(session, cb.from_user.id)
        allowed = {c.id for c in chats}
        if reports_chat_id not in allowed:
            await cb.answer("Это не твой чат 😈", show_alert=True)
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
        "Лучший вариант — отдельная группа «Отчёты».\n"
        "Добавь туда бота админом.\n"
        "Потом: *📍 Куда слать* → выбери эту группу.\n\n"
        "😈 Я не болтаю. Я фиксирую наказания."
    )
    await _edit_or_send(cb, txt, _kb_back_to_main())


# =========================================================
# CONNECT (инструкция без метаний)
# =========================================================

@router.callback_query(F.data == CB_CONNECT)
async def cb_connect(cb: CallbackQuery):
    await cb.answer()
    txt = (
        "➕ *Подключить чат*\n\n"
        "1) Добавь меня в нужную группу\n"
        "2) Дай админку: ✅ *Удалять сообщения*\n"
        "3) В группе напиши: */check*\n\n"
        "Вернись сюда: */panel*\n\n"
        "😈 Всё. Дальше я работаю."
    )
    await _edit_or_send(cb, txt, _kb_back_to_main())


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
