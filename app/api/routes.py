# app/api/routes.py
"""REST-маршруты для Mini App."""

from __future__ import annotations

import json
import logging
import os
import io
import secrets
import asyncio
import smtplib
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from time import perf_counter

import aiohttp
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, BufferedInputFile
from typing import Any

from sqlalchemy import select, func, delete, text, case, or_, literal_column
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image, ImageOps, UnidentifiedImageError

from app.api.auth import require_init_data, require_init_data_with_profile
from app.api.deps import get_db
from app.api.service import (
    get_activity_summary_chat_ids,
    get_accessible_chats_any_active,
    get_managed_chats,
    get_pending_chats,
    get_or_create_rule,
    get_selected_chat_id,
    set_selected_chat,
    user_can_access_chat,
    count_stopwords,
    list_stopwords,
    add_stopword,
    delete_stopword,
    copy_rule_to_chat,
    apply_promo_code,
)
from app.db.models import (
    AdminBroadcast,
    AdminBroadcastMedia,
    AdminBroadcastDelivery,
    AdminBroadcastRun,
    AdminBroadcastClick,
    AutopostCampaign,
    Channel,
    Chat,
    Rule,
    User,
    Payment,
    CreditLedger,
    PartnerPayoutRequest,
    PartnerCommission,
    GlobalAntispamUser,
    GlobalBadUrlPattern,
    UserGlobalBadUrlPattern,
    ModerationLog,
    NewMember,
    MemberLeft,
    ChatActivityEvent,
    ReferralShareHit,
    AdminMessageTemplate,
    ChatManager,
    ChatManagerInvite,
    UserContext,
    PromoCode,
    PromoCodeRedemption,
    OwnerJoinReportSetting,
    AppSetting,
    ChatSpikeAlert,
    WhitelistDomain,
    WhitelistUser,
    WhitelistSenderChat,
    LinkBlacklist,
)
from app.db.pii_session import PiiAsyncSessionLocal
from app.services.user_service import (
    get_or_create_user,
    can_add_chat,
    can_add_channel,
    count_managed_chats_by_kind,
    effective_group_limit,
    effective_channel_limit,
    TARIFF_CHAT_LIMITS,
    Tariff,
)
from app.services.pii_user_store import (
    pii_find_telegram_id_by_username_lower,
    pii_storage_enabled,
    resolve_username_lookup,
)
from app.services.telegram_notify import send_user_dm, send_user_dm_with_result, delete_user_dm_message
from app.services.telegram_bot_api import (
    tg_save_prepared_add_group_button,
    tg_unban_chat_member,
    tg_restrict_chat_member_unmute,
    tg_get_chat_member,
    tg_get_chat,
    tg_send_message,
    tg_pin_chat_message,
    tg_delete_message,
    tg_try_delete_pin_service_messages,
)
from app.services.telegram_notify import send_user_dm
from app.services.global_antispam import remove_from_global_antispam
from app.services.spam_spike_notify import SPAM_MODERATION_REASONS
from app.services.chat_cleanup import clean_deleted_accounts
from app.services.credit_policy import REFERRAL_LEVEL_RATES, PARTNER_TOKEN_RUB_RATE
from app.services.admin_roles import is_full_admin_user as _is_full_admin_user
from app.services.chat_limit_enforcer import enforce_owner_active_chat_limit
from app.texts.guardian_billing import format_subscription_until_ru

router = APIRouter(prefix="/api", tags=["webapp"])
_log = logging.getLogger(__name__)
# Личная «глобальная» база URL в кабинете (Premium / полный админ для своего tg id).
USER_GLOBAL_BAD_URL_MAX = 50
REPUTATION_CUSTOM_WORDS_MAX = 40
REPUTATION_TOP_LIMIT = 20
REPUTATION_DEFAULT_WORDS = (
    "спасибо", "thank", "thanks", "tnx", "благодарю", "благодарствую", "++", "+1", "👍", "🤝", "рахмет",
)


def _humanize_yookassa_error(err: Exception) -> str:
    msg = str(err or "").strip()
    low = msg.lower()
    if "can't make recurring payments" in low or "recurring payments" in low:
        return "Для LIVE-магазина пока не включены рекуррентные платежи в ЮKassa. Оплата проведена как обычная, а автосписание станет доступно после активации recurring."
    return msg or "Ошибка платёжной системы"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "y", "on"}


def _normalize_reputation_word(value: str) -> str:
    w = str(value or "").strip().lower().replace("ё", "е")
    return w[:64]


async def _get_app_bool_setting(session: AsyncSession, key: str, default: bool = False) -> bool:
    row = await session.get(AppSetting, str(key))
    if not row:
        return bool(default)
    raw = str(getattr(row, "value", "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "y", "on"}


async def _set_app_bool_setting(session: AsyncSession, key: str, value: bool) -> None:
    row = await session.get(AppSetting, str(key))
    val = "1" if bool(value) else "0"
    if not row:
        row = AppSetting(key=str(key), value=val)
    else:
        row.value = val
    session.add(row)
    await session.commit()


def _norm_username(raw: str | None) -> str:
    s = str(raw or "").strip()
    if s.startswith("@"):
        s = s[1:]
    return s.lower()


async def _touch_user_presence(session: AsyncSession, user_id: int) -> None:
    u = (await session.execute(select(User).where(User.telegram_id == int(user_id)).limit(1))).scalar_one_or_none()
    if not u:
        return
    u.last_webapp_seen_at = datetime.now(timezone.utc)
    uid = int(getattr(u, "telegram_id", 0) or 0)
    uname = _norm_username(getattr(u, "username", None))
    invite_filters = [ChatManagerInvite.target_telegram_id == uid]
    if uname:
        invite_filters.append(
            ChatManagerInvite.target_telegram_id.is_(None)
            & (func.lower(ChatManagerInvite.target_username) == uname)
        )
    invites = (
        await session.execute(
            select(ChatManagerInvite).where(or_(*invite_filters))
        )
    ).scalars().all()
    for inv in invites:
        exists = (
            await session.execute(
                select(ChatManager).where(
                    ChatManager.chat_id == int(inv.chat_id),
                    ChatManager.user_id == uid,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if not exists:
            session.add(
                ChatManager(
                    chat_id=int(inv.chat_id),
                    user_id=uid,
                    added_by=int(getattr(inv, "owner_user_id", 0) or 0),
                )
            )
        inv.target_telegram_id = uid
        if uname:
            inv.target_username = uname
        inv.connected_user_id = uid
        inv.status = "connected"
    if invites:
        await session.execute(
            delete(ChatManagerInvite).where(
                ChatManagerInvite.target_telegram_id == uid,
                ChatManagerInvite.status.in_(("sent", "connecting")),
                ChatManagerInvite.connected_user_id.is_(None),
            )
        )
    await session.commit()


async def _chat_managers_payload(session: AsyncSession, chat_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(ChatManager).where(ChatManager.chat_id == int(chat_id)).order_by(ChatManager.created_at.asc())
        )
    ).scalars().all()
    if not rows:
        return []
    tg_ids = {int(getattr(r, "user_id", 0) or 0) for r in rows if int(getattr(r, "user_id", 0) or 0) > 0}
    users_map: dict[int, User] = {}
    if tg_ids:
        urows = (
            await session.execute(select(User).where(User.telegram_id.in_(list(tg_ids))))
        ).scalars().all()
        users_map = {int(u.telegram_id): u for u in urows}
    out: list[dict] = []
    for r in rows:
        uid = int(getattr(r, "user_id", 0) or 0)
        u = users_map.get(uid)
        seen = getattr(u, "last_webapp_seen_at", None) if u else None
        is_online = bool(seen and (datetime.now(timezone.utc) - seen) <= timedelta(seconds=90))
        out.append(
            {
                "user_id": uid,
                "username": str(getattr(u, "username", "") or ""),
                "first_name": str(getattr(u, "first_name", "") or ""),
                "is_online": is_online,
                "last_seen_at": _format_dt(seen),
                "added_by": int(getattr(r, "added_by", 0) or 0),
                "created_at": _format_dt(getattr(r, "created_at", None)),
                "permissions": {
                    "protection": bool(getattr(r, "can_protection", False)),
                    "broadcast": bool(getattr(r, "can_broadcast", False)),
                    "reports": bool(getattr(r, "can_reports", False)),
                    "first_post_settings": bool(getattr(r, "can_first_post_settings", False)),
                },
            }
        )
    return out


async def _chat_manager_invites_payload(session: AsyncSession, chat_id: int, owner_user_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(ChatManagerInvite)
            .where(ChatManagerInvite.chat_id == int(chat_id), ChatManagerInvite.owner_user_id == int(owner_user_id))
            .order_by(ChatManagerInvite.created_at.desc())
        )
    ).scalars().all()
    out: list[dict] = []
    for r in rows:
        status = str(getattr(r, "status", "sent") or "sent").lower()
        if status == "sent" and int(getattr(r, "target_telegram_id", 0) or 0) > 0:
            status = "connecting"
        out.append(
            {
                "id": int(getattr(r, "id", 0) or 0),
                "target_telegram_id": int(getattr(r, "target_telegram_id", 0) or 0) or None,
                "target_username": str(getattr(r, "target_username", "") or ""),
                "connected_user_id": int(getattr(r, "connected_user_id", 0) or 0) or None,
                "status": status,
                "created_at": _format_dt(getattr(r, "created_at", None)),
                "updated_at": _format_dt(getattr(r, "updated_at", None)),
                "permissions": {
                    "protection": bool(getattr(r, "can_protection", False)),
                    "broadcast": bool(getattr(r, "can_broadcast", False)),
                    "reports": bool(getattr(r, "can_reports", False)),
                    "first_post_settings": bool(getattr(r, "can_first_post_settings", False)),
                },
            }
        )
    return out




def _admin_template_public(t: AdminMessageTemplate) -> dict:
    return {
        "id": int(t.id),
        "template_key": str(getattr(t, "template_key", "") or ""),
        "title": str(getattr(t, "title", "") or ""),
        "body_text": str(getattr(t, "body_text", "") or ""),
        "enabled": bool(getattr(t, "enabled", True)),
        "delay_minutes": int(t.delay_minutes) if getattr(t, "delay_minutes", None) is not None else None,
        "parse_mode": str(getattr(t, "parse_mode", "") or ""),
        "is_custom": bool(getattr(t, "is_custom", False)),
        "event_key": str(getattr(t, "event_key", "") or "manual"),
        "target_kind": str(getattr(t, "target_kind", "") or "owner_admin"),
        "trigger_hours": int(getattr(t, "trigger_hours", 24) or 24),
        "min_count": int(getattr(t, "min_count", 1) or 1),
        "cooldown_minutes": int(getattr(t, "cooldown_minutes", 1440) or 1440),
        "schedule_time_hm": str(getattr(t, "schedule_time_hm", "") or ""),
        "created_at": _format_dt(getattr(t, "created_at", None)),
        "updated_at": _format_dt(getattr(t, "updated_at", None)),
    }


def _safe_template_key(title: str, fallback: str = "custom_message") -> str:
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in (title or "").strip())[:40].strip("_")
    return base or fallback


def _test_tariff_payment_telegram_ids() -> set[int]:
    """
    Telegram user_id (положительные), для которых в Mini App показывается блок «тестовая оплата» тарифов.

    Переменные (достаточно одной): TEST_TARIFF_PAYMENT_TELEGRAM_IDS, TEST_TARIFF_PAYMENT_TELEGRAM_ID,
    OWNER_TEST_PAYMENT_TG_ID. Формат: одно число или несколько через запятую/перенос строки; допускаются кавычки.
    """
    chunks: list[str] = []
    for key in (
        "TEST_TARIFF_PAYMENT_TELEGRAM_IDS",
        "TEST_TARIFF_PAYMENT_TELEGRAM_ID",
        "OWNER_TEST_PAYMENT_TG_ID",
    ):
        v = (os.getenv(key) or "").strip()
        if v:
            chunks.append(v)
    raw = ",".join(chunks).replace("\n", ",").replace(";", ",")
    out: set[int] = set()
    for part in raw.split(","):
        part = (part or "").strip().strip('"').strip("'").strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out
_PARTNER_PAYOUT_MIN_RUB = 1500.0
_PARTNER_PAYOUT_RATE = 0.15
# Fallback для uptime, если роутер вызывают без lifespan (тесты). В проде используется request.app.state.api_boot_at.
_API_BOOT_TS = datetime.now(timezone.utc)
_DELIVERY_SCHEMA_CACHE: dict[str, Any] = {"ts": 0.0, "cols": set()}
_DELIVERY_SCHEMA_TTL_SEC = 60.0

# Кэш username бота для ссылки «Добавить в группу»
_bot_username: str | None = None


async def _get_bot_username() -> str | None:
    """Имя для t.me/… Сначала getMe по BOT_TOKEN API (совпадает с ботом Mini App). ENV только если getMe не вернул username."""
    global _bot_username
    if _bot_username:
        return _bot_username
    token = os.getenv("BOT_TOKEN")
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.telegram.org/bot{token}/getMe") as resp:
                data = await resp.json()
                if data.get("ok") and data.get("result"):
                    u = (data["result"].get("username") or "").strip()
                    if u:
                        _bot_username = u
                        return u
    except Exception:
        pass
    forced = (os.getenv("BOT_USERNAME") or os.getenv("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    return forced or None


def _format_dt(dt):
    if dt is None:
        return None
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(dt)


def _partner_webapp_url() -> str | None:
    base = (os.getenv("MINI_APP_URL") or os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/?section=partner"


async def _delegated_chats_webapp_url() -> str | None:
    # Приоритет: deep link в Telegram Mini App (не браузер).
    uname = await _get_bot_username()
    short_name = (os.getenv("MINI_APP_SHORT_NAME") or os.getenv("WEBAPP_SHORT_NAME") or "").strip().strip("/")
    if uname and short_name:
        return f"https://t.me/{uname}/{short_name}?startapp=chats_delegated"
    if uname:
        return f"https://t.me/{uname}?startapp=chats_delegated"
    # Фолбэк (если не удалось определить username бота).
    base = (os.getenv("MINI_APP_URL") or os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/chats?cabinet=delegated"


def _mini_app_admin_broadcast_url() -> str | None:
    base = (os.getenv("MINI_APP_URL") or os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    if not base:
        return None
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return f"{base}/admin?tab=broadcasts"


def _user_dm_link(username: str | None, telegram_id: int | None) -> str | None:
    u = (username or "").strip().lstrip("@")
    if u:
        return f"https://t.me/{u}"
    tg_id = int(telegram_id or 0)
    if tg_id > 0:
        return f"https://t.me/user?id={tg_id}"
    return None


def _chat_open_link(chat_id: int | None, username: str | None) -> str | None:
    u = (username or "").strip().lstrip("@")
    if u:
        return f"https://t.me/{u}"
    cid = int(chat_id or 0)
    if cid == 0:
        return None
    if str(cid).startswith("-100"):
        suffix = str(cid)[4:]
        if suffix:
            return f"https://t.me/c/{suffix}"
    if cid < 0:
        return f"https://t.me/c/{abs(cid)}"
    return f"https://t.me/{cid}"


def _spike_recommendations(rule: Rule | None) -> list[str]:
    if not rule:
        return [
            "Включите режим новичков.",
            "Включите режим тишины после входа.",
            "Проверьте наказание: delete/mute/ban.",
        ]
    rec: list[str] = []
    if not bool(getattr(rule, "newbie_enabled", False)):
        rec.append("Включите режим новичков (усиление первых сообщений).")
    if int(getattr(rule, "silence_minutes", 0) or 0) <= 0:
        rec.append("Задайте режим тишины после вступления.")
    if not bool(getattr(rule, "first_message_captcha_enabled", False)):
        rec.append("Включите капчу на первое сообщение.")
    if not bool(getattr(rule, "antinakrutka_enabled", False)):
        rec.append("Включите антинакрутку на массовые входы.")
    if not rec:
        rec.append("Проверьте пороги стоп-слов, ссылок и медиа-фильтра.")
    return rec[:4]


def _is_user_premium_now(user, now: datetime) -> bool:
    """Premium активен, если есть неистекшая дата или бессрочный premium без даты."""
    tariff = (getattr(user, "tariff", None) or "free").lower()
    sub_until = getattr(user, "subscription_until", None)
    if sub_until:
        return sub_until > now
    return tariff in ("premium", "pro", "business")


async def _subscription_activated_at_resolved(session: AsyncSession, user: User) -> datetime | None:
    """
    Дата первой оплаты подписки (tariff=premium), не сдвигается при продлении/докупе.
    Колонка users.subscription_activated_at; иначе MIN(created_at) по успешным payments.
    """
    raw = getattr(user, "subscription_activated_at", None)
    if raw is not None:
        if getattr(raw, "tzinfo", None) is None:
            raw = raw.replace(tzinfo=timezone.utc)
        return raw
    uid = int(getattr(user, "id", 0) or 0)
    if not uid:
        return None
    r = await session.execute(
        select(func.min(Payment.created_at)).where(
            Payment.user_id == uid,
            Payment.status == "succeeded",
            Payment.tariff == Tariff.PREMIUM.value,
        )
    )
    return r.scalar_one_or_none()


async def _user_subscription_panel_dict(session: AsyncSession, user: User) -> dict[str, object]:
    """
    Поля для экрана «Моя подписка» (Mini App / админ-просмотр): даты, тариф последней оплаты, способ оплаты.
    """
    now = datetime.now(timezone.utc)
    is_premium = _is_user_premium_now(user, now)
    paid_months: int | None = None
    paid_days: int | None = None
    if user.id:
        pr = await session.execute(
            select(Payment.months, Payment.tariff)
            .where(
                Payment.user_id == user.id,
                Payment.status == "succeeded",
                Payment.tariff.in_((Tariff.PREMIUM.value, "premium_probe")),
            )
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        row = pr.one_or_none()
        if row:
            mv_raw, tv_raw = row[0], row[1]
            mv = int(mv_raw or 0)
            tv = str(tv_raw or "")
            if tv == Tariff.PREMIUM.value and mv > 0:
                paid_months = mv
            elif tv == "premium_probe" and mv > 0:
                paid_days = mv
    period_start_at = await _subscription_activated_at_resolved(session, user)
    return {
        "is_premium": is_premium,
        "subscription_until": _format_dt(getattr(user, "subscription_until", None)),
        "subscription_source": str(getattr(user, "subscription_source", "") or ""),
        "payment_method_bound": bool(getattr(user, "payment_method_bound", False)),
        "payment_method_type": str(getattr(user, "payment_method_type", "") or ""),
        "payment_method_last4": str(getattr(user, "payment_method_last4", "") or ""),
        "subscription_paid_period_months": paid_months,
        "subscription_paid_period_days": paid_days,
        "subscription_activated_at": _format_dt(period_start_at),
        "subscription_current_period_start_at": _format_dt(period_start_at),
    }


def _parse_query_datetime(val: str | None) -> datetime | None:
    """Парсинг ISO-даты из query (в т.ч. из JS Date.toISOString())."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _user_manages_foreign_owned_chat(session: AsyncSession, telegram_id: int) -> bool:
    """Менеджер в чате, владелец которого — другой Telegram id (делегированный доступ)."""
    tid = int(telegram_id)
    chats = await get_managed_chats(session, tid)
    for c in chats:
        if int(getattr(c, "owner_user_id", 0) or 0) != tid:
            return True
    return False


async def _require_admin_user(session: AsyncSession, user_id: int) -> User:
    user = await get_or_create_user(session, user_id)
    if not _is_full_admin_user(user, int(user_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access denied")
    return user


async def _require_premium_or_full_admin_personal_global(session: AsyncSession, user_id: int) -> User:
    """Личная база URL в кабинете: активный Premium или полный админ (свой список по telegram id)."""
    user = await get_or_create_user(session, user_id)
    if _is_full_admin_user(user, int(user_id)):
        return user
    if _is_user_premium_now(user, datetime.now(timezone.utc)):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Нужен Premium или полный доступ администратора",
    )


async def _require_broadcast_access(session: AsyncSession, user_id: int) -> tuple[User, bool]:
    """
    Доступ к рассылке: полные админы, активный Premium или менеджер чужого чата (делегирование).
    Возвращает (user, is_full_admin).
    """
    user = await get_or_create_user(session, user_id)
    if _is_full_admin_user(user, int(user_id)):
        return user, True
    now = datetime.now(timezone.utc)
    if _is_user_premium_now(user, now):
        return user, False
    if await _user_manages_foreign_owned_chat(session, int(user_id)):
        return user, False
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Нужен Premium, полный доступ администратора или менеджерство в чужом чате",
    )


def _broadcast_viewer_can_scope_all(user: User) -> bool:
    """Можно ли запрашивать scope=all для списка групп рассылки (все активные группы на этом боте)."""
    tid = int(getattr(user, "telegram_id", 0) or 0)
    return _is_full_admin_user(user, tid)


def _is_suspicious_payout(amount_rub: float, requisites: str) -> tuple[bool, str]:
    if amount_rub >= 30000:
        return True, "Большая сумма для ручной проверки"
    req = (requisites or "").strip().lower()
    digits = "".join(ch for ch in req if ch.isdigit())
    if len(digits) < 10:
        return True, "Неполные реквизиты"
    return False, ""


async def _partner_payout_duplicate_requisites(
    session: AsyncSession, user_internal_id: int, requisites: str
) -> tuple[bool, str]:
    """Те же реквизиты у другого user_id — сигнал мультиаккаунтов / общий кошелёк."""
    req = (requisites or "").strip()
    if len(req) < 6:
        return False, ""
    dup_q = await session.execute(
        select(func.count())
        .select_from(PartnerPayoutRequest)
        .where(
            PartnerPayoutRequest.user_id != int(user_internal_id),
            PartnerPayoutRequest.requisites == req,
            PartnerPayoutRequest.status.in_(("new", "approved", "paid", "frozen")),
        )
    )
    if int(dup_q.scalar() or 0) > 0:
        return True, "Реквизиты уже использовались другим аккаунтом"
    return False, ""


async def _partner_financials(session: AsyncSession, user: User) -> dict:
    now_utc = datetime.now(timezone.utc)
    is_owner_fast = str(getattr(user, "username", "") or "").lower() == "pastukh_viscera"
    try:
        if not is_owner_fast:
            # Продвигаем pending -> available, если прошел hold.
            await session.execute(
                text(
                    "UPDATE partner_commissions SET status='available' "
                    "WHERE owner_user_id=:uid AND status='pending' AND available_at IS NOT NULL AND available_at <= :now"
                ),
                {"uid": int(user.id), "now": now_utc},
            )
            await session.commit()
        else:
            await session.execute(
                text("UPDATE partner_commissions SET status='available' WHERE owner_user_id=:uid AND status='pending'"),
                {"uid": int(user.id)},
            )
            await session.commit()

        total_sales_q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.sales_amount_rub), 0.0)).where(
                PartnerCommission.owner_user_id == int(user.id),
                PartnerCommission.status.in_(("pending", "available", "paid")),
            )
        )
        total_sales_rub = float(total_sales_q.scalar() or 0.0)
        commission_total_q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0)).where(
                PartnerCommission.owner_user_id == int(user.id),
                PartnerCommission.status.in_(("pending", "available", "paid")),
            )
        )
        commission_total_rub = round(float(commission_total_q.scalar() or 0.0), 2)
        pending_q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0)).where(
                PartnerCommission.owner_user_id == int(user.id),
                PartnerCommission.status == "pending",
            )
        )
        pending_rub = round(float(pending_q.scalar() or 0.0), 2)
        available_commission_q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0)).where(
                PartnerCommission.owner_user_id == int(user.id),
                PartnerCommission.status == "available",
            )
        )
        available_commission_rub = float(available_commission_q.scalar() or 0.0)
    except Exception:
        # Фолбэк для старых окружений до миграции таблицы partner_commissions.
        total_sales_rub = float(getattr(user, "ref_sales_total", 0.0) or 0.0)
        token_balance = float(getattr(user, "bonus_credits", 0.0) or 0.0)
        commission_total_rub = round(token_balance * PARTNER_TOKEN_RUB_RATE, 2)
        pending_rub = 0.0
        available_commission_rub = commission_total_rub
    sum_reserved_q = await session.execute(
        select(func.coalesce(func.sum(PartnerPayoutRequest.amount_rub), 0.0)).where(
            PartnerPayoutRequest.user_id == int(user.id),
            PartnerPayoutRequest.status.in_(("new", "approved", "frozen")),
        )
    )
    reserved_rub = float(sum_reserved_q.scalar() or 0.0)
    paid_total_q = await session.execute(
        select(func.coalesce(func.sum(PartnerPayoutRequest.amount_rub), 0.0)).where(
            PartnerPayoutRequest.user_id == int(user.id),
            PartnerPayoutRequest.status == "paid",
        )
    )
    paid_total_rub = float(paid_total_q.scalar() or 0.0)
    token_balance = float(getattr(user, "bonus_credits", 0.0) or 0.0)
    token_balance_rub = round(token_balance * PARTNER_TOKEN_RUB_RATE, 2)
    # Доступно к выводу: баланс минус активные заявки и минус комиссии в холде (pending).
    # Иначе токены уже на счёте с момента оплаты, а вывод был бы возможен до понедельника.
    available_rub = round(max(0.0, token_balance_rub - reserved_rub - pending_rub), 2)
    # Всего комиссий (для UI): то, что сейчас на балансе + уже выплачено.
    commission_total_rub = round(token_balance_rub + paid_total_rub, 2)
    return {
        "total_sales_rub": round(total_sales_rub, 2),
        "commission_total_rub": commission_total_rub,
        "token_balance": round(token_balance, 2),
        "token_balance_rub": token_balance_rub,
        "token_rub_rate": PARTNER_TOKEN_RUB_RATE,
        "pending_rub": pending_rub,
        "reserved_rub": round(reserved_rub, 2),
        "paid_total_rub": round(paid_total_rub, 2),
        "available_rub": available_rub,
    }


def _next_monday_text(now: datetime | None = None) -> str:
    base = now or datetime.now(timezone.utc)
    days = (7 - base.weekday()) % 7
    if days == 0:
        days = 7
    d = base + timedelta(days=days)
    return d.strftime("%d.%m.%Y")


def _rule_to_dict(rule: Rule, stopwords_count: int = 0) -> dict:
    welcome_buttons: list = []
    rules_channel_buttons: list = []
    rules_group_buttons: list = []
    rules_channel_autopost_times: list[str] = []
    rules_group_autopost_times: list[str] = []
    try:
        raw_wb = getattr(rule, "welcome_buttons_json", None)
        if raw_wb:
            parsed = json.loads(str(raw_wb))
            if isinstance(parsed, list):
                welcome_buttons = parsed
    except Exception:
        welcome_buttons = []
    try:
        raw_rcb = getattr(rule, "rules_channel_buttons_json", None)
        if raw_rcb:
            parsed = json.loads(str(raw_rcb))
            if isinstance(parsed, list):
                rules_channel_buttons = parsed
    except Exception:
        rules_channel_buttons = []
    try:
        raw_rgb = getattr(rule, "rules_group_buttons_json", None)
        if raw_rgb:
            parsed = json.loads(str(raw_rgb))
            if isinstance(parsed, list):
                rules_group_buttons = parsed
    except Exception:
        rules_group_buttons = []
    try:
        raw_rct = getattr(rule, "rules_channel_autopost_times_json", None)
        if raw_rct:
            parsed = json.loads(str(raw_rct))
            if isinstance(parsed, list):
                rules_channel_autopost_times = [str(x) for x in parsed if str(x or "").strip()]
    except Exception:
        rules_channel_autopost_times = []
    try:
        raw_rgt = getattr(rule, "rules_group_autopost_times_json", None)
        if raw_rgt:
            parsed = json.loads(str(raw_rgt))
            if isinstance(parsed, list):
                rules_group_autopost_times = [str(x) for x in parsed if str(x or "").strip()]
    except Exception:
        rules_group_autopost_times = []
    return {
        "chat_id": rule.chat_id,
        "filter_links": getattr(rule, "filter_links", True),
        "filter_links_mode": getattr(rule, "filter_links_mode", "forbid"),
        "filter_links_scope": str(getattr(rule, "filter_links_scope", "all") or "all"),
        "filter_media_mode": getattr(rule, "filter_media_mode", "allow"),
        "filter_buttons_mode": getattr(rule, "filter_buttons_mode", "allow"),
        "filter_mentions": getattr(rule, "filter_mentions", False),
        "action_mode": getattr(rule, "action_mode", "delete"),
        "mute_minutes": int(rule.mute_minutes or 30),
        "newbie_enabled": bool(rule.newbie_enabled),
        "newbie_minutes": int(rule.newbie_minutes or 10),
        "first_message_captcha_enabled": bool(getattr(rule, "first_message_captcha_enabled", False)),
        "join_captcha_enabled": bool(getattr(rule, "join_captcha_enabled", False)),
        "join_captcha_ttl_minutes": int(getattr(rule, "join_captcha_ttl_minutes", 3) or 3),
        "join_captcha_kind": str(getattr(rule, "join_captcha_kind", "button") or "button"),
        "join_captcha_prefer_dm": bool(getattr(rule, "join_captcha_prefer_dm", False)),
        "welcome_enabled": bool(getattr(rule, "welcome_enabled", False)),
        "welcome_text": str(getattr(rule, "welcome_text", "") or ""),
        "welcome_buttons": welcome_buttons,
        "welcome_has_photo": bool(getattr(rule, "welcome_photo_path", None)),
        "welcome_max_per_min": int(getattr(rule, "welcome_max_per_min", 0) or 0),
        "welcome_silent_on_raid": bool(getattr(rule, "welcome_silent_on_raid", False)),
        "welcome_raid_threshold": int(getattr(rule, "welcome_raid_threshold", 8) or 8),
        "welcome_raid_window_minutes": int(getattr(rule, "welcome_raid_window_minutes", 2) or 2),
        "welcome_every_n_joins": int(getattr(rule, "welcome_every_n_joins", 1) or 1),
        "rules_channel_enabled": bool(getattr(rule, "rules_channel_enabled", False)),
        "rules_channel_text": str(getattr(rule, "rules_channel_text", "") or ""),
        "rules_channel_buttons": rules_channel_buttons,
        "rules_channel_has_photo": bool(getattr(rule, "rules_channel_photo_path", None)),
        "rules_channel_delete_window_sec": int(getattr(rule, "rules_channel_delete_window_sec", 0) or 0),
        "rules_channel_autopost_enabled": bool(getattr(rule, "rules_channel_autopost_enabled", False)),
        "rules_channel_autopost_times": rules_channel_autopost_times,
        "rules_group_enabled": bool(getattr(rule, "rules_group_enabled", False)),
        "rules_group_text": str(getattr(rule, "rules_group_text", "") or ""),
        "rules_group_buttons": rules_group_buttons,
        "rules_group_has_photo": bool(getattr(rule, "rules_group_photo_path", None)),
        "rules_group_autopost_enabled": bool(getattr(rule, "rules_group_autopost_enabled", False)),
        "rules_group_autopost_times": rules_group_autopost_times,
        "rules_group_pin_on_send": bool(getattr(rule, "rules_group_pin_on_send", True)),
        "rules_group_delete_pin_notice": bool(getattr(rule, "rules_group_delete_pin_notice", False)),
        "rules_group_event_on_trigger": bool(getattr(rule, "rules_group_event_on_trigger", False)),
        "rules_group_event_on_punish": bool(getattr(rule, "rules_group_event_on_punish", False)),
        "rules_group_event_trigger_every_n": int(getattr(rule, "rules_group_event_trigger_every_n", 1) or 1),
        "rules_group_event_punish_every_n": int(getattr(rule, "rules_group_event_punish_every_n", 1) or 1),
        "rules_group_active_draft_id": str(getattr(rule, "rules_group_active_draft_id", "") or ""),
        "all_captcha_minutes": int(getattr(rule, "all_captcha_minutes", 0) or 0),
        "delete_join_messages": bool(getattr(rule, "delete_join_messages", True)),
        "delete_left_messages": bool(getattr(rule, "delete_left_messages", True)),
        "silence_minutes": int(getattr(rule, "silence_minutes", 0) or 0),
        "master_anti_spam": bool(getattr(rule, "master_anti_spam", True)),
        "antinakrutka_enabled": bool(getattr(rule, "antinakrutka_enabled", False)),
        "antinakrutka_joins_threshold": int(getattr(rule, "antinakrutka_joins_threshold", 10) or 10),
        "antinakrutka_window_minutes": int(getattr(rule, "antinakrutka_window_minutes", 5) or 5),
        "antinakrutka_action": str(getattr(rule, "antinakrutka_action", "alert") or "alert"),
        "antinakrutka_restrict_minutes": int(getattr(rule, "antinakrutka_restrict_minutes", 30) or 30),
        "spam_spike_enabled": bool(getattr(rule, "spam_spike_enabled", True)),
        "spam_spike_min_deletes": int(getattr(rule, "spam_spike_min_deletes", 15) or 15),
        "spam_spike_window_minutes": int(getattr(rule, "spam_spike_window_minutes", 35) or 35),
        "spam_spike_notify_managers": bool(getattr(rule, "spam_spike_notify_managers", True)),
        "use_global_antispam_db": bool(getattr(rule, "use_global_antispam_db", False)),
        "use_global_bad_urls": bool(getattr(rule, "use_global_bad_urls", False)),
        "filter_channel_posts_enabled": bool(getattr(rule, "filter_channel_posts_enabled", False)),
        "filter_channel_posts_action": str(getattr(rule, "filter_channel_posts_action", "delete") or "delete"),
        "filter_profanity_enabled": bool(getattr(rule, "filter_profanity_enabled", True)),
        "filter_jobs_enabled": bool(getattr(rule, "filter_jobs_enabled", True)),
        "filter_casino_enabled": bool(getattr(rule, "filter_casino_enabled", True)),
        "filter_ads_enabled": bool(getattr(rule, "filter_ads_enabled", False)),
        "filter_insults_enabled": bool(getattr(rule, "filter_insults_enabled", False)),
        "filter_racism_enabled": bool(getattr(rule, "filter_racism_enabled", False)),
        "filter_nazi_enabled": bool(getattr(rule, "filter_nazi_enabled", False)),
        "filter_vulgar_enabled": bool(getattr(rule, "filter_vulgar_enabled", False)),
        "reputation_enabled": bool(getattr(rule, "reputation_enabled", False)),
        "log_enabled": bool(rule.log_enabled),
        "guardian_messages_enabled": bool(getattr(rule, "guardian_messages_enabled", True)),
        "guardian_periodic_enabled": bool(getattr(rule, "guardian_periodic_enabled", True)),
        "guardian_periodic_interval_hours": int(getattr(rule, "guardian_periodic_interval_hours", 24) or 24),
        "public_alerts_enabled": bool(getattr(rule, "public_alerts_enabled", False)),
        "public_alerts_every_n": int(getattr(rule, "public_alerts_every_n", 5)),
        "public_alerts_min_interval_sec": int(getattr(rule, "public_alerts_min_interval_sec", 300) or 300),
        "public_alerts_style": str(getattr(rule, "public_alerts_style", "guard") or "guard"),
        "auto_reports_enabled": bool(getattr(rule, "auto_reports_enabled", True)),
        "stopwords_count": stopwords_count,
    }


# ---------- GET /api/bot-info ----------
@router.get("/bot-info")
async def api_bot_info(
    user_id: int = Depends(require_init_data),
):
    """Username бота для ссылки «Добавить в группу» (t.me/username?startgroup)."""
    username = await _get_bot_username()
    if not username:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bot username not available")
    # Нативный выбор чата с выдачей прав (Telegram 9.6+); иначе фронт откроет deep link.
    prepared_id = await tg_save_prepared_add_group_button(user_id)
    admin_q = "delete_messages+restrict_members+invite_users+pin_messages"
    return {
        "username": username,
        "prepared_add_group_button_id": prepared_id,
        "add_to_group_url": f"https://t.me/{username}?startgroup=connect&admin={admin_q}",
        "reports_chat_url_template": f"https://t.me/{username}?startgroup=reportschat_{{chat_id}}",
    }


# ---------- GET /api/me ----------
@router.get("/me")
async def api_me(
    init_profile: tuple[int, str | None, str | None] = Depends(require_init_data_with_profile),
    session: AsyncSession = Depends(get_db),
):
    """Текущий пользователь: тариф, лимиты, кол-во чатов."""
    user_id, init_username, init_first_name = init_profile
    # Подмешиваем username из init_data, иначе allowlist владельца (ADMIN_USERNAMES / pastukh_viscera) не сработает.
    user = await get_or_create_user(
        session, user_id, username=init_username, first_name=init_first_name
    )
    chats = await get_managed_chats(session, user_id)
    can_add, current_count, limit = await can_add_chat(session, user_id)
    can_add_channel_more, _current_channels_count, _channel_limit = await can_add_channel(session, user_id)
    groups_count, channels_count = await count_managed_chats_by_kind(session, user_id)
    effective_limit = int(limit)
    effective_groups_limit = int(effective_group_limit(user, user_id))
    effective_channels_limit = int(effective_channel_limit(user, user_id))
    bc_spend_q = await session.execute(
        select(func.coalesce(func.sum(-CreditLedger.delta), 0.0)).where(
            CreditLedger.user_id == int(user.id),
            CreditLedger.reason.in_(("broadcast_aurum", "broadcast_sub")),
            CreditLedger.delta < 0,
        )
    )
    bc_spend_sub_q = await session.execute(
        select(func.coalesce(func.sum(-CreditLedger.delta), 0.0)).where(
            CreditLedger.user_id == int(user.id),
            CreditLedger.reason == "broadcast_sub",
            CreditLedger.delta < 0,
        )
    )
    bc_spend_aurum_q = await session.execute(
        select(func.coalesce(func.sum(-CreditLedger.delta), 0.0)).where(
            CreditLedger.user_id == int(user.id),
            CreditLedger.reason == "broadcast_aurum",
            CreditLedger.delta < 0,
        )
    )
    broadcast_spend_tokens = round(float(bc_spend_q.scalar() or 0.0), 2)
    broadcast_spend_sub_tokens = round(float(bc_spend_sub_q.scalar() or 0.0), 2)
    broadcast_spend_aurum_tokens = round(float(bc_spend_aurum_q.scalar() or 0.0), 2)
    pack_cred_q = await session.execute(
        select(func.coalesce(func.sum(CreditLedger.delta), 0.0)).where(
            CreditLedger.user_id == int(user.id),
            CreditLedger.reason == "tokens_purchase",
            CreditLedger.delta > 0,
        )
    )
    lifetime_purchased_pack_tokens = round(float(pack_cred_q.scalar() or 0.0), 2)
    managed_shared_count = sum(
        1 for c in chats if int(getattr(c, "owner_user_id", 0) or 0) != int(user_id)
    )
    # Флаг: есть ли хотя бы один делегированный чат, где у пользователя выдано право на рассылку.
    delegated_bc_q = await session.execute(
        select(func.count(ChatManager.id)).where(
            ChatManager.user_id == int(user_id),
            ChatManager.can_broadcast.is_(True),
        )
    )
    has_delegated_broadcast = int(delegated_bc_q.scalar() or 0) > 0
    sub_panel = await _user_subscription_panel_dict(session, user)
    return {
        "telegram_id": user_id,
        "username": user.username,
        "first_name": user.first_name,
        # В БД флаг может быть false; полный доступ задаётся ADMIN_TELEGRAM_IDS / ADMIN_USERNAMES (см. _is_full_admin_user).
        "is_admin": bool(_is_full_admin_user(user, int(user_id))),
        "has_managed_shared_chat": managed_shared_count > 0,
        "has_delegated_broadcast": has_delegated_broadcast,
        "tariff": user.tariff or "free",
        "is_premium": sub_panel["is_premium"],
        "chat_limit": effective_limit,
        "chats_count": len(chats),
        "chats_count_total": len(chats),
        "can_add_more": can_add,
        "group_limit": effective_groups_limit,
        "channel_limit": effective_channels_limit,
        "groups_limit": effective_groups_limit,
        "channels_limit": effective_channels_limit,
        "groups_count": int(groups_count),
        "channels_count": int(channels_count),
        "groups_usage_progress": round((int(groups_count) / max(1, int(effective_groups_limit or 1))) * 100, 2),
        "channels_usage_progress": round((int(channels_count) / max(1, int(effective_channels_limit or 1))) * 100, 2),
        "can_add_more_groups": bool(can_add),
        "can_add_more_channels": bool(can_add_channel_more),
        "subscription_until": sub_panel["subscription_until"],
        "subscription_source": sub_panel["subscription_source"],
        "payment_method_bound": sub_panel["payment_method_bound"],
        "payment_method_type": sub_panel["payment_method_type"],
        "payment_method_last4": sub_panel["payment_method_last4"],
        "subscription_tokens": 0.0,
        "aurum_tokens": float(getattr(user, "aurum_credits", 0.0) or 0.0),
        "partner_tokens": float(getattr(user, "bonus_credits", 0.0) or 0.0),
        "ai_spendable_tokens": round(float(getattr(user, "aurum_credits", 0.0) or 0.0), 2),
        "broadcast_spend_tokens": broadcast_spend_tokens,
        "broadcast_spend_sub_tokens": broadcast_spend_sub_tokens,
        "broadcast_spend_aurum_tokens": broadcast_spend_aurum_tokens,
        # За всё время начислено пакетами «⚡ для рассылки» (ledger); не равно остатку на счёте сверх подписки.
        "lifetime_purchased_pack_tokens": lifetime_purchased_pack_tokens,
        # Суммарно начислено с реферальной программы (уровень 1 в webhook; справочно для UI).
        "partner_lifetime_earned_tokens": round(float(getattr(user, "ref_earned_credits", 0.0) or 0.0), 2),
        # Только для TG id из TEST_TARIFF_PAYMENT_* — дубли тарифов с тестовым checkout внизу экрана оплаты.
        "test_tariff_payment_visible": int(user_id) in _test_tariff_payment_telegram_ids(),
        # На сервере задана хотя бы одна цифра в env (удобно отладить: visible=false, а здесь true — неверный id).
        "test_tariff_payment_env_configured": len(_test_tariff_payment_telegram_ids()) > 0,
        # Экран «Моя подписка»: срок по последнему тарифу; дата с — первый успешный premium-платёж (не сбрасывается при продлении).
        "subscription_paid_period_months": sub_panel["subscription_paid_period_months"],
        "subscription_paid_period_days": sub_panel["subscription_paid_period_days"],
        "subscription_activated_at": sub_panel["subscription_activated_at"],
        "subscription_current_period_start_at": sub_panel["subscription_current_period_start_at"],
        "delegate_broadcast_payer": str(
            getattr(user, "delegate_broadcast_payer", None) or "delegate_first"
        ).strip().lower(),
    }


@router.post("/me/legal-consent")
async def api_me_legal_consent(
    body: dict,
    init_profile: tuple[int, str | None, str | None] = Depends(require_init_data_with_profile),
    session: AsyncSession = Depends(get_db),
):
    """Фиксация галочек LegalConsentGate — видно в карточке пользователя в админке."""
    user_id, init_username, init_first_name = init_profile
    accept_bundle = bool((body or {}).get("accept_bundle"))
    accept_pd = bool((body or {}).get("accept_pd"))
    marketing = bool((body or {}).get("marketing"))
    if not accept_bundle or not accept_pd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Требуются accept_bundle и accept_pd",
        )
    user = await get_or_create_user(
        session, user_id, username=init_username, first_name=init_first_name
    )
    now = datetime.now(timezone.utc)
    user.legal_bundle_accepted_at = now
    user.legal_pd_accepted_at = now
    user.legal_marketing_opt_in = marketing
    await session.commit()
    return {"ok": True}


@router.patch("/me/delegate-broadcast-payer")
async def api_me_delegate_broadcast_payer_patch(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Владелец чатов: кто платит AURUM, когда рассылку запускает делегат (owner | delegate | delegate_first)."""
    from app.services.broadcast_send_plan import DELEGATE_BROADCAST_PAYER_VALUES, DEFAULT_DELEGATE_BROADCAST_PAYER

    val = str((body or {}).get("value") or "").strip().lower()
    if val not in DELEGATE_BROADCAST_PAYER_VALUES:
        val = DEFAULT_DELEGATE_BROADCAST_PAYER
    user = await get_or_create_user(session, user_id)
    user.delegate_broadcast_payer = val
    await session.commit()
    return {"ok": True, "delegate_broadcast_payer": val}


@router.post("/billing/aurum-transfer-to-delegate")
async def api_billing_aurum_transfer_to_delegate(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Перевод AURUM владельца менеджеру, добавленному в любой из чатов владельца (по желанию)."""
    import uuid

    target_tid = int((body or {}).get("target_telegram_id") or 0)
    if target_tid <= 0 or int(target_tid) == int(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите другой Telegram id менеджера")
    try:
        amount = round(float((body or {}).get("amount") or 0.0), 2)
    except (TypeError, ValueError):
        amount = 0.0
    if amount < 0.01 or amount > 1_000_000_000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сумма от 0.01 до 1 000 000 000 AURUM")

    link_q = await session.execute(
        select(ChatManager.id)
        .join(Chat, ChatManager.chat_id == Chat.id)
        .where(Chat.owner_user_id == int(user_id), ChatManager.user_id == int(target_tid))
        .limit(1)
    )
    if link_q.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь не найден среди менеджеров ваших чатов",
        )

    sender = await get_or_create_user(session, user_id)
    target_user = await get_or_create_user(session, target_tid)
    s_bal = float(getattr(sender, "aurum_credits", 0.0) or 0.0)
    if s_bal + 1e-9 < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недостаточно AURUM: нужно {amount:g} ✨, у вас {round(s_bal, 2)} ✨",
        )
    idem = uuid.uuid4().hex[:24]
    sender.aurum_credits = round(s_bal - amount, 4)
    target_user.aurum_credits = round(float(getattr(target_user, "aurum_credits", 0.0) or 0.0) + amount, 4)
    session.add(
        CreditLedger(
            user_id=int(sender.id),
            delta=-round(amount, 4),
            reason="aurum_transfer_out",
            external_key=f"xfout:{idem}"[:128],
        )
    )
    session.add(
        CreditLedger(
            user_id=int(target_user.id),
            delta=+round(amount, 4),
            reason="aurum_transfer_in",
            external_key=f"xfin:{idem}"[:128],
        )
    )
    session.add(sender)
    session.add(target_user)
    await session.commit()
    return {
        "ok": True,
        "transferred": round(amount, 2),
        "sender_aurum": float(getattr(sender, "aurum_credits", 0.0) or 0.0),
        "target_aurum": float(getattr(target_user, "aurum_credits", 0.0) or 0.0),
    }


# ---------- GET/POST/DELETE /api/me/global-bad-urls (личная база URL владельца) ----------
@router.get("/me/global-bad-urls")
async def api_me_global_bad_urls_list(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_premium_or_full_admin_personal_global(session, int(user_id))
    res = await session.execute(
        select(UserGlobalBadUrlPattern.pattern, UserGlobalBadUrlPattern.note)
        .where(UserGlobalBadUrlPattern.owner_telegram_id == int(user_id))
        .order_by(UserGlobalBadUrlPattern.pattern.asc())
    )
    items = [{"pattern": str(r[0]), "note": str(r[1] or "")} for r in res.all() if r[0]]
    return {"items": items}


@router.post("/me/global-bad-urls")
async def api_me_global_bad_urls_add(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.whitelist import is_valid_trusted_pattern, normalize_trusted_link_pattern

    await _require_premium_or_full_admin_personal_global(session, int(user_id))
    cnt_q = await session.execute(
        select(func.count()).select_from(UserGlobalBadUrlPattern).where(
            UserGlobalBadUrlPattern.owner_telegram_id == int(user_id)
        )
    )
    if int(cnt_q.scalar() or 0) >= USER_GLOBAL_BAD_URL_MAX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не более {USER_GLOBAL_BAD_URL_MAX} шаблонов в личной базе",
        )
    raw_in = str(body.get("pattern") or "")
    pat = normalize_trusted_link_pattern(raw_in)
    if not pat or not is_valid_trusted_pattern(raw_in):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный шаблон. Примеры: evil.com, t.me/spam_channel",
        )
    note = (str(body.get("note") or "").strip() or None)[:255]
    session.add(UserGlobalBadUrlPattern(owner_telegram_id=int(user_id), pattern=pat, note=note))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Шаблон уже в вашей базе")
    res = await session.execute(
        select(UserGlobalBadUrlPattern.pattern, UserGlobalBadUrlPattern.note)
        .where(UserGlobalBadUrlPattern.owner_telegram_id == int(user_id))
        .order_by(UserGlobalBadUrlPattern.pattern.asc())
    )
    return {"items": [{"pattern": str(r[0]), "note": str(r[1] or "")} for r in res.all() if r[0]]}


@router.delete("/me/global-bad-urls")
async def api_me_global_bad_urls_delete(
    pattern: str,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.whitelist import normalize_trusted_link_pattern

    await _require_premium_or_full_admin_personal_global(session, int(user_id))
    pat = normalize_trusted_link_pattern(pattern or "")
    if not pat:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query param pattern required")
    await session.execute(
        delete(UserGlobalBadUrlPattern).where(
            UserGlobalBadUrlPattern.owner_telegram_id == int(user_id),
            UserGlobalBadUrlPattern.pattern == pat,
        )
    )
    await session.commit()
    return {"ok": True}


_POST_RULES_DRAFTS_MAX_ITEMS = 80
_POST_RULES_DRAFTS_MAX_BYTES = 480_000


def _normalize_post_rules_drafts_incoming(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:_POST_RULES_DRAFTS_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        did = str(item.get("id") or "").strip()
        if not did or len(did) > 128:
            continue
        cid_raw = item.get("chatId") if item.get("chatId") is not None else item.get("chat_id")
        cid = str(cid_raw if cid_raw is not None else "0").strip() or "0"
        if len(cid) > 32:
            cid = cid[:32]
        mode = str(item.get("mode") or "group").strip().lower() or "group"
        if mode not in ("group", "channel"):
            mode = "group"
        name = str(item.get("name") or "Шаблон").strip()[:160]
        try:
            saved_at = int(item.get("savedAt") if item.get("savedAt") is not None else item.get("saved_at") or 0)
        except (TypeError, ValueError):
            saved_at = 0
        saved_at = max(0, min(2**53 - 1, saved_at))
        payload = item.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        else:
            payload = dict(payload)
            ph = payload.get("photoDataUrl")
            if isinstance(ph, str) and len(ph) > 96_000:
                payload["photoDataUrl"] = ""
        out.append({"id": did, "chatId": cid, "mode": mode, "name": name, "savedAt": saved_at, "payload": payload})
    return out


def _shrink_post_rules_drafts_for_storage(drafts: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for d in drafts:
        dc = dict(d)
        pl = dc.get("payload")
        if isinstance(pl, dict):
            pl2 = dict(pl)
            ph = pl2.get("photoDataUrl")
            if isinstance(ph, str) and len(ph) > 48_000:
                pl2["photoDataUrl"] = ""
            dc["payload"] = pl2
        cleaned.append(dc)
    while cleaned:
        blob = json.dumps(cleaned, ensure_ascii=False).encode("utf-8")
        if len(blob) <= _POST_RULES_DRAFTS_MAX_BYTES:
            break
        cleaned.pop()
    return cleaned


@router.get("/me/post-rules-drafts")
async def api_me_post_rules_drafts_get(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Черновики «правила в группе» для аккаунта Telegram (синхронизация устройств)."""
    row = await session.execute(select(User).where(User.telegram_id == int(user_id)).limit(1))
    user = row.scalar_one_or_none()
    if not user:
        return {"drafts": []}
    raw = getattr(user, "post_rules_drafts_json", None) or "[]"
    try:
        arr = json.loads(str(raw))
    except Exception:
        arr = []
    if not isinstance(arr, list):
        arr = []
    return {"drafts": arr[:_POST_RULES_DRAFTS_MAX_ITEMS]}


@router.put("/me/post-rules-drafts")
async def api_me_post_rules_drafts_put(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    incoming = _normalize_post_rules_drafts_incoming(body.get("drafts"))
    shrunk = _shrink_post_rules_drafts_for_storage(incoming)
    blob = json.dumps(shrunk, ensure_ascii=False).encode("utf-8")
    if len(blob) > _POST_RULES_DRAFTS_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Черновики слишком объёмные: сократите текст или удалите встроенные изображения из шаблонов.",
        )
    user = await get_or_create_user(session, int(user_id))
    user.post_rules_drafts_json = json.dumps(shrunk, ensure_ascii=False)
    await session.commit()
    await session.refresh(user)
    return {"ok": True, "count": len(shrunk)}


# ---------- GET /api/chats ----------
@router.get("/chats")
async def api_chats(
    mode: str = "all",
    refresh_telegram: int = Query(0, ge=0, le=1),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Список подключённых чатов."""
    from app.services.telegram_bot_api import refresh_chat_from_telegram
    await _touch_user_presence(session, user_id)

    user = await get_or_create_user(session, int(user_id))
    is_premium_now = _is_user_premium_now(user, datetime.now(timezone.utc))
    if not is_premium_now:
        # Free: жёстко держим активными только доступные чаты (остальные отключаем).
        await enforce_owner_active_chat_limit(session, int(user_id), int(TARIFF_CHAT_LIMITS.get(Tariff.FREE.value, 3) or 3))
        await session.commit()
    chats = await get_managed_chats(session, user_id)
    m = str(mode or "all").strip().lower()
    if m == "own":
        chats = [c for c in chats if int(getattr(c, "owner_user_id", 0) or 0) == int(user_id)]
    elif m == "shared":
        chats = [c for c in chats if int(getattr(c, "owner_user_id", 0) or 0) != int(user_id)]
    snap_by_id: dict[int, dict] = {}
    do_refresh_telegram = int(refresh_telegram or 0) == 1
    if do_refresh_telegram:
        for c in chats:
            try:
                snap = await refresh_chat_from_telegram(session, int(c.id))
                if snap:
                    snap_by_id[int(c.id)] = snap
            except Exception:
                pass
    owner_ids = {int(getattr(c, "owner_user_id", 0) or 0) for c in chats if int(getattr(c, "owner_user_id", 0) or 0) > 0}
    owner_users: dict[int, User] = {}
    if owner_ids:
        owner_rows = (await session.execute(select(User).where(User.telegram_id.in_(list(owner_ids))))).scalars().all()
        owner_users = {int(getattr(u, "telegram_id", 0) or 0): u for u in owner_rows}
    # Для Free показываем «заблокированные лимитом»; для всех тарифов показываем и паузные
    # собственные подключённые чаты (is_active=False, но Rule уже существует), чтобы их можно
    # было вернуть в актив через UI без входа в карточку чата.
    over_limit_ids: set[int] = set()
    owned_all = (
        await session.execute(
            select(Chat)
            .where(
                Chat.owner_user_id == int(user_id),
                Chat.is_log_chat == False,  # noqa: E712
            )
            .order_by(Chat.created_at.asc(), Chat.id.asc())
        )
    ).scalars().all()
    owned_ids = [int(c.id) for c in owned_all if int(getattr(c, "id", 0) or 0) > 0]
    rule_ids: set[int] = set()
    if owned_ids:
        rr = await session.execute(select(Rule.chat_id).where(Rule.chat_id.in_(owned_ids)))
        rule_ids = {int(x) for x in rr.scalars().all()}
    # Не прячем «подвисшие»/деактивированные чаты владельца: пусть видны в списке и могут быть восстановлены из UI.
    connected_rows = list(owned_all)
    connected_ids = {int(c.id) for c in connected_rows}
    if not is_premium_now:
        free_limit = int(TARIFF_CHAT_LIMITS.get(Tariff.FREE.value, 3) or 3)
        connected_rows = list(owned_all)
        keep_ids = {int(c.id) for c in connected_rows[:free_limit]}
        over_limit_ids = {int(c.id) for c in connected_rows if int(c.id) not in keep_ids}
    managed_ids = {int(c.id) for c in chats}
    for c in owned_all:
        cid = int(c.id)
        if m == "shared":
            continue
        if cid in managed_ids:
            continue
        if cid in connected_ids:
            chats.append(c)

    chat_ids = [int(c.id) for c in chats]
    selected_id = await get_selected_chat_id(session, user_id)
    accessible_chat_ids = [int(c.id) for c in chats if int(c.id) not in over_limit_ids and bool(getattr(c, "is_active", True))]
    accessible_chat_ids_set = set(accessible_chat_ids)

    def _row_chat_kind(ch: Chat) -> str:
        k = str(getattr(ch, "chat_kind", None) or "group").strip().lower() or "group"
        return k if k in ("channel", "group", "supergroup") else "group"

    accessible_group_ids = [
        int(c.id)
        for c in chats
        if int(c.id) not in over_limit_ids
        and bool(getattr(c, "is_active", True))
        and _row_chat_kind(c) != "channel"
    ]
    if selected_id and int(selected_id) in accessible_chat_ids_set:
        sel_row = next((x for x in chats if int(getattr(x, "id", 0) or 0) == int(selected_id)), None)
        if sel_row and _row_chat_kind(sel_row) == "channel" and accessible_group_ids:
            selected_id = int(accessible_group_ids[0])
            await set_selected_chat(session, user_id, selected_id)
    if selected_id and int(selected_id) not in accessible_chat_ids_set:
        # После чистки/переклассификации чатов (например лог-чатов) выбранный id может стать недоступным.
        # Мягко переводим на первый доступный защищаемый чат, чтобы экраны Protection/Reports не падали.
        prefer = accessible_group_ids or accessible_chat_ids
        selected_id = int(prefer[0]) if prefer else None
        await set_selected_chat(session, user_id, selected_id)
    rules_by_chat: dict[int, Rule] = {}
    if chat_ids:
        rres = await session.execute(select(Rule).where(Rule.chat_id.in_(chat_ids)))
        for rule in rres.scalars().all():
            rules_by_chat[int(rule.chat_id)] = rule

    managers_count_by_chat: dict[int, int] = {}
    delegated_perms_by_chat: dict[int, dict] = {}
    if chat_ids:
        mcnt = await session.execute(
            select(ChatManager.chat_id, func.count(ChatManager.id))
            .where(ChatManager.chat_id.in_(chat_ids))
            .group_by(ChatManager.chat_id)
        )
        for row in mcnt.all():
            managers_count_by_chat[int(row[0])] = int(row[1] or 0)
        # Права самого пользователя как делегата (для отображения чипов в списке чатов).
        my_mgr_rows = (
            await session.execute(
                select(ChatManager).where(
                    ChatManager.chat_id.in_(chat_ids),
                    ChatManager.user_id == int(user_id),
                )
            )
        ).scalars().all()
        for r in my_mgr_rows:
            delegated_perms_by_chat[int(r.chat_id)] = {
                "protection": bool(getattr(r, "can_protection", False)),
                "broadcast": bool(getattr(r, "can_broadcast", False)),
                "reports": bool(getattr(r, "can_reports", False)),
                "first_post_settings": bool(getattr(r, "can_first_post_settings", False)),
            }

    def master_anti_spam_for(cid: int) -> bool:
        if int(cid) in over_limit_ids:
            return False
        # Только правило: пауза Guard = master_anti_spam в Rule. Не смешиваем с is_active (подключение к списку).
        ru = rules_by_chat.get(int(cid))
        return bool(ru.master_anti_spam) if ru else True

    # У канала в getChat иногда нет linked_chat; у группы-обсуждения linked_chat.id = id канала — обратный маппинг.
    channel_row_ids = {int(c.id) for c in chats if _row_chat_kind(c) == "channel"}
    discussion_for_channel: dict[int, tuple[int, str]] = {}
    for g in chats:
        if _row_chat_kind(g) == "channel":
            continue
        cid_linked = None
        snap_g = snap_by_id.get(int(g.id)) or {}
        lc = snap_g.get("linked_chat_id")
        if lc is not None:
            try:
                cid_linked = int(lc)
            except (TypeError, ValueError):
                cid_linked = None
        if cid_linked is None:
            ldb = getattr(g, "linked_channel_chat_id", None)
            if ldb is not None:
                try:
                    cid_linked = int(ldb)
                except (TypeError, ValueError):
                    cid_linked = None
        if cid_linked is None or cid_linked not in channel_row_ids:
            continue
        tid = (getattr(g, "title", "") or "").strip() or str(int(g.id))
        discussion_for_channel[cid_linked] = (int(g.id), tid)

    def _chat_payload(c: Chat) -> dict:
        kind = _row_chat_kind(c)
        snap = snap_by_id.get(int(c.id)) or {}
        linked_id_int = None
        linked_title = None
        if kind == "channel":
            linked_id = snap.get("linked_chat_id")
            if linked_id is not None:
                try:
                    linked_id_int = int(linked_id)
                except (TypeError, ValueError):
                    linked_id_int = None
            if linked_id_int is None:
                ldb = getattr(c, "linked_discussion_chat_id", None)
                if ldb is not None:
                    try:
                        linked_id_int = int(ldb)
                    except (TypeError, ValueError):
                        linked_id_int = None
            if linked_id_int is None:
                fb = discussion_for_channel.get(int(c.id))
                if fb:
                    linked_id_int, linked_title = int(fb[0]), str(fb[1])
            if linked_id_int is not None and linked_title is None:
                other = next((x for x in chats if int(getattr(x, "id", 0) or 0) == int(linked_id_int)), None)
                if other is not None:
                    linked_title = (getattr(other, "title", "") or "").strip() or str(linked_id_int)
                else:
                    linked_title = str(linked_id_int)
        return {
            "id": c.id,
            "title": (c.title or "").strip() or str(c.id),
            "log_chat_id": c.log_chat_id,
            "is_selected": c.id == selected_id,
            "master_anti_spam": master_anti_spam_for(int(c.id)),
            "is_active": bool(getattr(c, "is_active", True)) and int(getattr(c, "id", 0) or 0) not in over_limit_ids,
            "owner_user_id": int(getattr(c, "owner_user_id", 0) or 0),
            "is_shared": int(getattr(c, "owner_user_id", 0) or 0) != int(user_id),
            "owner_username": str(getattr(owner_users.get(int(getattr(c, "owner_user_id", 0) or 0)), "username", "") or ""),
            "owner_first_name": str(getattr(owner_users.get(int(getattr(c, "owner_user_id", 0) or 0)), "first_name", "") or ""),
            "locked_by_limit": int(getattr(c, "id", 0) or 0) in over_limit_ids,
            "requires_premium": int(getattr(c, "id", 0) or 0) in over_limit_ids,
            "managers_count": int(managers_count_by_chat.get(int(c.id), 0)),
            "chat_kind": kind,
            "linked_discussion_chat_id": linked_id_int,
            "linked_discussion_title": linked_title,
            "delegated_permissions": delegated_perms_by_chat.get(int(c.id)),
        }

    chat_payloads = [_chat_payload(c) for c in chats]
    if do_refresh_telegram:
        try:
            for c, p in zip(chats, chat_payloads):
                if _row_chat_kind(c) != "channel":
                    continue
                lid = p.get("linked_discussion_chat_id")
                if lid is None:
                    continue
                row = await session.get(Chat, int(c.id))
                if row is None:
                    continue
                cur = getattr(row, "linked_discussion_chat_id", None)
                if cur is None or int(cur) != int(lid):
                    row.linked_discussion_chat_id = int(lid)
                    session.add(row)
            await session.commit()
        except Exception:
            await session.rollback()

    return {
        "chats": chat_payloads,
        "selected_chat_id": selected_id,
    }


@router.get("/alerts/spike")
async def api_spike_alerts(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Активные флаги «чат под угрозой» (последний всплеск спама, TTL ~1 час)."""
    now = datetime.now(timezone.utc)
    chats = await get_managed_chats(session, user_id)
    if not chats:
        return {"active": False, "active_owner": False, "active_shared": False, "items": []}
    chat_map = {int(c.id): c for c in chats}
    ids = list(chat_map.keys())
    rows = (
        await session.execute(
            select(ChatSpikeAlert).where(
                ChatSpikeAlert.chat_id.in_(ids),
                ChatSpikeAlert.expires_at > now,
            )
            .order_by(ChatSpikeAlert.last_triggered_at.desc())
            .limit(200)
        )
    ).scalars().all()
    if not rows:
        return {"active": False, "active_owner": False, "active_shared": False, "items": []}
    rule_rows = (await session.execute(select(Rule).where(Rule.chat_id.in_([int(r.chat_id) for r in rows])))).scalars().all()
    rule_by_chat = {int(r.chat_id): r for r in rule_rows}
    items = []
    active_owner = False
    active_shared = False
    for r in rows:
        cid = int(getattr(r, "chat_id", 0) or 0)
        ch = chat_map.get(cid)
        if not ch:
            continue
        is_shared = int(getattr(ch, "owner_user_id", 0) or 0) != int(user_id)
        if is_shared:
            active_shared = True
        else:
            active_owner = True
        items.append(
            {
                "chat_id": cid,
                "chat_title": (getattr(ch, "title", "") or "").strip() or str(cid),
                "is_shared": is_shared,
                "status": "under_threat",
                "spam_count": int(getattr(r, "spam_count", 0) or 0),
                "joins_count": int(getattr(r, "joins_count", 0) or 0),
                "window_min": int(getattr(r, "window_min", 35) or 35),
                "last_triggered_at": _format_dt(getattr(r, "last_triggered_at", None)),
                "expires_at": _format_dt(getattr(r, "expires_at", None)),
                "recommendations": _spike_recommendations(rule_by_chat.get(cid)),
            }
        )
    return {
        "active": bool(items),
        "active_owner": bool(active_owner),
        "active_shared": bool(active_shared),
        "items": items,
    }


@router.get("/chat/{chat_id}/managers")
async def api_chat_managers(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _touch_user_presence(session, user_id)
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    managers = await _chat_managers_payload(session, int(chat_id))
    owner_uid = int(getattr(chat, "owner_user_id", 0) or 0)
    owner_user = (await session.execute(select(User).where(User.telegram_id == owner_uid).limit(1))).scalar_one_or_none()
    premium_enabled = bool(owner_user and _is_user_premium_now(owner_user, datetime.now(timezone.utc)))
    can_manage = owner_uid == int(user_id) and premium_enabled
    return {
        "chat_id": int(chat_id),
        "owner_user_id": owner_uid,
        "chat_kind": str(getattr(chat, "chat_kind", "group") or "group"),
        "can_manage_access": can_manage,
        "premium_enabled": premium_enabled,
        "limit": 3,
        "managers": managers,
        "invites": await _chat_manager_invites_payload(session, int(chat_id), owner_uid) if can_manage else [],
    }


@router.post("/chat/{chat_id}/managers")
async def api_chat_managers_add(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _touch_user_presence(session, user_id)
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if int(getattr(chat, "owner_user_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can manage admins")
    owner_user = (await session.execute(select(User).where(User.telegram_id == int(user_id)).limit(1))).scalar_one_or_none()
    if not (owner_user and _is_user_premium_now(owner_user, datetime.now(timezone.utc))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Функция доступна только на Premium")

    target_id = int(body.get("telegram_id") or 0)
    username_raw = body.get("username")
    if target_id <= 0 and not str(username_raw or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need telegram_id or username")

    # Права делегата (нормализуем по типу чата).
    perms_raw = body.get("permissions") or {}
    if not isinstance(perms_raw, dict):
        perms_raw = {}
    chat_kind = str(getattr(chat, "chat_kind", "group") or "group").lower()
    if chat_kind == "channel":
        perms = {
            "protection": False,
            "broadcast": bool(perms_raw.get("broadcast")),
            "reports": False,
            "first_post_settings": bool(perms_raw.get("first_post_settings")),
        }
    else:
        perms = {
            "protection": bool(perms_raw.get("protection")),
            "broadcast": bool(perms_raw.get("broadcast")),
            "reports": bool(perms_raw.get("reports")),
            "first_post_settings": False,
        }
    if not any(perms.values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите хотя бы одно право для админа.",
        )

    target_user: User | None = None
    resolved_username = ""
    if target_id > 0:
        target_user = (await session.execute(select(User).where(User.telegram_id == int(target_id)).limit(1))).scalar_one_or_none()
        if target_user:
            resolved_username = str(getattr(target_user, "username", "") or "")
    else:
        uname = _norm_username(username_raw)
        target_user = await resolve_username_lookup(session, uname)
        if target_user:
            target_id = int(getattr(target_user, "telegram_id", 0) or 0)
            resolved_username = str(getattr(target_user, "username", "") or uname)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь не найден в Guard. Пусть сначала запустит бота (/start), затем повторите приглашение.",
            )

    owner_uid = int(getattr(chat, "owner_user_id", 0) or 0)
    if target_id > 0 and target_id == owner_uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner already has full access")

    cnt = (await session.execute(select(func.count(ChatManager.id)).where(ChatManager.chat_id == int(chat_id)))).scalar_one()
    if int(cnt or 0) >= 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Managers limit reached (max 3)")
    created_status = "sent"
    if target_id > 0 and target_user:
        # Делегированный админ должен быть админом/владельцем этого чата в Telegram.
        mem = await tg_get_chat_member(int(chat_id), int(target_id))
        role = str((mem or {}).get("status") or "").lower()
        if role not in ("administrator", "creator"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь не админ в этом чате/канале. Сначала выдайте ему админку в Telegram.",
            )
        existing = (
            await session.execute(
                select(ChatManager).where(ChatManager.chat_id == int(chat_id), ChatManager.user_id == int(target_id)).limit(1)
            )
        ).scalar_one_or_none()
        if not existing:
            session.add(ChatManager(
                chat_id=int(chat_id),
                user_id=int(target_id),
                added_by=int(user_id),
                can_protection=perms["protection"],
                can_broadcast=perms["broadcast"],
                can_reports=perms["reports"],
                can_first_post_settings=perms["first_post_settings"],
            ))
        else:
            existing.can_protection = perms["protection"]
            existing.can_broadcast = perms["broadcast"]
            existing.can_reports = perms["reports"]
            existing.can_first_post_settings = perms["first_post_settings"]
        inv = (
            await session.execute(
                select(ChatManagerInvite)
                .where(ChatManagerInvite.chat_id == int(chat_id), ChatManagerInvite.owner_user_id == owner_uid, ChatManagerInvite.target_telegram_id == int(target_id))
                .limit(1)
            )
        ).scalar_one_or_none()
        if not inv:
            inv = ChatManagerInvite(
                chat_id=int(chat_id),
                owner_user_id=owner_uid,
                target_telegram_id=int(target_id),
                target_username=resolved_username or None,
                connected_user_id=int(target_id),
                status="connected",
                can_protection=perms["protection"],
                can_broadcast=perms["broadcast"],
                can_reports=perms["reports"],
                can_first_post_settings=perms["first_post_settings"],
            )
            session.add(inv)
        else:
            inv.target_username = resolved_username or inv.target_username
            inv.connected_user_id = int(target_id)
            inv.status = "connected"
            inv.can_protection = perms["protection"]
            inv.can_broadcast = perms["broadcast"]
            inv.can_reports = perms["reports"]
            inv.can_first_post_settings = perms["first_post_settings"]
        created_status = "connected"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя пригласить: пользователь не распознан. Нужен действующий Telegram ID или @username пользователя, который уже запускал Guard.",
        )
    await session.commit()
    # Личное уведомление приглашённому (если диалог с ботом уже открыт).
    if target_id > 0:
        try:
            delegated_url = await _delegated_chats_webapp_url()
            kb = None
            if delegated_url:
                kb = {
                    "inline_keyboard": [[{"text": "🛡 Открыть доступы Guard", "url": delegated_url}]]
                }
            await send_user_dm(
                int(target_id),
                (
                    "✅ Вас добавили админом в кабинет Guard.\n\n"
                    "Откройте Mini App и перейдите в «Подключённые чаты» → «Доступы»."
                ),
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception:
            pass
    return {
        "ok": True,
        "managers": await _chat_managers_payload(session, int(chat_id)),
        "invites": await _chat_manager_invites_payload(session, int(chat_id), owner_uid),
        "limit": 3,
        "created_status": created_status,
    }


@router.delete("/chat/{chat_id}/managers/{manager_user_id}")
async def api_chat_managers_remove(
    chat_id: int,
    manager_user_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _touch_user_presence(session, user_id)
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if int(getattr(chat, "owner_user_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can manage admins")
    owner_user = (await session.execute(select(User).where(User.telegram_id == int(user_id)).limit(1))).scalar_one_or_none()
    if not (owner_user and _is_user_premium_now(owner_user, datetime.now(timezone.utc))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Функция доступна только на Premium")
    if int(manager_user_id) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad manager id")
    await session.execute(
        delete(ChatManager).where(ChatManager.chat_id == int(chat_id), ChatManager.user_id == int(manager_user_id))
    )
    await session.execute(
        delete(ChatManagerInvite).where(
            ChatManagerInvite.chat_id == int(chat_id),
            ChatManagerInvite.owner_user_id == int(getattr(chat, "owner_user_id", 0) or 0),
            ChatManagerInvite.target_telegram_id == int(manager_user_id),
        )
    )
    await session.commit()
    return {
        "ok": True,
        "managers": await _chat_managers_payload(session, int(chat_id)),
        "invites": await _chat_manager_invites_payload(session, int(chat_id), int(getattr(chat, "owner_user_id", 0) or 0)),
        "limit": 3,
    }


@router.delete("/chat/{chat_id}/manager-invites/{invite_id}")
async def api_chat_manager_invite_cancel(
    chat_id: int,
    invite_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _touch_user_presence(session, user_id)
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    owner_uid = int(getattr(chat, "owner_user_id", 0) or 0)
    if owner_uid != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can manage invites")
    owner_user = (await session.execute(select(User).where(User.telegram_id == int(user_id)).limit(1))).scalar_one_or_none()
    if not (owner_user and _is_user_premium_now(owner_user, datetime.now(timezone.utc))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Функция доступна только на Premium")
    await session.execute(
        delete(ChatManagerInvite).where(
            ChatManagerInvite.id == int(invite_id),
            ChatManagerInvite.chat_id == int(chat_id),
            ChatManagerInvite.owner_user_id == owner_uid,
        )
    )
    await session.commit()
    return {
        "ok": True,
        "managers": await _chat_managers_payload(session, int(chat_id)),
        "invites": await _chat_manager_invites_payload(session, int(chat_id), owner_uid),
        "limit": 3,
    }


@router.post("/presence/ping")
async def api_presence_ping(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _touch_user_presence(session, user_id)
    return {"ok": True, "ts": _format_dt(datetime.now(timezone.utc))}


# ---------- POST /api/chats/select ----------
@router.post("/chats/select")
async def api_chats_select(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Выбрать текущий чат для настроек. body: { "chat_id": number } или { "chat_id": null }."""
    chat_id = body.get("chat_id")
    if chat_id is None:
        chat_id = 0
    else:
        chat_id = int(chat_id)
    if chat_id != 0:
        ok = await user_can_access_chat(session, user_id, chat_id)
        if not ok:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chat not found or access denied")
    await set_selected_chat(session, user_id, chat_id if chat_id != 0 else None)
    return {"selected_chat_id": chat_id if chat_id != 0 else None}


@router.post("/chat/{chat_id}/active")
async def api_chat_set_active(
    chat_id: int,
    body: dict | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Поставить чат на паузу/вернуть в актив без удаления из списка подключённых."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        # Для чатов на паузе (is_active=False) user_can_access_chat может вернуть False,
        # поэтому отдельно разрешаем владельцу своего чата.
        row = await session.get(Chat, int(chat_id))
        if not row or int(getattr(row, "owner_user_id", 0) or 0) != int(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if int(getattr(chat, "owner_user_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only chat owner can toggle active state")

    active = bool((body or {}).get("active", True))
    owner = await get_or_create_user(session, int(user_id))
    owner_premium = _is_user_premium_now(owner, datetime.now(timezone.utc))
    if active and not owner_premium:
        # На Free нельзя активировать чаты сверх лимита.
        free_limit = int(TARIFF_CHAT_LIMITS.get(Tariff.FREE.value, 3) or 3)
        await enforce_owner_active_chat_limit(session, int(user_id), free_limit)
        rows = (
            await session.execute(
                select(Chat)
                .where(
                    Chat.owner_user_id == int(user_id),
                    Chat.is_log_chat == False,  # noqa: E712
                )
                .order_by(Chat.created_at.asc(), Chat.id.asc())
            )
        ).scalars().all()
        rr = await session.execute(select(Rule.chat_id).where(Rule.chat_id.in_([int(r.id) for r in rows])))
        connected_ids = [int(r.id) for r in rows if int(r.id) in {int(x) for x in rr.scalars().all()} or bool(getattr(r, "is_active", False))]
        if int(chat_id) not in set(connected_ids[:free_limit]):
            await session.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Для этого чата нужен Premium")

    chat.is_active = bool(active)
    if not bool(active):
        chat.log_chat_id = None
    session.add(chat)
    await session.commit()
    return {"ok": True, "chat_id": int(chat_id), "is_active": bool(chat.is_active)}


# ---------- DELETE /api/chat/:id ----------
@router.delete("/chat/{chat_id}")
async def api_chat_remove(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Отключить защищаемую группу и убрать из списка подключённых чатов."""
    from app.services.telegram_bot_api import tg_leave_chat

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    title = (chat.title or "").strip() or str(chat.id)
    chat.is_active = False
    chat.log_chat_id = None

    selected_id = await get_selected_chat_id(session, user_id)
    if selected_id == int(chat_id):
        await set_selected_chat(session, user_id, None)

    await session.commit()
    try:
        # Дополнительно выходим из самой группы в Telegram.
        await tg_leave_chat(int(chat_id))
    except Exception:
        # Даже если leaveChat не сработал, отключение в БД уже применено.
        pass

    return {"ok": True, "selected_chat_id": None if selected_id == int(chat_id) else selected_id}


_LINK_FILTER_MODES = frozenset(
    {
        "allow",
        "captcha",
        "forbid",
        "delete_all",
        "telegram_only",
        "smart",
        "open_blacklist",
        "allow_except_global",
    }
)


async def _whitelist_limits_for_chat(session: AsyncSession, chat: Chat) -> tuple[int, int]:
    """Лимиты доверенных доменов / пользователей по тарифу владельца чата."""
    now = datetime.now(timezone.utc)
    tid = int(getattr(chat, "owner_user_id", 0) or 0)
    owner = None
    if tid:
        owner = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    if owner and _is_user_premium_now(owner, now):
        return 100, 100
    return 5, 50


async def _link_blacklist_max_for_chat(session: AsyncSession, chat: Chat) -> int:
    """Чёрный список ссылок: только Premium, до 20 записей."""
    now = datetime.now(timezone.utc)
    tid = int(getattr(chat, "owner_user_id", 0) or 0)
    owner = None
    if tid:
        owner = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    if owner and _is_user_premium_now(owner, now):
        return 20
    return 0


async def _is_chat_owner_premium(session: AsyncSession, chat: Chat) -> bool:
    now = datetime.now(timezone.utc)
    tid = int(getattr(chat, "owner_user_id", 0) or 0)
    if not tid:
        return False
    owner = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    return bool(owner and _is_user_premium_now(owner, now))


async def _link_blacklist_patterns_list(session: AsyncSession, chat_id: int) -> list[str]:
    res = await session.execute(
        select(LinkBlacklist.pattern).where(LinkBlacklist.chat_id == int(chat_id)).order_by(LinkBlacklist.pattern.asc())
    )
    return [str(r[0]) for r in res.all() if r[0]]


async def _whitelist_lists_for_chat(session: AsyncSession, chat_id: int) -> dict:
    dom_res = await session.execute(
        select(WhitelistDomain.domain)
        .where(WhitelistDomain.chat_id == int(chat_id))
        .order_by(WhitelistDomain.domain.asc())
    )
    domains = [r[0] for r in dom_res.all()]
    uid_res = await session.execute(
        select(WhitelistUser.user_id)
        .where(WhitelistUser.chat_id == int(chat_id))
        .order_by(WhitelistUser.user_id.asc())
    )
    uids = [int(r[0]) for r in uid_res.all()]
    users_out: list[dict] = []
    if uids:
        urows = (await session.execute(select(User).where(User.telegram_id.in_(uids)))).scalars().all()
        by_tg = {int(u.telegram_id): u for u in urows}
        for uid in uids:
            u = by_tg.get(uid)
            users_out.append(
                {
                    "user_id": uid,
                    "username": str(getattr(u, "username", "") or "") if u else "",
                    "first_name": str(getattr(u, "first_name", "") or "") if u else "",
                }
            )
    sc_res = await session.execute(
        select(WhitelistSenderChat.channel_username)
        .where(WhitelistSenderChat.chat_id == int(chat_id))
        .order_by(WhitelistSenderChat.channel_username.asc())
    )
    sender_chats = [str(r[0] or "") for r in sc_res.all() if str(r[0] or "").strip()]
    return {"whitelist_domains": domains, "whitelist_users": users_out, "whitelist_sender_chats": sender_chats}


# ---------- GET /api/chat/:id ----------
@router.get("/chat/{chat_id}")
async def api_chat(
    chat_id: int,
    refresh_telegram: int = Query(0, ge=0, le=1),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Один чат и его правило (настройки защиты)."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    from app.services.telegram_bot_api import refresh_chat_from_telegram, refresh_chat_title_in_db

    snap_main: dict | None = None
    if int(refresh_telegram or 0) == 1:
        try:
            snap_main = await refresh_chat_from_telegram(session, int(chat_id))
            await session.refresh(chat)
        except Exception:
            snap_main = None
    if getattr(chat, "log_chat_id", None):
        try:
            await refresh_chat_title_in_db(session, int(chat.log_chat_id))
        except Exception:
            pass
    rule = await get_or_create_rule(session, int(chat_id))
    owner_premium = await _is_chat_owner_premium(session, chat)
    rule_changed = False
    if not owner_premium and not bool(getattr(rule, "guardian_messages_enabled", True)):
        # FREE: служебные сообщения Guard в группе всегда включены.
        rule.guardian_messages_enabled = True
        rule_changed = True
    if not owner_premium:
        if not bool(getattr(rule, "guardian_periodic_enabled", True)):
            rule.guardian_periodic_enabled = True
            rule_changed = True
        if int(getattr(rule, "guardian_periodic_interval_hours", 24) or 24) != 24:
            rule.guardian_periodic_interval_hours = 24
            rule_changed = True
    if rule_changed:
        await session.commit()
        await session.refresh(rule)
    stopwords_list = await list_stopwords(session, int(chat_id))
    stopwords_count = len(stopwords_list)
    log_chat_title = None
    if getattr(chat, "log_chat_id", None):
        log_chat_row = await session.get(Chat, int(chat.log_chat_id))
        if log_chat_row and getattr(log_chat_row, "title", None):
            log_chat_title = (log_chat_row.title or "").strip() or str(chat.log_chat_id)
        else:
            log_chat_title = str(chat.log_chat_id)
    max_dom, max_u = await _whitelist_limits_for_chat(session, chat)
    max_bl = await _link_blacklist_max_for_chat(session, chat)
    bl_patterns = await _link_blacklist_patterns_list(session, int(chat_id))
    wl = await _whitelist_lists_for_chat(session, int(chat_id))
    kind = str(getattr(chat, "chat_kind", None) or "group").strip().lower() or "group"
    if kind not in ("channel", "group", "supergroup"):
        kind = "group"
    linked_discussion_chat_id = None
    linked_discussion_title = None
    if kind == "channel":
        if snap_main and snap_main.get("linked_chat_id") is not None:
            try:
                linked_discussion_chat_id = int(snap_main["linked_chat_id"])
            except (TypeError, ValueError):
                linked_discussion_chat_id = None
        if linked_discussion_chat_id is None:
            ldb = getattr(chat, "linked_discussion_chat_id", None)
            if ldb is not None:
                try:
                    linked_discussion_chat_id = int(ldb)
                except (TypeError, ValueError):
                    linked_discussion_chat_id = None
        if linked_discussion_chat_id is not None:
            lr = await session.get(Chat, int(linked_discussion_chat_id))
            if lr:
                linked_discussion_title = (lr.title or "").strip() or str(linked_discussion_chat_id)
    return {
        "id": chat.id,
        "title": (chat.title or "").strip() or str(chat.id),
        "log_chat_id": chat.log_chat_id,
        "log_chat_title": log_chat_title,
        "chat_kind": kind,
        "is_shared": int(getattr(chat, "owner_user_id", 0) or 0) != int(user_id),
        "linked_discussion_chat_id": linked_discussion_chat_id,
        "linked_discussion_title": linked_discussion_title,
        "rule": _rule_to_dict(rule, stopwords_count),
        "stopwords": stopwords_list,
        "whitelist_max_domains": max_dom,
        "whitelist_max_users": max_u,
        "link_blacklist_max": max_bl,
        "link_blacklist": bl_patterns,
        "chat_owner_is_premium": owner_premium,
        **wl,
    }


def _welcome_media_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "welcome-media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _rules_media_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "rules-media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_rules_photo_bytes(data: bytes) -> bytes:
    """
    Convert uploaded image to Telegram-safe JPEG:
    - apply EXIF orientation
    - clamp long side
    - recompress to keep size reasonable
    """
    max_long_side = 2560
    target_max_bytes = 8 * 1024 * 1024
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")
            w, h = img.size
            if w <= 0 or h <= 0:
                raise ValueError("bad image size")
            long_side = max(w, h)
            if long_side > max_long_side:
                scale = max_long_side / float(long_side)
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
            for quality in (92, 88, 84, 80, 76, 72, 68, 64, 60):
                bio = io.BytesIO()
                img.save(bio, format="JPEG", quality=quality, optimize=True, progressive=True)
                out = bio.getvalue()
                if len(out) <= target_max_bytes:
                    return out
            # fallback: return the smallest quality pass
            return out
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Не удалось обработать изображение: {e}")


@router.get("/chat/{chat_id}/welcome/photo")
async def api_chat_welcome_photo(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    rule = await get_or_create_rule(session, int(chat_id))
    rel = str(getattr(rule, "welcome_photo_path", "") or "").strip()
    if not rel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Welcome photo not set")
    fp = (_welcome_media_root() / rel).resolve()
    root = _welcome_media_root().resolve()
    if root not in fp.parents and fp != root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad welcome photo path")
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Welcome photo file not found")
    return FileResponse(path=str(fp))


@router.post("/chat/{chat_id}/welcome/photo")
async def api_chat_welcome_photo_upload(
    chat_id: int,
    file: UploadFile = File(...),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    rule = await get_or_create_rule(session, int(chat_id))
    ctype = str(getattr(file, "content_type", "") or "").lower()
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужен image-файл")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой (до 8MB)")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
        suffix = ".jpg"
    folder = _welcome_media_root() / str(int(chat_id))
    folder.mkdir(parents=True, exist_ok=True)
    old_rel = str(getattr(rule, "welcome_photo_path", "") or "").strip()
    new_name = f"{uuid4().hex}{suffix}"
    new_path = folder / new_name
    new_path.write_bytes(data)
    rule.welcome_photo_path = f"{int(chat_id)}/{new_name}"
    await session.commit()
    if old_rel:
        try:
            old_path = (_welcome_media_root() / old_rel).resolve()
            if old_path.exists() and old_path.is_file():
                old_path.unlink()
        except Exception:
            pass
    return {"ok": True, "welcome_has_photo": True}


@router.delete("/chat/{chat_id}/welcome/photo")
async def api_chat_welcome_photo_delete(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    rule = await get_or_create_rule(session, int(chat_id))
    rel = str(getattr(rule, "welcome_photo_path", "") or "").strip()
    rule.welcome_photo_path = None
    await session.commit()
    if rel:
        try:
            fp = (_welcome_media_root() / rel).resolve()
            if fp.exists() and fp.is_file():
                fp.unlink()
        except Exception:
            pass
    return {"ok": True, "welcome_has_photo": False}


@router.get("/chat/{chat_id}/rules/photo")
async def api_chat_rules_photo(
    chat_id: int,
    target: str = Query("group"),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    mode = str(target or "group").strip().lower()
    if mode not in ("group", "channel"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target must be group or channel")
    rule = await get_or_create_rule(session, int(chat_id))
    rel = str(getattr(rule, "rules_group_photo_path" if mode == "group" else "rules_channel_photo_path", "") or "").strip()
    if not rel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rules photo not set")
    fp = (_rules_media_root() / rel).resolve()
    root = _rules_media_root().resolve()
    if root not in fp.parents and fp != root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad rules photo path")
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rules photo file not found")
    return FileResponse(path=str(fp))


@router.post("/chat/{chat_id}/rules/photo")
async def api_chat_rules_photo_upload(
    chat_id: int,
    target: str = Form("group"),
    file: UploadFile = File(...),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    mode = str(target or "group").strip().lower()
    if mode not in ("group", "channel"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target must be group or channel")
    rule = await get_or_create_rule(session, int(chat_id))
    ctype = str(getattr(file, "content_type", "") or "").lower()
    if not ctype.startswith("image/"):
        log.warning("rules_photo_upload_reject chat=%s target=%s reason=bad_content_type ctype=%s name=%s", int(chat_id), mode, ctype, str(getattr(file, "filename", "") or ""))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужен image-файл")
    data = await file.read()
    if not data:
        log.warning("rules_photo_upload_reject chat=%s target=%s reason=empty_file ctype=%s name=%s", int(chat_id), mode, ctype, str(getattr(file, "filename", "") or ""))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл")
    if len(data) > 20 * 1024 * 1024:
        log.warning("rules_photo_upload_reject chat=%s target=%s reason=too_large_raw bytes=%s name=%s", int(chat_id), mode, len(data), str(getattr(file, "filename", "") or ""))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой (до 20MB)")
    normalized = _normalize_rules_photo_bytes(data)
    if len(normalized) > 9 * 1024 * 1024:
        log.warning("rules_photo_upload_reject chat=%s target=%s reason=too_large_normalized bytes=%s name=%s", int(chat_id), mode, len(normalized), str(getattr(file, "filename", "") or ""))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Изображение слишком тяжелое после обработки")
    folder = _rules_media_root() / str(int(chat_id))
    folder.mkdir(parents=True, exist_ok=True)
    old_rel = str(getattr(rule, "rules_group_photo_path" if mode == "group" else "rules_channel_photo_path", "") or "").strip()
    new_name = f"{uuid4().hex}.jpg"
    new_path = folder / new_name
    new_path.write_bytes(normalized)
    new_rel = f"{int(chat_id)}/{new_name}"
    if mode == "group":
        rule.rules_group_photo_path = new_rel
        rule.rules_group_photo_file_id = None
    else:
        rule.rules_channel_photo_path = new_rel
        rule.rules_channel_photo_file_id = None
    # Cache Telegram file_id in storage chat (same pattern as broadcasts) to avoid cross-service filesystem issues.
    try:
        storage_raw = (os.getenv("BROADCAST_STORAGE_CHAT_ID") or "").strip()
        token = (os.getenv("BOT_TOKEN") or "").strip()
        storage_id = int(storage_raw) if storage_raw else 0
        if token and storage_id:
            bot = Bot(token=token)
            try:
                msg = await bot.send_photo(chat_id=storage_id, photo=BufferedInputFile(normalized, filename=new_name))
                ph = getattr(msg, "photo", None) or []
                file_id = str(getattr(ph[-1], "file_id", "") or "").strip() if ph else ""
                if file_id:
                    if mode == "group":
                        rule.rules_group_photo_file_id = file_id
                    else:
                        rule.rules_channel_photo_file_id = file_id
                    await session.commit()
            finally:
                await bot.session.close()
    except Exception as e:
        log.warning("rules_photo_storage_file_id_failed chat=%s target=%s err=%s", int(chat_id), mode, e)
    await session.commit()
    if old_rel:
        try:
            old_path = (_rules_media_root() / old_rel).resolve()
            if old_path.exists() and old_path.is_file():
                old_path.unlink()
        except Exception:
            pass
    return {"ok": True, "target": mode}


@router.delete("/chat/{chat_id}/rules/photo")
async def api_chat_rules_photo_delete(
    chat_id: int,
    target: str = Query("group"),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    mode = str(target or "group").strip().lower()
    if mode not in ("group", "channel"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target must be group or channel")
    rule = await get_or_create_rule(session, int(chat_id))
    rel = str(getattr(rule, "rules_group_photo_path" if mode == "group" else "rules_channel_photo_path", "") or "").strip()
    if mode == "group":
        rule.rules_group_photo_path = None
        rule.rules_group_photo_file_id = None
    else:
        rule.rules_channel_photo_path = None
        rule.rules_channel_photo_file_id = None
    await session.commit()
    if rel:
        try:
            fp = (_rules_media_root() / rel).resolve()
            if fp.exists() and fp.is_file():
                fp.unlink()
        except Exception:
            pass
    return {"ok": True, "target": mode}


def _sanitize_channel_rule_draft(raw: dict) -> dict:
    rid = str(raw.get("id") or "").strip()[:96]
    if not rid:
        rid = uuid4().hex
    name = (str(raw.get("name") or "").strip() or "Черновик")[:48]
    text_v = str(raw.get("text") or "")[:4000]
    manual_thread_id = str(raw.get("manualThreadId") or "")[:64]
    photo_data_url = str(raw.get("photoDataUrl") or "")
    if len(photo_data_url) > 2 * 1024 * 1024:
        photo_data_url = ""
    delete_window = max(0, min(600, int(raw.get("deleteWindowSec") or 0)))
    enabled = bool(raw.get("enabled"))
    is_active = bool(raw.get("isActive"))
    updated_at = int(raw.get("updatedAt") or 0)
    if updated_at <= 0:
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)
    buttons = raw.get("buttons")
    if not isinstance(buttons, list):
        buttons = []
    clean_rows: list[list[dict]] = []
    for row in buttons[:8]:
        if not isinstance(row, list):
            continue
        clean_btns: list[dict] = []
        for btn in row[:6]:
            if not isinstance(btn, dict):
                continue
            text_btn = str(btn.get("text") or "").strip()[:64]
            if not text_btn:
                continue
            url_v = str(btn.get("url") or "").strip()[:512]
            wu_v = str(btn.get("web_app_url") or "").strip()[:512]
            cb_v = str(btn.get("callback_data") or "").strip()[:64]
            item: dict = {"text": text_btn}
            if url_v:
                item["url"] = url_v
            elif wu_v:
                item["web_app_url"] = wu_v
            elif cb_v:
                item["callback_data"] = cb_v
            clean_btns.append(item)
        if clean_btns:
            clean_rows.append(clean_btns)
    return {
        "id": rid,
        "name": name,
        "enabled": enabled,
        "text": text_v,
        "deleteWindowSec": delete_window,
        "buttons": clean_rows,
        "manualThreadId": manual_thread_id,
        "photoDataUrl": photo_data_url,
        "isActive": is_active,
        "updatedAt": updated_at,
    }


@router.get("/chat/{chat_id}/channel-rule-drafts")
async def api_chat_channel_rule_drafts_get(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    q = text(
        """
        SELECT draft_id, name, enabled, text_value, delete_window_sec, buttons_json,
               manual_thread_id, photo_data_url, is_active, updated_at_ms
        FROM channel_rule_drafts
        WHERE owner_user_id = :uid AND discussion_chat_id = :cid
        ORDER BY updated_at_ms DESC, draft_id ASC
        LIMIT 20
        """
    )
    res = await session.execute(q, {"uid": int(user_id), "cid": int(chat_id)})
    out: list[dict] = []
    for r in res.mappings().all():
        try:
            btns = json.loads(str(r.get("buttons_json") or "[]"))
            if not isinstance(btns, list):
                btns = []
        except Exception:
            btns = []
        out.append(
            {
                "id": str(r.get("draft_id") or ""),
                "name": str(r.get("name") or "Черновик"),
                "enabled": bool(r.get("enabled")),
                "text": str(r.get("text_value") or ""),
                "deleteWindowSec": int(r.get("delete_window_sec") or 0),
                "buttons": btns,
                "manualThreadId": str(r.get("manual_thread_id") or ""),
                "photoDataUrl": str(r.get("photo_data_url") or ""),
                "isActive": bool(r.get("is_active")),
                "updatedAt": int(r.get("updated_at_ms") or 0),
            }
        )
    return {"drafts": out}


@router.post("/chat/{chat_id}/channel-rule-drafts")
async def api_chat_channel_rule_drafts_set(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    raw = body.get("drafts")
    incoming_raw = raw if isinstance(raw, list) else []
    incoming = [_sanitize_channel_rule_draft(d) for d in incoming_raw[:20] if isinstance(d, dict)]
    # Read current server state and merge by draft id using "newer updatedAt wins".
    sel = text(
        """
        SELECT draft_id, name, enabled, text_value, delete_window_sec, buttons_json,
               manual_thread_id, photo_data_url, is_active, updated_at_ms
        FROM channel_rule_drafts
        WHERE owner_user_id = :uid AND discussion_chat_id = :cid
        """
    )
    res = await session.execute(sel, {"uid": int(user_id), "cid": int(chat_id)})
    merged_by_id: dict[str, dict] = {}
    for r in res.mappings().all():
        try:
            btns = json.loads(str(r.get("buttons_json") or "[]"))
            if not isinstance(btns, list):
                btns = []
        except Exception:
            btns = []
        d = {
            "id": str(r.get("draft_id") or ""),
            "name": str(r.get("name") or "Черновик"),
            "enabled": bool(r.get("enabled")),
            "text": str(r.get("text_value") or ""),
            "deleteWindowSec": int(r.get("delete_window_sec") or 0),
            "buttons": btns,
            "manualThreadId": str(r.get("manual_thread_id") or ""),
            "photoDataUrl": str(r.get("photo_data_url") or ""),
            "isActive": bool(r.get("is_active")),
            "updatedAt": int(r.get("updated_at_ms") or 0),
        }
        if d["id"]:
            merged_by_id[d["id"]] = d
    for d in incoming:
        did = str(d.get("id") or "")
        if not did:
            continue
        prev = merged_by_id.get(did)
        if not prev or int(d.get("updatedAt") or 0) >= int(prev.get("updatedAt") or 0):
            merged_by_id[did] = d
    merged = sorted(merged_by_id.values(), key=lambda x: int(x.get("updatedAt") or 0), reverse=True)[:20]
    # Only one active draft is allowed (newest active wins).
    first_active_seen = False
    for d in merged:
        if bool(d.get("isActive")) and not first_active_seen:
            first_active_seen = True
        else:
            d["isActive"] = False
    await session.execute(
        text("DELETE FROM channel_rule_drafts WHERE owner_user_id = :uid AND discussion_chat_id = :cid"),
        {"uid": int(user_id), "cid": int(chat_id)},
    )
    ins = text(
        """
        INSERT INTO channel_rule_drafts
            (owner_user_id, discussion_chat_id, draft_id, name, enabled, text_value,
             delete_window_sec, buttons_json, manual_thread_id, photo_data_url, is_active, updated_at_ms)
        VALUES
            (:uid, :cid, :draft_id, :name, :enabled, :text_value,
             :delete_window_sec, :buttons_json, :manual_thread_id, :photo_data_url, :is_active, :updated_at_ms)
        """
    )
    for d in merged:
        await session.execute(
            ins,
            {
                "uid": int(user_id),
                "cid": int(chat_id),
                "draft_id": str(d["id"]),
                "name": str(d["name"]),
                "enabled": bool(d["enabled"]),
                "text_value": str(d["text"]),
                "delete_window_sec": int(d["deleteWindowSec"]),
                "buttons_json": json.dumps(d["buttons"], ensure_ascii=False),
                "manual_thread_id": str(d["manualThreadId"]),
                "photo_data_url": str(d["photoDataUrl"]),
                "is_active": bool(d["isActive"]),
                "updated_at_ms": int(d["updatedAt"]),
            },
        )
    await session.commit()
    return {"ok": True, "count": len(merged), "merge": "updatedAt-wins", "drafts": merged}


# ---------- POST /api/chat/:id/clean-deleted ----------
@router.post("/chat/{chat_id}/clean-deleted")
async def api_chat_clean_deleted(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Запустить очистку удалённых аккаунтов для выбранного чата (без выхода из Mini App)."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="BOT_TOKEN not set")

    bot = Bot(token=token)
    try:
        kicked, checked = await clean_deleted_accounts(bot, session, int(chat_id))
        return {"ok": True, "kicked": int(kicked), "checked": int(checked)}
    finally:
        await bot.session.close()


# ---------- POST /api/chat/:id/member-unban ----------
@router.post("/chat/{chat_id}/member-unban")
async def api_chat_member_unban(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    row = await session.get(Chat, int(chat_id))
    if not row or bool(getattr(row, "is_log_chat", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный чат")
    uid = int(body.get("user_id") or 0)
    if uid <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id required")
    if not await tg_unban_chat_member(int(chat_id), uid):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось выполнить разбан в Telegram (права бота или пользователь не в бане).",
        )
    return {"ok": True}


# ---------- POST /api/chat/:id/member-unmute ----------
@router.post("/chat/{chat_id}/member-unmute")
async def api_chat_member_unmute(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    row = await session.get(Chat, int(chat_id))
    if not row or bool(getattr(row, "is_log_chat", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный чат")
    uid = int(body.get("user_id") or 0)
    if uid <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id required")
    if not await tg_restrict_chat_member_unmute(int(chat_id), uid):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось снять ограничения в Telegram (права бота или статус участника).",
        )
    return {"ok": True}


# ---------- PATCH /api/chat/:id/rule ----------
@router.patch("/chat/{chat_id}/rule")
async def api_chat_rule(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Частичное обновление правил чата."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    rule = await get_or_create_rule(session, int(chat_id))
    chat = await session.get(Chat, int(chat_id))
    owner_premium = await _is_chat_owner_premium(session, chat) if chat else False
    allowed = {
        "filter_links", "filter_links_mode", "filter_links_scope", "filter_media_mode", "filter_buttons_mode", "filter_mentions",
        "filter_channel_posts_enabled", "filter_channel_posts_action",
        "welcome_enabled", "welcome_text", "welcome_buttons",
        "welcome_max_per_min", "welcome_silent_on_raid", "welcome_raid_threshold", "welcome_raid_window_minutes", "welcome_every_n_joins",
        "rules_channel_enabled", "rules_channel_text", "rules_channel_buttons",
        "rules_channel_delete_window_sec", "rules_channel_autopost_enabled", "rules_channel_autopost_times",
        "rules_group_enabled", "rules_group_text", "rules_group_buttons",
        "rules_group_autopost_enabled", "rules_group_autopost_times", "rules_group_pin_on_send",
        "rules_group_delete_pin_notice",
        "rules_group_event_on_trigger", "rules_group_event_on_punish",
        "rules_group_event_trigger_every_n", "rules_group_event_punish_every_n",
        "action_mode", "mute_minutes", "newbie_enabled", "newbie_minutes",
        "first_message_captcha_enabled",
        "join_captcha_enabled",
        "join_captcha_ttl_minutes",
        "join_captcha_kind",
        "join_captcha_prefer_dm",
        "all_captcha_minutes",
        "delete_join_messages",
        "delete_left_messages",
        "silence_minutes", "master_anti_spam",
        "antinakrutka_enabled", "antinakrutka_joins_threshold", "antinakrutka_window_minutes",
        "antinakrutka_action", "antinakrutka_restrict_minutes",
        "spam_spike_enabled", "spam_spike_min_deletes", "spam_spike_window_minutes", "spam_spike_notify_managers",
        "use_global_antispam_db",
        "use_global_bad_urls",
        "filter_profanity_enabled", "filter_jobs_enabled", "filter_casino_enabled",
        "filter_ads_enabled", "filter_insults_enabled",
        "filter_racism_enabled", "filter_nazi_enabled", "filter_vulgar_enabled",
        "reputation_enabled",
        "log_enabled",
        "guardian_messages_enabled",
        "guardian_periodic_enabled",
        "guardian_periodic_interval_hours",
        "public_alerts_enabled",
        "public_alerts_every_n",
        "public_alerts_min_interval_sec",
        "public_alerts_style",
        "auto_reports_enabled",
    }
    for key, value in body.items():
        if key in allowed and hasattr(rule, key):
            setattr(rule, key, value)
    if "rules_group_event_on_trigger" in body and hasattr(rule, "rules_group_event_on_trigger"):
        rule.rules_group_event_on_trigger = bool(body.get("rules_group_event_on_trigger"))
    if "rules_group_event_on_punish" in body and hasattr(rule, "rules_group_event_on_punish"):
        rule.rules_group_event_on_punish = bool(body.get("rules_group_event_on_punish"))
    if "rules_group_delete_pin_notice" in body and hasattr(rule, "rules_group_delete_pin_notice"):
        rule.rules_group_delete_pin_notice = bool(body.get("rules_group_delete_pin_notice"))
    if "guardian_messages_enabled" in body and not owner_premium:
        # FREE: выключать такие сообщения нельзя.
        rule.guardian_messages_enabled = True
    if "guardian_periodic_enabled" in body and not owner_premium:
        # FREE: дежурные сообщения в группе всегда включены.
        rule.guardian_periodic_enabled = True
    if "guardian_periodic_interval_hours" in body:
        try:
            v = int(getattr(rule, "guardian_periodic_interval_hours", 24) or 24)
        except (TypeError, ValueError):
            v = 24
        rule.guardian_periodic_interval_hours = max(6, min(168, v))
        if not owner_premium:
            # FREE: фиксированная частота.
            rule.guardian_periodic_interval_hours = 24
    if "join_captcha_ttl_minutes" in body:
        try:
            v = int(getattr(rule, "join_captcha_ttl_minutes", 3) or 3)
        except (TypeError, ValueError):
            v = 3
        rule.join_captcha_ttl_minutes = max(1, min(5, v))
    if "join_captcha_kind" in body:
        k = str(getattr(rule, "join_captcha_kind", "button") or "button").strip().lower()
        rule.join_captcha_kind = k if k in (
            "button",
            "math",
            "emoji",
            "digits",
            "word_send",
            "word_guess",
            "word_emoji",
        ) else "button"
    if "public_alerts_style" in body:
        st = str(getattr(rule, "public_alerts_style", "guard") or "guard").strip().lower()
        if st not in ("soft", "medium", "guard"):
            rule.public_alerts_style = "guard"
    if "filter_links_scope" in body and hasattr(rule, "filter_links_scope"):
        sc = str(body.get("filter_links_scope") or "all").strip().lower()
        rule.filter_links_scope = sc if sc in ("all", "channel_comments_only") else "all"
    if "spam_spike_min_deletes" in body:
        try:
            v = int(body.get("spam_spike_min_deletes"))
        except (TypeError, ValueError):
            v = 5
        rule.spam_spike_min_deletes = max(2, min(200, v))
    if "spam_spike_window_minutes" in body:
        try:
            v = int(body.get("spam_spike_window_minutes"))
        except (TypeError, ValueError):
            v = 35
        rule.spam_spike_window_minutes = max(5, min(720, v))
    am = str(getattr(rule, "action_mode", "") or "").lower()
    if am not in ("delete", "mute", "ban", "observe"):
        rule.action_mode = "delete"
    if "filter_links" in body and "filter_links_mode" not in body and hasattr(rule, "filter_links_mode"):
        rule.filter_links_mode = "forbid" if rule.filter_links else "allow"
    if "filter_channel_posts_action" in body and hasattr(rule, "filter_channel_posts_action"):
        sca = str(getattr(rule, "filter_channel_posts_action", "delete") or "delete").strip().lower()
        rule.filter_channel_posts_action = sca if sca in ("delete", "ban") else "delete"
    if "welcome_text" in body and hasattr(rule, "welcome_text"):
        txt = str(body.get("welcome_text") or "")
        rule.welcome_text = txt[:4000]
    if "welcome_buttons" in body and hasattr(rule, "welcome_buttons_json"):
        wb = body.get("welcome_buttons")
        clean_rows: list[list[dict]] = []
        if isinstance(wb, list):
            for row in wb[:6]:
                if not isinstance(row, list):
                    continue
                clean_btns: list[dict] = []
                for btn in row[:4]:
                    if not isinstance(btn, dict):
                        continue
                    text_v = str(btn.get("text") or "").strip()[:64]
                    if not text_v:
                        continue
                    url_v = str(btn.get("url") or "").strip()[:512]
                    wu_v = str(btn.get("web_app_url") or "").strip()[:512]
                    cb_v = str(btn.get("callback_data") or "").strip()[:64]
                    if url_v:
                        if not (url_v.startswith("http://") or url_v.startswith("https://") or url_v.startswith("tg://")):
                            continue
                        clean_btns.append({"text": text_v, "url": url_v})
                    elif wu_v:
                        if not (wu_v.startswith("http://") or wu_v.startswith("https://")):
                            continue
                        clean_btns.append({"text": text_v, "web_app_url": wu_v})
                    elif cb_v:
                        clean_btns.append({"text": text_v, "callback_data": cb_v})
                if clean_btns:
                    clean_rows.append(clean_btns)
        rule.welcome_buttons_json = json.dumps(clean_rows, ensure_ascii=False)
    if "rules_channel_text" in body and hasattr(rule, "rules_channel_text"):
        txt = str(body.get("rules_channel_text") or "")
        rule.rules_channel_text = txt[:4000]
    if "rules_group_text" in body and hasattr(rule, "rules_group_text"):
        txt = str(body.get("rules_group_text") or "")
        rule.rules_group_text = txt[:4000]
    if "rules_channel_buttons" in body and hasattr(rule, "rules_channel_buttons_json"):
        wb = body.get("rules_channel_buttons")
        clean_rows: list[list[dict]] = []
        if isinstance(wb, list):
            for row in wb[:8]:
                if not isinstance(row, list):
                    continue
                clean_btns: list[dict] = []
                for btn in row[:6]:
                    if not isinstance(btn, dict):
                        continue
                    text_v = str(btn.get("text") or "").strip()[:64]
                    if not text_v:
                        continue
                    url_v = str(btn.get("url") or "").strip()[:512]
                    wu_v = str(btn.get("web_app_url") or "").strip()[:512]
                    cb_v = str(btn.get("callback_data") or "").strip()[:64]
                    if url_v:
                        if not (url_v.startswith("http://") or url_v.startswith("https://") or url_v.startswith("tg://")):
                            continue
                        clean_btns.append({"text": text_v, "url": url_v})
                    elif wu_v:
                        if not (wu_v.startswith("http://") or wu_v.startswith("https://")):
                            continue
                        clean_btns.append({"text": text_v, "web_app_url": wu_v})
                    elif cb_v:
                        clean_btns.append({"text": text_v, "callback_data": cb_v})
                if clean_btns:
                    clean_rows.append(clean_btns)
        rule.rules_channel_buttons_json = json.dumps(clean_rows, ensure_ascii=False)
    if "rules_group_buttons" in body and hasattr(rule, "rules_group_buttons_json"):
        wb = body.get("rules_group_buttons")
        clean_rows: list[list[dict]] = []
        if isinstance(wb, list):
            for row in wb[:8]:
                if not isinstance(row, list):
                    continue
                clean_btns: list[dict] = []
                for btn in row[:6]:
                    if not isinstance(btn, dict):
                        continue
                    text_v = str(btn.get("text") or "").strip()[:64]
                    if not text_v:
                        continue
                    url_v = str(btn.get("url") or "").strip()[:512]
                    wu_v = str(btn.get("web_app_url") or "").strip()[:512]
                    cb_v = str(btn.get("callback_data") or "").strip()[:64]
                    if url_v:
                        if not (url_v.startswith("http://") or url_v.startswith("https://") or url_v.startswith("tg://")):
                            continue
                        clean_btns.append({"text": text_v, "url": url_v})
                    elif wu_v:
                        if not (wu_v.startswith("http://") or wu_v.startswith("https://")):
                            continue
                        clean_btns.append({"text": text_v, "web_app_url": wu_v})
                    elif cb_v:
                        clean_btns.append({"text": text_v, "callback_data": cb_v})
                if clean_btns:
                    clean_rows.append(clean_btns)
        rule.rules_group_buttons_json = json.dumps(clean_rows, ensure_ascii=False)
    if "rules_channel_delete_window_sec" in body and hasattr(rule, "rules_channel_delete_window_sec"):
        try:
            v = int(body.get("rules_channel_delete_window_sec"))
        except (TypeError, ValueError):
            v = 0
        rule.rules_channel_delete_window_sec = max(0, min(600, v))
    if "rules_channel_autopost_times" in body and hasattr(rule, "rules_channel_autopost_times_json"):
        raw = body.get("rules_channel_autopost_times")
        vals: list[str] = []
        if isinstance(raw, list):
            for x in raw[:8]:
                s = str(x or "").strip()
                if re.match(r"^\d{2}:\d{2}$", s):
                    vals.append(s)
        rule.rules_channel_autopost_times_json = json.dumps(vals, ensure_ascii=False)
    if "rules_group_autopost_times" in body and hasattr(rule, "rules_group_autopost_times_json"):
        raw = body.get("rules_group_autopost_times")
        vals: list[str] = []
        if isinstance(raw, list):
            for x in raw[:8]:
                s = str(x or "").strip()
                if re.match(r"^\d{2}:\d{2}$", s):
                    vals.append(s)
        rule.rules_group_autopost_times_json = json.dumps(vals, ensure_ascii=False)
    if "rules_group_event_trigger_every_n" in body and hasattr(rule, "rules_group_event_trigger_every_n"):
        try:
            v = int(body.get("rules_group_event_trigger_every_n"))
        except (TypeError, ValueError):
            v = 1
        rule.rules_group_event_trigger_every_n = max(1, min(500, v))
    if "rules_group_event_punish_every_n" in body and hasattr(rule, "rules_group_event_punish_every_n"):
        try:
            v = int(body.get("rules_group_event_punish_every_n"))
        except (TypeError, ValueError):
            v = 1
        rule.rules_group_event_punish_every_n = max(1, min(500, v))
    if "rules_group_active_draft_id" in body and hasattr(rule, "rules_group_active_draft_id"):
        v = body.get("rules_group_active_draft_id")
        s = (str(v).strip() if v is not None else "")
        rule.rules_group_active_draft_id = s or None
    if "welcome_max_per_min" in body and hasattr(rule, "welcome_max_per_min"):
        try:
            v = int(body.get("welcome_max_per_min"))
        except (TypeError, ValueError):
            v = 0
        rule.welcome_max_per_min = max(0, min(60, v))
    if "welcome_silent_on_raid" in body and hasattr(rule, "welcome_silent_on_raid"):
        rule.welcome_silent_on_raid = bool(body.get("welcome_silent_on_raid"))
    if "welcome_raid_threshold" in body and hasattr(rule, "welcome_raid_threshold"):
        try:
            v = int(body.get("welcome_raid_threshold"))
        except (TypeError, ValueError):
            v = 8
        rule.welcome_raid_threshold = max(2, min(200, v))
    if "welcome_raid_window_minutes" in body and hasattr(rule, "welcome_raid_window_minutes"):
        try:
            v = int(body.get("welcome_raid_window_minutes"))
        except (TypeError, ValueError):
            v = 2
        rule.welcome_raid_window_minutes = max(1, min(60, v))
    if "welcome_every_n_joins" in body and hasattr(rule, "welcome_every_n_joins"):
        try:
            v = int(body.get("welcome_every_n_joins"))
        except (TypeError, ValueError):
            v = 1
        rule.welcome_every_n_joins = max(1, min(500, v))
    fm = str(getattr(rule, "filter_links_mode", "forbid") or "").strip().lower()
    if fm not in _LINK_FILTER_MODES:
        fm = "forbid"
        rule.filter_links_mode = "forbid"
    if hasattr(rule, "filter_links"):
        rule.filter_links = fm != "allow"
    aa = (getattr(rule, "antinakrutka_action", None) or "alert").strip().lower()
    if aa not in ("alert", "alert_restrict"):
        rule.antinakrutka_action = "alert"
    await session.commit()
    await session.refresh(rule)
    stopwords_count = await count_stopwords(session, int(chat_id))
    return {"rule": _rule_to_dict(rule, stopwords_count)}


def _rules_reply_markup_from_json(raw_json: str | None) -> dict | None:
    if not raw_json:
        return None
    try:
        rows = json.loads(raw_json)
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    inline_keyboard: list[list[dict]] = []
    for row in rows[:8]:
        if not isinstance(row, list):
            continue
        out_row: list[dict] = []
        for btn in row[:6]:
            if not isinstance(btn, dict):
                continue
            text_v = str(btn.get("text") or "").strip()[:64]
            if not text_v:
                continue
            url_v = str(btn.get("url") or "").strip()[:512]
            wu_v = str(btn.get("web_app_url") or "").strip()[:512]
            cb_v = str(btn.get("callback_data") or "").strip()[:64]
            if url_v:
                out_row.append({"text": text_v, "url": url_v})
            elif wu_v:
                out_row.append({"text": text_v, "web_app": {"url": wu_v}})
            elif cb_v:
                out_row.append({"text": text_v, "callback_data": cb_v})
        if out_row:
            inline_keyboard.append(out_row)
    if not inline_keyboard:
        return None
    return {"inline_keyboard": inline_keyboard}


@router.post("/chat/{chat_id}/rules/send")
async def api_chat_rules_send_now(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    row = await session.get(Chat, int(chat_id))
    if not row or bool(getattr(row, "is_log_chat", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный чат")
    rule = await get_or_create_rule(session, int(chat_id))
    target = str(body.get("target") or "group").strip().lower()
    pin_message = bool(body.get("pin"))
    delete_pin_notice = bool(
        body.get("delete_pin_notice", getattr(rule, "rules_group_delete_pin_notice", False))
    )
    thread_id = int(body.get("message_thread_id") or 0)
    if target not in ("group", "channel_comments"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target должен быть group или channel_comments")
    async def _send_with_optional_photo(
        dest_chat_id: int,
        text: str,
        markup_dict: dict | None,
        photo_rel: str,
        photo_file_id: str,
        *,
        message_thread_id: int | None = None,
    ) -> dict | None:
        if not photo_rel and not photo_file_id:
            return await tg_send_message(
                int(dest_chat_id),
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=markup_dict,
                message_thread_id=message_thread_id,
            )
        fp = None
        if photo_rel:
            pp = (_rules_media_root() / photo_rel).resolve()
            root = _rules_media_root().resolve()
            if (root in pp.parents or pp == root) and pp.exists() and pp.is_file():
                fp = pp
        if not photo_file_id and fp is None:
            return await tg_send_message(
                int(dest_chat_id),
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=markup_dict,
                message_thread_id=message_thread_id,
            )
        token = (os.getenv("BOT_TOKEN") or "").strip()
        if not token:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="BOT_TOKEN not set")
        rm = InlineKeyboardMarkup.model_validate(markup_dict) if markup_dict else None
        bot = Bot(token=token)
        try:
            def _source():
                return photo_file_id if photo_file_id else FSInputFile(str(fp))
            # Try single message (photo + caption + buttons)
            msg = await bot.send_photo(
                chat_id=int(dest_chat_id),
                photo=_source(),
                caption=str(text or ""),
                parse_mode="HTML",
                reply_markup=rm,
                message_thread_id=int(message_thread_id) if message_thread_id and int(message_thread_id) > 0 else None,
            )
            return {"message_id": int(getattr(msg, "message_id", 0) or 0)}
        except Exception:
            # Fallback for Telegram caption/format limits: photo first, text second.
            await bot.send_photo(
                chat_id=int(dest_chat_id),
                photo=_source(),
                message_thread_id=int(message_thread_id) if message_thread_id and int(message_thread_id) > 0 else None,
            )
            msg2 = await bot.send_message(
                chat_id=int(dest_chat_id),
                text=str(text or "")[:4096],
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=rm,
                message_thread_id=int(message_thread_id) if message_thread_id and int(message_thread_id) > 0 else None,
            )
            return {"message_id": int(getattr(msg2, "message_id", 0) or 0)}
        finally:
            await bot.session.close()
    if target == "group":
        text = str(getattr(rule, "rules_group_text", "") or "").strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текст правил для группы пуст")
        markup = _rules_reply_markup_from_json(getattr(rule, "rules_group_buttons_json", None))
        rel = str(getattr(rule, "rules_group_photo_path", "") or "").strip()
        fid = str(getattr(rule, "rules_group_photo_file_id", "") or "").strip()
        sent = await _send_with_optional_photo(int(chat_id), text, markup, rel, fid)
    else:
        text = str(getattr(rule, "rules_channel_text", "") or "").strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текст правил для комментариев пуст")
        if thread_id <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message_thread_id обязателен для channel_comments")
        markup = _rules_reply_markup_from_json(getattr(rule, "rules_channel_buttons_json", None))
        rel = str(getattr(rule, "rules_channel_photo_path", "") or "").strip()
        fid = str(getattr(rule, "rules_channel_photo_file_id", "") or "").strip()
        sent = await _send_with_optional_photo(int(chat_id), text, markup, rel, fid, message_thread_id=int(thread_id))
    if not sent:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить правила в Telegram")
    message_id = int((sent or {}).get("message_id") or 0)
    if pin_message and message_id > 0 and target == "group":
        await tg_pin_chat_message(int(chat_id), message_id, disable_notification=True)
        if delete_pin_notice:
            await tg_try_delete_pin_service_messages(int(chat_id), int(message_id))
    return {"ok": True, "message_id": message_id}


# ---------- POST /api/chat/:id/reports-chat ----------
@router.post("/chat/{chat_id}/reports-chat")
async def api_set_reports_chat(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Выбрать чат отчётов для защищаемой группы прямо из Mini App (без deep link).
    Body: { "log_chat_id": number | null }  — null снимает привязку.
    """
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    log_chat_id = body.get("log_chat_id")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if log_chat_id is not None:
        log_chat_id = int(log_chat_id)
        ok2 = await user_can_access_chat(session, user_id, log_chat_id)
        if not ok2:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to target chat")
        log_chat_row = await session.get(Chat, log_chat_id)
        if log_chat_row:
            log_chat_row.is_log_chat = True
        chat.log_chat_id = log_chat_id
    else:
        chat.log_chat_id = None
    await session.commit()
    await session.refresh(chat)
    log_title = None
    if chat.log_chat_id:
        lr = await session.get(Chat, int(chat.log_chat_id))
        log_title = (lr.title or "").strip() if lr else str(chat.log_chat_id)
    return {"log_chat_id": chat.log_chat_id, "log_chat_title": log_title}


# ---------- GET /api/chat/:id/stopwords (список уже в GET /api/chat/:id)
# ---------- GET /api/chat/:id/reputation ----------
@router.get("/chat/{chat_id}/reputation")
async def api_chat_reputation(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    rule = await get_or_create_rule(session, int(chat_id))
    words_q = await session.execute(
        text(
            """
            SELECT word
            FROM chat_reputation_words
            WHERE chat_id = :cid
            ORDER BY word ASC
            """
        ),
        {"cid": int(chat_id)},
    )
    custom_words = [str(x or "") for x in words_q.scalars().all() if str(x or "").strip()]
    top_q = await session.execute(
        text(
            """
            SELECT user_id, score
            FROM chat_reputation_scores
            WHERE chat_id = :cid
            ORDER BY score DESC, updated_at DESC
            LIMIT :lim
            """
        ),
        {"cid": int(chat_id), "lim": REPUTATION_TOP_LIMIT},
    )
    top_rows = top_q.all()
    top_ids = [int(r[0]) for r in top_rows if int(r[0] or 0) > 0]
    usernames_by_id: dict[int, str] = {}
    if top_ids:
        uq = await session.execute(
            select(User.telegram_id, User.username).where(User.telegram_id.in_(top_ids))
        )
        for tg_id, uname in uq.all():
            usernames_by_id[int(tg_id or 0)] = str(uname or "")
    top = [
        {
            "user_id": int(r[0]),
            "score": int(r[1] or 0),
            "username": usernames_by_id.get(int(r[0] or 0), ""),
        }
        for r in top_rows
    ]

    me_row = await session.execute(
        text(
            """
            SELECT score
            FROM chat_reputation_scores
            WHERE chat_id = :cid AND user_id = :uid
            LIMIT 1
            """
        ),
        {"cid": int(chat_id), "uid": int(user_id)},
    )
    my_score = int(me_row.scalar_one_or_none() or 0)
    return {
        "enabled": bool(getattr(rule, "reputation_enabled", False)),
        "default_words": list(REPUTATION_DEFAULT_WORDS),
        "custom_words": custom_words,
        "top": top,
        "my_score": my_score,
    }


# ---------- POST /api/chat/:id/reputation/words ----------
@router.post("/chat/{chat_id}/reputation/words")
async def api_add_reputation_word(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    raw = body.get("word")
    word = _normalize_reputation_word(raw)
    if not word:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="word required")
    if len(word) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="word too short")
    if word in REPUTATION_DEFAULT_WORDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="already in defaults")
    count_q = await session.execute(
        text("SELECT COUNT(*) FROM chat_reputation_words WHERE chat_id = :cid"),
        {"cid": int(chat_id)},
    )
    if int(count_q.scalar_one() or 0) >= REPUTATION_CUSTOM_WORDS_MAX:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit reached")
    await session.execute(
        text(
            """
            INSERT INTO chat_reputation_words (chat_id, word)
            VALUES (:cid, :word)
            ON CONFLICT (chat_id, word) DO NOTHING
            """
        ),
        {"cid": int(chat_id), "word": word},
    )
    await session.commit()
    return {"ok": True}


# ---------- DELETE /api/chat/:id/reputation/words ----------
@router.delete("/chat/{chat_id}/reputation/words")
async def api_delete_reputation_word(
    chat_id: int,
    word: str,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    norm = _normalize_reputation_word(word)
    if not norm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="word required")
    await session.execute(
        text("DELETE FROM chat_reputation_words WHERE chat_id = :cid AND word = :word"),
        {"cid": int(chat_id), "word": norm},
    )
    await session.commit()
    return {"ok": True}


# ---------- POST /api/chat/:id/stopwords ----------
@router.post("/chat/{chat_id}/stopwords")
async def api_add_stopword(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Добавить стоп-слово или фразу (пробелы сохраняются). Body: { "word": "не звоните" } или { "words": ["a", "b c"] }."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    word = (body.get("word") or "").strip()
    words = body.get("words")
    if word:
        words = [word] if not words else list(words) + [word]
    elif not words:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need 'word' or 'words'")
    else:
        words = list(words) if isinstance(words, (list, tuple)) else [str(words)]
    added = []
    for w in words:
        if (w or "").strip():
            if await add_stopword(session, int(chat_id), w):
                added.append((w or "").strip().lower())
    return {"added": added, "stopwords": await list_stopwords(session, int(chat_id))}


# ---------- DELETE /api/chat/:id/stopwords ----------
@router.delete("/chat/{chat_id}/stopwords")
async def api_delete_stopword(
    chat_id: int,
    word: str,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Удалить стоп-слово. Query: ?word=казино"""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if not (word or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need query param 'word'")
    await delete_stopword(session, int(chat_id), word)
    return {"stopwords": await list_stopwords(session, int(chat_id))}


# ---------- Whitelist ссылок / пользователей (дублирует логику /wl_* в Mini App) ----------
@router.post("/chat/{chat_id}/whitelist/domains")
async def api_whitelist_domain_add(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache
    from app.handlers.whitelist import normalize_trusted_link_pattern, is_valid_trusted_pattern

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    raw_in = str(body.get("domain") or "")
    domain = normalize_trusted_link_pattern(raw_in)
    if not domain or not is_valid_trusted_pattern(raw_in):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректная запись. Примеры: vk.com, youtube.com, t.me/your_channel",
        )
    max_d, _max_u = await _whitelist_limits_for_chat(session, chat)
    cnt_q = await session.execute(select(func.count()).select_from(WhitelistDomain).where(WhitelistDomain.chat_id == int(chat_id)))
    if int(cnt_q.scalar_one() or 0) >= max_d:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Лимит доверенных ссылок для этого чата: {max_d}. С Premium у владельца — до 100.",
        )
    session.add(WhitelistDomain(chat_id=int(chat_id), domain=domain))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Домен уже в списке")
    invalidate_whitelist_cache(int(chat_id))
    return await _whitelist_lists_for_chat(session, int(chat_id))


@router.delete("/chat/{chat_id}/whitelist/domains")
async def api_whitelist_domain_delete(
    chat_id: int,
    domain: str,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache
    from app.handlers.whitelist import normalize_trusted_link_pattern

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    dom = normalize_trusted_link_pattern(domain or "")
    if not dom:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need query param domain")
    await session.execute(delete(WhitelistDomain).where(WhitelistDomain.chat_id == int(chat_id), WhitelistDomain.domain == dom))
    await session.commit()
    invalidate_whitelist_cache(int(chat_id))
    return await _whitelist_lists_for_chat(session, int(chat_id))


@router.post("/chat/{chat_id}/whitelist/users")
async def api_whitelist_user_add(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    raw_ref = body.get("user_ref")
    if raw_ref is None:
        raw_ref = body.get("user_id")
    if raw_ref is None:
        raw_ref = body.get("username")
    ref = str(raw_ref or "").strip()
    target_uid = 0
    if ref:
        if ref.lstrip("@").isdigit():
            try:
                target_uid = int(ref.lstrip("@"))
            except (TypeError, ValueError):
                target_uid = 0
        else:
            uname = _norm_username(ref)
            if uname:
                if pii_storage_enabled():
                    async with PiiAsyncSessionLocal() as pii_sess:
                        tid = await pii_find_telegram_id_by_username_lower(pii_sess, uname)
                    target_uid = int(tid or 0)
                else:
                    urow = (
                        await session.execute(select(User.telegram_id).where(func.lower(User.username) == uname).limit(1))
                    ).first()
                    target_uid = int(urow[0] or 0) if urow else 0
    if target_uid <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось распознать пользователя. Укажите Telegram ID или @username (пользователь должен хотя бы раз запустить Guard).",
        )
    _max_d, max_u = await _whitelist_limits_for_chat(session, chat)
    cnt_q = await session.execute(select(func.count()).select_from(WhitelistUser).where(WhitelistUser.chat_id == int(chat_id)))
    if int(cnt_q.scalar_one() or 0) >= max_u:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Лимит доверенных пользователей: {max_u}. Premium у владельца — до 100.",
        )
    session.add(WhitelistUser(chat_id=int(chat_id), user_id=target_uid))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь уже в списке")
    invalidate_whitelist_cache(int(chat_id))
    return await _whitelist_lists_for_chat(session, int(chat_id))


@router.delete("/chat/{chat_id}/whitelist/users")
async def api_whitelist_user_delete(
    chat_id: int,
    target_user_id: int = Query(..., description="Telegram user_id из списка"),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if target_user_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный target_user_id")
    await session.execute(
        delete(WhitelistUser).where(WhitelistUser.chat_id == int(chat_id), WhitelistUser.user_id == int(target_user_id))
    )
    await session.commit()
    invalidate_whitelist_cache(int(chat_id))
    return await _whitelist_lists_for_chat(session, int(chat_id))


@router.post("/chat/{chat_id}/whitelist/sender-chats")
async def api_whitelist_sender_chat_add(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    raw_ref = str(body.get("channel") or body.get("username") or "").strip().lstrip("@").lower()
    if not raw_ref:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужен @username канала")
    if not raw_ref.replace("_", "").isalnum() or len(raw_ref) < 5 or len(raw_ref) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный @username канала")
    session.add(WhitelistSenderChat(chat_id=int(chat_id), channel_username=raw_ref))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Канал уже в доверенных")
    invalidate_whitelist_cache(int(chat_id))
    return await _whitelist_lists_for_chat(session, int(chat_id))


@router.delete("/chat/{chat_id}/whitelist/sender-chats")
async def api_whitelist_sender_chat_delete(
    chat_id: int,
    channel_username: str = Query(..., description="@username канала"),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    uname = str(channel_username or "").strip().lstrip("@").lower()
    if not uname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный channel_username")
    await session.execute(
        delete(WhitelistSenderChat).where(
            WhitelistSenderChat.chat_id == int(chat_id),
            WhitelistSenderChat.channel_username == uname,
        )
    )
    await session.commit()
    invalidate_whitelist_cache(int(chat_id))
    return await _whitelist_lists_for_chat(session, int(chat_id))


@router.post("/chat/{chat_id}/link-blacklist")
async def api_link_blacklist_add(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache
    from app.handlers.whitelist import normalize_trusted_link_pattern, is_valid_trusted_pattern

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    max_bl = await _link_blacklist_max_for_chat(session, chat)
    if max_bl <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Чёрный список ссылок доступен только при Premium у владельца чата.",
        )
    raw_in = str(body.get("pattern") or body.get("domain") or "")
    pat = normalize_trusted_link_pattern(raw_in)
    if not pat or not is_valid_trusted_pattern(raw_in):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный фрагмент. Примеры: spam.com, t.me/spam_channel",
        )
    cnt_q = await session.execute(select(func.count()).select_from(LinkBlacklist).where(LinkBlacklist.chat_id == int(chat_id)))
    if int(cnt_q.scalar_one() or 0) >= max_bl:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Лимит чёрного списка: {max_bl} записей.",
        )
    session.add(LinkBlacklist(chat_id=int(chat_id), pattern=pat))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Уже в списке")
    invalidate_whitelist_cache(int(chat_id))
    return {"link_blacklist": await _link_blacklist_patterns_list(session, int(chat_id))}


@router.delete("/chat/{chat_id}/link-blacklist")
async def api_link_blacklist_delete(
    chat_id: int,
    pattern: str,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.moderation import invalidate_whitelist_cache
    from app.handlers.whitelist import normalize_trusted_link_pattern

    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    pat = normalize_trusted_link_pattern(pattern or "")
    if not pat:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need query param pattern")
    await session.execute(delete(LinkBlacklist).where(LinkBlacklist.chat_id == int(chat_id), LinkBlacklist.pattern == pat))
    await session.commit()
    invalidate_whitelist_cache(int(chat_id))
    return {"link_blacklist": await _link_blacklist_patterns_list(session, int(chat_id))}


# ---------- GET /api/connect/pending ----------
@router.get("/connect/pending")
async def api_connect_pending(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Чаты, добавленные в бота, но ещё не подключённые (для кнопки «подключить»)."""
    pending = await get_pending_chats(session, user_id)
    return {
        "chats": [
            {
                "id": c.id,
                "title": (c.title or "").strip() or str(c.id),
                "chat_kind": str(getattr(c, "chat_kind", "") or "group").strip().lower() or "group",
                "is_shared": int(getattr(c, "owner_user_id", 0) or 0) != int(user_id),
            }
            for c in pending[:100]
        ],
    }

@router.post("/connect/pending/activate")
async def api_connect_activate_pending(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """
    Активировать чаты из pending, где бот уже администратор.
    Полезно, если Telegram не прислал/пропустил событие my_chat_member.
    """
    from app.services.telegram_bot_api import tg_bot_is_admin_in_chat

    pending = await get_pending_chats(session, user_id)
    connected = 0
    skipped = 0
    for c in pending:
        cid = int(c.id)
        try:
            if not await tg_bot_is_admin_in_chat(cid):
                skipped += 1
                continue
            c.is_active = True
            await get_or_create_rule(session, cid)
            connected += 1
        except Exception:
            skipped += 1
    await session.commit()
    return {"ok": True, "connected": connected, "skipped": skipped}

@router.post("/connect/pending/cleanup")
async def api_connect_cleanup_pending(
    body: dict | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """
    Удалить из pending зависшие записи старше N часов (по умолчанию 24).
    Нужен как «сброс», если пользователь передумал/отменил выдачу прав.
    """
    hours = 24
    if body and body.get("hours") is not None:
        try:
            hours = int(body.get("hours"))
        except Exception:
            hours = 24
    hours = max(1, min(168, hours))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    res = await session.execute(
        select(Chat).where(
            Chat.owner_user_id == user_id,
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == False,  # noqa: E712
            Chat.created_at < cutoff,
        )
    )
    rows = list(res.scalars().all())
    removed = 0
    for row in rows:
        await session.delete(row)
        removed += 1
    await session.commit()
    return {"ok": True, "removed": removed, "hours": hours}


@router.post("/connect/pending/clear-all")
async def api_connect_clear_all_pending(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Удалить все записи «ожидающих» чатов пользователя (is_active=False, не лог-чаты)."""
    res = await session.execute(
        select(Chat).where(
            Chat.owner_user_id == user_id,
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == False,  # noqa: E712
        )
    )
    rows = list(res.scalars().all())
    for row in rows:
        await session.delete(row)
    await session.commit()
    return {"ok": True, "removed": len(rows)}


# ---------- GET /api/billing ----------
@router.get("/billing")
async def api_billing(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Тариф и лимиты."""
    user = await get_or_create_user(session, user_id)
    chats = await get_managed_chats(session, user_id)
    can_add, current_count, limit = await can_add_chat(session, user_id)
    can_add_channel_more, _channels_cur, _channels_limit = await can_add_channel(session, user_id)
    groups_count, channels_count = await count_managed_chats_by_kind(session, user_id)
    now = datetime.now(timezone.utc)
    is_premium = _is_user_premium_now(user, now)
    groups_limit = int(effective_group_limit(user, user_id))
    channels_limit = int(effective_channel_limit(user, user_id))
    return {
        "tariff": user.tariff or "free",
        "is_premium": is_premium,
        "chat_limit": limit,
        "chats_count": len(chats),
        "chats_count_total": len(chats),
        "can_add_more": can_add,
        "group_limit": groups_limit,
        "channel_limit": channels_limit,
        "groups_limit": groups_limit,
        "channels_limit": channels_limit,
        "groups_count": int(groups_count),
        "channels_count": int(channels_count),
        "groups_usage_progress": round((int(groups_count) / max(1, int(groups_limit or 1))) * 100, 2),
        "channels_usage_progress": round((int(channels_count) / max(1, int(channels_limit or 1))) * 100, 2),
        "can_add_more_groups": bool(can_add),
        "can_add_more_channels": bool(can_add_channel_more),
        "subscription_until": _format_dt(user.subscription_until),
        "test_tariff_payment_visible": int(user_id) in _test_tariff_payment_telegram_ids(),
        "test_tariff_payment_env_configured": len(_test_tariff_payment_telegram_ids()) > 0,
    }


@router.get("/billing/token-packs")
async def api_billing_token_packs():
    """Публичный прайс пакетов ⚡ (₽) для экрана покупки."""
    from app.services.token_packs import (
        TOKEN_PACK_EXTRA,
        TOKEN_PACK_PRICES_RUB,
        TOKEN_PACK_TAG,
        pack_savings_label_rub,
    )

    items = []
    for tokens in sorted(TOKEN_PACK_PRICES_RUB.keys()):
        t = int(tokens)
        items.append(
            {
                "tokens": t,
                "price_rub": float(TOKEN_PACK_PRICES_RUB[tokens]),
                "discount_label": pack_savings_label_rub(t),
                "tag": (TOKEN_PACK_TAG.get(t) or None),
                "extra": bool(t in TOKEN_PACK_EXTRA),
            }
        )
    return {"items": items}


async def _referral_move_all_bonus_to_aurum(session: AsyncSession, user_id: int) -> dict:
    """Перевод всех партнёрских токенов в AURUM (единый счёт для рассылок)."""
    user = await get_or_create_user(session, user_id)
    bonus = float(getattr(user, "bonus_credits", 0.0) or 0.0)
    if bonus <= 0:
        return {"ok": True, "moved": 0.0}
    moved = round(bonus, 2)
    user.bonus_credits = round(max(0.0, bonus - moved), 2)
    user.aurum_credits = round(float(getattr(user, "aurum_credits", 0.0) or 0.0) + moved, 2)
    session.add(CreditLedger(user_id=int(user.id), delta=-moved, reason="bonus_to_aurum"))
    session.add(CreditLedger(user_id=int(user.id), delta=+moved, reason="bonus_to_aurum_target"))
    await session.commit()
    return {"ok": True, "moved": moved}


@router.get("/referral")
async def api_referral(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(session, user_id)
    username = await _get_bot_username()
    if not username:
        username = "GuardAntiSpam_Bot"
    ref_link = f"https://t.me/{username}?start=ref_{user_id}"
    invited = int(getattr(user, "ref_invited_count", 0) or 0)
    starts = int(getattr(user, "ref_start_count", 0) or 0)
    shares = int(getattr(user, "ref_share_count", 0) or 0)
    paid = int(getattr(user, "ref_paid_count", 0) or 0)
    aurum_balance = float(getattr(user, "aurum_credits", 0.0) or 0.0)
    bonus_balance = float(getattr(user, "bonus_credits", 0.0) or 0.0)
    sub_until = getattr(user, "subscription_until", None)
    now = datetime.now(timezone.utc)
    days_left = 0
    if sub_until:
        if sub_until.tzinfo is None:
            sub_until = sub_until.replace(tzinfo=timezone.utc)
        days_left = max(0, (sub_until.date() - now.date()).days)
    last_months = None
    if user.id:
        pr = await session.execute(
            select(Payment.months).where(
                Payment.user_id == user.id,
                Payment.status == "succeeded",
                Payment.tariff == Tariff.PREMIUM.value,
            ).order_by(Payment.created_at.desc()).limit(1)
        )
        last_months = pr.scalar_one_or_none()
    return {
        "access_label": f"{int(last_months)} мес." if last_months else "без активного периода",
        "days_left": int(days_left),
        "active_until": _format_dt(sub_until),
        "subscription_credits": 0.0,
        "aurum_credits": aurum_balance,
        "bonus_credits": bonus_balance,
        "ref_link": ref_link,
        "invited_count": invited,
        "start_count": starts,
        "share_count": shares,
        "paid_count": paid,
        "level_rates": [{"level": int(l), "percent": int(r * 100)} for l, r in REFERRAL_LEVEL_RATES],
    }


@router.post("/referral/bonus-to-sub")
async def api_referral_bonus_to_sub(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Совместимость: раньше «в подписку», теперь то же, что bonus-to-aurum."""
    return await _referral_move_all_bonus_to_aurum(session, user_id)


@router.post("/referral/bonus-to-aurum")
async def api_referral_bonus_to_aurum(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    return await _referral_move_all_bonus_to_aurum(session, user_id)


@router.post("/referral/share-hit")
async def api_referral_share_hit(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(session, user_id)
    user.ref_share_count = int(getattr(user, "ref_share_count", 0) or 0) + 1
    session.add(ReferralShareHit(user_id=int(user.id)))
    session.add(user)
    await session.commit()
    return {"ok": True}


@router.get("/referral/payouts")
async def api_referral_payouts(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(session, user_id)
    fin = await _partner_financials(session, user)
    q = await session.execute(
        select(PartnerPayoutRequest).where(
            PartnerPayoutRequest.user_id == int(user.id)
        ).order_by(PartnerPayoutRequest.created_at.desc()).limit(50)
    )
    items = []
    for row in q.scalars().all():
        items.append({
            "id": int(row.id),
            "amount_rub": float(row.amount_rub or 0.0),
            "method": str(row.method or ""),
            "requisites": str(row.requisites or ""),
            "status": str(row.status or ""),
            "risk_flag": bool(row.risk_flag),
            "risk_note": str(row.risk_note or ""),
            "admin_note": str(row.admin_note or ""),
            "created_at": _format_dt(row.created_at),
        })
    commissions = []
    try:
        comm_q = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.owner_user_id == int(user.id)
            ).order_by(PartnerCommission.created_at.desc()).limit(50)
        )
        for c in comm_q.scalars().all():
            commissions.append({
                "id": int(c.id),
                "level": int(c.level or 0),
                "rate": float(c.rate or 0.0),
                "sales_amount_rub": float(c.sales_amount_rub or 0.0),
                "reward_amount_rub": float(c.reward_amount_rub or 0.0),
                "status": str(c.status or ""),
                "available_at": _format_dt(c.available_at),
                "created_at": _format_dt(c.created_at),
            })
    except Exception:
        commissions = []
    return {
        **fin,
        "min_payout_rub": _PARTNER_PAYOUT_MIN_RUB,
        "payout_weekday": 0,
        "items": items,
        "commissions": commissions,
    }


@router.post("/referral/payouts/request")
async def api_referral_payouts_request(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(session, user_id)
    amount_rub = float(body.get("amount_rub") or 0.0)
    method = str(body.get("method") or "sbp").strip().lower()[:32] or "sbp"
    requisites = str(body.get("requisites") or "").strip()[:255]
    full_name = str(body.get("full_name") or "").strip()[:255] or None
    is_owner_fast = str(getattr(user, "username", "") or "").lower() == "pastukh_viscera"
    if amount_rub < _PARTNER_PAYOUT_MIN_RUB and not is_owner_fast:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Минимальная сумма вывода {_PARTNER_PAYOUT_MIN_RUB:.0f} ₽")
    if not requisites:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите реквизиты для выплаты")
    fin = await _partner_financials(session, user)
    if amount_rub > fin["available_rub"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недостаточно доступного баланса")
    risk_flag, risk_note = _is_suspicious_payout(amount_rub, requisites)
    dup_flag, dup_note = await _partner_payout_duplicate_requisites(session, int(user.id), requisites)
    if dup_flag:
        risk_flag = True
        risk_note = ((risk_note + " · ") if risk_note else "") + dup_note
    status_value = "frozen" if risk_flag else "new"
    req = PartnerPayoutRequest(
        user_id=int(user.id),
        amount_rub=round(amount_rub, 2),
        method=method,
        requisites=requisites,
        full_name=full_name,
        status=status_value,
        risk_flag=risk_flag,
        risk_note=risk_note or None,
    )
    session.add(req)
    await session.commit()
    try:
        await send_user_dm(
            int(user.telegram_id),
            (
                "📨 Заявка на вывод принята.\n\n"
                f"Сумма: {round(amount_rub, 2):.2f} ₽\n"
                "Статус: на рассмотрении.\n"
                f"Ориентир выплаты: следующий понедельник ({_next_monday_text()}).\n"
                "Мы уведомим вас после обработки."
            ),
        )
    except Exception:
        _log.warning("payout request notify failed for %s", int(user.telegram_id))
    return {"ok": True, "id": int(req.id), "status": status_value}


@router.get("/admin/overview")
async def api_admin_overview(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))

    users_total_q = await session.execute(select(func.count()).select_from(User))
    users_total = int(users_total_q.scalar() or 0)

    log_targets = select(Chat.log_chat_id).where(Chat.log_chat_id.is_not(None))
    chats_total_q = await session.execute(
        select(func.count()).select_from(Chat).where(
            Chat.is_active == True,  # noqa: E712
            Chat.is_log_chat == False,  # noqa: E712
            Chat.id.not_in(log_targets),
        )
    )
    chats_total = int(chats_total_q.scalar() or 0)

    pays_succeeded_q = await session.execute(
        select(func.count()).select_from(Payment).where(Payment.status == "succeeded")
    )
    payments_succeeded = int(pays_succeeded_q.scalar() or 0)

    revenue_total_q = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0.0)).where(Payment.status == "succeeded")
    )
    revenue_total_rub = float(revenue_total_q.scalar() or 0.0)

    referral_paid_q = await session.execute(
        select(func.count()).select_from(User).where(User.referred_by_tg_id.is_not(None), User.ref_paid_count > 0)
    )
    referral_paid_users = int(referral_paid_q.scalar() or 0)

    return {
        "users_total": users_total,
        "chats_total": chats_total,
        "payments_succeeded": payments_succeeded,
        "revenue_total_rub": round(revenue_total_rub, 2),
        "referral_paid_users": referral_paid_users,
    }


@router.get("/admin/insights/summary")
async def api_admin_insights_summary(
    hours: int = Query(24, ge=1, le=168),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    since = datetime.now(timezone.utc) - timedelta(hours=int(hours))

    joins_q = await session.execute(
        select(func.count(NewMember.id), func.count(func.distinct(NewMember.chat_id))).where(
            NewMember.joined_at >= since
        )
    )
    joins_count, joins_chats = joins_q.one_or_none() or (0, 0)

    starts_q = await session.execute(
        select(func.count(User.id)).where(User.first_start_at.is_not(None), User.first_start_at >= since)
    )
    starts_count = int(starts_q.scalar() or 0)

    pays_q = await session.execute(
        select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0.0)).where(
            Payment.status == "succeeded",
            Payment.created_at >= since,
        )
    )
    pays_count, pays_sum = pays_q.one_or_none() or (0, 0.0)

    share_q = await session.execute(
        select(func.count(ReferralShareHit.id)).where(ReferralShareHit.created_at >= since)
    )
    shares_count = int(share_q.scalar() or 0)

    lvl_q = await session.execute(
        select(
            PartnerCommission.level,
            func.count(PartnerCommission.id).label("payments_count"),
            func.coalesce(func.sum(PartnerCommission.sales_amount_rub), 0.0).label("sales_sum"),
            func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0).label("reward_sum"),
        ).where(
            PartnerCommission.created_at >= since
        ).group_by(
            PartnerCommission.level
        ).order_by(
            PartnerCommission.level.asc()
        )
    )
    level_stats = []
    for row in lvl_q.all():
        level_stats.append(
            {
                "level": int(row.level or 0),
                "payments_count": int(row.payments_count or 0),
                "sales_sum_rub": round(float(row.sales_sum or 0.0), 2),
                "reward_sum_rub": round(float(row.reward_sum or 0.0), 2),
            }
        )

    return {
        "window_hours": int(hours),
        "group_joins_count": int(joins_count or 0),
        "group_joins_chats": int(joins_chats or 0),
        "starts_count": starts_count,
        "payments_count": int(pays_count or 0),
        "payments_sum_rub": round(float(pays_sum or 0.0), 2),
        "referral_shares_count": shares_count,
        "referral_levels": level_stats,
    }


@router.get("/admin/message-templates")
async def api_admin_message_templates(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    q = await session.execute(
        select(AdminMessageTemplate).order_by(AdminMessageTemplate.is_custom.asc(), AdminMessageTemplate.id.asc())
    )
    items = [_admin_template_public(x) for x in q.scalars().all()]
    return {"items": items}


@router.get("/admin/message-templates/options")
async def api_admin_message_templates_options(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    return {
        "events": [
            {"id": "manual", "label": "Ручной (только хранение/редактирование)"},
            {"id": "owner_daily_report", "label": "Суточная сводка владельцу"},
            {"id": "window_group_joins", "label": "Вступления в группы (окно)"},
            {"id": "window_starts", "label": "Нажали /start (окно)"},
            {"id": "window_payments", "label": "Оплаты (окно)"},
            {"id": "window_referral_shares", "label": "Шеры рефералки (окно)"},
        ],
        "targets": [
            {"id": "owner_admin", "label": "Владелец/админ в личку"},
        ],
    }


@router.post("/admin/message-templates")
async def api_admin_message_template_create(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    title = str(body.get("title") or "").strip()
    text_body = str(body.get("body_text") or "").strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title required")
    if not text_body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="body_text required")
    key_raw = str(body.get("template_key") or "").strip().lower()
    key = key_raw or _safe_template_key(title)
    i = 2
    while True:
        exists_q = await session.execute(select(AdminMessageTemplate.id).where(AdminMessageTemplate.template_key == key).limit(1))
        if not exists_q.scalar_one_or_none():
            break
        key = f"{_safe_template_key(title)}_{i}"
        i += 1
    row = AdminMessageTemplate(
        template_key=key,
        title=title,
        body_text=text_body,
        enabled=bool(body.get("enabled", True)),
        delay_minutes=int(body.get("delay_minutes")) if body.get("delay_minutes") is not None else None,
        parse_mode=(str(body.get("parse_mode") or "").strip() or None),
        is_custom=True,
        event_key=(str(body.get("event_key") or "manual").strip() or "manual"),
        target_kind=(str(body.get("target_kind") or "owner_admin").strip() or "owner_admin"),
        trigger_hours=max(1, min(168, int(body.get("trigger_hours") or 24))),
        min_count=max(1, int(body.get("min_count") or 1)),
        cooldown_minutes=max(1, int(body.get("cooldown_minutes") or 1440)),
        schedule_time_hm=(str(body.get("schedule_time_hm") or "").strip() or None),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _admin_template_public(row)


@router.patch("/admin/message-templates/{template_id}")
async def api_admin_message_template_patch(
    template_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    row = await session.get(AdminMessageTemplate, int(template_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template not found")
    if "title" in body:
        row.title = str(body.get("title") or "").strip() or row.title
    if "body_text" in body:
        row.body_text = str(body.get("body_text") or "")
    if "enabled" in body:
        row.enabled = bool(body.get("enabled"))
    if "delay_minutes" in body:
        v = body.get("delay_minutes")
        row.delay_minutes = int(v) if v is not None and str(v).strip() != "" else None
    if "parse_mode" in body:
        row.parse_mode = (str(body.get("parse_mode") or "").strip() or None)
    if "event_key" in body:
        row.event_key = (str(body.get("event_key") or "manual").strip() or "manual")
    if "target_kind" in body:
        row.target_kind = (str(body.get("target_kind") or "owner_admin").strip() or "owner_admin")
    if "trigger_hours" in body:
        row.trigger_hours = max(1, min(168, int(body.get("trigger_hours") or 24)))
    if "min_count" in body:
        row.min_count = max(1, int(body.get("min_count") or 1))
    if "cooldown_minutes" in body:
        row.cooldown_minutes = max(1, int(body.get("cooldown_minutes") or 1440))
    if "schedule_time_hm" in body:
        row.schedule_time_hm = (str(body.get("schedule_time_hm") or "").strip() or None)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _admin_template_public(row)


@router.delete("/admin/message-templates/{template_id}")
async def api_admin_message_template_delete(
    template_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    row = await session.get(AdminMessageTemplate, int(template_id))
    if not row:
        return {"ok": True}
    if not bool(getattr(row, "is_custom", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system template cannot be deleted")
    await session.delete(row)
    await session.commit()
    return {"ok": True}


@router.get("/admin/payouts")
async def api_admin_payouts(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    q = await session.execute(
        select(
            PartnerPayoutRequest,
            User.id,
            User.telegram_id,
            User.username,
            User.first_name,
        ).join(User, User.id == PartnerPayoutRequest.user_id).order_by(PartnerPayoutRequest.created_at.desc()).limit(200)
    )
    req_rows = q.all()
    # Кол-во пользователей на одинаковые реквизиты (быстрый антифрод сигнал).
    req_values = [str(r[0].requisites or "").strip() for r in req_rows if str(r[0].requisites or "").strip()]
    duplicates_map: dict[str, int] = {}
    if req_values:
        dup_q = await session.execute(
            select(
                PartnerPayoutRequest.requisites,
                func.count(func.distinct(PartnerPayoutRequest.user_id)).label("users_count"),
            ).where(
                PartnerPayoutRequest.requisites.in_(req_values)
            ).group_by(PartnerPayoutRequest.requisites)
        )
        for row in dup_q.all():
            duplicates_map[str(row.requisites or "").strip()] = int(row.users_count or 0)

    # Финансы по пользователям для отображения "доступно сейчас".
    user_ids = list({int(r[1]) for r in req_rows if r[1]})
    users_map: dict[int, User] = {}
    if user_ids:
        users_q = await session.execute(select(User).where(User.id.in_(user_ids)))
        for u in users_q.scalars().all():
            users_map[int(u.id)] = u
    fin_map: dict[int, dict] = {}
    for uid, u in users_map.items():
        fin_map[uid] = await _partner_financials(session, u)

    items = []
    for row in req_rows:
        req = row[0]
        user_id_int = int(row[1] or 0)
        fin = fin_map.get(user_id_int, {"available_rub": 0.0, "commission_total_rub": 0.0, "reserved_paid_rub": 0.0})
        req_key = str(req.requisites or "").strip()
        req_dup_users = int(duplicates_map.get(req_key, 0))
        items.append({
            "id": int(req.id),
            "status": str(req.status or ""),
            "amount_rub": float(req.amount_rub or 0.0),
            "method": str(req.method or ""),
            "requisites": str(req.requisites or ""),
            "full_name": str(req.full_name or ""),
            "risk_flag": bool(req.risk_flag),
            "risk_note": str(req.risk_note or ""),
            "admin_note": str(req.admin_note or ""),
            "payout_notice_message_id": int(req.payout_notice_message_id or 0) if req.payout_notice_message_id else None,
            "created_at": _format_dt(req.created_at),
            "updated_at": _format_dt(req.updated_at),
            "paid_at": _format_dt(req.updated_at) if str(req.status or "") == "paid" else None,
            "telegram_id": int(row.telegram_id or 0),
            "username": str(row.username or ""),
            "first_name": str(row.first_name or ""),
            "available_rub_now": float(fin.get("available_rub", 0.0) or 0.0),
            "commission_total_rub": float(fin.get("commission_total_rub", 0.0) or 0.0),
            "reserved_paid_rub": float(fin.get("reserved_paid_rub", 0.0) or 0.0),
            "requisites_users_count": req_dup_users,
        })
    return {"items": items}


@router.post("/admin/payouts/{request_id}/status")
async def api_admin_payout_set_status(
    request_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    new_status = str(body.get("status") or "").strip().lower()
    admin_note = str(body.get("admin_note") or "").strip()[:255] or None
    allowed = {"approved", "paid", "rejected", "frozen", "new"}
    if new_status not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый статус")
    req = await session.get(PartnerPayoutRequest, int(request_id))
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    prev_status = str(req.status or "")
    req.status = new_status
    req.admin_note = admin_note
    session.add(req)
    await session.commit()
    # Уведомление пользователю о результате выплаты.
    if new_status == "paid" and prev_status != "paid":
        u = await session.get(User, int(req.user_id))
        tg_id = int(getattr(u, "telegram_id", 0) or 0)
        remaining_rub = 0.0
        if u:
            debit_tokens = round(float(req.amount_rub or 0.0) / PARTNER_TOKEN_RUB_RATE, 2)
            u.bonus_credits = round(max(0.0, float(getattr(u, "bonus_credits", 0.0) or 0.0) - debit_tokens), 2)
            session.add(u)
            await session.commit()
            fin_after = await _partner_financials(session, u)
            remaining_rub = round(float(fin_after.get("available_rub", 0.0) or 0.0), 2)
        if tg_id:
            try:
                partner_url = _partner_webapp_url()
                reply_markup = None
                if partner_url:
                    reply_markup = {
                        "inline_keyboard": [[
                            {
                                "text": "Открыть партнерку",
                                "web_app": {"url": partner_url},
                            }
                        ]]
                    }
                payload = await send_user_dm_with_result(
                    tg_id,
                    (
                        "✅ Выплата одобрена и переведена.\n\n"
                        f"Сумма: {float(req.amount_rub or 0.0):.2f} ₽\n"
                        f"Осталось к выводу: {remaining_rub:.2f} ₽\n\n"
                        "Проверьте поступление средств по вашим реквизитам."
                    ),
                    reply_markup=reply_markup,
                )
                msg_id = int(((payload or {}).get("result") or {}).get("message_id") or 0)
                if msg_id > 0:
                    req.payout_notice_message_id = msg_id
                    session.add(req)
                    await session.commit()
            except Exception:
                _log.warning("payout paid notify failed for %s", tg_id)
    if new_status == "rejected" and prev_status == "paid":
        u = await session.get(User, int(req.user_id))
        tg_id = int(getattr(u, "telegram_id", 0) or 0)
        if u:
            credit_tokens = round(float(req.amount_rub or 0.0) / PARTNER_TOKEN_RUB_RATE, 2)
            u.bonus_credits = round(float(getattr(u, "bonus_credits", 0.0) or 0.0) + credit_tokens, 2)
            session.add(u)
            await session.commit()
        msg_id = int(getattr(req, "payout_notice_message_id", 0) or 0)
        if tg_id and msg_id:
            try:
                await delete_user_dm_message(tg_id, msg_id)
                req.payout_notice_message_id = None
                session.add(req)
                await session.commit()
            except Exception:
                _log.warning("payout notify delete failed for %s", tg_id)
    return {"ok": True, "id": int(req.id), "status": new_status}


@router.get("/admin/referrals/top")
async def api_admin_referrals_top(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    q = await session.execute(
        select(
            User.telegram_id,
            User.username,
            User.first_name,
            User.ref_paid_count,
            User.ref_sales_total,
        ).where(User.referred_by_tg_id.is_not(None)).order_by(User.ref_sales_total.desc()).limit(100)
    )
    items = []
    for row in q.all():
        items.append({
            "telegram_id": int(row.telegram_id or 0),
            "username": str(row.username or ""),
            "first_name": str(row.first_name or ""),
            "ref_paid_count": int(row.ref_paid_count or 0),
            "ref_sales_total": float(row.ref_sales_total or 0.0),
        })
    return {"items": items}


@router.get("/admin/commissions")
async def api_admin_commissions(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    try:
        q = await session.execute(
            select(
                PartnerCommission,
                User.username,
                User.first_name,
            ).join(User, User.id == PartnerCommission.owner_user_id).order_by(PartnerCommission.created_at.desc()).limit(200)
        )
    except Exception:
        return {"items": []}
    items = []
    for row in q.all():
        c = row[0]
        items.append({
            "id": int(c.id),
            "owner_name": str(row.first_name or ""),
            "owner_username": str(row.username or ""),
            "level": int(c.level or 0),
            "rate": float(c.rate or 0.0),
            "sales_amount_rub": float(c.sales_amount_rub or 0.0),
            "reward_amount_rub": float(c.reward_amount_rub or 0.0),
            "status": str(c.status or ""),
            "available_at": _format_dt(c.available_at),
            "created_at": _format_dt(c.created_at),
        })
    return {"items": items}


@router.get("/admin/commissions/summary")
async def api_admin_commissions_summary(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    try:
        pending_q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0)).where(
                PartnerCommission.status == "pending"
            )
        )
        available_q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0)).where(
                PartnerCommission.status == "available"
            )
        )
        paid_q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0)).where(
                PartnerCommission.status == "paid"
            )
        )
    except Exception:
        return {
            "pending_rub": 0.0,
            "available_rub": 0.0,
            "paid_rub": 0.0,
            "reserve_for_next_payout_rub": 0.0,
        }
    pending_rub = float(pending_q.scalar() or 0.0)
    available_rub = float(available_q.scalar() or 0.0)
    paid_rub = float(paid_q.scalar() or 0.0)
    total_partner_balance_q = await session.execute(
        select(func.coalesce(func.sum(User.bonus_credits), 0.0))
    )
    total_partner_balance_rub = float(total_partner_balance_q.scalar() or 0.0) * PARTNER_TOKEN_RUB_RATE
    return {
        "pending_rub": round(pending_rub, 2),
        "available_rub": round(available_rub, 2),
        "paid_rub": round(paid_rub, 2),
        # Отложить к понедельнику: текущий невыплаченный партнерский баланс.
        # После статуса paid уменьшается сразу, т.к. списываются bonus_credits.
        "reserve_for_next_payout_rub": round(max(0.0, total_partner_balance_rub), 2),
    }


@router.get("/admin/users")
async def api_admin_users(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    users_q = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(1000)
    )
    users = users_q.scalars().all()
    if not users:
        return {"items": []}
    now_utc = datetime.now(timezone.utc)
    tg_ids = [int(u.telegram_id) for u in users if getattr(u, "telegram_id", None)]
    user_by_tg: dict[int, User] = {
        int(getattr(u, "telegram_id", 0) or 0): u
        for u in users
        if int(getattr(u, "telegram_id", 0) or 0) > 0
    }
    chat_counts_map: dict[int, int] = {}
    global_antispam_ids: set[int] = set()
    delegated_counts_map: dict[int, int] = {}
    anti_url_enabled_counts_map: dict[int, int] = {}
    promo_by_user: dict[int, dict] = {}
    joins_24h_by_owner: dict[int, int] = {}
    joins_30d_by_owner: dict[int, int] = {}
    join_report_periods_by_owner: dict[int, list[str]] = {}
    if tg_ids:
        cc_q = await session.execute(
            select(Chat.owner_user_id, func.count(Chat.id)).where(
                Chat.owner_user_id.in_(tg_ids),
                Chat.is_active.is_(True),
                Chat.is_log_chat.is_(False),
            ).group_by(Chat.owner_user_id)
        )
        for row in cc_q.all():
            chat_counts_map[int(row[0])] = int(row[1] or 0)
        mg_q = await session.execute(
            select(ChatManager.user_id, func.count(ChatManager.id)).where(ChatManager.user_id.in_(tg_ids)).group_by(ChatManager.user_id)
        )
        for row in mg_q.all():
            delegated_counts_map[int(row[0])] = int(row[1] or 0)
        anti_url_q = await session.execute(
            select(Chat.owner_user_id, func.count(Chat.id))
            .join(Rule, Rule.chat_id == Chat.id)
            .where(
                Chat.owner_user_id.in_(tg_ids),
                Chat.is_log_chat.is_(False),
                Rule.use_global_bad_urls.is_(True),
            )
            .group_by(Chat.owner_user_id)
        )
        for row in anti_url_q.all():
            anti_url_enabled_counts_map[int(row[0])] = int(row[1] or 0)
        joins_24_q = await session.execute(
            select(Chat.owner_user_id, func.count(NewMember.id))
            .join(Chat, Chat.id == NewMember.chat_id)
            .where(
                Chat.owner_user_id.in_(tg_ids),
                Chat.is_log_chat.is_(False),
                NewMember.joined_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            )
            .group_by(Chat.owner_user_id)
        )
        for row in joins_24_q.all():
            joins_24h_by_owner[int(row[0])] = int(row[1] or 0)
        joins_30_q = await session.execute(
            select(Chat.owner_user_id, func.count(NewMember.id))
            .join(Chat, Chat.id == NewMember.chat_id)
            .where(
                Chat.owner_user_id.in_(tg_ids),
                Chat.is_log_chat.is_(False),
                NewMember.joined_at >= datetime.now(timezone.utc) - timedelta(days=30),
            )
            .group_by(Chat.owner_user_id)
        )
        for row in joins_30_q.all():
            joins_30d_by_owner[int(row[0])] = int(row[1] or 0)
        ga_q = await session.execute(select(GlobalAntispamUser.user_id).where(GlobalAntispamUser.user_id.in_(tg_ids)))
        global_antispam_ids = {int(r[0]) for r in ga_q.all()}
        jrs_q = await session.execute(
            select(OwnerJoinReportSetting).where(OwnerJoinReportSetting.telegram_user_id.in_(tg_ids))
        )
        for st in jrs_q.scalars().all():
            raw = str(getattr(st, "periods_csv", "") or "")
            vals = [x.strip().lower() for x in raw.split(",") if x.strip()]
            join_report_periods_by_owner[int(getattr(st, "telegram_user_id", 0) or 0)] = [
                x for x in vals if x in {"day", "3d", "week", "month"}
            ]
        red_q = await session.execute(
            select(
                PromoCodeRedemption.telegram_user_id,
                PromoCode.code,
                PromoCode.tariff,
                PromoCode.days,
                PromoCodeRedemption.redeemed_at,
            )
            .join(PromoCode, PromoCode.id == PromoCodeRedemption.promo_code_id)
            .where(PromoCodeRedemption.telegram_user_id.in_(tg_ids))
            .order_by(PromoCodeRedemption.telegram_user_id.asc(), PromoCodeRedemption.redeemed_at.desc())
        )
        for row in red_q.all():
            uid = int(row[0] or 0)
            if uid <= 0 or uid in promo_by_user:
                continue
            uobj = user_by_tg.get(uid)
            if not uobj:
                continue
            src = str(getattr(uobj, "subscription_source", "") or "").strip().lower()
            sub_until = getattr(uobj, "subscription_until", None)
            days = int(row[3] or 0)
            tariff = str(row[2] or "premium")
            is_active = False
            expires_at = ""
            remaining_days = 0
            if sub_until:
                if sub_until.tzinfo is None:
                    sub_until = sub_until.replace(tzinfo=timezone.utc)
                is_active = src == "promo" and sub_until > now_utc
                expires_at = _format_dt(sub_until)
                remaining_days = max(0, (sub_until.date() - now_utc.date()).days)
            purpose = (
                f"Активация {tariff} на {days} дн." if days > 0 else f"Активация {tariff} без срока"
            )
            promo_by_user[uid] = {
                "applied_code": str(row[1] or ""),
                "applied_at": _format_dt(row[4]),
                "purpose": purpose,
                "expires_at": expires_at,
                "remaining_days": int(remaining_days),
                "is_active": bool(is_active),
            }
    items = []
    for u in users:
        tg_id = int(getattr(u, "telegram_id", 0) or 0)
        promo = promo_by_user.get(tg_id) or {}
        items.append({
            "telegram_id": tg_id,
            "username": str(getattr(u, "username", "") or ""),
            "first_name": str(getattr(u, "first_name", "") or ""),
            "status": str(getattr(u, "status", "") or "active"),
            "in_global_antispam": tg_id in global_antispam_ids,
            "tariff": str(getattr(u, "tariff", "free") or "free"),
            "subscription_until": _format_dt(getattr(u, "subscription_until", None)),
            "subscription_tokens": 0.0,
            "aurum_tokens": float(getattr(u, "aurum_credits", 0.0) or 0.0),
            "partner_tokens": float(getattr(u, "bonus_credits", 0.0) or 0.0),
            "chat_count": int(chat_counts_map.get(tg_id, 0)),
            "delegated_chat_count": int(delegated_counts_map.get(tg_id, 0)),
            "anti_url_enabled_chats": int(anti_url_enabled_counts_map.get(tg_id, 0)),
            "anti_url_enabled": int(anti_url_enabled_counts_map.get(tg_id, 0)) > 0,
            "created_at": _format_dt(getattr(u, "created_at", None)),
            "first_start_at": _format_dt(getattr(u, "first_start_at", None)),
            "last_webapp_seen_at": _format_dt(getattr(u, "last_webapp_seen_at", None)),
            "promo_applied_code": str(promo.get("applied_code", "") or ""),
            "promo_applied_at": str(promo.get("applied_at", "") or ""),
            "promo_purpose": str(promo.get("purpose", "") or ""),
            "promo_expires_at": str(promo.get("expires_at", "") or ""),
            "promo_days_left": int(promo.get("remaining_days", 0) or 0),
            "promo_is_active": bool(promo.get("is_active", False)),
            "payment_method_bound": bool(getattr(u, "payment_method_bound", False)),
            "payment_method_type": str(getattr(u, "payment_method_type", "") or ""),
            "payment_method_last4": str(getattr(u, "payment_method_last4", "") or ""),
            "joins_24h": int(joins_24h_by_owner.get(tg_id, 0)),
            "joins_30d": int(joins_30d_by_owner.get(tg_id, 0)),
            "join_report_periods": join_report_periods_by_owner.get(tg_id, []),
            "legal_bundle_accepted_at": _format_dt(getattr(u, "legal_bundle_accepted_at", None)),
            "legal_pd_accepted_at": _format_dt(getattr(u, "legal_pd_accepted_at", None)),
            "legal_marketing_opt_in": bool(getattr(u, "legal_marketing_opt_in", False)),
        })
    return {"items": items}


@router.get("/admin/users/{target_telegram_id}/subscription-profile")
async def api_admin_user_subscription_profile(
    target_telegram_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """
    Как /api/me — только поля подписки, для отображения карточки в ADM (просмотр чужого аккаунта).
    """
    await _require_admin_user(session, int(user_id))
    u = await get_or_create_user(session, int(target_telegram_id))
    return await _user_subscription_panel_dict(session, u)


@router.get("/admin/chats")
async def api_admin_chats(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    log_targets = select(Chat.log_chat_id).where(Chat.log_chat_id.is_not(None))
    q = await session.execute(
        select(Chat).where(
            Chat.is_active == True,  # noqa: E712
            Chat.is_log_chat == False,  # noqa: E712
            Chat.id.not_in(log_targets),
        ).order_by(Chat.created_at.desc()).limit(2000)
    )
    rows = q.scalars().all()
    owner_ids = list({int(r.owner_user_id) for r in rows if getattr(r, "owner_user_id", None)})
    owners_map: dict[int, User] = {}
    if owner_ids:
        oq = await session.execute(select(User).where(User.telegram_id.in_(owner_ids)))
        for ou in oq.scalars().all():
            owners_map[int(getattr(ou, "telegram_id", 0) or 0)] = ou
    items = []
    for c in rows:
        owner_tg = int(getattr(c, "owner_user_id", 0) or 0)
        owner = owners_map.get(owner_tg)
        items.append({
            "chat_id": int(getattr(c, "id", 0) or 0),
            "title": str(getattr(c, "title", "") or ""),
            "username": str(getattr(c, "username", "") or ""),
            "is_log_chat": bool(getattr(c, "is_log_chat", False)),
            "is_active": bool(getattr(c, "is_active", False)),
            "owner_telegram_id": owner_tg,
            "owner_username": str(getattr(owner, "username", "") or ""),
            "owner_first_name": str(getattr(owner, "first_name", "") or ""),
            "open_link": _chat_open_link(int(getattr(c, "id", 0) or 0), str(getattr(c, "username", "") or "")),
            "created_at": _format_dt(getattr(c, "created_at", None)),
        })
    return {"items": items}


@router.get("/admin/broadcast/groups")
async def api_admin_broadcast_groups(
    scope: str = "mine",
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """
    Группы (supergroup/group) этого бота для рассылки/автопоста.
    scope=mine — только чаты, где владелец = текущий пользователь Telegram.
    scope=all — все активные группы в БД этого бота (только для полных прав админа).
    """
    user, _full = await _require_broadcast_access(session, int(user_id))
    sc = (scope or "mine").strip().lower()
    if sc not in ("mine", "all"):
        sc = "mine"
    if not _full:
        sc = "mine"
    if sc == "all" and not _broadcast_viewer_can_scope_all(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="scope=all: недостаточно прав (доступны только ваши группы)",
        )
    q = (
        select(Chat)
        .where(
            Chat.is_active == True,  # noqa: E712
            Chat.is_log_chat == False,  # noqa: E712
            Chat.id < 0,
            or_(Chat.chat_kind.is_(None), Chat.chat_kind == "group"),
        )
        .order_by(Chat.title.asc().nulls_last(), Chat.id.desc())
    )
    if sc == "mine":
        sub = select(ChatManager.chat_id).where(ChatManager.user_id == int(user_id)).subquery()
        q = q.where(or_(Chat.owner_user_id == int(user_id), Chat.id.in_(select(sub.c.chat_id))))
    rows = (await session.execute(q)).scalars().all()
    owner_ids = list({int(r.owner_user_id) for r in rows if getattr(r, "owner_user_id", None)})
    owners_map: dict[int, User] = {}
    if owner_ids:
        oq = await session.execute(select(User).where(User.telegram_id.in_(owner_ids)))
        for ou in oq.scalars().all():
            owners_map[int(getattr(ou, "telegram_id", 0) or 0)] = ou
    items = []
    for c in rows:
        owner_tg = int(getattr(c, "owner_user_id", 0) or 0)
        owner = owners_map.get(owner_tg)
        items.append(
            {
                "chat_id": int(getattr(c, "id", 0) or 0),
                "title": str(getattr(c, "title", "") or ""),
                "username": str(getattr(c, "username", "") or ""),
                "owner_telegram_id": owner_tg,
                "owner_username": str(getattr(owner, "username", "") or "") if owner else "",
            }
        )
    return {
        "items": items,
        "scope": sc,
        "can_scope_all": _broadcast_viewer_can_scope_all(user),
    }


@router.get("/admin/broadcast/channels")
async def api_admin_broadcast_channels(
    scope: str = "mine",
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Каналы, куда бот добавлен админом (chat_kind=channel) — для рассылки из Mini App."""
    user, _full = await _require_broadcast_access(session, int(user_id))
    sc = (scope or "mine").strip().lower()
    if sc not in ("mine", "all"):
        sc = "mine"
    if not _full:
        sc = "mine"
    if sc == "all" and not _broadcast_viewer_can_scope_all(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="scope=all: недостаточно прав",
        )
    q = (
        select(Chat)
        .where(
            Chat.is_active == True,  # noqa: E712
            Chat.is_log_chat == False,  # noqa: E712
            Chat.id < 0,
            Chat.chat_kind == "channel",
        )
        .order_by(Chat.title.asc().nulls_last(), Chat.id.desc())
    )
    if sc == "mine":
        sub = select(ChatManager.chat_id).where(ChatManager.user_id == int(user_id)).subquery()
        q = q.where(or_(Chat.owner_user_id == int(user_id), Chat.id.in_(select(sub.c.chat_id))))
    rows = (await session.execute(q)).scalars().all()
    owner_ids = list({int(r.owner_user_id) for r in rows if getattr(r, "owner_user_id", None)})
    owners_map: dict[int, User] = {}
    if owner_ids:
        oq = await session.execute(select(User).where(User.telegram_id.in_(owner_ids)))
        for ou in oq.scalars().all():
            owners_map[int(getattr(ou, "telegram_id", 0) or 0)] = ou
    items = []
    for c in rows:
        owner_tg = int(getattr(c, "owner_user_id", 0) or 0)
        owner = owners_map.get(owner_tg)
        items.append(
            {
                "chat_id": int(getattr(c, "id", 0) or 0),
                "title": str(getattr(c, "title", "") or ""),
                "username": str(getattr(c, "username", "") or ""),
                "owner_telegram_id": owner_tg,
                "owner_username": str(getattr(owner, "username", "") or "") if owner else "",
            }
        )
    return {
        "items": items,
        "scope": sc,
        "can_scope_all": _broadcast_viewer_can_scope_all(user),
    }


@router.get("/admin/revenue-stats")
async def api_admin_revenue_stats(
    period: str = "30d",
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    now_utc = datetime.now(timezone.utc)
    p = (period or "30d").strip().lower()
    if p not in {"7d", "30d", "90d", "12m"}:
        p = "30d"
    day_window = 7 if p == "7d" else 30 if p == "30d" else 90
    month_window_days = 370 if p == "12m" else 365
    today_q = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
            Payment.status == "succeeded",
            Payment.created_at >= now_utc - timedelta(hours=24),
        )
    )
    month_q = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
            Payment.status == "succeeded",
            func.extract("year", Payment.created_at) == now_utc.year,
            func.extract("month", Payment.created_at) == now_utc.month,
        )
    )
    bucket_day = func.date(Payment.created_at)
    day_rows_q = await session.execute(
        select(
            bucket_day.label("bucket_day"),
            func.coalesce(func.sum(Payment.amount), 0.0).label("amount_rub"),
            func.count(Payment.id).label("payments_count"),
        ).where(
            Payment.status == "succeeded",
            Payment.created_at >= now_utc - timedelta(days=day_window - 1),
        ).group_by(literal_column("1")).order_by(literal_column("1"))
    )
    bucket_month = func.date_trunc("month", Payment.created_at)
    month_rows_q = await session.execute(
        select(
            bucket_month.label("bucket_month"),
            func.coalesce(func.sum(Payment.amount), 0.0).label("amount_rub"),
            func.count(Payment.id).label("payments_count"),
        ).where(
            Payment.status == "succeeded",
            Payment.created_at >= now_utc - timedelta(days=month_window_days),
        ).group_by(literal_column("1")).order_by(literal_column("1"))
    )
    by_day = [
        {
            "date": str(row.bucket_day),
            "amount_rub": round(float(row.amount_rub or 0.0), 2),
            "payments_count": int(row.payments_count or 0),
        }
        for row in day_rows_q.all()
    ]
    by_month = [
        {
            "month": _format_dt(row.bucket_month),
            "amount_rub": round(float(row.amount_rub or 0.0), 2),
            "payments_count": int(row.payments_count or 0),
        }
        for row in month_rows_q.all()
    ]
    return {
        "period": p,
        "today_rub": round(float(today_q.scalar() or 0.0), 2),
        "month_rub": round(float(month_q.scalar() or 0.0), 2),
        "by_day": by_day,
        "by_month": by_month,
    }


@router.get("/admin/referrals/funnel")
async def api_admin_referrals_funnel(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    users_q = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(5000)
    )
    users = users_q.scalars().all()
    by_tg: dict[int, User] = {}
    children: dict[int, list[int]] = {}
    for u in users:
        tg_id = int(getattr(u, "telegram_id", 0) or 0)
        if not tg_id:
            continue
        by_tg[tg_id] = u
        parent = int(getattr(u, "referred_by_tg_id", 0) or 0)
        if parent:
            children.setdefault(parent, []).append(tg_id)

    def count_downline(root_tg: int, max_depth: int = 3) -> dict[int, int]:
        counts = {1: 0, 2: 0, 3: 0}
        frontier = [root_tg]
        for depth in range(1, max_depth + 1):
            nxt: list[int] = []
            for node in frontier:
                lst = children.get(node, [])
                counts[depth] += len(lst)
                nxt.extend(lst)
            frontier = nxt
            if not frontier:
                break
        return counts

    paid_rows_q = await session.execute(
        select(User).where(User.ref_paid_count > 0).order_by(User.ref_sales_total.desc()).limit(500)
    )
    paid_rows = paid_rows_q.scalars().all()
    items = []
    for u in paid_rows:
        tg_id = int(getattr(u, "telegram_id", 0) or 0)
        d = count_downline(tg_id, 3)
        items.append({
            "telegram_id": tg_id,
            "username": str(getattr(u, "username", "") or ""),
            "first_name": str(getattr(u, "first_name", "") or ""),
            "paid_count": int(getattr(u, "ref_paid_count", 0) or 0),
            "start_count": int(getattr(u, "ref_start_count", 0) or 0),
            "share_count": int(getattr(u, "ref_share_count", 0) or 0),
            "sales_total_rub": round(float(getattr(u, "ref_sales_total", 0.0) or 0.0), 2),
            "dm_link": _user_dm_link(str(getattr(u, "username", "") or ""), tg_id),
            "downline_level_1": int(d.get(1, 0)),
            "downline_level_2": int(d.get(2, 0)),
            "downline_level_3": int(d.get(3, 0)),
        })
    return {"items": items}


@router.get("/admin/my-partner-stats")
async def api_admin_my_partner_stats(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Личная партнерская статистика (админ или Premium)."""
    me = await get_or_create_user(session, int(user_id))
    now_chk = datetime.now(timezone.utc)
    if not (_is_full_admin_user(me, int(user_id)) or _is_user_premium_now(me, now_chk)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа")
    fin = await _partner_financials(session, me)
    now_utc = datetime.now(timezone.utc)
    periods = {
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "14d": timedelta(days=14),
        "30d": timedelta(days=30),
        "180d": timedelta(days=180),
        "365d": timedelta(days=365),
    }
    period_totals: dict[str, float] = {}
    for key, delta in periods.items():
        q = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0)).where(
                PartnerCommission.owner_user_id == int(me.id),
                PartnerCommission.created_at >= now_utc - delta,
                PartnerCommission.status.in_(("pending", "available", "paid")),
            )
        )
        period_totals[key] = round(float(q.scalar() or 0.0), 2)

    pc_bucket_month = func.date_trunc("month", PartnerCommission.created_at)
    by_month_q = await session.execute(
        select(
            pc_bucket_month.label("bucket_month"),
            func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0).label("amount_rub"),
        ).where(
            PartnerCommission.owner_user_id == int(me.id),
            PartnerCommission.created_at >= now_utc - timedelta(days=365),
            PartnerCommission.status.in_(("pending", "available", "paid")),
        ).group_by(literal_column("1")).order_by(literal_column("1"))
    )
    by_month = []
    for row in by_month_q.all():
        dt = row.bucket_month
        month_key = dt.strftime("%Y-%m") if hasattr(dt, "strftime") else str(dt)
        by_month.append({
            "month": month_key,
            "amount_rub": round(float(row.amount_rub or 0.0), 2),
        })

    return {
        "total_rub": round(float(fin.get("commission_total_rub", 0.0) or 0.0), 2),
        "available_rub": round(float(fin.get("available_rub", 0.0) or 0.0), 2),
        "pending_rub": round(float(fin.get("pending_rub", 0.0) or 0.0), 2),
        "paid_rub": round(float(fin.get("paid_total_rub", 0.0) or 0.0), 2),
        "periods_rub": period_totals,
        "by_month": by_month,
    }


def _railway_redeploy_ids() -> tuple[str, str, str, str]:
    """
    UUID среды и сервисов для вызова Railway GraphQL (redeploy).

    На самом Railway в каждый сервис уже подставляются системные переменные
    RAILWAY_ENVIRONMENT_ID и RAILWAY_SERVICE_ID (см. docs.railway.com → Variables).
    Дополнительно можно задать RAILWAY_SERVICE_ID_BOT / _API / _WEBAPP вручную;
    для текущего API-сервиса RAILWAY_SERVICE_ID_API можно не задавать — подставится RAILWAY_SERVICE_ID.
    """
    env_id = (os.getenv("RAILWAY_ENVIRONMENT_ID") or "").strip()
    sid_bot = (os.getenv("RAILWAY_SERVICE_ID_BOT") or "").strip()
    sid_api = (os.getenv("RAILWAY_SERVICE_ID_API") or os.getenv("RAILWAY_SERVICE_ID") or "").strip()
    sid_web = (os.getenv("RAILWAY_SERVICE_ID_WEBAPP") or "").strip()
    return env_id, sid_bot, sid_api, sid_web


@router.get("/admin/ops/health")
async def api_admin_ops_health(
    request: Request,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Операционный мониторинг: здоровье, активность, подсказки."""
    await _require_admin_user(session, int(user_id))
    now_utc = datetime.now(timezone.utc)
    boot = getattr(request.app.state, "api_boot_at", None) or _API_BOOT_TS
    uptime_sec = int((now_utc - boot).total_seconds())

    t0 = perf_counter()
    await session.execute(text("SELECT 1"))
    db_latency_ms = round((perf_counter() - t0) * 1000, 2)

    payments_24h_q = await session.execute(
        select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0.0)).where(
            Payment.status == "succeeded",
            Payment.created_at >= now_utc - timedelta(hours=24),
        )
    )
    payments_24h_count, payments_24h_sum = payments_24h_q.first() or (0, 0.0)

    payouts_open_q = await session.execute(
        select(func.count(PartnerPayoutRequest.id), func.coalesce(func.sum(PartnerPayoutRequest.amount_rub), 0.0)).where(
            PartnerPayoutRequest.status.in_(("new", "approved", "frozen"))
        )
    )
    payouts_open_count, payouts_open_sum = payouts_open_q.first() or (0, 0.0)

    moderation_24h_q = await session.execute(
        select(func.count(ModerationLog.id)).where(ModerationLog.created_at >= now_utc - timedelta(hours=24))
    )
    moderation_24h = int(moderation_24h_q.scalar() or 0)

    bucket_hour = func.date_trunc("hour", Payment.created_at)
    hours_activity_q = await session.execute(
        select(
            bucket_hour.label("bucket_hour"),
            func.count(Payment.id).label("payments_count"),
            func.coalesce(func.sum(Payment.amount), 0.0).label("payments_sum"),
        ).where(
            Payment.status == "succeeded",
            Payment.created_at >= now_utc - timedelta(hours=24),
        ).group_by(literal_column("1")).order_by(literal_column("1"))
    )
    by_hour = []
    for row in hours_activity_q.all():
        by_hour.append({
            "hour": _format_dt(row.bucket_hour),
            "payments_count": int(row.payments_count or 0),
            "payments_sum_rub": round(float(row.payments_sum or 0.0), 2),
        })

    status = "ok"
    diagnostics: list[str] = []
    if db_latency_ms > 300:
        status = "warn"
        diagnostics.append("База данных отвечает медленно — возможна нехватка ресурсов.")
    if int(payouts_open_count or 0) > 30:
        status = "warn"
        diagnostics.append("Много открытых заявок на выплаты — проверьте обработку выплат.")
    if int(moderation_24h or 0) > 10000:
        status = "warn"
        diagnostics.append("Сильный всплеск модерации — возможна атака/рейд в чатах.")

    rw_token = (os.getenv("RAILWAY_API_TOKEN") or os.getenv("RAILWAY_TOKEN") or "").strip()
    rw_env, rw_sid_bot, rw_sid_api, rw_sid_web = _railway_redeploy_ids()

    def _sid_ok(s: str) -> bool:
        t = (s or "").strip()
        return bool(t) and "YOUR_" not in t.upper()

    railway_redeploy = {
        "token_configured": bool(rw_token),
        "environment_configured": bool(rw_env),
        "service_ids": {
            "bot": _sid_ok(rw_sid_bot),
            "api": _sid_ok(rw_sid_api),
            "webapp": _sid_ok(rw_sid_web),
        },
    }
    if not rw_token:
        status = "warn"
        diagnostics.append(
            "Guard Pulse / перезапуск: создайте токен в Railway → Account → Tokens, "
            "добавьте в сервис API переменную RAILWAY_API_TOKEN (или RAILWAY_TOKEN). См. DEPLOY-RAILWAY.md."
        )
    elif not rw_env:
        status = "warn"
        diagnostics.append(
            "Guard Pulse / перезапуск: нет RAILWAY_ENVIRONMENT_ID (на Railway он обычно приходит сам; "
            "локально задайте вручную или смотрите DEPLOY-RAILWAY.md)."
        )
    elif not (_sid_ok(rw_sid_bot) and _sid_ok(rw_sid_api) and _sid_ok(rw_sid_web)):
        status = "warn"
        diagnostics.append(
            "Guard Pulse / перезапуск: задайте UUID сервисов RAILWAY_SERVICE_ID_BOT, "
            "RAILWAY_SERVICE_ID_API, RAILWAY_SERVICE_ID_WEBAPP (Settings → service → ID). См. DEPLOY-RAILWAY.md."
        )

    if not diagnostics:
        diagnostics.append("Система работает стабильно. Критичных отклонений не обнаружено.")

    return {
        "status": status,
        "server_time": _format_dt(now_utc),
        "api_boot_at": _format_dt(boot),
        "api_uptime_sec": uptime_sec,
        "db_latency_ms": db_latency_ms,
        "payments_24h": {
            "count": int(payments_24h_count or 0),
            "sum_rub": round(float(payments_24h_sum or 0.0), 2),
        },
        "payouts_open": {
            "count": int(payouts_open_count or 0),
            "sum_rub": round(float(payouts_open_sum or 0.0), 2),
        },
        "moderation_24h_count": int(moderation_24h or 0),
        "activity_by_hour": by_hour,
        "diagnostics": diagnostics,
        "railway_redeploy": railway_redeploy,
    }


@router.get("/admin/diagnostics/summary")
async def api_admin_diagnostics_summary(
    window_hours: int = Query(24, ge=1, le=168),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Сводка уровня здоровья журнала (ok / warn / critical) за окно — только полный админ."""
    await _require_admin_user(session, int(user_id))
    from app.services.admin_diagnostics_service import fetch_diagnostics_summary

    return await fetch_diagnostics_summary(session, window_hours=int(window_hours))


@router.get("/admin/diagnostics/feed")
async def api_admin_diagnostics_feed(
    limit: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, description="Поиск: telegram id или @username / имя из таблицы users"),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Журнал сбоев с фильтром по пользователю — только полный админ."""
    await _require_admin_user(session, int(user_id))
    from app.services.admin_diagnostics_service import fetch_diagnostics_feed

    items = await fetch_diagnostics_feed(session, limit=int(limit), q=q)
    return {"items": items}


@router.post("/admin/ops/action")
async def api_admin_ops_action(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Операционные действия (перезапуск сервисов через Railway API)."""
    await _require_admin_user(session, int(user_id))
    action = str(body.get("action") or "").strip().lower()
    token = (os.getenv("RAILWAY_API_TOKEN") or os.getenv("RAILWAY_TOKEN") or "").strip()
    environment_id, sid_bot, sid_api, sid_web = _railway_redeploy_ids()
    service_map = {
        "restart_bot": sid_bot,
        "restart_api": sid_api,
        "restart_webapp": sid_web,
    }
    if action not in service_map:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестное действие")
    if not token or not environment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Не настроены RAILWAY_API_TOKEN (или RAILWAY_TOKEN) или не виден RAILWAY_ENVIRONMENT_ID "
                "(на деплое Railway он задаётся платформой; локально добавьте в .env)."
            ),
        )
    service_id = service_map.get(action, "")
    if not service_id or "YOUR_" in service_id.upper():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Не настроен service id для действия. "
                "Проверьте RAILWAY_SERVICE_ID_BOT / RAILWAY_SERVICE_ID_API / RAILWAY_SERVICE_ID_WEBAPP"
            ),
        )
    gql = """
    mutation serviceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
      serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                "https://backboard.railway.app/graphql/v2",
                json={
                    "query": gql,
                    "variables": {"serviceId": service_id, "environmentId": environment_id},
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                payload = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Railway API HTTP {resp.status}")
                if isinstance(payload, dict) and payload.get("errors"):
                    parts: list[str] = []
                    for err in payload.get("errors") or []:
                        if isinstance(err, dict):
                            parts.append(str(err.get("message") or err))
                        else:
                            parts.append(str(err))
                    msg = ("; ".join(parts) if parts else str(payload.get("errors")))[:400]
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Railway: {msg}")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Ошибка вызова Railway API. Проверьте токен/ID окружения/ID сервиса."
            ),
        )
    return {"ok": True, "action": action}


@router.post("/admin/users/{target_telegram_id}/reset-finance")
async def api_admin_user_reset_finance(
    target_telegram_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    uq = await session.execute(select(User).where(User.telegram_id == int(target_telegram_id)).limit(1))
    u = uq.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    # Полный финансовый сброс пользователя.
    await session.execute(delete(Payment).where(Payment.user_id == int(u.id)))
    await session.execute(delete(CreditLedger).where(CreditLedger.user_id == int(u.id)))
    await session.execute(delete(PartnerPayoutRequest).where(PartnerPayoutRequest.user_id == int(u.id)))
    await session.execute(
        delete(PartnerCommission).where(
            (PartnerCommission.owner_user_id == int(u.id)) | (PartnerCommission.source_user_id == int(u.id))
        )
    )

    u.tariff = "free"
    u.subscription_until = None
    u.chat_limit = 3
    u.group_limit = 3
    u.channel_limit = 1
    u.credits_balance = 0.0
    u.aurum_credits = 0.0
    u.bonus_credits = 0.0
    u.ref_paid_count = 0
    u.ref_sales_total = 0.0
    u.ref_earned_credits = 0.0
    await enforce_owner_active_chat_limit(session, int(target_telegram_id), 3)
    session.add(u)
    await session.commit()
    return {"ok": True, "telegram_id": int(target_telegram_id)}


@router.post("/admin/users/{target_telegram_id}/reset-delegation")
async def api_admin_user_reset_delegation(
    target_telegram_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Снять пользователя со всех чатов как менеджера и удалить приглашения менеджера."""
    await _require_admin_user(session, int(user_id))
    tid = int(target_telegram_id)
    u = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    await session.execute(delete(ChatManager).where(ChatManager.user_id == tid))
    await session.execute(delete(ChatManagerInvite).where(ChatManagerInvite.target_telegram_id == tid))
    uname = _norm_username(getattr(u, "username", None))
    if uname:
        await session.execute(delete(ChatManagerInvite).where(func.lower(ChatManagerInvite.target_username) == uname))
    await session.commit()
    return {"ok": True, "telegram_id": tid}


@router.post("/admin/users/{target_telegram_id}/reset-connected-chats")
async def api_admin_user_reset_connected_chats(
    target_telegram_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Отключить все группы пользователя как владельца (is_active=false), без блокировки аккаунта."""
    await _require_admin_user(session, int(user_id))
    tid = int(target_telegram_id)
    u = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    await session.execute(
        text(
            "UPDATE chats SET is_active=FALSE, log_chat_id=NULL "
            "WHERE owner_user_id=:tg AND COALESCE(is_log_chat, FALSE)=FALSE"
        ),
        {"tg": tid},
    )
    ctx = await session.get(UserContext, tid)
    if ctx:
        ctx.selected_chat_id = None
        session.add(ctx)
    await session.commit()
    return {"ok": True, "telegram_id": tid}


@router.get("/admin/users/{target_telegram_id}/join-report-settings")
async def api_admin_user_join_report_settings_get(
    target_telegram_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    tid = int(target_telegram_id)
    st = await session.get(OwnerJoinReportSetting, tid)
    raw = str(getattr(st, "periods_csv", "") or "")
    periods = [x.strip().lower() for x in raw.split(",") if x.strip()]
    periods = [x for x in periods if x in {"day", "3d", "week", "month"}]
    return {"telegram_id": tid, "periods": periods}


@router.post("/admin/users/{target_telegram_id}/join-report-settings")
async def api_admin_user_join_report_settings_set(
    target_telegram_id: int,
    body: dict | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_admin_user(session, int(user_id))
    tid = int(target_telegram_id)
    u = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    arr = []
    if isinstance(body, dict):
        arr_raw = body.get("periods")
        if isinstance(arr_raw, (list, tuple)):
            arr = [str(x).strip().lower() for x in arr_raw]
    allowed = {"day", "3d", "week", "month"}
    periods: list[str] = []
    for p in arr:
        if p in allowed and p not in periods:
            periods.append(p)
    csv_val = ",".join(periods)
    st = await session.get(OwnerJoinReportSetting, tid)
    if not st:
        st = OwnerJoinReportSetting(telegram_user_id=tid, periods_csv=csv_val)
    else:
        st.periods_csv = csv_val
    session.add(st)
    await session.commit()
    return {"ok": True, "telegram_id": tid, "periods": periods}


@router.post("/admin/users/{target_telegram_id}/delete-block")
async def api_admin_user_delete_block(
    target_telegram_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Удалить операционные данные пользователя и пометить как blocked."""
    await _require_admin_user(session, int(user_id))
    uq = await session.execute(select(User).where(User.telegram_id == int(target_telegram_id)).limit(1))
    u = uq.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    # Снимаем активность чатов пользователя.
    await session.execute(
        text("UPDATE chats SET is_active=FALSE, log_chat_id=NULL WHERE owner_user_id=:tg"),
        {"tg": int(target_telegram_id)},
    )
    # Удаляем финансово-партнерские записи пользователя.
    await session.execute(delete(Payment).where(Payment.user_id == int(u.id)))
    await session.execute(delete(CreditLedger).where(CreditLedger.user_id == int(u.id)))
    await session.execute(delete(PartnerPayoutRequest).where(PartnerPayoutRequest.user_id == int(u.id)))
    await session.execute(
        delete(PartnerCommission).where(
            (PartnerCommission.owner_user_id == int(u.id)) | (PartnerCommission.source_user_id == int(u.id))
        )
    )
    # Блокировка в системе.
    u.status = "blocked"
    u.tariff = "free"
    u.subscription_until = None
    u.chat_limit = 3
    u.group_limit = 3
    u.channel_limit = 1
    u.credits_balance = 0.0
    u.aurum_credits = 0.0
    u.bonus_credits = 0.0
    u.ref_paid_count = 0
    u.ref_sales_total = 0.0
    u.ref_earned_credits = 0.0
    await enforce_owner_active_chat_limit(session, int(target_telegram_id), 3)
    session.add(u)
    # Добавляем в глобальный антиспам (чтобы не проходил проверки в чатах).
    row = await session.get(GlobalAntispamUser, int(target_telegram_id))
    if not row:
        session.add(
            GlobalAntispamUser(
                user_id=int(target_telegram_id),
                reason="blocked_by_admin",
                display_name=str(getattr(u, "first_name", "") or ""),
                username=str(getattr(u, "username", "") or ""),
            )
        )
    await session.commit()
    return {"ok": True, "telegram_id": int(target_telegram_id), "status": "blocked"}


@router.post("/admin/users/{target_telegram_id}/unblock")
async def api_admin_user_unblock(
    target_telegram_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Снять блокировку пользователя и убрать из глобальной антиспам-базы (разбан в группах бота)."""
    await _require_admin_user(session, int(user_id))
    uq = await session.execute(select(User).where(User.telegram_id == int(target_telegram_id)).limit(1))
    u = uq.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    u.status = "active"
    session.add(u)
    await session.commit()
    removed_ga = await remove_from_global_antispam(session, int(target_telegram_id))
    return {
        "ok": True,
        "telegram_id": int(target_telegram_id),
        "status": "active",
        "removed_from_global_antispam": removed_ga,
    }


@router.get("/referral/people")
async def api_referral_people(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Списки рефералов: полный и самые активные."""
    await get_or_create_user(session, user_id)
    invited_q = await session.execute(
        select(
            User.id,
            User.telegram_id,
            User.first_name,
            User.username,
            User.created_at,
        ).where(User.referred_by_tg_id == int(user_id)).limit(1000)
    )
    invited_rows = invited_q.all()
    if not invited_rows:
        return {"full_list": [], "top_active": []}

    invited_user_ids = [int(row.id) for row in invited_rows if row.id]
    payments_map: dict[int, dict] = {}
    tokens_map: dict[int, float] = {}

    if invited_user_ids:
        pay_q = await session.execute(
            select(
                Payment.user_id,
                func.count(Payment.id).label("pay_count"),
                func.max(Payment.created_at).label("last_paid_at"),
                func.coalesce(func.sum(Payment.amount), 0.0).label("sales_sum"),
            ).where(
                Payment.user_id.in_(invited_user_ids),
                Payment.status == "succeeded",
            ).group_by(Payment.user_id)
        )
        for row in pay_q.all():
            uid = int(row.user_id)
            payments_map[uid] = {
                "payments_count": int(row.pay_count or 0),
                "last_paid_at": _format_dt(row.last_paid_at),
                "sales_rub": float(row.sales_sum or 0.0),
            }

        token_q = await session.execute(
            select(
                CreditLedger.user_id,
                func.sum(CreditLedger.delta).label("tokens_sum"),
            ).where(
                CreditLedger.user_id.in_(invited_user_ids),
                CreditLedger.reason == "tokens_purchase",
                CreditLedger.delta > 0,
            ).group_by(CreditLedger.user_id)
        )
        for row in token_q.all():
            uid = int(row.user_id)
            tokens_map[uid] = float(row.tokens_sum or 0.0)

    full_list = []
    for row in invited_rows:
        uid = int(row.id)
        p = payments_map.get(uid, {})
        tokens_sum = float(tokens_map.get(uid, 0.0))
        full_list.append({
            "user_id": uid,
            "telegram_id": int(row.telegram_id or 0),
            "first_name": str(row.first_name or "").strip(),
            "username": str(row.username or "").strip(),
            "joined_at": _format_dt(row.created_at),
            "payments_count": int(p.get("payments_count", 0)),
            "last_paid_at": p.get("last_paid_at"),
            "sales_rub": round(float(p.get("sales_rub", 0.0) or 0.0), 2),
            "partner_reward_rub": round(float(p.get("sales_rub", 0.0) or 0.0) * _PARTNER_PAYOUT_RATE, 2),
            "tokens_purchased": round(tokens_sum, 2),
            "is_paid": int(p.get("payments_count", 0)) > 0,
        })

    full_list.sort(
        key=lambda x: (
            0 if x.get("is_paid") else 1,
            -(x.get("tokens_purchased") or 0.0),
            -(x.get("payments_count") or 0),
            x.get("first_name") or x.get("username") or "",
        )
    )
    top_active = sorted(
        [x for x in full_list if (x.get("tokens_purchased", 0.0) > 0 or x.get("payments_count", 0) > 0)],
        key=lambda x: (-(x.get("tokens_purchased") or 0.0), -(x.get("payments_count") or 0)),
    )[:20]
    return {"full_list": full_list, "top_active": top_active}


@router.get("/history/payments")
async def api_history_payments(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(session, user_id)
    q = await session.execute(
        select(Payment).where(
            Payment.user_id == user.id
        ).order_by(Payment.created_at.desc()).limit(100)
    )
    items = []
    for p in q.scalars().all():
        items.append({
            "id": int(getattr(p, "id", 0) or 0),
            "created_at": _format_dt(getattr(p, "created_at", None)),
            "amount_rub": float(getattr(p, "amount", 0.0) or 0.0),
            "months": int(getattr(p, "months", 0) or 0),
            "tariff": str(getattr(p, "tariff", "") or ""),
            "status": str(getattr(p, "status", "") or ""),
            "provider": str(getattr(p, "provider", "") or ""),
            "payment_id": str(getattr(p, "payment_id", "") or ""),
            "receipt_url": str(getattr(p, "receipt_url", "") or ""),
        })
    return {"items": items}


@router.get("/history/tokens")
async def api_history_tokens(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(session, user_id)
    q = await session.execute(
        select(CreditLedger).where(
            CreditLedger.user_id == user.id
        ).order_by(CreditLedger.created_at.desc()).limit(200)
    )
    items = []
    for row in q.scalars().all():
        items.append({
            "created_at": _format_dt(getattr(row, "created_at", None)),
            "delta": float(getattr(row, "delta", 0.0) or 0.0),
            "reason": str(getattr(row, "reason", "") or ""),
        })
    return {"items": items}


@router.get("/history/subscription")
async def api_history_subscription(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """История подписки: успешные оплаты Premium + активации промокодов."""
    user = await get_or_create_user(session, user_id)
    out: list[dict[str, Any]] = []

    pays_q = await session.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.status == "succeeded",
            Payment.tariff.in_(("premium", "premium_probe")),
        ).order_by(Payment.created_at.desc()).limit(200)
    )
    for p in pays_q.scalars().all():
        tariff = str(getattr(p, "tariff", "") or "")
        months_raw = int(getattr(p, "months", 0) or 0)
        out.append({
            "kind": "payment",
            "created_at": _format_dt(getattr(p, "created_at", None)),
            "amount_rub": round(float(getattr(p, "amount", 0.0) or 0.0), 2),
            "period_months": months_raw if tariff == "premium" else 0,
            "period_days": months_raw if tariff == "premium_probe" else 0,
            "provider": str(getattr(p, "provider", "") or ""),
            "promo_code": "",
            "grant_tokens": 0.0,
            "grant_aurum": 0.0,
        })

    promo_q = await session.execute(
        select(PromoCodeRedemption, PromoCode)
        .join(PromoCode, PromoCode.id == PromoCodeRedemption.promo_code_id)
        .where(PromoCodeRedemption.telegram_user_id == int(user_id))
        .order_by(PromoCodeRedemption.redeemed_at.desc())
        .limit(200)
    )
    for red, promo in promo_q.all():
        days = int(getattr(promo, "days", 0) or 0)
        out.append({
            "kind": "promo",
            "created_at": _format_dt(getattr(red, "redeemed_at", None)),
            "amount_rub": 0.0,
            "period_months": 0,
            "period_days": days if days > 0 else 0,
            "provider": "promo",
            "promo_code": str(getattr(promo, "code", "") or ""),
            "grant_tokens": round(float(getattr(promo, "grant_tokens", 0.0) or 0.0), 2),
            "grant_aurum": round(float(getattr(promo, "grant_aurum", 0.0) or 0.0), 2),
        })

    out.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return {"items": out[:200]}


@router.get("/activity/summary")
async def api_activity_summary(
    tz_offset_min: int = Query(0, ge=-840, le=840),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Сводка активности защиты по всем подключенным чатам пользователя.

    Поле "today" агрегируется с 00:00 локального времени пользователя
    (TZ передаёт фронт через `tz_offset_min`), чтобы счётчик
    обнулялся ровно в полночь, как ожидает пользователь.
    """
    # Тариф в основной БД; не тянуть ПДн на ВДС (get_or_create_user) при каждом summary — главный экран
    # параллелит /api/me + этот запрос; двойной round-trip на РФ сильно тормозил после split PII.
    res_u = await session.execute(select(User).where(User.telegram_id == user_id))
    user = res_u.scalar_one_or_none()
    if user is None:
        user = await get_or_create_user(session, user_id)
    chat_ids = await get_activity_summary_chat_ids(session, user_id)
    now_utc = datetime.now(timezone.utc)
    tz_offset = timedelta(minutes=int(tz_offset_min or 0))
    today_local_start = (now_utc + tz_offset).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_local_start - tz_offset
    yesterday_start_utc = today_start_utc - timedelta(days=1)
    deleted = 0
    muted = 0
    banned = 0
    observed = 0
    joins_24h = 0
    deleted_y = 0
    muted_y = 0
    banned_y = 0
    observed_y = 0
    joins_y = 0
    enabled = {"delete": True, "mute": False, "ban": False, "observe": False}
    if chat_ids:
        logs_q = await session.execute(
            select(ModerationLog.action, func.count(ModerationLog.id)).where(
                ModerationLog.chat_id.in_(chat_ids),
                ModerationLog.created_at >= today_start_utc,
            ).group_by(ModerationLog.action)
        )
        for row in logs_q.all():
            action = str(row[0] or "").lower()
            cnt = int(row[1] or 0)
            if "observe" in action:
                observed += cnt
            elif "ban" in action:
                banned += cnt
            elif "mute" in action or "restrict" in action:
                muted += cnt
            else:
                deleted += cnt

        rules_q = await session.execute(select(Rule).where(Rule.chat_id.in_(chat_ids)))
        rules = rules_q.scalars().all()
        enabled["ban"] = any(str(getattr(r, "action_mode", "") or "").lower() == "ban" for r in rules)
        enabled["mute"] = any(
            str(getattr(r, "action_mode", "") or "").lower() == "mute"
            or str(getattr(r, "antinakrutka_action", "") or "").lower() == "alert_restrict"
            for r in rules
        )
        enabled["observe"] = any(str(getattr(r, "action_mode", "") or "").lower() == "observe" for r in rules)
        joins_q = await session.execute(
            select(func.count(NewMember.id)).where(
                NewMember.chat_id.in_(chat_ids),
                NewMember.joined_at >= today_start_utc,
            )
        )
        joins_24h = int(joins_q.scalar() or 0)

        logs_y = await session.execute(
            select(ModerationLog.action, func.count(ModerationLog.id)).where(
                ModerationLog.chat_id.in_(chat_ids),
                ModerationLog.created_at >= yesterday_start_utc,
                ModerationLog.created_at < today_start_utc,
            ).group_by(ModerationLog.action)
        )
        for row in logs_y.all():
            action = str(row[0] or "").lower()
            cnt = int(row[1] or 0)
            if "observe" in action:
                observed_y += cnt
            elif "ban" in action:
                banned_y += cnt
            elif "mute" in action or "restrict" in action:
                muted_y += cnt
            else:
                deleted_y += cnt
        joins_y_q = await session.execute(
            select(func.count(NewMember.id)).where(
                NewMember.chat_id.in_(chat_ids),
                NewMember.joined_at >= yesterday_start_utc,
                NewMember.joined_at < today_start_utc,
            )
        )
        joins_y = int(joins_y_q.scalar() or 0)
    groups_count = 0
    channels_count = 0
    if chat_ids:
        kinds_q = await session.execute(select(Chat.chat_kind).where(Chat.id.in_(chat_ids)))
        for (kind,) in kinds_q.all():
            k = str(kind or "group").strip().lower()
            if k == "channel":
                channels_count += 1
            else:
                groups_count += 1
    _, _, group_limit = await can_add_chat(session, user_id)
    _, _, channel_limit = await can_add_channel(session, user_id)
    # Уровень защиты: есть хотя бы один чат с Guard не на паузе (включая каналы).
    # «Защищено» — только группы; считаем все доступные чаты, в т.ч. is_active=False (иначе занижали счёт).
    managed = await get_accessible_chats_any_active(session, user_id)
    protection_active = False
    protected_groups_count = 0
    if managed:
        mid = [int(c.id) for c in managed]
        res_m = await session.execute(
            select(Chat.chat_kind, Rule.master_anti_spam, Rule.chat_id)
            .select_from(Chat)
            .outerjoin(Rule, Rule.chat_id == Chat.id)
            .where(Chat.id.in_(mid)),
        )
        for kind, mas, rule_chat_id in res_m.all():
            # PK rules — chat_id; при отсутствии строки правила outerjoin даёт rule_chat_id IS NULL.
            eff = rule_chat_id is None or bool(mas)
            if eff:
                protection_active = True
                if str(kind or "group").strip().lower() != "channel":
                    protected_groups_count += 1
    return {
        "protection_active": protection_active,
        "protected_groups_count": int(protected_groups_count),
        "tariff": str(getattr(user, "tariff", "free") or "free"),
        "chats_count": len(chat_ids),
        "chats_count_total": len(chat_ids),
        "chat_limit": int(group_limit or 0),
        "group_limit": int(group_limit or 0),
        "channel_limit": int(channel_limit or 0),
        "usage_progress": round((int(groups_count) / max(1, int(group_limit or 1))) * 100, 2),
        "groups_count": int(groups_count),
        "channels_count": int(channels_count),
        "groups_limit": int(group_limit or 0),
        "channels_limit": int(channel_limit or 0),
        "groups_usage_progress": round((int(groups_count) / max(1, int(group_limit or 1))) * 100, 2),
        "channels_usage_progress": round((int(channels_count) / max(1, int(channel_limit or 1))) * 100, 2),
        "today": {
            "deleted": deleted,
            "muted": muted,
            "banned": banned,
            "observed": observed,
            "joins": joins_24h,
            "enabled_metrics": enabled,
        },
        "yesterday": {
            "deleted": deleted_y,
            "muted": muted_y,
            "banned": banned_y,
            "observed": observed_y,
            "joins": joins_y,
        },
    }


@router.get("/activity/breakdown")
async def api_activity_breakdown(
    period: str = Query("today", regex="^(today|7d|14d|30d|180d|365d)$"),
    scope: str = Query("all", regex="^(all|own|delegated)$"),
    chat_id: int | None = Query(None, description="Опционально: одна группа/канал по id (должен быть в списке доступных)."),
    tz_offset_min: int = Query(0, ge=-840, le=840),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Агрегированная статистика удалений: по типам/часам/дням недели + список чатов.

    Источник правды — `moderation_logs`. Часовой пояс задаётся клиентом
    (`tz_offset_min` = -new Date().getTimezoneOffset()), чтобы графики
    «по часам» соответствовали локальному времени пользователя.
    """
    chats = await get_managed_chats(session, user_id)
    active_chats = [c for c in chats if not bool(getattr(c, "is_log_chat", False)) and bool(getattr(c, "is_active", True))]
    if scope == "own":
        active_chats = [c for c in active_chats if int(getattr(c, "owner_user_id", 0) or 0) == int(user_id)]
    elif scope == "delegated":
        active_chats = [c for c in active_chats if int(getattr(c, "owner_user_id", 0) or 0) != int(user_id)]
    allowed_ids = [int(c.id) for c in active_chats]
    if chat_id is not None:
        cid = int(chat_id)
        if cid not in allowed_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к чату")
        active_chats = [c for c in active_chats if int(c.id) == cid]
    chat_ids = [int(c.id) for c in active_chats]

    # Физические chat_id для событий (группа обсуждения канала и т.д.) → логический id в списке чатов.
    # Иначе ChatActivityEvent / журнал модерации ищутся по id канала, а в БД лежит id группы — «Сообщений: 0».
    chn_by_id: dict[int, Channel] = {}
    phys_to_logical: dict[int, int] = {}
    if active_chats:
        chn_ids = [int(c.id) for c in active_chats if str(getattr(c, "chat_kind", "") or "group").lower() == "channel"]
        if chn_ids:
            chn_rows = (await session.execute(select(Channel).where(Channel.id.in_(chn_ids)))).scalars().all()
            chn_by_id = {int(r.id): r for r in chn_rows}
        for c in active_chats:
            lg = int(c.id)
            for p in _activity_effective_ids_for_chat(c, chn_by_id):
                phys_to_logical[int(p)] = lg
    scope_ids = sorted(set(phys_to_logical.keys()) | set(chat_ids)) if chat_ids else []
    event_scope_ids = scope_ids if scope_ids else chat_ids

    now_utc = datetime.now(timezone.utc)
    tz_offset = timedelta(minutes=int(tz_offset_min or 0))
    now_local = now_utc + tz_offset
    today_local_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_local_start - tz_offset

    if period == "365d":
        since_utc = now_utc - timedelta(days=365)
    elif period == "180d":
        since_utc = now_utc - timedelta(days=180)
    elif period == "30d":
        since_utc = now_utc - timedelta(days=30)
    elif period == "14d":
        since_utc = now_utc - timedelta(days=14)
    elif period == "7d":
        since_utc = now_utc - timedelta(days=7)
    else:
        # "today" = с 00:00 локального времени пользователя (TZ через tz_offset_min).
        since_utc = today_start_utc

    by_reason: dict[str, int] = {}
    by_hour_period = [0] * 24
    by_hour_today = [0] * 24
    by_hour_by_reason: dict[str, list[int]] = {}
    by_weekday = [0] * 7
    heatmap_24x7 = [[0] * 24 for _ in range(7)]
    chat_deleted: dict[int, int] = {cid: 0 for cid in chat_ids}
    chat_last_at: dict[int, datetime] = {}
    total_deleted = 0
    total_today = 0
    examples_by_reason: dict[str, dict[str, int]] = {}
    # Если нет chat_activity_events, оценка активности по часам из журнала модерации (не «удаления отдельно»).
    mod_fallback_hour = [0] * 24
    # Те же события, что mod_fallback_hour, но с разбивкой день×час — для activity_heatmap при отсутствии ChatActivityEvent.
    mod_activity_heatmap = [[0] * 24 for _ in range(7)]

    def _normalize_example(reason: str, raw: str) -> str | None:
        """Превращает detail/message_text в короткий пример ключевого слова или префикса URL."""
        s = str(raw or "").strip()
        if not s:
            return None
        if reason == "link":
            # Пример вида http://, https://, t.me/, bit.ly, goo.gl
            low = s.lower()
            for marker in ("https://", "http://", "tg://"):
                if low.startswith(marker):
                    return marker
            # Для произвольной ссылки — отрезаем по первому "/"
            for marker in ("https://", "http://", "tg://"):
                idx = low.find(marker)
                if idx >= 0:
                    rest = low[idx + len(marker):]
                    host = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
                    if host:
                        return host[:40]
                    return marker
            host = low.split("/", 1)[0]
            return host[:40] if host else None
        # Слова: берём первое слово/ngramm длиной до 24
        token = s.lower().split("\n", 1)[0].strip()
        token = token.split(",", 1)[0].split(";", 1)[0].strip()
        if len(token) > 32:
            token = token[:32].rstrip() + "…"
        return token or None

    if chat_ids:
        rows_q = await session.execute(
            select(
                ModerationLog.chat_id,
                ModerationLog.reason,
                ModerationLog.action,
                ModerationLog.created_at,
                ModerationLog.detail,
                ModerationLog.message_text,
            ).where(
                ModerationLog.chat_id.in_(scope_ids if scope_ids else chat_ids),
                ModerationLog.created_at >= since_utc,
            )
        )
        for cid, reason, action, created_at, detail, message_text in rows_q.all():
            act = str(action or "").lower()
            if created_at is not None:
                if created_at.tzinfo is None:
                    _ca = created_at.replace(tzinfo=timezone.utc)
                else:
                    _ca = created_at
                _local_dt = _ca.astimezone(timezone.utc) + tz_offset
                _fh = max(0, min(23, int(_local_dt.hour)))
                if "observe" not in act:
                    mod_fallback_hour[_fh] += 1
                    _wd = max(0, min(6, int(_local_dt.weekday())))
                    mod_activity_heatmap[_wd][_fh] += 1
            if "observe" in act:
                continue
            base = (str(reason or "").strip() or "other").lower()
            if base.endswith("_newbie"):
                base = base[: -len("_newbie")]
            if base in ("link_blacklist", "global_bad_url"):
                base = "link"
            by_reason[base] = by_reason.get(base, 0) + 1
            total_deleted += 1
            cid_phys = int(cid or 0)
            cid_log = phys_to_logical.get(cid_phys, cid_phys)
            if cid_log in chat_deleted:
                chat_deleted[cid_log] = chat_deleted.get(cid_log, 0) + 1
            example = _normalize_example(base, detail or message_text)
            if example:
                bucket_e = examples_by_reason.setdefault(base, {})
                bucket_e[example] = bucket_e.get(example, 0) + 1
            if created_at is not None:
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                local_dt = created_at.astimezone(timezone.utc) + tz_offset
                hour = max(0, min(23, int(local_dt.hour)))
                by_hour_period[hour] += 1
                bucket = by_hour_by_reason.setdefault(base, [0] * 24)
                bucket[hour] += 1
                if created_at >= today_start_utc:
                    by_hour_today[hour] += 1
                    total_today += 1
                wd = max(0, min(6, int(local_dt.weekday())))
                heatmap_24x7[wd][hour] += 1
                by_weekday[wd] += 1
                prev = chat_last_at.get(cid_log)
                if prev is None or created_at > prev:
                    chat_last_at[cid_log] = created_at

    rules_q = await session.execute(select(Rule).where(Rule.chat_id.in_(chat_ids))) if chat_ids else None
    rules_list = list(rules_q.scalars().all()) if rules_q is not None else []

    def _filter_enabled(attr: str, default: bool) -> bool:
        if not rules_list:
            return default
        return any(bool(getattr(r, attr, default)) for r in rules_list)

    enabled_filters = {
        "profanity": _filter_enabled("filter_profanity_enabled", True),
        "jobs": _filter_enabled("filter_jobs_enabled", True),
        "casino": _filter_enabled("filter_casino_enabled", True),
        "ads": _filter_enabled("filter_ads_enabled", False),
        "insult": _filter_enabled("filter_insults_enabled", False),
        "racism": _filter_enabled("filter_racism_enabled", False),
        "nazi": _filter_enabled("filter_nazi_enabled", False),
        "vulgar": _filter_enabled("filter_vulgar_enabled", False),
        "link": (
            _filter_enabled("filter_links", True)
            and any(str(getattr(r, "filter_links_mode", "forbid") or "forbid").lower() != "allow" for r in rules_list)
        ) if rules_list else True,
        "stopword": True,
        "mention": _filter_enabled("filter_mentions", False),
        "media": (
            _filter_enabled("filter_media_mode", "allow") if False else any(
                str(getattr(r, "filter_media_mode", "allow") or "allow").lower() != "allow" for r in rules_list
            )
        ),
        "buttons": any(
            str(getattr(r, "filter_buttons_mode", "allow") or "allow").lower() != "allow" for r in rules_list
        ),
    }

    examples_out: dict[str, list[str]] = {}
    for reason, bucket in examples_by_reason.items():
        ranked = sorted(bucket.items(), key=lambda x: (-x[1], x[0]))[:6]
        examples_out[reason] = [w for w, _ in ranked]

    # === Подписки / отписки / сообщения / активные ============================================
    by_hour_joins = [0] * 24
    by_hour_leaves = [0] * 24
    by_hour_messages = [0] * 24
    activity_heatmap = [[0] * 24 for _ in range(7)]
    chat_joined: dict[int, int] = {cid: 0 for cid in chat_ids}
    chat_left: dict[int, int] = {cid: 0 for cid in chat_ids}
    chat_messages: dict[int, int] = {cid: 0 for cid in chat_ids}
    total_joined = 0
    total_left = 0
    total_messages = 0
    active_user_ids: set[int] = set()

    if chat_ids:
        joins_q = await session.execute(
            select(NewMember.chat_id, NewMember.joined_at).where(
                NewMember.chat_id.in_(event_scope_ids),
                NewMember.joined_at >= since_utc,
            )
        )
        for cid, joined_at in joins_q.all():
            if joined_at is None:
                continue
            if joined_at.tzinfo is None:
                joined_at = joined_at.replace(tzinfo=timezone.utc)
            local_dt = joined_at.astimezone(timezone.utc) + tz_offset
            hour = max(0, min(23, int(local_dt.hour)))
            by_hour_joins[hour] += 1
            total_joined += 1
            ci_phys = int(cid or 0)
            ci_log = phys_to_logical.get(ci_phys, ci_phys)
            if ci_log in chat_joined:
                chat_joined[ci_log] = chat_joined.get(ci_log, 0) + 1

        leaves_q = await session.execute(
            select(MemberLeft.chat_id, MemberLeft.left_at).where(
                MemberLeft.chat_id.in_(event_scope_ids),
                MemberLeft.left_at >= since_utc,
            )
        )
        for cid, left_at in leaves_q.all():
            if left_at is None:
                continue
            if left_at.tzinfo is None:
                left_at = left_at.replace(tzinfo=timezone.utc)
            local_dt = left_at.astimezone(timezone.utc) + tz_offset
            hour = max(0, min(23, int(local_dt.hour)))
            by_hour_leaves[hour] += 1
            total_left += 1
            ci_phys = int(cid or 0)
            ci_log = phys_to_logical.get(ci_phys, ci_phys)
            if ci_log in chat_left:
                chat_left[ci_log] = chat_left.get(ci_log, 0) + 1

        msg_q = await session.execute(
            select(ChatActivityEvent.chat_id, ChatActivityEvent.user_id, ChatActivityEvent.created_at).where(
                ChatActivityEvent.chat_id.in_(event_scope_ids),
                ChatActivityEvent.created_at >= since_utc,
            )
        )
        for cid, uid, created_at in msg_q.all():
            if created_at is None:
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            local_dt = created_at.astimezone(timezone.utc) + tz_offset
            hour = max(0, min(23, int(local_dt.hour)))
            wd = max(0, min(6, int(local_dt.weekday())))
            by_hour_messages[hour] += 1
            activity_heatmap[wd][hour] += 1
            total_messages += 1
            ci_phys = int(cid or 0)
            ci_log = phys_to_logical.get(ci_phys, ci_phys)
            if ci_log in chat_messages:
                chat_messages[ci_log] = chat_messages.get(ci_log, 0) + 1
            if uid:
                active_user_ids.add(int(uid))

        # Нет строк в chat_activity_events (старые деплои / только канал без маппинга): часовая активность из журнала модерации.
        if total_messages == 0 and any(mod_fallback_hour):
            by_hour_messages = list(mod_fallback_hour)
            total_messages = int(sum(mod_fallback_hour))
            activity_heatmap = [list(row) for row in mod_activity_heatmap]

    # Пик активности (по сообщениям)
    peak_idx = 0
    peak_val = 0
    for i, v in enumerate(by_hour_messages):
        if v > peak_val:
            peak_val = int(v)
            peak_idx = int(i)
    peak_hour = {
        "hour": peak_idx,
        "value": peak_val,
        "label": f"{peak_idx:02d}:00",
    } if peak_val > 0 else None

    chats_meta = []
    for c in active_chats:
        cid = int(c.id)
        username = (str(getattr(c, "username", "") or "").strip().lstrip("@") or None)
        kind = str(getattr(c, "chat_kind", "") or "group").lower()
        last_at = chat_last_at.get(cid)
        is_delegated = int(getattr(c, "owner_user_id", 0) or 0) != int(user_id)
        chats_meta.append({
            "id": cid,
            "title": (c.title or "").strip() or str(cid),
            "username": username,
            "kind": "channel" if kind == "channel" else "group",
            "is_active": bool(getattr(c, "is_active", True)),
            "is_delegated": is_delegated,
            "deleted": int(chat_deleted.get(cid, 0)),
            "joined": int(chat_joined.get(cid, 0)),
            "left": int(chat_left.get(cid, 0)),
            "messages": int(chat_messages.get(cid, 0)),
            "growth": int(chat_joined.get(cid, 0)) - int(chat_left.get(cid, 0)),
            "last_action_at": _format_dt(last_at) if last_at else None,
        })
    chats_meta.sort(key=lambda x: (-(int(x.get("messages") or 0)), -(int(x.get("deleted") or 0)), str(x.get("title") or "")))

    return {
        "period": period,
        "tz_offset_min": int(tz_offset_min or 0),
        "since": since_utc.isoformat(),
        "total_deleted": int(total_deleted),
        "total_today": int(total_today),
        "total_joined": int(total_joined),
        "total_left": int(total_left),
        "total_messages": int(total_messages),
        "active_users": int(len(active_user_ids)),
        "peak_hour": peak_hour,
        "by_reason": [{"reason": k, "count": int(v)} for k, v in sorted(by_reason.items(), key=lambda x: -x[1])],
        "by_hour": list(by_hour_period),
        "by_hour_today": list(by_hour_today),
        "by_hour_by_reason": {k: list(v) for k, v in by_hour_by_reason.items()},
        "by_hour_joins": list(by_hour_joins),
        "by_hour_leaves": list(by_hour_leaves),
        "by_hour_messages": list(by_hour_messages),
        "activity_heatmap_24x7": activity_heatmap,
        "by_weekday": list(by_weekday),
        "heatmap_24x7": heatmap_24x7,
        "chats": chats_meta,
        "chats_total": len(chats_meta),
        "enabled_filters": enabled_filters,
        "examples_by_reason": examples_out,
    }


async def _usernames_for_telegram_ids(session: AsyncSession, tg_ids: set[int]) -> dict[int, str | None]:
    """Username из users по telegram_id (для панели)."""
    ids = sorted({int(x) for x in tg_ids if int(x or 0) > 0})
    if not ids:
        return {}
    q = await session.execute(select(User.telegram_id, User.username).where(User.telegram_id.in_(ids)))
    out: dict[int, str | None] = {}
    for tid, un in q.all():
        u = (str(un or "").strip().lstrip("@") or None)
        out[int(tid)] = u
    return out


@router.get("/activity/journal")
async def api_activity_journal(
    chat_id: int | None = None,
    limit: int = 100,
    from_ts: str | None = None,
    to_ts: str | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Журнал действий защиты в реальном времени."""
    chats = await get_managed_chats(session, user_id)
    active_chat_ids = [int(c.id) for c in chats if not bool(getattr(c, "is_log_chat", False))]
    # Fallback: если активных нет (или они временно сброшены), всё равно вернём список доступных групп,
    # чтобы UI отчётов не показывал "Групп пока нет".
    if not active_chat_ids:
        manager_sub = select(ChatManager.chat_id).where(ChatManager.user_id == int(user_id))
        invite_sub = select(ChatManagerInvite.chat_id).where(
            ChatManagerInvite.status == "connected",
            (ChatManagerInvite.connected_user_id == int(user_id)) | (ChatManagerInvite.target_telegram_id == int(user_id)),
        )
        managed_sub = manager_sub.union(invite_sub).subquery()
        fallback_rows = (
            await session.execute(
                select(Chat)
                .where(
                    Chat.is_log_chat == False,  # noqa: E712
                    (Chat.owner_user_id == int(user_id)) | (Chat.id.in_(select(managed_sub.c.chat_id))),
                )
                .order_by(Chat.id.asc())
            )
        ).scalars().all()
        chats_out = [
            {
                "id": int(c.id),
                "title": (c.title or "").strip() or str(c.id),
                "is_shared": int(getattr(c, "owner_user_id", 0) or 0) != int(user_id),
            }
            for c in fallback_rows
            if not bool(getattr(c, "is_log_chat", False))
        ]
        return {"items": [], "chats": chats_out}
    if chat_id is not None and int(chat_id) not in active_chat_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к чату")
    q = select(ModerationLog).where(ModerationLog.chat_id.in_(active_chat_ids))
    if chat_id is not None:
        q = q.where(ModerationLog.chat_id == int(chat_id))
    from_dt = _parse_query_datetime(from_ts)
    to_dt = _parse_query_datetime(to_ts)
    if from_dt is not None and to_dt is not None:
        if from_dt >= to_dt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный период: начало позже конца")
        if (to_dt - from_dt).days > 400:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Период не более 400 суток")
        q = q.where(ModerationLog.created_at >= from_dt, ModerationLog.created_at <= to_dt)
    lim = max(1, min(int(limit or 100), 500 if (from_dt and to_dt) else 300))
    q = q.order_by(ModerationLog.created_at.desc()).limit(lim)
    rows_q = await session.execute(q)
    rows = rows_q.scalars().all()
    chat_title_map = {int(c.id): ((c.title or "").strip() or str(c.id)) for c in chats}
    uid_set = {int(getattr(r, "user_id", 0) or 0) for r in rows if int(getattr(r, "user_id", 0) or 0) > 0}
    un_map = await _usernames_for_telegram_ids(session, uid_set)
    items = []
    for r in rows:
        uid = int(getattr(r, "user_id", 0) or 0)
        msg_t = str(getattr(r, "message_text", None) or "").strip()
        preview = None
        if msg_t:
            preview = (msg_t[:280] + "…") if len(msg_t) > 280 else msg_t
        det_raw = getattr(r, "detail", None)
        det = str(det_raw).strip() if det_raw is not None else ""
        items.append({
            "created_at": _format_dt(getattr(r, "created_at", None)),
            "chat_id": int(getattr(r, "chat_id", 0) or 0),
            "chat_title": str(chat_title_map.get(int(getattr(r, "chat_id", 0) or 0), str(getattr(r, "chat_id", "")))),
            "action": str(getattr(r, "action", "") or ""),
            "reason": str(getattr(r, "reason", "") or ""),
            "user_id": uid,
            "username": un_map.get(uid),
            "detail": det or None,
            "message_preview": preview,
        })
    chats_out = [
        {
            "id": int(c.id),
            "title": (c.title or "").strip() or str(c.id),
            "is_shared": int(getattr(c, "owner_user_id", 0) or 0) != int(user_id),
        }
        for c in chats
        if not bool(getattr(c, "is_log_chat", False))
    ]
    return {"items": items, "chats": chats_out}


def _activity_effective_ids_for_chat(chat: Chat, chn_by_id: dict[int, Channel]) -> list[int]:
    """Физические id чатов для событий: у канала — группа обсуждения, если привязана."""
    cid = int(chat.id)
    kind = str(getattr(chat, "chat_kind", "") or "group").lower()
    if kind == "channel":
        row = chn_by_id.get(cid)
        if row and getattr(row, "chat_id", None):
            return [int(row.chat_id)]
        return [cid]
    return [cid]


def _activity_slot_index(dt: datetime, bounds: list[tuple[datetime, datetime]]) -> int | None:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    for i, (a, b) in enumerate(bounds):
        if a <= dt < b:
            return i
    return None


def _activity_risk_index(spam_mod: int, mod_total: int, joins: int) -> dict:
    """Три уровня для UI: спокойно / умеренно / под ударом (по спам-срабатываниям и нагрузке)."""
    score = int(spam_mod) * 3 + int(mod_total) + int(joins) * 2
    if spam_mod <= 1 and mod_total <= 2 and joins <= 2:
        return {"key": "ok", "label": "в норме", "score": round(float(score), 1)}
    if spam_mod <= 4 and mod_total <= 10 and joins <= 8:
        return {"key": "moderate", "label": "умеренно", "score": round(float(score), 1)}
    return {"key": "attack", "label": "группа под нагрузкой", "score": round(float(score), 1)}


def _infer_gender_from_first_name(first_name: str | None) -> str:
    """Грубая эвристика пола по имени (ru/ua/en): male/female/unknown."""
    n = str(first_name or "").strip().lower().replace("ё", "е")
    if not n:
        return "unknown"
    n = n.split()[0].strip(".,!?:;()[]{}\"'")
    if not n:
        return "unknown"
    male_names = {
        "александр", "дмитрий", "сергей", "андрей", "алексей", "максим", "иван", "илья", "никита",
        "евгений", "артем", "денис", "михаил", "владимир", "павел", "роман", "кирилл", "тимур",
        "oleg", "alex", "michael", "david", "daniel", "andrew", "ivan",
    }
    female_names = {
        "анна", "мария", "елена", "ольга", "наталья", "екатерина", "софия", "полина", "алиса",
        "виктория", "татьяна", "ксения", "юлия", "ирина", "светлана", "вероника", "карина", "дарья",
        "anna", "maria", "elena", "olga", "sofia", "julia", "victoria",
    }
    if n in male_names:
        return "male"
    if n in female_names:
        return "female"
    if n.endswith(("а", "я")) and n not in {"никита", "илья", "кузьма", "фома"}:
        return "female"
    if n.endswith(("й", "н", "р", "г", "д", "м", "б", "в", "п", "с", "т", "к", "л", "х")):
        return "male"
    return "unknown"


@router.get("/activity/hours")
async def api_activity_hours(
    chat_id: int | None = None,
    hours: int = 24,
    from_ts: str | None = None,
    to_ts: str | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Активность по слотам времени (UTC): модерация, вступления, спам-метрики. Полоска = доля от макс. в периоде."""
    from collections import defaultdict

    chats = await get_managed_chats(session, user_id)
    active_chats = [c for c in chats if not bool(getattr(c, "is_log_chat", False))]
    active_chat_ids = [int(c.id) for c in active_chats]
    if not active_chat_ids:
        return {
            "slots": [],
            "hours": [],
            "totals": {
                "events": 0,
                "moderation": 0,
                "joins": 0,
                "spam_moderation": 0,
                "spam_deleted": 0,
                "messages_with_guard": 0,
            },
            "segment_joins": {"channel": 0, "group": 0, "linked_group": 0},
            "segment_spam": {"channel": 0, "group": 0, "linked_group": 0},
            "chats": [],
            "selected_chat_id": int(chat_id) if chat_id else None,
            "bucket": "hour",
            "bar_scale_max": 1,
            "bar_scale_note": "100% = максимум событий в одном слоте выбранного периода (не лимит Telegram).",
            "period_from": None,
            "period_to": None,
        }
    cid = int(chat_id) if chat_id is not None else None
    if cid is not None and cid not in active_chat_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к чату")

    now_utc = datetime.now(timezone.utc)
    from_dt = _parse_query_datetime(from_ts)
    to_dt = _parse_query_datetime(to_ts)
    if from_dt is not None and to_dt is not None:
        if from_dt >= to_dt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный период: начало позже конца")
        if (to_dt - from_dt).days > 400:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Период не более 400 суток")
        since = from_dt
        until = to_dt
    else:
        h = max(1, min(int(hours or 24), 24 * 180))
        since = now_utc - timedelta(hours=h)
        until = now_utc

    span_sec = max(1.0, (until - since).total_seconds())
    span_hours = span_sec / 3600.0
    max_hourly_slots = 168
    if span_hours <= float(max_hourly_slots):
        step = timedelta(hours=1)
        bucket = "hour"
    else:
        step = timedelta(days=1)
        bucket = "day"

    slot_bounds: list[tuple[datetime, datetime]] = []
    t = since.astimezone(timezone.utc)
    until_u = until.astimezone(timezone.utc)
    while t < until_u:
        end = min(t + step, until_u)
        slot_bounds.append((t, end))
        t = end
    if not slot_bounds:
        slot_bounds = [(since.astimezone(timezone.utc), until_u)]

    chn_ids = [int(c.id) for c in active_chats if str(getattr(c, "chat_kind", "") or "group").lower() == "channel"]
    chn_by_id: dict[int, Channel] = {}
    if chn_ids:
        chn_rows = (await session.execute(select(Channel).where(Channel.id.in_(chn_ids)))).scalars().all()
        chn_by_id = {int(r.id): r for r in chn_rows}

    discussion_parent: dict[int, int] = {}
    for c in active_chats:
        if str(getattr(c, "chat_kind", "") or "group").lower() != "channel":
            continue
        row = chn_by_id.get(int(c.id))
        if row and getattr(row, "chat_id", None):
            discussion_parent[int(row.chat_id)] = int(c.id)

    logical_targets: dict[int, set[int]] = {}
    phys_union: set[int] = set()
    for c in active_chats:
        lid = int(c.id)
        for p in _activity_effective_ids_for_chat(c, chn_by_id):
            phys_union.add(int(p))
            logical_targets.setdefault(int(p), set()).add(lid)

    if cid is not None:
        one = await session.get(Chat, int(cid))
        if not one:
            raise HTTPException(status_code=404, detail="Chat not found")
        phys_union = set(_activity_effective_ids_for_chat(one, chn_by_id))
        logical_targets = {p: {int(cid)} for p in phys_union}

    if not phys_union:
        return {
            "slots": [],
            "hours": [],
            "bucket": bucket,
            "bar_scale_max": 1,
            "bar_scale_note": "",
            "totals": {
                "events": 0,
                "moderation": 0,
                "joins": 0,
                "spam_moderation": 0,
                "spam_deleted": 0,
                "messages_with_guard": 0,
            },
            "segment_joins": {"channel": 0, "group": 0, "linked_group": 0},
            "segment_spam": {"channel": 0, "group": 0, "linked_group": 0},
            "spike_hours": [],
            "spike_meta": {"avg_events_per_slot": 0.0, "peak": {"index": 0, "label": "", "events": 0}},
            "period_from": _format_dt(since),
            "period_to": _format_dt(until),
            "selected_chat_id": cid,
            "chats": [],
        }

    spam_reasons = set(SPAM_MODERATION_REASONS)

    mods_rows = (
        await session.execute(
            select(ModerationLog.created_at, ModerationLog.chat_id, ModerationLog.reason, ModerationLog.action).where(
                ModerationLog.chat_id.in_(list(phys_union)),
                ModerationLog.created_at >= since,
                ModerationLog.created_at <= until,
            )
        )
    ).all()
    joins_rows = (
        await session.execute(
            select(NewMember.joined_at, NewMember.chat_id, NewMember.user_id).where(
                NewMember.chat_id.in_(list(phys_union)),
                NewMember.joined_at >= since,
                NewMember.joined_at <= until,
            )
        )
    ).all()

    n_slots = len(slot_bounds)
    mod_cnt = [0] * n_slots
    join_cnt = [0] * n_slots
    spam_mod_cnt = [0] * n_slots
    spam_del_cnt = [0] * n_slots
    mods_by_logical: dict[int, int] = defaultdict(int)
    joins_by_logical: dict[int, int] = defaultdict(int)
    spam_by_logical: dict[int, int] = defaultdict(int)

    for dtv, chatv, reason, action in mods_rows:
        dt = dtv if getattr(dtv, "tzinfo", None) else dtv.replace(tzinfo=timezone.utc)
        si = _activity_slot_index(dt, slot_bounds)
        if si is None:
            continue
        phys = int(chatv or 0)
        mod_cnt[si] += 1
        rs = str(reason or "").strip().lower()
        act = str(action or "").strip().lower()
        if rs in spam_reasons:
            spam_mod_cnt[si] += 1
            if act == "delete":
                spam_del_cnt[si] += 1
        for lg in logical_targets.get(phys, set()):
            mods_by_logical[int(lg)] += 1
            if rs in spam_reasons:
                spam_by_logical[int(lg)] += 1

    for dtv, chatv, _uid in joins_rows:
        dt = dtv if getattr(dtv, "tzinfo", None) else dtv.replace(tzinfo=timezone.utc)
        si = _activity_slot_index(dt, slot_bounds)
        if si is None:
            continue
        phys = int(chatv or 0)
        join_cnt[si] += 1
        for lg in logical_targets.get(phys, set()):
            joins_by_logical[int(lg)] += 1

    chat_by_id = {int(c.id): c for c in active_chats}

    def _ui_segment_for_chat(chat_obj: Chat) -> str:
        k = str(getattr(chat_obj, "chat_kind", "") or "group").lower()
        if k == "channel":
            return "channel"
        if int(chat_obj.id) in discussion_parent:
            return "linked_group"
        return "group"

    segment_joins = {"channel": 0, "group": 0, "linked_group": 0}
    for _dtv, chatv, _uid in joins_rows:
        phys = int(chatv or 0)
        for lg in logical_targets.get(phys, set()):
            co = chat_by_id.get(int(lg))
            if not co:
                continue
            seg = _ui_segment_for_chat(co)
            if seg in segment_joins:
                segment_joins[seg] += 1

    segment_spam = {"channel": 0, "group": 0, "linked_group": 0}
    for _dtv, chatv, reason, _action in mods_rows:
        phys = int(chatv or 0)
        rs = str(reason or "").strip().lower()
        if rs not in spam_reasons:
            continue
        for lg in logical_targets.get(phys, set()):
            co = chat_by_id.get(int(lg))
            if not co:
                continue
            seg = _ui_segment_for_chat(co)
            if seg in segment_spam:
                segment_spam[seg] += 1

    slots_out: list[dict] = []
    total_mod = total_join = total_spam = total_spam_del = 0
    spike_hours: list[dict] = []
    for i, (a, b) in enumerate(slot_bounds):
        m = int(mod_cnt[i] or 0)
        j = int(join_cnt[i] or 0)
        sm = int(spam_mod_cnt[i] or 0)
        sd = int(spam_del_cnt[i] or 0)
        ev = m + j
        total_mod += m
        total_join += j
        total_spam += sm
        total_spam_del += sd
        spike_score = round(float(j * 2 + m), 2)
        is_spike = j >= 3 and m >= 3
        if is_spike:
            spike_hours.append(
                {
                    "slot_index": i,
                    "label": _format_dt(a),
                    "joins": j,
                    "moderation": m,
                    "score": spike_score,
                }
            )
        risk = _activity_risk_index(sm, m, j)
        slots_out.append(
            {
                "index": i,
                "slot_start": _format_dt(a),
                "slot_end": _format_dt(b),
                "label": a.strftime("%d.%m %H:%M") + " — " + b.strftime("%d.%m %H:%M"),
                "moderation": m,
                "joins": j,
                "events": ev,
                "spam_moderation": sm,
                "spam_deleted": sd,
                "messages_with_guard": m,
                "spike_score": spike_score,
                "is_spike": is_spike,
                "risk": risk,
            }
        )

    bar_scale_max = max((int(s["events"] or 0) for s in slots_out), default=1)
    bar_scale_max = max(1, bar_scale_max)
    avg_events = round((total_mod + total_join) / float(max(1, n_slots)), 2)
    peak_row = max(slots_out, key=lambda x: int(x.get("events", 0) or 0), default={"index": 0, "label": "", "events": 0})

    chats_out = []
    for c in active_chats:
        cid_cur = int(c.id)
        kind = str(getattr(c, "chat_kind", "") or "group").lower()
        seg = "group"
        parent_channel_id = None
        if kind == "channel":
            seg = "channel"
        elif cid_cur in discussion_parent:
            seg = "linked_group"
            parent_channel_id = int(discussion_parent[cid_cur])
        members_count = None
        try:
            info = await tg_get_chat(cid_cur)
            if isinstance(info, dict):
                mc = info.get("member_count")
                members_count = int(mc) if mc is not None else None
        except Exception:
            members_count = None
        eff = _activity_effective_ids_for_chat(c, chn_by_id)
        chats_out.append(
            {
                "id": cid_cur,
                "title": (c.title or "").strip() or str(c.id),
                "chat_kind": kind,
                "is_shared": int(getattr(c, "owner_user_id", 0) or 0) != int(user_id),
                "ui_segment": seg,
                "parent_channel_id": parent_channel_id,
                "stats_chat_ids": eff,
                "joins": int(joins_by_logical.get(cid_cur, 0) or 0),
                "moderation": int(mods_by_logical.get(cid_cur, 0) or 0),
                "spam_moderation": int(spam_by_logical.get(cid_cur, 0) or 0),
                "members_count": members_count,
                "connected_at": _format_dt(getattr(c, "created_at", None)),
                "last_activity_at": _format_dt(getattr(c, "last_activity_at", None)),
                "messages_checked": int(getattr(c, "messages_checked", 0) or 0),
                "messages_deleted": int(getattr(c, "messages_deleted", 0) or 0),
                "users_banned": int(getattr(c, "users_banned", 0) or 0),
            }
        )

    legacy_hours = []
    if bucket == "hour" and n_slots <= 24:
        by_h = defaultdict(int)
        for s in slots_out:
            try:
                hs = datetime.fromisoformat(str(s["slot_start"]).replace("Z", "+00:00"))
                by_h[int(hs.astimezone(timezone.utc).hour)] += int(s.get("events") or 0)
            except Exception:
                continue
        for h in range(24):
            legacy_hours.append({"hour": h, "label": f"{h:02d}:00", "events": int(by_h.get(h, 0) or 0), "moderation": 0, "joins": 0})

    return {
        "slots": slots_out,
        "hours": legacy_hours,
        "bucket": bucket,
        "bar_scale_max": int(bar_scale_max),
        "bar_scale_note": "100% полоски = самый загруженный слот в выбранном периоде (относительная шкала, не лимит Telegram).",
        "totals": {
            "events": total_mod + total_join,
            "moderation": total_mod,
            "joins": total_join,
            "spam_moderation": total_spam,
            "spam_deleted": total_spam_del,
            "messages_with_guard": total_mod,
        },
        "spike_hours": spike_hours,
        "spike_meta": {
            "avg_events_per_slot": avg_events,
            "peak": {
                "index": int(peak_row.get("index", 0) or 0),
                "label": str(peak_row.get("label", "") or ""),
                "events": int(peak_row.get("events", 0) or 0),
            },
        },
        "period_from": _format_dt(since),
        "period_to": _format_dt(until),
        "selected_chat_id": cid,
        "chats": chats_out,
        "segment_joins": segment_joins,
        "segment_spam": segment_spam,
    }


@router.get("/activity/slot-detail")
async def api_activity_slot_detail(
    from_ts: str,
    to_ts: str,
    chat_id: int | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Детализация по интервалу: вступившие и строки модерации (для модалок «подробнее»)."""
    chats = await get_managed_chats(session, user_id)
    active_chats = [c for c in chats if not bool(getattr(c, "is_log_chat", False))]
    active_ids = {int(c.id) for c in active_chats}
    if not active_ids:
        return {"joins": [], "moderation": [], "chats": []}
    cid = int(chat_id) if chat_id is not None else None
    if cid is not None and cid not in active_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к чату")
    a = _parse_query_datetime(from_ts)
    b = _parse_query_datetime(to_ts)
    if not a or not b or a >= b:
        raise HTTPException(status_code=400, detail="Нужны корректные from_ts и to_ts")
    if (b - a).total_seconds() > 86400 * 2 + 3600:
        raise HTTPException(status_code=400, detail="Интервал не более ~49 часов для детализации")

    chn_ids = [int(c.id) for c in active_chats if str(getattr(c, "chat_kind", "") or "group").lower() == "channel"]
    chn_by_id: dict[int, Channel] = {}
    if chn_ids:
        chn_rows = (await session.execute(select(Channel).where(Channel.id.in_(chn_ids)))).scalars().all()
        chn_by_id = {int(r.id): r for r in chn_rows}

    if cid is not None:
        one = await session.get(Chat, int(cid))
        phys = set(_activity_effective_ids_for_chat(one, chn_by_id)) if one else set()
    else:
        phys = set()
        for c in active_chats:
            for p in _activity_effective_ids_for_chat(c, chn_by_id):
                phys.add(int(p))
    if not phys:
        return {"joins": [], "moderation": [], "chats": []}

    jrows = (
        await session.execute(
            select(NewMember.joined_at, NewMember.chat_id, NewMember.user_id)
            .where(NewMember.chat_id.in_(list(phys)), NewMember.joined_at >= a, NewMember.joined_at <= b)
            .order_by(NewMember.joined_at.desc())
            .limit(200)
        )
    ).all()
    mrows = (
        await session.execute(
            select(ModerationLog.created_at, ModerationLog.chat_id, ModerationLog.user_id, ModerationLog.action, ModerationLog.reason)
            .where(ModerationLog.chat_id.in_(list(phys)), ModerationLog.created_at >= a, ModerationLog.created_at <= b)
            .order_by(ModerationLog.created_at.desc())
            .limit(200)
        )
    ).all()
    chat_title_map = {int(c.id): ((c.title or "").strip() or str(c.id)) for c in active_chats}
    all_uids: set[int] = set()
    for r in jrows:
        all_uids.add(int(r[2] or 0))
    for r in mrows:
        all_uids.add(int(r[2] or 0))
    un_map = await _usernames_for_telegram_ids(session, all_uids)
    joins_out = [
        {
            "joined_at": _format_dt(r[0]),
            "chat_id": int(r[1] or 0),
            "chat_title": str(chat_title_map.get(int(r[1] or 0), str(r[1]))),
            "user_id": int(r[2] or 0),
            "username": un_map.get(int(r[2] or 0)),
        }
        for r in jrows
    ]
    mod_out = [
        {
            "created_at": _format_dt(r[0]),
            "chat_id": int(r[1] or 0),
            "chat_title": str(chat_title_map.get(int(r[1] or 0), str(r[1]))),
            "user_id": int(r[2] or 0),
            "username": un_map.get(int(r[2] or 0)),
            "action": str(r[3] or ""),
            "reason": str(r[4] or ""),
        }
        for r in mrows
    ]
    chats_mini = [{"id": int(c.id), "title": (c.title or "").strip() or str(c.id)} for c in active_chats]
    return {"joins": joins_out, "moderation": mod_out, "chats": chats_mini}


@router.get("/activity/audience-gender")
async def api_activity_audience_gender(
    chat_id: int | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Оценка пола аудитории по first_name среди вступивших участников."""
    chats = await get_managed_chats(session, user_id)
    active_chats = [c for c in chats if not bool(getattr(c, "is_log_chat", False))]
    active_ids = {int(c.id) for c in active_chats}
    if not active_ids:
        return {
            "male": 0,
            "female": 0,
            "unknown": 0,
            "male_pct": 0.0,
            "female_pct": 0.0,
            "known_total": 0,
            "audience_total": 0,
            "is_estimate": True,
        }
    cid = int(chat_id) if chat_id is not None else None
    if cid is not None and cid not in active_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к чату")

    chn_ids = [int(c.id) for c in active_chats if str(getattr(c, "chat_kind", "") or "group").lower() == "channel"]
    chn_by_id: dict[int, Channel] = {}
    if chn_ids:
        chn_rows = (await session.execute(select(Channel).where(Channel.id.in_(chn_ids)))).scalars().all()
        chn_by_id = {int(r.id): r for r in chn_rows}
    logical = [c for c in active_chats if cid is None or int(c.id) == cid]
    stats_chat_ids: set[int] = set()
    audience_total = 0
    for c in logical:
        audience_total += int(getattr(c, "members_count", 0) or 0)
        for x in _activity_effective_ids_for_chat(c, chn_by_id):
            stats_chat_ids.add(int(x))
    if not stats_chat_ids:
        return {
            "male": 0,
            "female": 0,
            "unknown": 0,
            "male_pct": 0.0,
            "female_pct": 0.0,
            "known_total": 0,
            "audience_total": int(audience_total),
            "is_estimate": True,
        }

    rows = (
        await session.execute(
            select(User.first_name)
            .join(NewMember, NewMember.user_id == User.telegram_id)
            .where(NewMember.chat_id.in_(sorted(stats_chat_ids)))
            .group_by(User.telegram_id, User.first_name)
        )
    ).all()
    male = 0
    female = 0
    unknown = 0
    for (first_name,) in rows:
        g = _infer_gender_from_first_name(first_name)
        if g == "male":
            male += 1
        elif g == "female":
            female += 1
        else:
            unknown += 1
    known_total = int(male + female)
    male_pct = round((male / known_total) * 100, 1) if known_total > 0 else 0.0
    female_pct = round((female / known_total) * 100, 1) if known_total > 0 else 0.0
    return {
        "male": int(male),
        "female": int(female),
        "unknown": int(unknown),
        "male_pct": float(male_pct),
        "female_pct": float(female_pct),
        "known_total": int(known_total),
        "audience_total": int(audience_total),
        "is_estimate": True,
    }


@router.get("/owner/join-report-settings")
async def api_owner_join_report_settings_get(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    st = await session.get(OwnerJoinReportSetting, int(user_id))
    raw = str(getattr(st, "periods_csv", "") or "")
    periods = [x.strip().lower() for x in raw.split(",") if x.strip()]
    periods = [x for x in periods if x in {"day", "3d", "week", "month"}]
    return {"periods": periods}


@router.post("/owner/join-report-settings")
async def api_owner_join_report_settings_set(
    body: dict | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    arr = []
    if isinstance(body, dict):
        arr_raw = body.get("periods")
        if isinstance(arr_raw, (list, tuple)):
            arr = [str(x).strip().lower() for x in arr_raw]
    allowed = {"day", "3d", "week", "month"}
    periods: list[str] = []
    for p in arr:
        if p in allowed and p not in periods:
            periods.append(p)
    st = await session.get(OwnerJoinReportSetting, int(user_id))
    if not st:
        st = OwnerJoinReportSetting(telegram_user_id=int(user_id), periods_csv=",".join(periods))
    else:
        st.periods_csv = ",".join(periods)
    session.add(st)
    await session.commit()
    return {"ok": True, "periods": periods}


@router.get("/activity/group-breakdown")
async def api_activity_group_breakdown(
    chat_id: int,
    hours: int = 24,
    from_ts: str | None = None,
    to_ts: str | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Сводка срабатываний по типам фильтров для одной группы (по moderation_logs)."""
    chats = await get_managed_chats(session, user_id)
    active_ids = [int(c.id) for c in chats if not bool(getattr(c, "is_log_chat", False))]
    if int(chat_id) not in active_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к чату")
    now = datetime.now(timezone.utc)
    from_dt = _parse_query_datetime(from_ts)
    to_dt = _parse_query_datetime(to_ts)
    if from_dt is not None and to_dt is not None:
        if from_dt >= to_dt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный период: начало позже конца")
        if (to_dt - from_dt).days > 400:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Период не более 400 суток")
        since = from_dt
        until = to_dt
        h = 0
        period_mode = "range"
    else:
        h = max(1, min(int(hours or 24), 8760))
        since = now - timedelta(hours=h)
        until = now
        period_mode = "hours"
    user = await get_or_create_user(session, user_id)
    is_premium = _is_user_premium_now(user, now)

    q = await session.execute(
        select(ModerationLog.reason, func.count(ModerationLog.id)).where(
            ModerationLog.chat_id == int(chat_id),
            ModerationLog.created_at >= since,
            ModerationLog.created_at <= until,
        ).group_by(ModerationLog.reason)
    )
    counts: dict[str, int] = {}
    for row in q.all():
        r = str(row[0] or "").strip().lower()
        counts[r] = int(row[1] or 0)

    def c(*keys: str) -> int:
        return sum(int(counts.get(k, 0) or 0) for k in keys)

    newbie_hits = sum(v for k, v in counts.items() if k.endswith("_newbie"))

    buckets = [
        {"key": "links", "label": "Ссылки", "count": c("link", "link_newbie"), "premium": False, "tone": "emerald"},
        {"key": "media", "label": "Медиа / стикеры", "count": c("media", "media_newbie"), "premium": False, "tone": "emerald"},
        {"key": "buttons", "label": "Сообщения с кнопками", "count": c("buttons", "buttons_newbie"), "premium": False, "tone": "rose"},
        {"key": "mentions", "label": "Упоминания", "count": c("mention", "mention_newbie"), "premium": False, "tone": "emerald"},
        {"key": "stopwords", "label": "Стоп-слова", "count": c("stopword", "stopword_newbie"), "premium": False, "tone": "rose"},
        {"key": "profanity", "label": "Мат (словарь)", "count": c("profanity", "profanity_newbie"), "premium": False, "tone": "rose"},
        {"key": "jobs", "label": "Подработки", "count": c("jobs", "jobs_newbie"), "premium": False, "tone": "amber"},
        {"key": "casino", "label": "Казино / ставки", "count": c("casino", "casino_newbie"), "premium": False, "tone": "amber"},
        {"key": "silence", "label": "Режим тишины", "count": c("silence"), "premium": True, "tone": "violet"},
        {"key": "newbie_mode", "label": "Срабатывания для новичков", "count": int(newbie_hits or 0), "premium": True, "tone": "violet"},
        {"key": "antinakrutka", "label": "Антинакрутка", "count": 0, "premium": True, "tone": "slate", "note": "События не пишутся в эту статистику"},
        {"key": "global_antispam", "label": "Глобальная антиспам база", "count": 0, "premium": True, "tone": "slate", "note": "События не пишутся в эту статистику"},
    ]
    chat_title = ""
    for cht in chats:
        if int(cht.id) == int(chat_id):
            chat_title = (cht.title or "").strip() or str(chat_id)
            break
    return {
        "chat_id": int(chat_id),
        "chat_title": chat_title,
        "hours": int(h) if period_mode == "hours" else None,
        "period_mode": period_mode,
        "period_from": _format_dt(since),
        "period_to": _format_dt(until),
        "is_premium": is_premium,
        "buckets": buckets,
    }


@router.post("/history/payments/receipt")
async def api_history_payment_receipt(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Отправить чек на email по записи оплаты пользователя.
    Body: { payment_id: number, email: string, full_name?: string }
    """
    payment_id = int(body.get("payment_id") or 0)
    email_to = (body.get("email") or "").strip()
    full_name = (body.get("full_name") or "").strip()
    if payment_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payment_id required")
    if not email_to or "@" not in email_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Введите корректный email")
    user = await get_or_create_user(session, user_id)
    q = await session.execute(
        select(Payment).where(Payment.id == payment_id, Payment.user_id == user.id).limit(1)
    )
    p = q.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платеж не найден")

    smtp_host = (os.getenv("SMTP_HOST") or "").strip()
    smtp_port = int((os.getenv("SMTP_PORT") or "587").strip())
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_pass = (os.getenv("SMTP_PASS") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or smtp_user or "").strip()
    if not smtp_host or not smtp_from:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис отправки чеков на email временно недоступен",
        )

    created = _format_dt(getattr(p, "created_at", None)) or "—"
    amount = float(getattr(p, "amount", 0.0) or 0.0)
    months = int(getattr(p, "months", 0) or 0)
    provider = str(getattr(p, "provider", "") or "yookassa")
    pay_ext = str(getattr(p, "payment_id", "") or "—")
    fio = full_name or "Пользователь"
    text = (
        "Чек оплаты Guard\n\n"
        f"Покупатель: {fio}\n"
        f"Дата: {created}\n"
        f"Сумма: {amount:.2f} RUB\n"
        f"Период: {months} мес.\n"
        f"Способ оплаты: {provider}\n"
        f"ID платежа: {pay_ext}\n"
    )
    msg = EmailMessage()
    msg["Subject"] = "Чек оплаты Guard"
    msg["From"] = smtp_from
    msg["To"] = email_to
    msg.set_content(text)

    def _send_mail():
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
            try:
                s.starttls()
            except Exception:
                pass
            if smtp_user and smtp_pass:
                s.login(smtp_user, smtp_pass)
            s.send_message(msg)

    try:
        await asyncio.to_thread(_send_mail)
    except Exception:
        _log.exception("send receipt email failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить чек")
    return {"ok": True}


# ---------- Admin: глобальная база плохих URL ----------
@router.get("/admin/global-bad-urls")
async def api_admin_global_bad_urls_list(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Полный админ: общая база Guard + персональные базы всех владельцев (только просмотр чужих)."""
    from collections import defaultdict

    await _require_admin_user(session, int(user_id))
    res = await session.execute(
        select(GlobalBadUrlPattern.pattern, GlobalBadUrlPattern.note).order_by(GlobalBadUrlPattern.pattern.asc())
    )
    system = [{"pattern": str(r[0]), "note": str(r[1] or "")} for r in res.all() if r[0]]
    uq = await session.execute(
        select(
            UserGlobalBadUrlPattern.owner_telegram_id,
            UserGlobalBadUrlPattern.pattern,
            UserGlobalBadUrlPattern.note,
        ).order_by(UserGlobalBadUrlPattern.owner_telegram_id.asc(), UserGlobalBadUrlPattern.pattern.asc())
    )
    grouped: dict[int, list] = defaultdict(list)
    owner_ids: set[int] = set()
    for row in uq.all():
        tid = int(row[0] or 0)
        pat = str(row[1] or "").strip()
        if tid <= 0 or not pat:
            continue
        grouped[tid].append({"pattern": pat, "note": str(row[2] or "")})
        owner_ids.add(tid)
    users_map: dict[int, User] = {}
    if owner_ids:
        urows = (await session.execute(select(User).where(User.telegram_id.in_(list(owner_ids))))).scalars().all()
        users_map = {int(getattr(u, "telegram_id", 0) or 0): u for u in urows if int(getattr(u, "telegram_id", 0) or 0) > 0}
    user_bases = []
    for tid in sorted(grouped.keys()):
        u = users_map.get(tid)
        user_bases.append(
            {
                "owner_telegram_id": tid,
                "owner_username": str(getattr(u, "username", "") or "") if u else "",
                "owner_first_name": str(getattr(u, "first_name", "") or "") if u else "",
                "items": grouped[tid],
            }
        )
    return {"system": system, "user_bases": user_bases}


@router.post("/admin/global-bad-urls")
async def api_admin_global_bad_urls_add(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.whitelist import is_valid_trusted_pattern, normalize_trusted_link_pattern
    from app.services.global_bad_urls import invalidate_global_bad_url_cache

    await _require_admin_user(session, int(user_id))
    raw_in = str(body.get("pattern") or "")
    pat = normalize_trusted_link_pattern(raw_in)
    if not pat or not is_valid_trusted_pattern(raw_in):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный шаблон. Примеры: evil.com, t.me/spam_channel",
        )
    note = (str(body.get("note") or "").strip() or None)[:255]
    session.add(GlobalBadUrlPattern(pattern=pat, note=note))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Шаблон уже в базе")
    invalidate_global_bad_url_cache()
    res = await session.execute(
        select(GlobalBadUrlPattern.pattern, GlobalBadUrlPattern.note).order_by(GlobalBadUrlPattern.pattern.asc())
    )
    return {"items": [{"pattern": str(r[0]), "note": str(r[1] or "")} for r in res.all() if r[0]]}


@router.delete("/admin/global-bad-urls")
async def api_admin_global_bad_urls_delete(
    pattern: str,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.handlers.whitelist import normalize_trusted_link_pattern
    from app.services.global_bad_urls import invalidate_global_bad_url_cache

    await _require_admin_user(session, int(user_id))
    pat = normalize_trusted_link_pattern(pattern or "")
    if not pat:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query param pattern required")
    await session.execute(delete(GlobalBadUrlPattern).where(GlobalBadUrlPattern.pattern == pat))
    await session.commit()
    invalidate_global_bad_url_cache()
    return {"ok": True}


@router.get("/admin/global-bad-urls/by-owners")
async def api_admin_global_bad_urls_by_owners(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Полный админ: кто какие шаблоны запрещает в своих чатах (локальные blacklist-правила)."""
    from collections import defaultdict

    await _require_admin_user(session, int(user_id))
    # Строки: чат → владелец как в БД → шаблон. Владелец в chats.owner_user_id почти всегда telegram_id,
    # но встречается legacy, где там оказался users.id — тогда без нормализации чужие шаблоны «липнут» к неверному владельцу.
    detail_q = await session.execute(
        select(Chat.id, Chat.owner_user_id, LinkBlacklist.pattern)
        .select_from(LinkBlacklist)
        .join(Chat, Chat.id == LinkBlacklist.chat_id)
        .where(Chat.is_log_chat.is_(False))
    )
    raw_rows = detail_q.all()
    if not raw_rows:
        return {"items": []}

    raw_owner_ids = {int(r[1] or 0) for r in raw_rows if int(r[1] or 0) > 0}
    user_rows = (
        await session.execute(
            select(User).where(or_(User.telegram_id.in_(list(raw_owner_ids)), User.id.in_(list(raw_owner_ids))))
        )
    ).scalars().all()
    raw_to_canon_tg: dict[int, int] = {}
    for u in user_rows:
        tg = int(getattr(u, "telegram_id", 0) or 0)
        if tg <= 0:
            continue
        raw_to_canon_tg[tg] = tg
        internal = int(getattr(u, "id", 0) or 0)
        if internal > 0:
            raw_to_canon_tg[internal] = tg

    def _canon_owner_tid(raw: int) -> int:
        r = int(raw or 0)
        if r <= 0:
            return 0
        return int(raw_to_canon_tg.get(r, r))

    # canonical telegram_id -> pattern -> chat ids
    owner_pattern_chats: dict[int, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for r in raw_rows:
        chat_id = int(r[0] or 0)
        pat = str(r[2] or "").strip()
        if chat_id <= 0 or not pat:
            continue
        canon = _canon_owner_tid(int(r[1] or 0))
        if canon <= 0:
            continue
        owner_pattern_chats[canon][pat].add(chat_id)

    canon_ids = list(owner_pattern_chats.keys())
    u_by_tg: dict[int, User] = {}
    if canon_ids:
        uq2 = await session.execute(select(User).where(User.telegram_id.in_(canon_ids)))
        u_by_tg = {
            int(getattr(u, "telegram_id", 0) or 0): u
            for u in uq2.scalars().all()
            if int(getattr(u, "telegram_id", 0) or 0) > 0
        }

    items: list[dict] = []
    for canon in sorted(canon_ids):
        pat_map = owner_pattern_chats[canon]
        u = u_by_tg.get(canon)
        all_chats: set[int] = set()
        pat_items: list[dict] = []
        for pat, cids in sorted(pat_map.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            pat_items.append({"pattern": pat, "chats_count": len(cids)})
            all_chats.update(cids)
        items.append(
            {
                "owner_telegram_id": canon,
                "owner_username": str(getattr(u, "username", "") or "") if u else "",
                "owner_first_name": str(getattr(u, "first_name", "") or "") if u else "",
                "patterns_count": len(pat_items),
                "total_chats_covered": len(all_chats),
                "items": pat_items,
            }
        )

    items.sort(
        key=lambda x: (
            -int(x.get("patterns_count", 0) or 0),
            -int(x.get("total_chats_covered", 0) or 0),
            int(x.get("owner_telegram_id", 0) or 0),
        )
    )
    return {"items": items}


# ---------- GET /api/global-antispam ----------
@router.get("/global-antispam")
async def api_global_antispam_list(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Список пользователей в глобальной антиспам базе (общая для бота)."""
    from app.services.global_antispam import list_global_antispam_for_api
    items = await list_global_antispam_for_api(session, limit=500)
    return {"items": items}


# ---------- POST /api/global-antispam ----------
@router.post("/global-antispam")
async def api_global_antispam_add(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Добавить user_id в глобальную антиспам базу. Body: { "user_id": number, "reason": "optional" }."""
    from app.services.global_antispam import add_to_global_antispam, update_antispam_user_profile
    from app.services.telegram_bot_api import private_chat_profile, tg_get_chat

    uid = body.get("user_id")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id required")
    uid = int(uid)
    added = await add_to_global_antispam(session, uid, body.get("reason"))
    if added:
        info = await tg_get_chat(uid)
        disp, un = private_chat_profile(info)
        if disp or un:
            await update_antispam_user_profile(session, uid, disp, un)
    return {"added": added, "user_id": uid}


# ---------- DELETE /api/global-antispam/:target_uid ----------
@router.delete("/global-antispam/{target_uid}")
async def api_global_antispam_remove(
    target_uid: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Удалить target_uid из глобальной антиспам базы."""
    from app.services.global_antispam import remove_from_global_antispam
    removed = await remove_from_global_antispam(session, target_uid)
    return {"removed": removed}


# ---------- POST /api/promo/apply ----------
@router.post("/promo/apply")
async def api_promo_apply(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Активировать промокод. Body: { "code": "TRIAL3" }. Для теста Premium на 3 дня создайте промокод с days=3."""
    code = (body.get("code") or "").strip()
    success, message = await apply_promo_code(session, user_id, code)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    try:
        code_norm = (code or "").strip().upper()
        promo_q = await session.execute(select(PromoCode).where(PromoCode.code == code_norm).limit(1))
        promo = promo_q.scalar_one_or_none()
        days = int(getattr(promo, "days", 0) or 0) if promo else 0
        gt = round(float(getattr(promo, "grant_tokens", 0.0) or 0.0), 2) if promo else 0.0
        ga = round(float(getattr(promo, "grant_aurum", 0.0) or 0.0), 2) if promo else 0.0
        is_sub_promo = bool(promo and days >= 0)
        is_tokens_promo = bool(promo and (gt > 0 or ga > 0))
        if is_sub_promo or is_tokens_promo:
            user = await get_or_create_user(session, int(user_id))
            until_txt = format_subscription_until_ru(getattr(user, "subscription_until", None))
            bonus_parts: list[str] = []
            if gt > 0:
                bonus_parts.append(f"+{gt:g} ⚡")
            if ga > 0:
                bonus_parts.append(f"+{ga:g} ✨")
            period_txt = "без срока" if days == 0 else f"на {days} дн."
            bonus_txt = f"\nНачислено: *{', '.join(bonus_parts)}*" if bonus_parts else ""
            if is_sub_promo:
                body_txt = (
                    "✅ *Guard подтверждает активацию*\n\n"
                    f"Промокод: *{code_norm}*\n"
                    f"Подписка Guard Premium: *{period_txt}*\n"
                    f"Действует до: *{until_txt}*"
                    f"{bonus_txt}\n\n"
                    "Защита активна, можно перейти к рассылке."
                )
            else:
                body_txt = (
                    "✅ *Guard начислил бонусы по промокоду*\n\n"
                    f"Промокод: *{code_norm}*"
                    f"{bonus_txt}\n\n"
                    "Токены готовы к использованию в рассылках."
                )
            reply_markup = None
            admin_url = _mini_app_admin_broadcast_url()
            if admin_url:
                reply_markup = {
                    "inline_keyboard": [[{"text": "🔵 Настроить рассылку", "web_app": {"url": admin_url}}]]
                }
            await send_user_dm(
                int(user_id),
                body_txt,
                reply_markup=reply_markup,
            )
    except Exception:
        _log.exception("failed to send promo activation dm user_id=%s code=%s", int(user_id), code)
    return {"ok": True, "message": message}


# ---------- POST /api/payments/yookassa/create ----------
@router.post("/payments/yookassa/create")
async def api_yookassa_create_payment(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Создать платёж ЮKassa. Body: { \"months\": 1|3|6|12|24|72 }. Ответ: { \"confirmation_url\": \"...\" }."""
    from app.services.payments_yookassa import create_yookassa_subscription_payment, yookassa_configured

    if not yookassa_configured("live"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Платежи не настроены",
        )
    raw = body.get("months")
    try:
        months = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="months required")
    try:
        url = await create_yookassa_subscription_payment(
            session,
            user_id,
            months,
            mode="live",
            save_payment_method=True,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый период")
    except RuntimeError as e:
        _log.exception("YooKassa create failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_humanize_yookassa_error(e),
        ) from e
    return {"confirmation_url": url}


@router.post("/payments/yookassa/create-test-subscription")
async def api_yookassa_create_test_subscription_payment(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """
    Тестовая оплата подписки (отдельный URL от продовой — позже можно подменить на тестовый магазин YooKassa).
    Доступна только для telegram id из TEST_TARIFF_PAYMENT_TELEGRAM_IDS.
    """
    if int(user_id) not in _test_tariff_payment_telegram_ids():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Тестовая оплата недоступна")
    from app.services.payments_yookassa import create_yookassa_subscription_payment, yookassa_configured

    if not yookassa_configured("test"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Платежи не настроены",
        )
    raw = body.get("months")
    try:
        months = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="months required")
    try:
        url = await create_yookassa_subscription_payment(session, user_id, months, mode="test")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый период")
    except RuntimeError as e:
        _log.exception("YooKassa test subscription create failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_humanize_yookassa_error(e),
        ) from e
    return {"confirmation_url": url}


@router.post("/payments/yookassa/create-tokens")
async def api_yookassa_create_tokens_payment(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Создать платёж ЮKassa для токенов. Body: { "tokens": 50|150|300 }."""
    from app.services.payments_yookassa import create_yookassa_tokens_payment, yookassa_configured

    if not yookassa_configured("live"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Платежи не настроены",
        )
    user = await get_or_create_user(session, user_id)
    if not _is_user_premium_now(user, datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токены доступны только при активной подписке")
    raw = body.get("tokens")
    try:
        tokens = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tokens required")
    try:
        url = await create_yookassa_tokens_payment(session, user_id, tokens, mode="live")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый пакет токенов")
    except RuntimeError as e:
        _log.exception("YooKassa tokens create failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "Ошибка платёжной системы",
        ) from e
    return {"confirmation_url": url}


@router.post("/payments/autorenew/disable")
async def api_disable_autorenew(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """
    Пользовательский выключатель автосписаний:
    - очищает сохраненный способ оплаты в нашей системе;
    - прекращает напоминания/ретраи автосписания (они завязаны на payment_method_bound).
    """
    user = await get_or_create_user(session, int(user_id))
    user.payment_method_bound = False
    user.payment_method_type = None
    user.payment_method_last4 = None
    user.yookassa_payment_method_id = None
    user.subscription_autorenew_months = None
    session.add(user)
    await session.commit()
    return {"ok": True}


@router.post("/payments/yookassa/reconcile-pending")
async def api_yookassa_reconcile_pending(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """
    Fallback после возврата из оплаты: пытаемся применить pending-оплаты напрямую из YooKassa
    (если webhook задержался/не дошел).
    """
    from app.services.payments_yookassa import reconcile_user_pending_yookassa_payments

    applied = await reconcile_user_pending_yookassa_payments(session, user_id)
    return {"ok": True, "applied": int(applied)}


@router.post("/admin/test-payments/create-subscription")
async def api_admin_test_create_subscription_payment(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Админ: создать тестовую оплату подписки (те же тарифы, что в проде)."""
    from app.services.payments_yookassa import create_yookassa_subscription_payment, yookassa_configured

    await _require_admin_user(session, int(user_id))
    if not yookassa_configured("test"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Платежи не настроены",
        )
    raw = body.get("months")
    try:
        months = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="months required")
    target_telegram_id = int(body.get("target_telegram_id") or user_id)
    try:
        url = await create_yookassa_subscription_payment(session, target_telegram_id, months, mode="test")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый период")
    except RuntimeError as e:
        _log.exception("Admin test YooKassa create subscription failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_humanize_yookassa_error(e),
        ) from e
    return {"confirmation_url": url}


@router.post("/admin/test-payments/create-tokens")
async def api_admin_test_create_tokens_payment(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Админ: создать тестовую оплату пакета токенов (без требования premium)."""
    from app.services.payments_yookassa import create_yookassa_tokens_payment, yookassa_configured

    await _require_admin_user(session, int(user_id))
    if not yookassa_configured("test"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Платежи не настроены",
        )
    raw = body.get("tokens")
    try:
        tokens = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tokens required")
    target_telegram_id = int(body.get("target_telegram_id") or user_id)
    try:
        url = await create_yookassa_tokens_payment(session, target_telegram_id, tokens, mode="test")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый пакет токенов")
    except RuntimeError as e:
        _log.exception("Admin test YooKassa create tokens failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "Ошибка платёжной системы",
        ) from e
    return {"confirmation_url": url}


@router.post("/admin/test-payments/create-binding-probe")
async def api_admin_test_create_binding_probe_payment(
    body: dict | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Админ: тестовый тариф 2 дня / 1 RUB для проверки привязки карты и напоминаний."""
    from app.services.payments_yookassa import create_yookassa_binding_probe_payment, yookassa_configured

    await _require_admin_user(session, int(user_id))
    mode = str((body or {}).get("mode") or "live").strip().lower()
    if mode not in {"live", "test"}:
        mode = "live"
    if not yookassa_configured(mode):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Платежи не настроены",
        )
    target_telegram_id = int((body or {}).get("target_telegram_id") or user_id)
    try:
        url = await create_yookassa_binding_probe_payment(session, target_telegram_id, mode=mode)
    except RuntimeError as e:
        _log.exception("Admin test YooKassa create binding probe failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_humanize_yookassa_error(e),
        ) from e
    return {"confirmation_url": url}


@router.get("/admin/test-payments/capability")
async def api_admin_test_payments_capability(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Статус доступности recurring (по env-флагу/наблюдаемой привязке карты)."""
    from app.services.payments_yookassa import yookassa_configured

    await _require_admin_user(session, int(user_id))
    live_autorenew_enabled = await _get_app_bool_setting(session, "payments.live_autorenew_enabled", False)

    def _mode_payload(mode: str) -> dict:
        configured = bool(yookassa_configured(mode))
        env_recurring = _env_bool(f"YOOKASSA_{mode.upper()}_RECURRING_ENABLED", False)
        return {
            "configured": configured,
            "recurring_enabled": bool(env_recurring),
        }

    live = _mode_payload("live")
    test = _mode_payload("test")

    # Наблюдаемая телеметрия: была ли хотя бы одна успешная привязка способа оплаты.
    bound_q = await session.execute(
        select(func.count(User.id)).where(
            User.payment_method_bound == True,  # noqa: E712
            User.subscription_source == "payment",
        )
    )
    observed_bound_count = int(bound_q.scalar() or 0)
    observed_bound_any = observed_bound_count > 0

    def _final(mode_payload: dict) -> dict:
        configured = bool(mode_payload.get("configured"))
        recurring_enabled = bool(mode_payload.get("recurring_enabled"))
        if not configured:
            status = "not_configured"
            hint = "Платежи для этого режима не настроены."
        elif recurring_enabled:
            status = "enabled"
            hint = "Recurring отмечен как включённый в настройках окружения."
        elif observed_bound_any:
            status = "enabled_observed"
            hint = "Обнаружены успешные привязки карты в базе."
        else:
            status = "unknown_or_disabled"
            hint = "Привязки пока не наблюдались. Если LIVE ругается на recurring — подключите у YooMoney менеджера."
        return {
            **mode_payload,
            "status": status,
            "hint": hint,
        }

    return {
        "live": _final(live),
        "test": _final(test),
        "observed_bound_count": observed_bound_count,
        "live_autorenew_enabled": bool(live_autorenew_enabled),
    }


@router.post("/admin/payments/live-autorenew")
async def api_admin_set_live_autorenew_flag(
    body: dict | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Админский переключатель: включать ли save_payment_method для LIVE-оплат подписки."""
    await _require_admin_user(session, int(user_id))
    enabled = bool((body or {}).get("enabled", False))
    await _set_app_bool_setting(session, "payments.live_autorenew_enabled", bool(enabled))
    return {"ok": True, "enabled": bool(enabled)}


# ---------- Admin broadcasts (рассылка постов пользователям бота) ----------
@router.get("/admin/broadcasts")
async def api_admin_broadcasts_list(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
    scope: str = Query("mine"),
):
    from app.services.admin_broadcast import broadcast_list_origins_for_rows, broadcast_row_to_dict

    _u, full = await _require_broadcast_access(session, int(user_id))
    sc = str(scope or "mine").strip().lower()
    if sc not in ("mine", "all"):
        sc = "mine"
    effective = "all" if full and sc == "all" else "mine"
    q = select(AdminBroadcast).options(selectinload(AdminBroadcast.media_items)).order_by(AdminBroadcast.id.desc()).limit(80)
    if effective != "all":
        q = q.where(AdminBroadcast.admin_telegram_id == int(user_id))
    rows = (await session.execute(q)).scalars().all()
    origins_merged: dict[int, str] = {}
    by_owner: dict[int, list] = {}
    for r in rows:
        oid = int(getattr(r, "admin_telegram_id", 0) or 0)
        if oid > 0:
            by_owner.setdefault(oid, []).append(r)
    for oid, chunk in by_owner.items():
        origins_merged.update(await broadcast_list_origins_for_rows(session, oid, chunk))
    items = []
    for r in rows:
        d = broadcast_row_to_dict(r)
        d["list_origin"] = origins_merged.get(int(r.id), "one_shot")
        items.append(d)
    return {"items": items, "scope": effective}


@router.get("/admin/broadcasts/{broadcast_id}")
async def api_admin_broadcasts_get(
    broadcast_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import broadcast_list_origins_for_rows, broadcast_row_to_dict

    _u, full = await _require_broadcast_access(session, int(user_id))
    q = await session.execute(
        select(AdminBroadcast)
        .options(selectinload(AdminBroadcast.media_items))
        .where(AdminBroadcast.id == int(broadcast_id))
    )
    row = q.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    d = broadcast_row_to_dict(row)
    oid = int(getattr(row, "admin_telegram_id", 0) or 0)
    if oid > 0:
        d["list_origin"] = (await broadcast_list_origins_for_rows(session, oid, [row])).get(int(row.id), "one_shot")
    else:
        d["list_origin"] = "one_shot"
    return d


@router.get("/public/broadcast/click")
async def api_public_broadcast_click(
    b: int,
    k: str,
    t: int,
    u: str,
    session: AsyncSession = Depends(get_db),
):
    """Трекинг реальных кликов/переходов по ссылкам из рассылки."""
    url = str(u or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid url")
    row = await session.get(AdminBroadcast, int(b))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    ev = AdminBroadcastClick(
        broadcast_id=int(b),
        target_kind=str(k or "user")[:16],
        target_id=int(t or 0),
        url=url[:2000],
    )
    session.add(ev)
    await session.commit()
    return RedirectResponse(url=url, status_code=307)


_BROADCAST_LINK_CLICK_FILTER = or_(
    AdminBroadcastClick.url.like("http://%"),
    AdminBroadcastClick.url.like("https://%"),
)
_BROADCAST_CALLBACK_CLICK_FILTER = AdminBroadcastClick.url.like("callback:%")


def _split_broadcast_click_rows(rows: list[tuple[Any, Any]]) -> tuple[int, int]:
    users = 0
    groups = 0
    for kind, cnt in rows:
        c = int(cnt or 0)
        ks = str(kind or "").strip().lower()
        if ks in {"group", "groups", "channel", "channels"}:
            groups += c
        else:
            users += c
    return users, groups


async def _admin_broadcast_click_breakdown(
    session: AsyncSession,
    *,
    bid: int | None = None,
    bids: list[int] | None = None,
    since: datetime | None = None,
) -> dict[str, Any]:
    if bid is not None:
        flt: list[Any] = [AdminBroadcastClick.broadcast_id == int(bid)]
    else:
        bl = sorted({int(x) for x in (bids or []) if int(x) > 0})
        if not bl:
            return {
                "users": 0,
                "groups": 0,
                "total": 0,
                "link_users": 0,
                "link_groups": 0,
                "link_total": 0,
                "callback_users": 0,
                "callback_groups": 0,
                "callback_total": 0,
                "link_items": [],
                "callback_items": [],
            }
        flt = [AdminBroadcastClick.broadcast_id.in_(bl)]
    if since is not None:
        flt = [*flt, AdminBroadcastClick.created_at >= since]

    all_q = await session.execute(
        select(AdminBroadcastClick.target_kind, func.count(AdminBroadcastClick.id))
        .where(*flt)
        .group_by(AdminBroadcastClick.target_kind)
    )
    link_q = await session.execute(
        select(AdminBroadcastClick.target_kind, func.count(AdminBroadcastClick.id))
        .where(*flt, _BROADCAST_LINK_CLICK_FILTER)
        .group_by(AdminBroadcastClick.target_kind)
    )
    cb_q = await session.execute(
        select(AdminBroadcastClick.target_kind, func.count(AdminBroadcastClick.id))
        .where(*flt, _BROADCAST_CALLBACK_CLICK_FILTER)
        .group_by(AdminBroadcastClick.target_kind)
    )
    link_items_q = await session.execute(
        select(
            AdminBroadcastClick.url,
            AdminBroadcastClick.target_kind,
            func.count(AdminBroadcastClick.id),
        )
        .where(*flt, _BROADCAST_LINK_CLICK_FILTER)
        .group_by(AdminBroadcastClick.url, AdminBroadcastClick.target_kind)
    )
    callback_items_q = await session.execute(
        select(
            AdminBroadcastClick.url,
            AdminBroadcastClick.target_kind,
            func.count(AdminBroadcastClick.id),
        )
        .where(*flt, _BROADCAST_CALLBACK_CLICK_FILTER)
        .group_by(AdminBroadcastClick.url, AdminBroadcastClick.target_kind)
    )
    u_all, g_all = _split_broadcast_click_rows(list(all_q.all()))
    u_ln, g_ln = _split_broadcast_click_rows(list(link_q.all()))
    u_cb, g_cb = _split_broadcast_click_rows(list(cb_q.all()))
    link_map: dict[str, dict[str, Any]] = {}
    for raw_url, kind, cnt in link_items_q.all():
        url = str(raw_url or "").strip()
        if not url:
            continue
        row = link_map.get(url)
        if row is None:
            row = {"key": url, "title": url, "users": 0, "groups": 0, "total": 0}
            link_map[url] = row
        c = int(cnt or 0)
        ks = str(kind or "").strip().lower()
        if ks in {"group", "groups", "channel", "channels"}:
            row["groups"] += c
        else:
            row["users"] += c
        row["total"] += c

    callback_map: dict[str, dict[str, Any]] = {}
    for raw_url, kind, cnt in callback_items_q.all():
        val = str(raw_url or "").strip()
        if not val:
            continue
        parts = val.split(":", 2)
        btn_idx = -1
        if len(parts) >= 2:
            try:
                btn_idx = int(parts[1])
            except Exception:
                btn_idx = -1
        inner = parts[2] if len(parts) >= 3 else ""
        title = f"Кнопка #{btn_idx + 1}" if btn_idx >= 0 else "Кнопка"
        if inner:
            title = f"{title} · {inner[:96]}"
        row = callback_map.get(val)
        if row is None:
            row = {"key": val, "title": title, "users": 0, "groups": 0, "total": 0}
            callback_map[val] = row
        c = int(cnt or 0)
        ks = str(kind or "").strip().lower()
        if ks in {"group", "groups", "channel", "channels"}:
            row["groups"] += c
        else:
            row["users"] += c
        row["total"] += c

    link_items = sorted(link_map.values(), key=lambda x: int(x.get("total", 0)), reverse=True)[:40]
    callback_items = sorted(callback_map.values(), key=lambda x: int(x.get("total", 0)), reverse=True)[:40]
    return {
        "users": u_all,
        "groups": g_all,
        "total": u_all + g_all,
        "link_users": u_ln,
        "link_groups": g_ln,
        "link_total": u_ln + g_ln,
        "callback_users": u_cb,
        "callback_groups": g_cb,
        "callback_total": u_cb + g_cb,
        "link_items": link_items,
        "callback_items": callback_items,
    }


@router.get("/admin/broadcasts/{broadcast_id}/stats")
async def api_admin_broadcasts_stats(
    broadcast_id: int,
    batch_id: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    target_kind: str | None = None,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    wanted_target = str(target_kind or "").strip().lower()
    def _target_matches_wanted(k: str) -> bool:
        ks = str(k or "").strip().lower()
        if not wanted_target:
            return True
        if wanted_target in {"group", "groups"}:
            return ks in {"group", "groups"}
        if wanted_target in {"bot", "bots", "user", "users"}:
            return ks in {"bot", "bots", "user", "users"}
        return True
    _viewer, full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    gtotal_q = await session.execute(
        select(func.count(Chat.id)).where(
            Chat.is_active.is_(True),
            Chat.is_log_chat.is_(False),
            Chat.owner_user_id == int(row.admin_telegram_id),
        )
    )
    connected_groups_total = int(gtotal_q.scalar() or 0)
    btotal_q = await session.execute(
        select(func.count(User.id)).where(
            User.telegram_id > 0,
            User.status == "active",
        )
    )
    connected_bots_total = int(btotal_q.scalar() or 0)

    from app.services.admin_broadcast import broadcast_url_tracking_configured

    click_metrics = await _admin_broadcast_click_breakdown(session, bid=int(broadcast_id))
    tracking_cfg = broadcast_url_tracking_configured()
    click_extras = {
        "real_link_clicks": int(click_metrics["link_users"]),
        "real_link_transitions": int(click_metrics["link_groups"]),
        "real_link_clicks_total": int(click_metrics["link_total"]),
        "real_callback_clicks": int(click_metrics["callback_users"]),
        "real_callback_transitions": int(click_metrics["callback_groups"]),
        "real_callback_clicks_total": int(click_metrics["callback_total"]),
        "real_link_items": click_metrics.get("link_items") or [],
        "real_callback_items": click_metrics.get("callback_items") or [],
        "broadcast_url_tracking_configured": bool(tracking_cfg),
    }
    real_clicks_users = int(click_metrics["users"])
    real_clicks_groups = int(click_metrics["groups"])
    real_clicks_total = int(click_metrics["total"])

    run_target_filter: list[Any] = []
    if wanted_target in {"group", "groups"}:
        run_target_filter.append(AdminBroadcastRun.target_kind.in_(("group", "groups")))
    elif wanted_target in {"bot", "bots", "user", "users"}:
        run_target_filter.append(AdminBroadcastRun.target_kind.in_(("user", "users", "bot", "bots")))
    runs_q = await session.execute(
        select(
            AdminBroadcastRun.id,
            AdminBroadcastRun.target_kind,
            AdminBroadcastRun.recipient_total,
            AdminBroadcastRun.recipient_ok,
            AdminBroadcastRun.recipient_fail,
            AdminBroadcastRun.audience_total,
            AdminBroadcastRun.audience_ok,
            AdminBroadcastRun.created_at,
            AdminBroadcastRun.sent_at,
        )
        .where(AdminBroadcastRun.broadcast_id == int(broadcast_id), *run_target_filter)
        .order_by(AdminBroadcastRun.created_at.desc())
        .limit(200)
    )
    run_rows = runs_q.all()

    has_delivery = False
    has_batch_id = False
    has_created_at = False
    has_error_message = False
    has_target_id = False
    try:
        now_tick = perf_counter()
        cols = _DELIVERY_SCHEMA_CACHE.get("cols") if (now_tick - float(_DELIVERY_SCHEMA_CACHE.get("ts") or 0.0)) < _DELIVERY_SCHEMA_TTL_SEC else None
        if not cols:
            col_q = await session.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'admin_broadcast_delivery'
                    """
                )
            )
            cols = {str(x[0] or "") for x in col_q.all()}
            _DELIVERY_SCHEMA_CACHE["ts"] = now_tick
            _DELIVERY_SCHEMA_CACHE["cols"] = cols
        has_delivery = {"broadcast_id", "target_kind", "ok"}.issubset(cols)
        has_batch_id = "batch_id" in cols
        has_created_at = "created_at" in cols
        has_error_message = "error_message" in cols
        has_target_id = "target_id" in cols
    except Exception:
        has_delivery = False
        has_batch_id = False
        has_created_at = False
        has_error_message = False
        has_target_id = False

    target_where: list[Any] = []
    if wanted_target in {"group", "groups"}:
        target_where.append(AdminBroadcastDelivery.target_kind.in_(("group", "groups")))
    elif wanted_target in {"bot", "bots", "user", "users"}:
        target_where.append(AdminBroadcastDelivery.target_kind.in_(("user", "users", "bot", "bots")))

    batches = []
    latest_audience_total = 0
    latest_audience_ok = 0
    if run_rows:
        for rid, rtarget, rtotal, rok, rfail, raud_total, raud_ok, rcreated, rsent in run_rows:
            batches.append(
                {
                    "batch_id": f"run:{int(rid)}",
                    "started_at": rcreated.isoformat() if rcreated else None,
                    "ended_at": (rsent or rcreated).isoformat() if (rsent or rcreated) else None,
                    "total": int(rtotal or 0),
                    "ok": int(rok or 0),
                    "fail": int(rfail or 0),
                    "audience_total": int(raud_total or 0),
                    "audience_ok": int(raud_ok or 0),
                    "target_kind": str(rtarget or ""),
                }
            )
        latest_audience_total = int(run_rows[0][5] or 0)
        latest_audience_ok = int(run_rows[0][6] or 0)

    if has_delivery and has_batch_id and has_created_at:
        bq = await session.execute(
            select(
                AdminBroadcastDelivery.batch_id,
                func.min(AdminBroadcastDelivery.created_at),
                func.max(AdminBroadcastDelivery.created_at),
                func.count(AdminBroadcastDelivery.id),
                func.sum(case((AdminBroadcastDelivery.ok.is_(True), 1), else_=0)),
            )
            .where(AdminBroadcastDelivery.broadcast_id == int(broadcast_id), *target_where)
            .group_by(AdminBroadcastDelivery.batch_id)
            .order_by(func.max(AdminBroadcastDelivery.created_at).desc())
            .limit(50)
        )
        for bid, started, ended, total, ok_count in bq.all():
            total_i = int(total or 0)
            ok_i = int(ok_count or 0)
            batches.append(
                {
                    "batch_id": str(bid or ""),
                    "started_at": started.isoformat() if started else None,
                    "ended_at": ended.isoformat() if ended else None,
                    "total": total_i,
                    "ok": ok_i,
                    "fail": max(0, total_i - ok_i),
                }
            )
    elif has_delivery:
        bq = await session.execute(
            select(
                func.min(AdminBroadcastDelivery.created_at) if has_created_at else func.now(),
                func.max(AdminBroadcastDelivery.created_at) if has_created_at else func.now(),
                func.count(AdminBroadcastDelivery.id),
                func.sum(case((AdminBroadcastDelivery.ok.is_(True), 1), else_=0)),
            )
            .where(AdminBroadcastDelivery.broadcast_id == int(broadcast_id), *target_where)
        )
        started, ended, total, ok_count = bq.one()
        total_i = int(total or 0)
        ok_i = int(ok_count or 0)
        if total_i > 0:
            batches.append(
                {
                    "batch_id": "__single__",
                    "started_at": started.isoformat() if started else None,
                    "ended_at": ended.isoformat() if ended else None,
                    "total": total_i,
                    "ok": ok_i,
                    "fail": max(0, total_i - ok_i),
                }
            )
    row_last_target = str(getattr(row, "last_target", "") or "").strip().lower()
    if not batches:
        # Исторические запуски до внедрения delivery-логов: показываем агрегат из самой рассылки.
        legacy_total = int(row.recipient_total or 0)
        legacy_ok = int(row.recipient_ok or 0)
        legacy_fail = int(row.recipient_fail or max(0, legacy_total - legacy_ok))
        if (legacy_total > 0 or row.sent_at or row.created_at) and _target_matches_wanted(row_last_target):
            started = row.sent_at or row.created_at
            ended = row.sent_at or row.created_at
            batches.append(
                {
                    "batch_id": f"legacy:{int(row.id)}",
                    "started_at": started.isoformat() if started else None,
                    "ended_at": ended.isoformat() if ended else None,
                    "total": legacy_total,
                    "ok": legacy_ok,
                    "fail": legacy_fail,
                    "is_legacy": True,
                }
            )
    if not batches and str(row.status or "").lower() == "sending" and _target_matches_wanted(row_last_target):
        # Текущий запуск еще не успел записать delivery-строки.
        batches.append(
            {
                "batch_id": "__live__",
                "started_at": row.created_at.isoformat() if row.created_at else None,
                "ended_at": None,
                "total": int(row.recipient_total or 0),
                "ok": int(row.recipient_ok or 0),
                "fail": int(row.recipient_fail or 0),
                "is_live": True,
            }
        )
    active_batch = (batch_id or "").strip() or (batches[0]["batch_id"] if batches else "")

    from_dt: datetime | None = None
    to_dt: datetime | None = None
    try:
        if from_ts and str(from_ts).strip():
            from_dt = datetime.fromisoformat(str(from_ts).strip().replace("Z", "+00:00"))
            if from_dt.tzinfo is None:
                from_dt = from_dt.replace(tzinfo=timezone.utc)
        if to_ts and str(to_ts).strip():
            to_dt = datetime.fromisoformat(str(to_ts).strip().replace("Z", "+00:00"))
            if to_dt.tzinfo is None:
                to_dt = to_dt.replace(tzinfo=timezone.utc)
    except Exception:
        from_dt = None
        to_dt = None

    where_batch = [AdminBroadcastDelivery.broadcast_id == int(broadcast_id)]
    if target_where:
        where_batch.extend(target_where)
    if active_batch and has_batch_id and active_batch not in {"__single__"}:
        where_batch.append(AdminBroadcastDelivery.batch_id == active_batch)
    if from_dt and has_created_at:
        where_batch.append(AdminBroadcastDelivery.created_at >= from_dt)
    if to_dt and has_created_at:
        where_batch.append(AdminBroadcastDelivery.created_at <= to_dt)

    if active_batch.startswith("run:"):
        run_map = {
            f"run:{int(rid)}": (
                str(rtarget or ""),
                int(rtotal or 0),
                int(rok or 0),
                int(rfail or 0),
                int(raud_total or 0),
                int(raud_ok or 0),
            )
            for rid, rtarget, rtotal, rok, rfail, raud_total, raud_ok, _, _ in run_rows
        }
        rtarget, rtotal, rok, rfail, raud_total, raud_ok = run_map.get(active_batch, ("", 0, 0, 0, 0, 0))
        if str(rtarget).lower() in {"group", "groups"}:
            bots_ok = bots_fail = 0
            groups_ok = int(rok)
            groups_fail = int(rfail)
        else:
            bots_ok = int(rok)
            bots_fail = int(rfail)
            groups_ok = groups_fail = 0
        return {
            "broadcast_id": int(broadcast_id),
            "active_batch_id": active_batch,
            "batches": batches,
            "bots": {"ok": bots_ok, "fail": bots_fail, "total": bots_ok + bots_fail},
            "groups": {"ok": groups_ok, "fail": groups_fail, "total": groups_ok + groups_fail},
            "overall": {"ok": bots_ok + groups_ok, "fail": bots_fail + groups_fail, "total": bots_ok + groups_ok + bots_fail + groups_fail},
            "audience_total": int(raud_total or latest_audience_total or 0),
            "audience_ok": int(raud_ok or latest_audience_ok or 0),
            "real_clicks": int(real_clicks_users),
            "real_transitions": int(real_clicks_groups),
            "real_clicks_total": int(real_clicks_total),
            "per_groups": [],
            "errors": [],
            "connected_groups_total": connected_groups_total,
            "connected_bots_total": connected_bots_total,
            **click_extras,
        }

    if active_batch.startswith("legacy:"):
        if wanted_target and not _target_matches_wanted(row_last_target):
            bots_ok = bots_fail = groups_ok = groups_fail = 0
        elif wanted_target in {"group", "groups"}:
            bots_ok = 0
            bots_fail = 0
            groups_ok = int(row.recipient_ok or 0)
            groups_fail = int(row.recipient_fail or 0)
        else:
            bots_ok = int(row.recipient_ok or 0)
            bots_fail = int(row.recipient_fail or 0)
            groups_ok = 0
            groups_fail = 0
        result = {
            "broadcast_id": int(broadcast_id),
            "active_batch_id": active_batch,
            "batches": batches,
            "bots": {"ok": bots_ok, "fail": bots_fail, "total": bots_ok + bots_fail},
            "groups": {"ok": groups_ok, "fail": groups_fail, "total": groups_ok + groups_fail},
            "overall": {
                "ok": bots_ok + groups_ok,
                "fail": bots_fail + groups_fail,
                "total": bots_ok + groups_ok + bots_fail + groups_fail,
            },
            "audience_total": int(latest_audience_total or 0),
            "audience_ok": int(latest_audience_ok or 0),
            "real_clicks": int(real_clicks_users),
            "real_transitions": int(real_clicks_groups),
            "real_clicks_total": int(real_clicks_total),
            "per_groups": [],
            "errors": [],
            "connected_groups_total": connected_groups_total,
            "connected_bots_total": connected_bots_total,
            **click_extras,
        }
        _log.warning(
            "broadcast stats legacy/live: id=%s target=%s batch=%s from_ts=%s to_ts=%s history_count=%s bots=%s groups=%s connected_groups_total=%s",
            int(broadcast_id),
            wanted_target or "auto",
            active_batch,
            str(from_ts or ""),
            str(to_ts or ""),
            len(batches),
            result["bots"],
            result["groups"],
            connected_groups_total,
        )
        return result
    if active_batch == "__live__":
        if wanted_target and not _target_matches_wanted(row_last_target):
            bots_ok = bots_fail = groups_ok = groups_fail = 0
        elif wanted_target in {"group", "groups"}:
            bots_ok = 0
            bots_fail = 0
            groups_ok = int(row.recipient_ok or 0)
            groups_fail = int(row.recipient_fail or 0)
        else:
            bots_ok = int(row.recipient_ok or 0)
            bots_fail = int(row.recipient_fail or 0)
            groups_ok = 0
            groups_fail = 0
        result = {
            "broadcast_id": int(broadcast_id),
            "active_batch_id": active_batch,
            "batches": batches,
            "bots": {"ok": bots_ok, "fail": bots_fail, "total": bots_ok + bots_fail},
            "groups": {"ok": groups_ok, "fail": groups_fail, "total": groups_ok + groups_fail},
            "overall": {
                "ok": bots_ok + groups_ok,
                "fail": bots_fail + groups_fail,
                "total": bots_ok + groups_ok + bots_fail + groups_fail,
            },
            "audience_total": int(latest_audience_total or 0),
            "audience_ok": int(latest_audience_ok or 0),
            "real_clicks": int(real_clicks_users),
            "real_transitions": int(real_clicks_groups),
            "real_clicks_total": int(real_clicks_total),
            "per_groups": [],
            "errors": [],
            "connected_groups_total": connected_groups_total,
            "connected_bots_total": connected_bots_total,
            **click_extras,
        }
        _log.warning(
            "broadcast stats no-delivery: id=%s target=%s batch=%s from_ts=%s to_ts=%s history_count=%s bots=%s groups=%s connected_groups_total=%s",
            int(broadcast_id),
            wanted_target or "auto",
            active_batch,
            str(from_ts or ""),
            str(to_ts or ""),
            len(batches),
            result["bots"],
            result["groups"],
            connected_groups_total,
        )
        return result

    if not has_delivery:
        if wanted_target and not _target_matches_wanted(row_last_target):
            bots_ok = bots_fail = groups_ok = groups_fail = 0
        elif wanted_target in {"group", "groups"}:
            bots_ok = 0
            bots_fail = 0
            groups_ok = int(row.recipient_ok or 0)
            groups_fail = int(row.recipient_fail or 0)
        else:
            bots_ok = int(row.recipient_ok or 0)
            bots_fail = int(row.recipient_fail or 0)
            groups_ok = 0
            groups_fail = 0
        return {
            "broadcast_id": int(broadcast_id),
            "active_batch_id": active_batch,
            "batches": batches,
            "bots": {"ok": bots_ok, "fail": bots_fail, "total": bots_ok + bots_fail},
            "groups": {"ok": groups_ok, "fail": groups_fail, "total": groups_ok + groups_fail},
            "overall": {
                "ok": bots_ok + groups_ok,
                "fail": bots_fail + groups_fail,
                "total": bots_ok + groups_ok + bots_fail + groups_fail,
            },
            "audience_total": int(latest_audience_total or 0),
            "audience_ok": int(latest_audience_ok or 0),
            "real_clicks": int(real_clicks_users),
            "real_transitions": int(real_clicks_groups),
            "real_clicks_total": int(real_clicks_total),
            "per_groups": [],
            "errors": [],
            "connected_groups_total": connected_groups_total,
            "connected_bots_total": connected_bots_total,
            **click_extras,
        }

    q = await session.execute(
        select(
            AdminBroadcastDelivery.target_kind,
            AdminBroadcastDelivery.ok,
            func.count(AdminBroadcastDelivery.id),
        )
        .where(*where_batch)
        .group_by(AdminBroadcastDelivery.target_kind, AdminBroadcastDelivery.ok)
    )
    bots_ok = bots_fail = groups_ok = groups_fail = 0
    for kind, ok, cnt in q.all():
        c = int(cnt or 0)
        kind_s = str(kind or "").strip().lower()
        if kind_s in {"group", "groups"}:
            if bool(ok):
                groups_ok += c
            else:
                groups_fail += c
        else:
            if bool(ok):
                bots_ok += c
            else:
                bots_fail += c

    if has_target_id:
        gq = await session.execute(
            select(
                AdminBroadcastDelivery.target_id,
                AdminBroadcastDelivery.ok,
                func.count(AdminBroadcastDelivery.id),
            )
            .where(
                *where_batch,
                AdminBroadcastDelivery.target_kind.in_(("group", "groups")),
            )
            .group_by(AdminBroadcastDelivery.target_id, AdminBroadcastDelivery.ok)
        )
        gq_rows = gq.all()
    else:
        gq_rows = []
    per_group_map: dict[int, dict] = {}
    for gid, ok, cnt in gq_rows:
        k = int(gid)
        if k not in per_group_map:
            per_group_map[k] = {"chat_id": k, "ok": 0, "fail": 0}
        if bool(ok):
            per_group_map[k]["ok"] += int(cnt or 0)
        else:
            per_group_map[k]["fail"] += int(cnt or 0)

    group_ids = list(per_group_map.keys())
    titles_map: dict[int, str] = {}
    if group_ids:
        cq = await session.execute(select(Chat.id, Chat.title).where(Chat.id.in_(group_ids)))
        for cid, title in cq.all():
            titles_map[int(cid)] = str(title or "")

    per_groups = []
    for gid in sorted(group_ids):
        item = per_group_map[gid]
        per_groups.append(
            {
                "chat_id": gid,
                "title": titles_map.get(gid, "") or str(gid),
                "ok": int(item["ok"]),
                "fail": int(item["fail"]),
                "total": int(item["ok"]) + int(item["fail"]),
            }
        )

    if has_error_message and has_target_id and has_created_at:
        eq = await session.execute(
            select(
                AdminBroadcastDelivery.target_kind,
                AdminBroadcastDelivery.target_id,
                AdminBroadcastDelivery.error_message,
                AdminBroadcastDelivery.created_at,
            )
            .where(
                *where_batch,
                AdminBroadcastDelivery.ok.is_(False),
            )
            .order_by(AdminBroadcastDelivery.created_at.desc())
            .limit(200)
        )
        errors = [
            {
                "target_kind": str(k or "user"),
                "target_id": int(tid or 0),
                "error_message": str(msg or ""),
                "created_at": dt.isoformat() if dt else None,
            }
            for k, tid, msg, dt in eq.all()
        ]
    else:
        errors = []

    result = {
        "broadcast_id": int(broadcast_id),
        "active_batch_id": active_batch,
        "batches": batches,
        "bots": {"ok": bots_ok, "fail": bots_fail, "total": bots_ok + bots_fail},
        "groups": {"ok": groups_ok, "fail": groups_fail, "total": groups_ok + groups_fail},
        "overall": {
            "ok": bots_ok + groups_ok,
            "fail": bots_fail + groups_fail,
            "total": bots_ok + groups_ok + bots_fail + groups_fail,
        },
        "audience_total": int(latest_audience_total or 0),
        "audience_ok": int(latest_audience_ok or 0),
        "real_clicks": int(real_clicks_users),
        "real_transitions": int(real_clicks_groups),
        "real_clicks_total": int(real_clicks_total),
        "per_groups": per_groups,
        "errors": errors,
        "connected_groups_total": connected_groups_total,
        "connected_bots_total": connected_bots_total,
        **click_extras,
    }
    _log.warning(
        "broadcast stats: id=%s target=%s batch=%s from_ts=%s to_ts=%s history_count=%s bots=%s groups=%s per_groups=%s errors=%s connected_groups_total=%s",
        int(broadcast_id),
        wanted_target or "auto",
        active_batch,
        str(from_ts or ""),
        str(to_ts or ""),
        len(batches),
        result["bots"],
        result["groups"],
        len(per_groups),
        len(errors),
        connected_groups_total,
    )
    return result


@router.get("/admin/broadcasts/{broadcast_id}/autopost-stats")
async def api_admin_broadcasts_autopost_stats(
    broadcast_id: int,
    days: int = Query(1, ge=1, le=30),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Агрегаты по запускам с run_source=autopost для черновиков из ротации этого якоря."""
    from app.services.admin_broadcast import normalize_autopost_payload

    _u, full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")

    ap_dict: dict | None = None
    raw_ap = getattr(row, "autopost_json", None) or ""
    if raw_ap:
        try:
            parsed = json.loads(raw_ap) if isinstance(raw_ap, str) else None
            if isinstance(parsed, dict):
                ap_dict = normalize_autopost_payload(parsed)
        except Exception:
            ap_dict = None

    owner_tid = int(row.admin_telegram_id)
    rotation_ids: list[int] = [int(broadcast_id)]
    if ap_dict:
        if bool(ap_dict.get("use_all_broadcasts")):
            res = await session.execute(
                select(AdminBroadcast.id).where(
                    AdminBroadcast.admin_telegram_id == owner_tid,
                    AdminBroadcast.status == "draft",
                )
            )
            rotation_ids = sorted({int(x[0]) for x in res.all()} | {int(broadcast_id)})
        else:
            bids = [int(x) for x in (ap_dict.get("broadcast_ids") or []) if int(x) > 0]
            rotation_ids = sorted(set(bids + [int(broadcast_id)]))

    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    rq = await session.execute(
        select(AdminBroadcastRun)
        .where(
            AdminBroadcastRun.broadcast_id.in_(rotation_ids),
            AdminBroadcastRun.created_at >= since,
        )
        .order_by(AdminBroadcastRun.created_at.desc())
        .limit(500)
    )
    runs = list(rq.scalars().all())
    autopost_rows = [r for r in runs if str(getattr(r, "run_source", None) or "") == "autopost"]

    def _is_bot_kind(tk: str) -> bool:
        t = (tk or "").lower()
        return t in {"user", "users", "bot", "bots"}

    def _is_group_kind(tk: str) -> bool:
        t = (tk or "").lower()
        return t in {"group", "groups", "channel", "channels"}

    bots_ok = bots_fail = groups_ok = groups_fail = 0
    bot_rec_total = group_rec_total = 0
    for r in autopost_rows:
        tk = str(getattr(r, "target_kind", "") or "")
        rok = int(getattr(r, "recipient_ok", 0) or 0)
        rfail = int(getattr(r, "recipient_fail", 0) or 0)
        rt = int(getattr(r, "recipient_total", 0) or 0)
        if _is_bot_kind(tk):
            bots_ok += rok
            bots_fail += rfail
            bot_rec_total += rt
        elif _is_group_kind(tk):
            groups_ok += rok
            groups_fail += rfail
            group_rec_total += rt

    posts_per_day = int(ap_dict.get("postsPerDay") or 0) if ap_dict else 0

    runs_payload: list[dict] = []
    for r in autopost_rows[:80]:
        cat = getattr(r, "created_at", None)
        sat = getattr(r, "sent_at", None)
        runs_payload.append(
            {
                "id": int(r.id),
                "broadcast_id": int(r.broadcast_id),
                "target_kind": str(r.target_kind or ""),
                "recipient_total": int(r.recipient_total or 0),
                "recipient_ok": int(r.recipient_ok or 0),
                "recipient_fail": int(r.recipient_fail or 0),
                "created_at": cat.isoformat() if cat else None,
                "sent_at": sat.isoformat() if sat else None,
            }
        )

    return {
        "broadcast_id": int(broadcast_id),
        "days": int(days),
        "rotation_broadcast_ids": rotation_ids,
        "posts_per_day_config": posts_per_day,
        "autopost_slots_recorded": len(autopost_rows),
        "bots": {"recipient_ok": bots_ok, "recipient_fail": bots_fail, "recipient_total": bot_rec_total},
        "groups": {"recipient_ok": groups_ok, "recipient_fail": groups_fail, "recipient_total": group_rec_total},
        "runs": runs_payload,
    }


def _autopost_campaign_public(row: AutopostCampaign) -> dict:
    from app.services.admin_broadcast import normalize_autopost_payload

    ap_out = None
    raw = (getattr(row, "autopost_json", None) or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                clean = {k: v for k, v in parsed.items() if k != "_state"}
                ap_out = normalize_autopost_payload(clean)
        except Exception:
            ap_out = None
    ab = getattr(row, "anchor_broadcast_id", None)
    us = getattr(row, "user_seq", None)
    return {
        "id": int(row.id),
        "user_seq": int(us) if us is not None else None,
        "title": str(row.title or ""),
        "anchor_broadcast_id": int(ab) if ab else None,
        "autopost": ap_out,
    }


@router.get("/admin/autopost-campaigns")
async def api_admin_autopost_campaigns_list(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_broadcast_access(session, int(user_id))
    res = await session.execute(
        select(AutopostCampaign)
        .where(AutopostCampaign.admin_telegram_id == int(user_id))
        .order_by(AutopostCampaign.id.desc())
    )
    rows = list(res.scalars().all())
    return {"items": [_autopost_campaign_public(r) for r in rows]}


@router.post("/admin/autopost-campaigns")
async def api_admin_autopost_campaigns_create(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    await _require_broadcast_access(session, int(user_id))
    anchor_bid = int(body.get("anchor_broadcast_id") or 0)
    if anchor_bid <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите anchor_broadcast_id — черновик для ротации постов в кампании",
        )
    brow = await session.get(AdminBroadcast, anchor_bid)
    if not brow or int(getattr(brow, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Черновик не найден или недоступен")
    cnt_q = await session.execute(select(func.count()).where(AutopostCampaign.admin_telegram_id == int(user_id)))
    next_seq = int(cnt_q.scalar() or 0) + 1
    title = str(body.get("title") or "").strip()[:255]
    if not title:
        title = f"Кампания {next_seq}"
    row = AutopostCampaign(
        admin_telegram_id=int(user_id),
        user_seq=next_seq,
        title=title,
        anchor_broadcast_id=anchor_bid,
        autopost_json=None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _autopost_campaign_public(row)


@router.patch("/admin/autopost-campaigns/{campaign_id}")
async def api_admin_autopost_campaigns_patch(
    campaign_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import finalize_autopost_json_for_owner, normalize_autopost_payload

    user, full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AutopostCampaign, int(campaign_id))
    if not row or int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if "anchor_broadcast_id" in body:
        ab = int(body.get("anchor_broadcast_id") or 0)
        if ab > 0:
            brow = await session.get(AdminBroadcast, ab)
            if not brow or int(getattr(brow, "admin_telegram_id", 0) or 0) != int(user_id):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Черновик не найден или недоступен")
            row.anchor_broadcast_id = ab
    if "title" in body:
        row.title = str(body.get("title") or "")[:255]
    if "autopost" in body:
        ap_raw = body.get("autopost")
        if ap_raw is None:
            row.autopost_json = None
        else:
            anchor_bid = int(getattr(row, "anchor_broadcast_id", 0) or 0)
            if anchor_bid <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Сначала задайте anchor_broadcast_id (якорный черновик для ротации)",
                )
            owner_tid = int(user_id)
            can_scope_all_self = _broadcast_viewer_can_scope_all(user) and owner_tid == int(user_id)
            merged_raw = ap_raw
            if isinstance(ap_raw, dict) and row.autopost_json:
                try:
                    prev = json.loads(row.autopost_json)
                    if isinstance(prev, dict):
                        prev_clean = {k: v for k, v in prev.items() if k != "_state"}
                        prev_norm = normalize_autopost_payload(prev_clean)
                        if prev_norm:
                            merged_raw = {**prev_norm, **ap_raw}
                except Exception:
                    merged_raw = ap_raw
            try:
                ap = await finalize_autopost_json_for_owner(
                    session,
                    viewer_telegram_id=int(user_id),
                    owner_telegram_id=owner_tid,
                    anchor_broadcast_id=anchor_bid,
                    allow_scope_all_for_owner=can_scope_all_self,
                    force_groups_target=not full,
                    ap_raw=merged_raw,
                    existing_autopost_json=row.autopost_json,
                )
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            row.autopost_json = json.dumps(ap, ensure_ascii=False)
    await session.commit()
    await session.refresh(row)
    return _autopost_campaign_public(row)


@router.delete("/admin/autopost-campaigns/{campaign_id}")
async def api_admin_autopost_campaigns_delete(
    campaign_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import normalize_autopost_payload

    row = await session.get(AutopostCampaign, int(campaign_id))
    if not row or int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    raw = (row.autopost_json or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                clean = {k: v for k, v in parsed.items() if k != "_state"}
                ap = normalize_autopost_payload(clean)
                if ap and str(ap.get("runState") or "").lower() in ("running", "paused"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Сначала остановите автопост кампании (runState: stopped)",
                    )
        except HTTPException:
            raise
        except Exception:
            pass
    await session.delete(row)
    await session.commit()
    return {"ok": True}


@router.get("/admin/autopost-campaigns/{campaign_id}/autopost-stats")
async def api_admin_autopost_campaigns_autopost_stats(
    campaign_id: int,
    days: int = Query(1, ge=1, le=30),
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import normalize_autopost_payload

    row = await session.get(AutopostCampaign, int(campaign_id))
    if not row or int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    ap_dict: dict | None = None
    raw_ap = getattr(row, "autopost_json", None) or ""
    if raw_ap:
        try:
            parsed = json.loads(raw_ap) if isinstance(raw_ap, str) else None
            if isinstance(parsed, dict):
                ap_dict = normalize_autopost_payload(parsed)
        except Exception:
            ap_dict = None

    owner_tid = int(row.admin_telegram_id)
    seed_bid = int(getattr(row, "anchor_broadcast_id", 0) or 0)
    rotation_ids: list[int] = [seed_bid] if seed_bid > 0 else []
    if ap_dict:
        if bool(ap_dict.get("use_all_broadcasts")):
            res = await session.execute(
                select(AdminBroadcast.id).where(
                    AdminBroadcast.admin_telegram_id == owner_tid,
                    AdminBroadcast.status == "draft",
                )
            )
            rotation_ids = sorted({int(x[0]) for x in res.all()} | ({seed_bid} if seed_bid > 0 else set()))
        else:
            bids = [int(x) for x in (ap_dict.get("broadcast_ids") or []) if int(x) > 0]
            rotation_ids = sorted(set(bids + ([seed_bid] if seed_bid > 0 else [])))

    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    if not rotation_ids:
        runs = []
    else:
        rq = await session.execute(
            select(AdminBroadcastRun)
            .where(
                AdminBroadcastRun.broadcast_id.in_(rotation_ids),
                AdminBroadcastRun.created_at >= since,
            )
            .order_by(AdminBroadcastRun.created_at.desc())
            .limit(500)
        )
        runs = list(rq.scalars().all())
    autopost_rows = [r for r in runs if str(getattr(r, "run_source", None) or "") == "autopost"]

    def _is_bot_kind(tk: str) -> bool:
        t = (tk or "").lower()
        return t in {"user", "users", "bot", "bots"}

    def _is_group_kind(tk: str) -> bool:
        t = (tk or "").lower()
        return t in {"group", "groups", "channel", "channels"}

    bots_ok = bots_fail = groups_ok = groups_fail = 0
    bot_rec_total = group_rec_total = 0
    for r in autopost_rows:
        tk = str(getattr(r, "target_kind", "") or "")
        rok = int(getattr(r, "recipient_ok", 0) or 0)
        rfail = int(getattr(r, "recipient_fail", 0) or 0)
        rt = int(getattr(r, "recipient_total", 0) or 0)
        if _is_bot_kind(tk):
            bots_ok += rok
            bots_fail += rfail
            bot_rec_total += rt
        elif _is_group_kind(tk):
            groups_ok += rok
            groups_fail += rfail
            group_rec_total += rt

    posts_per_day = int(ap_dict.get("postsPerDay") or 0) if ap_dict else 0

    runs_payload: list[dict] = []
    for r in autopost_rows[:80]:
        cat = getattr(r, "created_at", None)
        sat = getattr(r, "sent_at", None)
        runs_payload.append(
            {
                "id": int(r.id),
                "broadcast_id": int(r.broadcast_id),
                "target_kind": str(r.target_kind or ""),
                "recipient_total": int(r.recipient_total or 0),
                "recipient_ok": int(r.recipient_ok or 0),
                "recipient_fail": int(r.recipient_fail or 0),
                "created_at": cat.isoformat() if cat else None,
                "sent_at": sat.isoformat() if sat else None,
            }
        )

    from app.services.admin_broadcast import broadcast_url_tracking_configured

    cm = await _admin_broadcast_click_breakdown(session, bids=rotation_ids, since=since)
    clk_users = int(cm["users"])
    clk_groups = int(cm["groups"])
    total_clk = int(cm["total"])
    track_ok = broadcast_url_tracking_configured()
    ap_click_extras = {
        "real_link_clicks": int(cm["link_users"]),
        "real_link_transitions": int(cm["link_groups"]),
        "real_link_clicks_total": int(cm["link_total"]),
        "real_callback_clicks": int(cm["callback_users"]),
        "real_callback_transitions": int(cm["callback_groups"]),
        "real_callback_clicks_total": int(cm["callback_total"]),
        "real_link_items": cm.get("link_items") or [],
        "real_callback_items": cm.get("callback_items") or [],
        "broadcast_url_tracking_configured": bool(track_ok),
    }
    delivered_total = int(bots_ok + groups_ok)
    ctr = (100.0 * float(total_clk) / float(delivered_total)) if delivered_total > 0 else 0.0

    return {
        "campaign_id": int(campaign_id),
        "days": int(days),
        "rotation_broadcast_ids": rotation_ids,
        "posts_per_day_config": posts_per_day,
        "autopost_slots_recorded": len(autopost_rows),
        "bots": {"recipient_ok": bots_ok, "recipient_fail": bots_fail, "recipient_total": bot_rec_total},
        "groups": {
            "recipient_ok": groups_ok,
            "recipient_fail": groups_fail,
            "recipient_total": group_rec_total,
            "clicks": int(clk_users),
            "transitions": int(clk_groups),
            "ctr": round(float(ctr), 2),
        },
        "real_clicks": int(clk_users),
        "real_transitions": int(clk_groups),
        "real_clicks_total": int(total_clk),
        "runs": runs_payload,
        **ap_click_extras,
    }


@router.post("/admin/broadcasts")
async def api_admin_broadcasts_create(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import broadcast_row_to_dict, normalize_keyboard_rows, parse_mode_or_none

    await _require_broadcast_access(session, int(user_id))
    title = str(body.get("title") or "")[:255]
    body_text = str(body.get("body_text") or "")
    pm = parse_mode_or_none(body.get("parse_mode"))
    kbd = normalize_keyboard_rows(body.get("keyboard_rows"))
    row = AdminBroadcast(
        title=title,
        body_text=body_text,
        parse_mode=pm,
        keyboard_json=kbd,
        media_kind="none",
        admin_telegram_id=int(user_id),
        status="draft",
    )
    session.add(row)
    await session.commit()
    q = await session.execute(
        select(AdminBroadcast)
        .options(selectinload(AdminBroadcast.media_items))
        .where(AdminBroadcast.id == int(row.id))
    )
    row = q.scalar_one()
    return broadcast_row_to_dict(row)


@router.patch("/admin/broadcasts/{broadcast_id}")
async def api_admin_broadcasts_patch(
    broadcast_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import (
        broadcast_row_to_dict,
        broadcast_upload_root,
        finalize_autopost_json_for_owner,
        normalize_keyboard_rows,
        parse_mode_or_none,
    )

    user, full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    if (row.status or "") == "sending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя менять шаблон во время активной рассылки")
    if (row.status or "") != "draft":
        row.status = "draft"
        row.error_message = None

    if "autopost" in body:
        ap_raw = body.get("autopost")
        if ap_raw is None:
            row.autopost_json = None
        else:
            owner_tid = int(getattr(row, "admin_telegram_id", 0) or 0)
            can_scope_all_self = _broadcast_viewer_can_scope_all(user) and owner_tid == int(user_id)
            try:
                ap = await finalize_autopost_json_for_owner(
                    session,
                    viewer_telegram_id=int(user_id),
                    owner_telegram_id=owner_tid,
                    anchor_broadcast_id=int(row.id),
                    allow_scope_all_for_owner=can_scope_all_self,
                    force_groups_target=not full,
                    ap_raw=ap_raw,
                    existing_autopost_json=row.autopost_json,
                )
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            row.autopost_json = json.dumps(ap, ensure_ascii=False)

    if "title" in body:
        row.title = str(body.get("title") or "")[:255]
    if "body_text" in body:
        row.body_text = str(body.get("body_text") or "")
    if "parse_mode" in body:
        row.parse_mode = parse_mode_or_none(body.get("parse_mode"))
    if "keyboard_rows" in body:
        row.keyboard_json = normalize_keyboard_rows(body.get("keyboard_rows"))

    if body.get("clear_media"):
        media_q = await session.execute(
            select(AdminBroadcastMedia).where(AdminBroadcastMedia.broadcast_id == int(row.id))
        )
        for m in media_q.scalars().all():
            try:
                p = broadcast_upload_root() / str(m.media_local_name or "")
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
            await session.delete(m)
        if row.media_local_name:
            try:
                p = broadcast_upload_root() / row.media_local_name
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        row.media_kind = "none"
        row.media_local_name = None
        row.media_original_name = None
        row.telegram_file_id = None

    await session.commit()
    q = await session.execute(
        select(AdminBroadcast)
        .options(selectinload(AdminBroadcast.media_items))
        .where(AdminBroadcast.id == int(row.id))
    )
    row = q.scalar_one()
    return broadcast_row_to_dict(row)


@router.post("/admin/broadcasts/{broadcast_id}/media")
async def api_admin_broadcasts_upload_media(
    broadcast_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    media_kind: str = Form(""),
):
    from app.services.admin_broadcast import (
        _MAX_UPLOAD_BYTES,
        broadcast_row_to_dict,
        broadcast_upload_root,
        guess_media_kind_from_name,
        new_local_filename,
        safe_media_kind,
    )

    _u, full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    if (row.status or "") == "sending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя менять медиа во время активной рассылки")
    if (row.status or "") != "draft":
        row.status = "draft"
        row.error_message = None

    data = await file.read()

    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Файл слишком большой")

    # GIF временно отключены по продуктовой логике.
    lower_name = str(file.filename or "").lower()
    ct = str(getattr(file, "content_type", "") or "").lower()
    if lower_name.endswith(".gif") or ct.startswith("image/gif"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GIF отключены. Используйте PNG/JPEG/MP4/MP3 и другие поддерживаемые форматы.")

    mk = safe_media_kind(media_kind) or guess_media_kind_from_name(
        file.filename or "", getattr(file, "content_type", None)
    )
    fname = new_local_filename(file.filename or "upload.bin")
    root = broadcast_upload_root()
    path = root / fname
    path.write_bytes(data)

    item = AdminBroadcastMedia(
        broadcast_id=int(row.id),
        media_kind=mk,
        media_local_name=fname,
        media_original_name=str(file.filename or "")[:255] or None,
        telegram_file_id=None,
    )
    session.add(item)
    row.media_kind = mk
    row.media_local_name = fname
    row.media_original_name = str(file.filename or "")[:255] or None
    row.telegram_file_id = None
    await session.commit()
    q = await session.execute(
        select(AdminBroadcast)
        .options(selectinload(AdminBroadcast.media_items))
        .where(AdminBroadcast.id == int(row.id))
    )
    row = q.scalar_one()
    return broadcast_row_to_dict(row)


@router.get("/admin/broadcasts/{broadcast_id}/media/{media_id}/file")
async def api_admin_broadcasts_media_file(
    broadcast_id: int,
    media_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Отдаёт загруженный файл медиа для превью в админке (с initData)."""
    from pathlib import Path

    from app.services.admin_broadcast import broadcast_upload_root

    viewer, _full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if int(row.admin_telegram_id) != int(user_id) and not _broadcast_viewer_can_scope_all(viewer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    m = await session.get(AdminBroadcastMedia, int(media_id))
    if not m or int(m.broadcast_id) != int(broadcast_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    path = broadcast_upload_root() / str(m.media_local_name or "")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    mk = str(m.media_kind or "photo").lower()
    suffix = Path(path.name).suffix.lower()
    media_type = "application/octet-stream"
    if mk == "photo" or suffix in (".jpg", ".jpeg", ".png", ".webp"):
        if suffix == ".png":
            media_type = "image/png"
        elif suffix == ".webp":
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"
    elif mk == "video" or suffix in (".mp4", ".webm", ".mov"):
        media_type = "video/mp4" if suffix == ".mp4" else "video/webm"
    return FileResponse(
        str(path),
        media_type=media_type,
        filename=str(m.media_original_name or path.name)[:255],
    )


@router.delete("/admin/broadcasts/{broadcast_id}/media/{media_id}")
async def api_admin_broadcasts_delete_media_item(
    broadcast_id: int,
    media_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import broadcast_row_to_dict, broadcast_upload_root

    _u, full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    if (row.status or "") == "sending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя менять медиа во время активной рассылки")
    m = await session.get(AdminBroadcastMedia, int(media_id))
    if not m or int(m.broadcast_id) != int(row.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    try:
        p = broadcast_upload_root() / str(m.media_local_name or "")
        if p.is_file():
            p.unlink()
    except Exception:
        pass
    await session.delete(m)
    await session.commit()
    q = await session.execute(
        select(AdminBroadcast)
        .options(selectinload(AdminBroadcast.media_items))
        .where(AdminBroadcast.id == int(row.id))
    )
    row = q.scalar_one()
    items = list(getattr(row, "media_items", []) or [])
    if items:
        last = items[-1]
        row.media_kind = str(last.media_kind or "photo")
        row.media_local_name = str(last.media_local_name or "")
        row.media_original_name = str(last.media_original_name or "")
        row.telegram_file_id = str(last.telegram_file_id or "") or None
    else:
        row.media_kind = "none"
        row.media_local_name = None
        row.media_original_name = None
        row.telegram_file_id = None
    await session.commit()
    return broadcast_row_to_dict(row)


@router.delete("/admin/broadcasts/{broadcast_id}")
async def api_admin_broadcasts_delete(
    broadcast_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import broadcast_upload_root

    _u, full = await _require_broadcast_access(session, int(user_id))
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    if (row.status or "") == "sending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить во время активной рассылки")
    media_q = await session.execute(select(AdminBroadcastMedia).where(AdminBroadcastMedia.broadcast_id == int(row.id)))
    for m in media_q.scalars().all():
        try:
            p = broadcast_upload_root() / str(m.media_local_name or "")
            if p.is_file():
                p.unlink()
        except Exception:
            pass
    if row.media_local_name:
        try:
            p = broadcast_upload_root() / row.media_local_name
            if p.is_file():
                p.unlink()
        except Exception:
            pass
    await session.delete(row)
    await session.commit()
    return {"ok": True}


@router.post("/admin/broadcasts/{broadcast_id}/quote")
async def api_admin_broadcasts_quote(
    broadcast_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Оценка ⚡ за рассылку (те же target/chat_ids, что у send)."""
    from app.services.broadcast_send_plan import (
        broadcast_charge_tokens,
        estimate_recipient_counts,
        resolve_broadcast_billing_plan,
        resolve_broadcast_target_chat_ids,
    )

    target = str((body or {}).get("target") or "users").strip().lower()
    raw_chat_ids = (body or {}).get("chat_ids") or []
    body_chat_ids: list[int] = []
    if isinstance(raw_chat_ids, list):
        for x in raw_chat_ids:
            try:
                v = int(x)
            except Exception:
                continue
            if v != 0:
                body_chat_ids.append(v)
    if target not in {"users", "groups", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый тип отправки")

    viewer, full = await _require_broadcast_access(session, int(user_id))
    allow_all_groups = _broadcast_viewer_can_scope_all(viewer)
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    if not full and target in ("users", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для Premium доступна рассылка только в ваши группы (не в личку и не «всё»).",
        )

    target_chat_ids: list[int] = []
    if target in {"groups", "all"}:
        target_chat_ids = await resolve_broadcast_target_chat_ids(
            session,
            viewer_telegram_id=int(user_id),
            allow_all_groups=allow_all_groups,
            target=target,
            body_chat_ids=body_chat_ids,
        )
        if body_chat_ids and not target_chat_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверные id чатов: для групп укажите chat_id супергруппы (обычно отрицательное число)",
            )
        if target == "groups" and not target_chat_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нет групп для отправки (проверьте выбор или подключите группу к боту)",
            )

    n_users, n_groups = await estimate_recipient_counts(session, target=target, target_chat_ids=target_chat_ids)
    cost_tokens = broadcast_charge_tokens(n_users=n_users, n_groups=n_groups)
    plan = await resolve_broadcast_billing_plan(
        session,
        viewer=viewer,
        viewer_telegram_id=int(user_id),
        full_admin=full,
        cost_tokens=int(cost_tokens),
        resolved_chat_ids=target_chat_ids,
    )
    aurum = float(getattr(viewer, "aurum_credits", 0.0) or 0.0)
    payer_au = float(getattr(plan.payer_user, "aurum_credits", 0.0) or 0.0)
    partner_bonus = float(getattr(viewer, "bonus_credits", 0.0) or 0.0)
    spendable = round(payer_au, 2)
    can_afford = bool(full or int(cost_tokens) <= 0 or plan.can_afford)
    return {
        "target": target,
        "n_users": int(n_users),
        "n_groups": int(n_groups),
        "cost_tokens": int(cost_tokens),
        "broadcast_charge_applies": not full,
        "aurum_credits": aurum,
        "billing_payer_telegram_id": int(getattr(plan.payer_user, "telegram_id", 0) or 0),
        "billing_payer_aurum": round(payer_au, 2),
        "billing_detail": plan.billing_detail,
        "bonus_credits": partner_bonus,
        "subscription_credits": 0.0,
        "spendable_credits": spendable,
        "can_afford": can_afford,
    }


@router.post("/admin/broadcasts/{broadcast_id}/send")
async def api_admin_broadcasts_send(
    broadcast_id: int,
    background_tasks: BackgroundTasks,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    from app.services.admin_broadcast import run_broadcast_job
    from app.services.broadcast_send_plan import (
        broadcast_charge_tokens,
        debit_user_broadcast_tokens,
        estimate_recipient_counts,
        resolve_broadcast_billing_plan,
        resolve_broadcast_target_chat_ids,
    )

    target = str((body or {}).get("target") or "users").strip().lower()
    keep_draft_after = bool((body or {}).get("keep_draft_after") or (body or {}).get("keepDraftAfter") or False)
    raw_chat_ids = (body or {}).get("chat_ids") or []
    body_chat_ids: list[int] = []
    if isinstance(raw_chat_ids, list):
        for x in raw_chat_ids:
            try:
                v = int(x)
            except Exception:
                continue
            if v != 0:
                body_chat_ids.append(v)
    if target not in {"users", "groups", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый тип отправки")
    _log.warning(
        "broadcast send request: id=%s target=%s raw_chat_ids=%s by_user=%s",
        int(broadcast_id),
        target,
        len(raw_chat_ids) if isinstance(raw_chat_ids, list) else 0,
        int(user_id),
    )

    viewer, full = await _require_broadcast_access(session, int(user_id))
    allow_all_groups = _broadcast_viewer_can_scope_all(viewer)
    row = await session.get(AdminBroadcast, int(broadcast_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not full and int(getattr(row, "admin_telegram_id", 0) or 0) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к этому посту")
    if not full and target in ("users", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для Premium доступна рассылка только в ваши группы (не в личку и не «всё»).",
        )
    if (row.status or "") == "sending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Рассылка уже выполняется")
    if (row.status or "") != "draft":
        row.status = "draft"
        row.error_message = None

    target_chat_ids: list[int] = []
    if target in {"groups", "all"}:
        target_chat_ids = await resolve_broadcast_target_chat_ids(
            session,
            viewer_telegram_id=int(user_id),
            allow_all_groups=allow_all_groups,
            target=target,
            body_chat_ids=body_chat_ids,
        )
        if body_chat_ids and not target_chat_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверные id чатов: для групп укажите chat_id супергруппы (обычно отрицательное число)",
            )
        _log.warning(
            "broadcast send groups filter: id=%s target=%s allow_all=%s selected=%s",
            int(broadcast_id),
            target,
            allow_all_groups,
            len(target_chat_ids),
        )
        if target == "groups" and not target_chat_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нет групп для отправки (проверьте выбор или подключите группу к боту)",
            )

    text_ok = bool((row.body_text or "").strip())
    media_count_q = await session.execute(
        select(func.count()).select_from(AdminBroadcastMedia).where(AdminBroadcastMedia.broadcast_id == int(row.id))
    )
    media_ok = int(media_count_q.scalar() or 0) > 0 or (
        (row.media_kind or "none").lower() != "none" and bool(row.media_local_name)
    )
    if not text_ok and not media_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужен текст или загруженное медиа",
        )

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="BOT_TOKEN не задан")

    n_users, n_groups = await estimate_recipient_counts(session, target=target, target_chat_ids=target_chat_ids)
    cost_tokens = broadcast_charge_tokens(n_users=n_users, n_groups=n_groups)
    spent_aurum = 0.0
    spent_sub = 0.0
    if not full and int(cost_tokens) > 0:
        plan = await resolve_broadcast_billing_plan(
            session,
            viewer=viewer,
            viewer_telegram_id=int(user_id),
            full_admin=full,
            cost_tokens=int(cost_tokens),
            resolved_chat_ids=target_chat_ids,
        )
        if not plan.can_afford:
            pid = int(getattr(plan.payer_user, "telegram_id", 0) or 0)
            pau = round(float(getattr(plan.payer_user, "aurum_credits", 0.0) or 0.0), 2)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Недостаточно AURUM для рассылки: нужно {int(cost_tokens)} ✨ "
                    f"(платит аккаунт {pid}, на счету {pau} ✨). Докупите пакет или переведите AURUM менеджеру."
                ),
            )
        try:
            spent_aurum, spent_sub = await debit_user_broadcast_tokens(
                session,
                user=plan.payer_user,
                full_admin=full,
                broadcast_id=int(row.id),
                cost_tokens=int(cost_tokens),
            )
        except ValueError:
            avail = round(float(getattr(plan.payer_user, "aurum_credits", 0.0) or 0.0), 2)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Недостаточно AURUM для рассылки: нужно {int(cost_tokens)} ✨ "
                    f"(сейчас у плательщика: {avail} ✨). Докупите пакет в разделе «Токены» при активной подписке."
                ),
            ) from None

    row.status = "sending"
    row.last_target = target
    row.sent_at = None
    row.recipient_ok = 0
    row.recipient_fail = 0
    row.error_message = None
    await session.commit()
    _log.warning(
        "broadcast queued: id=%s target=%s selected_groups=%s",
        int(broadcast_id),
        target,
        len(target_chat_ids),
    )
    background_tasks.add_task(
        run_broadcast_job,
        int(broadcast_id),
        target,
        target_chat_ids,
        keep_draft_after=bool(keep_draft_after),
        run_source="manual",
    )
    return {
        "ok": True,
        "queued": True,
        "id": int(broadcast_id),
        "target": target,
        "chat_ids_count": len(target_chat_ids),
        "cost_tokens": int(cost_tokens),
        "spent_aurum": float(spent_aurum),
        "spent_bonus": float(spent_aurum),
        "spent_sub": float(spent_sub),
        "n_users": int(n_users),
        "n_groups": int(n_groups),
    }


# ---------- POST /api/webhooks/yoomoney (HTTP-уведомления кошелька ЮMoney, form-urlencoded) ----------
@router.post("/webhooks/yoomoney")
async def api_yoomoney_wallet_notification(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Входящие переводы на кошелёк ЮMoney (виджет / P2P). Без initData.
    Секрет из настроек HTTP-уведомлений: `YOOMONEY_NOTIFICATION_SECRET`.
    Подпись: параметр `sign` (HMAC-SHA256), см. документацию ЮMoney.
    """
    secret = str(os.getenv("YOOMONEY_NOTIFICATION_SECRET") or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YooMoney notifications not configured",
        )
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid form")
    flat: dict[str, str] = {}
    for k, v in form.multi_items():
        # повторы ключей — оставляем первое значение
        key = str(k)
        if key not in flat:
            flat[key] = str(v)
    from app.services.payments_yoomoney import process_yoomoney_http_notification

    try:
        await process_yoomoney_http_notification(session, flat)
    except PermissionError:
        _log.warning("YooMoney notification: invalid signature")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")
    except RuntimeError as e:
        if "yoomoney_secret" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="YooMoney secret not configured",
            ) from e
        _log.exception("YooMoney notification handler error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="retry",
        ) from e
    except Exception:
        _log.exception("YooMoney notification failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="retry",
        )
    return PlainTextResponse("OK", status_code=status.HTTP_200_OK)


# ---------- POST /api/webhooks/yookassa/:secret (без initData) ----------
@router.post("/webhooks/yookassa/{secret_token}")
async def api_yookassa_webhook(
    secret_token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Входящие уведомления ЮKassa. URL с секретом задаётся в личном кабинете."""
    expected_live = str(os.getenv("YOOKASSA_WEBHOOK_SECRET") or "").strip()
    expected_test = str(os.getenv("YOOKASSA_TEST_WEBHOOK_SECRET") or "").strip()
    configured = [s for s in (expected_live, expected_test) if s]
    valid = False
    if configured:
        valid = any(secrets.compare_digest(secret_token, s) for s in configured)
    else:
        # Fallback для аварийной совместимости: если секреты не заданы в ENV,
        # не блокируем webhook (иначе всегда 404 и платежи не активируются).
        _log.warning("YooKassa webhook secrets are not configured; accepting token from URL")
        valid = True
    if not valid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    from app.services.payments_yookassa import process_yookassa_webhook

    try:
        await process_yookassa_webhook(session, body)
    except Exception:
        _log.exception("YooKassa webhook handler failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="retry")
    return {"ok": True}


# ---------- /api/profanity (зарезервировано; список скрыт, управление — не через Mini App) ----------
@router.get("/profanity")
async def api_profanity_list(_user_id: int = Depends(require_init_data)):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="profanity_list_not_available",
    )


@router.post("/profanity")
async def api_profanity_add(_user_id: int = Depends(require_init_data)):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="profanity_list_not_available",
    )


@router.delete("/profanity/{word:path}")
async def api_profanity_remove(_word: str, _user_id: int = Depends(require_init_data)):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="profanity_list_not_available",
    )


# ---------- POST /api/chat/:id/copy-settings ----------
@router.post("/chat/{chat_id}/copy-settings")
async def api_chat_copy_settings(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Перенести настройки из текущего чата в другой. Body: { "target_chat_id": number }."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    target_id = body.get("target_chat_id")
    if target_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_chat_id required")
    target_id = int(target_id)
    ok_target = await user_can_access_chat(session, user_id, target_id)
    if not ok_target:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Target chat not found or access denied")
    if int(chat_id) == target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source and target must differ")
    try:
        rule = await copy_rule_to_chat(session, int(chat_id), target_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"target_chat_id": target_id, "ok": True}
