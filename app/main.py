# app/main.py
from __future__ import annotations

import asyncio
import logging
import os
import socket

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    ErrorEvent,
    BotCommandScopeDefault,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
    MenuButtonWebApp,
    WebAppInfo,
)
from dotenv import load_dotenv
from aiohttp import web
from sqlalchemy import text

from app.db.ensure_defaults import (
    ensure_chats_chat_kind_column,
    ensure_chats_linked_discussion_chat_id_column,
    ensure_chats_linked_channel_chat_id_column,
    ensure_default_trial_promo,
    ensure_default_admin_promo_codes,
    ensure_default_token_aurum_promo_codes,
    ensure_disable_legacy_simple_promo_codes,
    ensure_default_comeback_promo,
    ensure_owner_forever_promo,
    ensure_default_profanity_roots,
    ensure_referral_credits_schema,
    ensure_promo_codes_grant_schema,
    ensure_credit_ledger_schema,
    ensure_subscription_credits_merged_to_aurum_v1,
    ensure_rules_public_alerts_columns,
    ensure_rules_guardian_periodic_columns,
    ensure_users_comeback_offer_column,
    ensure_rules_filter_links_scope_column,
    ensure_rules_filter_links_mode_width,
    ensure_link_blacklist_schema,
    ensure_global_bad_url_patterns_schema,
    ensure_user_global_bad_url_patterns_schema,
    ensure_rules_use_global_bad_urls_column,
    ensure_rules_channel_posts_filter_columns,
    ensure_rules_welcome_columns,
    ensure_whitelist_sender_chats_schema,
    ensure_rules_hard_dictionary_independent_v1,
    ensure_admin_insights_schema,
    ensure_chat_manager_invites_schema,
    ensure_spam_spike_notify_schema,
    ensure_payments_receipt_url_schema,
    ensure_users_subscription_source_schema,
    ensure_users_subscription_activated_at_schema,
    ensure_users_payment_binding_schema,
    ensure_users_group_channel_limits_schema,
    ensure_chat_spike_alerts_schema,
    ensure_rules_spam_spike_columns,
    ensure_admin_dispatch_bucket_unique,
    ensure_app_settings_schema,
    ensure_join_captcha_schema,
    ensure_chat_reputation_schema,
    ensure_rules_post_rules_columns,
    ensure_channel_rule_drafts_schema,
    ensure_moderation_logs_detail_column,
    ensure_user_post_rules_drafts_json_column,
    ensure_users_delegate_broadcast_payer_column,
    ensure_admin_incident_feed_schema,
)
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
from app.handlers.join_captcha import router as join_captcha_router

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()


def _telegram_user_id_from_update(update) -> int:
    """Для журнала сбоев: кто инициировал апдейт (если можно вытащить)."""
    try:
        if getattr(update, "message", None) and update.message and update.message.from_user:
            return int(update.message.from_user.id)
        if getattr(update, "callback_query", None) and update.callback_query and update.callback_query.from_user:
            return int(update.callback_query.from_user.id)
        if getattr(update, "edited_message", None) and update.edited_message and update.edited_message.from_user:
            return int(update.edited_message.from_user.id)
        if getattr(update, "inline_query", None) and update.inline_query and update.inline_query.from_user:
            return int(update.inline_query.from_user.id)
        if getattr(update, "chosen_inline_result", None) and update.chosen_inline_result and update.chosen_inline_result.from_user:
            return int(update.chosen_inline_result.from_user.id)
        if getattr(update, "my_chat_member", None) and update.my_chat_member and update.my_chat_member.from_user:
            return int(update.my_chat_member.from_user.id)
        if getattr(update, "chat_member", None) and update.chat_member and update.chat_member.from_user:
            return int(update.chat_member.from_user.id)
    except Exception:
        return 0
    return 0


@dp.errors()
async def _guardian_bot_error_journal(event: ErrorEvent) -> None:
    """Пишет сбои обработчиков бота в admin_incident_feed (как категория «Бот»)."""
    try:
        from app.services.admin_diagnostics_service import record_user_incident

        exc = event.exception
        update = event.update
        tid = _telegram_user_id_from_update(update)
        await record_user_incident(
            kind="bot_handler",
            category="bot",
            summary_ru=(
                f"Ошибка в боте при обработке апдейта ({type(update).__name__}): "
                f"{type(exc).__name__}: {str(exc)[:220]}. Полный стек — в логах сервиса бота на Railway."
            ),
            telegram_ids=[tid] if tid > 0 else [],
            detail_snippet=str(exc)[:800],
            method="BOT",
            path=str(type(update).__name__)[:200],
            status_code=500,
        )
    except Exception:
        logging.getLogger(__name__).exception("guardian_bot_error_journal failed")


# ТЗ: Меню команд Telegram (синяя кнопка) — только основные команды
BOT_COMMANDS = [
    BotCommand(command="start", description="Начать работу с ботом"),
    BotCommand(command="panel", description="Открыть панель Guard"),
    BotCommand(command="guard_help", description="Инструкция Guard"),
    BotCommand(command="guard_ref", description="Реферальная программа"),
    BotCommand(command="guard_lang", description="Смена языка"),
    BotCommand(command="guard_tip", description="Поддержать проект"),
    BotCommand(command="karma", description="Моя карма в группе"),
    BotCommand(command="topkarma", description="Топ кармы группы"),
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
    ("filter_jobs_enabled", "BOOLEAN", "FALSE"),
    ("filter_casino_enabled", "BOOLEAN", "FALSE"),
    ("delete_left_messages", "BOOLEAN", "TRUE"),
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


async def _railway_health_server() -> None:
    """Railway проверяет $PORT; чистый polling без HTTP — деплой/restart долго висят на «healthy»."""
    raw = os.getenv("PORT", "").strip()
    if not raw:
        return
    try:
        port = int(raw)
    except ValueError:
        return
    app = web.Application()

    async def ping(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/", ping)
    app.router.add_get("/health", ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


# Пустая строка = слой "для всех языков без отдельного описания" (см. Telegram setMyDescription).
# ru/uk/en/be: иначе русскоязычный Telegram часто продолжает показывать старый текст из BotFather.
_BOT_PROFILE_LANGUAGE_CODES = ("", "ru", "uk", "en", "be")


async def _sync_bot_profile(b: Bot) -> None:
    """Синхронизация имени и описаний (экран «пустой чат» до /start)."""
    log = logging.getLogger(__name__)
    from app.texts.bot_intro import (
        BOT_TELEGRAM_DESCRIPTION,
        BOT_TELEGRAM_SHORT_DESCRIPTION,
    )

    # setMyName имеет жёсткий rate-limit у Telegram (может блокироваться на сутки).
    # Имя бота меняется редко, поэтому не дёргаем этот метод на каждом старте.
    # При необходимости имя можно изменить вручную в BotFather (Edit Name).

    for lang in _BOT_PROFILE_LANGUAGE_CODES:
        lc = lang if lang else ""
        try:
            await b.set_my_description(BOT_TELEGRAM_DESCRIPTION, language_code=lc)
        except Exception as e:
            log.warning("set_my_description language_code=%r: %s", lc, e)
        try:
            await b.set_my_short_description(BOT_TELEGRAM_SHORT_DESCRIPTION, language_code=lc)
        except Exception as e:
            log.warning("set_my_short_description language_code=%r: %s", lc, e)

    try:
        check = await b.get_my_description(language_code="ru")
        preview = (check.description or "")[:160].replace("\n", " ")
        log.info("bot profile ok: getMyDescription(ru) starts with: %s…", preview)
    except Exception as e:
        log.warning("get_my_description(ru): %s", e)


async def on_startup() -> None:
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL not set. Railway: Add Reference → Postgres → DATABASE_URL, "
            "или задай PGHOST, PGUSER, PGPASSWORD, PGDATABASE (и при необходимости PGPORT)."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_ensure_rules_migration()
    await ensure_rules_public_alerts_columns(engine)
    await ensure_rules_guardian_periodic_columns(engine)
    await ensure_users_comeback_offer_column(engine)
    await ensure_rules_filter_links_scope_column(engine)
    await ensure_rules_filter_links_mode_width(engine)
    await ensure_link_blacklist_schema(engine)
    await ensure_global_bad_url_patterns_schema(engine)
    await ensure_user_global_bad_url_patterns_schema(engine)
    await ensure_rules_use_global_bad_urls_column(engine)
    await ensure_rules_channel_posts_filter_columns(engine)
    await ensure_rules_welcome_columns(engine)
    await ensure_whitelist_sender_chats_schema(engine)
    await ensure_chats_chat_kind_column(engine)
    await ensure_chats_linked_discussion_chat_id_column(engine)
    await ensure_chats_linked_channel_chat_id_column(engine)
    await ensure_default_trial_promo(engine)
    await ensure_default_admin_promo_codes(engine)
    await ensure_referral_credits_schema(engine)
    await ensure_promo_codes_grant_schema(engine)
    await ensure_default_token_aurum_promo_codes(engine)
    await ensure_disable_legacy_simple_promo_codes(engine)
    await ensure_default_comeback_promo(engine)
    await ensure_owner_forever_promo(engine)
    await ensure_default_profanity_roots(engine)
    await ensure_credit_ledger_schema(engine)
    await ensure_subscription_credits_merged_to_aurum_v1(engine)
    await ensure_rules_hard_dictionary_independent_v1(engine)
    await ensure_admin_insights_schema(engine)
    await ensure_chat_manager_invites_schema(engine)
    await ensure_spam_spike_notify_schema(engine)
    await ensure_payments_receipt_url_schema(engine)
    await ensure_users_subscription_source_schema(engine)
    await ensure_users_subscription_activated_at_schema(engine)
    await ensure_users_payment_binding_schema(engine)
    await ensure_users_group_channel_limits_schema(engine)
    await ensure_chat_spike_alerts_schema(engine)
    await ensure_rules_spam_spike_columns(engine)
    await ensure_admin_dispatch_bucket_unique(engine)
    await ensure_app_settings_schema(engine)
    await ensure_join_captcha_schema(engine)
    await ensure_chat_reputation_schema(engine)
    await ensure_rules_post_rules_columns(engine)
    await ensure_channel_rule_drafts_schema(engine)
    await ensure_moderation_logs_detail_column(engine)
    await ensure_user_post_rules_drafts_json_column(engine)
    await ensure_users_delegate_broadcast_payer_column(engine)
    await ensure_admin_incident_feed_schema(engine)
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
    # Кнопка слева от поля ввода (вместо "Open"): задаём текст "Меню", если есть URL мини-приложения.
    miniapp_url = (os.getenv("MINI_APP_URL") or os.getenv("WEBAPP_URL") or "").strip()
    if miniapp_url:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Меню",
                    web_app=WebAppInfo(url=miniapp_url),
                )
            )
        except Exception:
            pass
    await _sync_bot_profile(bot)


async def _safe_delete_webhook() -> None:
    """После ручного logOut Bot API может вернуть Logged out на deleteWebhook — не валим запуск."""
    import logging

    log = logging.getLogger(__name__)
    for attempt in range(3):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            return
        except TelegramBadRequest as e:
            msg = str(e).lower()
            if "logged out" in msg:
                log.warning("delete_webhook skipped: bot is logged out (attempt %s/3)", attempt + 1)
                await asyncio.sleep(2)
                continue
            raise
    log.warning("delete_webhook: still logged out, continue startup and let polling recover")


def _is_transient_db_boot_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "temporary failure in name resolution" in msg
        or "name or service not known" in msg
        or "could not translate host name" in msg
        or isinstance(exc, socket.gaierror)
    )


async def _run_startup_with_retry() -> None:
    log = logging.getLogger(__name__)
    attempts = 6
    delay_sec = 3.0
    for i in range(1, attempts + 1):
        try:
            await on_startup()
            return
        except Exception as e:
            if i >= attempts or not _is_transient_db_boot_error(e):
                raise
            log.warning(
                "startup DB connect failed (transient DNS) attempt %s/%s: %s; retry in %.1fs",
                i,
                attempts,
                e,
                delay_sec,
            )
            await asyncio.sleep(delay_sec)


async def main() -> None:
    # log_setup ДО moderation: иначе chat_member в moderation перехватывает добавление бота в группу,
    # и my_chat_member в log_setup не срабатывает — группа не подключается, приветствие не уходит
    dp.include_router(health_router)
    dp.include_router(start_router)
    dp.include_router(onboarding_router)
    # dp.include_router(first_message_captcha_router)  # капча на паузе
    dp.include_router(log_setup_router)
    dp.include_router(join_captcha_router)
    dp.include_router(moderation_router)
    dp.include_router(panel_router)
    dp.include_router(log_actions_router)
    dp.include_router(whitelist_router)
    dp.include_router(stopwords_router)

    # Порт открываем до любых вызовов Telegram API и БД — иначе Railway/Docker healthcheck и delete_webhook висят в гонке.
    await _railway_health_server()
    logging.getLogger(__name__).info("Health HTTP on PORT (Railway) — слушаем / и /health")

    await _run_startup_with_retry()
    await _safe_delete_webhook()

    # ТЗ Напоминания + Автоотчёты: фоновый цикл (напоминания 12ч/24ч/3д, Guard раз в 3 дня, дайджест раз в сутки)
    from app.services.reminders import reminder_loop
    from app.services.autopost_loop import autopost_loop

    asyncio.create_task(reminder_loop(bot, interval_sec=900))
    asyncio.create_task(autopost_loop(interval_sec=30.0))

    print("😈 AntiSpam Guard запущен / BUILD 777")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
