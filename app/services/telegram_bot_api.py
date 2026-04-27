# app/services/telegram_bot_api.py
"""Вызовы Bot API через HTTP (процесс Mini App без aiogram Bot)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat

logger = logging.getLogger(__name__)

# Должен совпадать с CONNECT_REQUEST_ID в app/handlers/panel_dm.py (обработчик chat_shared).
_CONNECT_REQUEST_CHAT_ID = 0x7E17


def _connect_group_keyboard_button() -> Dict[str, Any]:
    """Как _kb_connect_request_chat_with_admin: только bot_administrator_rights (без user_* — иначе список групп сильно режется)."""
    bot_rights: Dict[str, Any] = {
        "is_anonymous": False,
        "can_manage_chat": False,
        "can_delete_messages": True,
        "can_manage_video_chats": False,
        "can_restrict_members": True,
        "can_promote_members": False,
        "can_change_info": False,
        "can_invite_users": True,
        "can_post_stories": False,
        "can_edit_stories": False,
        "can_delete_stories": False,
        "can_pin_messages": True,
    }
    return {
        "text": "➕ Выбрать группу",
        "request_chat": {
            "request_id": _CONNECT_REQUEST_CHAT_ID,
            "chat_is_channel": False,
            "bot_is_member": False,
            "request_title": True,
            "bot_administrator_rights": bot_rights,
        },
    }


async def tg_save_prepared_add_group_button(telegram_user_id: int) -> Optional[str]:
    """
    Подготовленная кнопка выбора чата для Telegram.WebApp.requestChat (Bot API 9.6+).
    """
    data = await _tg_request(
        "savePreparedKeyboardButton",
        user_id=int(telegram_user_id),
        button=_connect_group_keyboard_button(),
    )
    if not data.get("ok"):
        logger.warning("savePreparedKeyboardButton failed: %s", data.get("description") or data)
        return None
    result = data.get("result") or {}
    bid = result.get("id")
    return str(bid) if bid else None


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

async def tg_get_me() -> Optional[Dict[str, Any]]:
    data = await _tg_request("getMe")
    if not data.get("ok"):
        return None
    return data.get("result") or {}

async def tg_get_chat_member(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    data = await _tg_request("getChatMember", chat_id=chat_id, user_id=user_id)
    if not data.get("ok"):
        return None
    return data.get("result") or {}

async def tg_bot_is_admin_in_chat(chat_id: int) -> bool:
    me = await tg_get_me()
    if not me or not me.get("id"):
        return False
    row = await tg_get_chat_member(chat_id, int(me["id"]))
    if not row:
        return False
    status = str(row.get("status") or "").lower()
    return status in ("administrator", "creator")


async def tg_unban_chat_member(chat_id: int, user_id: int) -> bool:
    data = await _tg_request(
        "unbanChatMember",
        chat_id=chat_id,
        user_id=user_id,
        only_if_banned=True,
    )
    return bool(data.get("ok"))


async def tg_restrict_chat_member_unmute(chat_id: int, user_id: int) -> bool:
    """Снять ограничения отправки (размут), совместимо с разными типами чатов."""
    permissions: Dict[str, Any] = {
        "can_send_messages": True,
        "can_send_audios": True,
        "can_send_documents": True,
        "can_send_photos": True,
        "can_send_videos": True,
        "can_send_video_notes": True,
        "can_send_voice_notes": True,
        "can_send_polls": True,
        "can_send_other_messages": True,
        "can_add_web_page_previews": True,
        "can_invite_users": True,
    }
    data = await _tg_request(
        "restrictChatMember",
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        use_independent_chat_permissions=True,
    )
    return bool(data.get("ok"))

async def tg_leave_chat(chat_id: int) -> bool:
    data = await _tg_request("leaveChat", chat_id=chat_id)
    return bool(data.get("ok"))


async def tg_send_message(
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = True,
    reply_markup: Dict[str, Any] | None = None,
    message_thread_id: int | None = None,
) -> Optional[Dict[str, Any]]:
    payload: Dict[str, Any] = {
        "chat_id": int(chat_id),
        "text": str(text or "")[:4096],
        "disable_web_page_preview": bool(disable_web_page_preview),
    }
    if parse_mode:
        payload["parse_mode"] = str(parse_mode)
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if message_thread_id and int(message_thread_id) > 0:
        payload["message_thread_id"] = int(message_thread_id)
    data = await _tg_request("sendMessage", **payload)
    if not data.get("ok"):
        return None
    return data.get("result") or None


async def tg_pin_chat_message(chat_id: int, message_id: int, *, disable_notification: bool = True) -> bool:
    data = await _tg_request(
        "pinChatMessage",
        chat_id=int(chat_id),
        message_id=int(message_id),
        disable_notification=bool(disable_notification),
    )
    return bool(data.get("ok"))


async def tg_delete_message(chat_id: int, message_id: int) -> bool:
    data = await _tg_request(
        "deleteMessage",
        chat_id=int(chat_id),
        message_id=int(message_id),
    )
    if not data.get("ok"):
        from app.services.diagnostics_incidents import record_tg_http_delete_failed

        desc = str(data.get("description") or data)
        await record_tg_http_delete_failed(int(chat_id), int(message_id), desc)
    return bool(data.get("ok"))


async def tg_try_delete_pin_service_messages(
    chat_id: int,
    anchor_message_id: int,
    *,
    spread: int = 18,
    delay_sec: float = 0.45,
) -> None:
    """Best-effort: после pinChatMessage удалить сервисное «закрепил(а) сообщение».

    Telegram не гарантирует id сервисного сообщения; обычно оно следует сразу за закреплённым.
    """
    try:
        await asyncio.sleep(max(0.0, float(delay_sec)))
    except Exception:
        pass
    base = int(anchor_message_id)
    for mid in range(base + 1, base + 1 + max(1, int(spread))):
        try:
            await tg_delete_message(int(chat_id), int(mid))
        except Exception:
            pass


def linked_chat_meta_from_get_chat(info: Dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    """getChat → (linked chat id, linked chat type) или (None, None).

    Telegram Bot API обычно отдает `linked_chat_id` (число), а не вложенный `linked_chat`.
    Для совместимости поддерживаем оба варианта.
    """
    oid: Optional[int] = None
    typ: Optional[str] = None

    raw_id = info.get("linked_chat_id")
    if raw_id is not None:
        try:
            oid = int(raw_id)
        except (TypeError, ValueError):
            oid = None

    lc = info.get("linked_chat")
    if isinstance(lc, dict):
        if oid is None and lc.get("id") is not None:
            try:
                oid = int(lc["id"])
            except (TypeError, ValueError):
                oid = None
        typ_raw = str(lc.get("type") or "").strip().lower()
        if typ_raw:
            typ = typ_raw

    # Если тип не пришел, выводим по типу текущего чата:
    # channel -> linked discussion group/supergroup; group/supergroup -> linked channel.
    if oid is not None and not typ:
        chat_type = str(info.get("type") or "").strip().lower()
        if chat_type == "channel":
            typ = "supergroup"
        elif chat_type in ("group", "supergroup"):
            typ = "channel"

    return oid, typ


def _linked_chat_id_from_get_chat(info: Dict[str, Any]) -> Optional[int]:
    oid, _ = linked_chat_meta_from_get_chat(info)
    return oid


async def refresh_chat_from_telegram(session: AsyncSession, chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Один getChat: обновить title/username в БД и вернуть linked_chat_id (для каналов с обсуждением).
    """
    info = await tg_get_chat(chat_id)
    if not info:
        return None
    linked_chat_id, linked_chat_type = linked_chat_meta_from_get_chat(info)
    title = (info.get("title") or "").strip()
    if not title:
        un = (info.get("username") or "").strip()
        title = (un or str(info.get("id") or chat_id))[:255]
    if not title:
        title = str(chat_id)
    title = title[:255]
    row = await session.get(Chat, chat_id)
    if row:
        row.title = title
        un = info.get("username")
        if un:
            row.username = (str(un).strip()[:255]) or row.username
        kind = str(getattr(row, "chat_kind", None) or "group").strip().lower()
        if kind == "channel":
            # Telegram периодически не возвращает linked_chat для канала даже при живой связке.
            # Не затираем уже известную привязку discussion-группы на None.
            if linked_chat_id is not None:
                row.linked_discussion_chat_id = int(linked_chat_id)
        elif kind != "channel" and hasattr(row, "linked_channel_chat_id"):
            if linked_chat_id is not None and linked_chat_type == "channel":
                row.linked_channel_chat_id = int(linked_chat_id)
            else:
                row.linked_channel_chat_id = None
        await session.commit()
    out: Dict[str, Any] = {"title": title, "linked_chat_id": linked_chat_id, "linked_chat_type": linked_chat_type}
    return out


async def refresh_chat_title_in_db(session: AsyncSession, chat_id: int) -> Optional[str]:
    """Подтянуть актуальное название супергруппы/группы/канала и сохранить в chats.title."""
    snap = await refresh_chat_from_telegram(session, chat_id)
    if not snap:
        return None
    t = snap.get("title")
    return str(t).strip() if t else None


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
