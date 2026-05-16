# app/services/payments_yookassa.py
"""Создание платежей ЮKassa и обработка webhook (см. https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start)."""

from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import aiohttp
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Tariff, User, CreditLedger, PartnerCommission
from app.services.credit_policy import REFERRAL_LEVEL_RATES, PARTNER_TOKEN_RUB_RATE
from app.services.token_packs import ALLOWED_TOKEN_PACKS, TOKEN_PACK_PRICES_RUB
from app.services.user_service import (
    TARIFF_CHAT_LIMITS,
    TARIFF_GROUP_LIMITS,
    TARIFF_CHANNEL_LIMITS,
    get_or_create_user,
)
from app.services.chat_limit_enforcer import restore_owner_chats_after_premium
from app.services.chat_owner_premium import user_effective_miniapp_premium
from app.texts.guardian_billing import PREMIUM_PLANS
from app.i18n import normalize_locale, t as i18n_t

log = logging.getLogger(__name__)

_MONTH_TO_PRICE_RUB: dict[int, float] = {p[0]: float(p[2]) for p in PREMIUM_PLANS}
_ALLOWED_MONTHS = frozenset(_MONTH_TO_PRICE_RUB.keys())
_TOKEN_TO_RUB = 2.0

_YOOKASSA_API = "https://api.yookassa.ru/v3/payments"


def _parse_yookassa_utc_dt(val: object | None) -> datetime | None:
    if val is None:
        return None
    s = str(val).strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_receipt_url(payment_obj: dict | None) -> str:
    if not isinstance(payment_obj, dict):
        return ""
    candidates = [
        payment_obj.get("receipt_url"),
        payment_obj.get("receipt"),
    ]
    meta = payment_obj.get("metadata")
    if isinstance(meta, dict):
        candidates.append(meta.get("receipt_url"))
        candidates.append(meta.get("receipt"))
    for v in candidates:
        s = str(v or "").strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
    return ""


def _parse_admin_ids() -> set[int]:
    out: set[int] = set()
    for part in (os.getenv("ADMIN_TELEGRAM_IDS") or "").split(","):
        p = str(part or "").strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except Exception:
            continue
    return out


def _next_payout_monday(after_dt: datetime) -> datetime:
    """Следующий понедельник 00:00 UTC после даты начисления."""
    base = after_dt.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days_ahead = (7 - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return base + timedelta(days=days_ahead)


def _norm_mode(mode: str | None) -> str:
    m = str(mode or "live").strip().lower()
    return "test" if m == "test" else "live"


def _yookassa_env(mode: str | None = "live") -> tuple[str, str, str]:
    m = _norm_mode(mode)
    if m == "test":
        shop = str(os.getenv("YOOKASSA_TEST_SHOP_ID") or os.getenv("YOOKASSA_SHOP_ID") or "").strip()
        secret = str(os.getenv("YOOKASSA_TEST_SECRET_KEY") or os.getenv("YOOKASSA_SECRET_KEY") or "").strip()
        return_url = str(os.getenv("YOOKASSA_TEST_RETURN_URL") or os.getenv("YOOKASSA_RETURN_URL") or "").strip()
    else:
        shop = str(os.getenv("YOOKASSA_SHOP_ID") or "").strip()
        secret = str(os.getenv("YOOKASSA_SECRET_KEY") or "").strip()
        return_url = str(os.getenv("YOOKASSA_RETURN_URL") or "").strip()
    return shop, secret, return_url


def yookassa_configured(mode: str | None = "live") -> bool:
    shop, secret, return_url = _yookassa_env(mode)
    return bool(shop and secret and return_url)


def _mini_app_chats_url() -> str | None:
    base = (
        os.getenv("MINI_APP_URL")
        or os.getenv("WEBAPP_URL")
        or os.getenv("RAILWAY_SERVICE_ACCOMPLISHED_CAT_URL")
        or ""
    ).strip().rstrip("/")
    if not base:
        return None
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return f"{base}/chats"


def _mini_app_admin_broadcast_url() -> str | None:
    base = (
        os.getenv("MINI_APP_URL")
        or os.getenv("WEBAPP_URL")
        or os.getenv("RAILWAY_SERVICE_ACCOMPLISHED_CAT_URL")
        or ""
    ).strip().rstrip("/")
    if not base:
        return None
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return f"{base}/admin?tab=broadcasts"


async def _user_aurum_and_bonus(session: AsyncSession, user_id: int) -> tuple[float, float]:
    """AURUM + партнёрский баланс (для текста после оплаты подписки)."""
    row = await session.execute(select(User).where(User.id == user_id).limit(1))
    user = row.scalar_one_or_none()
    aurum = float(getattr(user, "aurum_credits", 0.0) or 0.0)
    bonus = float(getattr(user, "bonus_credits", 0.0) or 0.0)
    return aurum, bonus


def _basic_auth_header(mode: str | None = "live") -> str:
    shop, secret, _ = _yookassa_env(mode)
    mm = _norm_mode(mode)
    if mm == "live" and str(secret).startswith("test_"):
        raise RuntimeError("yookassa_live_secret_invalid")
    if mm == "test" and str(secret).startswith("live_"):
        raise RuntimeError("yookassa_test_secret_invalid")
    token = base64.b64encode(f"{shop}:{secret}".encode()).decode()
    return f"Basic {token}"


def _money_equal(a: Any, b: Any) -> bool:
    da = Decimal(str(a)).quantize(Decimal("0.01"))
    db = Decimal(str(b)).quantize(Decimal("0.01"))
    return da == db


def apply_premium_months(user: User, months: int) -> None:
    now = datetime.now(timezone.utc)
    base = user.subscription_until if user.subscription_until and user.subscription_until > now else now
    user.subscription_until = base + timedelta(days=30 * int(months))
    user.tariff = Tariff.PREMIUM.value
    user.chat_limit = TARIFF_CHAT_LIMITS.get(Tariff.PREMIUM.value, 20)
    user.group_limit = TARIFF_GROUP_LIMITS.get(Tariff.PREMIUM.value, 20)
    user.channel_limit = TARIFF_CHANNEL_LIMITS.get(Tariff.PREMIUM.value, 20)
    user.subscription_source = "payment"


def apply_premium_days(user: User, days: int) -> None:
    now = datetime.now(timezone.utc)
    base = user.subscription_until if user.subscription_until and user.subscription_until > now else now
    user.subscription_until = base + timedelta(days=max(1, int(days)))
    user.tariff = Tariff.PREMIUM.value
    user.chat_limit = TARIFF_CHAT_LIMITS.get(Tariff.PREMIUM.value, 20)
    user.group_limit = TARIFF_GROUP_LIMITS.get(Tariff.PREMIUM.value, 20)
    user.channel_limit = TARIFF_CHANNEL_LIMITS.get(Tariff.PREMIUM.value, 20)
    user.subscription_source = "payment"


async def _yookassa_create_payment(
    amount_rub: str,
    description: str,
    return_url: str,
    metadata: dict[str, str],
    *,
    mode: str = "live",
    save_payment_method: bool = False,
) -> dict[str, Any]:
    idem = str(uuid.uuid4())
    shop, _, _ = _yookassa_env(mode)
    shop_tail = shop[-4:] if shop else "none"
    log.info("YooKassa create payment mode=%s shop_tail=%s amount=%s", _norm_mode(mode), shop_tail, amount_rub)
    payload: dict[str, Any] = {
        "amount": {"value": amount_rub, "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description[:128],
        "metadata": {str(k): str(v)[:512] for k, v in metadata.items()},
        "save_payment_method": bool(save_payment_method),
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(
            _YOOKASSA_API,
            json=payload,
            headers={
                "Authorization": _basic_auth_header(mode),
                "Idempotence-Key": idem,
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                log.warning("YooKassa create failed %s: %s", resp.status, data)
                desc = data.get("description") if isinstance(data, dict) else None
                raise RuntimeError(str(desc or data))
            return data


def yookassa_autorenew_worker_enabled() -> bool:
    """Фоновые автосписания Premium по сохранённой карте (ENV, по умолчанию включено)."""
    return str(os.getenv("YOOKASSA_AUTORENEW_WORKER_ENABLED", "1")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _autorenew_cooldown_hours() -> int:
    try:
        return max(1, int(os.getenv("YOOKASSA_AUTORENEW_COOLDOWN_HOURS", "20")))
    except ValueError:
        return 20


def _autorenew_window_hours() -> int:
    try:
        return max(1, int(os.getenv("YOOKASSA_AUTORENEW_WINDOW_HOURS", "48")))
    except ValueError:
        return 48


def autorenew_window_hours() -> int:
    """Окно (часы до конца подписки), в котором бот пытается автосписание — для текстов и UI."""
    return _autorenew_window_hours()


async def _yookassa_create_autopayment(
    amount_rub: str,
    description: str,
    payment_method_id: str,
    metadata: dict[str, str],
    *,
    mode: str = "live",
    idempotence_key: str,
) -> dict[str, Any]:
    """
    Автоплатёж по сохранённому payment_method.id (без участия пользователя).
    https://yookassa.ru/developers/payment-acceptance/scenario-extensions/recurring-payments/pay-with-saved
    """
    mm = _norm_mode(mode)
    if not yookassa_configured(mm):
        raise RuntimeError("yookassa_not_configured")
    shop, _, _ = _yookassa_env(mm)
    shop_tail = shop[-4:] if shop else "none"
    pm_short = str(payment_method_id).strip()[:10]
    log.info(
        "YooKassa autopayment mode=%s shop_tail=%s amount=%s pm~=%s",
        mm,
        shop_tail,
        amount_rub,
        pm_short,
    )
    payload: dict[str, Any] = {
        "amount": {"value": amount_rub, "currency": "RUB"},
        "capture": True,
        "payment_method_id": str(payment_method_id).strip(),
        "description": description[:128],
        "metadata": {str(k): str(v)[:512] for k, v in metadata.items()},
    }
    idem = str(idempotence_key or uuid.uuid4())[:128]
    async with aiohttp.ClientSession() as http:
        async with http.post(
            _YOOKASSA_API,
            json=payload,
            headers={
                "Authorization": _basic_auth_header(mm),
                "Idempotence-Key": idem,
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=45),
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                log.warning("YooKassa autopayment HTTP %s: %s", resp.status, data)
                desc_e = data.get("description") if isinstance(data, dict) else None
                raise RuntimeError(str(desc_e or data))
            return data if isinstance(data, dict) else {}


async def _yookassa_get_payment(payment_id: str, *, mode: str = "live") -> dict[str, Any] | None:
    if not payment_id:
        return None
    try:
        auth = _basic_auth_header(mode)
    except Exception:
        return None
    url = f"{_YOOKASSA_API}/{payment_id}"
    async with aiohttp.ClientSession() as http:
        try:
            async with http.get(
                url,
                headers={"Authorization": auth, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status >= 400:
                    return None
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else None
        except Exception:
            return None


async def create_yookassa_subscription_payment(
    session: AsyncSession,
    telegram_id: int,
    months: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    mode: str = "live",
    save_payment_method: bool = False,
) -> str:
    """
    Создаёт запись Payment и платёж в ЮKassa. Возвращает confirmation_url для редиректа пользователя.
    """
    if months not in _ALLOWED_MONTHS:
        raise ValueError("invalid_months")
    if not yookassa_configured(mode):
        raise RuntimeError("yookassa_not_configured")

    amount = _MONTH_TO_PRICE_RUB[months]
    amount_str = f"{Decimal(str(amount)).quantize(Decimal('0.01'))}"

    user = await get_or_create_user(session, telegram_id, username=username, first_name=first_name)
    pay = Payment(
        user_id=user.id,
        amount=amount,
        currency="RUB",
        months=months,
        tariff=Tariff.PREMIUM.value,
        status="pending",
        provider="yookassa",
        payment_id=None,
    )
    session.add(pay)
    await session.flush()

    _, _, return_url = _yookassa_env(mode)
    loc = normalize_locale(getattr(user, "language", None))
    desc = i18n_t(loc, "billing.guardian.yk_desc_premium_months", months=months)

    try:
        payload_meta = {
            "telegram_user_id": str(telegram_id),
            "payment_db_id": str(pay.id),
            "months": str(months),
            "yookassa_mode": _norm_mode(mode),
        }
        try:
            data = await _yookassa_create_payment(
                amount_str,
                desc,
                return_url,
                metadata=payload_meta,
                mode=mode,
                save_payment_method=bool(save_payment_method),
            )
        except RuntimeError as e:
            msg = str(e or "").lower()
            # Не блокируем оплату, если recurring пока не активирован у магазина:
            # повторяем как обычный платеж без привязки payment_method.
            if bool(save_payment_method) and "recurring payments" in msg:
                log.warning("YooKassa recurring unavailable, fallback to one-time payment")
                data = await _yookassa_create_payment(
                    amount_str,
                    desc,
                    return_url,
                    metadata=payload_meta,
                    mode=mode,
                    save_payment_method=False,
                )
            else:
                raise
    except Exception:
        await session.rollback()
        raise

    conf = data.get("confirmation") if isinstance(data.get("confirmation"), dict) else {}
    conf_url = conf.get("confirmation_url")
    yid = data.get("id")
    if not conf_url or not yid:
        await session.rollback()
        raise RuntimeError("invalid_yookassa_response")

    pay.payment_id = str(yid)
    await session.commit()
    return str(conf_url)


async def create_yookassa_tokens_payment(
    session: AsyncSession,
    telegram_id: int,
    tokens: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    mode: str = "live",
) -> str:
    """Создаёт оплату пакета токенов (сумма из прайса пакетов; число токенов хранится в Payment.months)."""
    token_count = int(tokens)
    if token_count not in ALLOWED_TOKEN_PACKS:
        raise ValueError("invalid_tokens_pack")
    if not yookassa_configured(mode):
        raise RuntimeError("yookassa_not_configured")

    amount = float(TOKEN_PACK_PRICES_RUB[token_count])
    amount_str = f"{Decimal(str(amount)).quantize(Decimal('0.01'))}"
    user = await get_or_create_user(session, telegram_id, username=username, first_name=first_name)
    pay = Payment(
        user_id=user.id,
        amount=amount,
        currency="RUB",
        months=token_count,
        tariff="tokens",
        status="pending",
        provider="yookassa",
        payment_id=None,
    )
    session.add(pay)
    await session.flush()
    _, _, return_url = _yookassa_env(mode)
    loc = normalize_locale(getattr(user, "language", None))
    desc = i18n_t(loc, "billing.guardian.yk_desc_tokens", count=token_count)
    try:
        data = await _yookassa_create_payment(
            amount_str,
            desc,
            return_url,
            metadata={
                "telegram_user_id": str(telegram_id),
                "payment_db_id": str(pay.id),
                "tokens": str(token_count),
                "yookassa_mode": _norm_mode(mode),
            },
            mode=mode,
            save_payment_method=False,
        )
    except Exception:
        await session.rollback()
        raise
    conf = data.get("confirmation") if isinstance(data.get("confirmation"), dict) else {}
    conf_url = conf.get("confirmation_url")
    yid = data.get("id")
    if not conf_url or not yid:
        await session.rollback()
        raise RuntimeError("invalid_yookassa_response")
    pay.payment_id = str(yid)
    await session.commit()
    return str(conf_url)


async def create_yookassa_binding_probe_payment(
    session: AsyncSession,
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    mode: str = "live",
) -> str:
    """Тестовый тариф для админки: 2 дня Premium за 1 RUB, с сохранением payment_method."""
    if not yookassa_configured(mode):
        raise RuntimeError("yookassa_not_configured")
    amount = 1.0
    amount_str = "1.00"
    user = await get_or_create_user(session, telegram_id, username=username, first_name=first_name)
    pay = Payment(
        user_id=user.id,
        amount=amount,
        currency="RUB",
        months=2,  # здесь используем как «дни», см. tariff == premium_probe
        tariff="premium_probe",
        status="pending",
        provider="yookassa",
        payment_id=None,
    )
    session.add(pay)
    await session.flush()
    _, _, return_url = _yookassa_env(mode)
    loc = normalize_locale(getattr(user, "language", None))
    desc = i18n_t(loc, "billing.guardian.yk_desc_binding_probe")
    try:
        data = await _yookassa_create_payment(
            amount_str,
            desc,
            return_url,
            metadata={
                "telegram_user_id": str(telegram_id),
                "payment_db_id": str(pay.id),
                "plan": "binding_probe_2d_1rub",
                "yookassa_mode": _norm_mode(mode),
            },
            mode=mode,
            save_payment_method=True,
        )
    except Exception:
        await session.rollback()
        raise
    conf = data.get("confirmation") if isinstance(data.get("confirmation"), dict) else {}
    conf_url = conf.get("confirmation_url")
    yid = data.get("id")
    if not conf_url or not yid:
        await session.rollback()
        raise RuntimeError("invalid_yookassa_response")
    pay.payment_id = str(yid)
    await session.commit()
    return str(conf_url)


async def process_yookassa_webhook(session: AsyncSession, body: dict) -> None:
    """Обрабатывает тело входящего уведомления ЮKassa."""
    event = body.get("event") or body.get("type")
    obj = body.get("object")
    if not isinstance(obj, dict):
        return
    yid = obj.get("id")
    if not yid:
        return
    yid = str(yid)

    if event == "payment.succeeded":
        await _fulfill_payment(session, yid, obj)
    elif event == "payment.canceled":
        await _mark_payment_canceled(session, yid)


async def reconcile_user_pending_yookassa_payments(session: AsyncSession, telegram_id: int) -> int:
    """
    Fallback для mini app: проверяет pending-платежи пользователя напрямую в YooKassa и
    применяет успешные без ожидания webhook.
    """
    user = await get_or_create_user(session, int(telegram_id))
    q = (
        select(Payment)
        .where(
            Payment.user_id == int(user.id),
            Payment.provider == "yookassa",
            Payment.status == "pending",
        )
        .order_by(Payment.id.desc())
        .limit(10)
    )
    rows = (await session.execute(q)).scalars().all()
    applied = 0
    for row in rows:
        yid = str(getattr(row, "payment_id", "") or "").strip()
        if not yid:
            continue
        data = await _yookassa_get_payment(yid, mode="live")
        if not data:
            data = await _yookassa_get_payment(yid, mode="test")
        if not data:
            continue
        status_s = str(data.get("status") or "").strip().lower()
        if status_s == "succeeded":
            await _fulfill_payment(session, yid, data)
            applied += 1
        elif status_s == "canceled":
            await _mark_payment_canceled(session, yid)
    return applied


async def _fulfill_payment(session: AsyncSession, yookassa_id: str, payment_obj: dict) -> None:
    res = await session.execute(select(Payment).where(Payment.payment_id == yookassa_id).limit(1))
    row = res.scalar_one_or_none()
    if not row:
        log.warning("YooKassa webhook: no Payment for yookassa_id=%s", yookassa_id)
        return
    if row.status == "succeeded":
        return

    amt = (payment_obj.get("amount") or {}).get("value")
    if amt is not None and not _money_equal(amt, row.amount):
        log.error("YooKassa amount mismatch payment=%s", yookassa_id)
        return
    receipt_url = _extract_receipt_url(payment_obj)
    if receipt_url:
        row.receipt_url = receipt_url

    user = await session.get(User, row.user_id)
    if not user:
        log.error("YooKassa: user id=%s missing", row.user_id)
        return

    pm = payment_obj.get("payment_method") if isinstance(payment_obj.get("payment_method"), dict) else {}
    pm_saved = bool(pm.get("saved"))
    pm_type = str(pm.get("type") or "").strip() or None
    pm_card = pm.get("card") if isinstance(pm.get("card"), dict) else {}
    pm_last4 = str(pm_card.get("last4") or "").strip() or None
    pm_id = str(pm.get("id") or "").strip() or None
    user.payment_method_bound = pm_saved
    user.payment_method_type = pm_type
    user.payment_method_last4 = pm_last4
    user.yookassa_last_mode = "test" if bool(payment_obj.get("test")) else "live"

    is_tokens_payment = (str(getattr(row, "tariff", "") or "").lower() == "tokens")
    is_binding_probe = (str(getattr(row, "tariff", "") or "").lower() == "premium_probe")
    if not is_tokens_payment and not is_binding_probe:
        user.subscription_autorenew_months = int(row.months)
        if pm_id and pm_saved:
            user.yookassa_payment_method_id = pm_id
    if is_tokens_payment:
        pack_n = int(getattr(row, "months", 0) or 0)
        if pack_n > 0:
            added_tokens = pack_n
        else:
            added_tokens = int(round(float(row.amount or 0.0) / _TOKEN_TO_RUB))
        user.aurum_credits = float(getattr(user, "aurum_credits", 0.0) or 0.0) + float(added_tokens)
        session.add(
            CreditLedger(
                user_id=int(user.id),
                delta=float(added_tokens),
                reason="tokens_purchase",
                external_key=f"tokens_purchase:{row.id}",
            )
        )
    elif is_binding_probe:
        apply_premium_days(user, int(getattr(row, "months", 2) or 2))
        user.aurum_credits = round(float(getattr(user, "aurum_credits", 0.0) or 0.0) + 1.0, 4)
        session.add(
            CreditLedger(
                user_id=int(user.id),
                delta=1.0,
                reason="subscription_probe_gift",
                external_key=f"sub_probe_gift:{row.id}"[:128],
            )
        )
        await restore_owner_chats_after_premium(session, int(getattr(user, "telegram_id", 0) or 0))
    else:
        apply_premium_months(user, row.months)
        # Подарок к подписке в AURUM: в 2 раза меньше старого правила (раньше amount/2 ₽ за ⚡).
        gift_aurum = round(float(row.amount or 0.0) / _TOKEN_TO_RUB / 2.0, 2)
        user.aurum_credits = round(float(getattr(user, "aurum_credits", 0.0) or 0.0) + gift_aurum, 4)
        if gift_aurum > 1e-9:
            session.add(
                CreditLedger(
                    user_id=int(user.id),
                    delta=float(gift_aurum),
                    reason="subscription_gift_aurum",
                    external_key=f"subscription_gift:{row.id}"[:128],
                )
            )
        if getattr(user, "subscription_activated_at", None) is None:
            act_at = _parse_yookassa_utc_dt(payment_obj.get("captured_at")) or _parse_yookassa_utc_dt(
                payment_obj.get("created_at")
            )
            user.subscription_activated_at = act_at or datetime.now(timezone.utc)
        # Новый оплаченный период — счётчик попыток автосписания для следующего цикла обнуляем
        user.autorenew_last_attempt_at = None
        await restore_owner_chats_after_premium(session, int(getattr(user, "telegram_id", 0) or 0))

    # Первая ли успешная оплата этого пользователя.
    paid_before_res = await session.execute(
        select(Payment.id).where(
            Payment.user_id == row.user_id,
            Payment.status == "succeeded",
            Payment.id != row.id,
        ).limit(1)
    )
    first_paid = paid_before_res.scalar_one_or_none() is None

    ref_notify_texts: list[tuple[int, str]] = []
    now_utc = datetime.now(timezone.utc)
    # 3 уровня партнерки: 15% / 10% / 5%.
    # Анти-арбитраж по цепочке: не платим при цикле A→B→A и не дублируем уровень при повторе tg.
    chain_tg_ids: list[int] = []
    seen_chain: set[int] = set()
    buyer_tg = int(user.telegram_id)
    current_tg = int(getattr(user, "referred_by_tg_id", 0) or 0)
    for _level in range(3):
        if not current_tg:
            break
        if current_tg == buyer_tg:
            break
        if current_tg in seen_chain:
            break
        seen_chain.add(current_tg)
        chain_tg_ids.append(current_tg)
        next_ref_res = await session.execute(select(User.referred_by_tg_id).where(User.telegram_id == current_tg).limit(1))
        current_tg = int(next_ref_res.scalar_one_or_none() or 0)

    def _partner_available_at_dt() -> datetime:
        base = _next_payout_monday(now_utc + timedelta(days=7))
        try:
            extra_days = int(str(os.getenv("PARTNER_HOLD_EXTRA_DAYS") or "0").strip() or "0")
        except Exception:
            extra_days = 0
        if extra_days > 0:
            base = base + timedelta(days=extra_days)
        return base

    for level, rate in REFERRAL_LEVEL_RATES:
        if level > len(chain_tg_ids):
            continue
        owner_tg_id = int(chain_tg_ids[level - 1] or 0)
        if not owner_tg_id or owner_tg_id == int(user.telegram_id):
            continue
        ref_res = await session.execute(select(User).where(User.telegram_id == owner_tg_id).limit(1))
        ref_user = ref_res.scalar_one_or_none()
        if not ref_user:
            continue
        # Уровни 2–3 только при активной подписке Premium у партнёра, получающего комиссию (Free — только уровень 1).
        if level > 1 and not user_effective_miniapp_premium(ref_user, now_utc):
            continue
        reward_rub = round(float(row.amount or 0.0) * float(rate), 2)
        reward_tokens = round(reward_rub / PARTNER_TOKEN_RUB_RATE, 2)
        # Для совместимости с текущим UI — начисляем партнерские токены сразу.
        ref_user.bonus_credits = float(getattr(ref_user, "bonus_credits", 0.0) or 0.0) + reward_tokens
        if level == 1:
            ref_user.ref_sales_total = float(getattr(ref_user, "ref_sales_total", 0.0) or 0.0) + float(row.amount or 0.0)
            ref_user.ref_earned_credits = float(getattr(ref_user, "ref_earned_credits", 0.0) or 0.0) + reward_tokens
            if first_paid:
                ref_user.ref_paid_count = int(getattr(ref_user, "ref_paid_count", 0) or 0) + 1

        is_owner_fast = str(getattr(ref_user, "username", "") or "").lower() == "pastukh_viscera"
        available_at = now_utc if is_owner_fast else _partner_available_at_dt()
        comm = PartnerCommission(
            owner_user_id=int(ref_user.id),
            source_user_id=int(user.id),
            payment_id=int(row.id),
            level=int(level),
            rate=float(rate),
            sales_amount_rub=float(row.amount or 0.0),
            reward_amount_rub=reward_rub,
            status="available" if is_owner_fast else "pending",
            available_at=available_at,
        )
        session.add(comm)

        bal_tok = round(float(getattr(ref_user, "bonus_credits", 0.0) or 0.0), 2)
        bal_rub = round(bal_tok * PARTNER_TOKEN_RUB_RATE, 2)
        ref_lang = normalize_locale(getattr(ref_user, "language", None))
        ref_notify_texts.append(
            (
                int(owner_tg_id),
                i18n_t(
                    ref_lang,
                    "billing.guardian.partner_commission",
                    level=level,
                    rate_pct=int(rate * 100),
                    reward_tokens=reward_tokens,
                    reward_rub=f"{reward_rub:.2f}",
                    balance_tokens=f"{bal_tok:.2f}",
                    balance_rub=f"{bal_rub:.2f}",
                ),
            )
        )
    row.status = "succeeded"
    await session.commit()

    try:
        from app.texts.guardian_billing import build_premium_payment_success_text
        from app.services.telegram_notify import send_user_dm

        pay_lang = normalize_locale(getattr(user, "language", None))

        if is_tokens_payment:
            pack_n = int(getattr(row, "months", 0) or 0)
            added_tokens = pack_n if pack_n > 0 else int(round(float(row.amount or 0.0) / _TOKEN_TO_RUB))
            text = i18n_t(
                pay_lang,
                "billing.guardian.tokens_payment_success",
                added=added_tokens,
                amount=f"{float(row.amount):.0f}",
            )
        elif is_binding_probe:
            saved_key = (
                "billing.guardian.probe_card_saved_yes" if pm_saved else "billing.guardian.probe_card_saved_no"
            )
            saved_txt = i18n_t(pay_lang, saved_key)
            card_tail = f" · ****{pm_last4}" if pm_last4 else ""
            text = i18n_t(
                pay_lang,
                "billing.guardian.probe_binding_success",
                saved=saved_txt,
                card_tail=card_tail,
            )
        else:
            aurum_bal, bonus_credits = await _user_aurum_and_bonus(session, int(user.id))
            gift_aurum = round(float(row.amount or 0.0) / _TOKEN_TO_RUB / 2.0, 2)
            body = build_premium_payment_success_text(
                months=row.months,
                amount_rub=float(row.amount),
                subscription_until=user.subscription_until,
                gift_aurum=float(gift_aurum),
                aurum_balance=float(aurum_bal),
                bonus_credits=bonus_credits,
                lang=pay_lang,
            )
            text = f"{i18n_t(pay_lang, 'billing.guardian.subscription_renewal_header')}\n\n{body}"
        admin_broadcast_url = _mini_app_admin_broadcast_url()
        receipt_url = _extract_receipt_url(payment_obj) or str(getattr(row, "receipt_url", "") or "").strip()
        reply_markup = None
        buttons_row: list[dict[str, object]] = []
        if admin_broadcast_url:
            buttons_row.append(
                {
                    "text": i18n_t(pay_lang, "billing.guardian.btn_configure_broadcast"),
                    "web_app": {"url": admin_broadcast_url},
                }
            )
        if receipt_url:
            buttons_row.append(
                {
                    "text": i18n_t(pay_lang, "billing.guardian.btn_receipt"),
                    "url": receipt_url,
                }
            )
        if buttons_row:
            reply_markup = {"inline_keyboard": [buttons_row]}
        await send_user_dm(user.telegram_id, text, reply_markup=reply_markup)
        for tg_id, msg in ref_notify_texts:
            await send_user_dm(tg_id, msg)
        if not is_tokens_payment and not receipt_url:
            alert_loc = normalize_locale(os.getenv("ADMIN_ALERT_LOCALE", "en"))
            warn = i18n_t(
                alert_loc,
                "billing.guardian.admin_missing_receipt_dm",
                user_tg_id=int(getattr(user, "telegram_id", 0) or 0),
                payment_db_id=int(getattr(row, "id", 0) or 0),
                yookassa_payment_id=str(getattr(row, "payment_id", "") or ""),
                amount=f"{float(getattr(row, 'amount', 0.0) or 0.0):.2f}",
            )
            for admin_tg_id in sorted(_parse_admin_ids()):
                try:
                    await send_user_dm(int(admin_tg_id), warn)
                except Exception:
                    log.exception("failed to send missing receipt_url alert to admin=%s", admin_tg_id)
            log.error(
                "payment succeeded without receipt_url user_tg_id=%s payment_db_id=%s yookassa_id=%s",
                int(getattr(user, "telegram_id", 0) or 0),
                int(getattr(row, "id", 0) or 0),
                str(getattr(row, "payment_id", "") or ""),
            )
    except Exception:
        log.exception("YooKassa: failed to notify user telegram_id=%s after payment", user.telegram_id)
        try:
            from app.services.admin_diagnostics_service import record_user_incident

            tid = int(getattr(user, "telegram_id", 0) or 0)
            await record_user_incident(
                kind="payment_notify",
                category="payment",
                summary_ru=i18n_t("ru", "billing.guardian.incident_payment_notify_failed"),
                telegram_ids=[tid] if tid > 0 else [],
                detail_snippet=f"telegram_id={tid} payment_db_id={int(getattr(row, 'id', 0) or 0)}",
                method="WEBHOOK",
                path="yookassa_payment_notify",
                status_code=502,
            )
        except Exception:
            log.exception("record_user_incident after payment notify failure")


async def _mark_payment_canceled(session: AsyncSession, yookassa_id: str) -> None:
    res = await session.execute(select(Payment).where(Payment.payment_id == yookassa_id).limit(1))
    row = res.scalar_one_or_none()
    if row and row.status == "pending":
        row.status = "canceled"
        await session.commit()


async def _notify_autorenew_card_revoked(
    telegram_id: int, *, lang: str | None = None, bot: Any = None
) -> None:
    if not telegram_id:
        return
    loc = normalize_locale(lang)
    text = i18n_t(loc, "billing.guardian.autorenew_card_revoked")
    try:
        from app.services.telegram_notify import send_user_dm

        await send_user_dm(int(telegram_id), text)
    except Exception:
        log.exception("autorenew notify revoke failed tg=%s", telegram_id)


async def _handle_autorenew_canceled(
    session: AsyncSession,
    user: User,
    payment_obj: dict[str, Any],
    *,
    bot: Any = None,
) -> None:
    """Отмена автоплатежа: при отзыве разрешения — сбрасываем привязку как в ручном «отключить автопродление»."""
    details = payment_obj.get("cancellation_details") if isinstance(payment_obj.get("cancellation_details"), dict) else {}
    reason = str(details.get("reason") or "").strip().lower()
    revoke = "permission" in reason or reason == "permission_revoked"
    if revoke:
        user.payment_method_bound = False
        user.payment_method_type = None
        user.payment_method_last4 = None
        user.yookassa_payment_method_id = None
        user.subscription_autorenew_months = None
        session.add(user)
    tid = int(getattr(user, "telegram_id", 0) or 0)
    if revoke and tid > 0:
        await _notify_autorenew_card_revoked(tid, lang=getattr(user, "language", None), bot=bot)


async def try_yookassa_autorenew_for_user(
    session: AsyncSession,
    user: User,
    *,
    bot: Any = None,
) -> bool:
    """
    Пытается списать Premium по сохранённому payment_method_id в окне до окончания подписки.
    Возвращает True, если платёж сразу succeeded и _fulfill_payment отработал.
    """
    if not yookassa_autorenew_worker_enabled():
        return False
    if not yookassa_configured("live") and not yookassa_configured("test"):
        return False
    if str(getattr(user, "subscription_source", "") or "").strip().lower() != "payment":
        return False
    if not bool(getattr(user, "payment_method_bound", False)):
        return False
    pm_id = str(getattr(user, "yookassa_payment_method_id", "") or "").strip()
    if not pm_id:
        return False
    sub_until = getattr(user, "subscription_until", None)
    if not sub_until:
        return False
    now = datetime.now(timezone.utc)
    if sub_until.tzinfo is None:
        sub_until = sub_until.replace(tzinfo=timezone.utc)
    else:
        sub_until = sub_until.astimezone(timezone.utc)
    if sub_until <= now:
        return False
    win = timedelta(hours=_autorenew_window_hours())
    if sub_until > now + win:
        return False
    cooldown = timedelta(hours=_autorenew_cooldown_hours())
    last_att = getattr(user, "autorenew_last_attempt_at", None)
    if last_att is not None:
        if last_att.tzinfo is None:
            last_att = last_att.replace(tzinfo=timezone.utc)
        else:
            last_att = last_att.astimezone(timezone.utc)
        if now - last_att < cooldown:
            return False

    res = await session.execute(
        update(User)
        .where(
            User.id == int(user.id),
            User.yookassa_payment_method_id.isnot(None),
            or_(
                User.autorenew_last_attempt_at.is_(None),
                User.autorenew_last_attempt_at < now - cooldown,
            ),
        )
        .values(autorenew_last_attempt_at=now)
        .returning(User.id)
    )
    if res.scalar_one_or_none() is None:
        await session.rollback()
        return False

    months = int(getattr(user, "subscription_autorenew_months", 0) or 0)
    if months not in _ALLOWED_MONTHS:
        months = 1
    amount = _MONTH_TO_PRICE_RUB[months]
    amount_str = f"{Decimal(str(amount)).quantize(Decimal('0.01'))}"
    mode = str(getattr(user, "yookassa_last_mode", None) or "live").strip().lower()
    if mode not in ("live", "test"):
        mode = "live"
    if not yookassa_configured(mode):
        if yookassa_configured("live"):
            mode = "live"
        elif yookassa_configured("test"):
            mode = "test"
    if not yookassa_configured(mode):
        log.warning("YooKassa autorenew: no configured mode for user_id=%s", user.id)
        await session.commit()
        return False

    tg_id = int(getattr(user, "telegram_id", 0) or 0)
    idem = f"autorenew-u{user.id}-until{sub_until.date().isoformat()}"
    loc = normalize_locale(getattr(user, "language", None))
    desc = i18n_t(loc, "billing.guardian.yk_desc_autorenew", months=months)
    meta = {
        "telegram_user_id": str(tg_id),
        "months": str(months),
        "autorenew": "1",
        "yookassa_mode": _norm_mode(mode),
    }
    try:
        data = await _yookassa_create_autopayment(
            amount_str,
            desc,
            pm_id,
            meta,
            mode=mode,
            idempotence_key=idem,
        )
    except Exception as e:
        log.warning("YooKassa autorenew API user_id=%s: %s", user.id, e)
        await session.commit()
        return False

    yid = str(data.get("id") or "").strip()
    if not yid:
        await session.commit()
        return False
    st = str(data.get("status") or "").strip().lower()

    dup = await session.execute(
        select(Payment.id).where(Payment.payment_id == yid, Payment.provider == "yookassa").limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        log.info("YooKassa autorenew: payment %s already in DB, skip duplicate", yid)
        await session.commit()
        return False

    pay = Payment(
        user_id=int(user.id),
        amount=float(amount),
        currency="RUB",
        months=int(months),
        tariff=Tariff.PREMIUM.value,
        status="pending",
        provider="yookassa",
        payment_id=yid,
    )
    session.add(pay)
    await session.flush()
    if st == "succeeded":
        await _fulfill_payment(session, yid, data)
        return True
    if st == "pending":
        await session.commit()
        return False
    if st == "canceled":
        pay.status = "canceled"
        u2 = await session.get(User, int(user.id))
        if u2:
            await _handle_autorenew_canceled(session, u2, data, bot=bot)
        await session.commit()
        return False
    await session.commit()
    return False


async def run_yookassa_autorenew_batch(*, bot: Any = None, limit: int = 40) -> int:
    """
    Находит пользователей в окне автопродления и по очереди пытается списать оплату.
    Вызывается из планировщика бота (reminders). Возвращает число успешных мгновенных списаний.
    """
    if not yookassa_autorenew_worker_enabled():
        return 0
    from app.db.session import get_session

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=_autorenew_window_hours())
    q = (
        select(User)
        .where(
            User.tariff.in_((Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value)),
            User.subscription_source == "payment",
            User.payment_method_bound == True,  # noqa: E712
            User.yookassa_payment_method_id.isnot(None),
            User.subscription_until.is_not(None),
            User.subscription_until > now,
            User.subscription_until <= window_end,
        )
        .order_by(User.subscription_until.asc())
        .limit(int(limit))
    )
    async with await get_session() as session:
        rows = (await session.execute(q)).scalars().all()
    ok = 0
    for u in rows:
        try:
            async with await get_session() as session:
                u2 = await session.get(User, int(getattr(u, "id", 0) or 0))
                if not u2:
                    continue
                if await try_yookassa_autorenew_for_user(session, u2, bot=bot):
                    ok += 1
        except Exception:
            log.exception("YooKassa autorenew batch user_id=%s", getattr(u, "id", None))
    return ok
