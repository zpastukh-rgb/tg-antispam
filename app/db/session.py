import os
import re
from urllib.parse import quote_plus

from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Railway: DATABASE_URL из Reference или собираем из PG* (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_PRIVATE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("POSTGRES_PRIVATE_URL")
)
# Неподставленная ссылка или шаблон — не используем
if DATABASE_URL and ("${{" in DATABASE_URL or "}}" in DATABASE_URL):
    DATABASE_URL = None
if not DATABASE_URL:
    pg_host = os.getenv("PGHOST")
    pg_port = os.getenv("PGPORT", "5432")
    pg_user = os.getenv("PGUSER")
    pg_pass = os.getenv("PGPASSWORD", "")
    pg_db = os.getenv("PGDATABASE", "railway")
    if pg_host and pg_user:
        safe_pass = quote_plus(pg_pass) if pg_pass else ""
        DATABASE_URL = f"postgresql+asyncpg://{pg_user}:{safe_pass}@{pg_host}:{pg_port}/{pg_db}"
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL not set. Railway: Add Reference → Postgres → DATABASE_URL, "
        "или задай PGHOST, PGUSER, PGPASSWORD, PGDATABASE (и при необходимости PGPORT)."
    )

# Схема postgresql → postgresql+asyncpg; порт не должен быть буквально "PORT"
if DATABASE_URL.startswith("postgresql://") and "postgresql+asyncpg" not in DATABASE_URL:
    DATABASE_URL = "postgresql+asyncpg://" + DATABASE_URL.split("://", 1)[1]
if re.search(r":PORT(\D|$)", DATABASE_URL):
    DATABASE_URL = re.sub(r":PORT(\D|$)", r":5432\1", DATABASE_URL)

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_session() -> AsyncSession:
    return AsyncSessionLocal()