"""Передача владения чатом в Guard другому Telegram-админу."""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.service import get_selected_chat_id, set_selected_chat
from app.db.models import Channel, Chat, ChatManager, ChatManagerInvite, User
from app.services.telegram_bot_api import tg_get_chat_member
from app.services.user_service import can_add_chat_by_kind, get_or_create_user


async def transfer_chat_ownership(
    session: AsyncSession,
    *,
    chat_id: int,
    from_user_id: int,
    to_user_id: int,
) -> dict:
    """
    Меняет owner_user_id у Chat (и Channel при наличии).
    Новый владелец должен быть administrator/creator в Telegram.
    """
    cid = int(chat_id)
    old_owner = int(from_user_id)
    new_owner = int(to_user_id)
    if cid <= 0 or old_owner <= 0 or new_owner <= 0:
        raise ValueError("invalid_ids")
    if old_owner == new_owner:
        raise ValueError("same_owner")

    chat = await session.get(Chat, cid)
    if not chat or bool(getattr(chat, "is_log_chat", False)):
        raise ValueError("invalid_chat")
    if int(getattr(chat, "owner_user_id", 0) or 0) != old_owner:
        raise ValueError("not_owner")

    mem = await tg_get_chat_member(cid, new_owner)
    role = str((mem or {}).get("status") or "").lower()
    if role not in ("administrator", "creator"):
        raise ValueError("target_not_tg_admin")

    target_user = (
        await session.execute(select(User).where(User.telegram_id == new_owner).limit(1))
    ).scalar_one_or_none()
    if not target_user:
        target_user = await get_or_create_user(session, new_owner)
    if not target_user:
        raise ValueError("target_user_unknown")

    kind = str(getattr(chat, "chat_kind", "group") or "group").strip().lower() or "group"
    can_add, cur_count, lim = await can_add_chat_by_kind(session, new_owner, kind)
    if not can_add:
        raise ValueError(f"target_chat_limit:{cur_count}:{lim}")

    chat.owner_user_id = new_owner
    session.add(chat)

    ch_row = await session.get(Channel, cid)
    if ch_row is not None:
        ch_row.owner_user_id = new_owner
        session.add(ch_row)

    await session.execute(
        delete(ChatManager).where(ChatManager.chat_id == cid, ChatManager.user_id == new_owner)
    )
    await session.execute(
        update(ChatManagerInvite)
        .where(ChatManagerInvite.chat_id == cid)
        .values(owner_user_id=new_owner)
    )

    sel_old = await get_selected_chat_id(session, old_owner)
    if sel_old is not None and int(sel_old) == cid:
        await set_selected_chat(session, old_owner, None)

    await session.flush()
    return {
        "chat_id": cid,
        "old_owner_user_id": old_owner,
        "new_owner_user_id": new_owner,
        "chat_kind": kind,
    }
