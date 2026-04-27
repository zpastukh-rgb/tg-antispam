"""Перенос записей в БД при апгрейде обычной группы в супергруппу (новый chat_id от Telegram)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, Rule
from app.db.session import get_session

logger = logging.getLogger(__name__)

_MIGRATE_RE = re.compile(r"migrated to a supergroup with id\s*(-?\d+)", re.I)

# Если information_schema недоступен или схема обрезана — тот же набор, что раньше.
_FALLBACK_TABLES_WITH_CHAT_ID: tuple[str, ...] = (
    "chat_managers",
    "chat_manager_invites",
    "new_members",
    "moderation_logs",
    "join_captcha_sessions",
    "whitelist_domains",
    "whitelist_users",
    "whitelist_sender_chats",
    "link_blacklist",
    "stop_words",
    "spam_spike_notify_sent",
    "spam_spike_group_ping_sent",
    "chat_spike_alerts",
    "chat_seen_members",
    "chat_reputation_words",
    "chat_reputation_scores",
    "chat_reputation_events",
)


def parse_migrate_to_supergroup_id(exc: BaseException) -> int | None:
    """Достаёт целевой chat_id из текста ошибки Telegram (Bad Request: group chat was upgraded…)."""
    raw = str(exc or "")
    m = _MIGRATE_RE.search(raw)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _copy_chat_row(old: Chat, new_id: int) -> Chat:
    return Chat(
        id=int(new_id),
        owner_user_id=int(old.owner_user_id),
        is_log_chat=bool(getattr(old, "is_log_chat", False)),
        log_chat_id=int(old.log_chat_id) if old.log_chat_id is not None else None,
        is_active=bool(getattr(old, "is_active", True)),
        title=getattr(old, "title", None),
        username=getattr(old, "username", None),
        chat_kind=str(getattr(old, "chat_kind", None) or "group")[:16] or "group",
        linked_discussion_chat_id=(
            int(old.linked_discussion_chat_id) if old.linked_discussion_chat_id is not None else None
        ),
        linked_channel_chat_id=(int(old.linked_channel_chat_id) if old.linked_channel_chat_id is not None else None),
        messages_checked=int(getattr(old, "messages_checked", 0) or 0),
        messages_deleted=int(getattr(old, "messages_deleted", 0) or 0),
        users_banned=int(getattr(old, "users_banned", 0) or 0),
        last_activity_at=getattr(old, "last_activity_at", None),
    )


async def _exec(session: AsyncSession, sql: str, params: dict[str, Any]) -> None:
    await session.execute(text(sql), params)


async def _discover_tables_with_column(session: AsyncSession, column: str) -> list[str]:
    """Таблицы в user-схеме с колонкой column (PostgreSQL public / SQLite main)."""
    q = text(
        """
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.column_name = :col
          AND t.table_type = 'BASE TABLE'
          AND c.table_schema NOT IN ('information_schema', 'pg_catalog', 'sqlite_temp_master')
          AND c.table_schema IN ('public', 'main')
        ORDER BY c.table_name
        """
    )
    try:
        r = await session.execute(q, {"col": column})
        names = [str(row[0]) for row in r.fetchall() if row[0]]
        return sorted(set(names))
    except Exception as e:
        logger.warning("chat migrate: discovery column=%s failed: %s", column, e)
        return []


async def remap_group_chat_ids(old_id: int, new_id: int) -> bool:
    """
    old_id — прежний id группы, new_id — id супергруппы из Telegram.
    Возвращает True, если перенос выполнен (или нечего переносить).
    """
    old_id = int(old_id)
    new_id = int(new_id)
    if old_id == new_id:
        return True

    async with await get_session() as session:
        async with session.begin():
            old = await session.get(Chat, old_id)
            if not old:
                logger.info("chat migrate: old chat %s not in DB, skip", old_id)
                return True
            if await session.get(Chat, new_id):
                logger.info("chat migrate: target chat %s already exists, skip remap from %s", new_id, old_id)
                return False

            session.add(_copy_chat_row(old, new_id))
            await session.flush()

            await session.execute(update(Rule).where(Rule.chat_id == old_id).values(chat_id=new_id))

            chat_id_tables = await _discover_tables_with_column(session, "chat_id")
            if not chat_id_tables:
                chat_id_tables = list(_FALLBACK_TABLES_WITH_CHAT_ID)
            skip_chat_id = {"chats", "rules"}
            for tbl in chat_id_tables:
                if tbl in skip_chat_id:
                    continue
                await _exec(
                    session,
                    f'UPDATE "{tbl}" SET chat_id = :new WHERE chat_id = :old',
                    {"new": new_id, "old": old_id},
                )

            msg_tables = await _discover_tables_with_column(session, "message_chat_id")
            if not msg_tables:
                msg_tables = ["join_captcha_sessions"]
            for tbl in msg_tables:
                await _exec(
                    session,
                    f'UPDATE "{tbl}" SET message_chat_id = :new WHERE message_chat_id = :old',
                    {"new": new_id, "old": old_id},
                )

            for stmt, params in (
                (
                    "UPDATE user_context SET selected_chat_id = :new WHERE selected_chat_id = :old",
                    {"new": new_id, "old": old_id},
                ),
                ("UPDATE chats SET log_chat_id = :new WHERE log_chat_id = :old", {"new": new_id, "old": old_id}),
                (
                    "UPDATE chats SET linked_discussion_chat_id = :new WHERE linked_discussion_chat_id = :old",
                    {"new": new_id, "old": old_id},
                ),
                (
                    "UPDATE chats SET linked_channel_chat_id = :new WHERE linked_channel_chat_id = :old",
                    {"new": new_id, "old": old_id},
                ),
                ("UPDATE channels SET chat_id = :new WHERE chat_id = :old", {"new": new_id, "old": old_id}),
            ):
                try:
                    await _exec(session, stmt, params)
                except Exception as e:
                    logger.warning("chat migrate: extra stmt failed (%s): %s", stmt[:48], e)

            await session.execute(delete(Chat).where(Chat.id == old_id))

    logger.info("chat migrate: remapped group %s -> supergroup %s", old_id, new_id)
    return True
