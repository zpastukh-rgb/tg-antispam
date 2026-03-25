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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Tariff, User
from app.services.user_service import TARIFF_CHAT_LIMITS, get_or_create_user
from app.texts.guardian_billing import PREMIUM_PLANS

log = logging.getLogger(__name__)

_MONTH_TO_PRICE_RUB: dict[int, float] = {p[0]: float(p[2]) for p in PREMIUM_PLANS}
_ALLOWED_MONTHS = frozenset(_MONTH_TO_PRICE_RUB.keys())
_YOOKASSA_API = "https://api.yookassa.ru/v3/payments"


def yookassa_configured() -> bool:
    return bool(
        os.getenv("YOOKASSA_SHOP_ID")
        and os.getenv("YOOKASSA_SECRET_KEY")
        and os.getenv("YOOKASSA_RETURN_URL")
    )


def _basic_auth_header() -> str:
    shop = os.getenv("YOOKASSA_SHOP_ID", "")
    secret = os.getenv("YOOKASSA_SECRET_KEY", "")
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


async def _yookassa_create_payment(
    amount_rub: str,
    description: str,
    return_url: str,
    metadata: dict[str, str],
) -> dict[str, Any]:
    idem = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "amount": {"value": amount_rub, "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description[:128],
        "metadata": {str(k): str(v)[:512] for k, v in metadata.items()},
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(
            _YOOKASSA_API,
            json=payload,
            headers={
                "Authorization": _basic_auth_header(),
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


async def create_yookassa_subscription_payment(
    session: AsyncSession,
    telegram_id: int,
    months: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
) -> str:
    """
    Создаёт запись Payment и платёж в ЮKassa. Возвращает confirmation_url для редиректа пользователя.
    """
    if months not in _ALLOWED_MONTHS:
        raise ValueError("invalid_months")
    if not yookassa_configured():
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

    return_url = os.environ["YOOKASSA_RETURN_URL"].strip()
    desc = f"Guardian Premium {months} мес."

    try:
        data = await _yookassa_create_payment(
            amount_str,
            desc,
            return_url,
            metadata={
                "telegram_user_id": str(telegram_id),
                "payment_db_id": str(pay.id),
                "months": str(months),
            },
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

    user = await session.get(User, row.user_id)
    if not user:
        log.error("YooKassa: user id=%s missing", row.user_id)
        return

    apply_premium_months(user, row.months)
    row.status = "succeeded"
    await session.commit()

    try:
        from app.texts.guardian_billing import build_premium_payment_success_text
        from app.services.telegram_notify import send_user_dm

        text = build_premium_payment_success_text(
            months=row.months,
            amount_rub=float(row.amount),
            subscription_until=user.subscription_until,
        )
        await send_user_dm(user.telegram_id, text)
    except Exception:
        log.exception("YooKassa: failed to notify user telegram_id=%s after payment", user.telegram_id)


async def _mark_payment_canceled(session: AsyncSession, yookassa_id: str) -> None:
    res = await session.execute(select(Payment).where(Payment.payment_id == yookassa_id).limit(1))
    row = res.scalar_one_or_none()
    if row and row.status == "pending":
        row.status = "canceled"
        await session.commit()
