from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from urllib.parse import quote
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
    InlineKeyboardButton,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButtonRequestChat,
    WebAppInfo,
    FSInputFile,
    InputMediaPhoto,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, or_, func, update

from app.db.session import get_session
from app.db.models import Chat, Rule, UserContext, StopWord, Payment, CreditLedger, PromoCode, PromoCodeRedemption
from app.db.ensure_defaults import DEFAULT_PREMIUM7_PROMO_CODE, DEFAULT_PREMIUM14_PROMO_CODE
from app.services.group_connect_actor import (
    actor_may_connect_chat_as_owner,
    resolve_guard_connect_actor_for_group,
)
from app.services.group_connect_rights import (
    GROUP_CONNECT_ADMIN_QUERY,
    aiogram_bot_administrator_rights,
    aiogram_user_group_administrator_rights,
    first_missing_i18n_key,
)
from app.services.chat_owner_guard import apply_chat_owner_on_connect
from app.services.user_service import (
    get_or_create_user,
    can_add_chat,
    effective_chat_limit,
    effective_channel_limit,
    effective_group_limit,
    ensure_user_chat_limit_synced_for_tariff,
    is_trial_eligible,
)
from app.api.service import apply_promo_code, count_chat_ids_by_kind, get_activity_summary_chat_ids, get_managed_chats, miniapp_actor_has_global_antispam_access
from app.services.admin_roles import is_full_admin_user
from app.services.chat_owner_premium import chat_owner_has_miniapp_premium
from app.services.user_locale import get_user_language, lang_from_update
from app.services.referral_partner_dashboard import (
    referral_partner_access_block,
    referral_partner_level_dashboard,
    referral_partner_ui_max_levels,
)
from app.i18n import t as i18n_t
from app.texts.guardian_billing import PREMIUM_PLANS

logger = logging.getLogger(__name__)


async def _user_lang(user_id: int) -> str:
    """Загрузить язык пользователя из кэша/БД (default 'ru')."""
    try:
        return await get_user_language(int(user_id))
    except Exception:
        return "ru"


router = Router()

# =========================================================
# 😈 AntiSpam Guard — ПАНЕЛЬ (PRO)
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


#
# Reply-клавиатура (быстрые действия): подписи на языке пользователя → отдельные хендлеры (не литералы /команд в тексте кнопок).
#

_DM_QUICK_KB_LAYOUT_VER = 6  # bump: видимый footer вместо \u2063; force_refresh на /start
_DM_QUICK_KB_APPLIED_VER: Dict[int, int] = {}
_DM_QUICK_KB_MSG_ID: Dict[int, int] = {}


def _quick_reply_kb_label_set(leaf_key: str) -> frozenset[str]:
    key = f"panel.reply_kb.{leaf_key}"
    return frozenset(i18n_t(lng, key) for lng in ("ru", "en"))


_DM_REPLY_LABEL_OPEN_MENU = _quick_reply_kb_label_set("quick_open_menu")
_DM_REPLY_LABEL_CHANGE_LANG = _quick_reply_kb_label_set("quick_change_lang")
_DM_REPLY_LABEL_SUPPORT_TIP = _quick_reply_kb_label_set("quick_support_tip")


def dm_quick_reply_kb_clear(user_id: int) -> None:
    """Разрешить снова прислать reply-клаву (язык/смена раскладки)."""
    uid = int(user_id)
    _DM_QUICK_KB_APPLIED_VER.pop(uid, None)
    _DM_QUICK_KB_MSG_ID.pop(uid, None)


async def dm_reply_keyboard_removed_send(bot, user_id: int) -> None:
    dm_quick_reply_kb_clear(int(user_id))
    try:
        await bot.send_message(int(user_id), "\u2063", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass


def reply_kb_dm_quick_commands(lang: str = "ru") -> ReplyKeyboardMarkup:
    lk = lambda key: i18n_t(lang, f"panel.reply_kb.{key}")
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=lk("quick_open_menu"))],
            [
                KeyboardButton(text=lk("quick_change_lang")),
                KeyboardButton(text=lk("quick_support_tip")),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=False,
        is_persistent=True,
    )


async def ensure_dm_quick_reply_keyboard(bot, user_id: int, *, silent: bool = True, force_refresh: bool = False) -> None:
    """Reply-клава быстрых действий. Служебное сообщение не удаляем — иначе клава пропадает в клиенте."""
    uid = int(user_id)
    if (
        not force_refresh
        and int(_DM_QUICK_KB_APPLIED_VER.get(uid, 0)) >= _DM_QUICK_KB_LAYOUT_VER
    ):
        return
    try:
        lang = await _user_lang(uid)
        kb = reply_kb_dm_quick_commands(lang)
        footer = i18n_t(lang, "panel.reply_kb.footer")
        old_mid = int(_DM_QUICK_KB_MSG_ID.get(uid) or 0)
        if old_mid > 0:
            try:
                await bot.edit_message_text(
                    chat_id=uid,
                    message_id=old_mid,
                    text=footer,
                    reply_markup=kb,
                )
                _DM_QUICK_KB_APPLIED_VER[uid] = _DM_QUICK_KB_LAYOUT_VER
                return
            except Exception:
                _DM_QUICK_KB_MSG_ID.pop(uid, None)

        kwargs = dict(
            chat_id=uid,
            text=footer,
            reply_markup=kb,
        )
        if silent:
            kwargs["disable_notification"] = True
        m = await bot.send_message(**kwargs)
        _DM_QUICK_KB_APPLIED_VER[uid] = _DM_QUICK_KB_LAYOUT_VER
        mid = int(getattr(m, "message_id", 0) or 0)
        if mid > 0:
            _DM_QUICK_KB_MSG_ID[uid] = mid
    except Exception:
        logger.debug("ensure_dm_quick_reply_keyboard failed uid=%s", uid, exc_info=True)


# Один активный апдейт панели на пользователя: два параллельных /start не должны успеть дважды
# отправить сообщение между _cache_get (промах) и _cache_set после send_message.
_PANEL_EDIT_GUARD: Dict[int, asyncio.Lock] = {}


def _panel_edit_guard_for(user_id: int) -> asyncio.Lock:
    lk = _PANEL_EDIT_GUARD.get(user_id)
    if lk is None:
        lk = asyncio.Lock()
        _PANEL_EDIT_GUARD[user_id] = lk
    return lk


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
CB_PROFANITY_MAT_TOGGLE = "p:prof_mat_toggle"
CB_PROFANITY_JOBS_TOGGLE = "p:prof_jobs_toggle"
CB_PROFANITY_CASINO_TOGGLE = "p:prof_casino_toggle"
CB_PROMO_ENTER = "p:promo_enter"
CB_COPY_SETTINGS = "p:copy_settings"
CB_COPY_TARGET = "p:copy_target:"  # + chat_id
CB_PUBLIC_ALERTS = "p:public_alerts"
CB_REF = "p:ref"
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
CB_FILTER_LEFT_MSG = "p:fl_left"
CB_FILTER_SILENCE = "p:fl_silence"
CB_FILTER_SPAM = "p:fl_spam"
# Режимы фильтра: allow / captcha / forbid
CB_FILTER_SET = "p:fl_set:"  # + mode (allow|captcha|forbid) + key (links|media|buttons)
CB_FILTER_ALL_CAPTCHA_TIME = "p:fl_cap:"   # + minutes
CB_FILTER_JOIN_TOGGLE = "p:fl_join_t"
CB_FILTER_LEFT_TOGGLE = "p:fl_left_t"
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
# Защита от гонки: чат, выбранный как чат отчётов, не должен автоподключаться как защищаемый.
_reports_chat_guard_until: Dict[int, datetime] = {}


def _mark_reports_chat_guard(chat_id: int, ttl_minutes: int = 15) -> None:
    _reports_chat_guard_until[int(chat_id)] = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(ttl_minutes)))


def _is_reports_chat_guarded(chat_id: int) -> bool:
    now = datetime.now(timezone.utc)
    for cid, until in list(_reports_chat_guard_until.items()):
        if until <= now:
            _reports_chat_guard_until.pop(cid, None)
    until = _reports_chat_guard_until.get(int(chat_id))
    return bool(until and until > now)
# user_id -> True (ожидаем ввод user_id для добавления в антиспам базу)
_pending_antispam_add: Dict[int, bool] = {}
_pending_promo: Dict[int, bool] = {}

# Отмена ввода
CB_CANCEL = "p:cancel"


# =========================================================
# HELPERS (DB / titles / safe edits)
# =========================================================

def _format_mute_minutes_short(minutes: int, lang: str = "ru") -> str:
    """Для кнопок и коротких подписей: 1440 мин → «1 день»."""
    m = int(minutes)
    if m == 1440:
        return i18n_t(lang, "panel.mute.btn_1d")
    return i18n_t(lang, "panel.mute.btn_min", m=m)


def _duration_option_label(minutes: int, lang: str = "ru") -> str:
    return i18n_t(lang, f"panel.duration.{int(minutes)}")


def _format_mute_minutes_long(minutes: int, lang: str = "ru") -> str:
    """Для текста в сообщениях: 1440 мин → «1 день», иначе «N мин»."""
    m = int(minutes)
    if m == 1440:
        return i18n_t(lang, "panel.mute.one_day")
    return i18n_t(lang, "panel.mute.minutes", m=m)


def _human_mode(mode: str, lang: str = "ru") -> str:
    mode = (mode or "delete").lower()
    if mode == "ban":
        return i18n_t(lang, "panel.action.ban")
    if mode == "kick":
        return i18n_t(lang, "panel.action.kick")
    if mode == "mute":
        return i18n_t(lang, "panel.action.mute")
    if mode == "observe":
        return i18n_t(lang, "panel.action.observe")
    if mode == "off":
        return i18n_t(lang, "panel.action.off") if i18n_t(lang, "panel.action.off") != "panel.action.off" else "только фильтры"
    return i18n_t(lang, "panel.action.delete")


def _next_mode(mode: str) -> str:
    mode = (mode or "delete").lower()
    if mode == "delete":
        return "mute"
    if mode == "mute":
        return "kick"
    if mode == "kick":
        return "ban"
    if mode == "ban":
        return "observe"
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
    """Активные управляемые чаты — как в Mini App (`get_managed_chats`: владелец, менеджер, принятый инвайт)."""
    return await get_managed_chats(session, int(user_id))


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
    log_targets = select(Chat.log_chat_id).where(Chat.log_chat_id.is_not(None))
    res = await session.execute(
        select(Chat)
        .where(
            Chat.owner_user_id == user_id,
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == False,  # noqa: E712
            Chat.id.not_in(log_targets),
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
        filter_profanity_enabled=True,
        filter_jobs_enabled=True,
        filter_casino_enabled=True,
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
    async with _panel_edit_guard_for(int(user_id)):
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
                try:
                    await bot.edit_message_caption(
                        caption=text,
                        chat_id=user_id,
                        message_id=msg_id,
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                    return
                except Exception:
                    _cache_clear(user_id)

        m = await bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=kb)
        _cache_set(user_id, m.message_id)


async def _edit_or_send(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        _cache_set(cb.from_user.id, cb.message.message_id)
    except Exception:
        try:
            await cb.message.edit_caption(caption=text, parse_mode="Markdown", reply_markup=kb)
            _cache_set(cb.from_user.id, cb.message.message_id)
        except Exception:
            await _edit_panel(cb.bot, cb.from_user.id, text, kb)


async def _get_selected_or_alert(cb: CallbackQuery) -> Optional[int]:
    async with await get_session() as session:
        sel = await _get_selected_chat(session, cb.from_user.id)
        if sel:
            return sel
    lang = await _user_lang(cb.from_user.id)
    await cb.answer(i18n_t(lang, "panel.alert_pick_chat_first"), show_alert=True)
    return None


# =========================================================
# KEYBOARDS (2 колонки + понятные кнопки)
# =========================================================

def _kb_back_to_main(lang: str = "ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


def _fmt_dm_compact_num(v: float) -> str:
    x = float(v or 0.0)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s


def _render_referral_partner_breakdown(lang: str, tier_dash: dict, bonus_balance_str: str, *, max_partner_level: int) -> str:
    net = tier_dash.get("partner_network") or {}
    stats = tier_dash.get("partner_level_stats") or []
    lines: list[str] = []

    ml = max(1, min(3, int(max_partner_level or 1)))
    lines.append(i18n_t(lang, "panel.referral.partner.network_head"))
    if ml == 1:
        lines.append(i18n_t(lang, "panel.referral.partner.net_l1_solo", n=int(net.get("l1") or 0)))
        lines.append("")
        lines.append(i18n_t(lang, "panel.referral.partner.network_levels_premium_hint"))
    else:
        lines.append(i18n_t(lang, "panel.referral.partner.net_l1", n=int(net.get("l1") or 0)))
        lines.append(i18n_t(lang, "panel.referral.partner.net_l2", n=int(net.get("l2") or 0)))
        lines.append(i18n_t(lang, "panel.referral.partner.net_l3", n=int(net.get("l3") or 0)))
        lines.append(i18n_t(lang, "panel.referral.partner.net_total", n=int(net.get("total") or 0)))

    stats = [row for row in stats if int(row.get("level") or 0) <= ml]

    lines.append("")
    lines.append(i18n_t(lang, "panel.referral.partner.confirmed_head"))
    tot_ctok = 0.0
    for row in stats:
        c = row.get("confirmed") or {}
        pay = int(c.get("payments") or 0)
        rub = float(c.get("sales_rub") or 0.0)
        tok = float(c.get("reward_tokens") or 0.0)
        tot_ctok += tok
        lines.append(
            i18n_t(
                lang,
                "panel.referral.partner.comm_row",
                l=int(row.get("level") or 0),
                pct=int(row.get("percent") or 0),
                pay=pay,
                rub=_fmt_dm_compact_num(rub) + " ₽",
                tok=_fmt_dm_compact_num(tok),
            )
        )
    lines.append(i18n_t(lang, "panel.referral.partner.confirmed_total", tok=_fmt_dm_compact_num(round(tot_ctok, 2))))

    lines.append("")
    lines.append(i18n_t(lang, "panel.referral.partner.pending_head"))
    tot_pp = 0.0
    tot_prub = 0.0
    tot_ptok = 0.0
    for row in stats:
        p = row.get("pending") or {}
        pay = int(p.get("payments") or 0)
        rub = float(p.get("sales_rub") or 0.0)
        tok = float(p.get("reward_tokens") or 0.0)
        tot_pp += float(pay)
        tot_prub += rub
        tot_ptok += tok
        lines.append(
            i18n_t(
                lang,
                "panel.referral.partner.comm_row",
                l=int(row.get("level") or 0),
                pct=int(row.get("percent") or 0),
                pay=pay,
                rub=_fmt_dm_compact_num(rub) + " ₽",
                tok=_fmt_dm_compact_num(tok),
            )
        )
    lines.append(
        i18n_t(
            lang,
            "panel.referral.partner.pending_total",
            pay=int(round(tot_pp)),
            rub=_fmt_dm_compact_num(round(tot_prub, 2)) + " ₽",
            tok=_fmt_dm_compact_num(round(tot_ptok, 2)),
        )
    )

    lines.append("")
    lines.append(i18n_t(lang, "panel.referral.partner.avail_head"))
    lines.append(i18n_t(lang, "panel.referral.partner.avail_row", bonus=bonus_balance_str))

    return "\n".join(lines)


async def _build_referral_screen(bot, tg_user_id: int, from_user) -> tuple[str, InlineKeyboardMarkup, str | None]:
    me = await bot.get_me()
    username = (me.username or "").strip()
    lang = await get_user_language(int(tg_user_id))
    if not username:
        return i18n_t(lang, "panel.referral.link_fail"), _kb_back_to_main(lang=lang), None
    ref_link = f"https://t.me/{username}?start=ref_{tg_user_id}"
    share_text = i18n_t(lang, "panel.referral.share_text")
    share_url = f"https://t.me/share/url?url={quote(ref_link, safe='')}&text={quote(share_text, safe='')}"

    async with await get_session() as session:
        user = await get_or_create_user(
            session,
            tg_user_id,
            username=getattr(from_user, "username", None),
            first_name=getattr(from_user, "first_name", None),
        )
        invited = int(getattr(user, "ref_invited_count", 0) or 0)
        paid = int(getattr(user, "ref_paid_count", 0) or 0)
        aurum_balance = float(getattr(user, "aurum_credits", 0.0) or 0.0)
        bonus_balance = float(getattr(user, "bonus_credits", 0.0) or 0.0)
        tier_dash = await referral_partner_level_dashboard(session, user, int(tg_user_id))
        now = datetime.now(timezone.utc)
        from app.services.chat_owner_premium import user_premium_subscription_snapshot

        sub_snap = user_premium_subscription_snapshot(user, now)
        promo_code = None
        pr_promo = await session.execute(
            select(PromoCode.code)
            .join(PromoCodeRedemption, PromoCode.id == PromoCodeRedemption.promo_code_id)
            .where(PromoCodeRedemption.telegram_user_id == int(tg_user_id))
            .order_by(PromoCodeRedemption.redeemed_at.desc())
            .limit(1)
        )
        row_promo = pr_promo.scalar_one_or_none()
        if row_promo:
            promo_code = str(row_promo or "").strip().upper() or None

        def _access_label(kind: str, *, levels: int) -> str:
            if kind == "full":
                return i18n_t(lang, "panel.referral.access_levels_full", levels=int(levels))
            return i18n_t(lang, "panel.referral.access_levels_free", levels=int(levels))

        def _fmt_dt(dt: datetime | None) -> str:
            if not dt:
                return "—"
            return dt.strftime("%d.%m.%Y %H:%M")

        access_block = referral_partner_access_block(
            user,
            now_utc=now,
            access_label_fn=_access_label,
            format_dt_fn=_fmt_dt,
            subscription_snapshot=sub_snap,
            promo_code=promo_code,
        )
        partner_max_lv = int(access_block.get("partner_ui_max_levels") or 1)

    access_line = str(access_block.get("access_label") or "")
    if access_block.get("subscription_active"):
        if access_block.get("subscription_forever"):
            premium_extra = i18n_t(lang, "panel.referral.premium_extra_forever")
        elif access_block.get("premium_kind") == "promo" and access_block.get("days_left") is not None:
            premium_extra = i18n_t(
                lang,
                "panel.referral.premium_extra_promo",
                code=str(access_block.get("subscription_promo_code") or "—"),
                days_left=int(access_block.get("days_left") or 0),
                active_until=str(access_block.get("active_until") or "—"),
            )
        elif access_block.get("days_left") is not None:
            premium_extra = i18n_t(
                lang,
                "panel.referral.premium_extra",
                days_left=int(access_block.get("days_left") or 0),
                active_until=str(access_block.get("active_until") or "—"),
            )
        else:
            premium_extra = i18n_t(lang, "panel.referral.premium_extra_active")
    else:
        premium_extra = i18n_t(lang, "panel.referral.premium_extra_none")
    aurum_balance_str = str(int(aurum_balance)) if aurum_balance == int(aurum_balance) else f"{aurum_balance:.2f}"
    bonus_balance_str = str(int(bonus_balance)) if bonus_balance == int(bonus_balance) else f"{bonus_balance:.2f}"
    partner_breakdown = _render_referral_partner_breakdown(
        lang, tier_dash, bonus_balance_str, max_partner_level=partner_max_lv
    )
    txt = i18n_t(
        lang,
        "panel.referral.body",
        access_line=access_line,
        premium_extra=premium_extra,
        aurum=aurum_balance_str,
        bonus=bonus_balance_str,
        partner_breakdown=partner_breakdown,
        ref_link=ref_link,
        invited=invited,
        paid=paid,
    )
    kb = InlineKeyboardBuilder()
    me = await bot.get_me()
    uname = str(getattr(me, "username", "") or "").strip()
    if uname:
        kb.row(
            InlineKeyboardButton(
                text=i18n_t(lang, "panel.referral.kb_program"),
                url=_mini_app_startapp_link(uname, "referral"),
            )
        )
    else:
        kb.button(text=i18n_t(lang, "panel.referral.kb_access_terms"), callback_data="p:ref_access")
    kb.button(text=i18n_t(lang, "panel.referral.kb_bonus_to_aurum"), callback_data="p:ref_bonus_to_aurum")
    kb.button(text=i18n_t(lang, "panel.referral.kb_share"), url=share_url)
    kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    kb.adjust(1)

    _static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    _banner_png = _static_dir / "referral_banner.png"
    _banner_jpg = _static_dir / "referral_banner.jpg"
    if _banner_png.is_file():
        banner_path = str(_banner_png)
    elif _banner_jpg.is_file():
        banner_path = str(_banner_jpg)
    else:
        banner_path = None
    return txt, kb.as_markup(), banner_path


def _kb_cancel(lang: str = "ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, "panel.kb.cancel"), callback_data=CB_CANCEL)
    b.adjust(1)
    return b.as_markup()


def _kb_main(bot_username: str | None = None, lang: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню. startapp deep-link — стабильнее web_app с прямым URL Railway."""
    uname = (bot_username or "").strip().lstrip("@")
    txt_chats = i18n_t(lang, "panel.kb.chats")
    txt_plan = i18n_t(lang, "panel.kb.plan")
    txt_ref = i18n_t(lang, "panel.kb.ref")
    txt_connect_group = i18n_t(lang, "panel.kb.connect_group")
    txt_connect_chat = i18n_t(lang, "panel.kb.connect_chat")
    b = InlineKeyboardBuilder()
    if uname:
        b.row(InlineKeyboardButton(text=txt_chats, url=_mini_app_startapp_link(uname, "chats")))
        b.row(InlineKeyboardButton(text=txt_plan, url=_mini_app_startapp_link(uname, "billing")))
    else:
        b.button(text=txt_chats, callback_data=CB_CHATS)
        b.button(text=txt_plan, callback_data=CB_BILLING)
    b.button(text=txt_ref, callback_data=CB_REF)
    if uname:
        b.row(InlineKeyboardButton(text=txt_connect_group, url=_mini_app_startapp_link(uname, "connect")))
    else:
        b.button(text=txt_connect_chat, callback_data=CB_CONNECT)
    b.adjust(1)
    return b.as_markup()


def _kb_protection(lang: str = "ru") -> InlineKeyboardMarkup:
    """ТЗ доработка Защита: Капча, Фильтры, Наказания, Новички, Стоп-слова, Публичные сообщения. Назад → управление группой."""
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, "inline.protection.kb_filters"), callback_data=CB_FILTERS)
    b.button(text=i18n_t(lang, "inline.protection.kb_punishments"), callback_data=CB_PUNISH)
    b.button(text=i18n_t(lang, "inline.protection.kb_newbies"), callback_data=CB_NEWBIE)
    b.button(text=i18n_t(lang, "inline.protection.kb_stopwords"), callback_data=CB_STOPWORDS)
    b.button(text=i18n_t(lang, "inline.protection.kb_public_alerts"), callback_data=CB_PUBLIC_ALERTS)
    b.button(text=i18n_t(lang, "inline.protection.kb_antinakrutka"), callback_data=CB_ANTINAKRUTKA)
    b.button(text=i18n_t(lang, "inline.protection.kb_back"), callback_data=CB_BACK_TO_CHAT)
    b.adjust(1, 1, 2, 2, 1, 1)
    return b.as_markup()


def _kb_public_alerts(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    """Настройки сообщений Guard (ТЗ): общий переключатель + раз в N удалений."""
    pk = "panel.public_alerts_kb"
    enabled = bool(getattr(rule, "guardian_messages_enabled", True))
    b = InlineKeyboardBuilder()
    b.button(
        text=i18n_t(lang, f"{pk}.enable") if not enabled else i18n_t(lang, f"{pk}.disable"),
        callback_data=CB_PUBLIC_ALERTS_ON if not enabled else CB_PUBLIC_ALERTS_OFF,
    )
    b.button(text=i18n_t(lang, f"{pk}.every_5"), callback_data=CB_PUBLIC_ALERTS_EVERY_5)
    b.button(text=i18n_t(lang, f"{pk}.every_10"), callback_data=CB_PUBLIC_ALERTS_EVERY_10)
    b.button(text=i18n_t(lang, f"{pk}.int_2"), callback_data=CB_PUBLIC_ALERTS_INT_2)
    b.button(text=i18n_t(lang, f"{pk}.int_5"), callback_data=CB_PUBLIC_ALERTS_INT_5)
    b.button(text=i18n_t(lang, f"{pk}.int_10"), callback_data=CB_PUBLIC_ALERTS_INT_10)
    b.button(text=i18n_t(lang, f"{pk}.back"), callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_chats_modes(lang: str = "ru") -> InlineKeyboardMarkup:
    """Подключённые чаты: выбор режима — одна группа / все группы (ТЗ правки)."""
    cu = "panel.chats_ui"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{cu}.mode_one"), callback_data=CB_CHATS_ONE)
    b.button(text=i18n_t(lang, f"{cu}.mode_all"), callback_data=CB_CHATS_ALL)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


def _kb_chat_manage(open_protection_url: str | None = None, lang: str = "ru", *, bot_username: str | None = None) -> InlineKeyboardMarkup:
    """Внутри выбранного чата: одна кнопка открытия защиты + выбор чата."""
    b = InlineKeyboardBuilder()
    uname = (bot_username or "").strip().lstrip("@")
    if uname:
        b.row(
            InlineKeyboardButton(
                text=i18n_t(lang, "panel.kb.protection_selected"),
                url=_mini_app_startapp_link(uname, "protection"),
            )
        )
    elif open_protection_url:
        b.row(
            InlineKeyboardButton(
                text=i18n_t(lang, "panel.kb.protection_selected"),
                web_app=WebAppInfo(url=open_protection_url),
            )
        )
    b.button(text=i18n_t(lang, "panel.kb.change_chat"), callback_data=CB_PICK_CHAT)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


def _kb_chats(lang: str = "ru") -> InlineKeyboardMarkup:
    """Подменю Чаты (старый: список + лог-чаты) — для совместимости."""
    cu = "panel.chats_ui"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{cu}.sub_connected"), callback_data=CB_CHATS_LIST)
    b.button(text=i18n_t(lang, f"{cu}.sub_change_chat"), callback_data=CB_PICK_CHAT)
    b.button(text=i18n_t(lang, f"{cu}.sub_logs"), callback_data=CB_CHATS_LOGS)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    b.adjust(1)
    return b.as_markup()


def _filter_policy_label(mode: str, lang: str = "ru") -> str:
    m = (mode or "").strip().lower()
    if m == "forbid":
        return i18n_t(lang, "panel.filter_policy.forbid")
    if m == "captcha":
        return i18n_t(lang, "panel.filter_policy.captcha")
    return i18n_t(lang, "panel.filter_policy.allow")


def _filter_links_mode_label(mode: str, lang: str = "ru") -> str:
    m = (mode or "").strip().lower()
    key = f"panel.filter_links.{m}"
    got = i18n_t(lang, key)
    if got != key:
        return got
    return _filter_policy_label(m, lang=lang)


def _kb_filters_main(rule: Rule, chat_title: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """ТЗ доработка: главный экран Фильтры — 8 подпунктов, Назад → Защита."""
    fk = "panel.filters_kb"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{fk}.links"), callback_data=CB_FILTER_LINKS)
    b.button(text=i18n_t(lang, f"{fk}.media"), callback_data=CB_FILTER_MEDIA)
    b.button(text=i18n_t(lang, f"{fk}.buttons"), callback_data=CB_FILTER_BUTTONS)
    b.button(text=i18n_t(lang, f"{fk}.join"), callback_data=CB_FILTER_JOIN_MSG)
    b.button(text=i18n_t(lang, f"{fk}.left"), callback_data=CB_FILTER_LEFT_MSG)
    b.button(text=i18n_t(lang, f"{fk}.silence"), callback_data=CB_FILTER_SILENCE)
    b.button(text=i18n_t(lang, f"{fk}.spam"), callback_data=CB_FILTER_SPAM)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_filter_policy(rule: Rule, key: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для Ссылки/Медиа/Кнопки: Разрешить, Проверять капчей, Запретить. Назад → Фильтры."""
    mode = getattr(rule, f"filter_{key}_mode", "allow") if key != "links" else getattr(rule, "filter_links_mode", "forbid")
    if key == "links" and not getattr(rule, "filter_links_mode", None):
        mode = "forbid" if rule.filter_links else "allow"
    fk = "panel.filters_kb"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{fk}.allow"), callback_data=f"{CB_FILTER_SET}allow:{key}")
    b.button(text=i18n_t(lang, f"{fk}.forbid"), callback_data=f"{CB_FILTER_SET}forbid:{key}")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_FILTERS)
    b.adjust(1)
    return b.as_markup()


def _kb_filter_all_captcha(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    """Проверка всех сообщений капчей: интервалы по времени, Назад → Фильтры."""
    CAPTCHA_MINUTES = (10, 60, 120, 180, 240, 360, 480, 600, 720, 1440)
    fk = "panel.filters_kb"
    b = InlineKeyboardBuilder()
    for minutes in CAPTCHA_MINUTES:
        b.button(text=_duration_option_label(minutes, lang=lang), callback_data=f"{CB_FILTER_ALL_CAPTCHA_TIME}{minutes}")
    b.button(text=i18n_t(lang, f"{fk}.disable"), callback_data=f"{CB_FILTER_ALL_CAPTCHA_TIME}0")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_FILTERS)
    b.adjust(2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()


def _kb_filter_join(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    fk = "panel.filters_kb"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{fk}.delete"), callback_data=f"{CB_FILTER_JOIN_TOGGLE}:1")
    b.button(text=i18n_t(lang, f"{fk}.keep"), callback_data=f"{CB_FILTER_JOIN_TOGGLE}:0")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_FILTERS)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_filter_left(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    fk = "panel.filters_kb"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{fk}.delete"), callback_data=f"{CB_FILTER_LEFT_TOGGLE}:1")
    b.button(text=i18n_t(lang, f"{fk}.keep"), callback_data=f"{CB_FILTER_LEFT_TOGGLE}:0")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_FILTERS)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_filter_silence(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    SILENCE_MINUTES = (10, 60, 120, 180, 240, 360, 480, 600, 720, 1440)
    fk = "panel.filters_kb"
    b = InlineKeyboardBuilder()
    for minutes in SILENCE_MINUTES:
        b.button(text=_duration_option_label(minutes, lang=lang), callback_data=f"{CB_FILTER_SILENCE_TIME}{minutes}")
    b.button(text=i18n_t(lang, f"{fk}.disable"), callback_data=f"{CB_FILTER_SILENCE_TIME}0")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_FILTERS)
    b.adjust(2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()


def _kb_filter_spam(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    fk = "panel.filters_kb"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{fk}.enable"), callback_data=f"{CB_FILTER_SPAM_TOGGLE}:1")
    b.button(text=i18n_t(lang, f"{fk}.disable"), callback_data=f"{CB_FILTER_SPAM_TOGGLE}:0")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_FILTERS)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_filters(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    """Старый экран фильтров (тумблеры) — для CB_TOGGLE_* после изменения, Назад → Защита."""
    fk = "panel.filters_kb"
    cut = i18n_t(lang, f"{fk}.cut")
    nocut = i18n_t(lang, f"{fk}.nocut")
    on = i18n_t(lang, "panel.master_on")
    off = i18n_t(lang, "panel.master_off")
    b = InlineKeyboardBuilder()
    b.button(
        text=i18n_t(lang, f"{fk}.row_links", state=(cut if rule.filter_links else nocut)),
        callback_data=CB_TOGGLE_LINKS,
    )
    b.button(
        text=i18n_t(lang, f"{fk}.row_mentions", state=(cut if rule.filter_mentions else nocut)),
        callback_data=CB_TOGGLE_MENTIONS,
    )
    b.button(
        text=i18n_t(lang, f"{fk}.row_antiedit", state=(on if rule.anti_edit else off)),
        callback_data=CB_TOGGLE_ANTIEDIT,
    )
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(2, 2)
    return b.as_markup()


def _kb_punish(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    mode = _human_mode(rule.action_mode, lang=lang)
    mute_min = int(rule.mute_minutes or 30)

    b = InlineKeyboardBuilder()

    b.button(text=i18n_t(lang, "panel.punish_kb.mode", mode=mode), callback_data=CB_MODE)

    b.button(text=i18n_t(lang, "panel.punish_kb.mute", label=_format_mute_minutes_short(mute_min, lang=lang)), callback_data=CB_SET_MUTE_MIN)

    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_PROTECTION)

    b.adjust(2, 1)
    return b.as_markup()


def _kb_newbie(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    newbie_on = bool(rule.newbie_enabled)
    newbie_min = int(rule.newbie_minutes or 10)
    st_on = i18n_t(lang, "panel.master_on")
    st_off = i18n_t(lang, "panel.master_off")

    b = InlineKeyboardBuilder()
    b.button(
        text=i18n_t(lang, "panel.newbie_kb.toggle", state=(st_on if newbie_on else st_off)),
        callback_data=CB_TOGGLE_NEWBIE,
    )
    b.button(
        text=i18n_t(lang, "panel.newbie_kb.window", minutes=newbie_min),
        callback_data=CB_SET_NEWBIE_MIN,
    )
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(2, 1)
    return b.as_markup()


def _kb_reports(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    """ТЗ Отчёты: чат отчётов (не «лог»), кнопка «Подключить чат отчётов»."""
    rk = "panel.reports_kb"
    st_on = i18n_t(lang, "panel.master_on")
    st_off = i18n_t(lang, "panel.master_off")
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{rk}.connect"), callback_data=CB_CONNECT_REPORTS)
    b.button(
        text=i18n_t(lang, f"{rk}.toggle", state=(st_on if rule.log_enabled else st_off)),
        callback_data=CB_TOGGLE_REPORTS,
    )
    b.button(text=i18n_t(lang, f"{rk}.change_chat"), callback_data=CB_PICK_REPORTS_CHAT)
    b.button(text=i18n_t(lang, f"{rk}.no_reports"), callback_data=CB_CLEAR_REPORTS_CHAT)
    b.button(text=i18n_t(lang, f"{rk}.help"), callback_data=CB_REPORTS_HELP)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_CHAT)
    b.adjust(1, 2, 2, 1)
    return b.as_markup()


def _kb_stopwords_stub(lang: str = "ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_raid_stub(lang: str = "ru") -> InlineKeyboardMarkup:
    """Анти-рейд: заглушка (Guard Premium). Кнопка «Открыть подписку» + Назад."""
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, "billing_panel.open_subscription"), callback_data=CB_BILLING)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_PROTECTION)
    b.adjust(1)
    return b.as_markup()


def _kb_antinakrutka(rule: Rule, lang: str = "ru") -> InlineKeyboardMarkup:
    """Антинакрутка: вкл/выкл, порог, окно, действие; мут — только при «оповещение + мут»."""
    ak = "panel.antinakrutka_kb"
    enabled = bool(getattr(rule, "antinakrutka_enabled", False))
    act = (getattr(rule, "antinakrutka_action", None) or "alert").strip().lower()
    if act not in ("alert", "alert_restrict"):
        act = "alert"
    b = InlineKeyboardBuilder()
    b.button(
        text=i18n_t(lang, f"{ak}.disable") if enabled else i18n_t(lang, f"{ak}.enable"),
        callback_data=CB_ANTINAKRUTKA_TOGGLE,
    )
    for n in (5, 10, 15, 20):
        b.button(text=i18n_t(lang, f"{ak}.threshold", n=n), callback_data=f"{CB_ANTINAKRUTKA_THRESH}{n}")
    for m in (3, 5, 10):
        b.button(text=i18n_t(lang, f"{ak}.window", m=m), callback_data=f"{CB_ANTINAKRUTKA_WINDOW}{m}")
    b.button(text=i18n_t(lang, f"{ak}.action_alert"), callback_data=f"{CB_ANTINAKRUTKA_ACTION}alert")
    b.button(text=i18n_t(lang, f"{ak}.action_restrict"), callback_data=f"{CB_ANTINAKRUTKA_ACTION}alert_restrict")
    if act == "alert_restrict":
        for r in (15, 30, 60):
            b.button(text=i18n_t(lang, f"{ak}.mute_min", r=r), callback_data=f"{CB_ANTINAKRUTKA_RESTRICT}{r}")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_PROTECTION)
    if act == "alert_restrict":
        b.adjust(1, 4, 3, 2, 3, 1)
    else:
        b.adjust(1, 4, 3, 2, 1)
    return b.as_markup()


def _kb_premium_plans(back_callback: str = CB_MAIN, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора периода подписки (Guard Premium) и ввод промокода."""
    b = InlineKeyboardBuilder()
    for months, _label, _price, _savings in PREMIUM_PLANS:
        b.button(
            text=i18n_t(lang, f"billing_panel.plan_btn.{months}"),
            callback_data=f"{CB_PLAN}{months}",
        )
    b.button(text=i18n_t(lang, "billing_panel.promo_btn"), callback_data=CB_PROMO_ENTER)
    b.button(text=i18n_t(lang, "billing_panel.back_btn"), callback_data=back_callback)
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
        await ensure_user_chat_limit_synced_for_tariff(session, user)
        await session.refresh(user)
        summary_ids = await get_activity_summary_chat_ids(session, user_id)
        groups_in_dashboard_scope, channels_in_dashboard_scope = await count_chat_ids_by_kind(session, summary_ids)
        groups_limit_disp = effective_group_limit(user, user_id)
        channels_limit_disp = effective_channel_limit(user, user_id)
        tariff_key = (user.tariff or "free").lower()
        is_premium = tariff_key in ("premium", "pro", "business")
        tariff_label = "PREMIUM" if is_premium else "FREE"
        sub_until = _format_subscription_until(user.subscription_until)
        aurum_credits = float(getattr(user, "aurum_credits", 0.0) or 0.0)
        aurum_credits_str = str(int(aurum_credits)) if aurum_credits == int(aurum_credits) else f"{aurum_credits:.2f}"
        bonus_credits = float(getattr(user, "bonus_credits", 0.0) or 0.0)
        bonus_credits_str = str(int(bonus_credits)) if bonus_credits == int(bonus_credits) else f"{bonus_credits:.2f}"
        lang = await get_user_language(int(user_id))
        txt = i18n_t(
            lang,
            "panel.main.body",
            tariff_label=tariff_label,
            groups_count=groups_in_dashboard_scope,
            groups_limit=groups_limit_disp,
            channels_count=channels_in_dashboard_scope,
            channels_limit=channels_limit_disp,
            sub_until=sub_until,
            aurum=aurum_credits_str,
            bonus=bonus_credits_str,
        )
        if not is_premium and is_trial_eligible(user):
            txt += "\n\n" + i18n_t(lang, "panel.main.trial_gift_hint")
        me = await bot.get_me()
        return txt, _kb_main(getattr(me, "username", None), lang=lang)


def _mini_app_base_url() -> Optional[str]:
    url = (
        os.getenv("MINI_APP_URL")
        or os.getenv("WEBAPP_URL")
        or os.getenv("RAILWAY_SERVICE_ACCOMPLISHED_CAT_URL")
        or ""
    ).strip()
    if not url:
        return None
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    return url.rstrip("/")


def _mini_app_connect_url() -> Optional[str]:
    base = _mini_app_base_url()
    if not base:
        return None
    return f"{base}/connect"


def _mini_app_chats_url() -> Optional[str]:
    base = _mini_app_base_url()
    if not base:
        return None
    return f"{base}/chats"


def _mini_app_protection_url() -> Optional[str]:
    base = _mini_app_base_url()
    if not base:
        return None
    return f"{base}/protection"


def _mini_app_reports_url() -> Optional[str]:
    base = _mini_app_base_url()
    if not base:
        return None
    return f"{base}/reports"


def _mini_app_startapp_link(bot_username: str, section: str) -> str:
    """
    Универсальный deep-link для Mini App (лучше совместим с клиентами, где web_app-кнопки работают нестабильно).
    Если задан MINI_APP_SHORT_NAME — используем прямой формат /<short_name>?startapp=...
    """
    uname = (bot_username or "").strip().lstrip("@")
    short_name = (os.getenv("MINI_APP_SHORT_NAME") or os.getenv("WEBAPP_SHORT_NAME") or "").strip().strip("/")
    safe_section = (section or "panel").strip() or "panel"
    if short_name:
        return f"https://t.me/{uname}/{short_name}?startapp={safe_section}"
    return f"https://t.me/{uname}?startapp={safe_section}"


def _mini_app_billing_url() -> Optional[str]:
    base = _mini_app_base_url()
    if not base:
        return None
    return f"{base}/?section=billing"


def _mini_app_referral_url(open_info: bool = False) -> Optional[str]:
    base = _mini_app_base_url()
    if not base:
        return None
    return f"{base}/referral?info=1" if open_info else f"{base}/referral"


def _mini_app_partner_url() -> Optional[str]:
    base = _mini_app_base_url()
    if not base:
        return None
    return f"{base}/?section=partner"


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
    lang = await get_user_language(int(user_id))
    if exclude_chat_id is not None:
        chats = [c for c in chats if c.id != exclude_chat_id]

    b = InlineKeyboardBuilder()

    if not chats:
        b.button(text=i18n_t(lang, "panel.pick_chat.connect"), callback_data=CB_CONNECT)
        b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=back_to)
        b.adjust(1)
        return b.as_markup()

    total = len(chats)
    max_page = (total - 1) // PAGE_SIZE
    page = max(0, min(page, max_page))

    chunk = chats[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    titles_to_update: Dict[int, str] = {}

    for ch in chunk:
        title = (ch.title or "").strip() or str(ch.id)
        try:
            tg_chat = await bot.get_chat(ch.id)
            fresh = (tg_chat.title or "").strip()
            if fresh:
                if fresh != (ch.title or "").strip():
                    titles_to_update[ch.id] = fresh[:255]
                title = fresh
        except Exception:
            pass
        btn = f"🛡 {title}"
        if len(btn) > 60:
            btn = btn[:57] + "…"
        b.button(text=btn, callback_data=f"{prefix}{ch.id}")

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

    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=back_to)
    b.adjust(1)
    return b.as_markup()


# Кэш chat_id, для которых уже отправили приветствие (защита от двойного my_chat_member / chat_shared)
_WELCOME_SENT_AT: Dict[int, float] = {}
_WELCOME_SENT_TTL = 120  # секунд


def _purge_old_welcome_sent() -> None:
    now = time.monotonic()
    to_del = [cid for cid, t in _WELCOME_SENT_AT.items() if now - t > _WELCOME_SENT_TTL]
    for cid in to_del:
        del _WELCOME_SENT_AT[cid]


async def _send_connect_welcome_once(bot, chat_id: int, chat_title: str, user_id: int) -> None:
    """Одно приветствие в группу + одно сообщение владельцу в личку (дедуп по chat_id)."""
    _purge_old_welcome_sent()
    if chat_id in _WELCOME_SENT_AT:
        return
    _WELCOME_SENT_AT[chat_id] = time.monotonic()
    lang = await get_user_language(int(user_id))
    try:
        default_title = i18n_t(lang, "panel.connect.unnamed_chat")
        title_esc = (chat_title or default_title).replace("*", "\\*")
        welcome = i18n_t(lang, "panel.connect.welcome_group", title=title_esc)
        await bot.send_message(chat_id, welcome, parse_mode="Markdown")

        protection_url = _mini_app_protection_url()
        reports_url = _mini_app_reports_url()
        me = await bot.get_me()
        panel_url = f"https://t.me/{me.username}?start=panel"
        protection_startapp_url = _mini_app_startapp_link(str(me.username or ""), "protection")
        reports_startapp_url = _mini_app_startapp_link(str(me.username or ""), "reports")
        kb_rows = []
        # В зеркальных/сторонних клиентах web_app-кнопки часто не открываются.
        # Для совместимости используем startapp deep-link'и (Telegram внутри сам откроет Mini App).
        kb_rows.append(
            [InlineKeyboardButton(text=i18n_t(lang, "panel.kb.open_protection"), url=protection_startapp_url)]
        )
        kb_rows.append(
            [InlineKeyboardButton(text=i18n_t(lang, "panel.kb.connect_reports"), url=reports_startapp_url)]
        )
        owner_dm = i18n_t(lang, "panel.connect.owner_dm", title=title_esc)
        await bot.send_message(
            user_id,
            owner_dm,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=kb_rows
                or [[InlineKeyboardButton(text=i18n_t(lang, "panel.kb.open_panel"), url=panel_url)]]
            ),
        )
    except Exception as e:
        logger.warning("connect welcome send failed chat=%s: %s", chat_id, e)
        _WELCOME_SENT_AT.pop(chat_id, None)


async def connect_chat_after_bot_added(
    bot, chat_id: int, chat_title: str, user_id: int, username: str | None, first_name: str | None
) -> tuple[bool, str | None]:
    """Подключить чат после добавления бота. Возвращает (успех, код_ошибки): limit | owner | log | error."""
    # Явный /start connect в группе — отменяем «ожидание чата отчётов» и гард от ложной привязки лога.
    _reports_chat_guard_until.pop(int(chat_id), None)
    _pending_reports_for.pop(int(user_id), None)
    # Не подключать как защищаемую: чужой лог или уже куда-то привязан как лог (кроме снятия ложной пометки ниже).
    try:
        async with await get_session() as session:
            cr = await session.get(Chat, chat_id)
            if cr and cr.is_log_chat:
                ow = int(getattr(cr, "owner_user_id", 0) or 0)
                if ow != int(user_id) or bool(getattr(cr, "is_active", False)):
                    return False, "log"
                await session.execute(
                    update(Chat).where(Chat.log_chat_id == int(chat_id)).values(log_chat_id=None)
                )
                cr.is_log_chat = False
                await session.commit()
            res = await session.execute(
                select(Chat.id).where(Chat.log_chat_id == int(chat_id)).limit(1)
            )
            if res.scalar_one_or_none():
                return False, "log"
    except Exception:
        pass
    try:
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
        miss_key = first_missing_i18n_key(bot_member)
        if miss_key:
            try:
                lang_rights = await get_user_language(int(user_id))
                await bot.send_message(
                    int(user_id),
                    i18n_t(lang_rights, f"panel.connect_verify.{miss_key}"),
                )
            except Exception:
                pass
            return False, "rights"
    except Exception:
        return False, "rights"
    try:
        lang = await get_user_language(int(user_id))
        async with await get_session() as session:
            await get_or_create_user(session, user_id, username=username, first_name=first_name)
            log_targets = select(Chat.log_chat_id).where(Chat.log_chat_id.is_not(None))
            can_add, current_count, limit = await can_add_chat(session, user_id)
            if not can_add:
                try:
                    await bot.send_message(
                        user_id,
                        i18n_t(lang, "panel.connect.limit", current=current_count, limit=limit),
                    )
                except Exception:
                    pass
                return False, "limit"

            chat_row = await session.get(Chat, chat_id)
            rule = await session.get(Rule, chat_id)
            owner_id = int(user_id or 0)
            if chat_row:
                ow_ok, ow_err = await apply_chat_owner_on_connect(bot, chat_row, owner_id)
                if not ow_ok:
                    try:
                        await bot.send_message(
                            user_id,
                            i18n_t(lang, "panel.connect.owner_conflict"),
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass
                    return False, ow_err or "owner"
            # Чат уже в БД как активный (например после chat_shared) — догоняем приветствие один раз
            if chat_row and chat_row.is_active and rule is not None:
                chat_row.title = chat_title
                await _set_selected_chat(session, user_id, chat_id)
                await session.commit()
                await _send_connect_welcome_once(bot, chat_id, chat_title, owner_id)
                return True, None

            if not chat_row:
                chat_row = Chat(
                    id=chat_id,
                    title=chat_title,
                    owner_user_id=owner_id,
                    is_active=True,
                    is_log_chat=False,
                )
                session.add(chat_row)
            else:
                chat_row.title = chat_title
                chat_row.is_active = True
                chat_row.is_log_chat = False
                chat_row.owner_user_id = owner_id

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
                    filter_profanity_enabled=True,
                    filter_jobs_enabled=True,
                    filter_casino_enabled=True,
                )
                session.add(rule)

            await _set_selected_chat(session, user_id, chat_id)
            await session.commit()

        await _send_connect_welcome_once(bot, chat_id, chat_title, owner_id)
        return True, None
    except Exception:
        return False, "error"


async def render_chat_manage(bot, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Экран выбранной группы: одна кнопка открытия защиты + смена чата."""
    async with await get_session() as session:
        selected = await _get_selected_chat(session, user_id)
        if not selected:
            chats = await _managed_chats(session, user_id)
            if chats:
                selected = chats[0].id
                await _set_selected_chat(session, user_id, int(selected))
            else:
                return await render_main(bot, user_id)
        chat_row = await session.get(Chat, selected)
        rule = await _get_or_create_rule(session, selected)
    title = (getattr(chat_row, "title", None) or "").strip() if chat_row else ""
    try:
        tg_chat = await bot.get_chat(selected)
        ft = (tg_chat.title or "").strip()[:255]
        if ft:
            title = ft
            async with await get_session() as session:
                row = await session.get(Chat, selected)
                if row and (row.title or "").strip() != ft:
                    row.title = ft
                    await session.commit()
    except Exception:
        pass
    if not title:
        title = await _get_chat_title(bot, selected)
    lang = await get_user_language(int(user_id))
    master_on = i18n_t(lang, "panel.master_on") if bool(getattr(rule, "master_anti_spam", True)) else i18n_t(lang, "panel.master_off")
    action = _human_mode(getattr(rule, "action_mode", "delete"), lang=lang)
    silence = int(getattr(rule, "silence_minutes", 0) or 0)
    silence_txt = (
        i18n_t(lang, "panel.chat_manage.silence_off")
        if silence <= 0
        else _format_mute_minutes_long(silence, lang=lang)
    )
    cm = "panel.chat_manage"
    txt = (
        f"{i18n_t(lang, f'{cm}.title')}\n\n"
        f"{i18n_t(lang, f'{cm}.settings_for')}: *{title}*\n"
        f"• {i18n_t(lang, f'{cm}.protection')}: *{master_on}*\n"
        f"• {i18n_t(lang, f'{cm}.mode')}: *{action}*\n"
        f"• {i18n_t(lang, f'{cm}.silence')}: *{silence_txt}*\n\n"
        f"{i18n_t(lang, f'{cm}.footer')}"
    )
    me = await bot.get_me()
    return txt, _kb_chat_manage(
        _mini_app_protection_url(),
        lang=lang,
        bot_username=getattr(me, "username", None),
    )


# =========================================================
# SHOW PANEL
# =========================================================

async def reset_and_show_private_panel(
    bot,
    user_id: int,
    *,
    cabinet_added_count: int = 0,
) -> None:
    """/start и /panel: сброс кэша панели, принудительная выдача reply-клавы (без сброса msg_id — сначала edit)."""
    uid = int(user_id)
    _cache_clear(uid)
    _DM_QUICK_KB_APPLIED_VER.pop(uid, None)
    await show_panel(
        bot,
        uid,
        send_quick_reply_keyboard=False,
        cabinet_added_count=int(cabinet_added_count or 0),
    )
    await ensure_dm_quick_reply_keyboard(bot, uid, force_refresh=True)


async def show_panel(
    bot,
    user_id: int,
    *,
    send_quick_reply_keyboard: bool = False,
    cabinet_added_count: int = 0,
) -> None:
    import logging
    logger = logging.getLogger(__name__)
    try:
        text, kb = await render_main(bot, user_id)
        n_cab = max(0, int(cabinet_added_count or 0))
        if n_cab > 0:
            lang = await _user_lang(int(user_id))
            text = f"{text}\n\n{i18n_t(lang, 'bot.start.cabinet_added', n=n_cab)}"
        await _edit_panel(bot, user_id, text, kb)
        if send_quick_reply_keyboard:
            await ensure_dm_quick_reply_keyboard(bot, user_id)
    except Exception as e:
        logger.exception("show_panel error: %s", e)
        try:
            lang = await get_user_language(int(user_id))
            err_text = str(e).lower()
            hint = ""
            if "users" in err_text or "is_log_chat" in err_text or "does not exist" in err_text:
                hint = i18n_t(lang, "panel.error.db_migration_hint")
            open_msg = i18n_t(lang, "panel.error.open_panel", hint=hint, error=repr(e))
            await bot.send_message(
                user_id,
                open_msg,
                parse_mode="Markdown",
            )
        except Exception:
            pass


# =========================================================
# COMMAND
# =========================================================


def _cmd_private_only(lang: str) -> str:
    return i18n_t(lang, "panel.cmd.private_only")


@router.message(Command("panel"))
async def panel_cmd(message: Message):
    if message.chat.type != "private":
        lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
        await message.answer(
            i18n_t(lang, "panel.cmd.panel_dm_only"),
            parse_mode="Markdown",
        )
        return
    if not message.from_user:
        return
    await reset_and_show_private_panel(message.bot, message.from_user.id)


# ТЗ: Меню команд Telegram (синяя кнопка) — /group, /groups, /buy, /support
@router.message(Command("group"))
async def cmd_group(message: Message):
    if not message.from_user:
        return
    lang = await _user_lang(message.from_user.id)
    if message.chat.type != "private":
        await message.answer(_cmd_private_only(lang))
        return
    _cache_clear(message.from_user.id)
    kb = await render_pick_chat(message.bot, message.from_user.id, page=0, back_to=CB_CHATS)
    txt = i18n_t(lang, "panel.cmd.group_pick")
    await _edit_panel(message.bot, message.from_user.id, txt, kb)


@router.message(Command("groups"))
async def cmd_groups(message: Message):
    if not message.from_user:
        return
    lang = await _user_lang(message.from_user.id)
    if message.chat.type != "private":
        await message.answer(_cmd_private_only(lang))
        return
    _cache_clear(message.from_user.id)
    txt = i18n_t(lang, "panel.cmd.groups_all_body")
    btn_prot = i18n_t(lang, "panel.cmd.groups_btn_protection")
    btn_rep = i18n_t(lang, "panel.cmd.groups_btn_reports")
    btn_back = i18n_t(lang, "panel.cmd.groups_btn_back")
    kb = InlineKeyboardBuilder()
    kb.button(text=btn_prot, callback_data="p:protection_all")
    kb.button(text=btn_rep, callback_data="p:reports_all")
    kb.button(text=btn_back, callback_data=CB_MAIN)
    kb.adjust(1)
    await _edit_panel(message.bot, message.from_user.id, txt, kb.as_markup())


async def _send_premium_screen(bot, user_id: int, back_callback: str = CB_MAIN) -> None:
    """Показать экран Guard Premium: описание + кнопки периодов подписки."""
    lang = await _user_lang(user_id)
    txt = i18n_t(lang, "billing_panel.cmd_premium_screen")
    kb = _kb_premium_plans(back_callback=back_callback, lang=lang)
    await _edit_panel(bot, user_id, txt, kb)


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    if message.chat.type != "private":
        lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
        await message.answer(_cmd_private_only(lang))
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


async def _is_full_admin_sender(session, message: Message) -> bool:
    if not message.from_user:
        return False
    u = await get_or_create_user(
        session,
        int(message.from_user.id),
        username=getattr(message.from_user, "username", None),
        first_name=getattr(message.from_user, "first_name", None),
    )
    return is_full_admin_user(u, int(message.from_user.id))


@router.message(Command("premium7"))
async def cmd_premium7(message: Message):
    if message.chat.type != "private" or not message.from_user:
        return
    lang = await _user_lang(message.from_user.id)
    await message.answer(
        i18n_t(lang, "panel.premium_cmd_disabled.7", code=DEFAULT_PREMIUM7_PROMO_CODE),
        parse_mode="Markdown",
    )


@router.message(Command("premium14"))
async def cmd_premium14(message: Message):
    if message.chat.type != "private" or not message.from_user:
        return
    lang = await _user_lang(message.from_user.id)
    await message.answer(
        i18n_t(lang, "panel.premium_cmd_disabled.14", code=DEFAULT_PREMIUM14_PROMO_CODE),
        parse_mode="Markdown",
    )


@router.message(Command("aurum1000"))
async def cmd_aurum1000(message: Message):
    if message.chat.type != "private" or not message.from_user:
        return
    lang = await _user_lang(message.from_user.id)
    await message.answer(
        i18n_t(lang, "panel.premium_cmd_disabled.aurum"),
    )


@router.message(
    F.chat.type == "private",
    F.text.func(lambda t: (t or "").strip().lower() in ("тариф", "tariff")),
)
async def cmd_text_tariff(message: Message):
    """Ответ на текст «тариф» — экран Guard Premium."""
    if not message.from_user:
        return
    _cache_clear(message.from_user.id)
    await _send_premium_screen(message.bot, message.from_user.id)


async def _try_delete_quiet(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass
    except TelegramForbiddenError as e:
        from app.services.diagnostics_incidents import record_panel_dm_delete_forbidden

        await record_panel_dm_delete_forbidden(int(chat_id), int(message_id), e)


async def _ban_from_chat_after_global_antispam(bot, chat_id: int, user_id: int) -> bool:
    """
    Исключить пользователя из текущей группы (как при входе с включённой проверкой базы).
    Не трогаем админов/создателя; уже вышедших считаем ок.
    """
    try:
        tm = await bot.get_chat_member(chat_id, user_id)
    except TelegramBadRequest as e:
        logger.warning("addantispam get_chat_member target %s: %s", user_id, e)
        return False
    if tm.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        return True
    if tm.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
        return False
    try:
        await bot.ban_chat_member(chat_id, user_id)
        return True
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning("addantispam ban_chat_member %s: %s", user_id, e)
        return False


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    Command(commands=["addantispam"], ignore_mention=True),
    F.reply_to_message,
)
async def cmd_addantispam_group(message: Message):
    """В группе: ответьте на сообщение пользователя и отправьте /addantispam — автор будет добавлен в антиспам базу."""
    if not message.from_user or not message.reply_to_message or not message.reply_to_message.from_user:
        return
    lang = await _user_lang(message.from_user.id)
    ag = "panel.addantispam_group"
    target = message.reply_to_message.from_user
    if target.is_bot:
        await message.reply(i18n_t(lang, f"{ag}.no_bots"))
        return
    try:
        mem = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    except TelegramBadRequest:
        await message.reply(i18n_t(lang, f"{ag}.mem_fail"))
        return
    except Exception as e:
        await message.reply(i18n_t(lang, f"{ag}.cmd_error", error=e))
        return

    if mem.status == ChatMemberStatus.CREATOR:
        pass
    elif mem.status == ChatMemberStatus.ADMINISTRATOR:
        if not getattr(mem, "can_restrict_members", False):
            await message.reply(
                i18n_t(lang, f"{ag}.restrict_required"),
                parse_mode="Markdown",
            )
            return
    else:
        await message.reply(i18n_t(lang, f"{ag}.admin_only"), parse_mode="Markdown")
        return

    from app.api.service import user_can_access_chat
    from app.services.global_antispam import add_to_global_antispam
    fn = (target.first_name or "").strip()
    ln = (target.last_name or "").strip()
    disp = f"{fn} {ln}".strip() or None
    un = (target.username or "").strip().lstrip("@") or None
    async with await get_session() as session:
        if not await user_can_access_chat(session, message.from_user.id, message.chat.id):
            await message.reply(i18n_t(lang, f"{ag}.not_linked"))
            return
        if not await chat_owner_has_miniapp_premium(session, message.chat.id):
            return
        cht = message.chat
        cht_title = (getattr(cht, "title", None) or "").strip().replace("«", '"').replace("»", '"')[:220]
        group_reason = f"из группы «{cht_title}»" if cht_title else f"из группы {getattr(cht, 'id', 0)}"
        added = await add_to_global_antispam(
            session,
            target.id,
            reason=group_reason,
            display_name=disp,
            username=un,
        )

    kicked = await _ban_from_chat_after_global_antispam(message.bot, message.chat.id, target.id)

    if added:
        extra = i18n_t(lang, f"{ag}.extra_kicked") if kicked else ""
        tail = "" if kicked else i18n_t(lang, f"{ag}.tail_ban_fail")
        bot_reply = await message.reply(
            i18n_t(
                lang,
                f"{ag}.added_notice",
                user_id=target.id,
                extra=extra,
                tail=tail,
            ),
            parse_mode="Markdown" if tail else None,
        )
        await _try_delete_quiet(message.bot, message.chat.id, message.message_id)
        await _try_delete_quiet(message.bot, bot_reply.chat.id, bot_reply.message_id)
    else:
        if kicked:
            bot_reply = await message.reply(
                i18n_t(lang, f"{ag}.already_kicked", user_id=target.id)
            )
            await _try_delete_quiet(message.bot, message.chat.id, message.message_id)
            await _try_delete_quiet(message.bot, bot_reply.chat.id, bot_reply.message_id)
        else:
            await message.reply(i18n_t(lang, f"{ag}.already", user_id=target.id))


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    Command(commands=["addantispam"], ignore_mention=True),
    ~F.reply_to_message,
)
async def cmd_addantispam_group_no_reply(message: Message):
    """Подсказка, если /addantispam без ответа на сообщение."""
    lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
    await message.reply(
        i18n_t(lang, "panel.addantispam_group.hint_no_reply"),
        parse_mode="Markdown",
    )


@router.message(Command("support"))
async def cmd_support(message: Message):
    if message.chat.type != "private":
        lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
        await message.answer(_cmd_private_only(lang))
        return
    lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
    await message.answer(i18n_t(lang, "panel.support.body"), parse_mode="Markdown")


@router.message(Command("guard_help"))
async def cmd_guard_help(message: Message):
    if message.chat.type != "private":
        lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
        await message.answer(_cmd_private_only(lang))
        return
    lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
    txt = i18n_t(lang, "panel.guard_help.body")
    me = await message.bot.get_me()
    uname = str(getattr(me, "username", "") or "").strip()
    if uname:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        await message.answer(
            txt,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=i18n_t(lang, "panel.guard_help.open_panel_btn"),
                    url=_mini_app_startapp_link(uname, "panel"),
                )],
            ]),
        )
    else:
        await message.answer(
            txt + i18n_t(lang, "panel.guard_help.no_url_hint"),
            parse_mode="Markdown",
        )


@router.message(Command("guard_ref"))
async def cmd_guard_ref(message: Message):
    if message.chat.type != "private":
        lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
        await message.answer(_cmd_private_only(lang))
        return
    if not message.from_user:
        return
    txt, kb, banner_path = await _build_referral_screen(message.bot, message.from_user.id, message.from_user)
    if banner_path:
        from aiogram.types import FSInputFile
        await message.answer_photo(FSInputFile(banner_path), caption=txt, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.answer(txt, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data == CB_REF)
async def cb_ref(cb: CallbackQuery):
    await cb.answer()
    if not cb.from_user:
        return
    txt, kb, banner_path = await _build_referral_screen(cb.bot, cb.from_user.id, cb.from_user)
    if banner_path:
        try:
            await cb.message.edit_media(
                media=InputMediaPhoto(media=FSInputFile(banner_path), caption=txt, parse_mode="Markdown"),
                reply_markup=kb,
            )
            _cache_set(cb.from_user.id, cb.message.message_id)
            return
        except Exception:
            try:
                await cb.message.edit_caption(caption=txt, parse_mode="Markdown", reply_markup=kb)
                _cache_set(cb.from_user.id, cb.message.message_id)
                return
            except Exception:
                pass
    await _edit_or_send(cb, txt, kb)


async def _send_dm_guard_lang_prompt(message: Message) -> None:
    """RU/EN — инлайн-кнопки выбора языка (общий код для /guard_lang и reply-клавы «Язык»)."""
    lang = await lang_from_update(message)
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "bot.lang_cmd.btn_ru"), callback_data="p:lang:set:ru")
    kb.button(text=i18n_t(lang, "bot.lang_cmd.btn_en"), callback_data="p:lang:set:en")
    kb.adjust(2)
    await message.answer(i18n_t(lang, "bot.lang_cmd.prompt"), reply_markup=kb.as_markup())


async def _send_dm_guard_tip(message: Message) -> None:
    lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
    await message.answer(i18n_t(lang, "panel.guard_tip"))


@router.message(Command("guard_lang"))
async def cmd_guard_lang(message: Message):
    if message.chat.type != "private":
        lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
        await message.answer(_cmd_private_only(lang))
        return
    await _send_dm_guard_lang_prompt(message)


@router.callback_query(F.data.startswith("p:lang:set:"))
async def cb_guard_lang_set(cb: CallbackQuery):
    from app.i18n import normalize_locale, t
    from app.services.user_locale import set_user_language

    code = normalize_locale((cb.data or "").split(":")[-1])
    user_id = int(getattr(cb.from_user, "id", 0) or 0)
    if user_id <= 0:
        await cb.answer()
        return
    try:
        await set_user_language(user_id, code)
    except Exception:
        pass
    toast = t(code, "bot.lang_cmd.saved")
    try:
        await cb.message.edit_text(toast)
    except Exception:
        try:
            await cb.message.answer(toast)
        except Exception:
            pass
    await cb.answer(toast)
    # Обновить подписи reply-клавы + главное сообщение с инлайн после смены языка (иначе остаётся старый текст/клавиатура).
    await reset_and_show_private_panel(cb.bot, user_id)


@router.message(Command("guard_tip"))
async def cmd_guard_tip(message: Message):
    if message.chat.type != "private":
        lang = await _user_lang(message.from_user.id) if message.from_user else "ru"
        await message.answer(_cmd_private_only(lang))
        return
    await _send_dm_guard_tip(message)


@router.message(F.text.in_(_DM_REPLY_LABEL_OPEN_MENU), F.chat.type == "private")
async def dm_reply_quick_open_menu(message: Message):
    """Reply «Главное меню» → то же, что явный перезход к инлайн-панели (/panel без спама литералов в клавиатуре)."""
    if not message.from_user:
        return
    await show_panel(message.bot, message.from_user.id, send_quick_reply_keyboard=False)


@router.message(F.text.in_(_DM_REPLY_LABEL_CHANGE_LANG), F.chat.type == "private")
async def dm_reply_quick_change_lang(message: Message):
    if not message.from_user:
        return
    await _send_dm_guard_lang_prompt(message)


@router.message(F.text.in_(_DM_REPLY_LABEL_SUPPORT_TIP), F.chat.type == "private")
async def dm_reply_quick_support_tip(message: Message):
    if not message.from_user:
        return
    await _send_dm_guard_tip(message)


@router.callback_query(F.data == "p:ref_access")
async def cb_ref_access(cb: CallbackQuery):
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.ref_access.body")
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "panel.ref_access.autorenew_off_btn"), callback_data="p:ref_autorenew_off")
    kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data.in_(("p:ref_bonus_to_sub", "p:ref_bonus_to_aurum")))
async def cb_ref_bonus_to_aurum(cb: CallbackQuery):
    await cb.answer()
    if not cb.from_user:
        return
    lang = await _user_lang(cb.from_user.id)
    moved = 0.0
    async with await get_session() as session:
        user = await get_or_create_user(
            session,
            cb.from_user.id,
            username=getattr(cb.from_user, "username", None),
            first_name=getattr(cb.from_user, "first_name", None),
        )
        bonus = float(getattr(user, "bonus_credits", 0.0) or 0.0)
        if bonus > 0:
            moved = round(bonus, 2)
            user.bonus_credits = round(max(0.0, bonus - moved), 2)
            user.aurum_credits = round(float(getattr(user, "aurum_credits", 0.0) or 0.0) + moved, 2)
            session.add(CreditLedger(user_id=int(user.id), delta=-moved, reason="bonus_to_aurum"))
            session.add(CreditLedger(user_id=int(user.id), delta=+moved, reason="bonus_to_aurum_target"))
            await session.commit()
    if moved <= 0:
        await cb.answer(i18n_t(lang, "panel.ref_access.bonus_empty"), show_alert=True)
    else:
        moved_str = str(int(moved)) if moved == int(moved) else f"{moved:.2f}"
        await cb.answer(i18n_t(lang, "panel.ref_access.bonus_moved", amount=moved_str), show_alert=True)
    txt, kb, _ = await _build_referral_screen(cb.bot, cb.from_user.id, cb.from_user)
    await _edit_or_send(cb, txt, kb)


@router.callback_query(F.data == "p:ref_autorenew_off")
async def cb_ref_autorenew_off(cb: CallbackQuery):
    lang = await _user_lang(cb.from_user.id)
    await cb.answer(i18n_t(lang, "panel.ref_access.done_toast"))
    txt = i18n_t(lang, "panel.ref_access.autorenew_off_body")
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


# =========================================================
# CALLBACKS: NAV
# =========================================================

@router.callback_query(F.data == "noop:0")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data == CB_MAIN)
async def cb_main(cb: CallbackQuery):
    await cb.answer()
    uid = int(cb.from_user.id)
    text, kb = await render_main(cb.bot, uid)
    has_referral_media = bool(
        getattr(cb.message, "photo", None)
        or getattr(cb.message, "video", None)
        or getattr(cb.message, "animation", None)
        or getattr(cb.message, "document", None)
    )
    if has_referral_media:
        new_msg = await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        _cache_set(uid, new_msg.message_id)
        try:
            await cb.message.delete()
        except Exception:
            pass
        return
    await _edit_or_send(cb, text, kb)


async def _render_protection_screen(bot, user_id: int, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура экрана Защита: перечислены все текущие настройки раздела."""
    lang = await _user_lang(user_id)
    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
        rule = await _get_or_create_rule(session, chat_id)
        # количество стоп-слов для чата
        r = await session.execute(select(func.count()).select_from(StopWord).where(StopWord.chat_id == chat_id))
        stopwords_count = r.scalar() or 0

    title = (getattr(chat_row, "title", None) or "").strip() if chat_row else str(chat_id)
    if not title:
        title = await _get_chat_title(bot, chat_id)

    on_lbl = i18n_t(lang, "inline.protection.on")
    off_lbl = i18n_t(lang, "inline.protection.off")
    del_lbl = i18n_t(lang, "inline.protection.delete_act")
    keep_lbl = i18n_t(lang, "inline.protection.keep_act")

    links_mode = _get_filter_links_mode(rule)
    links_label = _filter_links_mode_label(links_mode, lang=lang)
    media_mode = getattr(rule, "filter_media_mode", "allow")
    media_label = _filter_policy_label(media_mode, lang=lang)
    buttons_mode = getattr(rule, "filter_buttons_mode", "allow")
    buttons_label = _filter_policy_label(buttons_mode, lang=lang)
    join_msg = del_lbl if getattr(rule, "delete_join_messages", True) else keep_lbl
    left_msg = del_lbl if getattr(rule, "delete_left_messages", True) else keep_lbl
    silence_m = getattr(rule, "silence_minutes", 0) or 0
    silence = off_lbl if silence_m == 0 else _format_mute_minutes_long(silence_m, lang=lang)
    anti_spam = on_lbl if getattr(rule, "master_anti_spam", True) else off_lbl
    punish_mode = _human_mode(getattr(rule, "action_mode", "delete"), lang=lang)
    mute_m = int(rule.mute_minutes or 30)
    newbie_on = on_lbl if rule.newbie_enabled else off_lbl
    newbie_m = int(rule.newbie_minutes or 10)
    if stopwords_count:
        stopwords_str = i18n_t(lang, "inline.protection.stopwords_words", count=stopwords_count)
    else:
        stopwords_str = i18n_t(lang, "inline.protection.stopwords_not_set")
    gm_on = on_lbl if getattr(rule, "guardian_messages_enabled", True) else off_lbl
    every_n = getattr(rule, "public_alerts_every_n", 5)
    interval_sec = getattr(rule, "public_alerts_min_interval_sec", 300)
    interval_min = interval_sec // 60

    mute_for = i18n_t(lang, "inline.protection.mute_for")
    newbie_win = i18n_t(lang, "inline.protection.newbie_window_min")
    every_n_line = i18n_t(lang, "inline.protection.every_n_deletions", n=every_n, m=interval_min)
    min_word = i18n_t(lang, "panel.minute_abbr")

    txt = (
        f"{i18n_t(lang, 'inline.protection.screen_title')}\n\n"
        f"{i18n_t(lang, 'inline.protection.chat_label')}: *{title}*\n\n"
        f"{i18n_t(lang, 'inline.protection.current_settings')}\n"
        f"• {i18n_t(lang, 'inline.protection.links')}: *{links_label}*\n"
        f"• {i18n_t(lang, 'inline.protection.media')}: *{media_label}*\n"
        f"• {i18n_t(lang, 'inline.protection.buttons')}: *{buttons_label}*\n"
        f"• {i18n_t(lang, 'inline.protection.join_msg')}: *{join_msg}*\n"
        f"• {i18n_t(lang, 'inline.protection.left_msg')}: *{left_msg}*\n"
        f"• {i18n_t(lang, 'inline.protection.silence')}: *{silence}*\n"
        f"• {i18n_t(lang, 'inline.protection.antispam')}: *{anti_spam}*\n"
        f"• {i18n_t(lang, 'inline.protection.punishments')}: *{punish_mode}*, {mute_for} *{_format_mute_minutes_long(mute_m, lang=lang)}*\n"
        f"• {i18n_t(lang, 'inline.protection.newbies')}: *{newbie_on}*, {newbie_win} *{newbie_m}* {min_word}\n"
        f"• {i18n_t(lang, 'inline.protection.stopwords_label')}: *{stopwords_str}*\n"
        f"• {i18n_t(lang, 'inline.protection.guard_messages')}: *{gm_on}*, {every_n_line}\n"
        f"• {i18n_t(lang, 'inline.protection.antinakrutka')}: *{on_lbl if getattr(rule, 'antinakrutka_enabled', False) else off_lbl}*\n"
        f"• {i18n_t(lang, 'inline.protection.antispam_db')}: *{on_lbl if getattr(rule, 'use_global_antispam_db', False) else off_lbl}*\n"
        f"• {i18n_t(lang, 'inline.protection.hard_dict')}: "
        f"{i18n_t(lang, 'inline.protection.profanity_short')} *{on_lbl if getattr(rule, 'filter_profanity_enabled', False) else off_lbl}*, "
        f"{i18n_t(lang, 'inline.protection.jobs_short')} *{on_lbl if getattr(rule, 'filter_jobs_enabled', False) else off_lbl}*, "
        f"{i18n_t(lang, 'inline.protection.casino_short')} *{on_lbl if getattr(rule, 'filter_casino_enabled', False) else off_lbl}*\n\n"
        f"{i18n_t(lang, 'inline.protection.select_below')}"
    )
    return txt, _kb_protection(lang=lang)


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
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_off = (
        i18n_t(lang, "panel.master_on")
        if getattr(rule, "first_message_captcha_enabled", False)
        else i18n_t(lang, "panel.master_off")
    )
    txt = i18n_t(lang, "panel.screens.captcha_first", on_off=on_off)
    ck = "panel.captcha_first_kb"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{ck}.enable"), callback_data=CB_CAPTCHA_FIRST_ON)
    b.button(text=i18n_t(lang, f"{ck}.disable"), callback_data=CB_CAPTCHA_FIRST_OFF)
    b.button(text=i18n_t(lang, f"{ck}.back"), callback_data=CB_BACK_TO_PROTECTION)
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
    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.screens.raid") + i18n_t(lang, "billing_panel.feature_block")
    await _edit_or_send(cb, txt, _kb_raid_stub(lang=lang))


@router.callback_query(F.data == CB_ANTINAKRUTKA)
async def cb_antinakrutka(cb: CallbackQuery):
    """📈 Антинакрутка: оповещение и реакция на массовый вход."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_off = (
        i18n_t(lang, "panel.master_on")
        if getattr(rule, "antinakrutka_enabled", False)
        else i18n_t(lang, "panel.master_off")
    )
    th = int(getattr(rule, "antinakrutka_joins_threshold", 10) or 10)
    win = int(getattr(rule, "antinakrutka_window_minutes", 5) or 5)
    act = getattr(rule, "antinakrutka_action", "alert") or "alert"
    rmin = int(getattr(rule, "antinakrutka_restrict_minutes", 30) or 30)
    sc = "panel.screens"
    act_lbl = (
        i18n_t(lang, f"{sc}.antinakrutka_act_restrict")
        if act == "alert_restrict"
        else i18n_t(lang, f"{sc}.antinakrutka_act_alert")
    )
    mute_line = (
        i18n_t(lang, f"{sc}.antinakrutka_mute_line", mute=_format_mute_minutes_long(rmin, lang=lang)) + "\n\n"
        if act == "alert_restrict"
        else ""
    )
    txt = i18n_t(
        lang,
        f"{sc}.antinakrutka",
        on_off=on_off,
        th=th,
        win=win,
        action=act_lbl,
        mute_line=mute_line,
    )
    await _edit_or_send(cb, txt, _kb_antinakrutka(rule, lang=lang))


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
    """📢 Сообщения Guard (ТЗ Напоминания): вкл/выкл + раз в N удалений, не чаще 72ч/30мин."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_off = (
        i18n_t(lang, "panel.master_on")
        if getattr(rule, "guardian_messages_enabled", True)
        else i18n_t(lang, "panel.master_off")
    )
    every = getattr(rule, "public_alerts_every_n", 5)
    interval_sec = getattr(rule, "public_alerts_min_interval_sec", 300)
    interval_min = interval_sec // 60
    sc = "panel.screens"
    txt = i18n_t(
        lang,
        f"{sc}.public_alerts",
        on_off=on_off,
        every=every,
        interval_min=interval_min,
    )
    await _edit_or_send(cb, txt, _kb_public_alerts(rule, lang=lang))


@router.callback_query(F.data == CB_PUBLIC_ALERTS_ON)
async def cb_public_alerts_on(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.guardian_messages_enabled = True
        rule.public_alerts_enabled = True
        await session.commit()
    txt = i18n_t(lang, "panel.screens.public_alerts_on_toast")
    await _edit_or_send(cb, txt, _kb_public_alerts(rule, lang=lang))


@router.callback_query(F.data == CB_PUBLIC_ALERTS_OFF)
async def cb_public_alerts_off(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.guardian_messages_enabled = False
        rule.public_alerts_enabled = False
        await session.commit()
    txt = i18n_t(lang, "panel.screens.public_alerts_off_toast")
    await _edit_or_send(cb, txt, _kb_public_alerts(rule, lang=lang))


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
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.public_alerts_every_n = n
        await session.commit()
    on_off = (
        i18n_t(lang, "panel.master_on")
        if getattr(rule, "guardian_messages_enabled", True)
        else i18n_t(lang, "panel.master_off")
    )
    txt = i18n_t(lang, "panel.screens.public_alerts_every", n=n, on_off=on_off)
    await _edit_or_send(cb, txt, _kb_public_alerts(rule, lang=lang))


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
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.public_alerts_min_interval_sec = sec
        await session.commit()
    min_val = sec // 60
    txt = i18n_t(lang, "panel.screens.public_alerts_interval", min_val=min_val)
    await _edit_or_send(cb, txt, _kb_public_alerts(rule, lang=lang))


@router.callback_query(F.data == CB_BILLING)
async def cb_billing(cb: CallbackQuery):
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        user = await get_or_create_user(session, cb.from_user.id)
        await ensure_user_chat_limit_synced_for_tariff(session, user)
        await session.refresh(user)
        count = len(await _managed_chats(session, cb.from_user.id))
    t = (user.tariff or "free").lower()
    tariff_label = "PREMIUM" if t in ("premium", "pro", "business") else "FREE"
    sub_until = _format_subscription_until(user.subscription_until)
    limit = effective_chat_limit(user, cb.from_user.id)
    txt = (
        f"{i18n_t(lang, 'billing_panel.title')}\n\n"
        f"{i18n_t(lang, 'billing_panel.tariff_line', label=tariff_label)}\n"
        f"{i18n_t(lang, 'billing_panel.chats_count', count=count, limit=limit)}\n"
        f"{i18n_t(lang, 'billing_panel.subscription_until', until=sub_until)}\n\n"
        f"{i18n_t(lang, 'billing_panel.description_body')}"
    )
    kb = _kb_premium_plans(back_callback=CB_MAIN, lang=lang)
    await _edit_or_send(cb, txt, kb)


@router.callback_query(F.data == CB_PROMO_ENTER)
async def cb_promo_enter(cb: CallbackQuery):
    """Запрос ввода промокода Premium."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    _pending_promo[cb.from_user.id] = True
    await cb.message.answer(
        i18n_t(lang, "billing_panel.promo_prompt"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith(CB_PLAN))
async def cb_plan_select(cb: CallbackQuery):
    """Выбор периода подписки (1, 3, 6, 12, 24 мес): ЮKassa или заглушка."""
    await cb.answer()
    if cb.data == CB_PLAN_COMPARE:
        await _send_premium_screen(cb.bot, cb.from_user.id)
        return
    try:
        months = int(cb.data.replace(CB_PLAN, ""))
    except ValueError:
        return
    lang = await _user_lang(cb.from_user.id)
    fallback_lbl = i18n_t(lang, "panel.plan.months_short", months=months)
    plan_label = i18n_t(lang, f"billing_panel.plan_btn.{months}")
    if plan_label == f"billing_panel.plan_btn.{months}":
        plan_label = fallback_lbl

    from app.services.payments_yookassa import create_yookassa_subscription_payment, yookassa_configured

    if yookassa_configured():
        try:
            async with await get_session() as session:
                pay_url = await create_yookassa_subscription_payment(
                    session,
                    cb.from_user.id,
                    months,
                    username=cb.from_user.username,
                    first_name=cb.from_user.first_name,
                )
        except ValueError:
            await cb.message.answer(i18n_t(lang, "billing_panel.plan_invalid"))
            return
        except Exception:
            logger.exception("YooKassa create from bot panel")
            await cb.message.answer(i18n_t(lang, "billing_panel.yookassa_fail"))
            return
        txt = i18n_t(lang, "billing_panel.pay_screen", label=plan_label)
        kb = InlineKeyboardBuilder()
        kb.button(text=i18n_t(lang, "billing_panel.pay_btn"), url=pay_url)
        kb.button(text=i18n_t(lang, "billing_panel.back_to_plans"), callback_data=CB_BILLING)
        kb.adjust(1)
        await _edit_or_send(cb, txt, kb.as_markup())
        return

    txt = i18n_t(lang, "billing_panel.no_yookassa", label=plan_label)
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "billing_panel.back_to_plans"), callback_data=CB_BILLING)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == CB_CHATS)
async def cb_chats_menu(cb: CallbackQuery):
    """Подключённые чаты: сразу экран выбранной группы (без режима one/all)."""
    await cb.answer()
    text, kb = await render_chat_manage(cb.bot, cb.from_user.id)
    await _edit_or_send(cb, text, kb)


@router.callback_query(F.data == CB_CHATS_ONE)
async def cb_chats_one(cb: CallbackQuery):
    """Управление одной группой: список чатов, Back → выбор режима."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_CHATS)
    await _edit_or_send(cb, i18n_t(lang, "panel.nav_chats.one_pick_chat"), kb)


@router.callback_query(F.data == CB_CHATS_ALL)
async def cb_chats_all(cb: CallbackQuery):
    """Управление всеми группами: выбор чата для защиты или отчётов."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.nav_chats.all_intro")
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "panel.nav_chats.all_btn_protection"), callback_data="p:protection_all")
    kb.button(text=i18n_t(lang, "panel.nav_chats.all_btn_reports"), callback_data="p:reports_all")
    kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_CHATS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == "p:protection_all")
async def cb_protection_all(cb: CallbackQuery):
    """Защита для всех: выбор чата из списка → экран управления защитой."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
    if not chats:
        txt = i18n_t(lang, "panel.nav_chats.no_chats_protection")
        kb = InlineKeyboardBuilder()
        kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_CHATS_ALL)
        kb.adjust(1)
        await _edit_or_send(cb, txt, kb.as_markup())
        return
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_CHATS_ALL)
    await _edit_or_send(cb, i18n_t(lang, "panel.nav_chats.protection_all_pick"), kb)


@router.callback_query(F.data == "p:reports_all")
async def cb_reports_all(cb: CallbackQuery):
    """Отчёты для всех: выбор чата из списка → экран отчётов для этого чата."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
    if not chats:
        txt = i18n_t(lang, "panel.nav_chats.no_chats_reports")
        kb = InlineKeyboardBuilder()
        kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_CHATS_ALL)
        kb.adjust(1)
        await _edit_or_send(cb, txt, kb.as_markup())
        return
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_CHATS_ALL)
    await _edit_or_send(cb, i18n_t(lang, "panel.nav_chats.reports_all_pick"), kb)


@router.callback_query(F.data == CB_CHATS_LIST)
async def cb_chats_list(cb: CallbackQuery):
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
    if not chats:
        txt = i18n_t(lang, "panel.nav_chats.list_empty")
        kb = InlineKeyboardBuilder()
        kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_CHATS)
        kb.adjust(1)
        await _edit_or_send(cb, txt, kb.as_markup())
        return
    lines = [f"• { (c.title or '').strip() or str(c.id) }" for c in chats[:50]]
    txt = i18n_t(lang, "panel.nav_chats.list_title") + "\n\n" + "\n".join(lines)
    if len(chats) > 50:
        txt += "\n" + i18n_t(lang, "panel.nav_chats.list_more", n=len(chats) - 50)
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_CHATS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == CB_CHATS_LOGS)
async def cb_chats_logs(cb: CallbackQuery):
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        log_chats = await _user_log_chats(session, cb.from_user.id)
    if not log_chats:
        txt = i18n_t(lang, "panel.nav_chats.logs_empty")
    else:
        lines = [f"• {(c.title or '').strip() or str(c.id)}" for c in log_chats[:50]]
        txt = i18n_t(lang, "panel.nav_chats.logs_title") + "\n\n" + "\n".join(lines)
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_CHATS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


@router.callback_query(F.data == CB_PICK_CHAT)
async def cb_pick_chat(cb: CallbackQuery):
    """Сменить чат — список с возвратом в «Управление группой»."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    kb = await render_pick_chat(cb.bot, cb.from_user.id, page=0, back_to=CB_BACK_TO_CHAT)
    await _edit_or_send(cb, i18n_t(lang, "panel.nav_chats.pick_change"), kb)


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
    lang = await _user_lang(cb.from_user.id)
    msg_text = cb.message.text or i18n_t(lang, "panel.nav_chats.pick_default")
    await _edit_or_send(cb, msg_text, kb)


@router.callback_query(F.data.startswith(CB_SET_CHAT))
async def cb_set_chat(cb: CallbackQuery):
    """Выбор чата из списка → экран «Управление группой» (ТЗ правки)."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    try:
        chat_id = int(cb.data.split(":")[-1])
    except Exception:
        await cb.answer(i18n_t(lang, "panel.alerts.bad_payload"), show_alert=True)
        return

    async with await get_session() as session:
        chats = await _managed_chats(session, cb.from_user.id)
        if chat_id not in {c.id for c in chats}:
            await cb.answer(i18n_t(lang, "panel.alerts.not_your_chat"), show_alert=True)
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
    lang = await _user_lang(cb.from_user.id)
    from app.services.chat_cleanup import clean_deleted_accounts
    try:
        async with await get_session() as session:
            kicked, checked = await clean_deleted_accounts(cb.bot, session, chat_id)
        title = await _get_chat_title(cb.bot, chat_id)
        cl = "panel.cleanup"
        text = (
            f"{i18n_t(lang, f'{cl}.title')}\n\n"
            f"{i18n_t(lang, f'{cl}.chat')}: *{title}*\n"
            f"{i18n_t(lang, f'{cl}.checked')}: *{checked}*\n"
            f"{i18n_t(lang, f'{cl}.kicked')}: *{kicked}*"
        )
    except Exception as e:
        text = i18n_t(lang, "panel.cleanup.error", error=str(e))
    me = await cb.bot.get_me()
    await _edit_or_send(
        cb,
        text,
        _kb_chat_manage(
            _mini_app_protection_url(),
            lang=lang,
            bot_username=getattr(me, "username", None),
        ),
    )


@router.callback_query(F.data == CB_GLOBAL_ANTISPAM)
async def cb_global_antispam(cb: CallbackQuery):
    """Экран антиспам базы: переключатель использования в чате + список + добавить."""
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    ga = "panel.global_antispam"
    from app.services.global_antispam import list_global_antispam_for_api
    async with await get_session() as session:
        if not await miniapp_actor_has_global_antispam_access(session, int(cb.from_user.id)):
            await cb.answer(i18n_t(lang, "panel.global_antispam.premium_required"), show_alert=True)
            return
        if not await chat_owner_has_miniapp_premium(session, int(chat_id)):
            await cb.answer(i18n_t(lang, "panel.global_antispam.owner_premium_required"), show_alert=True)
            return
        rule = await _get_or_create_rule(session, chat_id)
        use_db = bool(getattr(rule, "use_global_antispam_db", False))
        items = await list_global_antispam_for_api(session, limit=30)
    on_off = i18n_t(lang, "panel.master_on" if use_db else "panel.master_off")
    txt = i18n_t(lang, f"{ga}.title") + "\n\n" + i18n_t(lang, f"{ga}.body", on_off=on_off, count=len(items))
    if items:
        lines = []
        for i, row in enumerate(items[:15], 1):
            label = (row.get("display_label") or str(row.get("user_id", "")))[:48]
            reason = (row.get("reason_display") or row.get("reason") or "").strip() or "—"
            lines.append(i18n_t(lang, f"{ga}.list_line", i=i, label=label, reason=reason[:36]))
        txt += "\n\n" + "\n".join(lines)
    b = InlineKeyboardBuilder()
    b.button(
        text=i18n_t(lang, f"{ga}.toggle_disable" if use_db else f"{ga}.toggle_enable"),
        callback_data=CB_GLOBAL_ANTISPAM_TOGGLE,
    )
    b.button(text=i18n_t(lang, f"{ga}.add_by_id"), callback_data=CB_GLOBAL_ANTISPAM_ADD)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_CHAT)
    b.adjust(1)
    await _edit_or_send(cb, txt, b.as_markup())
    await cb.answer()


@router.callback_query(F.data == CB_GLOBAL_ANTISPAM_TOGGLE)
async def cb_global_antispam_toggle(cb: CallbackQuery):
    """Вкл/выкл использование глобальной антиспам базы в выбранном чате."""
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        if not await miniapp_actor_has_global_antispam_access(session, int(cb.from_user.id)):
            await cb.answer(i18n_t(lang, "panel.global_antispam.premium_required"), show_alert=True)
            return
        if not await chat_owner_has_miniapp_premium(session, int(chat_id)):
            await cb.answer(i18n_t(lang, "panel.global_antispam.owner_premium_required"), show_alert=True)
            return
        rule = await _get_or_create_rule(session, chat_id)
        rule.use_global_antispam_db = not getattr(rule, "use_global_antispam_db", False)
        await session.commit()
    await cb_global_antispam(cb)


@router.callback_query(F.data == CB_GLOBAL_ANTISPAM_ADD)
async def cb_global_antispam_add(cb: CallbackQuery):
    """Запросить ввод user_id для добавления в антиспам базу."""
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        if not await miniapp_actor_has_global_antispam_access(session, int(cb.from_user.id)):
            await cb.answer(i18n_t(lang, "panel.global_antispam.premium_required"), show_alert=True)
            return
        if not await chat_owner_has_miniapp_premium(session, int(chat_id)):
            await cb.answer(i18n_t(lang, "panel.global_antispam.owner_premium_required"), show_alert=True)
            return
    await cb.answer()
    _pending_antispam_add[cb.from_user.id] = True
    await cb.message.answer(
        i18n_t(lang, "panel.global_antispam.add_prompt"),
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
    lang = await _user_lang(cb.from_user.id)
    ts = "panel.transfer_settings"
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id or chat_id == target_chat_id:
        await cb.answer(i18n_t(lang, f"{ts}.pick_other"), show_alert=True)
        return
    from app.api.service import user_can_access_chat, copy_rule_to_chat
    async with await get_session() as session:
        ok = await user_can_access_chat(session, cb.from_user.id, target_chat_id)
        if not ok:
            await cb.answer(i18n_t(lang, f"{ts}.no_access_target"), show_alert=True)
            return
        try:
            await copy_rule_to_chat(session, chat_id, target_chat_id)
        except ValueError as e:
            await cb.answer(str(e), show_alert=True)
            return
    title_src = await _get_chat_title(cb.bot, chat_id)
    title_dst = await _get_chat_title(cb.bot, target_chat_id)
    text = i18n_t(lang, f"{ts}.done", src=title_src, dst=title_dst)
    me = await cb.bot.get_me()
    await _edit_or_send(
        cb,
        text,
        _kb_chat_manage(
            _mini_app_protection_url(),
            lang=lang,
            bot_username=getattr(me, "username", None),
        ),
    )


@router.callback_query(F.data == CB_PROFANITY)
async def cb_profanity(cb: CallbackQuery):
    """Экран «Жёсткий словарь»: категории с отдельными тумблерами."""
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)

    def _onoff(v: bool) -> str:
        return i18n_t(lang, "panel.master_on" if v else "panel.master_off")

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        use_mat = bool(getattr(rule, "filter_profanity_enabled", False))
        use_jobs = bool(getattr(rule, "filter_jobs_enabled", False))
        use_casino = bool(getattr(rule, "filter_casino_enabled", False))
    pd = "panel.profanity_dm"
    txt = i18n_t(
        lang,
        f"{pd}.body",
        mat=_onoff(use_mat),
        jobs=_onoff(use_jobs),
        casino=_onoff(use_casino),
    )
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, f"{pd}.btn_mat", on_off=_onoff(use_mat)), callback_data=CB_PROFANITY_MAT_TOGGLE)
    b.button(text=i18n_t(lang, f"{pd}.btn_jobs", on_off=_onoff(use_jobs)), callback_data=CB_PROFANITY_JOBS_TOGGLE)
    b.button(text=i18n_t(lang, f"{pd}.btn_casino", on_off=_onoff(use_casino)), callback_data=CB_PROFANITY_CASINO_TOGGLE)
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_BACK_TO_CHAT)
    b.adjust(1)
    await _edit_or_send(cb, txt, b.as_markup())


@router.callback_query(F.data == CB_PROFANITY_MAT_TOGGLE)
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


@router.callback_query(F.data == CB_PROFANITY_JOBS_TOGGLE)
async def cb_profanity_jobs_toggle(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.filter_jobs_enabled = not getattr(rule, "filter_jobs_enabled", False)
        await session.commit()
    await cb_profanity(cb)


@router.callback_query(F.data == CB_PROFANITY_CASINO_TOGGLE)
async def cb_profanity_casino_toggle(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
        rule.filter_casino_enabled = not getattr(rule, "filter_casino_enabled", False)
        await session.commit()
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
    lang = await _user_lang(cb.from_user.id)
    await _edit_or_send(
        cb,
        i18n_t(lang, "panel.copy_settings_intro", title=title),
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
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    title = ""
    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
        title = (getattr(chat_row, "title", None) or "").strip() if chat_row else ""
    if not title:
        title = await _get_chat_title(cb.bot, chat_id)
    fi = "panel.filters_intro"
    txt = i18n_t(lang, f"{fi}.main", title=title)
    await _edit_or_send(cb, txt, _kb_filters_main(rule, title, lang=lang))


def _get_filter_links_mode(rule: Rule) -> str:
    mode = getattr(rule, "filter_links_mode", None)
    if mode in (
        "allow",
        "captcha",
        "forbid",
        "delete_all",
        "telegram_only",
        "smart",
        "open_blacklist",
        "allow_except_global",
    ):
        return mode
    return "forbid" if rule.filter_links else "allow"


@router.callback_query(F.data == CB_FILTER_LINKS)
async def cb_filter_links(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mode = _get_filter_links_mode(rule)
    fi = "panel.filters_intro"
    txt = i18n_t(lang, f"{fi}.links", state=_filter_links_mode_label(mode, lang=lang))
    await _edit_or_send(cb, txt, _kb_filter_policy(rule, "links", lang=lang))


@router.callback_query(F.data == CB_FILTER_MEDIA)
async def cb_filter_media(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mode = getattr(rule, "filter_media_mode", "allow")
    fi = "panel.filters_intro"
    txt = i18n_t(lang, f"{fi}.media", state=_filter_policy_label(mode, lang=lang))
    await _edit_or_send(cb, txt, _kb_filter_policy(rule, "media", lang=lang))


@router.callback_query(F.data == CB_FILTER_BUTTONS)
async def cb_filter_buttons(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mode = getattr(rule, "filter_buttons_mode", "allow")
    fi = "panel.filters_intro"
    txt = i18n_t(lang, f"{fi}.buttons", state=_filter_policy_label(mode, lang=lang))
    await _edit_or_send(cb, txt, _kb_filter_policy(rule, "buttons", lang=lang))


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
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mins = getattr(rule, "all_captcha_minutes", 0) or 0
    fi = "panel.filters_intro"
    if mins == 0:
        state = i18n_t(lang, "panel.master_off")
    else:
        state = i18n_t(lang, f"{fi}.all_captcha_on", mins=mins)
    txt = i18n_t(lang, f"{fi}.all_captcha", state=state)
    await _edit_or_send(cb, txt, _kb_filter_all_captcha(rule, lang=lang))


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
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    delete_ = getattr(rule, "delete_join_messages", True)
    fi = "panel.filters_intro"
    state = i18n_t(lang, f"{fi}.del" if delete_ else f"{fi}.keep")
    txt = i18n_t(lang, f"{fi}.join", state=state)
    await _edit_or_send(cb, txt, _kb_filter_join(rule, lang=lang))


@router.callback_query(F.data == CB_FILTER_LEFT_MSG)
async def cb_filter_left_msg(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    delete_ = getattr(rule, "delete_left_messages", True)
    fi = "panel.filters_intro"
    state = i18n_t(lang, f"{fi}.del" if delete_ else f"{fi}.keep")
    txt = i18n_t(lang, f"{fi}.left", state=state)
    await _edit_or_send(cb, txt, _kb_filter_left(rule, lang=lang))


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


@router.callback_query(F.data.startswith(CB_FILTER_LEFT_TOGGLE))
async def cb_filter_left_toggle(cb: CallbackQuery):
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
        rule.delete_left_messages = bool(val)
        await session.commit()
    await cb_filter_left_msg(cb)


@router.callback_query(F.data == CB_FILTER_SILENCE)
async def cb_filter_silence(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    mins = getattr(rule, "silence_minutes", 0) or 0
    fi = "panel.filters_intro"
    if mins == 0:
        state = i18n_t(lang, "panel.master_off")
    else:
        state = i18n_t(lang, f"{fi}.silence_on", mins=mins)
    txt = i18n_t(lang, f"{fi}.silence", state=state)
    await _edit_or_send(cb, txt, _kb_filter_silence(rule, lang=lang))


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
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)
    on_ = getattr(rule, "master_anti_spam", True)
    state = i18n_t(lang, "panel.master_on" if on_ else "panel.master_off")
    fi = "panel.filters_intro"
    txt = i18n_t(lang, f"{fi}.spam", state=state)
    await _edit_or_send(cb, txt, _kb_filter_spam(rule, lang=lang))


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

    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.punish_intro")
    await _edit_or_send(cb, txt, _kb_punish(rule, lang=lang))


@router.callback_query(F.data == CB_NEWBIE)
async def cb_newbie_menu(cb: CallbackQuery):
    await cb.answer()
    chat_id = await _get_selected_or_alert(cb)
    if not chat_id:
        return

    async with await get_session() as session:
        rule = await _get_or_create_rule(session, chat_id)

    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.newbie_intro")
    await _edit_or_send(cb, txt, _kb_newbie(rule, lang=lang))


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
    lang = await _user_lang(cb.from_user.id)
    reports_chat_id = getattr(chat_row, "log_chat_id", None) if chat_row else None
    reports_where = i18n_t(lang, "panel.reports_not_selected")
    if reports_chat_id:
        try:
            reports_where = (await cb.bot.get_chat(reports_chat_id)).title or str(reports_chat_id)
        except Exception:
            reports_where = str(reports_chat_id)
    state = i18n_t(lang, "panel.master_on" if rule.log_enabled else "panel.master_off")
    txt = i18n_t(
        lang,
        "panel.reports_intro",
        group_title=group_title,
        reports_where=reports_where,
        state=state,
    )
    await _edit_or_send(cb, txt, _kb_reports(rule, lang=lang))


@router.callback_query(F.data == CB_STOPWORDS)
async def cb_stopwords(cb: CallbackQuery):
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.stopwords_stub")
    await _edit_or_send(cb, txt, _kb_stopwords_stub(lang=lang))


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

    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.pending_prompt.mute")
    await _edit_or_send(cb, txt, _kb_cancel(lang=lang))


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

    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.pending_prompt.newbie")
    await _edit_or_send(cb, txt, _kb_cancel(lang=lang))


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
    lang = await _user_lang(cb.from_user.id)
    rf = "panel.reports_flow"
    _pending_reports_for[cb.from_user.id] = protected_chat_id
    try:
        me = await cb.bot.get_me()
        username = me.username or "bot"
        pick_url = f"https://t.me/{username}?startgroup=reportschat_{protected_chat_id}"
        await dm_reply_keyboard_removed_send(cb.bot, cb.from_user.id)
        kb = InlineKeyboardBuilder()
        kb.button(text=i18n_t(lang, f"{rf}.btn_pick"), url=pick_url)
        kb.adjust(1)
        await cb.message.answer(
            i18n_t(lang, f"{rf}.connect_hint"),
            parse_mode="Markdown",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("cb_connect_reports answer failed: %s", e)
        try:
            await cb.message.answer(
                i18n_t(lang, f"{rf}.pick_failed"),
                parse_mode="Markdown",
            )
        except Exception:
            pass


@router.callback_query(F.data == CB_PICK_REPORTS_CHAT)
async def cb_pick_reports_chat(cb: CallbackQuery):
    """Выбор нового чата отчётов через inline deep-link кнопку."""
    await cb.answer()
    protected_chat_id = await _get_selected_or_alert(cb)
    if not protected_chat_id:
        return
    lang = await _user_lang(cb.from_user.id)
    rf = "panel.reports_flow"
    _pending_reports_for[cb.from_user.id] = protected_chat_id
    try:
        me = await cb.bot.get_me()
        username = me.username or "bot"
        pick_url = f"https://t.me/{username}?startgroup=reportschat_{protected_chat_id}"
        await dm_reply_keyboard_removed_send(cb.bot, cb.from_user.id)
        kb = InlineKeyboardBuilder()
        kb.button(text=i18n_t(lang, f"{rf}.btn_pick_new"), url=pick_url)
        kb.adjust(1)
        await cb.message.answer(
            i18n_t(lang, f"{rf}.change_hint"),
            parse_mode="Markdown",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("cb_pick_reports_chat: %s", e)


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

    lang = await _user_lang(cb.from_user.id)
    rf = "panel.reports_flow"
    try:
        reports_chat_id = int(cb.data.split(":")[-1])
    except Exception:
        await cb.answer(i18n_t(lang, f"{rf}.set_bad_payload"), show_alert=True)
        return

    async with await get_session() as session:
        # разрешать только лог-чаты пользователя (где был /setlog)
        log_chats = await _user_log_chats(session, cb.from_user.id)
        allowed_log_ids = {c.id for c in log_chats}
        if reports_chat_id not in allowed_log_ids:
            await cb.answer(i18n_t(lang, f"{rf}.set_pick_from_list"), show_alert=True)
            return

        chat_row = await session.get(Chat, selected)
        if chat_row:
            chat_row.log_chat_id = reports_chat_id
            await session.commit()

    await cb_reports_menu(cb)


@router.callback_query(F.data == CB_REPORTS_HELP)
async def cb_reports_help(cb: CallbackQuery):
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    txt = i18n_t(lang, "panel.reports_flow.help_body")
    kb = InlineKeyboardBuilder()
    kb.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_REPORTS)
    kb.adjust(1)
    await _edit_or_send(cb, txt, kb.as_markup())


# =========================================================
# CONNECT (инструкция без метаний)
# =========================================================

# ТЗ ЧЕККК: права бота при добавлении через выбор чата (минимум для модерации).
BOT_ADMIN_RIGHTS = aiogram_bot_administrator_rights()
USER_GROUP_ADMIN_RIGHTS = aiogram_user_group_administrator_rights()


def _kb_connect_reports_chat(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Чат отчётов: любая группа; если бота там нет — клиент предложит добавить (без выдачи админки)."""
    pick = i18n_t(lang, "panel.reply_kb.pick_reports_chat")
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=pick,
                    request_chat=KeyboardButtonRequestChat(
                        request_id=REPORTS_REQUEST_ID,
                        chat_is_channel=False,
                        bot_is_member=False,
                        request_title=True,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _kb_connect_request_chat(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Выбор группы: показываем чаты, где бот уже есть (bot_is_member=True — лучше работает в клиентах)."""
    pick = i18n_t(lang, "panel.reply_kb.pick_group")
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=pick,
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


def _kb_connect_request_chat_with_admin(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Добавить бота в группу и сразу выдать права: Telegram откроет выбор группы и модалку назначения админа."""
    pick = i18n_t(lang, "panel.reply_kb.pick_group")
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=pick,
                    request_chat=KeyboardButtonRequestChat(
                        request_id=CONNECT_REQUEST_ID,
                        chat_is_channel=False,
                        request_title=True,
                        bot_administrator_rights=BOT_ADMIN_RIGHTS,
                        user_administrator_rights=USER_GROUP_ADMIN_RIGHTS,
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
    lang = await _user_lang(cb.from_user.id)
    add_txt = i18n_t(lang, "panel.addgroup.body")
    # Пробуем отправить сообщение с Reply-клавиатурой (синяя кнопка под полем ввода)
    try:
        await cb.bot.send_message(
            cb.from_user.id,
            add_txt,
            parse_mode="Markdown",
            reply_markup=_kb_connect_request_chat_with_admin(lang=lang),
        )
    except Exception as e:
        log.warning("cb_addgroup: reply keyboard send failed: %s", e, exc_info=True)
        await cb.message.answer(add_txt, parse_mode="Markdown")
    # Всегда добавляем инлайн-кнопку: если синяя кнопка не показывается (клиент/превью), пользователь может нажать ссылку
    try:
        from aiogram.types import InlineKeyboardButton
        me = await cb.bot.get_me()
        username = me.username or "bot"
        admin_q = GROUP_CONNECT_ADMIN_QUERY
        add_url = f"https://t.me/{username}?startgroup=connect&admin={admin_q}"
        fallback_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=i18n_t(lang, "panel.addgroup.fallback_btn"), url=add_url)],
        ])
        await cb.bot.send_message(
            cb.from_user.id,
            i18n_t(lang, "panel.addgroup.fallback_hint"),
            reply_markup=fallback_kb,
        )
    except Exception as e:
        log.warning("cb_addgroup: fallback inline send failed: %s", e)


@router.callback_query(F.data == CB_CONNECT)
async def cb_connect(cb: CallbackQuery):
    """ТЗ: подключение — выбор группы из списка или нативная модалка Telegram."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    async with await get_session() as session:
        pending = await _pending_chats(session, cb.from_user.id)

    txt = f"{i18n_t(lang, 'panel.connect.menu_title')}\n\n{i18n_t(lang, 'panel.connect.menu_body')}"
    b = InlineKeyboardBuilder()
    b.button(text=i18n_t(lang, "panel.connect.btn_pick_modal"), callback_data=CB_CONNECT_PICK_MODAL)
    if pending:
        for ch in pending[:20]:
            title = (ch.title or "").strip() or str(ch.id)
            if len(title) > 35:
                title = title[:32] + "…"
            b.button(text=f"🛡 {title}", callback_data=f"{CB_CONNECT_CONFIRM_PREFIX}{ch.id}")
    b.button(text=i18n_t(lang, "panel.kb.back"), callback_data=CB_MAIN)
    b.adjust(1)
    await _edit_or_send(cb, txt, b.as_markup())


@router.callback_query(F.data == CB_CONNECT_PICK_MODAL)
async def cb_connect_pick_modal(cb: CallbackQuery):
    """Отправляем сообщение с Reply-кнопкой — по нажатию откроется нативная модалка выбора чата."""
    await cb.answer()
    lang = await _user_lang(cb.from_user.id)
    try:
        await cb.message.answer(
            i18n_t(lang, "panel.connect.pick_modal_prompt"),
            reply_markup=_kb_connect_request_chat_with_admin(lang=lang),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("cb_connect_pick_modal reply keyboard failed: %s", e)
        try:
            await cb.message.answer(
                i18n_t(lang, "panel.connect.pick_modal_fallback"),
                parse_mode="Markdown",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith(CB_CONNECT_CONFIRM_PREFIX))
async def cb_connect_confirm(cb: CallbackQuery):
    """Подключить выбранную группу к защите (без /check в группе)."""
    await cb.answer()
    actor_id = cb.from_user.id
    actor_lang = await _user_lang(actor_id)
    cv = "panel.connect_verify"

    try:
        chat_id = int(cb.data.split(":")[-1])
    except (ValueError, IndexError):
        await cb.answer(i18n_t(actor_lang, f"{cv}.bad_data"), show_alert=True)
        return

    bot = cb.bot

    try:
        chat = await bot.get_chat(chat_id)
        if chat.type not in ("group", "supergroup"):
            await cb.answer(i18n_t(actor_lang, f"{cv}.groups_only"), show_alert=True)
            return
        member = await bot.get_chat_member(chat_id, actor_id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await cb.answer(i18n_t(actor_lang, f"{cv}.admin_only"), show_alert=True)
            return
        if not await actor_may_connect_chat_as_owner(bot, chat_id, actor_id):
            await cb.answer(i18n_t(actor_lang, f"{cv}.creator_only"), show_alert=True)
            return
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
        miss_key = first_missing_i18n_key(bot_member)
        if miss_key:
            await cb.answer(i18n_t(actor_lang, f"{cv}.{miss_key}"), show_alert=True)
            return
    except Exception:
        await cb.answer(i18n_t(actor_lang, f"{cv}.verify_fail"), show_alert=True)
        return

    owner_id, owner_un, owner_fn = await resolve_guard_connect_actor_for_group(bot, chat_id, cb.from_user)
    owner_lang = await _user_lang(owner_id)
    unnamed = i18n_t(owner_lang, "panel.connect.unnamed_chat")

    try:
        async with await get_session() as session:
            await get_or_create_user(session, owner_id, username=owner_un, first_name=owner_fn)
            can_add, current_count, limit = await can_add_chat(session, owner_id)
            if not can_add:
                try:
                    await bot.send_message(
                        actor_id,
                        i18n_t(actor_lang, "panel.connect.limit", current=current_count, limit=limit),
                    )
                except Exception:
                    pass
                return

            chat_row = await session.get(Chat, chat_id)
            if not chat_row:
                chat_row = Chat(
                    id=chat_id,
                    title=chat.title,
                    owner_user_id=owner_id,
                    is_active=True,
                    is_log_chat=False,
                )
                session.add(chat_row)
            else:
                ow_ok, ow_err = await apply_chat_owner_on_connect(bot, chat_row, int(owner_id))
                if not ow_ok:
                    await cb.answer(
                        i18n_t(actor_lang, "panel.connect.owner_bind_alert"),
                        show_alert=True,
                    )
                    return
                chat_row.title = chat.title
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
                    filter_profanity_enabled=True,
                    filter_jobs_enabled=True,
                    filter_casino_enabled=True,
                )
                session.add(rule)

            await _set_selected_chat(session, owner_id, chat_id)
            await session.commit()

        title_esc = (chat.title or unnamed).replace("*", "\\*")
        welcome = i18n_t(owner_lang, "panel.connect.welcome_group", title=title_esc)
        try:
            await bot.send_message(chat_id, welcome, parse_mode="Markdown")
        except Exception:
            pass
        try:
            await cb.message.edit_text(
                i18n_t(actor_lang, "panel.connect.connected_user_msg"),
                reply_markup=_kb_back_to_main(lang=actor_lang),
            )
        except Exception:
            await _edit_panel(
                bot,
                actor_id,
                i18n_t(actor_lang, "panel.connect.connected_user_fallback"),
                _kb_back_to_main(lang=actor_lang),
            )
    except Exception:
        await cb.answer(
            i18n_t(actor_lang, "panel.connect.db_error_alert"),
            show_alert=True,
        )


@router.message(F.chat.type == "private", F.text)
async def on_private_text_antispam_add(message: Message):
    """Ввод: промокод, user_id для антиспам базы."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    lang = await _user_lang(user_id)
    text = (message.text or "").strip()

    if user_id in _pending_promo:
        _pending_promo.pop(user_id, None)
        if text.lower() in ("/cancel", "отмена", "cancel"):
            await message.answer(i18n_t(lang, "panel.promo_input.cancelled"))
            return
        from app.api.service import apply_promo_code
        async with await get_session() as session:
            ok, msg = await apply_promo_code(session, user_id, text)
        await message.answer(msg if ok else f"❌ {msg}")
        return

    if user_id not in _pending_antispam_add:
        return
    ap = "panel.antispam_private"
    if text.lower() in ("/cancel", "отмена", "cancel"):
        _pending_antispam_add.pop(message.from_user.id, None)
        await message.answer(i18n_t(lang, "panel.promo_input.cancelled"))
        return
    if not text.isdigit():
        await message.answer(i18n_t(lang, f"{ap}.user_id_expected"))
        return
    from app.services.global_antispam import add_to_global_antispam, update_antispam_user_profile
    from app.services.telegram_bot_api import private_chat_profile, tg_get_chat

    uid = int(text)
    async with await get_session() as session:
        sel_chat = await _get_selected_chat(session, message.from_user.id)
        if not sel_chat or not await miniapp_actor_has_global_antispam_access(session, int(message.from_user.id)):
            _pending_antispam_add.pop(message.from_user.id, None)
            await message.answer(i18n_t(lang, "panel.global_antispam.premium_required"))
            return
        if not await chat_owner_has_miniapp_premium(session, int(sel_chat)):
            _pending_antispam_add.pop(message.from_user.id, None)
            await message.answer(i18n_t(lang, "panel.global_antispam.owner_premium_required"))
            return
        added = await add_to_global_antispam(session, uid, reason=None)
        if added:
            info = await tg_get_chat(uid)
            disp, un = private_chat_profile(info)
            if disp or un:
                await update_antispam_user_profile(session, uid, disp, un)
    _pending_antispam_add.pop(message.from_user.id, None)
    await message.answer(
        i18n_t(lang, f"{ap}.added" if added else f"{ap}.already", uid=uid),
        parse_mode="Markdown",
    )


@router.message(F.chat.type == "private", F.chat_shared)
async def on_chat_shared(message: Message):
    """Пользователь выбрал чат в модалке: подключение группы (CONNECT) или чат отчётов (REPORTS)."""
    if not message.chat_shared or not message.from_user:
        return

    request_id = message.chat_shared.request_id
    user_id = message.from_user.id
    actor_lang = await _user_lang(user_id)
    rf = "panel.reports_flow"
    cv = "panel.connect_verify"

    # ТЗ Отчёты: выбор чата отчётов для выбранной защищаемой группы
    if request_id == REPORTS_REQUEST_ID:
        protected_chat_id = _pending_reports_for.pop(user_id, None)
        if not protected_chat_id:
            dm_quick_reply_kb_clear(user_id)
            await message.answer(
                i18n_t(actor_lang, f"{rf}.session_expired"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        reports_chat_id = message.chat_shared.chat_id
        _mark_reports_chat_guard(int(reports_chat_id))
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
                    log_chat_row.is_active = False
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
            welcome_lang = await _user_lang(user_id)
            msg_text = i18n_t(welcome_lang, f"{rf}.chat_welcome", title=title_esc)
            await message.bot.send_message(
                reports_chat_id,
                msg_text,
                parse_mode="Markdown",
            )
        except Exception:
            pass
        dm_quick_reply_kb_clear(user_id)
        await message.answer(
            i18n_t(actor_lang, f"{rf}.connected_dm"),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if request_id != CONNECT_REQUEST_ID:
        return

    chat_id = message.chat_shared.chat_id
    bot = message.bot
    actor_id = message.from_user.id

    try:
        chat = await bot.get_chat(chat_id)
        if chat.type not in ("group", "supergroup"):
            dm_quick_reply_kb_clear(actor_id)
            await message.answer(
                i18n_t(actor_lang, f"{cv}.groups_only_dm"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        member = await bot.get_chat_member(chat_id, actor_id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            dm_quick_reply_kb_clear(actor_id)
            await message.answer(
                i18n_t(actor_lang, f"{cv}.admin_only"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        if not await actor_may_connect_chat_as_owner(bot, chat_id, actor_id):
            dm_quick_reply_kb_clear(actor_id)
            await message.answer(
                i18n_t(actor_lang, f"{cv}.creator_only"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
        miss_key = first_missing_i18n_key(bot_member)
        if miss_key:
            dm_quick_reply_kb_clear(actor_id)
            await message.answer(
                i18n_t(actor_lang, f"{cv}.{miss_key}"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return
    except Exception:
        dm_quick_reply_kb_clear(actor_id)
        await message.answer(
            i18n_t(actor_lang, f"{cv}.verify_fail"),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    owner_id, owner_un, owner_fn = await resolve_guard_connect_actor_for_group(bot, chat_id, message.from_user)
    owner_lang = await _user_lang(owner_id)
    unnamed = i18n_t(owner_lang, "panel.connect.unnamed_chat")

    try:
        async with await get_session() as session:
            await get_or_create_user(session, owner_id, username=owner_un, first_name=owner_fn)
            can_add, current_count, limit = await can_add_chat(session, owner_id)
            if not can_add:
                dm_quick_reply_kb_clear(actor_id)
                await message.answer(
                    i18n_t(actor_lang, "panel.connect.limit", current=current_count, limit=limit),
                    reply_markup=ReplyKeyboardRemove(),
                )
                return

            chat_row = await session.get(Chat, chat_id)
            if not chat_row:
                chat_row = Chat(
                    id=chat_id,
                    title=chat.title,
                    owner_user_id=owner_id,
                    is_active=True,
                    is_log_chat=False,
                )
                session.add(chat_row)
            else:
                ow_ok, ow_err = await apply_chat_owner_on_connect(bot, chat_row, int(owner_id))
                if not ow_ok:
                    dm_quick_reply_kb_clear(actor_id)
                    await message.answer(
                        i18n_t(actor_lang, "panel.connect.owner_conflict"),
                        reply_markup=ReplyKeyboardRemove(),
                    )
                    return
                chat_row.title = chat.title
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
                    filter_profanity_enabled=True,
                    filter_jobs_enabled=True,
                    filter_casino_enabled=True,
                )
                session.add(rule)

            await _set_selected_chat(session, owner_id, chat_id)
            await session.commit()
        dm_quick_reply_kb_clear(actor_id)
        await message.answer(
            i18n_t(actor_lang, "panel.connect.connected_user_msg"),
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        dm_quick_reply_kb_clear(actor_id)
        await message.answer(
            i18n_t(actor_lang, "panel.connect.db_error_dm"),
            reply_markup=ReplyKeyboardRemove(),
        )


# =========================================================
# CANCEL pending input
# =========================================================

@router.callback_query(F.data == CB_CANCEL)
async def cb_cancel(cb: CallbackQuery):
    lang = await _user_lang(cb.from_user.id)
    await cb.answer(i18n_t(lang, "panel.cancel_toast"))
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

    lang = await _user_lang(message.from_user.id)
    pi = "panel.pending_input"

    try:
        value = int(raw)
    except Exception:
        await _edit_panel(
            message.bot,
            message.from_user.id,
            i18n_t(lang, f"{pi}.need_number"),
            _kb_cancel(lang=lang),
        )
        return

    if value < 1 or value > 1440:
        hint = (
            i18n_t(lang, f"{pi}.mute_range")
            if p.kind == "mute_minutes"
            else i18n_t(lang, f"{pi}.newbie_range")
        )
        await _edit_panel(
            message.bot,
            message.from_user.id,
            hint,
            _kb_cancel(lang=lang),
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
