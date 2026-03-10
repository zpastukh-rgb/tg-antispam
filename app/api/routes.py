# app/api/routes.py
"""REST-маршруты для Mini App."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_init_data
from app.api.deps import get_db
from app.api.service import (
    get_managed_chats,
    get_pending_chats,
    get_or_create_rule,
    get_selected_chat_id,
    set_selected_chat,
    user_can_access_chat,
    count_stopwords,
)
from app.db.models import Chat, Rule
from app.services.user_service import get_or_create_user, can_add_chat

router = APIRouter(prefix="/api", tags=["webapp"])

# Кэш username бота для ссылки «Добавить в группу»
_bot_username: str | None = None


async def _get_bot_username() -> str | None:
    global _bot_username
    if _bot_username:
        return _bot_username
    token = os.getenv("BOT_TOKEN")
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.telegram.org/bot{token}/getMe") as resp:
                data = await resp.json()
                if data.get("ok") and data.get("result"):
                    _bot_username = data["result"].get("username")
                    return _bot_username
    except Exception:
        pass
    return None


def _format_dt(dt):
    if dt is None:
        return None
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(dt)


def _rule_to_dict(rule: Rule, stopwords_count: int = 0) -> dict:
    return {
        "chat_id": rule.chat_id,
        "filter_links": getattr(rule, "filter_links", True),
        "filter_links_mode": getattr(rule, "filter_links_mode", "forbid"),
        "filter_media_mode": getattr(rule, "filter_media_mode", "allow"),
        "filter_buttons_mode": getattr(rule, "filter_buttons_mode", "allow"),
        "filter_mentions": getattr(rule, "filter_mentions", False),
        "action_mode": getattr(rule, "action_mode", "delete"),
        "mute_minutes": int(rule.mute_minutes or 30),
        "newbie_enabled": bool(rule.newbie_enabled),
        "newbie_minutes": int(rule.newbie_minutes or 10),
        "first_message_captcha_enabled": bool(getattr(rule, "first_message_captcha_enabled", False)),
        "all_captcha_minutes": int(getattr(rule, "all_captcha_minutes", 0) or 0),
        "delete_join_messages": bool(getattr(rule, "delete_join_messages", True)),
        "silence_minutes": int(getattr(rule, "silence_minutes", 0) or 0),
        "master_anti_spam": bool(getattr(rule, "master_anti_spam", True)),
        "log_enabled": bool(rule.log_enabled),
        "guardian_messages_enabled": bool(getattr(rule, "guardian_messages_enabled", True)),
        "public_alerts_every_n": int(getattr(rule, "public_alerts_every_n", 5)),
        "public_alerts_min_interval_sec": int(getattr(rule, "public_alerts_min_interval_sec", 300) or 300),
        "auto_reports_enabled": bool(getattr(rule, "auto_reports_enabled", True)),
        "stopwords_count": stopwords_count,
    }


# ---------- GET /api/bot-info ----------
@router.get("/bot-info")
async def api_bot_info(
    user_id: int = Depends(require_init_data),
):
    """Username бота для ссылки «Добавить в группу» (t.me/username?startgroup)."""
    username = await _get_bot_username()
    if not username:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bot username not available")
    return {"username": username, "add_to_group_url": f"https://t.me/{username}?startgroup"}


# ---------- GET /api/me ----------
@router.get("/me")
async def api_me(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Текущий пользователь: тариф, лимиты, кол-во чатов."""
    user = await get_or_create_user(session, user_id)
    chats = await get_managed_chats(session, user_id)
    can_add, current_count, limit = await can_add_chat(session, user_id)
    return {
        "telegram_id": user_id,
        "username": user.username,
        "first_name": user.first_name,
        "tariff": user.tariff or "free",
        "chat_limit": user.chat_limit,
        "chats_count": len(chats),
        "can_add_more": can_add,
        "subscription_until": _format_dt(user.subscription_until),
    }


# ---------- GET /api/chats ----------
@router.get("/chats")
async def api_chats(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Список подключённых чатов."""
    chats = await get_managed_chats(session, user_id)
    selected_id = await get_selected_chat_id(session, user_id)
    return {
        "chats": [
            {
                "id": c.id,
                "title": (c.title or "").strip() or str(c.id),
                "log_chat_id": c.log_chat_id,
                "is_selected": c.id == selected_id,
            }
            for c in chats
        ],
        "selected_chat_id": selected_id,
    }


# ---------- POST /api/chats/select ----------
@router.post("/chats/select")
async def api_chats_select(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Выбрать текущий чат для настроек. body: { "chat_id": number } или { "chat_id": null }."""
    chat_id = body.get("chat_id")
    if chat_id is None:
        chat_id = 0
    else:
        chat_id = int(chat_id)
    if chat_id != 0:
        ok = await user_can_access_chat(session, user_id, chat_id)
        if not ok:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chat not found or access denied")
    await set_selected_chat(session, user_id, chat_id if chat_id != 0 else None)
    return {"selected_chat_id": chat_id if chat_id != 0 else None}


# ---------- GET /api/chat/:id ----------
@router.get("/chat/{chat_id}")
async def api_chat(
    chat_id: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Один чат и его правило (настройки защиты)."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat = await session.get(Chat, int(chat_id))
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    rule = await get_or_create_rule(session, int(chat_id))
    stopwords_count = await count_stopwords(session, int(chat_id))
    return {
        "id": chat.id,
        "title": (chat.title or "").strip() or str(chat.id),
        "log_chat_id": chat.log_chat_id,
        "rule": _rule_to_dict(rule, stopwords_count),
    }


# ---------- PATCH /api/chat/:id/rule ----------
@router.patch("/chat/{chat_id}/rule")
async def api_chat_rule(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Частичное обновление правил чата."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    rule = await get_or_create_rule(session, int(chat_id))
    allowed = {
        "filter_links", "filter_links_mode", "filter_media_mode", "filter_buttons_mode", "filter_mentions",
        "action_mode", "mute_minutes", "newbie_enabled", "newbie_minutes",
        "first_message_captcha_enabled", "all_captcha_minutes", "delete_join_messages",
        "silence_minutes", "master_anti_spam", "log_enabled",
        "guardian_messages_enabled", "public_alerts_every_n", "public_alerts_min_interval_sec",
        "auto_reports_enabled",
    }
    for key, value in body.items():
        if key in allowed and hasattr(rule, key):
            setattr(rule, key, value)
    await session.commit()
    await session.refresh(rule)
    stopwords_count = await count_stopwords(session, int(chat_id))
    return {"rule": _rule_to_dict(rule, stopwords_count)}


# ---------- GET /api/connect/pending ----------
@router.get("/connect/pending")
async def api_connect_pending(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Чаты, добавленные в бота, но ещё не подключённые (для кнопки «подключить»)."""
    pending = await get_pending_chats(session, user_id)
    return {
        "chats": [{"id": c.id, "title": (c.title or "").strip() or str(c.id)} for c in pending[:50]],
    }


# ---------- GET /api/billing ----------
@router.get("/billing")
async def api_billing(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Тариф и лимиты."""
    user = await get_or_create_user(session, user_id)
    chats = await get_managed_chats(session, user_id)
    can_add, current_count, limit = await can_add_chat(session, user_id)
    return {
        "tariff": user.tariff or "free",
        "chat_limit": limit,
        "chats_count": len(chats),
        "can_add_more": can_add,
        "subscription_until": _format_dt(user.subscription_until),
    }
