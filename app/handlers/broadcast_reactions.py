"""Обработка emoji-реакций на сообщениях из рассылки / автокампании."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import MessageReactionUpdated

from app.db.session import get_session
from app.services.broadcast_reactions import (
    added_reaction_keys,
    lookup_broadcast_meta_for_message,
    record_broadcast_reaction_clicks,
    reactor_target_kind_id,
)

logger = logging.getLogger(__name__)

router = Router()


@router.message_reaction()
async def on_broadcast_message_reaction(event: MessageReactionUpdated) -> None:
    chat = event.chat
    if not chat:
        return
    chat_id = int(getattr(chat, "id", 0) or 0)
    message_id = int(getattr(event, "message_id", 0) or 0)
    if chat_id == 0 or message_id <= 0:
        return

    added = added_reaction_keys(event.old_reaction, event.new_reaction)
    if not added:
        return

    target_kind, target_id = reactor_target_kind_id(event)

    async with await get_session() as session:
        meta = await lookup_broadcast_meta_for_message(session, chat_id=chat_id, message_id=message_id)
        if not meta:
            logger.debug(
                "broadcast reaction ignored: no sent_message map chat=%s msg=%s chat_type=%s",
                chat_id,
                message_id,
                getattr(chat, "type", None),
            )
            return
        bid, ap_cid = meta
        await record_broadcast_reaction_clicks(
            session,
            broadcast_id=int(bid),
            target_kind=target_kind,
            target_id=target_id,
            reaction_keys=added,
            autopost_campaign_id=ap_cid,
        )
        await session.commit()
        logger.info(
            "broadcast reaction recorded bid=%s chat=%s msg=%s keys=%s target=%s:%s",
            bid,
            chat_id,
            message_id,
            added,
            target_kind,
            target_id,
        )
