# app/api/debug_webapp_client_log.py
"""Логи Mini App в stdout API (Railway Deploy Logs).

Два способа (любой достаточно):
1) Заголовок `X-Guard-Webapp-Debug-Token` = переменная окружения `GUARD_WEBAPP_DEBUG_LOG_TOKEN` (≥8 символов).
2) Или только подписанный `X-Telegram-Init-Data` (как у остальных запросов Mini App) — тогда токен не нужен.

Клиент шлёт POST из production при цепочке filter-chain (см. webapp/src/utils/guardDebugLog.js).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.responses import Response

from app.api.auth import get_telegram_user_id

router = APIRouter(prefix="/api/debug", tags=["debug"])
_log = logging.getLogger("guard.webapp_client")

_MAX_BODY = 12_288


def _expected_token() -> str:
    return str(os.getenv("GUARD_WEBAPP_DEBUG_LOG_TOKEN", "") or "").strip()


def _resolve_auth(
    x_guard_webapp_debug_token: str | None,
    x_telegram_init_data: str | None,
) -> tuple[str, int | None]:
    """Возвращает (режим, telegram_user_id или None для token-режима)."""
    expected = _expected_token()
    got_tok = str(x_guard_webapp_debug_token or "").strip()
    init_raw = str(x_telegram_init_data or "").strip()

    if len(expected) >= 8:
        if got_tok:
            if got_tok == expected:
                return "token", None
            raise HTTPException(status_code=404, detail="Not Found")
        tid = get_telegram_user_id(init_raw)
        if tid is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return "init", int(tid)

    tid = get_telegram_user_id(init_raw)
    if tid is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return "init", int(tid)


@router.post("/webapp-client-log")
async def webapp_client_log(
    request: Request,
    x_guard_webapp_debug_token: str | None = Header(default=None, alias="X-Guard-Webapp-Debug-Token"),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> Response:
    mode, tg_user = _resolve_auth(x_guard_webapp_debug_token, x_telegram_init_data)

    raw = await request.body()
    if len(raw) > _MAX_BODY:
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        payload: Any = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {"raw": raw.decode("utf-8", errors="replace")[:2000]}

    if not isinstance(payload, dict):
        payload = {"value": payload}

    out = dict(payload)
    out["auth"] = mode
    if tg_user is not None:
        out["tg_user"] = tg_user

    try:
        line = json.dumps(out, ensure_ascii=False, default=str)[:8000]
    except Exception:
        line = str(out)[:8000]

    _log.info("[webapp-client] %s", line)
    print(f"[webapp-client] {line}", flush=True)
    return Response(status_code=204)
