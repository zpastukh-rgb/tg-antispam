"""Идемпотентные значения в БД при старте процессов (бот, API)."""

from __future__ import annotations

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)

# Пробный premium на 3 дня; активация — в мини-приложении или панели (per-user в promo_code_redemptions).
DEFAULT_TRIAL_PROMO_CODE = "TRIAL3"
DEFAULT_TRIAL_DAYS = 3

# Бессрочный premium для владельца / внутренних тестов (отдельная строка в promo_codes, TRIAL3 не меняем).
# Переопределить код: OWNER_FOREVER_PROMO_CODE=my_secret
# Лимит чатов при активации: OWNER_FOREVER_CHAT_LIMIT (по умолчанию 500)
DEFAULT_OWNER_FOREVER_CODE = "GUARDIAN_OWNER"


def get_owner_forever_promo_code() -> str:
    return (os.getenv("OWNER_FOREVER_PROMO_CODE") or DEFAULT_OWNER_FOREVER_CODE).strip().upper()


def get_owner_forever_chat_limit() -> int:
    try:
        return int(os.getenv("OWNER_FOREVER_CHAT_LIMIT", "500"))
    except ValueError:
        return 500


async def ensure_default_trial_promo(engine: AsyncEngine) -> None:
    """Гарантирует строку промокода TRIAL3 (3 дня premium), не трогая used_at / redemptions."""
    stmt = text(
        """
        INSERT INTO promo_codes (code, tariff, days)
        VALUES (:code, 'premium', :days)
        ON CONFLICT (code) DO UPDATE
        SET tariff = EXCLUDED.tariff,
            days = EXCLUDED.days
        """
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(
                stmt,
                {"code": DEFAULT_TRIAL_PROMO_CODE, "days": DEFAULT_TRIAL_DAYS},
            )
    except Exception as e:
        log.warning("ensure_default_trial_promo skipped: %s", e)


async def ensure_owner_forever_promo(engine: AsyncEngine) -> None:
    """Гарантирует промокод владельца: premium, days=0 (бессрочно), без затрагивания redemptions."""
    code = get_owner_forever_promo_code()
    if not code:
        return
    stmt = text(
        """
        INSERT INTO promo_codes (code, tariff, days)
        VALUES (:code, 'premium', 0)
        ON CONFLICT (code) DO UPDATE
        SET tariff = EXCLUDED.tariff,
            days = EXCLUDED.days
        """
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(stmt, {"code": code})
    except Exception as e:
        log.warning("ensure_owner_forever_promo skipped: %s", e)
