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
)
from app.services.chat_limit_enforcer import enforce_owner_active_chat_limit
from app.db.models import Tariff
from app.services.admin_roles import is_full_admin_user
from app.services.spam_spike_notify import run_spam_spike_owner_manager_alerts
from app.services.chat_supergroup_migrate import parse_migrate_to_supergroup_id, remap_group_chat_ids
from app.texts.guardian_billing import PREMIUM_PLANS
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
EXPIRED_WARNING_TEXT = (
    "Эх 🥹\n\n"
    "🔔 Здравствуйте!\n"
    "Сообщаем, что срок действия вашей подписки Guard истёк.\n\n"
    "Чтобы снова получить полный доступ ко всем инструментам защиты,\n"
    "пожалуйста, продлите подписку в приложении по кнопке ниже 😇"
)
TRIAL_PREVIEW_GUARD_TEXT = (
    "⚠ *Guard: подписка завершилась*\n\n"
    "Guard остаётся в чате, но без активной подписки не сможет держать полный автоматический режим.\n"
    "Часть опасного контента придётся чистить вручную.\n\n"
    "Без активной защиты в ленте чаще появляются\n"
    "⛔ реклама казино, мошенников и крипто-схем\n"
    "❌ сообщения о запрещённых веществах\n"
    "👎 ссылки на нелегальный контент\n\n"
    "*Важно по закону:* ст. 6.13 КоАП и ст. 228.1 УК РФ.\n"
    "Если админ знал о таких публикациях и не удалил их, возможна ответственность.\n"
    "Примеры из [судебной практики](https://dzen.ru/a/Z4-D4Y6bG07j33Kc) уже есть.\n\n"
    "Продлите подписку и верните Guard в полный боевой режим."
)
# Истёк оплаченный период (не промо): без формулировок про «неудачное списание» — период просто закончился.
GUARD_PAYMENT_SUB_EXPIRED_TEXT = (
    "🛡 *Guard: оплаченный период Premium закончился*\n\n"
    "Бот в чатах *остаётся*, но без активной подписки Guard держит только *базовый* режим: лимиты и часть правил будут уже не те, "
    "что на полном Premium.\n\n"
    "Автопродление с карты ЮKassa срабатывает только если вы сохраняли способ оплаты и на стороне сервиса включены попытки списания. "
    "Если период просто истёк — это не обязательно «ошибка банка»: чаще всего достаточно *продлить вручную* в мини-приложении.\n\n"
    "Без полной защиты в ленте чаще проскакивают\n"
    "⛔ казино и мошенники\n"
    "❌ запрещённые темы\n"
    "👎 сомнительные ссылки\n\n"
    "*По закону:* ст. 6.13 КоАП и ст. 228.1 УК РФ — модератору важно не оставлять опасный контент без реакции.\n\n"
    "Верните Premium одним нажатием — кнопка ниже."
)
GUARD_25_DAYS_TEXT = (
    "🛡 *Guard рядом уже 25 дней* — и вот что мы сделали вместе:\n\n"
    "• Остановлено и удалено: *{moderation_count}*\n"
    "• Под защитой сейчас: *{chats_count}* чатов\n"
    "• Подключились в ваши чаты: *{joins_count}* участников\n\n"
    "Если бы это делалось вручную,\n"
    f"это заняло бы примерно *{{hours_saved}} ч* и стоило около *{{human_cost_rub}} ₽*.\n\n"
    "Спасибо, что доверяете Guard безопасность ваших сообществ 💚"
)
SUB_END_5D_TEXT = (
    "Хай 👋\n\n"
    "До окончания периода *Guard Premium* осталось *5 дней*.\n\n"
    "Если у вас привязана карта ЮKassa, автосписание мы *по очереди пытаемся провести* в течение "
    "*последних {charge_window_hours} ч.* до конца периода (сервер обходит подписчиков по расписанию — не строго в последний час).\n\n"
    "Проверьте, что на карте достаточно средств.\n\n"
    "💡 Если продлевать сразу на *12 месяцев*, экономия составляет примерно *{discount_percent}%*.\n\n"
    "Все настройки — в разделе «Тариф и оплата»."
)
# Менее чем за час до конца периода: совпадает с «последним шансом» попасть в окно реального автосписания
SUB_END_1H_TEXT_AUTORENEW = (
    "Напомним бережно 💛\n\n"
    "До окончания *Guard Premium* осталось *меньше часа*.\n\n"
    "Если карта привязана, в ближайшее время сервис *попытается списать продление* "
    "— это та же механика, что и фоновые попытки ЮKassa (окно до *{charge_window_hours} ч.* до срока уже могло начаться ранее).\n\n"
    "Проверьте баланс карты. Отключить автосписание — в «Тариф и оплата».\n\n"
    "Спасибо, что вы с Guard 🛡"
)
SUB_END_1H_TEXT_MANUAL = (
    "Напомним бережно 💛\n\n"
    "До окончания *Guard Premium* осталось *меньше часа*.\n\n"
    "Автосписание по карте сейчас недоступно (нет сохранённого способа оплаты) — "
    "продлите подписку вручную в разделе «Тариф и оплата», чтобы защита не прерывалась.\n\n"
    "Спасибо, что вы с Guard 🛡"
)
PROMO_ENDED_TEXT = (
    "Промокодный период *Guard Premium* завершился.\n\n"
    "Если у вас есть новый промокод — активируйте его в разделе «Аккаунт → Промокод».\n"
    "Или подключите Premium в «Тариф и оплата», чтобы снова получить:\n"
    "• рассылку\n"
    "• AI-функции\n"
    "• гибкие настройки управления\n"
    "• подключение админов к управлению группой через своего бота."
)
AUTOPAY_FAIL_TEXT = (
    "Попытка автосписания за продление Guard через ЮKassa *не прошла* (ответ банка или ЮKassa).\n\n"
    "Мы дали ещё *1 день* доступа и сможем повторить попытку позже (не чаще, чем раз в сутки по правилам сервиса).\n\n"
    "Если и повторная попытка не удастся, расширенные функции Premium отключатся — можно продлить вручную."
)
AUTOPAY_RETRY_FAIL_TEXT = (
    "К сожалению, повторная попытка автосписания за Guard тоже не удалась 💛\n\n"
    "Чтобы не потерять Premium-защиту,\n"
    "продлите подписку вручную — по кнопке ниже."
)


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

# Тексты напоминаний (ТЗ)
REMINDER_12H_TEXT = (
    "😈 AntiSpam Guard напоминает.\n\n"
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
    "😈 *AntiSpam Guard*\n\n"
    "Подключи чат отчётов, чтобы не пропускать важное:\n"
    "• 🧹 удаления сообщений\n"
    "• 🔇 муты\n"
    "• ⛔ баны\n"
    "• ✅ кнопки размута\n\n"
    "Так в одном месте видно, кого и за что остановил Guard."
)

# Guard сообщения в группе раз в 3 дня (ТЗ, случайный выбор)
GUARDIAN_PERIODIC_TEXTS = [
    "😈 AntiSpam Guard на месте.\nПока всё спокойно.\nСпамеров не обнаружено.\nНо если появятся — разберусь.",
    "🛡 AntiSpam Guard проверил чат.\nСпам не обнаружен.\nМожно продолжать общаться спокойно.",
    "😈 Я здесь.\nСлежу за ссылками,\nботами\nи подозрительными сообщениями.\nЕсли кто-то решит спамить — долго не проживёт.",
    "🛡 Guard проверяет чат.\nЕсли заметите странные ссылки — можете не переживать.\nЯ их тоже вижу.",
    "😈 AntiSpam Guard на дежурстве.\nПорядок в чате поддерживается автоматически.",
]


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


def _expired_warning_text_for(display_name: str | None = None) -> str:
    name = (display_name or "").strip()
    if not name:
        return EXPIRED_WARNING_TEXT
    return (
        "Эх 🥹\n\n"
        f"🔔 Здравствуйте, {name}!\n"
        "Сообщаем, что срок действия вашей подписки Guard истёк.\n\n"
        "Чтобы снова получить полный доступ ко всем инструментам защиты,\n"
        "пожалуйста, продлите подписку в приложении по кнопке ниже 😇"
    )


def _guard_payment_sub_expired_text_for(display_name: str | None = None) -> str:
    name = (display_name or "").strip()
    if not name:
        return GUARD_PAYMENT_SUB_EXPIRED_TEXT
    return GUARD_PAYMENT_SUB_EXPIRED_TEXT.replace(
        "🛡 *Guard: оплаченный период Premium закончился*\n\n",
        f"🛡 *Guard: оплаченный период Premium закончился*\n\nЗдравствуйте, {name}.\n\n",
        1,
    )


async def send_expired_guard_payment(bot, user_id: int) -> None:
    """Окончание оплаченного Premium — в том же Guard-голосе, что предпросмотр trial, без «не прошло списание»."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.types import FSInputFile
    from aiogram.exceptions import TelegramBadRequest

    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Продлить Premium", url=billing_link)]]
    )
    text = _guard_payment_sub_expired_text_for(None)
    try:
        chat = await bot.get_chat(user_id)
        text = _guard_payment_sub_expired_text_for(getattr(chat, "first_name", None))
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
    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Продлить защиту", url=billing_link),
    ]])
    text = EXPIRED_WARNING_TEXT
    try:
        chat = await bot.get_chat(user_id)
        text = _expired_warning_text_for(getattr(chat, "first_name", None))
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


async def send_expired_warning_preview(bot, chat_id: int, *, display_name: str | None = None) -> None:
    """Предпросмотр сообщения об истечении подписки в любом чате."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.types import FSInputFile
    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Продлить защиту", url=billing_link)]])
    text = _expired_warning_text_for(display_name)
    photo = FSInputFile(str(EXPIRED_WARNING_PHOTO_PATH)) if EXPIRED_WARNING_PHOTO_PATH.exists() else None
    if photo is not None:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)


async def send_trial_warning_preview_guard(bot, chat_id: int, *, display_name: str | None = None) -> None:
    """Предпросмотр guard-версии сообщения об истечении подписки с ссылкой на практику."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.types import FSInputFile
    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Продлить подписку", url=billing_link)]])
    name = (display_name or "").strip()
    text = TRIAL_PREVIEW_GUARD_TEXT if not name else TRIAL_PREVIEW_GUARD_TEXT.replace("⚠ *Guard: подписка завершилась*", f"⚠ *Guard: подписка завершилась*\n\nЗдравствуйте, {name}.")
    photo = FSInputFile(str(TRIAL_PREVIEW_GUARD_PHOTO_PATH)) if TRIAL_PREVIEW_GUARD_PHOTO_PATH.exists() else None
    if photo is not None:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)


async def _run_reminders_no_group(bot, session: AsyncSession, now: datetime, tpl: dict[str, AdminMessageTemplate]) -> None:
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

            d12 = _tpl_delay(tpl, "reminder_12h", REMINDER_12H)
            d24 = _tpl_delay(tpl, "reminder_24h", REMINDER_24H)
            d3d = _tpl_delay(tpl, "reminder_3d", REMINDER_3D)

            if stage == 0 and elapsed >= d12:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = _tpl_text(tpl, "reminder_12h", REMINDER_12H_TEXT)
                button_text = "➕ Подключить группу"
                user.reminder_stage = 1
            elif stage == 1 and elapsed >= d24:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = _tpl_text(tpl, "reminder_24h", REMINDER_24H_TEXT)
                button_text = "🛡 Подключить группу"
                user.reminder_stage = 2
            elif stage == 2 and elapsed >= d3d:
                count = await count_protected_chats(session, user.telegram_id)
                if count > 0:
                    user.reminder_stage = 4
                    await session.commit()
                    continue
                text = _tpl_text(tpl, "reminder_3d", REMINDER_3D_TEXT)
                button_text = "➕ Подключить группу"
                user.reminder_stage = 4
            else:
                continue

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            connect_link = await _startapp_link_for_bot(bot, "connect")
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=button_text, url=connect_link),
            ]])
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


async def _run_reminders_reports_chat(bot, session: AsyncSession, now: datetime, tpl: dict[str, AdminMessageTemplate]) -> None:
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
            me = await bot.get_me()
            reports_link = _startapp_link(str(me.username or ""), "reports")
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📊 Подключить чат отчётов", url=reports_link),
            ]])
            await bot.send_message(
                user.telegram_id,
                _tpl_text(tpl, "reports_reminder", REPORTS_REMINDER_TEXT),
                parse_mode="Markdown",
                reply_markup=kb,
            )
            user.reports_reminder_sent_at = now
            await session.commit()
        except Exception as e:
            logger.warning("reminder reports user=%s: %s", getattr(user, "telegram_id"), e)
            await session.rollback()


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
        ).join(Rule, Chat.id == Rule.chat_id).where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            # Каналы (рассылка / Mini App) — не группы: туда нельзя слать «проверил чат» (лезет в ленту канала).
            or_(Chat.chat_kind.is_(None), Chat.chat_kind != "channel"),
        )
    )
    for row in res.all():
        chat_id, last_activity, rule_chat_id, guardian_enabled, periodic_enabled, periodic_hours, last_sent = row
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
            guard_msg = random.choice(GUARDIAN_PERIODIC_TEXTS)
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
                            await bot.send_message(int(new_cid), random.choice(GUARDIAN_PERIODIC_TEXTS))
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
                "📊 *Автоотчёт Guard*\n\n"
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
    lvl_lines = []
    for row in lvl_q.all():
        lvl_lines.append(f"• L{int(row.level or 0)}: оплат {int(row.payments_count or 0)} / продажи {round(float(row.sales_sum or 0.0), 2):.2f} ₽")
    if not lvl_lines:
        lvl_lines.append("• Нет оплат по реферальным уровням")

    pay_count, pay_sum = pays_q.one_or_none() or (0, 0.0)
    text_head = _tpl_text(tpl, "owner_daily_report", "📊 Ежесуточная сводка Guard")
    msg = (
        f"{text_head}\n\n"
        f"За {window_h} ч.:\n"
        f"• Вступлений в группы: {int(joins_q.scalar() or 0)}\n"
        f"• Нажали /start: {int(starts_q.scalar() or 0)}\n"
        f"• Оплат: {int(pay_count or 0)} на {round(float(pay_sum or 0.0), 2):.2f} ₽\n"
        f"• Шеров рефералки: {int(shares_q.scalar() or 0)}\n\n"
        f"Реферальные уровни ({window_h}ч):\n" + "\n".join(lvl_lines)
    )

    ids = await _owner_admin_target_ids(session)
    if not ids:
        return

    for tid in sorted(ids):
        try:
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
            label = "день" if p == "day" else "3 дня" if p == "3d" else "неделю" if p == "week" else "месяц"
            msg = (
                "📈 Короткий отчёт Guard\n\n"
                f"За {label} в ваши группы подключились: *{joins}* чел.\n"
                f"Активных ваших групп: *{active_groups}*"
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
    events = {
        "window_group_joins": "Вступления в группы",
        "window_starts": "Нажали /start",
        "window_payments": "Оплаты",
        "window_referral_shares": "Шеры рефералки",
    }
    targets = await _owner_admin_target_ids(session)
    if not targets:
        return
    for t in tpl.values():
        event_key = str(getattr(t, "event_key", "") or "manual")
        if event_key not in events:
            continue
        if not bool(getattr(t, "enabled", True)):
            continue
        hours = max(1, min(168, int(getattr(t, "trigger_hours", 24) or 24)))
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

        if count < max(1, int(getattr(t, "min_count", 1) or 1)):
            continue
        ctx = {
            "count": str(count),
            "hours": str(hours),
            "payments_sum": f"{round(amount, 2):.2f}",
            "event_label": events[event_key],
            "date": now.date().isoformat(),
        }
        default_text = (
            f"🔔 {events[event_key]}\n\n"
            f"За {{hours}} ч: {{count}}\n"
            + ("Сумма оплат: {{payments_sum}} ₽\n" if event_key == "window_payments" else "")
            + "Дата: {{date}}"
        )
        text_msg = _render_template_text(str(getattr(t, "body_text", "") or default_text), ctx)
        bucket = f"{event_key}:{now.date().isoformat()}:{hours}:c{count}"
        for tid in targets:
            try:
                if not await _template_can_send_now(session, t, int(tid), now, bucket=bucket):
                    continue
                await bot.send_message(int(tid), text_msg, parse_mode=str(getattr(t, "parse_mode", "") or "Markdown"))
                await _mark_template_sent(session, t, int(tid), bucket=bucket)
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
                    InlineKeyboardButton(text="💳 Тариф и оплата", url=billing_link),
                ]])
                await bot.send_message(uid, PROMO_ENDED_TEXT, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
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
            await send_trial_warning_preview_guard(
                bot,
                tid,
                display_name=first_name,
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
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🛡 Открыть Guard Premium", url=billing_link)]]
    )
    for u in users:
        try:
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
            msg = GUARD_25_DAYS_TEXT.format(
                moderation_count=moderation_count,
                chats_count=chats_count,
                joins_count=joins_count,
                human_cost_rub=human_cost_rub,
                hours_saved=hours_saved,
            )
            await bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
            await _mark_dispatch_bucket(session, uid, bucket)
        except Exception as e:
            logger.warning("guard_25_days notify user=%s: %s", getattr(u, "telegram_id", None), e)
            await session.rollback()


async def _run_subscription_renewal_reminders(bot, session: AsyncSession, now: datetime) -> None:
    """Напоминания перед продлением: за 5 дней и за 1 час до окончания."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    billing_link = await _startapp_link_for_bot(bot, "billing")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Тариф и оплата", url=billing_link)]]
    )
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
                        SUB_END_5D_TEXT.format(
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
                        body = SUB_END_1H_TEXT_AUTORENEW.format(
                            charge_window_hours=autorenew_window_hours(),
                        )
                    else:
                        body = SUB_END_1H_TEXT_MANUAL
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
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Перейти к тарифам", url=billing_link)]]
    )
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
                await bot.send_message(uid, AUTOPAY_FAIL_TEXT, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
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
                await bot.send_message(uid, AUTOPAY_RETRY_FAIL_TEXT, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
            elif now >= sub_until:
                logger.info("autorenew_retries skip user=%s reason=duplicate_bucket bucket=%s", uid, retry_bucket)
        except Exception as e:
            logger.warning("autorenew_retries user=%s: %s", getattr(u, "telegram_id", None), e)
            await session.rollback()


async def run_reminders_and_guardian(bot) -> None:
    """Запуск всех проверок: напоминания, Guard раз в 3 дня, автоотчёты раз в сутки."""
    now = datetime.now(timezone.utc)
    async with await get_session() as session:
        tpl = await _load_message_templates(session)
        await _run_reminders_no_group(bot, session, now, tpl)
    async with await get_session() as session:
        tpl = await _load_message_templates(session)
        await _run_reminders_reports_chat(bot, session, now, tpl)
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
