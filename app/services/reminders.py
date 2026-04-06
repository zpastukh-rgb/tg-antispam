# app/services/reminders.py
"""ТЗ Напоминания: напоминания пользователю (нет группы / нет чата отчётов), Guardian-сообщения раз в 3 дня."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import User, Chat, Rule
from app.services.user_service import count_protected_chats, TARIFF_CHAT_LIMITS
from app.db.models import Tariff

logger = logging.getLogger(__name__)

# Интервалы напоминаний (ТЗ)
REMINDER_12H = timedelta(hours=12)
REMINDER_24H = timedelta(hours=24)
REMINDER_3D = timedelta(days=3)
GUARDIAN_MSG_INTERVAL = timedelta(hours=72)  # не чаще 1 раз в 72 часа
GUARDIAN_ACTIVITY_WINDOW = timedelta(hours=24)  # «≥10 сообщений за сутки» — считаем активным если была модерация
AUTO_REPORT_INTERVAL = timedelta(hours=24)  # дайджест раз в сутки
EXPIRED_REMINDER_PATTERN_DAYS = (7, 3)  # после первого уведомления: раз в неделю, затем через 3 дня, по кругу

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
EXPIRED_WARNING_PHOTO_PATH = _STATIC_DIR / "trial_warning.jpg"
EXPIRED_WARNING_FALLBACK_PATH = Path(__file__).resolve().parent.parent.parent / "webapp" / "public" / "logo.png"
EXPIRED_WARNING_PHOTO_FILE_ID = (os.getenv("TRIAL_WARNING_PHOTO_FILE_ID") or "").strip()
EXPIRED_WARNING_TEXT = (
    "⚠ *Guard сообщает: триальный период завершён*\n\n"
    "Бот продолжает работать, но расширенные Premium-функции отключены.\n\n"
    "Без усиленной защиты в чате чаще появляются:\n"
    "⛔ реклама казино и мошеннических схем\n"
    "⛔ предложения по запрещённым веществам\n"
    "⛔ ссылки на нелегальный контент\n\n"
    "По [судебной практике](https://dzen.ru/a/Z4-D4Y6bG07j33Kc) такие ситуации уже приводили к рискам для администраторов.\n\n"
    "Guard не допустит такого исхода. Продлите защиту сейчас и держите чат под контролем."
)

# Тексты напоминаний (ТЗ)
REMINDER_12H_TEXT = (
    "😈 AntiSpam Guardian напоминает.\n\n"
    "Вы запустили бота, но ещё не подключили ни одной группы.\n\n"
    "Я могу защищать чат от:\n"
    "• спама\n"
    "• ссылочного мусора\n"
    "• рейдов\n"
    "• ботов\n\n"
    "Подключение занимает 10 секунд."
)
REMINDER_24H_TEXT = (
    "😈 Я всё ещё жду.\n\n"
    "Пока я не подключён — спамеры чувствуют себя спокойно.\n"
    "Подключите группу и я начну работу."
)
REMINDER_3D_TEXT = (
    "😈 Последнее напоминание.\n\n"
    "Я могу защищать ваши чаты автоматически.\n"
    "Добавьте меня администратором и я начну работу."
)

REPORTS_REMINDER_TEXT = (
    "😈 AntiSpam Guardian советует подключить чат отчётов.\n\n"
    "Туда будут приходить:\n"
    "• удаления\n"
    "• муты\n"
    "• баны\n"
    "• кнопки размута\n\n"
    "Так администратору удобнее следить за порядком."
)

# Guardian сообщения в группе раз в 3 дня (ТЗ, случайный выбор)
GUARDIAN_PERIODIC_TEXTS = [
    "😈 AntiSpam Guardian на месте.\nПока всё спокойно.\nСпамеров не обнаружено.\nНо если появятся — разберусь.",
    "🛡 AntiSpam Guardian проверил чат.\nСпам не обнаружен.\nМожно продолжать общаться спокойно.",
    "😈 Я здесь.\nСлежу за ссылками,\nботами\nи подозрительными сообщениями.\nЕсли кто-то решит спамить — долго не проживёт.",
    "🛡 Guardian проверяет чат.\nЕсли заметите странные ссылки — можете не переживать.\nЯ их тоже вижу.",
    "😈 AntiSpam Guardian на дежурстве.\nПорядок в чате поддерживается автоматически.",
]


def _billing_url() -> str | None:
    base = (os.getenv("MINI_APP_URL") or os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/billing"


def _expired_reminder_threshold_days(n: int) -> int:
    """Порог в днях для n-го follow-up после первого уведомления об истечении."""
    total = 0
    for i in range(n):
        total += EXPIRED_REMINDER_PATTERN_DAYS[i % len(EXPIRED_REMINDER_PATTERN_DAYS)]
    return total


async def send_expired_warning(bot, user_id: int) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from aiogram.types import FSInputFile
    from aiogram.exceptions import TelegramBadRequest
    url = _billing_url()
    if url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Продлить защиту", web_app=WebAppInfo(url=url)),
        ]])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Продлить защиту", callback_data="p:billing"),
        ]])
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
                caption=EXPIRED_WARNING_TEXT,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=EXPIRED_WARNING_TEXT,
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
                caption=EXPIRED_WARNING_TEXT,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        elif EXPIRED_WARNING_FALLBACK_PATH.exists():
            fallback_photo = FSInputFile(str(EXPIRED_WARNING_FALLBACK_PATH))
            await bot.send_photo(
                chat_id=user_id,
                photo=fallback_photo,
                caption=EXPIRED_WARNING_TEXT,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=EXPIRED_WARNING_TEXT,
                parse_mode="Markdown",
                reply_markup=kb,
                disable_web_page_preview=True,
            )


async def _run_reminders_no_group(bot, session: AsyncSession, now: datetime) -> None:
    """Напоминания: пользователь сделал /start, но не подключил ни одной группы."""
    res = await session.execute(
        select(User).where(User.first_start_at.isnot(None)).where(User.reminder_stage < 4)
    )
    users = list(res.scalars().all())
    for user in users:
        try:
            started_at = user.first_start_at
            if not started_at:
                continue
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed = now - started_at
            stage = user.reminder_stage or 0

            if stage == 0 and elapsed >= REMINDER_12H:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = REMINDER_12H_TEXT
                button_text = "➕ Подключить группу"
                user.reminder_stage = 1
            elif stage == 1 and elapsed >= REMINDER_24H:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = REMINDER_24H_TEXT
                button_text = "🛡 Подключить группу"
                user.reminder_stage = 2
            elif stage == 2 and elapsed >= REMINDER_3D:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = REMINDER_3D_TEXT
                button_text = "➕ Подключить группу"
                user.reminder_stage = 4
            else:
                continue

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=button_text, callback_data="st:panel"),
            ]])
            await bot.send_message(
                user.telegram_id,
                text,
                parse_mode=None,
                reply_markup=kb,
            )
            await session.commit()
        except Exception as e:
            logger.warning("reminder no_group user=%s: %s", getattr(user, "telegram_id"), e)
            await session.rollback()


async def _run_reminders_reports_chat(bot, session: AsyncSession, now: datetime) -> None:
    """Напоминание: группа подключена, но чат отчётов не выбран (log_chat_id = null)."""
    # Пользователи, у которых есть хотя бы один защищаемый чат без log_chat_id
    res = await session.execute(
        select(User).where(User.reports_reminder_sent_at.is_(None)).where(User.first_start_at.isnot(None))
    )
    users = list(res.scalars().all())
    for user in users:
        try:
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
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📊 Подключить чат отчётов", callback_data="st:panel"),
            ]])
            await bot.send_message(
                user.telegram_id,
                REPORTS_REMINDER_TEXT,
                parse_mode=None,
                reply_markup=kb,
            )
            user.reports_reminder_sent_at = now
            await session.commit()
        except Exception as e:
            logger.warning("reminder reports user=%s: %s", getattr(user, "telegram_id"), e)
            await session.rollback()


async def _run_guardian_periodic_messages(bot, session: AsyncSession, now: datetime) -> None:
    """Guardian сообщения в группе раз в 3 дня (72ч), только если чат был активен (last_activity_at за 24ч)."""
    res = await session.execute(
        select(Chat, Rule).join(Rule, Chat.id == Rule.chat_id).where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
        )
    )
    for row in res.all():
        chat_row, rule = row[0], row[1]
        if not getattr(rule, "guardian_messages_enabled", True):
            continue
        last_sent = getattr(rule, "last_guardian_message_at", None)
        if last_sent:
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if (now - last_sent) < GUARDIAN_MSG_INTERVAL:
                continue
        last_activity = getattr(chat_row, "last_activity_at", None)
        if last_activity:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            if (now - last_activity) > GUARDIAN_ACTIVITY_WINDOW:
                continue
        # Если last_activity_at нет — всё равно шлём раз в 72ч (упрощение)
        try:
            text = random.choice(GUARDIAN_PERIODIC_TEXTS)
            await bot.send_message(chat_row.id, text)
            rule.last_guardian_message_at = now
            await session.commit()
        except Exception as e:
            logger.warning("guardian periodic chat=%s: %s", chat_row.id, e)
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
            text = (
                "📊 *Автоотчёт Guardian*\n\n"
                f"Чат: *{title}*\n"
                f"За последние 24 ч: зафиксировано действий — *{total}*\n\n"
                "_Подробные отчёты приходят сюда при каждом удалении/муте/бане._"
            )
            await bot.send_message(log_chat_id, text, parse_mode="Markdown")
            rule.last_auto_report_at = now
            await session.commit()
        except Exception as e:
            logger.warning("auto_report chat=%s log=%s: %s", chat_row.id, log_chat_id, e)
            await session.rollback()


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
            user.tariff = Tariff.FREE.value
            user.chat_limit = TARIFF_CHAT_LIMITS[Tariff.FREE.value]
            # Сохраняем expired subscription_until как якорь для follow-up кампании.
            user.reminder_stage = max(int(getattr(user, "reminder_stage", 0) or 0), 100)
            await session.commit()
            await send_expired_warning(bot, user.telegram_id)
        except Exception as e:
            logger.warning("subscription_expired user=%s: %s", getattr(user, "telegram_id"), e)
            await session.rollback()


async def _run_subscription_expired_followups(bot, session: AsyncSession, now: datetime) -> None:
    """Follow-up после истечения: 7 дней, 3 дня, 7 дней, 3 дня..."""
    res = await session.execute(
        select(User).where(
            User.subscription_until.isnot(None),
            User.subscription_until < now,
            User.telegram_id.isnot(None),
            User.tariff == Tariff.FREE.value,
            User.reminder_stage >= 100,
        )
    )
    for user in res.scalars().all():
        try:
            expired_at = user.subscription_until
            if not expired_at:
                continue
            if expired_at.tzinfo is None:
                expired_at = expired_at.replace(tzinfo=timezone.utc)
            elapsed_days = (now - expired_at).total_seconds() / 86400.0
            stage = int(getattr(user, "reminder_stage", 100) or 100)
            followups_sent = max(0, stage - 100)
            next_threshold = _expired_reminder_threshold_days(followups_sent + 1)
            if elapsed_days < next_threshold:
                continue
            await send_expired_warning(bot, user.telegram_id)
            user.reminder_stage = stage + 1
            await session.commit()
        except Exception as e:
            logger.warning("subscription_expired_followup user=%s: %s", getattr(user, "telegram_id"), e)
            await session.rollback()


async def run_reminders_and_guardian(bot) -> None:
    """Запуск всех проверок: напоминания, Guardian раз в 3 дня, автоотчёты раз в сутки."""
    now = datetime.now(timezone.utc)
    async with await get_session() as session:
        await _run_reminders_no_group(bot, session, now)
    async with await get_session() as session:
        await _run_reminders_reports_chat(bot, session, now)
    async with await get_session() as session:
        await _run_subscription_expired(bot, session, now)
    async with await get_session() as session:
        await _run_subscription_expired_followups(bot, session, now)
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


async def reminder_loop(bot, interval_sec: int = 900) -> None:
    """Фоновый цикл: каждые interval_sec секунд запускает run_reminders_and_guardian."""
    while True:
        try:
            await run_reminders_and_guardian(bot)
        except Exception as e:
            logger.exception("reminder_loop: %s", e)
        await asyncio.sleep(interval_sec)
