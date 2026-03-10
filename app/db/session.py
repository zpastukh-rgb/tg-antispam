import os
import re
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set. Put it in .env.docker (for Docker) or .env (for local).")

# Railway: схема postgresql → postgresql+asyncpg для async; порт не должен быть буквально "PORT"
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