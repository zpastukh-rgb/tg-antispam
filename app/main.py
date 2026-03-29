# app/main.py
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)
from dotenv import load_dotenv
from sqlalchemy import text

from app.db.ensure_defaults import ensure_default_trial_promo
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


# Критичные колонки rules для миграции 008 (имя, тип, default)
_RULES_COLUMNS_008 = (
    ("antinakrutka_enabled", "BOOLEAN", "FALSE"),
    ("antinakrutka_joins_threshold", "INTEGER", "10"),
    ("antinakrutka_window_minutes", "INTEGER", "5"),
    ("antinakrutka_action", "VARCHAR(32)", "'alert'"),
    ("antinakrutka_restrict_minutes", "INTEGER", "30"),
    ("use_global_antispam_db", "BOOLEAN", "FALSE"),
    ("filter_profanity_enabled", "BOOLEAN", "FALSE"),
)


async def _run_ensure_rules_migration() -> None:
    """При старте бота добавить колонки в rules через information_schema (работает везде)."""
    import logging
    log = logging.getLogger(__name__)
    ok = 0
    for col_name, col_type, default in _RULES_COLUMNS_008:
        # В EXECUTE кавычки в default удваиваем для plpgsql
        default_esc = default.replace("'", "''")
        sql_str = f"""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'rules' AND column_name = '{col_name}'
              ) THEN
                EXECUTE 'ALTER TABLE rules ADD COLUMN {col_name} {col_type} DEFAULT {default_esc}';
              END IF;
            END $$;
        """
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql_str))
            ok += 1
        except Exception as e:
            log.warning("ensure_rules column %s failed: %s", col_name, e)
    if ok > 0:
        log.info("ensure_rules migration: %s/%s columns ensured", ok, len(_RULES_COLUMNS_008))


async def on_startup() -> None:
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL not set. Railway: Add Reference → Postgres → DATABASE_URL, "
            "или задай PGHOST, PGUSER, PGPASSWORD, PGDATABASE (и при необходимости PGPORT)."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_ensure_rules_migration()
    await ensure_default_trial_promo(engine)
    # Меню команд:
    # - ЛС: основной список (default).
    # - Обычные участники групп: пустое меню (не видят /addantispam и прочее).
    # - Админы/создатели в группах: тот же список + /addantispam (scope all_chat_administrators).
    GROUP_ADMIN_COMMANDS = [
        *BOT_COMMANDS,
        BotCommand(command="addantispam", description="Добавить автора ответа в антиспам базу"),
    ]
    try:
        await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
        await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(GROUP_ADMIN_COMMANDS, scope=BotCommandScopeAllChatAdministrators())
    except Exception:
        pass
    # Описание в профиле бота (как в BotFather /setdescription и краткое для поиска)
    try:
        from app.texts.bot_intro import BOT_TELEGRAM_DESCRIPTION, BOT_TELEGRAM_SHORT_DESCRIPTION

        await bot.set_my_description(BOT_TELEGRAM_DESCRIPTION)
        await bot.set_my_short_description(BOT_TELEGRAM_SHORT_DESCRIPTION)
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
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
