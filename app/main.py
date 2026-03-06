# app/main.py
from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from app.db.session import engine
from app.db.models import Base

from app.handlers.health import router as health_router
from app.handlers.start import router as start_router
from app.handlers.onboarding import router as onboarding_router
from app.handlers.panel_dm import router as panel_router
from app.handlers.log_setup import router as log_setup_router
from app.handlers.log_actions import router as log_actions_router
from app.handlers.moderation import router as moderation_router
from app.handlers.whitelist import router as whitelist_router
from app.handlers.stopwords import router as stopwords_router

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main() -> None:
    dp.include_router(health_router)
    dp.include_router(moderation_router)
    dp.include_router(start_router)
    dp.include_router(onboarding_router)
    dp.include_router(panel_router)
    dp.include_router(log_setup_router)
    dp.include_router(log_actions_router)
    dp.include_router(whitelist_router)
    dp.include_router(stopwords_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await on_startup()

    print("😈 AntiSpam Guardian запущен / BUILD 777")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
