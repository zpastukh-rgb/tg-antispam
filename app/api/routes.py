# app/api/routes.py
"""REST-маршруты для Mini App."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, status

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
    list_stopwords,
    add_stopword,
    delete_stopword,
    copy_rule_to_chat,
    apply_promo_code,
)
from app.db.models import Chat, Rule
from app.services.user_service import get_or_create_user, can_add_chat

router = APIRouter(prefix="/api", tags=["webapp"])
_log = logging.getLogger(__name__)

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
        "antinakrutka_enabled": bool(getattr(rule, "antinakrutka_enabled", False)),
        "antinakrutka_joins_threshold": int(getattr(rule, "antinakrutka_joins_threshold", 10) or 10),
        "antinakrutka_window_minutes": int(getattr(rule, "antinakrutka_window_minutes", 5) or 5),
        "antinakrutka_action": str(getattr(rule, "antinakrutka_action", "alert") or "alert"),
        "antinakrutka_restrict_minutes": int(getattr(rule, "antinakrutka_restrict_minutes", 30) or 30),
        "use_global_antispam_db": bool(getattr(rule, "use_global_antispam_db", False)),
        "filter_profanity_enabled": bool(getattr(rule, "filter_profanity_enabled", False)),
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
    return {
        "username": username,
        "add_to_group_url": f"https://t.me/{username}?start=addgroup",
        "reports_chat_url": f"https://t.me/{username}?start=reportschat",
    }


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
    tariff = (user.tariff or "free").lower()
    sub_until = user.subscription_until
    now = datetime.now(timezone.utc)
    is_premium = tariff in ("premium", "pro", "business") or (sub_until and sub_until > now)
    return {
        "telegram_id": user_id,
        "username": user.username,
        "first_name": user.first_name,
        "tariff": user.tariff or "free",
        "is_premium": is_premium,
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
    from app.services.telegram_bot_api import refresh_chat_title_in_db

    chats = await get_managed_chats(session, user_id)
    for c in chats:
        try:
            await refresh_chat_title_in_db(session, int(c.id))
        except Exception:
            pass
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
    from app.services.telegram_bot_api import refresh_chat_title_in_db

    try:
        await refresh_chat_title_in_db(session, int(chat_id))
        await session.refresh(chat)
    except Exception:
        pass
    if getattr(chat, "log_chat_id", None):
        try:
            await refresh_chat_title_in_db(session, int(chat.log_chat_id))
        except Exception:
            pass
    rule = await get_or_create_rule(session, int(chat_id))
    stopwords_list = await list_stopwords(session, int(chat_id))
    stopwords_count = len(stopwords_list)
    log_chat_title = None
    if getattr(chat, "log_chat_id", None):
        log_chat_row = await session.get(Chat, int(chat.log_chat_id))
        if log_chat_row and getattr(log_chat_row, "title", None):
            log_chat_title = (log_chat_row.title or "").strip() or str(chat.log_chat_id)
        else:
            log_chat_title = str(chat.log_chat_id)
    return {
        "id": chat.id,
        "title": (chat.title or "").strip() or str(chat.id),
        "log_chat_id": chat.log_chat_id,
        "log_chat_title": log_chat_title,
        "rule": _rule_to_dict(rule, stopwords_count),
        "stopwords": stopwords_list,
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
        "silence_minutes", "master_anti_spam",
        "antinakrutka_enabled", "antinakrutka_joins_threshold", "antinakrutka_window_minutes",
        "antinakrutka_action", "antinakrutka_restrict_minutes",
        "use_global_antispam_db",
        "filter_profanity_enabled",
        "log_enabled",
        "guardian_messages_enabled", "public_alerts_every_n", "public_alerts_min_interval_sec",
        "auto_reports_enabled",
    }
    for key, value in body.items():
        if key in allowed and hasattr(rule, key):
            setattr(rule, key, value)
    # Синхронизация ссылок: при "allow" выключаем и legacy filter_links
    if "filter_links_mode" in body and hasattr(rule, "filter_links"):
        mode = (body.get("filter_links_mode") or "").strip().lower()
        rule.filter_links = mode != "allow"
    if "filter_links" in body and "filter_links_mode" not in body and hasattr(rule, "filter_links_mode"):
        rule.filter_links_mode = "forbid" if rule.filter_links else "allow"
    aa = (getattr(rule, "antinakrutka_action", None) or "alert").strip().lower()
    if aa not in ("alert", "alert_restrict"):
        rule.antinakrutka_action = "alert"
    await session.commit()
    await session.refresh(rule)
    stopwords_count = await count_stopwords(session, int(chat_id))
    return {"rule": _rule_to_dict(rule, stopwords_count)}


# ---------- GET /api/chat/:id/stopwords (список уже в GET /api/chat/:id)
# ---------- POST /api/chat/:id/stopwords ----------
@router.post("/chat/{chat_id}/stopwords")
async def api_add_stopword(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Добавить стоп-слово. Body: { "word": "казино" } или { "words": ["казино", "реклама"] }."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    word = (body.get("word") or "").strip()
    words = body.get("words")
    if word:
        words = [word] if not words else list(words) + [word]
    elif not words:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need 'word' or 'words'")
    else:
        words = list(words) if isinstance(words, (list, tuple)) else [str(words)]
    added = []
    for w in words:
        if (w or "").strip():
            if await add_stopword(session, int(chat_id), w):
                added.append((w or "").strip().lower())
    return {"added": added, "stopwords": await list_stopwords(session, int(chat_id))}


# ---------- DELETE /api/chat/:id/stopwords ----------
@router.delete("/chat/{chat_id}/stopwords")
async def api_delete_stopword(
    chat_id: int,
    word: str,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Удалить стоп-слово. Query: ?word=казино"""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    if not (word or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need query param 'word'")
    await delete_stopword(session, int(chat_id), word)
    return {"stopwords": await list_stopwords(session, int(chat_id))}


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
    tariff = (user.tariff or "free").lower()
    sub_until = user.subscription_until
    now = datetime.now(timezone.utc)
    is_premium = tariff in ("premium", "pro", "business") or (sub_until and sub_until > now)
    return {
        "tariff": user.tariff or "free",
        "is_premium": is_premium,
        "chat_limit": limit,
        "chats_count": len(chats),
        "can_add_more": can_add,
        "subscription_until": _format_dt(user.subscription_until),
    }


# ---------- GET /api/global-antispam ----------
@router.get("/global-antispam")
async def api_global_antispam_list(
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Список пользователей в глобальной антиспам базе (общая для бота)."""
    from app.services.global_antispam import list_global_antispam_for_api
    items = await list_global_antispam_for_api(session, limit=500)
    return {"items": items}


# ---------- POST /api/global-antispam ----------
@router.post("/global-antispam")
async def api_global_antispam_add(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Добавить user_id в глобальную антиспам базу. Body: { "user_id": number, "reason": "optional" }."""
    from app.services.global_antispam import add_to_global_antispam, update_antispam_user_profile
    from app.services.telegram_bot_api import private_chat_profile, tg_get_chat

    uid = body.get("user_id")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id required")
    uid = int(uid)
    added = await add_to_global_antispam(session, uid, body.get("reason"))
    if added:
        info = await tg_get_chat(uid)
        disp, un = private_chat_profile(info)
        if disp or un:
            await update_antispam_user_profile(session, uid, disp, un)
    return {"added": added, "user_id": uid}


# ---------- DELETE /api/global-antispam/:target_uid ----------
@router.delete("/global-antispam/{target_uid}")
async def api_global_antispam_remove(
    target_uid: int,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Удалить target_uid из глобальной антиспам базы."""
    from app.services.global_antispam import remove_from_global_antispam
    removed = await remove_from_global_antispam(session, target_uid)
    return {"removed": removed}


# ---------- POST /api/promo/apply ----------
@router.post("/promo/apply")
async def api_promo_apply(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Активировать промокод. Body: { "code": "TRIAL3" }. Для теста Premium на 3 дня создайте промокод с days=3."""
    code = (body.get("code") or "").strip()
    success, message = await apply_promo_code(session, user_id, code)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return {"ok": True, "message": message}


# ---------- POST /api/payments/yookassa/create ----------
@router.post("/payments/yookassa/create")
async def api_yookassa_create_payment(
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Создать платёж ЮKassa. Body: { \"months\": 1|3|6|12|24 }. Ответ: { \"confirmation_url\": \"...\" }."""
    from app.services.payments_yookassa import create_yookassa_subscription_payment, yookassa_configured

    if not yookassa_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Платежи не настроены",
        )
    raw = body.get("months")
    try:
        months = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="months required")
    try:
        url = await create_yookassa_subscription_payment(session, user_id, months)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый период")
    except RuntimeError as e:
        _log.exception("YooKassa create failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "Ошибка платёжной системы",
        ) from e
    return {"confirmation_url": url}


# ---------- POST /api/webhooks/yookassa/:secret (без initData) ----------
@router.post("/webhooks/yookassa/{secret_token}")
async def api_yookassa_webhook(
    secret_token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Входящие уведомления ЮKassa. URL с секретом задаётся в личном кабинете."""
    expected = os.getenv("YOOKASSA_WEBHOOK_SECRET")
    if not expected or not secrets.compare_digest(secret_token, expected):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")
    from app.services.payments_yookassa import process_yookassa_webhook

    try:
        await process_yookassa_webhook(session, body)
    except Exception:
        _log.exception("YooKassa webhook handler failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="retry")
    return {"ok": True}


# ---------- /api/profanity (зарезервировано; список скрыт, управление — не через Mini App) ----------
@router.get("/profanity")
async def api_profanity_list(_user_id: int = Depends(require_init_data)):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="profanity_list_not_available",
    )


@router.post("/profanity")
async def api_profanity_add(_user_id: int = Depends(require_init_data)):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="profanity_list_not_available",
    )


@router.delete("/profanity/{word:path}")
async def api_profanity_remove(_word: str, _user_id: int = Depends(require_init_data)):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="profanity_list_not_available",
    )


# ---------- POST /api/chat/:id/copy-settings ----------
@router.post("/chat/{chat_id}/copy-settings")
async def api_chat_copy_settings(
    chat_id: int,
    body: dict,
    user_id: int = Depends(require_init_data),
    session: AsyncSession = Depends(get_db),
):
    """Перенести настройки из текущего чата в другой. Body: { "target_chat_id": number }."""
    ok = await user_can_access_chat(session, user_id, int(chat_id))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    target_id = body.get("target_chat_id")
    if target_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_chat_id required")
    target_id = int(target_id)
    ok_target = await user_can_access_chat(session, user_id, target_id)
    if not ok_target:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Target chat not found or access denied")
    if int(chat_id) == target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source and target must differ")
    try:
        rule = await copy_rule_to_chat(session, int(chat_id), target_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"target_chat_id": target_id, "ok": True}
