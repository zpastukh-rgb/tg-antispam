#!/usr/bin/env python3
"""
Проверка строк БД перед деплоем (запускай у себя на Mac / в CI).

  export DATABASE_URL='postgresql://...'        # основная (Railway Postgres)
  export PII_DATABASE_URL='postgresql+asyncpg://...'   # опционально, ВДС ПДн
  python3 scripts/check_db_urls.py

Без PII_DATABASE_URL — только основная (так проще и стабильнее).
"""

from __future__ import annotations

import asyncio
import os
import sys


def _to_asyncpg_dsn(url: str) -> str:
    """asyncpg принимает postgresql://..., не sqlalchemy postgresql+asyncpg://."""
    u = (url or "").strip()
    if u.startswith("postgresql+asyncpg://"):
        return "postgresql://" + u.split("://", 1)[1]
    return u


async def _ping(url: str, label: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_to_asyncpg_dsn(url), timeout=15)
    try:
        v = await conn.fetchval("SELECT 1")
        print(f"OK  {label}: SELECT 1 -> {v}")
    finally:
        await conn.close()


async def main() -> int:
    main_url = (os.getenv("DATABASE_URL") or os.getenv("MAIN_DATABASE_URL") or "").strip()
    if not main_url:
        print("Задай DATABASE_URL (строка из Railway → Postgres → Variables).", file=sys.stderr)
        return 2
    try:
        await _ping(main_url, "DATABASE_URL (основная)")
    except Exception as e:
        print(f"FAIL DATABASE_URL: {e}", file=sys.stderr)
        return 1

    pii = (os.getenv("PII_DATABASE_URL") or "").strip()
    if not pii:
        print("PII_DATABASE_URL не задан — ник/имя хранятся в основной БД (нормально для старта).")
        return 0
    try:
        await _ping(pii, "PII_DATABASE_URL (ПДн)")
    except Exception as e:
        print(f"FAIL PII_DATABASE_URL: {e}", file=sys.stderr)
        return 1
    print("Оба URL отвечают. Можно Deploy в Railway.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
