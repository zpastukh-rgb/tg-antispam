# app/api/main.py
"""FastAPI приложение для Mini App (REST API)."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.routes import router
from app.db.ensure_defaults import (
    ensure_chats_chat_kind_column,
    ensure_default_trial_promo,
    ensure_owner_forever_promo,
    ensure_default_profanity_roots,
    ensure_default_comeback_promo,
    ensure_referral_credits_schema,
    ensure_credit_ledger_schema,
    ensure_partner_payouts_schema,
    ensure_partner_commissions_schema,
    ensure_partner_token_rate_v2,
    ensure_subscription_token_rate_v2,
    ensure_rules_public_alerts_columns,
    ensure_rules_hard_dictionary_independent_v1,
    ensure_admin_broadcasts_schema,
)
from app.db.session import engine

log = logging.getLogger(__name__)

def _is_startup_exempt_path(path: str) -> bool:
    """Маршруты, доступные до завершения фонового прогрева БД (health, документация, корень для Railway)."""
    if path in ("/", "/health", "/api/health"):
        return True
    if path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/redoc"):
        return True
    return False


class _StartupGateMiddleware(BaseHTTPMiddleware):
    """Пока идёт фоновый прогрев БД — остальные маршруты 503, чтобы не ловить гонки."""

    async def dispatch(self, request: Request, call_next):
        if _is_startup_exempt_path(request.url.path):
            return await call_next(request)
        if not getattr(request.app.state, "api_ready", False):
            return JSONResponse({"detail": "Service is starting"}, status_code=503)
        return await call_next(request)


async def _run_api_startup_ensures(app: FastAPI) -> None:
    if engine is None:
        app.state.api_ready = True
        return
    try:
        await ensure_rules_public_alerts_columns(engine)
        await ensure_chats_chat_kind_column(engine)
        await ensure_default_trial_promo(engine)
        await ensure_default_comeback_promo(engine)
        await ensure_owner_forever_promo(engine)
        await ensure_default_profanity_roots(engine)
        await ensure_referral_credits_schema(engine)
        await ensure_credit_ledger_schema(engine)
        await ensure_partner_payouts_schema(engine)
        await ensure_partner_commissions_schema(engine)
        await ensure_partner_token_rate_v2(engine)
        await ensure_subscription_token_rate_v2(engine)
        await ensure_rules_hard_dictionary_independent_v1(engine)
        await ensure_admin_broadcasts_schema(engine)
    except Exception:
        log.exception("API startup ensures failed")
    else:
        # Автопостинг раньше крутился только в процессе бота (app.main). На Railway API и бот часто
        # раздельные сервисы — без тиков здесь рассылка никогда не стартовала. Нужен BOT_TOKEN для Telegram.
        if (os.getenv("BOT_TOKEN") or "").strip():
            from app.services.autopost_loop import autopost_loop

            asyncio.create_task(autopost_loop(interval_sec=30.0))
            log.info("autopost_loop started from API worker (BOT_TOKEN set; duplicate bot worker uses PG advisory lock)")
        else:
            log.warning(
                "autopost_loop not started on API: BOT_TOKEN unset. Add BOT_TOKEN to this service or rely on bot process (python -m app.main)."
            )
    finally:
        app.state.api_ready = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.api_ready = False
    asyncio.create_task(_run_api_startup_ensures(app))
    yield


app = FastAPI(
    title="AntiSpam Guard API",
    description="REST API для Mini App панели управления",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(_StartupGateMiddleware)

# Mini App может открываться с другого origin. Нельзя одновременно allow_origins=["*"] и
# allow_credentials=True — Starlette падает при старте (uvicorn сразу выходит → 502 у прокси).
# Авторизация через заголовок X-Telegram-Init-Data, не через cookie — credentials не нужны.
_raw_cors = os.getenv("CORS_ORIGINS", "*").split(",")
_cors_origins = [o.strip() for o in _raw_cors if o.strip()]
if not _cors_origins:
    _cors_origins = ["*"]
_cors_credentials = False if _cors_origins == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Корень: часть платформ шлёт GET / как health — отвечаем сразу, без ожидания прогрева."""
    return {"status": "ok", "service": "antispam-guardian-api"}


@app.get("/health")
@app.get("/api/health")
async def health():
    """Проверка доступности API (и /health для прокси/Railway)."""
    return {"status": "ok"}


app.include_router(router)
