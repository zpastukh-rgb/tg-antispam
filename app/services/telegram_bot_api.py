# app/services/telegram_bot_api.py
"""Вызовы Bot API через HTTP (процесс Mini App без aiogram Bot)."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat

logger = logging.getLogger(__name__)


async def _tg_request(method: str, **kwargs: Any) -> Dict[str, Any]:
    token = os.getenv("BOT_TOKEN")
    if not token:
        return {"ok": False, "description": "BOT_TOKEN not set"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=kwargs, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json(content_type=None)
    except Exception as e:
        logger.debug("telegram_bot_api %s: %s", method, e)
        return {"ok": False, "description": str(e)}


async def tg_get_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    data = await _tg_request("getChat", chat_id=chat_id)
    if not data.get("ok"):
        return None
    return data.get("result") or {}


async def tg_unban_chat_member(chat_id: int, user_id: int) -> bool:
    data = await _tg_request(
        "unbanChatMember",
        chat_id=chat_id,
        user_id=user_id,
        only_if_banned=True,
    )
    return bool(data.get("ok"))


async def refresh_chat_title_in_db(session: AsyncSession, chat_id: int) -> Optional[str]:
    """Подтянуть актуальное название супергруппы/группы и сохранить в chats.title."""
    info = await tg_get_chat(chat_id)
    if not info:
        return None
    title = (info.get("title") or "").strip()
    if not title:
        return None
    title = title[:255]
    row = await session.get(Chat, chat_id)
    if row:
        row.title = title
        un = info.get("username")
        if un:
            row.username = (str(un).strip()[:255]) or row.username
        await session.commit()
    return title


async def unban_user_in_all_managed_groups(session: AsyncSession, user_id: int) -> int:
    """
    Снять блокировку (unban) в группах из нашей БД (не лог-чаты).
    Вызывать после удаления пользователя из глобальной антиспам-базы.
    """
    res = await session.execute(select(Chat.id).where(Chat.is_log_chat.is_(False)))
    chat_ids: List[int] = [int(r[0]) for r in res.all()]
    ok = 0
    for cid in chat_ids:
        if await tg_unban_chat_member(cid, user_id):
            ok += 1
    return ok


def private_chat_profile(info: Optional[Dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    """Из ответа getChat для private: (display_name, username без @)."""
    if not info or (info.get("type") or "").lower() != "private":
        return None, None
    fn = (info.get("first_name") or "").strip()
    ln = (info.get("last_name") or "").strip()
    display = (f"{fn} {ln}".strip()) or None
    un = info.get("username")
    username = (str(un).strip().lstrip("@")[:64]) if un else None
    return display, username
