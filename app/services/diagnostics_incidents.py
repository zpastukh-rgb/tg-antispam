"""Точечные записи в admin_incident_feed (не один глобальный перехватчик)."""

from __future__ import annotations

import time
from typing import Any

from aiogram.types import Message

_THROTTLE: dict[tuple[Any, ...], float] = {}
_THROTTLE_PRUNE_EVERY = 400


def _throttle(key: tuple[Any, ...], ttl_sec: float) -> bool:
    now = time.monotonic()
    at = _THROTTLE.get(key, 0.0)
    if now - at < ttl_sec:
        return False
    _THROTTLE[key] = now
    if len(_THROTTLE) > _THROTTLE_PRUNE_EVERY:
        cutoff = now - ttl_sec * 3
        for k in list(_THROTTLE):
            if _THROTTLE[k] < cutoff:
                del _THROTTLE[k]
    return True


async def record_bot_delete_message_failed(
    *,
    context: str,
    message: Message,
    exc: BaseException,
    ttl_sec: float = 120.0,
) -> None:
    """Неуспешное deleteMessage через aiogram (модерация, сервисные join/left)."""
    chat_id = int(message.chat.id)
    mid = int(message.message_id)
    uid = int(message.from_user.id) if message.from_user else None
    ctx = (context or "unknown").strip()[:48] or "unknown"
    if not _throttle(("bot_del", chat_id, ctx, type(exc).__name__), ttl_sec):
        return
    from app.services.admin_diagnostics_service import record_user_incident

    ids = [uid] if uid else []
    summary = (
        f"Удаление сообщения не удалось ({ctx}, чат {chat_id}). {type(exc).__name__}: "
        "проверьте права бота (удаление сообщений)."
    )[:4000]
    detail = f"context={ctx} chat_id={chat_id} msg_id={mid} err={exc!s}"[:800]
    cat = "moderation" if ctx in ("moderation", "join_service", "left_service") else "telegram_api"
    await record_user_incident(
        kind=f"tg_del_{ctx}"[:32],
        category=cat,
        summary_ru=summary,
        telegram_ids=ids,
        detail_snippet=detail,
    )


async def record_moderation_restrict_failed(
    *,
    message: Message,
    action: str,
    exc: BaseException,
    target_telegram_id: int | None = None,
    ttl_sec: float = 180.0,
) -> None:
    """Неуспешный mute / ban (в т.ч. ban_chat_sender_chat — без from_user)."""
    chat_id = int(message.chat.id)
    act = (action or "restrict").strip()[:32]
    if not _throttle(("mod_rest", chat_id, act, type(exc).__name__), ttl_sec):
        return
    from app.services.admin_diagnostics_service import record_user_incident

    uid = target_telegram_id
    if uid is None and message.from_user:
        uid = int(message.from_user.id)
    ids = [int(uid)] if uid else []
    summary = (
        f"Модерация: действие «{act}» не выполнено (чат {chat_id}). {type(exc).__name__}: "
        "проверьте права бота (ограничение участников)."
    )[:4000]
    detail = f"action={act} chat_id={chat_id} err={exc!s}"[:800]
    await record_user_incident(
        kind=f"mod_{act}"[:32],
        category="moderation",
        summary_ru=summary,
        telegram_ids=ids,
        detail_snippet=detail,
    )


async def record_tg_http_delete_failed(
    chat_id: int,
    message_id: int,
    description: str,
    *,
    ttl_sec: float = 90.0,
) -> None:
    """Неуспешный deleteMessage через HTTP Bot API (Mini App / сервисный код)."""
    desc = (description or "").strip()[:400]
    if not _throttle(("tg_http_del", int(chat_id), desc[:120]), ttl_sec):
        return
    from app.services.admin_diagnostics_service import record_user_incident

    summary = (
        f"HTTP Bot API: deleteMessage неуспех (чат {chat_id}). "
        "Проверьте ответ Telegram и права бота."
    )[:4000]
    detail = f"chat_id={chat_id} message_id={message_id} desc={desc}"[:800]
    await record_user_incident(
        kind="tg_http_del",
        category="telegram_api",
        summary_ru=summary,
        telegram_ids=[],
        detail_snippet=detail,
    )


async def record_panel_dm_delete_forbidden(
    telegram_user_id: int,
    message_id: int,
    exc: BaseException,
    *,
    ttl_sec: float = 600.0,
) -> None:
    """ЛС панели: не удалось удалить служебное сообщение (нет прав / блокировка)."""
    tuid = int(telegram_user_id)
    if not _throttle(("panel_dm_del", tuid, type(exc).__name__), ttl_sec):
        return
    from app.services.admin_diagnostics_service import record_user_incident

    await record_user_incident(
        kind="panel_dm_del",
        category="telegram_api",
        summary_ru=f"Панель: не удалось удалить сообщение в ЛС пользователю {tuid} (deleteMessage).",
        telegram_ids=[tuid],
        detail_snippet=f"message_id={message_id} {exc!s}"[:800],
    )


async def record_user_dm_delete_failed(
    telegram_user_id: int,
    message_id: int,
    detail: str,
    *,
    ttl_sec: float = 300.0,
) -> None:
    """Не удалось удалить сообщение в личке пользователя (deleteMessage)."""
    tuid = int(telegram_user_id)
    if not _throttle(("dm_del", tuid), ttl_sec):
        return
    from app.services.admin_diagnostics_service import record_user_incident

    d = (detail or "").strip()[:500]
    await record_user_incident(
        kind="dm_del",
        category="telegram_api",
        summary_ru=f"Не удалось удалить сообщение в ЛС пользователю {tuid} (deleteMessage).",
        telegram_ids=[tuid],
        detail_snippet=f"message_id={message_id} {d}"[:800],
    )


async def record_join_captcha_expire_delete_failed(
    chat_id: int,
    user_id: int,
    message_chat_id: int,
    message_id: int,
    exc: BaseException,
    *,
    ttl_sec: float = 300.0,
) -> None:
    """Истечение капчи: не сняли сообщение с кнопками (часто нет прав на удаление)."""
    cid = int(chat_id)
    uid = int(user_id)
    if not _throttle(("jc_exp_del", cid, uid, type(exc).__name__), ttl_sec):
        return
    from app.services.admin_diagnostics_service import record_user_incident

    summary = (
        f"Капча входа: не удалось удалить сообщение после таймаута (чат {cid}). "
        f"{type(exc).__name__}: проверьте права бота."
    )[:4000]
    detail = f"chat_id={cid} user_id={uid} msg_chat={message_chat_id} msg_id={message_id} err={exc!s}"[:800]
    await record_user_incident(
        kind="join_captcha_del",
        category="moderation",
        summary_ru=summary,
        telegram_ids=[uid],
        detail_snippet=detail,
    )
