"""Premium-тариф владельца чата (как в routes._is_chat_owner_premium для Mini App)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, User

_PREMIUM_TARIFFS = frozenset({"premium", "pro", "business"})


def _normalize_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def user_premium_subscription_snapshot(user: User | None, now: datetime | None = None) -> dict[str, Any]:
    """Единая проверка Premium: оплата, промокод, триал, бессрочный tariff без даты."""
    now = _normalize_utc(now) or datetime.now(timezone.utc)
    if user is None:
        return {
            "subscription_active": False,
            "subscription_forever": False,
            "subscription_days_left": None,
            "subscription_until": None,
            "subscription_source": "",
            "tariff": "free",
        }
    tariff = str(getattr(user, "tariff", None) or "free").strip().lower()
    source = str(getattr(user, "subscription_source", "") or "").strip().lower()
    sub_until = _normalize_utc(getattr(user, "subscription_until", None))

    is_active = False
    if sub_until is not None:
        is_active = sub_until > now
    elif tariff in _PREMIUM_TARIFFS:
        is_active = True

    is_forever = bool(is_active and sub_until is None and tariff in _PREMIUM_TARIFFS)
    days_left: int | None = None
    if is_active and sub_until is not None:
        days_left = max(0, (sub_until.date() - now.date()).days)

    return {
        "subscription_active": bool(is_active),
        "subscription_forever": bool(is_forever),
        "subscription_days_left": days_left,
        "subscription_until": sub_until,
        "subscription_source": source,
        "tariff": tariff,
    }


def user_effective_miniapp_premium(user: User | None, now: datetime | None = None) -> bool:
    """Premium активен: оплата / промокод / триал / бессрочный tariff."""
    return bool(user_premium_subscription_snapshot(user, now).get("subscription_active"))


async def chat_owner_has_miniapp_premium(session: AsyncSession, chat_id: int) -> bool:
    row = await session.get(Chat, int(chat_id))
    if not row:
        return False
    tid = int(getattr(row, "owner_user_id", 0) or 0)
    if tid <= 0:
        return False
    owner = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    return user_effective_miniapp_premium(owner, datetime.now(timezone.utc))
