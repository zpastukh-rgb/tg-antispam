"""Идемпотентные значения в БД при старте процессов (бот, API)."""

from __future__ import annotations

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)

# Пробный premium на 3 дня; активация — в мини-приложении или панели (per-user в promo_code_redemptions).
DEFAULT_TRIAL_PROMO_CODE = "TRIAL3"
DEFAULT_TRIAL_DAYS = 3
DEFAULT_COMEBACK_PROMO_CODE = "GUARDPLUS3"
DEFAULT_COMEBACK_DAYS = 3

# Бессрочный premium для владельца / внутренних тестов (отдельная строка в promo_codes, TRIAL3 не меняем).
# Переопределить код: OWNER_FOREVER_PROMO_CODE=my_secret
# Лимит чатов при активации: OWNER_FOREVER_CHAT_LIMIT (по умолчанию 500)
DEFAULT_OWNER_FOREVER_CODE = "GUARDIAN_OWNER"
DEFAULT_PROFANITY_ROOTS = (
    # Мат (корни/формы, чтобы ловить искажения и составные токены)
    "бля", "бляд", "блят", "еб", "еба", "ебан", "ебуч", "ебл", "заеб", "наеб", "поеб", "подъеб",
    "разъеб", "проеб", "уеб", "выеб", "пизд", "пезд", "пидор", "пидар", "пидр", "педик", "гондон",
    "хуй", "хуе", "хуйл", "хуйн", "хуяр", "хуяч", "хер", "муд", "мудак", "сук", "суч", "шлюх",
    "манда", "манд", "залуп", "гнид", "чмо", "урод", "ублюд", "долбоеб", "долбоеб",
    # Частые формы в фразах
    "иди нах", "пошел нах", "пошла нах", "похуй", "нихуя", "хуесос", "хуеплет",
)

DEFAULT_CASINO_ROOTS = (
    "казин", "ставк", "букмек", "букмекер", "bet", "бет", "1xbet", "winline", "fonbet", "фонбет",
    "леон", "pari", "пари", "рулетк", "слот", "слоты", "джекпот", "экспресс", "тотал",
    "кэф", "коэфф", "прогноз", "договорняк", "каппер", "капперск", "фрибет",
)

DEFAULT_JOBS_ROOTS = (
    "подработк", "подзаработ", "заработ", "заработа", "зарабаты", "заработать", "зарабатывать",
    "удаленк", "удаленнаяработа", "работанадому", "занятост",
    "легкийзаработок", "быстрыйдоход", "доход", "доходвдень", "безвложен", "безопыта",
    "пассивныйдоход", "обучениеснуля", "менеджерпеписок", "кураторчата", "переписки",
    "арбитражтрафика", "криптосигнал", "инвестпроект", "гарантированныйдоход",
    "заработоквтелеграм", "выплатыкаждыйдень", "осталосьпарумест", "график22", "график33",
    "2часавдень", "3часавдень", "4часавдень", "вариантзаработка", "рабочийвариант",
    "пишивличку", "пишивлс", "пишивпрофиль", "био", "смотривбио", "смотривпрофиле", "заподробностями",
    "пару людей", "кто бы смог", "кто интересно", "хочешь зарабатывать", "вариант неплохо заработать",
    "выплаты каждый день", "оплата на руки", "безнал", "давай ко мне за деталями",
    "есть свободные", "время менять жизнь", "узнай в био", "смотри описание", "схема приносит",
)


def get_owner_forever_promo_code() -> str:
    return (os.getenv("OWNER_FOREVER_PROMO_CODE") or DEFAULT_OWNER_FOREVER_CODE).strip().upper()


def get_owner_forever_chat_limit() -> int:
    try:
        return int(os.getenv("OWNER_FOREVER_CHAT_LIMIT", "500"))
    except ValueError:
        return 500


def get_comeback_promo_code() -> str:
    return (os.getenv("COMEBACK_PROMO_CODE") or DEFAULT_COMEBACK_PROMO_CODE).strip().upper()


async def ensure_default_trial_promo(engine: AsyncEngine) -> None:
    """Гарантирует строку промокода TRIAL3 (3 дня premium), не трогая used_at / redemptions."""
    stmt = text(
        """
        INSERT INTO promo_codes (code, tariff, days)
        VALUES (:code, 'premium', :days)
        ON CONFLICT (code) DO UPDATE
        SET tariff = EXCLUDED.tariff,
            days = EXCLUDED.days
        """
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(
                stmt,
                {"code": DEFAULT_TRIAL_PROMO_CODE, "days": DEFAULT_TRIAL_DAYS},
            )
    except Exception as e:
        log.warning("ensure_default_trial_promo skipped: %s", e)


async def ensure_owner_forever_promo(engine: AsyncEngine) -> None:
    """Гарантирует промокод владельца: premium, days=0 (бессрочно), без затрагивания redemptions."""
    code = get_owner_forever_promo_code()
    if not code:
        return
    stmt = text(
        """
        INSERT INTO promo_codes (code, tariff, days)
        VALUES (:code, 'premium', 0)
        ON CONFLICT (code) DO UPDATE
        SET tariff = EXCLUDED.tariff,
            days = EXCLUDED.days
        """
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(stmt, {"code": code})
    except Exception as e:
        log.warning("ensure_owner_forever_promo skipped: %s", e)


async def ensure_default_profanity_roots(engine: AsyncEngine) -> None:
    """Гарантирует базовый словарь корней: мат + казино/ставки + мутные подработки."""
    words = sorted({(w or "").strip().lower().replace("ё", "е")[:64] for w in DEFAULT_PROFANITY_ROOTS if w})
    if not words:
        return
    stmt = text("INSERT INTO profanity_words (word) VALUES (:w) ON CONFLICT (word) DO NOTHING")
    try:
        async with engine.begin() as conn:
            for word in words:
                await conn.execute(stmt, {"w": word})
    except Exception as e:
        log.warning("ensure_default_profanity_roots skipped: %s", e)


async def ensure_default_comeback_promo(engine: AsyncEngine) -> None:
    """Гарантирует бонусный промокод возвращения (3 дня premium) отдельно от TRIAL3."""
    code = get_comeback_promo_code()
    if not code:
        return
    stmt = text(
        """
        INSERT INTO promo_codes (code, tariff, days)
        VALUES (:code, 'premium', :days)
        ON CONFLICT (code) DO UPDATE
        SET tariff = EXCLUDED.tariff,
            days = EXCLUDED.days
        """
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(stmt, {"code": code, "days": DEFAULT_COMEBACK_DAYS})
    except Exception as e:
        log.warning("ensure_default_comeback_promo skipped: %s", e)


async def ensure_chats_chat_kind_column(engine: AsyncEngine) -> None:
    """
    migrations/012: колонка chats.chat_kind (группа vs канал для рассылки).
    Без неё ORM падает на UndefinedColumnError на старых БД.
    """
    sql_blocks = (
        "ALTER TABLE chats ADD COLUMN IF NOT EXISTS chat_kind VARCHAR(16) DEFAULT 'group'",
        "UPDATE chats SET chat_kind = 'group' WHERE chat_kind IS NULL",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
        log.info("ensure_chats_chat_kind_column: ok")
    except Exception as e:
        log.warning("ensure_chats_chat_kind_column skipped: %s", e)


async def ensure_referral_credits_schema(engine: AsyncEngine) -> None:
    """Идемпотентно добавляет поля рефералки/кредитов в users для старых БД."""
    sql_blocks = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits_balance DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_credits DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_tg_id BIGINT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_invited_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_start_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_share_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_paid_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_sales_total DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_earned_credits DOUBLE PRECISION DEFAULT 0.0",
        "CREATE INDEX IF NOT EXISTS ix_users_referred_by_tg_id ON users (referred_by_tg_id)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_referral_credits_schema skipped: %s", e)


async def ensure_credit_ledger_schema(engine: AsyncEngine) -> None:
    """Идемпотентно создаёт таблицу истории кредитов."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS credit_ledger (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            delta DOUBLE PRECISION NOT NULL,
            reason VARCHAR(64) NOT NULL DEFAULT 'adjust',
            external_key VARCHAR(128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_credit_ledger_user_id ON credit_ledger (user_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_ledger_user_external ON credit_ledger (user_id, external_key)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_credit_ledger_schema skipped: %s", e)


async def ensure_partner_payouts_schema(engine: AsyncEngine) -> None:
    """Идемпотентно создает таблицу заявок на партнерские выплаты."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS partner_payout_requests (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            amount_rub DOUBLE PRECISION NOT NULL,
            method VARCHAR(32) NOT NULL DEFAULT 'sbp',
            requisites VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            risk_flag BOOLEAN NOT NULL DEFAULT FALSE,
            risk_note VARCHAR(255),
            admin_note VARCHAR(255),
            payout_notice_message_id INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE partner_payout_requests ADD COLUMN IF NOT EXISTS payout_notice_message_id INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_partner_payout_requests_user_id ON partner_payout_requests (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_partner_payout_requests_status ON partner_payout_requests (status)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_partner_payouts_schema skipped: %s", e)


async def ensure_partner_commissions_schema(engine: AsyncEngine) -> None:
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS partner_commissions (
            id SERIAL PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            payment_id INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
            level INTEGER NOT NULL,
            rate DOUBLE PRECISION NOT NULL,
            sales_amount_rub DOUBLE PRECISION NOT NULL,
            reward_amount_rub DOUBLE PRECISION NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            available_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_partner_commissions_owner_user_id ON partner_commissions (owner_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_partner_commissions_source_user_id ON partner_commissions (source_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_partner_commissions_payment_id ON partner_commissions (payment_id)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_partner_commissions_schema skipped: %s", e)


async def ensure_partner_token_rate_v2(engine: AsyncEngine) -> None:
    """Одноразовый пересчет партнерских токенов под курс 1 токен = 2 RUB."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS system_flags (
                    key VARCHAR(128) PRIMARY KEY,
                    value VARCHAR(255),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ))
            flag_q = await conn.execute(
                text("SELECT value FROM system_flags WHERE key = 'partner_token_rate_v2_applied' LIMIT 1")
            )
            if flag_q.scalar_one_or_none():
                return
            await conn.execute(
                text("UPDATE users SET bonus_credits = ROUND(COALESCE(bonus_credits, 0.0) / 2.0, 2)")
            )
            await conn.execute(
                text("INSERT INTO system_flags (key, value) VALUES ('partner_token_rate_v2_applied', '1')")
            )
    except Exception as e:
        log.warning("ensure_partner_token_rate_v2 skipped: %s", e)


async def ensure_subscription_token_rate_v2(engine: AsyncEngine) -> None:
    """Одноразовый пересчет подписочных токенов под курс 1 токен = 2 RUB."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS system_flags (
                    key VARCHAR(128) PRIMARY KEY,
                    value VARCHAR(255),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ))
            flag_q = await conn.execute(
                text("SELECT value FROM system_flags WHERE key = 'subscription_token_rate_v2_applied' LIMIT 1")
            )
            if flag_q.scalar_one_or_none():
                return
            await conn.execute(
                text("UPDATE users SET credits_balance = ROUND(COALESCE(credits_balance, 0.0) / 2.0, 2)")
            )
            await conn.execute(
                text("INSERT INTO system_flags (key, value) VALUES ('subscription_token_rate_v2_applied', '1')")
            )
    except Exception as e:
        log.warning("ensure_subscription_token_rate_v2 skipped: %s", e)


async def ensure_rules_hard_dictionary_independent_v1(engine: AsyncEngine) -> None:
    """
    Одноразово включает все три тумблера жёсткого словаря для существующих rules.

    Раньше при «ВКЛ» только одного пункта в БД оставались false у двух других, и evaluate
    отключал мат / подработки / казино независимо от ожиданий по UI. После патча тумблеры
    независимы; отключать смыслы можно явно в приложении.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS system_flags (
                        key VARCHAR(128) PRIMARY KEY,
                        value VARCHAR(255),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            chk = await conn.execute(
                text(
                    "SELECT value FROM system_flags WHERE key = 'rules_hard_dict_independent_v1' LIMIT 1"
                )
            )
            if chk.scalar_one_or_none():
                return
            await conn.execute(
                text(
                    """
                    UPDATE rules SET
                        filter_profanity_enabled = TRUE,
                        filter_jobs_enabled = TRUE,
                        filter_casino_enabled = TRUE
                    """
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO system_flags (key, value) VALUES ('rules_hard_dict_independent_v1', '1')"
                )
            )
    except Exception as e:
        log.warning("ensure_rules_hard_dictionary_independent_v1 skipped: %s", e)


async def ensure_admin_broadcasts_schema(engine: AsyncEngine) -> None:
    """Таблица рассылок из админки (посты в личку пользователям бота)."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS admin_broadcasts (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL DEFAULT '',
            body_text TEXT NOT NULL DEFAULT '',
            parse_mode VARCHAR(32),
            keyboard_json TEXT,
            media_kind VARCHAR(32) NOT NULL DEFAULT 'none',
            media_local_name VARCHAR(255),
            media_original_name VARCHAR(255),
            telegram_file_id VARCHAR(255),
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            last_target VARCHAR(16),
            admin_telegram_id BIGINT NOT NULL,
            recipient_total INTEGER NOT NULL DEFAULT 0,
            recipient_ok INTEGER NOT NULL DEFAULT 0,
            recipient_fail INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            sent_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_admin_telegram_id ON admin_broadcasts (admin_telegram_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_status ON admin_broadcasts (status)",
        "ALTER TABLE admin_broadcasts ADD COLUMN IF NOT EXISTS media_original_name VARCHAR(255)",
        "ALTER TABLE admin_broadcasts ADD COLUMN IF NOT EXISTS last_target VARCHAR(16)",
        "ALTER TABLE admin_broadcasts ADD COLUMN IF NOT EXISTS autopost_json TEXT",
        """
        CREATE TABLE IF NOT EXISTS admin_broadcast_media (
            id SERIAL PRIMARY KEY,
            broadcast_id INTEGER NOT NULL REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
            media_kind VARCHAR(32) NOT NULL DEFAULT 'photo',
            media_local_name VARCHAR(255) NOT NULL,
            media_original_name VARCHAR(255),
            telegram_file_id VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_media_broadcast_id ON admin_broadcast_media (broadcast_id)",
        """
        CREATE TABLE IF NOT EXISTS admin_broadcast_delivery (
            id SERIAL PRIMARY KEY,
            broadcast_id INTEGER NOT NULL REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
            batch_id VARCHAR(64) NOT NULL DEFAULT '',
            target_kind VARCHAR(16) NOT NULL DEFAULT 'user',
            target_id BIGINT NOT NULL,
            ok BOOLEAN NOT NULL DEFAULT FALSE,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_delivery_broadcast_id ON admin_broadcast_delivery (broadcast_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_delivery_target_kind ON admin_broadcast_delivery (target_kind)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_delivery_target_id ON admin_broadcast_delivery (target_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_delivery_ok ON admin_broadcast_delivery (ok)",
        "ALTER TABLE admin_broadcast_delivery ADD COLUMN IF NOT EXISTS batch_id VARCHAR(64) NOT NULL DEFAULT ''",
        "ALTER TABLE admin_broadcast_delivery ADD COLUMN IF NOT EXISTS target_kind VARCHAR(16) NOT NULL DEFAULT 'user'",
        "ALTER TABLE admin_broadcast_delivery ADD COLUMN IF NOT EXISTS target_id BIGINT",
        "ALTER TABLE admin_broadcast_delivery ADD COLUMN IF NOT EXISTS error_message TEXT",
        "ALTER TABLE admin_broadcast_delivery ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_delivery_batch_id ON admin_broadcast_delivery (batch_id)",
        """
        CREATE TABLE IF NOT EXISTS admin_broadcast_runs (
            id SERIAL PRIMARY KEY,
            broadcast_id INTEGER NOT NULL REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
            target_kind VARCHAR(16) NOT NULL DEFAULT 'users',
            recipient_total INTEGER NOT NULL DEFAULT 0,
            recipient_ok INTEGER NOT NULL DEFAULT 0,
            recipient_fail INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            sent_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_runs_broadcast_id ON admin_broadcast_runs (broadcast_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_runs_target_kind ON admin_broadcast_runs (target_kind)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_runs_created_at ON admin_broadcast_runs (created_at)",
        # migrations/012: источник запуска (manual | autopost)
        "ALTER TABLE admin_broadcast_runs ADD COLUMN IF NOT EXISTS run_source VARCHAR(16)",
        "UPDATE admin_broadcast_runs SET run_source = 'manual' WHERE run_source IS NULL",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_admin_broadcasts_schema skipped: %s", e)


async def ensure_rules_public_alerts_columns(engine: AsyncEngine) -> None:
    """
    Колонки публичных анонсов (migrations/002_public_alerts.sql, 004_public_alerts_style.sql).
    Если не применить SQL вручную на проде, API падает на SELECT rules... public_alerts_style.
    """
    stmts = (
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_every_n INTEGER DEFAULT 5",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_min_interval_sec INTEGER DEFAULT 300",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_last_sent_at TIMESTAMPTZ",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_style VARCHAR(16) DEFAULT 'guard'",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
        log.info("ensure_rules_public_alerts_columns: ok")
    except Exception as e:
        log.warning("ensure_rules_public_alerts_columns skipped: %s", e)
