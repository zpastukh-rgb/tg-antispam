# app/main.py
from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)
from dotenv import load_dotenv

from app.db.session import engine
from app.db.models import Base

from app.handlers.health import router as health_router
from app.handlers.start import router as start_router
from app.handlers.onboarding import router as onboarding_router
from app.handlers.panel_dm import router as panel_router
from app.handlers.log_setup import router as log_setup_router
from app.handlers.log_actions import router as log_actions_router
# Капча на паузе
# from app.handlers.first_message_captcha import router as first_message_captcha_router
from app.handlers.moderation import router as moderation_router
from app.handlers.whitelist import router as whitelist_router
from app.handlers.stopwords import router as stopwords_router

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ТЗ: Меню команд Telegram (синяя кнопка) — только основные команды
BOT_COMMANDS = [
    BotCommand(command="start", description="Начать работу с ботом"),
    BotCommand(command="group", description="Управление одной группой"),
    BotCommand(command="groups", description="Управление всеми группами"),
    BotCommand(command="buy", description="Тариф и подписка"),
    BotCommand(command="premium", description="Guardian Premium"),
    BotCommand(command="support", description="Техподдержка"),
]


async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Меню команд: в ЛС — полный список; в группах — только у админов, у обычных пользователей пусто
    try:
        await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
        await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeAllChatAdministrators())
    except Exception:
        pass


async def main() -> None:
    # log_setup ДО moderation: иначе chat_member в moderation перехватывает добавление бота в группу,
    # и my_chat_member в log_setup не срабатывает — группа не подключается, приветствие не уходит
    dp.include_router(health_router)
    dp.include_router(start_router)
    dp.include_router(onboarding_router)
    # dp.include_router(first_message_captcha_router)  # капча на паузе
    dp.include_router(log_setup_router)
    dp.include_router(moderation_router)
    dp.include_router(panel_router)
    dp.include_router(log_actions_router)
    dp.include_router(whitelist_router)
    dp.include_router(stopwords_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await on_startup()

    # ТЗ Напоминания + Автоотчёты: фоновый цикл (напоминания 12ч/24ч/3д, Guardian раз в 3 дня, дайджест раз в сутки)
    from app.services.reminders import reminder_loop
    asyncio.create_task(reminder_loop(bot, interval_sec=900))

    print("😈 AntiSpam Guardian запущен / BUILD 777")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
