# app/api/main.py
"""FastAPI приложение для Mini App (REST API)."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="AntiSpam Guardian API",
    description="REST API для Mini App панели управления",
    version="0.1.0",
)

# Mini App может открываться с другого origin (например статика на Vercel, API на своём домене)
# В продакшене указать конкретные origins
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
async def health():
    """Проверка доступности API."""
    return {"status": "ok"}
