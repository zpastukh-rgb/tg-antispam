"""Трекинг кликов по inline callback-кнопкам рассылки (bcM:…, bcHC:…)."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Update

from app.db.models import AdminBroadcast, AdminBroadcastClick
from app.db.session import get_session
from app.services.admin_broadcast import (
    BROADCAST_HIDDEN_CONTINUATION_PREFIX,
    BROADCAST_TRACKED_CALLBACK_PREFIX,
    list_broadcast_callback_payloads_for_layout,
    list_hidden_continuation_configs,
)

logger = logging.getLogger(__name__)

router = Router()

_MEMBER_STATUSES = frozenset(
    {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    }
)


async def _is_channel_or_group_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    status = member.status
    if status in _MEMBER_STATUSES:
        return True
    if status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", False))
    return False


async def _answer_hidden_continuation(bot: Bot, cb: CallbackQuery, text: str) -> None:
    body = str(text or "").strip() or "—"
    if len(body) <= 200:
        try:
            await cb.answer(body, show_alert=True)
        except TelegramBadRequest:
            pass
        return
    try:
        await cb.answer()
    except TelegramBadRequest:
        pass
    uid = int(cb.from_user.id) if cb.from_user else 0
    if uid > 0:
        try:
            await bot.send_message(uid, body)
            try:
                await cb.answer("Текст отправлен в личные сообщения.", show_alert=False)
            except TelegramBadRequest:
                pass
            return
        except Exception:
            logger.debug("hidden continuation DM failed uid=%s", uid, exc_info=True)
    try:
        await cb.answer(body[:200], show_alert=True)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith(BROADCAST_HIDDEN_CONTINUATION_PREFIX))
async def handle_broadcast_hidden_continuation(cb: CallbackQuery, bot: Bot) -> None:
    raw = str(cb.data or "")
    if not raw.startswith(BROADCAST_HIDDEN_CONTINUATION_PREFIX):
        return
    rest = raw[len(BROADCAST_HIDDEN_CONTINUATION_PREFIX) :]
    autopost_campaign_id: int | None = None
    try:
        parts = rest.split(":")
        if len(parts) < 2:
            raise ValueError("bad token")
        broadcast_id = int(parts[0])
        if len(parts) == 2:
            hc_idx = int(parts[1])
        else:
            cid = int(parts[1])
            hc_idx = int(parts[2])
            autopost_campaign_id = cid if cid > 0 else None
    except (ValueError, TypeError):
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass
        return

    if not cb.message or not cb.message.chat or not cb.from_user:
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass
        return

    chat = cb.message.chat
    user_id = int(cb.from_user.id)
    layout_group = chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL)
    target_kind = "group" if layout_group else "user"
    target_id = int(chat.id)

    async with await get_session() as session:
        row = await session.get(AdminBroadcast, int(broadcast_id))
        if not row:
            try:
                await cb.answer()
            except TelegramBadRequest:
                pass
            return
        configs = list_hidden_continuation_configs(row.keyboard_json)
        if hc_idx < 0 or hc_idx >= len(configs):
            try:
                await cb.answer()
            except TelegramBadRequest:
                pass
            return
        cfg = configs[hc_idx]
        if layout_group:
            is_member = await _is_channel_or_group_member(bot, int(chat.id), user_id)
            audience = "member" if is_member else "non_member"
            text = cfg["member_text"] if is_member else cfg["non_member_text"]
            if not text.strip():
                text = cfg["non_member_text"] if is_member else cfg["member_text"]
        else:
            audience = "dm"
            text = cfg["non_member_text"] or cfg["member_text"]
        session.add(
            AdminBroadcastClick(
                broadcast_id=int(broadcast_id),
                target_kind=target_kind,
                target_id=target_id,
                url=(f"callback:hc:{hc_idx}:{audience}")[:2000],
                autopost_campaign_id=autopost_campaign_id,
            )
        )
        await session.commit()

    await _answer_hidden_continuation(bot, cb, text)


@router.callback_query(F.data.startswith(BROADCAST_TRACKED_CALLBACK_PREFIX))
async def handle_broadcast_tracked_callback(cb: CallbackQuery, bot: Bot) -> None:
    raw = str(cb.data or "")
    if not raw.startswith(BROADCAST_TRACKED_CALLBACK_PREFIX):
        return
    rest = raw[len(BROADCAST_TRACKED_CALLBACK_PREFIX) :]
    autopost_campaign_id: int | None = None
    try:
        parts = rest.split(":")
        if len(parts) == 2:
            broadcast_id = int(parts[0])
            idx = int(parts[1])
        elif len(parts) >= 3:
            broadcast_id = int(parts[0])
            cid = int(parts[1])
            idx = int(parts[2])
            autopost_campaign_id = cid if cid > 0 else None
        else:
            raise ValueError("bad token")
    except (ValueError, TypeError):
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass
        return

    if not cb.message or not cb.message.chat:
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass
        return

    chat = cb.message.chat
    layout_group = chat.type in ("group", "supergroup", "channel")
    target_kind = "group" if layout_group else "user"
    target_id = int(chat.id)

    async with await get_session() as session:
        row = await session.get(AdminBroadcast, int(broadcast_id))
        if not row:
            try:
                await cb.answer()
            except TelegramBadRequest:
                pass
            return
        payloads = list_broadcast_callback_payloads_for_layout(
            row.keyboard_json,
            layout_group=layout_group,
        )
        if idx < 0 or idx >= len(payloads):
            try:
                await cb.answer()
            except TelegramBadRequest:
                pass
            return
        inner = payloads[idx]
        session.add(
            AdminBroadcastClick(
                broadcast_id=int(broadcast_id),
                target_kind=target_kind,
                target_id=target_id,
                url=(f"callback:{idx}:{inner}")[:2000],
                autopost_campaign_id=autopost_campaign_id,
            )
        )
        await session.commit()

    from app.main import dp

    new_cq = cb.model_copy(update={"data": inner})
    upd = Update(update_id=0, callback_query=new_cq)
    try:
        await dp.feed_update(bot, upd)
    except Exception:
        logger.exception("broadcast callback redispatch failed bid=%s idx=%s", broadcast_id, idx)
        try:
            await cb.answer("Ошибка обработки кнопки.", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    try:
        await cb.answer()
    except TelegramBadRequest:
        pass
