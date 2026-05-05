"""Опциональная БД персональных данных (например PostgreSQL на ВДС в РФ).

Задайте PII_DATABASE_URL (postgresql+asyncpg://...). Если не задано — всё как раньше
(username/first_name только в основной БД).
"""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

PII_DATABASE_URL = (
    os.getenv("PII_DATABASE_URL")
    or os.getenv("RU_DATABASE_URL")
    or os.getenv("PERSONAL_DATA_DATABASE_URL")
    or ""
).strip()

if PII_DATABASE_URL and ("${{" in PII_DATABASE_URL or "}}" in PII_DATABASE_URL):
    PII_DATABASE_URL = ""

if not PII_DATABASE_URL:
    pg_host = os.getenv("PII_PGHOST") or os.getenv("RU_PGHOST")
    pg_port = os.getenv("PII_PGPORT") or os.getenv("RU_PGPORT") or "5432"
    pg_user = os.getenv("PII_PGUSER") or os.getenv("RU_PGUSER")
    pg_pass = os.getenv("PII_PGPASSWORD") or os.getenv("RU_PGPASSWORD") or ""
    pg_db = os.getenv("PII_PGDATABASE") or os.getenv("RU_PGDATABASE") or "guardian_pii"
    if pg_host and pg_user:
        safe_pass = quote_plus(pg_pass) if pg_pass else ""
        PII_DATABASE_URL = f"postgresql+asyncpg://{pg_user}:{safe_pass}@{pg_host}:{pg_port}/{pg_db}"

if PII_DATABASE_URL:
    if PII_DATABASE_URL.startswith("postgresql://") and "postgresql+asyncpg" not in PII_DATABASE_URL:
        PII_DATABASE_URL = "postgresql+asyncpg://" + PII_DATABASE_URL.split("://", 1)[1]
    if re.search(r":PORT(\D|$)", PII_DATABASE_URL):
        PII_DATABASE_URL = re.sub(r":PORT(\D|$)", r":5432\1", PII_DATABASE_URL)

if PII_DATABASE_URL:
    # Railway → ВДС: NAT/фаервол часто рвёт долгие idle-соединения; без pre_ping/recycle — «closed in the middle of operation».
    pii_engine = create_async_engine(
        PII_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=180,
        pool_timeout=30,
        connect_args={
            "timeout": 25,
            "command_timeout": 45,
        },
    )
    PiiAsyncSessionLocal = sessionmaker(
        bind=pii_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
else:
    pii_engine = None
    PiiAsyncSessionLocal = None


def pii_storage_enabled() -> bool:
    return PiiAsyncSessionLocal is not None


@asynccontextmanager
async def get_pii_session():
    if PiiAsyncSessionLocal is None:
        raise RuntimeError(
            "PII_DATABASE_URL не задан. Для хранения ПДн на ВДС добавьте переменную "
            "(postgresql+asyncpg://user:pass@host:5432/db) в Railway и в процесс бота."
        )
    async with PiiAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def open_pii_session():
    """Сессия без автокоммита — вызывающий делает commit (как основной get_session)."""
    if PiiAsyncSessionLocal is None:
        raise RuntimeError("PII_DATABASE_URL не задан")
    return PiiAsyncSessionLocal()
