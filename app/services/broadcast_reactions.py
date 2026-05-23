"""Учёт emoji-реакций на сообщениях рассылки (группы / каналы)."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from aiogram.types import MessageReactionUpdated, ReactionTypeCustomEmoji, ReactionTypeEmoji
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminBroadcastClick, AdminBroadcastSentMessage

log = logging.getLogger(__name__)


def reaction_type_key(reaction: Any) -> str | None:
    if isinstance(reaction, ReactionTypeEmoji):
        em = str(getattr(reaction, "emoji", "") or "").strip()
        return f"emoji:{em}" if em else None
    if isinstance(reaction, ReactionTypeCustomEmoji):
        cid = int(getattr(reaction, "custom_emoji_id", 0) or 0)
        return f"ce:{cid}" if cid > 0 else None
    return None


def added_reaction_keys(old_reactions: Iterable[Any] | None, new_reactions: Iterable[Any] | None) -> list[str]:
    """Ключи реакций, появившихся в new по сравнению с old (для одного пользователя на сообщении)."""
    old_keys: set[str] = set()
    for r in old_reactions or []:
        k = reaction_type_key(r)
        if k:
            old_keys.add(k)
    added: list[str] = []
    for r in new_reactions or []:
        k = reaction_type_key(r)
        if k and k not in old_keys:
            added.append(k)
            old_keys.add(k)
    return added


def click_url_for_reaction_key(key: str) -> str:
    return f"reaction:{str(key or '')[:180]}"


def target_kind_for_chat_type(chat_type: str | None) -> str:
    t = str(chat_type or "").strip().lower()
    if t == "channel":
        return "channel"
    if t in {"group", "supergroup"}:
        return "group"
    return "user"


def reactor_target_kind_id(event: MessageReactionUpdated) -> tuple[str, int]:
    chat = event.chat
    kind = target_kind_for_chat_type(getattr(chat, "type", None))
    if event.user:
        return kind, int(event.user.id)
    if event.actor_chat:
        return "group", int(event.actor_chat.id)
    return kind, int(getattr(chat, "id", 0) or 0)


async def register_broadcast_sent_message(
    session: AsyncSession,
    *,
    broadcast_id: int,
    chat_id: int,
    message_id: int,
    target_kind: str,
    autopost_campaign_id: int | None = None,
) -> None:
    bid = int(broadcast_id or 0)
    cid = int(chat_id or 0)
    mid = int(message_id or 0)
    if bid <= 0 or cid == 0 or mid <= 0:
        return
    tk = str(target_kind or "group").strip().lower()
    if tk in ("groups", "users"):
        tk = tk[:-1]
    if tk not in ("group", "user", "channel"):
        tk = "group"
    ap_cid = int(autopost_campaign_id or 0) or None
    try:
        stmt = pg_insert(AdminBroadcastSentMessage).values(
            broadcast_id=bid,
            chat_id=cid,
            message_id=mid,
            target_kind=tk,
            autopost_campaign_id=ap_cid,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["chat_id", "message_id"])
        async with session.begin_nested():
            await session.execute(stmt)
    except Exception as e:
        log.warning(
            "register_broadcast_sent_message failed bid=%s chat=%s msg=%s err=%s",
            bid,
            cid,
            mid,
            e,
        )


async def lookup_broadcast_id_for_message(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
) -> int | None:
    meta = await lookup_broadcast_meta_for_message(session, chat_id=chat_id, message_id=message_id)
    return meta[0] if meta else None


async def lookup_broadcast_meta_for_message(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
) -> tuple[int, int | None] | None:
    cid = int(chat_id or 0)
    mid = int(message_id or 0)
    if cid == 0 or mid <= 0:
        return None
    res = await session.execute(
        select(AdminBroadcastSentMessage.broadcast_id, AdminBroadcastSentMessage.autopost_campaign_id).where(
            AdminBroadcastSentMessage.chat_id == cid,
            AdminBroadcastSentMessage.message_id == mid,
        ).limit(1)
    )
    row = res.first()
    if not row:
        return None
    bid = int(row[0] or 0)
    if bid <= 0:
        return None
    ap_cid = int(row[1] or 0) or None
    return bid, ap_cid


async def record_broadcast_reaction_clicks(
    session: AsyncSession,
    *,
    broadcast_id: int,
    target_kind: str,
    target_id: int,
    reaction_keys: list[str],
    autopost_campaign_id: int | None = None,
) -> int:
    bid = int(broadcast_id or 0)
    if bid <= 0 or not reaction_keys:
        return 0
    tk = str(target_kind or "user")[:16]
    tid = int(target_id or 0)
    ap_cid = int(autopost_campaign_id or 0) or None
    n = 0
    for key in reaction_keys:
        url = click_url_for_reaction_key(key)
        session.add(
            AdminBroadcastClick(
                broadcast_id=bid,
                target_kind=tk,
                target_id=tid,
                url=url[:2000],
                autopost_campaign_id=ap_cid,
            )
        )
        n += 1
    return n
