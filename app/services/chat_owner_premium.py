"""Premium-тариф владельца чата (как в routes._is_chat_owner_premium для Mini App)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, User


def user_effective_miniapp_premium(user: User | None, now: datetime | None = None) -> bool:
    """Premium активен так же, как в `routes._is_user_premium_now` (trial + оплата)."""
    now = now or datetime.now(timezone.utc)
    if user is None:
        return False
    tariff = (getattr(user, "tariff", None) or "free").lower()
    sub_until = getattr(user, "subscription_until", None)
    if sub_until is not None:
        if getattr(sub_until, "tzinfo", None) is None:
            sub_until = sub_until.replace(tzinfo=timezone.utc)
        return sub_until > now
    return tariff in ("premium", "pro", "business")


async def chat_owner_has_miniapp_premium(session: AsyncSession, chat_id: int) -> bool:
    row = await session.get(Chat, int(chat_id))
    if not row:
        return False
    tid = int(getattr(row, "owner_user_id", 0) or 0)
    if tid <= 0:
        return False
    owner = (await session.execute(select(User).where(User.telegram_id == tid).limit(1))).scalar_one_or_none()
    return user_effective_miniapp_premium(owner, datetime.now(timezone.utc))
