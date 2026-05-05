"""Таблицы только в БД персональных данных (отдельный engine)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PiiBase(DeclarativeBase):
    pass


class UserPersonalProfile(PiiBase):
    """
    Персональные атрибуты аккаунта Telegram, которые не храним в основной БД при включённом PII.
    Ключ — telegram_id (тот же, что User.telegram_id в основной БД).
    """

    __tablename__ = "user_personal_profiles"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
