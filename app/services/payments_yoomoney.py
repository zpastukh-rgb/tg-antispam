# app/services/payments_yoomoney.py
"""
HTTP-уведомления ЮMoney о входящих переводах (кошелёк / карта).

Документация: https://yoomoney.ru/docs/payment-buttons/using-api/notifications
- Подпись `sign` — HMAC-SHA256 (HEX) от отсортированных URL-encoded параметров (кроме `sign`).
- Параметр `sha1_hash` устарел и не будет передаваться с 18.05.2026 — оставляем
  опциональную legacy-проверку на переходный период.

Отличие от ЮKassa: здесь form-urlencoded POST, не JSON webhook.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.user_service import get_or_create_user
from app.services.payments_yookassa import _fulfill_payment
from app.texts.guardian_billing import PREMIUM_PLANS

log = logging.getLogger(__name__)

RFC3986_SAFE = ""


def yoomoney_notifications_configured() -> bool:
    return bool(str(os.getenv("YOOMONEY_NOTIFICATION_SECRET") or "").strip())


def build_yoomoney_sign_message(params: dict[str, str]) -> str:
    """
    Строка для HMAC-SHA256: все параметры кроме `sign`, ключи A→Z,
    значения — URL-encoding UTF-8 по RFC 3986.
    """
    filtered = {k: v for k, v in params.items() if k != "sign"}
    parts: list[str] = []
    for key in sorted(filtered.keys()):
        val = filtered[key]
        enc = quote(val, safe=RFC3986_SAFE)
        parts.append(f"{key}={enc}")
    return "&".join(parts)


def verify_yoomoney_sign(params: dict[str, str], secret: str, sign_hex: str) -> bool:
    if not secret or not sign_hex:
        return False
    msg = build_yoomoney_sign_message(params)
    expected = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected.lower(), sign_hex.strip().lower())
    except Exception:
        return False


def _verify_legacy_sha1_hash(params: dict[str, str], secret: str, sha1_hex: str) -> bool:
    """
    Классическая строка из доков/образцов (до параметра sign):
    notification_type & operation_id & amount & 643 & datetime & sender & codepro & secret & label
    """
    if not secret or not sha1_hex:
        return False
    parts = [
        params.get("notification_type", ""),
        params.get("operation_id", ""),
        params.get("amount", ""),
        "643",
        params.get("datetime", ""),
        params.get("sender", ""),
        str(params.get("codepro", "false")).lower(),
        secret,
        params.get("label", ""),
    ]
    s = "&".join(parts)
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest()
    try:
        return hmac.compare_digest(digest.lower(), sha1_hex.strip().lower())
    except Exception:
        return False


def verify_yoomoney_notification(params: dict[str, str], secret: str) -> bool:
    """Сначала `sign` (актуально), иначе fallback на `sha1_hash` (до 18.05.2026)."""
    sign = (params.get("sign") or "").strip()
    if sign:
        return verify_yoomoney_sign(params, secret, sign)
    sha1 = (params.get("sha1_hash") or "").strip()
    if sha1:
        ok = _verify_legacy_sha1_hash(params, secret, sha1)
        if ok:
            log.warning("YooMoney notification verified via deprecated sha1_hash; migrate to sign")
        return ok
    return False


_LABEL_RE_EXPLICIT = re.compile(
    r"^guard:tgid:(?P<tg>\d+):m:(?P<m>\d+)$",
    re.IGNORECASE,
)
_LABEL_TG_ONLY = re.compile(r"^guard:tgid:(?P<tg>\d+)$", re.IGNORECASE)
_LABEL_RE_SHORT = re.compile(r"^g(?P<tg>\d+)m(?P<m>\d+)$", re.IGNORECASE)


def _months_from_amount_rub(amount: float) -> int | None:
    d = Decimal(str(amount)).quantize(Decimal("0.01"))
    for months, _lbl, price_rub, _sav in PREMIUM_PLANS:
        if d == Decimal(str(price_rub)).quantize(Decimal("0.01")):
            return int(months)
    return None


def _parse_label(label: str) -> tuple[int | None, int | None]:
    """Возвращает (telegram_id, months или None если месяцы из суммы)."""
    raw = (label or "").strip()
    if not raw:
        return None, None
    m = _LABEL_RE_EXPLICIT.match(raw) or _LABEL_RE_SHORT.match(raw)
    if m:
        return int(m.group("tg")), int(m.group("m"))
    m2 = _LABEL_TG_ONLY.match(raw)
    if m2:
        return int(m2.group("tg")), None
    return None, None


async def process_yoomoney_http_notification(session: AsyncSession, flat: dict[str, str]) -> None:
    """
    Обрабатывает одно HTTP-уведомление (после проверки подписи вызывающим кодом).

    Формат метки перевода (поле label в форме оплаты ЮMoney):
      guard:tgid:<telegram_id>:m:<months>   или короткий   g<telegram_id>m<months>
      либо только guard:tgid:<telegram_id> — тогда период определяется по сумме (как в PREMIUM_PLANS).

    Если месяцев в метке нет — подбираем по сумме, совпадающей с тарифом PREMIUM_PLANS.
    """
    secret = str(os.getenv("YOOMONEY_NOTIFICATION_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("yoomoney_secret_not_configured")

    if not verify_yoomoney_notification(flat, secret):
        raise PermissionError("yoomoney_invalid_signature")

    ntype = (flat.get("notification_type") or "").strip()
    if ntype not in ("p2p-incoming", "card-incoming"):
        log.info("YooMoney skip: notification_type=%s", ntype)
        return

    if str(flat.get("test_notification") or "").lower() == "true":
        log.info("YooMoney test_notification accepted, skip fulfillment")
        return

    op_id = str(flat.get("operation_id") or "").strip()
    if not op_id:
        log.warning("YooMoney: missing operation_id")
        return

    existing = await session.execute(
        select(Payment).where(Payment.payment_id == op_id, Payment.provider == "yoomoney").limit(1)
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None:
        if str(getattr(existing_row, "status", "") or "").lower() == "succeeded":
            log.info("YooMoney duplicate succeeded operation_id=%s", op_id)
            return
        log.warning("YooMoney retry pending operation_id=%s — повторное начисление", op_id)

    try:
        amount = float(str(flat.get("amount") or "0").replace(",", "."))
    except ValueError:
        log.warning("YooMoney: bad amount")
        return

    label = flat.get("label") or ""
    tg_id, months_from_label = _parse_label(label)
    if tg_id is None:
        log.warning("YooMoney: в label нужен Telegram ID, см. guard:tgid:<id>:m:<mes> — label=%r", label)
        return
    months = months_from_label
    if months is None:
        months = _months_from_amount_rub(amount)
    if not months or months <= 0:
        log.warning(
            "YooMoney: cannot resolve user/plan label=%r amount=%s — начисление пропущено",
            label,
            amount,
        )
        return

    expected_price = next((float(p[2]) for p in PREMIUM_PLANS if int(p[0]) == int(months)), None)
    if expected_price is None:
        log.warning("YooMoney: неизвестный период months=%s", months)
        return
    if abs(amount - expected_price) > 0.02:
        log.warning(
            "YooMoney: amount %.2f не совпадает с тарифом %s мес. (ожид. %.2f), пропуск",
            amount,
            months,
            expected_price,
        )
        return

    user = await get_or_create_user(session, int(tg_id))
    if existing_row is None:
        pay = Payment(
            user_id=int(user.id),
            amount=float(amount),
            currency="RUB",
            months=int(months),
            tariff="premium",
            status="pending",
            provider="yoomoney",
            payment_id=op_id,
        )
        session.add(pay)
        await session.flush()

    payment_obj: dict[str, Any] = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "created_at": flat.get("datetime"),
        "metadata": {"source": "yoomoney_http"},
    }
    await _fulfill_payment(session, op_id, payment_obj)
