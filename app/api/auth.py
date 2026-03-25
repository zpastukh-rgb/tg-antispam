# app/api/auth.py
"""Проверка init data от Telegram Web App (Mini App)."""

from __future__ import annotations

import hmac
import hashlib
import json
import os
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, status


def _validate_init_data(init_data: str, bot_token: str) -> dict:
    """
    Проверяет подпись init_data и возвращает распарсенные данные.
    По документации: secret_key = HMAC_SHA256("WebAppData", bot_token);
    hash = HMAC_SHA256(secret_key, data_check_string).hex()
    """
    if not init_data or not bot_token:
        return None
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    # data_check_string: пары key=value без hash, отсортированные по ключу, через \n
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()
    computed = hmac.new(
        secret_key,
        data_check.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    return parsed


def get_telegram_user_id(init_data: str) -> int | None:
    """Из проверенных init_data извлекает user.id (telegram_id)."""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        return None
    data = _validate_init_data(init_data, bot_token)
    if not data:
        return None
    user_json = data.get("user")
    if not user_json:
        return None
    try:
        user = json.loads(user_json)
        return int(user.get("id"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


async def require_init_data(
    x_telegram_init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
) -> int:
    """FastAPI dependency: требует валидный init data и возвращает telegram user_id."""
    if not x_telegram_init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Telegram-Init-Data required",
        )
    user_id = get_telegram_user_id(x_telegram_init_data)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid init data",
        )
    return user_id
