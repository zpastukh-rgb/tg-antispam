# app/services/reminders.py
"""ТЗ Напоминания: напоминания пользователю (нет группы / нет чата отчётов), Guardian-сообщения раз в 3 дня."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import User, Chat, Rule
from app.services.user_service import count_protected_chats, TARIFF_CHAT_LIMITS
from app.db.models import Tariff
from app.texts.guardian_billing import (
    REMINDER_PREMIUM_WEEKLY,
    REMINDER_PREMIUM_SOFT,
    SUBSCRIPTION_EXPIRED,
)

logger = logging.getLogger(__name__)

# Интервалы напоминаний (ТЗ)
REMINDER_12H = timedelta(hours=12)
REMINDER_24H = timedelta(hours=24)
REMINDER_3D = timedelta(days=3)
GUARDIAN_MSG_INTERVAL = timedelta(hours=72)  # не чаще 1 раз в 72 часа
GUARDIAN_ACTIVITY_WINDOW = timedelta(hours=24)  # «≥10 сообщений за сутки» — считаем активным если была модерация
AUTO_REPORT_INTERVAL = timedelta(hours=24)  # дайджест раз в сутки

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
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    CB_BILLING = "p:billing"

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
            user.subscription_until = None
            await session.commit()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Продлить Premium", callback_data=CB_BILLING)],
            ])
            await bot.send_message(
                user.telegram_id,
                SUBSCRIPTION_EXPIRED,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning("subscription_expired user=%s: %s", getattr(user, "telegram_id"), e)
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
