# app/services/reminders.py
"""ТЗ Напоминания: напоминания пользователю (нет группы / нет чата отчётов), Guard-сообщения раз в 3 дня."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import select, text, func, update, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import (
    User,
    Chat,
    Rule,
    ModerationLog,
    Payment,
    NewMember,
    PartnerCommission,
    ReferralShareHit,
    AdminMessageTemplate,
    AdminMessageDispatchLog,
    OwnerJoinReportSetting,
)
from app.services.user_service import (
    count_protected_chats,
    TARIFF_CHAT_LIMITS,
    TARIFF_GROUP_LIMITS,
    TARIFF_CHANNEL_LIMITS,
    TRIAL_DAYS,
    TRIAL_WINDOW_DAYS,
    TRIAL_SUBSCRIPTION_SOURCE,
    is_trial_active,
    is_trial_eligible,
    trial_active_remaining_days,
    trial_window_remaining_days,
)
from app.services.chat_limit_enforcer import enforce_owner_active_chat_limit
from app.db.models import Tariff
from app.services.admin_roles import is_full_admin_user
from app.services.spam_spike_notify import run_spam_spike_owner_manager_alerts
from app.services.chat_supergroup_migrate import parse_migrate_to_supergroup_id, remap_group_chat_ids
from app.texts.guardian_billing import PREMIUM_PLANS
from app.texts.guard_group_messages import guardian_periodic_texts
from app.i18n import DEFAULT_LOCALE, normalize_locale, t
from app.services.chat_owner_locale import owner_locale_for_chat, user_locale
from app.services.chat_owner_premium import chat_owner_has_miniapp_premium
from app.services.payments_yookassa import (
    autorenew_window_hours,
    run_yookassa_autorenew_batch,
    yookassa_autorenew_worker_enabled,
)

logger = logging.getLogger(__name__)
_BOT_USERNAME_CACHE: str | None = None


def _log_expected_telegram_user_block(log, prefix: str, telegram_id, exc: BaseException) -> None:
    """Пользователь заблокировал бота / запретил писать — не пишем warning (шум в Railway)."""
    msg = str(exc).lower()
    if any(
        x in msg
        for x in (
            "blocked",
            "forbidden",
            "deactivated",
            "bot was blocked",
            "user is deactivated",
            "chat not found",
        )
    ):
        log.debug("%s user=%s: %s", prefix, telegram_id, exc)
        return
    log.warning("%s user=%s: %s", prefix, telegram_id, exc)
_TOPIC_CLOSED_LOG_TS: dict[int, float] = {}

# Интервалы напоминаний (ТЗ)
REMINDER_12H = timedelta(hours=12)
REMINDER_24H = timedelta(hours=24)
REMINDER_3D = timedelta(days=3)
GUARDIAN_MSG_INTERVAL = timedelta(hours=24)  # дефолт (на Free фиксированно 24ч)
GUARDIAN_ACTIVITY_WINDOW = timedelta(hours=24)  # «≥10 сообщений за сутки» — считаем активным если была модерация
AUTO_REPORT_INTERVAL = timedelta(hours=24)  # дайджест раз в сутки
EXPIRED_REMINDER_PATTERN_DAYS = (7, 3)  # после первого уведомления: раз в неделю, затем через 3 дня, по кругу
SUB_END_5D_WINDOW = timedelta(days=5)
SUB_END_1H_WINDOW = timedelta(hours=1)

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
EXPIRED_WARNING_PHOTO_PATH = _STATIC_DIR / "trial_warning.jpg"
EXPIRED_WARNING_FALLBACK_PATH = Path(__file__).resolve().parent.parent.parent / "webapp" / "public" / "logo.png"
EXPIRED_WARNING_PHOTO_FILE_ID = (os.getenv("TRIAL_WARNING_PHOTO_FILE_ID") or "").strip()
TRIAL_PREVIEW_GUARD_PHOTO_PATH = _STATIC_DIR / "trial_preview_guard.jpg"


def _is_topic_closed_error(exc: Exception) -> bool:
    s = str(exc or "")
    up = s.upper()
    return ("TOPIC_CLOSED" in up) or ("TOPIC IS CLOSED" in up)


def _topic_closed_log_allowed(chat_id: int, *, ttl_sec: int = 3600) -> bool:
    now_ts = datetime.now(timezone.utc).timestamp()
    last_ts = float(_TOPIC_CLOSED_LOG_TS.get(int(chat_id), 0.0) or 0.0)
    if now_ts - last_ts < float(ttl_sec):
        return False
    _TOPIC_CLOSED_LOG_TS[int(chat_id)] = now_ts
    return True


def _annual_discount_percent() -> int:
    """
    Процент выгоды 12 месяцев относительно помесячной оплаты:
    (1м * 12 - 12м) / (1м * 12) * 100.
    """
    by_months = {int(x[0]): float(x[2]) for x in PREMIUM_PLANS if int(x[0]) > 0}
    p1 = by_months.get(1)
    p12 = by_months.get(12)
    if not p1 or not p12:
        return 50
    base = p1 * 12.0
    if base <= 0:
        return 50
    pct = int(round(((base - p12) / base) * 100.0))
    return max(1, min(95, pct))

def _parse_admin_ids() -> set[int]:
    out: set[int] = set()
    for part in (os.getenv("ADMIN_TELEGRAM_IDS") or "").split(","):
        p = (part or "").strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except Exception:
            continue
    return out


async def _load_message_templates(session: AsyncSession) -> dict[str, AdminMessageTemplate]:
    q = await session.execute(select(AdminMessageTemplate).where(AdminMessageTemplate.enabled == True))  # noqa: E712
    return {str(x.template_key or "").strip(): x for x in q.scalars().all() if str(x.template_key or "").strip()}


def _tpl_text(tpl: dict[str, AdminMessageTemplate], key: str, fallback: str) -> str:
    row = tpl.get(key)
    if not row:
        return fallback
    text = str(getattr(row, "body_text", "") or "").strip()
    return text or fallback


def _tpl_delay(tpl: dict[str, AdminMessageTemplate], key: str, fallback: timedelta) -> timedelta:
    row = tpl.get(key)
    if not row or getattr(row, "delay_minutes", None) is None:
        return fallback
    try:
        n = max(1, int(getattr(row, "delay_minutes", 0) or 0))
    except Exception:
        return fallback
    return timedelta(minutes=n)


def _parse_hm(value: str | None) -> tuple[int, int] | None:
    s = str(value or "").strip()
    if len(s) != 5 or s[2] != ":":
        return None
    try:
        h = int(s[:2])
        m = int(s[3:])
    except Exception:
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return h, m


async def _owner_admin_target_ids(session: AsyncSession) -> list[int]:
    ids = _parse_admin_ids()
    if not ids:
        q_admins = await session.execute(select(User))
        for u in q_admins.scalars().all():
            try:
                tid = int(getattr(u, "telegram_id", 0) or 0)
                if tid > 0 and is_full_admin_user(u, tid):
                    ids.add(tid)
            except Exception:
                continue
    return sorted(ids)


async def _template_can_send_now(
    session: AsyncSession,
    t: AdminMessageTemplate,
    target_tg_id: int,
    now: datetime,
    bucket: str | None = None,
) -> bool:
    hm = _parse_hm(getattr(t, "schedule_time_hm", None))
    if hm:
        # отправляем в 15-минутное окно возле заданного времени UTC
        total_now = now.hour * 60 + now.minute
        total_cfg = hm[0] * 60 + hm[1]
        if abs(total_now - total_cfg) > 15:
            return False
    last_q = await session.execute(
        select(AdminMessageDispatchLog).where(
            AdminMessageDispatchLog.template_id == int(t.id),
            AdminMessageDispatchLog.target_tg_id == int(target_tg_id),
        ).order_by(AdminMessageDispatchLog.created_at.desc()).limit(1)
    )
    last = last_q.scalar_one_or_none()
    if last:
        last_at = last.created_at
        if last_at and last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        cooldown = max(1, int(getattr(t, "cooldown_minutes", 1440) or 1440))
        if last_at and (now - last_at) < timedelta(minutes=cooldown):
            return False
    if bucket:
        bucket_q = await session.execute(
            select(AdminMessageDispatchLog.id).where(
                AdminMessageDispatchLog.template_id == int(t.id),
                AdminMessageDispatchLog.target_tg_id == int(target_tg_id),
                AdminMessageDispatchLog.event_bucket == bucket,
            ).limit(1)
        )
        if bucket_q.scalar_one_or_none():
            return False
    return True


async def _mark_template_sent(session: AsyncSession, t: AdminMessageTemplate, target_tg_id: int, bucket: str | None = None) -> None:
    session.add(
        AdminMessageDispatchLog(
            template_id=int(t.id),
            target_tg_id=int(target_tg_id),
            event_bucket=(bucket or None),
        )
    )
    await session.commit()


async def _dispatch_bucket_sent(session: AsyncSession, target_tg_id: int, bucket: str) -> bool:
    q = await session.execute(
        select(AdminMessageDispatchLog.id).where(
            AdminMessageDispatchLog.template_id == 0,
            AdminMessageDispatchLog.target_tg_id == int(target_tg_id),
            AdminMessageDispatchLog.event_bucket == str(bucket),
        ).limit(1)
    )
    return q.scalar_one_or_none() is not None


async def _mark_dispatch_bucket(session: AsyncSession, target_tg_id: int, bucket: str) -> None:
    session.add(
        AdminMessageDispatchLog(
            template_id=0,
            target_tg_id=int(target_tg_id),
            event_bucket=str(bucket),
        )
    )
    await session.commit()


async def _claim_dispatch_bucket(session: AsyncSession, target_tg_id: int, bucket: str) -> bool:
    """Атомарно резервирует bucket: только один воркер продолжит отправку."""
    session.add(
        AdminMessageDispatchLog(
            template_id=0,
            target_tg_id=int(target_tg_id),
            event_bucket=str(bucket),
        )
    )
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def _user_has_successful_subscription_payment(session: AsyncSession, user_db_id: int) -> bool:
    q = await session.execute(
        select(Payment.id).where(
            Payment.user_id == int(user_db_id),
            Payment.status == "succeeded",
            Payment.months > 0,
        ).limit(1)
    )
    return q.scalar_one_or_none() is not None


def _startapp_link(bot_username: str, section: str) -> str:
    uname = (bot_username or "").strip().lstrip("@")
    short_name = (os.getenv("MINI_APP_SHORT_NAME") or os.getenv("WEBAPP_SHORT_NAME") or "").strip().strip("/")
    safe_section = (section or "panel").strip() or "panel"
    if short_name:
        return f"https://t.me/{uname}/{short_name}?startapp={safe_section}"
    return f"https://t.me/{uname}?startapp={safe_section}"


async def _startapp_link_for_bot(bot, section: str) -> str:
    global _BOT_USERNAME_CACHE
    if not _BOT_USERNAME_CACHE:
        me = await bot.get_me()
        _BOT_USERNAME_CACHE = str(getattr(me, "username", "") or "").strip()
    return _startapp_link(_BOT_USERNAME_CACHE, section)


def _expired_reminder_threshold_days(n: int) -> int:
    """Порог в днях для n-го follow-up после первого уведомления об истечении."""
    total = 0
    for i in range(n):
        total += EXPIRED_REMINDER_PATTERN_DAYS[i % len(EXPIRED_REMINDER_PATTERN_DAYS)]
    return total


def _expired_warning_text_for(display_name: str | None, locale: str) -> str:
    name = (display_name or "").strip()
    loc = normalize_locale(locale)
    if not name:
        return t(loc, "reminders.expired_warning")
    return t(loc, "reminders.expired_warning_named", name=name)


def _guard_payment_sub_expired_text_for(display_name: str | None, locale: str) -> str:
    name = (display_name or "").strip()
    loc = normalize_locale(locale)
    block = t(loc, "reminders.payment_name_block", name=name) if name else ""
    return t(loc, "reminders.guard_payment_sub_expired", name_block=block)


def _trial_preview_guard_text_for(display_name: str | None, locale: str) -> str:
    name = (display_name or "").strip()
    loc = normalize_locale(locale)
    block = t(loc, "reminders.trial_name_block", name=name) if name else ""
    return t(loc, "reminders.trial_preview_guard", name_block=block)


async def send_expired_guard_payment(bot, user_id: int) -> None:
    """Окончание оплаченного Premium — в том же Guard-голосе, что предпросмотр trial, без «не прошло списание»."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.types import FSInputFile
    from aiogram.exceptions import TelegramBadRequest

    async with await get_session() as session:
        loc = await user_locale(session, int(user_id))

    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(loc, "reminders.btn_extend_premium"), url=billing_link)]]
    )
    text = _guard_payment_sub_expired_text_for(None, loc)
    try:
        chat = await bot.get_chat(user_id)
        text = _guard_payment_sub_expired_text_for(getattr(chat, "first_name", None), loc)
    except Exception:
        pass
    photo = None
    if TRIAL_PREVIEW_GUARD_PHOTO_PATH.exists():
        photo = FSInputFile(str(TRIAL_PREVIEW_GUARD_PHOTO_PATH))
    elif EXPIRED_WARNING_PHOTO_PATH.exists():
        photo = FSInputFile(str(EXPIRED_WARNING_PHOTO_PATH))
    elif EXPIRED_WARNING_FALLBACK_PATH.exists():
        photo = FSInputFile(str(EXPIRED_WARNING_FALLBACK_PATH))
    try:
        if photo is not None:
            await bot.send_photo(
                chat_id=user_id,
                photo=photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
    except TelegramBadRequest:
        if EXPIRED_WARNING_PHOTO_PATH.exists():
            await bot.send_photo(
                chat_id=user_id,
                photo=FSInputFile(str(EXPIRED_WARNING_PHOTO_PATH)),
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
                disable_web_page_preview=True,
            )


async def send_expired_warning(bot, user_id: int) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.types import FSInputFile
    from aiogram.exceptions import TelegramBadRequest

    async with await get_session() as session:
        loc = await user_locale(session, int(user_id))

    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(loc, "reminders.btn_extend_protection"), url=billing_link),
    ]])
    text = _expired_warning_text_for(None, loc)
    try:
        chat = await bot.get_chat(user_id)
        text = _expired_warning_text_for(getattr(chat, "first_name", None), loc)
    except Exception:
        pass

    if EXPIRED_WARNING_PHOTO_FILE_ID:
        photo = EXPIRED_WARNING_PHOTO_FILE_ID
    elif EXPIRED_WARNING_PHOTO_PATH.exists():
        photo = FSInputFile(str(EXPIRED_WARNING_PHOTO_PATH))
    elif EXPIRED_WARNING_FALLBACK_PATH.exists():
        photo = FSInputFile(str(EXPIRED_WARNING_FALLBACK_PATH))
    else:
        photo = None
    try:
        if photo is not None:
            await bot.send_photo(
                chat_id=user_id,
                photo=photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
    except TelegramBadRequest:
        # Частая причина: невалидный file_id в TRIAL_WARNING_PHOTO_FILE_ID.
        # Пробуем безопасный fallback, чтобы предпросмотр и рассылка не ломались.
        if EXPIRED_WARNING_PHOTO_PATH.exists():
            fallback_photo = FSInputFile(str(EXPIRED_WARNING_PHOTO_PATH))
            await bot.send_photo(
                chat_id=user_id,
                photo=fallback_photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        elif EXPIRED_WARNING_FALLBACK_PATH.exists():
            fallback_photo = FSInputFile(str(EXPIRED_WARNING_FALLBACK_PATH))
            await bot.send_photo(
                chat_id=user_id,
                photo=fallback_photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
                disable_web_page_preview=True,
            )


async def send_expired_warning_preview(
    bot,
    chat_id: int,
    *,
    display_name: str | None = None,
    locale: str | None = None,
) -> None:
    """Предпросмотр сообщения об истечении подписки в любом чате."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.types import FSInputFile

    loc = normalize_locale(locale) if locale is not None else DEFAULT_LOCALE
    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(loc, "reminders.btn_extend_protection"), url=billing_link)]]
    )
    text = _expired_warning_text_for(display_name, loc)
    photo = FSInputFile(str(EXPIRED_WARNING_PHOTO_PATH)) if EXPIRED_WARNING_PHOTO_PATH.exists() else None
    if photo is not None:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)


async def send_trial_warning_preview_guard(
    bot,
    chat_id: int,
    *,
    display_name: str | None = None,
    locale: str | None = None,
) -> None:
    """Предпросмотр guard-версии сообщения об истечении подписки с ссылкой на практику."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.types import FSInputFile

    loc = normalize_locale(locale) if locale is not None else DEFAULT_LOCALE
    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(loc, "reminders.btn_extend_sub"), url=billing_link)]]
    )
    text = _trial_preview_guard_text_for(display_name, loc)
    photo = FSInputFile(str(TRIAL_PREVIEW_GUARD_PHOTO_PATH)) if TRIAL_PREVIEW_GUARD_PHOTO_PATH.exists() else None
    if photo is not None:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)


async def _run_reminders_no_group(
    bot,
    session: AsyncSession,
    now: datetime,
    tpl: dict[str, AdminMessageTemplate],
    *,
    skip_user_ids: set[int] | None = None,
) -> None:
    """Напоминания: пользователь сделал /start, но не подключил ни одной группы.

    `skip_user_ids` — кому уже отправили trial-DM в этой итерации: их пропускаем,
    чтобы не слать два письма в одни сутки.
    """
    skip_user_ids = skip_user_ids or set()
    res = await session.execute(
        select(User).where(User.first_start_at.isnot(None)).where(User.reminder_stage < 4)
    )
    users = list(res.scalars().all())
    for user in users:
        if int(getattr(user, "telegram_id", 0) or 0) in skip_user_ids:
            continue
        try:
            loc = normalize_locale(getattr(user, "language", None))
            started_at = user.first_start_at
            if not started_at:
                continue
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed = now - started_at
            stage = user.reminder_stage or 0

            d12 = _tpl_delay(tpl, "reminder_12h", REMINDER_12H)
            d24 = _tpl_delay(tpl, "reminder_24h", REMINDER_24H)
            d3d = _tpl_delay(tpl, "reminder_3d", REMINDER_3D)

            if stage == 0 and elapsed >= d12:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = _tpl_text(tpl, "reminder_12h", t(loc, "reminders.no_group_12h"))
                button_text = t(loc, "reminders.btn_connect_group")
                user.reminder_stage = 1
            elif stage == 1 and elapsed >= d24:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = _tpl_text(tpl, "reminder_24h", t(loc, "reminders.no_group_24h"))
                button_text = t(loc, "reminders.btn_connect_group_shield")
                user.reminder_stage = 2
            elif stage == 2 and elapsed >= d3d:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = _tpl_text(tpl, "reminder_3d", t(loc, "reminders.no_group_3d"))
                button_text = t(loc, "reminders.btn_connect_group")
                user.reminder_stage = 4
            else:
                continue

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            connect_link = await _startapp_link_for_bot(bot, "connect")
            rows: list[list[InlineKeyboardButton]] = [[
                InlineKeyboardButton(text=button_text, url=connect_link),
            ]]
            if stage == 0 and is_trial_eligible(user, now):
                trial_link = await _startapp_link_for_bot(bot, "trial")
                rows.append([
                    InlineKeyboardButton(text=t(loc, "reminders.btn_trial_activate"), url=trial_link),
                ])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            await bot.send_message(
                user.telegram_id,
                text,
                parse_mode=None,
                reply_markup=kb,
            )
            await session.commit()
        except Exception as e:
            _log_expected_telegram_user_block(logger, "reminder no_group", getattr(user, "telegram_id"), e)
            await session.rollback()


async def _run_reminders_reports_chat(
    bot,
    session: AsyncSession,
    now: datetime,
    tpl: dict[str, AdminMessageTemplate],
    *,
    skip_user_ids: set[int] | None = None,
) -> None:
    """Напоминание: группа подключена, но чат отчётов не выбран (log_chat_id = null).

    `skip_user_ids` — кому в этой итерации уже отправили trial-DM или no-group-DM:
    пропускаем, чтобы не плодить два письма в одни сутки.
    """
    skip_user_ids = skip_user_ids or set()
    res = await session.execute(
        select(User).where(User.reports_reminder_sent_at.is_(None)).where(User.first_start_at.isnot(None))
    )
    users = list(res.scalars().all())
    for user in users:
        if int(getattr(user, "telegram_id", 0) or 0) in skip_user_ids:
            continue
        try:
            loc = normalize_locale(getattr(user, "language", None))
            count = await count_protected_chats(session, user.telegram_id)
            if count == 0:
                continue
            res2 = await session.execute(
                select(Chat).where(Chat.owner_user_id == user.telegram_id).where(
                    Chat.is_log_chat == False,  # noqa: E712
                    Chat.is_active == True,  # noqa: E712
                    Chat.log_chat_id.is_(None),
                )
            )
            chats_without_log = list(res2.scalars().all())
            if not chats_without_log:
                continue
            # Не чаще чем через 12ч после first_start
            started_at = user.first_start_at
            if started_at and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if started_at and (now - started_at) < REMINDER_12H:
                continue

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            me = await bot.get_me()
            reports_link = _startapp_link(str(me.username or ""), "reports")
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(loc, "reminders.btn_reports_connect"), url=reports_link),
            ]])
            await bot.send_message(
                user.telegram_id,
                _tpl_text(tpl, "reports_reminder", t(loc, "reminders.reports_reminder")),
                parse_mode="Markdown",
                reply_markup=kb,
            )
            user.reports_reminder_sent_at = now
            await session.commit()
        except Exception as e:
            logger.warning("reminder reports user=%s: %s", getattr(user, "telegram_id"), e)
            await session.rollback()


# === Premium-триал DM-серии ====================================================

def _select_pre_trial_targets(users, now: datetime):
    """Pure: какие юзеры (и какой "оставшийся день N") должны получить pre-trial DM.

    Pre-trial — юзер ещё не активировал триал, но окно ещё открыто.
    Шлём не каждый день после /start, а только при N=1..9 (день N=10 = день первого
    /start — пропускаем, чтобы не заваливать сразу). Дедуп через
    `user.trial_reminder_last_day_sent`: положительное значение хранит последний
    отправленный pre-trial-день.
    """
    for u in users:
        if bool(getattr(u, "trial_used", False)):
            continue
        if getattr(u, "first_start_at", None) is None:
            continue
        src = (getattr(u, "subscription_source", None) or "").strip().lower()
        if src in ("payment", "promo"):
            continue
        n = trial_window_remaining_days(u, now)
        if n <= 0 or n >= TRIAL_WINDOW_DAYS:
            continue
        if int(getattr(u, "trial_reminder_last_day_sent", 0) or 0) == n:
            continue
        yield u, n


def _select_in_trial_targets(users, now: datetime):
    """Pure: какие юзеры (и сколько дней N) должны получить in-trial DM.

    In-trial — триал активирован и сейчас идёт. Шлём при N=1..9; день активации
    (N=TRIAL_DAYS) пропускаем — юзер только что активировал, не заваливаем.
    Дедуп через `user.trial_reminder_last_day_sent` отрицательным значением
    (-N), чтобы не пересекаться с pre-trial-нумерацией.
    """
    for u in users:
        if not is_trial_active(u, now):
            continue
        n = trial_active_remaining_days(u, now)
        if n <= 0 or n >= TRIAL_DAYS:
            continue
        if int(getattr(u, "trial_reminder_last_day_sent", 0) or 0) == -n:
            continue
        yield u, n


async def _run_reminders_pre_trial(bot, session: AsyncSession, now: datetime) -> set[int]:
    """Pre-trial DM: «осталось N дней попробовать Premium бесплатно».

    Возвращает множество telegram_id, которым уже отправили в этой итерации —
    используется для гармонизации с серией «нет группы» / «нет чата отчётов»
    (чтобы не плодить два письма в одни сутки).
    """
    sent: set[int] = set()
    res = await session.execute(
        select(User)
        .where(User.first_start_at.isnot(None))
        .where(User.trial_used.is_(False))
    )
    users = list(res.scalars().all())
    for user, n in _select_pre_trial_targets(users, now):
        try:
            loc = normalize_locale(getattr(user, "language", None))
            text_body = _trial_window_text(loc, n)
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            trial_link = await _startapp_link_for_bot(bot, "trial")
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(loc, "reminders.btn_trial_activate"), url=trial_link),
            ]])
            await bot.send_message(
                user.telegram_id,
                text_body,
                parse_mode=None,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            user.trial_reminder_last_day_sent = int(n)
            await session.commit()
            sent.add(int(user.telegram_id))
        except Exception as e:
            _log_expected_telegram_user_block(logger, "reminder pre_trial", getattr(user, "telegram_id"), e)
            await session.rollback()
    return sent


async def _run_reminders_in_trial(bot, session: AsyncSession, now: datetime) -> set[int]:
    """In-trial DM: «осталось N дней Premium-триала — закрепи защиту»."""
    sent: set[int] = set()
    res = await session.execute(
        select(User)
        .where(User.trial_used.is_(True))
        .where(User.subscription_source == TRIAL_SUBSCRIPTION_SOURCE)
        .where(User.subscription_until.isnot(None))
        .where(User.subscription_until > now)
    )
    users = list(res.scalars().all())
    for user, n in _select_in_trial_targets(users, now):
        try:
            loc = normalize_locale(getattr(user, "language", None))
            text_body = _trial_active_text(loc, n)
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            billing_link = await _startapp_link_for_bot(bot, "billing")
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(loc, "reminders.btn_trial_billing"), url=billing_link),
            ]])
            await bot.send_message(
                user.telegram_id,
                text_body,
                parse_mode=None,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            user.trial_reminder_last_day_sent = -int(n)
            await session.commit()
            sent.add(int(user.telegram_id))
        except Exception as e:
            _log_expected_telegram_user_block(logger, "reminder in_trial", getattr(user, "telegram_id"), e)
            await session.rollback()
    return sent


def _trial_window_text(loc: str, n: int) -> str:
    """Текст pre-trial DM для дня N (1..9). Fallback на generic, если в i18n нет."""
    key = f"reminders.trial_window_left.{n}"
    specific = t(loc, key)
    if specific and specific != key:
        return specific
    return t(loc, "reminders.trial_window_left.generic", n=n)


def _trial_active_text(loc: str, n: int) -> str:
    """Текст in-trial DM для дня N (1..9). Fallback на generic, если в i18n нет."""
    key = f"reminders.trial_active_left.{n}"
    specific = t(loc, key)
    if specific and specific != key:
        return specific
    return t(loc, "reminders.trial_active_left.generic", n=n)


async def _run_guardian_periodic_messages(bot, session: AsyncSession, now: datetime) -> None:
    """Guard сообщения в группе по правилу чата (на Free фиксировано 24ч), если чат был активен (last_activity_at за 24ч)."""
    res = await session.execute(
        select(
            Chat.id,
            Chat.last_activity_at,
            Rule.chat_id,
            Rule.guardian_messages_enabled,
            Rule.guardian_periodic_enabled,
            Rule.guardian_periodic_interval_hours,
            Rule.last_guardian_message_at,
            User.language,
        )
        .join(Rule, Chat.id == Rule.chat_id)
        .outerjoin(User, User.telegram_id == Chat.owner_user_id)
        .where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            # Каналы (рассылка / Mini App) — не группы: туда нельзя слать «проверил чат» (лезет в ленту канала).
            or_(Chat.chat_kind.is_(None), Chat.chat_kind != "channel"),
        )
    )
    for row in res.all():
        (
            chat_id,
            last_activity,
            rule_chat_id,
            guardian_enabled,
            periodic_enabled,
            periodic_hours,
            last_sent,
            owner_lang,
        ) = row
        loc = normalize_locale(owner_lang)
        if not bool(guardian_enabled) or not bool(periodic_enabled):
            continue
        interval_h = max(6, min(168, int(periodic_hours or 24)))
        interval_td = timedelta(hours=interval_h)
        if last_sent:
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if (now - last_sent) < interval_td:
                continue
        if last_activity:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            if (now - last_activity) > GUARDIAN_ACTIVITY_WINDOW:
                continue
        # Если last_activity_at нет — всё равно шлём по текущему интервалу (упрощение)
        try:
            guard_msg = random.choice(guardian_periodic_texts(loc))
            await bot.send_message(int(chat_id), guard_msg)
            await session.execute(
                update(Rule)
                .where(Rule.chat_id == int(rule_chat_id))
                .values(last_guardian_message_at=now)
            )
            await session.commit()
        except Exception as e:
            if _is_topic_closed_error(e):
                if _topic_closed_log_allowed(int(chat_id)):
                    logger.info("guardian periodic chat=%s skipped: topic closed", chat_id)
            else:
                new_cid = parse_migrate_to_supergroup_id(e)
                if new_cid and int(new_cid) != int(chat_id):
                    await session.rollback()
                    if await remap_group_chat_ids(int(chat_id), int(new_cid)):
                        try:
                            await bot.send_message(int(new_cid), random.choice(guardian_periodic_texts(loc)))
                            async with await get_session() as s2:
                                await s2.execute(
                                    update(Rule)
                                    .where(Rule.chat_id == int(new_cid))
                                    .values(last_guardian_message_at=now)
                                )
                                await s2.commit()
                        except Exception as e2:
                            logger.warning("guardian periodic after migrate chat=%s->%s: %s", chat_id, new_cid, e2)
                    else:
                        logger.info("guardian periodic chat=%s migrate to %s: remap failed", chat_id, new_cid)
                else:
                    logger.info("guardian periodic chat=%s: %s", chat_id, e)
            await session.rollback()


async def _run_auto_reports(bot, session: AsyncSession, now: datetime) -> None:
    """ТЗ Автоматические отчёты: раз в сутки отправлять дайджест в чат отчётов."""
    from app.db.models import ModerationLog
    from sqlalchemy import func

    res = await session.execute(
        select(Chat, Rule).join(Rule, Chat.id == Rule.chat_id).where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            Chat.log_chat_id.isnot(None),
        ).where(
            Rule.auto_reports_enabled == True,  # noqa: E712
        )
    )
    for row in res.all():
        chat_row, rule = row[0], row[1]
        if not await chat_owner_has_miniapp_premium(session, int(chat_row.id)):
            continue
        log_chat_id = chat_row.log_chat_id
        if not log_chat_id:
            continue
        last_sent = getattr(rule, "last_auto_report_at", None)
        if last_sent:
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if (now - last_sent) < AUTO_REPORT_INTERVAL:
                continue
        since = now - AUTO_REPORT_INTERVAL
        cnt = await session.execute(
            select(func.count(ModerationLog.id)).where(
                ModerationLog.chat_id == chat_row.id,
                ModerationLog.created_at >= since,
            )
        )
        total = cnt.scalar() or 0
        try:
            title = (chat_row.title or "").strip() or str(chat_row.id)
            loc = await owner_locale_for_chat(session, int(chat_row.id))
            text = t(loc, "reminders.auto_report", title=title, total=int(total))
            await bot.send_message(log_chat_id, text, parse_mode="Markdown")
            rule.last_auto_report_at = now
            await session.commit()
        except Exception as e:
            logger.warning("auto_report chat=%s log=%s: %s", chat_row.id, log_chat_id, e)
            await session.rollback()


async def _run_owner_daily_report(bot, session: AsyncSession, now: datetime, tpl: dict[str, AdminMessageTemplate]) -> None:
    """Раз в сутки отправляет владельцу(ям) сводку за последние 24 часа в личку."""
    trow = tpl.get("owner_daily_report")
    if trow and not bool(getattr(trow, "enabled", True)):
        return
    day_key = now.date().isoformat()
    window_h = 24 if not trow else max(1, min(168, int(getattr(trow, "trigger_hours", 24) or 24)))
    since = now - timedelta(hours=window_h)
    joins_q = await session.execute(select(func.count(NewMember.id)).where(NewMember.joined_at >= since))
    starts_q = await session.execute(select(func.count(User.id)).where(User.first_start_at.is_not(None), User.first_start_at >= since))
    pays_q = await session.execute(
        select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0.0)).where(
            Payment.status == "succeeded",
            Payment.created_at >= since,
        )
    )
    shares_q = await session.execute(select(func.count(ReferralShareHit.id)).where(ReferralShareHit.created_at >= since))
    lvl_q = await session.execute(
        select(
            PartnerCommission.level,
            func.count(PartnerCommission.id).label("payments_count"),
            func.coalesce(func.sum(PartnerCommission.sales_amount_rub), 0.0).label("sales_sum"),
        ).where(
            PartnerCommission.created_at >= since
        ).group_by(PartnerCommission.level).order_by(PartnerCommission.level.asc())
    )
    lvl_rows = list(lvl_q.all())
    pay_count, pay_sum = pays_q.one_or_none() or (0, 0.0)
    joins_n = int(joins_q.scalar() or 0)
    starts_n = int(starts_q.scalar() or 0)
    shares_n = int(shares_q.scalar() or 0)
    pay_sum_f = float(pay_sum or 0.0)

    ids = await _owner_admin_target_ids(session)
    if not ids:
        return

    for tid in sorted(ids):
        try:
            loc = await user_locale(session, int(tid))
            lvl_lines_loc: list[str] = []
            for row in lvl_rows:
                lvl_lines_loc.append(
                    t(
                        loc,
                        "reminders.owner_daily_lvl_line",
                        level=int(row.level or 0),
                        payments_count=int(row.payments_count or 0),
                        sales_sum=float(row.sales_sum or 0.0),
                    )
                )
            if not lvl_lines_loc:
                lvl_lines_loc.append(t(loc, "reminders.owner_daily_no_lvl"))
            text_head = _tpl_text(tpl, "owner_daily_report", t(loc, "reminders.owner_daily_head"))
            msg = t(
                loc,
                "reminders.owner_daily_block",
                head=text_head,
                window_h=window_h,
                joins=joins_n,
                starts=starts_n,
                pay_count=int(pay_count or 0),
                pay_sum=pay_sum_f,
                shares=shares_n,
                lvl_block="\n".join(lvl_lines_loc),
            )
            if trow:
                if not await _template_can_send_now(session, trow, int(tid), now, bucket=f"owner_daily:{day_key}"):
                    continue
                await bot.send_message(tid, msg, parse_mode=str(getattr(trow, "parse_mode", "") or "Markdown"))
                await _mark_template_sent(session, trow, int(tid), bucket=f"owner_daily:{day_key}")
            else:
                await bot.send_message(tid, msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning("owner_daily_report notify %s: %s", tid, e)


async def _run_owner_join_reports(bot, session: AsyncSession, now: datetime) -> None:
    """Персональные дайджесты владельцам групп по выбранным периодам."""
    rows = (
        await session.execute(select(OwnerJoinReportSetting).where(OwnerJoinReportSetting.periods_csv.is_not(None)))
    ).scalars().all()
    if not rows:
        return
    intervals = {
        "day": timedelta(days=1),
        "3d": timedelta(days=3),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
    }
    for st in rows:
        tid = int(getattr(st, "telegram_user_id", 0) or 0)
        if tid <= 0:
            continue
        periods_raw = [x.strip().lower() for x in str(getattr(st, "periods_csv", "") or "").split(",") if x.strip()]
        periods = [x for x in periods_raw if x in intervals]
        if not periods:
            continue
        active_groups_q = await session.execute(
            select(func.count(Chat.id)).where(
                Chat.owner_user_id == tid,
                Chat.is_active.is_(True),
                Chat.is_log_chat.is_(False),
            )
        )
        active_groups = int(active_groups_q.scalar() or 0)
        if active_groups <= 0:
            continue
        for p in periods:
            td = intervals[p]
            last_attr = (
                "last_sent_day_at" if p == "day" else
                "last_sent_3d_at" if p == "3d" else
                "last_sent_week_at" if p == "week" else
                "last_sent_month_at"
            )
            last_sent = getattr(st, last_attr, None)
            if last_sent and (now - last_sent) < td:
                continue
            since = now - td
            joins_q = await session.execute(
                select(func.count(NewMember.id))
                .join(Chat, Chat.id == NewMember.chat_id)
                .where(
                    Chat.owner_user_id == tid,
                    Chat.is_log_chat.is_(False),
                    NewMember.joined_at >= since,
                )
            )
            joins = int(joins_q.scalar() or 0)
            loc = await user_locale(session, tid)
            period_i18n_key = {
                "day": "owner_join_period_day",
                "3d": "owner_join_period_3d",
                "week": "owner_join_period_week",
                "month": "owner_join_period_month",
            }[p]
            label = t(loc, f"reminders.{period_i18n_key}")
            msg = t(loc, "reminders.owner_join_title") + t(
                loc,
                "reminders.owner_join_body",
                period=label,
                joins=joins,
                groups=active_groups,
            )
            try:
                await bot.send_message(tid, msg, parse_mode="Markdown")
                setattr(st, last_attr, now)
                session.add(st)
                await session.commit()
            except Exception as e:
                logger.warning("owner_join_report notify %s (%s): %s", tid, p, e)
                await session.rollback()


def _render_template_text(raw: str, ctx: dict[str, str]) -> str:
    text = str(raw or "")
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text


async def _run_flexible_templates(bot, session: AsyncSession, now: datetime, tpl: dict[str, AdminMessageTemplate]) -> None:
    """Гибкие сообщения по событиям в окне: joins/starts/payments/referral shares."""
    events = (
        "window_group_joins",
        "window_starts",
        "window_payments",
        "window_referral_shares",
    )
    targets = await _owner_admin_target_ids(session)
    if not targets:
        return
    default_tpl_key = {
        "window_group_joins": "reminders.flex_default_window_joins",
        "window_starts": "reminders.flex_default_window_starts",
        "window_payments": "reminders.flex_default_window_payments",
        "window_referral_shares": "reminders.flex_default_window_referral",
    }
    for tpl_row in tpl.values():
        event_key = str(getattr(tpl_row, "event_key", "") or "manual")
        if event_key not in events:
            continue
        if not bool(getattr(tpl_row, "enabled", True)):
            continue
        hours = max(1, min(168, int(getattr(tpl_row, "trigger_hours", 24) or 24)))
        since = now - timedelta(hours=hours)
        count = 0
        amount = 0.0
        if event_key == "window_group_joins":
            q = await session.execute(select(func.count(NewMember.id)).where(NewMember.joined_at >= since))
            count = int(q.scalar() or 0)
        elif event_key == "window_starts":
            q = await session.execute(select(func.count(User.id)).where(User.first_start_at.is_not(None), User.first_start_at >= since))
            count = int(q.scalar() or 0)
        elif event_key == "window_payments":
            q = await session.execute(
                select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0.0)).where(
                    Payment.status == "succeeded",
                    Payment.created_at >= since,
                )
            )
            c, a = q.one_or_none() or (0, 0.0)
            count = int(c or 0)
            amount = float(a or 0.0)
        elif event_key == "window_referral_shares":
            q = await session.execute(select(func.count(ReferralShareHit.id)).where(ReferralShareHit.created_at >= since))
            count = int(q.scalar() or 0)

        if count < max(1, int(getattr(tpl_row, "min_count", 1) or 1)):
            continue
        bucket = f"{event_key}:{now.date().isoformat()}:{hours}:c{count}"
        for tid in targets:
            try:
                loc = await user_locale(session, int(tid))
                ev_k = f"reminders.flex_event.{event_key}"
                ev_label = t(loc, ev_k)
                if ev_label == ev_k:
                    alt = "en" if loc == "ru" else "ru"
                    ev_label = t(alt, ev_k)
                if ev_label == ev_k:
                    ev_label = event_key
                ctx = {
                    "count": str(count),
                    "hours": str(hours),
                    "payments_sum": f"{round(amount, 2):.2f}",
                    "event_label": ev_label,
                    "date": now.date().isoformat(),
                }
                default_text = t(loc, default_tpl_key[event_key], **ctx)
                text_msg = _render_template_text(str(getattr(tpl_row, "body_text", "") or default_text), ctx)
                if not await _template_can_send_now(session, tpl_row, int(tid), now, bucket=bucket):
                    continue
                await bot.send_message(int(tid), text_msg, parse_mode=str(getattr(tpl_row, "parse_mode", "") or "Markdown"))
                await _mark_template_sent(session, tpl_row, int(tid), bucket=bucket)
            except Exception as e:
                logger.warning("flex_template %s to %s: %s", event_key, tid, e)


async def _run_subscription_expired(bot, session: AsyncSession, now: datetime) -> None:
    """Проверка истечения подписки: перевод на FREE, уведомление."""
    res = await session.execute(
        select(User).where(
            User.subscription_until.isnot(None),
            User.subscription_until < now,
            User.telegram_id.isnot(None),
        )
    )
    for user in res.scalars().all():
        try:
            if (user.tariff or "").lower() not in ("premium", "pro", "business"):
                continue
            uid = int(getattr(user, "telegram_id", 0) or 0)
            if uid and is_full_admin_user(user, uid):
                continue
            src = str(getattr(user, "subscription_source", "") or "").strip().lower()
            loc = normalize_locale(getattr(user, "language", None))
            user.tariff = Tariff.FREE.value
            user.chat_limit = TARIFF_CHAT_LIMITS[Tariff.FREE.value]
            user.group_limit = TARIFF_GROUP_LIMITS[Tariff.FREE.value]
            user.channel_limit = TARIFF_CHANNEL_LIMITS[Tariff.FREE.value]
            await enforce_owner_active_chat_limit(session, int(uid), int(TARIFF_CHAT_LIMITS[Tariff.FREE.value]))
            # Промо-истечение: отдельное одноразовое уведомление, без цепочки follow-up «автосписания».
            if src == "promo":
                user.reminder_stage = max(int(getattr(user, "reminder_stage", 0) or 0), 4)
            else:
                # Сохраняем expired subscription_until как якорь для follow-up кампании.
                user.reminder_stage = max(int(getattr(user, "reminder_stage", 0) or 0), 100)
            await session.commit()
            if src == "promo":
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                billing_link = await _startapp_link_for_bot(bot, "billing")
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=t(loc, "reminders.btn_billing"), url=billing_link),
                ]])
                await bot.send_message(uid, t(loc, "reminders.promo_ended"), parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
            elif src == "payment":
                await send_expired_guard_payment(bot, uid)
            else:
                await send_expired_warning(bot, uid)
        except Exception as e:
            logger.warning("subscription_expired user=%s: %s", getattr(user, "telegram_id"), e)
            await session.rollback()


async def _run_subscription_expired_followups(bot, session: AsyncSession, now: datetime) -> None:
    """Follow-up после истечения: 7 дней, 3 дня, 7 дней, 3 дня..."""
    # Скаляры + update по id: после await на ORM-объекте User ленивая подгрузка даёт MissingGreenlet (asyncpg).
    res = await session.execute(
        select(
            User.id,
            User.telegram_id,
            User.first_name,
            User.subscription_until,
            User.reminder_stage,
        ).where(
            User.subscription_until.isnot(None),
            User.subscription_until < now,
            User.telegram_id.isnot(None),
            User.tariff == Tariff.FREE.value,
            User.reminder_stage >= 100,
        )
    )
    for user_id, telegram_id, first_name, expired_at, reminder_stage in res.all():
        tid = int(telegram_id)
        try:
            if not expired_at:
                continue
            if expired_at.tzinfo is None:
                expired_at = expired_at.replace(tzinfo=timezone.utc)
            elapsed_days = (now - expired_at).total_seconds() / 86400.0
            stage = int(reminder_stage or 100)
            followups_sent = max(0, stage - 100)
            next_threshold = _expired_reminder_threshold_days(followups_sent + 1)
            if elapsed_days < next_threshold:
                continue
            loc = await user_locale(session, tid)
            await send_trial_warning_preview_guard(
                bot,
                tid,
                display_name=first_name,
                locale=loc,
            )
            await session.execute(update(User).where(User.id == int(user_id)).values(reminder_stage=stage + 1))
            await session.commit()
        except Exception as e:
            _log_expected_telegram_user_block(logger, "subscription_expired_followup", tid, e)
            await session.rollback()


async def _run_daily_credit_burn(session: AsyncSession, now: datetime) -> None:
    """Ежедневное списание кредитов для active premium с защитой от дублей (ledger key)."""
    today_key = now.date().isoformat()
    res = await session.execute(
        select(User).where(
            User.tariff.in_([Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value]),
            User.subscription_until.isnot(None),
            User.subscription_until > now,
        )
    )
    users = list(res.scalars().all())
    for user in users:
        try:
            ext_key = f"daily_burn:{today_key}"
            exists = await session.execute(
                text(
                    "SELECT 1 FROM credit_ledger WHERE user_id = :uid AND external_key = :ek LIMIT 1"
                ),
                {"uid": int(user.id), "ek": ext_key},
            )
            if exists.first():
                continue

            bal = float(getattr(user, "credits_balance", 0.0) or 0.0)
            if bal <= 0:
                # До даты окончания подписки не переводим в FREE:
                # истечение уже обрабатывает _run_subscription_expired.
                await session.execute(
                    text(
                        "INSERT INTO credit_ledger (user_id, delta, reason, external_key) "
                        "VALUES (:uid, :delta, 'daily_burn', :ek)"
                    ),
                    {"uid": int(user.id), "delta": 0.0, "ek": ext_key},
                )
                await session.commit()
                continue

            sub_until = user.subscription_until
            if not sub_until:
                continue
            if sub_until.tzinfo is None:
                sub_until = sub_until.replace(tzinfo=timezone.utc)
            days_left = max(1, (sub_until.date() - now.date()).days + 1)
            burn = round(bal / days_left, 2)
            if burn <= 0:
                burn = min(0.01, bal)
            burn = min(burn, bal)

            user.credits_balance = round(max(0.0, bal - burn), 2)
            await session.execute(
                text(
                    "INSERT INTO credit_ledger (user_id, delta, reason, external_key) "
                    "VALUES (:uid, :delta, 'daily_burn', :ek)"
                ),
                {"uid": int(user.id), "delta": -float(burn), "ek": ext_key},
            )

            if user.credits_balance <= 0:
                user.credits_balance = 0.0
            await session.commit()
        except Exception as e:
            logger.warning("daily_burn user=%s: %s", getattr(user, "telegram_id", None), e)
            await session.rollback()


async def _run_guard_25_days_story(bot, session: AsyncSession, now: datetime) -> None:
    """Через 25 дней после /start отправить персональную историю пользы Guard."""
    users = (
        await session.execute(
            select(User).where(
                User.telegram_id.is_not(None),
                User.first_start_at.is_not(None),
            )
        )
    ).scalars().all()
    billing_link = await _startapp_link_for_bot(bot, "billing")
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    for u in users:
        try:
            loc = normalize_locale(getattr(u, "language", None))
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t(loc, "reminders.btn_open_guard_premium"), url=billing_link)]]
            )
            uid = int(getattr(u, "telegram_id", 0) or 0)
            if uid <= 0:
                continue
            started = getattr(u, "first_start_at", None)
            if not started:
                continue
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = now - started
            if elapsed < timedelta(days=25):
                continue
            bucket = f"guard25d:{uid}"
            if await _dispatch_bucket_sent(session, uid, bucket):
                continue
            start_25 = started
            end_25 = started + timedelta(days=25)
            owned_chat_ids_q = await session.execute(
                select(Chat.id).where(
                    Chat.owner_user_id == uid,
                    Chat.is_log_chat.is_(False),
                )
            )
            owned_ids = [int(x[0]) for x in owned_chat_ids_q.all() if int(x[0] or 0) != 0]
            chats_count_q = await session.execute(
                select(func.count(Chat.id)).where(
                    Chat.owner_user_id == uid,
                    Chat.is_log_chat.is_(False),
                    Chat.is_active.is_(True),
                )
            )
            chats_count = int(chats_count_q.scalar() or 0)
            moderation_count = 0
            joins_count = 0
            if owned_ids:
                mod_q = await session.execute(
                    select(func.count(ModerationLog.id)).where(
                        ModerationLog.chat_id.in_(owned_ids),
                        ModerationLog.created_at >= start_25,
                        ModerationLog.created_at <= end_25,
                    )
                )
                join_q = await session.execute(
                    select(func.count(NewMember.id)).where(
                        NewMember.chat_id.in_(owned_ids),
                        NewMember.joined_at >= start_25,
                        NewMember.joined_at <= end_25,
                    )
                )
                moderation_count = int(mod_q.scalar() or 0)
                joins_count = int(join_q.scalar() or 0)
            # Линейка оценки ручной модерации:
            # в среднем ~35 сек на событие (проверить, открыть профиль, действие, контроль),
            # ставка модератора ~600 ₽/ч.
            hours_saved = round((moderation_count * 35.0) / 3600.0, 1)
            human_cost_rub = int(round(hours_saved * 600))
            msg = t(
                loc,
                "reminders.guard_25_days",
                moderation_count=moderation_count,
                chats_count=chats_count,
                joins_count=joins_count,
                human_cost_rub=human_cost_rub,
                hours_saved=hours_saved,
            )
            await bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            logger.warning("guard_25_days notify user=%s: %s", getattr(u, "telegram_id", None), e)
            continue
        try:
            await _mark_dispatch_bucket(session, uid, bucket)
        except Exception as e:
            logger.warning("guard_25_days mark user=%s: %s", getattr(u, "telegram_id", None), e)
            await session.rollback()


async def _run_subscription_renewal_reminders(bot, session: AsyncSession, now: datetime) -> None:
    """Напоминания перед продлением: за 5 дней и за 1 час до окончания."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    billing_link = await _startapp_link_for_bot(bot, "billing")
    users = (
        await session.execute(
            select(User).where(
                User.telegram_id.is_not(None),
                User.subscription_until.is_not(None),
                User.tariff.in_([Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value]),
            )
        )
    ).scalars().all()
    for u in users:
        try:
            uid = int(getattr(u, "telegram_id", 0) or 0)
            if uid <= 0:
                continue
            loc = normalize_locale(getattr(u, "language", None))
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t(loc, "reminders.btn_billing"), url=billing_link)]]
            )
            src = str(getattr(u, "subscription_source", "") or "").strip().lower()
            if src != "payment":
                logger.info("renewal_reminder skip user=%s reason=source_%s", uid, src or "unknown")
                continue
            if not bool(getattr(u, "payment_method_bound", False)):
                logger.info("renewal_reminder skip user=%s reason=payment_method_not_bound", uid)
                continue
            if not await _user_has_successful_subscription_payment(session, int(getattr(u, "id", 0) or 0)):
                logger.info("renewal_reminder skip user=%s reason=no_success_payment", uid)
                continue
            sub_until = getattr(u, "subscription_until", None)
            if not sub_until:
                continue
            if sub_until.tzinfo is None:
                sub_until = sub_until.replace(tzinfo=timezone.utc)
            delta = sub_until - now
            period_key = sub_until.date().isoformat()
            if delta <= SUB_END_5D_WINDOW and delta > timedelta(days=4):
                bucket = f"sub_end_5d:{uid}:{period_key}"
                if await _claim_dispatch_bucket(session, uid, bucket):
                    await bot.send_message(
                        uid,
                        t(
                            loc,
                            "reminders.sub_end_5d",
                            discount_percent=_annual_discount_percent(),
                            charge_window_hours=autorenew_window_hours(),
                        ),
                        parse_mode="Markdown",
                        reply_markup=kb,
                        disable_web_page_preview=True,
                    )
                else:
                    logger.info("renewal_reminder skip user=%s reason=duplicate_bucket bucket=%s", uid, bucket)
            if delta <= SUB_END_1H_WINDOW and delta > timedelta(minutes=5):
                bucket = f"sub_end_1h:{uid}:{period_key}"
                if await _claim_dispatch_bucket(session, uid, bucket):
                    pm_stored = bool(str(getattr(u, "yookassa_payment_method_id", "") or "").strip())
                    if yookassa_autorenew_worker_enabled() and pm_stored:
                        body = t(
                            loc,
                            "reminders.sub_end_1h_autorenew",
                            charge_window_hours=autorenew_window_hours(),
                        )
                    else:
                        body = t(loc, "reminders.sub_end_1h_manual")
                    await bot.send_message(uid, body, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
                else:
                    logger.info("renewal_reminder skip user=%s reason=duplicate_bucket bucket=%s", uid, bucket)
        except Exception as e:
            logger.warning("subscription_renewal_reminder user=%s: %s", getattr(u, "telegram_id", None), e)
            await session.rollback()


async def _run_autorenew_retries(bot, session: AsyncSession, now: datetime) -> None:
    """
    Логика soft-ретрая после неуспешного продления:
    - 1-й день после окончания: даём grace 24ч + отправляем предупреждение.
    - после grace: переводим на FREE и отправляем сообщение о повторной неудаче.

    Тексты про «списание не прошло» — только если фоновый воркер ЮKassa включён и была
    реальная попытка API (autorenew_last_attempt_at) с сохранённым payment_method_id.
    """
    if not yookassa_autorenew_worker_enabled():
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    billing_link = await _startapp_link_for_bot(bot, "billing")

    users = (
        await session.execute(
            select(User).where(
                User.telegram_id.is_not(None),
                User.subscription_until.is_not(None),
                User.tariff.in_([Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value]),
            )
        )
    ).scalars().all()
    for u in users:
        try:
            uid = int(getattr(u, "telegram_id", 0) or 0)
            if uid <= 0:
                continue
            loc = normalize_locale(getattr(u, "language", None))
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t(loc, "reminders.btn_go_tariffs"), url=billing_link)]]
            )
            src = str(getattr(u, "subscription_source", "") or "").strip().lower()
            if src != "payment":
                logger.info("autorenew_retries skip user=%s reason=source_%s", uid, src or "unknown")
                continue
            if not bool(getattr(u, "payment_method_bound", False)):
                logger.info("autorenew_retries skip user=%s reason=payment_method_not_bound", uid)
                continue
            if not await _user_has_successful_subscription_payment(session, int(getattr(u, "id", 0) or 0)):
                logger.info("autorenew_retries skip user=%s reason=no_success_payment", uid)
                continue
            if not str(getattr(u, "yookassa_payment_method_id", "") or "").strip():
                logger.info("autorenew_retries skip user=%s reason=no_stored_payment_method", uid)
                continue
            last_att = getattr(u, "autorenew_last_attempt_at", None)
            sub_until = getattr(u, "subscription_until", None)
            if not sub_until:
                continue
            if sub_until.tzinfo is None:
                sub_until = sub_until.replace(tzinfo=timezone.utc)
            if now < sub_until:
                continue
            if last_att is None:
                logger.info("autorenew_retries skip user=%s reason=no_autorenew_api_attempt", uid)
                continue
            fail_bucket = f"autorenew_fail_1:{uid}:{sub_until.date().isoformat()}"
            retry_bucket = f"autorenew_fail_2:{uid}:{sub_until.date().isoformat()}"
            if await _claim_dispatch_bucket(session, uid, fail_bucket):
                u.subscription_until = now + timedelta(days=1)
                await session.commit()
                await bot.send_message(uid, t(loc, "reminders.autopay_fail"), parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
                continue
            logger.info("autorenew_retries skip user=%s reason=duplicate_bucket bucket=%s", uid, fail_bucket)
            if now >= sub_until and await _claim_dispatch_bucket(session, uid, retry_bucket):
                if uid and is_full_admin_user(u, uid):
                    continue
                u.tariff = Tariff.FREE.value
                u.chat_limit = TARIFF_CHAT_LIMITS[Tariff.FREE.value]
                u.group_limit = TARIFF_GROUP_LIMITS[Tariff.FREE.value]
                u.channel_limit = TARIFF_CHANNEL_LIMITS[Tariff.FREE.value]
                await enforce_owner_active_chat_limit(session, int(uid), int(TARIFF_CHAT_LIMITS[Tariff.FREE.value]))
                u.reminder_stage = max(int(getattr(u, "reminder_stage", 0) or 0), 100)
                await session.commit()
                await bot.send_message(uid, t(loc, "reminders.autopay_retry_fail"), parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
            elif now >= sub_until:
                logger.info("autorenew_retries skip user=%s reason=duplicate_bucket bucket=%s", uid, retry_bucket)
        except Exception as e:
            logger.warning("autorenew_retries user=%s: %s", getattr(u, "telegram_id", None), e)
            await session.rollback()


async def run_reminders_and_guardian(bot) -> None:
    """Запуск всех проверок: напоминания, Guard раз в 3 дня, автоотчёты раз в сутки."""
    now = datetime.now(timezone.utc)
    # Premium-триал DM-серии идут ПЕРВЫМИ (приоритет in-trial > pre-trial), затем
    # передаём множество получателей в no_group/reports, чтобы юзер не получил
    # два письма в одни сутки.
    trial_recipients: set[int] = set()
    try:
        async with await get_session() as session:
            in_trial_sent = await _run_reminders_in_trial(bot, session, now)
            trial_recipients |= in_trial_sent
    except Exception as e:
        logger.warning("reminders in_trial skipped: %s", e)
    try:
        async with await get_session() as session:
            pre_trial_sent = await _run_reminders_pre_trial(bot, session, now)
            trial_recipients |= pre_trial_sent
    except Exception as e:
        logger.warning("reminders pre_trial skipped: %s", e)
    async with await get_session() as session:
        tpl = await _load_message_templates(session)
        await _run_reminders_no_group(bot, session, now, tpl, skip_user_ids=trial_recipients)
    async with await get_session() as session:
        tpl = await _load_message_templates(session)
        await _run_reminders_reports_chat(bot, session, now, tpl, skip_user_ids=trial_recipients)
    try:
        n_charged = await run_yookassa_autorenew_batch(bot=bot, limit=50)
        if n_charged:
            logger.info("yookassa autorenew: %s successful immediate charges", n_charged)
    except Exception as e:
        logger.warning("yookassa autorenew batch failed: %s", e)
    async with await get_session() as session:
        await _run_autorenew_retries(bot, session, now)
    async with await get_session() as session:
        await _run_subscription_expired(bot, session, now)
    async with await get_session() as session:
        await _run_subscription_expired_followups(bot, session, now)
    async with await get_session() as session:
        await _run_subscription_renewal_reminders(bot, session, now)
    async with await get_session() as session:
        await _run_daily_credit_burn(session, now)
    try:
        async with await get_session() as session:
            await _run_guardian_periodic_messages(bot, session, now)
    except Exception as e:
        if "antinakrutka_enabled" in str(e) or "UndefinedColumnError" in str(e):
            logger.warning("guardian_periodic skipped (run migration 008): %s", e)
        else:
            raise
    try:
        async with await get_session() as session:
            await _run_auto_reports(bot, session, now)
    except Exception as e:
        if "antinakrutka_enabled" in str(e) or "UndefinedColumnError" in str(e):
            logger.warning("auto_reports skipped (run migration 008): %s", e)
        else:
            raise
    try:
        async with await get_session() as session:
            tpl = await _load_message_templates(session)
            await _run_owner_daily_report(bot, session, now, tpl)
    except Exception as e:
        logger.warning("owner_daily_report skipped: %s", e)
    try:
        async with await get_session() as session:
            await _run_owner_join_reports(bot, session, now)
    except Exception as e:
        logger.warning("owner_join_reports skipped: %s", e)
    try:
        async with await get_session() as session:
            await run_spam_spike_owner_manager_alerts(bot, session, now)
    except Exception as e:
        logger.warning("spam_spike_notify skipped: %s", e)
    try:
        async with await get_session() as session:
            tpl = await _load_message_templates(session)
            await _run_flexible_templates(bot, session, now, tpl)
    except Exception as e:
        logger.warning("flexible_templates skipped: %s", e)
    try:
        async with await get_session() as session:
            await _run_guard_25_days_story(bot, session, now)
    except Exception as e:
        logger.warning("guard_25_days_story skipped: %s", e)


async def reminder_loop(bot, interval_sec: int = 900) -> None:
    """Фоновый цикл: каждые interval_sec секунд запускает run_reminders_and_guardian."""
    while True:
        try:
            await run_reminders_and_guardian(bot)
        except Exception as e:
            logger.exception("reminder_loop: %s", e)
        await asyncio.sleep(interval_sec)
