# app/db/models.py

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    func,
    String,
    UniqueConstraint,
    Integer,
    ForeignKey,
    Index
)

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# =========================================================
# ENUMS
# =========================================================

class ActionMode(str, enum.Enum):
    delete = "delete"
    mute = "mute"
    ban = "ban"


class Tariff(str, enum.Enum):
    FREE = "free"
    PREMIUM = "premium"
    # Оставлены для обратной совместимости, считаются как premium
    PRO = "pro"
    BUSINESS = "business"


# =========================================================
# BASE
# =========================================================

class Base(DeclarativeBase):
    pass


# =========================================================
# USER (SaaS-пользователь, подписка, лимиты)
# =========================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tariff: Mapped[str] = mapped_column(String(32), default=Tariff.FREE.value)
    chat_limit: Mapped[int] = mapped_column(Integer, default=3)
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active")

    # ТЗ Напоминания: первое /start, этапы напоминаний (0=none, 1=12h, 2=24h, 3=3d, 4=done)
    first_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_stage: Mapped[int] = mapped_column(Integer, default=0)
    reports_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# =========================================================
# CHAT (главная таблица: защищаемые и лог-чаты)
# =========================================================

class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # кто подключил чат (владелец)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    # True = эта группа только лог-чат (зарегистрирована через /setlog)
    is_log_chat: Mapped[bool] = mapped_column(Boolean, default=False)

    # куда слать логи (только для защищаемых чатов)
    log_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # включен ли антиспам (для защищаемых)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # служебные данные
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # статистика
    messages_checked: Mapped[int] = mapped_column(Integer, default=0)
    messages_deleted: Mapped[int] = mapped_column(Integer, default=0)
    users_banned: Mapped[int] = mapped_column(Integer, default=0)

    # ТЗ Напоминания: активность чата для «Guardian сообщения раз в 3 дня» (обновляется при модерации)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


# =========================================================
# CHANNEL (если бот работает с каналами)
# =========================================================

class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    # discussion group
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# =========================================================
# RULES (настройки антиспама)
# =========================================================

class Rule(Base):
    __tablename__ = "rules"

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True
    )

    # фильтры
    filter_links: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_mentions: Mapped[bool] = mapped_column(Boolean, default=False)

    # режим наказания
    action_mode: Mapped[str] = mapped_column(
        String(16),
        default=ActionMode.delete.value
    )

    mute_minutes: Mapped[int] = mapped_column(Integer, default=60)

    # защита
    anti_edit: Mapped[bool] = mapped_column(Boolean, default=False)

    # новичок режим
    newbie_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    newbie_minutes: Mapped[int] = mapped_column(Integer, default=10)

    # логи
    log_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Публичные сообщения Guardian раз в N удалений (ТЗ ПРАВКИ 2)
    public_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    public_alerts_every_n: Mapped[int] = mapped_column(Integer, default=5)
    public_alerts_min_interval_sec: Mapped[int] = mapped_column(Integer, default=300)
    public_alerts_last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ТЗ Напоминания: Guardian сообщения в группе (раз в 3 дня, не чаще 72ч)
    guardian_messages_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_guardian_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ТЗ Автоматические отчёты: дайджест в чат отчётов раз в сутки
    auto_reports_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_auto_report_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ТЗ доработка Защита: капча на первое сообщение, фильтры (режимы allow/captcha/forbid)
    first_message_captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    filter_links_mode: Mapped[str] = mapped_column(String(16), default="forbid")
    filter_media_mode: Mapped[str] = mapped_column(String(16), default="allow")
    filter_buttons_mode: Mapped[str] = mapped_column(String(16), default="allow")
    all_captcha_minutes: Mapped[int] = mapped_column(Integer, default=0)
    delete_join_messages: Mapped[bool] = mapped_column(Boolean, default=True)
    silence_minutes: Mapped[int] = mapped_column(Integer, default=0)
    master_anti_spam: Mapped[bool] = mapped_column(Boolean, default=True)

    # Антинакрутка: оповещение и реакция на массовый вход
    antinakrutka_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    antinakrutka_joins_threshold: Mapped[int] = mapped_column(Integer, default=10)
    antinakrutka_window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    antinakrutka_action: Mapped[str] = mapped_column(String(32), default="alert")  # alert | alert_restrict
    antinakrutka_restrict_minutes: Mapped[int] = mapped_column(Integer, default=30)

    # Антиспам база: проверять вступивших по общей базе пользователей
    use_global_antispam_db: Mapped[bool] = mapped_column(Boolean, default=False)

    # Фильтр мата: удалять/наказывать сообщения с матерными словами (общая таблица profanity_words)
    filter_profanity_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# =========================================================
# CHAT SEEN MEMBER (для очистки от удалённых аккаунтов)
# =========================================================

class ChatSeenMember(Base):
    """Участники, которых видели в чате (сообщения или вход). Нужны для проверки на удалённые аккаунты."""
    __tablename__ = "chat_seen_members"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =========================================================
# PROFANITY WORDS (общая таблица матерных слов для фильтра)
# =========================================================

class ProfanityWord(Base):
    """Глобальный список матерных слов для фильтрации сообщений."""
    __tablename__ = "profanity_words"

    word: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# GLOBAL ANTISPAM USER (общая база по всем группам бота)
# =========================================================

class GlobalAntispamUser(Base):
    """Глобальный чёрный список пользователей: проверка при вступлении в любую группу."""
    __tablename__ = "global_antispam_users"

    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, primary_key=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# WHITELIST DOMAIN
# =========================================================

class WhitelistDomain(Base):
    __tablename__ = "whitelist_domains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    domain: Mapped[str] = mapped_column(String(255), index=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "domain", name="uq_whitelist_domain"),
    )


# =========================================================
# WHITELIST USERS
# =========================================================

class WhitelistUser(Base):
    __tablename__ = "whitelist_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_whitelist_user"),
    )


# =========================================================
# STOP WORDS
# =========================================================

class StopWord(Base):
    __tablename__ = "stop_words"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    word: Mapped[str] = mapped_column(String(64), index=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "word", name="uq_stopword_chat_word"),
    )


# =========================================================
# USER CONTEXT (панель управления)
# =========================================================

class UserContext(Base):
    __tablename__ = "user_context"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    selected_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


# =========================================================
# CHAT MANAGERS
# =========================================================

class ChatManager(Base):
    __tablename__ = "chat_managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True
    )

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    added_by: Mapped[int] = mapped_column(BigInteger)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_manager"),
    )


# =========================================================
# NEW MEMBERS (режим новичка)
# =========================================================

class NewMember(Base):
    __tablename__ = "new_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    joined_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_new_member"),
    )


# =========================================================
# AUDIT LOG (история действий бота)
# =========================================================

class ModerationLog(Base):
    __tablename__ = "moderation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    action: Mapped[str] = mapped_column(String(32))

    reason: Mapped[str | None] = mapped_column(String(255))

    message_text: Mapped[str | None] = mapped_column(String(2000))

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        Index("idx_modlog_chat", "chat_id"),
    )


# =========================================================
# PROMO CODE (промокоды для активации Premium / пробного периода)
# =========================================================

class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tariff: Mapped[str] = mapped_column(String(32), default=Tariff.PREMIUM.value)  # premium, premium_trial
    days: Mapped[int] = mapped_column(Integer, default=0)  # 0 = бессрочно до явной отмены, 3 = пробный 3 дня
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromoCodeRedemption(Base):
    """Один пользователь (telegram_id) — не более одной активации данного промокода."""

    __tablename__ = "promo_code_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_code_id", "telegram_user_id", name="uq_promo_code_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# PAYMENT (история оплат, задел под интеграцию)
# =========================================================

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)

    amount: Mapped[float] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    months: Mapped[int] = mapped_column(Integer)
    tariff: Mapped[str] = mapped_column(String(32))

    status: Mapped[str] = mapped_column(String(32), default="pending")
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
