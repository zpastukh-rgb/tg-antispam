# app/db/models.py

from __future__ import annotations

import enum
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


# =========================================================
# BASE
# =========================================================

class Base(DeclarativeBase):
    pass


# =========================================================
# CHAT (главная таблица)
# =========================================================

class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # кто подключил чат
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    # куда слать логи
    log_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # включен ли антиспам
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # служебные данные
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # статистика
    messages_checked: Mapped[int] = mapped_column(Integer, default=0)
    messages_deleted: Mapped[int] = mapped_column(Integer, default=0)
    users_banned: Mapped[int] = mapped_column(Integer, default=0)

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

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


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
