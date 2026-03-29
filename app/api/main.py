# app/api/main.py
"""FastAPI приложение для Mini App (REST API)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.ensure_defaults import ensure_default_trial_promo
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        await ensure_default_trial_promo(engine)
    yield


app = FastAPI(
    title="AntiSpam Guardian API",
    description="REST API для Mini App панели управления",
    version="0.1.0",
    lifespan=lifespan,
)

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

app.include_router(router)


@app.get("/health")
@app.get("/api/health")
async def health():
    """Проверка доступности API (и /health для прокси/Railway)."""
    return {"status": "ok"}
