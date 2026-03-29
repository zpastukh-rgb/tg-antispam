"""Идемпотентные значения в БД при старте процессов (бот, API)."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)

# Пробный premium на 3 дня; активация — в мини-приложении или панели (per-user в promo_code_redemptions).
DEFAULT_TRIAL_PROMO_CODE = "TRIAL3"
DEFAULT_TRIAL_DAYS = 3


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
