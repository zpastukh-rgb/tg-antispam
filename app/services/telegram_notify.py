# app/services/telegram_notify.py
"""Исходящие сообщения бота через HTTP API (для процессов без polling, например webhook API)."""

from __future__ import annotations

import logging
import os

import aiohttp

log = logging.getLogger(__name__)


async def send_user_dm(telegram_user_id: int, text: str, *, parse_mode: str = "Markdown") -> bool:
    """
    Отправить пользователю сообщение в ЛС.
    Нужен BOT_TOKEN в окружении (тот же, что у бота). Если токена нет — тихо пропускаем.
    """
    token = os.getenv("BOT_TOKEN")
    if not token:
        log.warning("BOT_TOKEN not set: cannot send payment notification to user %s", telegram_user_id)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": telegram_user_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
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
                    return False
    except Exception:
        log.exception("Telegram sendMessage error for user %s", telegram_user_id)
        return False
    return True
