# app/services/telegram_notify.py
"""Исходящие сообщения бота через HTTP API (для процессов без polling, например webhook API)."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import aiohttp
from sqlalchemy import select

from app.db.ensure_defaults import get_comeback_promo_code
from app.db.models import User
from app.db.session import get_session

log = logging.getLogger(__name__)

# Один раз за короткое окно: отключение из панели (leaveChat) + my_chat_member почти одновременно.
_DISCONNECT_NOTICE_AT: dict[tuple[int, int], float] = {}
_DISCONNECT_NOTICE_TTL_SEC = 120.0


def _purge_disconnect_notice() -> None:
    now = time.monotonic()
    dead = [k for k, t in _DISCONNECT_NOTICE_AT.items() if now - t > _DISCONNECT_NOTICE_TTL_SEC]
    for k in dead:
        _DISCONNECT_NOTICE_AT.pop(k, None)


async def send_user_dm_with_result(
    telegram_user_id: int,
    text: str,
    *,
    parse_mode: str | None = "Markdown",
    reply_markup: dict | None = None,
) -> dict | None:
    """
    Отправить пользователю сообщение в ЛС.
    Нужен BOT_TOKEN в окружении (тот же, что у бота). Если токена нет — тихо пропускаем.
    """
    token = os.getenv("BOT_TOKEN")
    if not token:
        log.warning("BOT_TOKEN not set: cannot send payment notification to user %s", telegram_user_id)
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": telegram_user_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
                if not resp.ok or not isinstance(data, dict) or not data.get("ok"):
                    log.warning(
                        "Telegram sendMessage failed for %s: %s %s",
                        telegram_user_id,
                        resp.status,
                        data,
                    )
                    return None
    except Exception:
        log.exception("Telegram sendMessage error for user %s", telegram_user_id)
        return None
    return data


async def send_user_dm(
    telegram_user_id: int,
    text: str,
    *,
    parse_mode: str = "Markdown",
    reply_markup: dict | None = None,
) -> bool:
    data = await send_user_dm_with_result(
        telegram_user_id,
        text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
    return bool(isinstance(data, dict) and data.get("ok"))


async def send_disconnect_comeback_dm(telegram_user_id: int, chat_id: int, group_title: str) -> bool:
    """
    Единое сообщение владельцу при отключении группы / выходе бота (дедуп по user+chat).
    """
    _purge_disconnect_notice()
    key = (int(telegram_user_id), int(chat_id))
    now = time.monotonic()
    prev = _DISCONNECT_NOTICE_AT.get(key)
    if prev is not None and now - prev < _DISCONNECT_NOTICE_TTL_SEC:
        return False

    title = (group_title or "").strip() or str(chat_id)
    title_esc = title.replace("*", "\\*")

    owner_is_premium = False
    comeback_already_offered = False
    try:
        async with await get_session() as session:
            user = (
                await session.execute(
                    select(User).where(User.telegram_id == int(telegram_user_id)).limit(1)
                )
            ).scalar_one_or_none()
            if user:
                comeback_already_offered = bool(getattr(user, "comeback_offer_sent_at", None))
                now = datetime.now(timezone.utc)
                sub_until = getattr(user, "subscription_until", None)
                if sub_until:
                    if sub_until.tzinfo is None:
                        sub_until = sub_until.replace(tzinfo=timezone.utc)
                    owner_is_premium = sub_until > now
                else:
                    t = str(getattr(user, "tariff", "free") or "free").lower()
                    owner_is_premium = t in ("premium", "pro", "business")
    except Exception:
        owner_is_premium = False

    if owner_is_premium and not comeback_already_offered:
        code = get_comeback_promo_code()
        text = (
            "😈 *Гуард на связи*\n\n"
            f"Бот удалён из группы *{title_esc}*.\n"
            "Защита приостановлена.\n\n"
            f"🎁 Не уходи: держи бонус на *3 дня Premium* — промокод `{code}`.\n\n"
            "Если что-то не устроило — напиши в *Службу Заботы* [@Help_guard](https://t.me/Help_guard).\n"
            "Мы быстро доработаем и вернём тебе комфорт в чате."
        )
    else:
        text = (
            "😈 *Гуард на связи*\n\n"
            f"Бот удалён из группы *{title_esc}*.\n"
            "Защита приостановлена.\n\n"
            "Если что-то не устроило — напиши в *Службу Заботы* [@Help_guard](https://t.me/Help_guard).\n"
            "Мы всё учтём и поможем настроить Guard под ваш чат."
        )
    ok = await send_user_dm(int(telegram_user_id), text, parse_mode="Markdown")
    if ok:
        if owner_is_premium and not comeback_already_offered:
            # Фиксируем только один бонусный оффер на пользователя.
            try:
                async with await get_session() as session:
                    user = (
                        await session.execute(
                            select(User).where(User.telegram_id == int(telegram_user_id)).limit(1)
                        )
                    ).scalar_one_or_none()
                    if user and not getattr(user, "comeback_offer_sent_at", None):
                        user.comeback_offer_sent_at = datetime.now(timezone.utc)
                        await session.commit()
            except Exception:
                pass
        _DISCONNECT_NOTICE_AT[key] = time.monotonic()
    return ok


async def delete_user_dm_message(telegram_user_id: int, message_id: int) -> bool:
    from app.services.diagnostics_incidents import record_user_dm_delete_failed

    token = os.getenv("BOT_TOKEN")
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/deleteMessage"
    payload = {"chat_id": telegram_user_id, "message_id": int(message_id)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
                ok = bool(resp.ok and isinstance(data, dict) and data.get("ok"))
                if not ok:
                    desc = ""
                    if isinstance(data, dict):
                        desc = str(data.get("description") or data)
                    else:
                        desc = f"http={resp.status} body={data!s}"
                    await record_user_dm_delete_failed(
                        int(telegram_user_id), int(message_id), desc or "deleteMessage not ok"
                    )
                return ok
    except Exception as e:
        log.exception("Telegram deleteMessage error for user %s", telegram_user_id)
        await record_user_dm_delete_failed(int(telegram_user_id), int(message_id), str(e))
        return False
