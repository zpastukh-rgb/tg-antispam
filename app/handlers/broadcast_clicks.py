"""Трекинг кликов по inline callback-кнопкам рассылки (bcM:…) и передача во внутренние обработчики."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Update

from app.db.models import AdminBroadcast, AdminBroadcastClick
from app.db.session import get_session
from app.services.admin_broadcast import (
    BROADCAST_TRACKED_CALLBACK_PREFIX,
    list_broadcast_callback_payloads_for_layout,
)

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data.startswith(BROADCAST_TRACKED_CALLBACK_PREFIX))
async def handle_broadcast_tracked_callback(cb: CallbackQuery, bot: Bot) -> None:
    raw = str(cb.data or "")
    if not raw.startswith(BROADCAST_TRACKED_CALLBACK_PREFIX):
        return
    rest = raw[len(BROADCAST_TRACKED_CALLBACK_PREFIX) :]
    try:
        bid_s, idx_s = rest.split(":", 1)
        broadcast_id = int(bid_s)
        idx = int(idx_s)
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
