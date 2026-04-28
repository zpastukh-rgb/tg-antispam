"""Идемпотентные значения в БД при старте процессов (бот, API)."""

from __future__ import annotations

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)

# Пробный premium на 3 дня; активация — в мини-приложении или панели (per-user в promo_code_redemptions).
DEFAULT_TRIAL_PROMO_CODE = "TRIAL-3D-V4K9-ZTQ2-N8WP"
DEFAULT_TRIAL_DAYS = 3
DEFAULT_PREMIUM7_PROMO_CODE = "PREM-7D-X7QP-4M2K-R8TZ"
DEFAULT_PREMIUM14_PROMO_CODE = "PREM-14D-L9VW-2QXR-N6MT"
DEFAULT_PREMIUM3M_PROMO_CODE = "PREM-3M-Q8TX-5RKW-N2VP"
DEFAULT_PREMIUM6M_PROMO_CODE = "PREM-6M-V7QP-4LNZ-K9WT"
DEFAULT_PREMIUM12M_PROMO_CODE = "PREM-12M-R6MX-3QTV-P8ZN"
DEFAULT_COMEBACK_PROMO_CODE = "COME-3D-P7RK-9VQW-M4XT"
DEFAULT_COMEBACK_DAYS = 3
DEFAULT_TOKENS500_PROMO_CODE = "TOK500-Q7MX-4VNZ-P2KW"
DEFAULT_TOKENS1000_PROMO_CODE = "TOK1000-R8PT-5WQX-K3ZM"
# 2000 ⚡: без лимита активаций на одного пользователя (как владельческий «вечный» код, но только токены).
DEFAULT_TOKENS2000_REPEAT_PROMO_CODE = "TOK2000-M7RK-4PVW-Q9NL"
DEFAULT_AURUM1500_PROMO_CODE = "AUR1500-T9VK-6QRM-X4NP"
LEGACY_SIMPLE_PROMO_CODES = ("TRIAL3", "PREM7", "PREM14", "GUARDPLUS3")

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


def get_repeatable_tokens2000_promo_code() -> str:
    """Промокод +2000 ⚡ без ограничения повторных активаций одним пользователем."""
    return (os.getenv("REPEATABLE_TOKENS2000_PROMO_CODE") or DEFAULT_TOKENS2000_REPEAT_PROMO_CODE).strip().upper()


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


async def ensure_default_admin_promo_codes(engine: AsyncEngine) -> None:
    """Гарантирует служебные промокоды Premium разных сроков."""
    rows = (
        (DEFAULT_PREMIUM7_PROMO_CODE, 7),
        (DEFAULT_PREMIUM14_PROMO_CODE, 14),
        (DEFAULT_PREMIUM3M_PROMO_CODE, 90),
        (DEFAULT_PREMIUM6M_PROMO_CODE, 180),
        (DEFAULT_PREMIUM12M_PROMO_CODE, 365),
    )
    try:
        async with engine.begin() as conn:
            for code, days in rows:
                await conn.execute(
                    text(
                        """
                        INSERT INTO promo_codes (code, tariff, days)
                        VALUES (:code, 'premium', :days)
                        ON CONFLICT (code) DO UPDATE
                        SET tariff = EXCLUDED.tariff,
                            days = EXCLUDED.days
                        """
                    ),
                    {"code": code, "days": int(days)},
                )
    except Exception as e:
        log.warning("ensure_default_admin_promo_codes skipped: %s", e)


async def ensure_default_token_aurum_promo_codes(engine: AsyncEngine) -> None:
    """Гарантирует разовые промокоды на токены/AURUM без изменения тарифа."""
    rows = (
        (DEFAULT_TOKENS500_PROMO_CODE, 500.0, 0.0),
        (DEFAULT_TOKENS1000_PROMO_CODE, 1000.0, 0.0),
        (get_repeatable_tokens2000_promo_code(), 2000.0, 0.0),
        (DEFAULT_AURUM1500_PROMO_CODE, 0.0, 1500.0),
    )
    try:
        async with engine.begin() as conn:
            for code, grant_tokens, grant_aurum in rows:
                await conn.execute(
                    text(
                        """
                        INSERT INTO promo_codes (code, tariff, days, grant_tokens, grant_aurum)
                        VALUES (:code, 'free', -1, :grant_tokens, :grant_aurum)
                        ON CONFLICT (code) DO UPDATE
                        SET tariff = EXCLUDED.tariff,
                            days = EXCLUDED.days,
                            grant_tokens = EXCLUDED.grant_tokens,
                            grant_aurum = EXCLUDED.grant_aurum
                        """
                    ),
                    {
                        "code": code,
                        "grant_tokens": float(grant_tokens or 0.0),
                        "grant_aurum": float(grant_aurum or 0.0),
                    },
                )
    except Exception as e:
        log.warning("ensure_default_token_aurum_promo_codes skipped: %s", e)


async def ensure_disable_legacy_simple_promo_codes(engine: AsyncEngine) -> None:
    """Отключает старые простые коды после перехода на сложные (только по явному ENV)."""
    raw = str(os.getenv("DISABLE_LEGACY_SIMPLE_PROMO_CODES", "") or "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return
    try:
        async with engine.begin() as conn:
            for code in LEGACY_SIMPLE_PROMO_CODES:
                await conn.execute(text("DELETE FROM promo_codes WHERE code=:code"), {"code": str(code)})
    except Exception as e:
        log.warning("ensure_disable_legacy_simple_promo_codes skipped: %s", e)


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


async def ensure_chats_linked_discussion_chat_id_column(engine: AsyncEngine) -> None:
    """Колонка chats.linked_discussion_chat_id — связка канал → группа обсуждения (делегат канала → API правил комментариев)."""
    sql_blocks = ("ALTER TABLE chats ADD COLUMN IF NOT EXISTS linked_discussion_chat_id BIGINT",)
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
        log.info("ensure_chats_linked_discussion_chat_id_column: ok")
    except Exception as e:
        log.warning("ensure_chats_linked_discussion_chat_id_column skipped: %s", e)


async def ensure_chats_linked_channel_chat_id_column(engine: AsyncEngine) -> None:
    """Колонка chats.linked_channel_chat_id — группа обсуждения → id канала (для списка чатов Mini App)."""
    sql_blocks = ("ALTER TABLE chats ADD COLUMN IF NOT EXISTS linked_channel_chat_id BIGINT",)
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
        log.info("ensure_chats_linked_channel_chat_id_column: ok")
    except Exception as e:
        log.warning("ensure_chats_linked_channel_chat_id_column skipped: %s", e)


async def ensure_referral_credits_schema(engine: AsyncEngine) -> None:
    """Идемпотентно добавляет поля рефералки/кредитов в users для старых БД."""
    sql_blocks = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits_balance DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS aurum_credits DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_credits DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_tg_id BIGINT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_invited_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_start_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_share_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_paid_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_sales_total DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_earned_credits DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_webapp_seen_at TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS ix_users_referred_by_tg_id ON users (referred_by_tg_id)",
        "CREATE INDEX IF NOT EXISTS ix_users_last_webapp_seen_at ON users (last_webapp_seen_at)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_referral_credits_schema skipped: %s", e)


async def ensure_promo_codes_grant_schema(engine: AsyncEngine) -> None:
    """Идемпотентно добавляет поля начислений в promo_codes для токенов и AURUM."""
    sql_blocks = (
        "ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS grant_tokens DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS grant_aurum DOUBLE PRECISION DEFAULT 0.0",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_promo_codes_grant_schema skipped: %s", e)


async def ensure_chat_manager_invites_schema(engine: AsyncEngine) -> None:
    """Идемпотентно создает таблицу приглашений админов в кабинеты чатов."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS chat_manager_invites (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            owner_user_id BIGINT NOT NULL,
            target_telegram_id BIGINT NULL,
            target_username VARCHAR(255) NULL,
            connected_user_id BIGINT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'sent',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_chat_manager_invites_chat_id ON chat_manager_invites (chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_manager_invites_owner_user_id ON chat_manager_invites (owner_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_manager_invites_target_telegram_id ON chat_manager_invites (target_telegram_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_manager_invites_target_username ON chat_manager_invites (target_username)",
        "CREATE INDEX IF NOT EXISTS ix_chat_manager_invites_connected_user_id ON chat_manager_invites (connected_user_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_manager_invite_tg ON chat_manager_invites (chat_id, owner_user_id, target_telegram_id) WHERE target_telegram_id IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_manager_invite_uname ON chat_manager_invites (chat_id, owner_user_id, lower(target_username)) WHERE target_username IS NOT NULL",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_chat_manager_invites_schema skipped: %s", e)


async def ensure_admin_insights_schema(engine: AsyncEngine) -> None:
    """Идемпотентно создает таблицы для сводки и шаблонов сообщений админки."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS referral_share_hits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_referral_share_hits_user_id ON referral_share_hits (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_referral_share_hits_created_at ON referral_share_hits (created_at)",
        """
        CREATE TABLE IF NOT EXISTS admin_message_templates (
            id SERIAL PRIMARY KEY,
            template_key VARCHAR(64) NOT NULL UNIQUE,
            title VARCHAR(255) NOT NULL,
            body_text TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            delay_minutes INTEGER,
            parse_mode VARCHAR(16),
            is_custom BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE admin_message_templates ADD COLUMN IF NOT EXISTS event_key VARCHAR(64) DEFAULT 'manual'",
        "ALTER TABLE admin_message_templates ADD COLUMN IF NOT EXISTS target_kind VARCHAR(32) DEFAULT 'owner_admin'",
        "ALTER TABLE admin_message_templates ADD COLUMN IF NOT EXISTS trigger_hours INTEGER DEFAULT 24",
        "ALTER TABLE admin_message_templates ADD COLUMN IF NOT EXISTS min_count INTEGER DEFAULT 1",
        "ALTER TABLE admin_message_templates ADD COLUMN IF NOT EXISTS cooldown_minutes INTEGER DEFAULT 1440",
        "ALTER TABLE admin_message_templates ADD COLUMN IF NOT EXISTS schedule_time_hm VARCHAR(5)",
        "CREATE INDEX IF NOT EXISTS ix_admin_message_templates_key ON admin_message_templates (template_key)",
        """
        CREATE TABLE IF NOT EXISTS admin_message_dispatch_logs (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL,
            target_tg_id BIGINT NOT NULL,
            event_bucket VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_admin_message_dispatch_logs_template_target ON admin_message_dispatch_logs (template_id, target_tg_id, created_at)",
    )
    seed_templates = (
        ("reminder_12h", "Напоминание через 12 часов", "😈 AntiSpam Guard напоминает.\n\nВы запустили бота, но ещё не подключили ни одной группы.\n\nЯ могу защищать чат от:\n• спама\n• ссылочного мусора\n• рейдов\n• ботов\n\nПодключение занимает 10 секунд.", 12 * 60, None),
        ("reminder_24h", "Напоминание через 24 часа", "😈 Я всё ещё жду.\n\nПока я не подключён — спамеры чувствуют себя спокойно.\nПодключите группу и я начну работу.", 24 * 60, None),
        ("reminder_3d", "Напоминание через 3 дня", "😈 Последнее напоминание.\n\nЯ могу защищать ваши чаты автоматически.\nДобавьте меня администратором и я начну работу.", 72 * 60, None),
        ("reports_reminder", "Напоминание подключить чат отчётов", "😈 *AntiSpam Guard*\n\nПодключи чат отчётов, чтобы не пропускать важное:\n• 🧹 удаления сообщений\n• 🔇 муты\n• ⛔ баны\n• ✅ кнопки размута\n\nТак в одном месте видно, кого и за что остановил Guard.", None, "Markdown"),
        ("owner_daily_report", "Ежедневная сводка владельцу", "📊 Ежесуточная сводка Guard", None, "Markdown"),
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
            for key, title, body, delay, parse_mode in seed_templates:
                await conn.execute(
                    text(
                        """
                        INSERT INTO admin_message_templates
                        (template_key, title, body_text, enabled, delay_minutes, parse_mode, is_custom, event_key, target_kind, trigger_hours, min_count, cooldown_minutes)
                        VALUES (:k, :t, :b, TRUE, :d, :p, FALSE, :e, 'owner_admin', 24, 1, 1440)
                        ON CONFLICT (template_key) DO UPDATE
                        SET event_key = EXCLUDED.event_key,
                            target_kind = EXCLUDED.target_kind
                        """
                    ),
                    {
                        "k": key,
                        "t": title,
                        "b": body,
                        "d": delay,
                        "p": parse_mode,
                        "e": (
                            "user_no_group_reminder_12h" if key == "reminder_12h" else
                            "user_no_group_reminder_24h" if key == "reminder_24h" else
                            "user_no_group_reminder_3d" if key == "reminder_3d" else
                            "user_reports_chat_reminder" if key == "reports_reminder" else
                            "owner_daily_report" if key == "owner_daily_report" else
                            "manual"
                        ),
                    },
                )
    except Exception as e:
        log.warning("ensure_admin_insights_schema skipped: %s", e)


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
                text(
                    "UPDATE users SET bonus_credits = ("
                    "ROUND((COALESCE(bonus_credits, 0.0) / 2.0)::numeric, 2)"
                    ")::double precision"
                )
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
                text(
                    "UPDATE users SET credits_balance = ("
                    "ROUND((COALESCE(credits_balance, 0.0) / 2.0)::numeric, 2)"
                    ")::double precision"
                )
            )
            await conn.execute(
                text("INSERT INTO system_flags (key, value) VALUES ('subscription_token_rate_v2_applied', '1')")
            )
    except Exception as e:
        log.warning("ensure_subscription_token_rate_v2 skipped: %s", e)


async def ensure_subscription_credits_merged_to_aurum_v1(engine: AsyncEngine) -> None:
    """Одноразово: старый «подписочный» счётчик credits_balance переносится в aurum_credits и обнуляется."""
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
            flag_q = await conn.execute(
                text(
                    "SELECT value FROM system_flags WHERE key = 'subscription_credits_merged_to_aurum_v1' LIMIT 1"
                )
            )
            if flag_q.scalar_one_or_none():
                return
            await conn.execute(
                text(
                    """
                    UPDATE users SET
                        aurum_credits = (
                            ROUND(
                                (COALESCE(aurum_credits, 0.0) + COALESCE(credits_balance, 0.0))::numeric,
                                4
                            )
                        )::double precision,
                        credits_balance = 0.0
                    WHERE COALESCE(credits_balance, 0.0) > 0
                    """
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO system_flags (key, value) VALUES ('subscription_credits_merged_to_aurum_v1', '1')"
                )
            )
    except Exception as e:
        log.warning("ensure_subscription_credits_merged_to_aurum_v1 skipped: %s", e)


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
        # migrations/020: аудитория и реальные клики по ссылкам
        "ALTER TABLE admin_broadcast_runs ADD COLUMN IF NOT EXISTS audience_total INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE admin_broadcast_runs ADD COLUMN IF NOT EXISTS audience_ok INTEGER NOT NULL DEFAULT 0",
        """
        CREATE TABLE IF NOT EXISTS admin_broadcast_clicks (
            id SERIAL PRIMARY KEY,
            broadcast_id INTEGER NOT NULL REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
            target_kind VARCHAR(16) NOT NULL DEFAULT 'user',
            target_id BIGINT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_broadcast_id ON admin_broadcast_clicks (broadcast_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_target_kind ON admin_broadcast_clicks (target_kind)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_target_id ON admin_broadcast_clicks (target_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_created_at ON admin_broadcast_clicks (created_at)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_admin_broadcasts_schema skipped: %s", e)


async def ensure_autopost_campaigns_schema(engine: AsyncEngine) -> None:
    """Независимые кампании автопоста (migrations/013_autopost_campaigns.sql)."""
    stmts = (
        """
        CREATE TABLE IF NOT EXISTS autopost_campaigns (
            id SERIAL PRIMARY KEY,
            admin_telegram_id BIGINT NOT NULL,
            title VARCHAR(255) NOT NULL DEFAULT '',
            anchor_broadcast_id INTEGER,
            autopost_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_autopost_campaigns_admin_telegram_id ON autopost_campaigns (admin_telegram_id)",
        "CREATE INDEX IF NOT EXISTS ix_autopost_campaigns_anchor_broadcast_id ON autopost_campaigns (anchor_broadcast_id)",
        "ALTER TABLE autopost_campaigns ADD COLUMN IF NOT EXISTS user_seq INTEGER",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_autopost_campaigns_schema skipped: %s", e)


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


async def ensure_rules_guardian_periodic_columns(engine: AsyncEngine) -> None:
    """Колонки периодических служебных сообщений Guard в группе."""
    stmts = (
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS guardian_periodic_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS guardian_periodic_interval_hours INTEGER DEFAULT 24",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
        log.info("ensure_rules_guardian_periodic_columns: ok")
    except Exception as e:
        log.warning("ensure_rules_guardian_periodic_columns skipped: %s", e)


async def ensure_users_comeback_offer_column(engine: AsyncEngine) -> None:
    """Отметка, что бонусный comeback-промокод уже предлагали пользователю."""
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS comeback_offer_sent_at TIMESTAMPTZ")
            )
        log.info("ensure_users_comeback_offer_column: ok")
    except Exception as e:
        log.warning("ensure_users_comeback_offer_column skipped: %s", e)


async def ensure_global_bad_url_patterns_schema(engine: AsyncEngine) -> None:
    """Глобальные шаблоны плохих URL (админка)."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS global_bad_url_patterns (
            id BIGSERIAL PRIMARY KEY,
            pattern VARCHAR(255) NOT NULL,
            note VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_global_bad_url_pattern ON global_bad_url_patterns (pattern)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
        log.info("ensure_global_bad_url_patterns_schema: ok")
    except Exception as e:
        log.warning("ensure_global_bad_url_patterns_schema skipped: %s", e)


async def ensure_user_global_bad_url_patterns_schema(engine: AsyncEngine) -> None:
    """Персональные шаблоны плохих URL по владельцу (Premium / личная база в кабинете)."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS user_global_bad_url_patterns (
            id BIGSERIAL PRIMARY KEY,
            owner_telegram_id BIGINT NOT NULL,
            pattern VARCHAR(255) NOT NULL,
            note VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_user_global_bad_url_owner ON user_global_bad_url_patterns (owner_telegram_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_global_bad_url_owner_pattern ON user_global_bad_url_patterns (owner_telegram_id, pattern)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
        log.info("ensure_user_global_bad_url_patterns_schema: ok")
    except Exception as e:
        log.warning("ensure_user_global_bad_url_patterns_schema skipped: %s", e)


async def ensure_rules_use_global_bad_urls_column(engine: AsyncEngine) -> None:
    """Флаг: дополнительно проверять глобальную базу плохих URL."""
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE rules ADD COLUMN IF NOT EXISTS use_global_bad_urls BOOLEAN DEFAULT FALSE")
            )
        log.info("ensure_rules_use_global_bad_urls_column: ok")
    except Exception as e:
        log.warning("ensure_rules_use_global_bad_urls_column skipped: %s", e)


async def ensure_rules_channel_posts_filter_columns(engine: AsyncEngine) -> None:
    """Фильтр сообщений от имени каналов/чатов в группах."""
    stmts = (
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_posts_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_posts_action VARCHAR(16) DEFAULT 'delete'",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
        log.info("ensure_rules_channel_posts_filter_columns: ok")
    except Exception as e:
        log.warning("ensure_rules_channel_posts_filter_columns skipped: %s", e)


async def ensure_rules_welcome_columns(engine: AsyncEngine) -> None:
    """Колонки приветствия новых участников по каждому чату."""
    stmts = (
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_text TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_buttons_json TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_photo_path VARCHAR(512)",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_max_per_min INTEGER DEFAULT 0",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_silent_on_raid BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_raid_threshold INTEGER DEFAULT 8",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_raid_window_minutes INTEGER DEFAULT 2",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS welcome_every_n_joins INTEGER DEFAULT 1",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
        log.info("ensure_rules_welcome_columns: ok")
    except Exception as e:
        log.warning("ensure_rules_welcome_columns skipped: %s", e)


async def ensure_whitelist_sender_chats_schema(engine: AsyncEngine) -> None:
    """Whitelist @username каналов для фильтра sender_chat."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS whitelist_sender_chats (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            channel_username VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_whitelist_sender_chats_chat_id ON whitelist_sender_chats (chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_whitelist_sender_chats_username ON whitelist_sender_chats (channel_username)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_whitelist_sender_chat ON whitelist_sender_chats (chat_id, channel_username)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
        log.info("ensure_whitelist_sender_chats_schema: ok")
    except Exception as e:
        log.warning("ensure_whitelist_sender_chats_schema skipped: %s", e)


async def ensure_link_blacklist_schema(engine: AsyncEngine) -> None:
    """Чёрный список ссылок по чату (Premium)."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS link_blacklist (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            pattern VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_link_blacklist_chat_id ON link_blacklist (chat_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_link_blacklist_chat_pattern ON link_blacklist (chat_id, pattern)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
        log.info("ensure_link_blacklist_schema: ok")
    except Exception as e:
        log.warning("ensure_link_blacklist_schema skipped: %s", e)


async def ensure_rules_filter_links_mode_width(engine: AsyncEngine) -> None:
    """Расширить VARCHAR для новых режимов ссылок (smart, telegram_only, …)."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE rules ALTER COLUMN filter_links_mode TYPE VARCHAR(32)"))
        log.info("ensure_rules_filter_links_mode_width: ok")
    except Exception as e:
        log.warning("ensure_rules_filter_links_mode_width skipped: %s", e)


async def ensure_rules_filter_links_scope_column(engine: AsyncEngine) -> None:
    """Область фильтра ссылок: весь чат или только комментарии к постам канала (форум-обсуждение)."""
    stmts = (
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_links_scope VARCHAR(32) DEFAULT 'all'",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
        log.info("ensure_rules_filter_links_scope_column: ok")
    except Exception as e:
        log.warning("ensure_rules_filter_links_scope_column skipped: %s", e)


async def ensure_spam_spike_notify_schema(engine: AsyncEngine) -> None:
    """Таблицы антидубля для DM и служебного сообщения в группу при всплеске спама."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS spam_spike_notify_sent (
            id SERIAL PRIMARY KEY,
            recipient_telegram_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            bucket_key VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_spam_spike_notify_recipient ON spam_spike_notify_sent (recipient_telegram_id)",
        "CREATE INDEX IF NOT EXISTS ix_spam_spike_notify_chat ON spam_spike_notify_sent (chat_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_spam_spike_dm ON spam_spike_notify_sent (recipient_telegram_id, chat_id, bucket_key)",
        """
        CREATE TABLE IF NOT EXISTS spam_spike_group_ping_sent (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            bucket_key VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_spam_spike_group_ping_chat ON spam_spike_group_ping_sent (chat_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_spam_spike_group_ping ON spam_spike_group_ping_sent (chat_id, bucket_key)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_spam_spike_notify_schema skipped: %s", e)


async def ensure_payments_receipt_url_schema(engine: AsyncEngine) -> None:
    """Колонка ссылки на чек для payments (для кнопки «🧾 Чек»)."""
    stmts = (
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS receipt_url VARCHAR(1024)",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_payments_receipt_url_schema skipped: %s", e)


async def ensure_users_subscription_source_schema(engine: AsyncEngine) -> None:
    """Источник подписки у пользователя (payment/promo/...)."""
    stmts = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_source VARCHAR(32)",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_users_subscription_source_schema skipped: %s", e)


async def ensure_users_subscription_activated_at_schema(engine: AsyncEngine) -> None:
    """Дата первого оплаченного периода подписки; бэкфилл из payments (min created_at, tariff=premium)."""
    stmts = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_activated_at TIMESTAMPTZ",
        """
        UPDATE users u
        SET subscription_activated_at = s.first_paid
        FROM (
            SELECT user_id, MIN(created_at) AS first_paid
            FROM payments
            WHERE status = 'succeeded' AND tariff = 'premium'
            GROUP BY user_id
        ) s
        WHERE u.id = s.user_id AND u.subscription_activated_at IS NULL
        """,
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_users_subscription_activated_at_schema skipped: %s", e)


async def ensure_users_payment_binding_schema(engine: AsyncEngine) -> None:
    """Поля users для отслеживания привязки способа оплаты (card saved)."""
    stmts = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_method_bound BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_method_type VARCHAR(32)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_method_last4 VARCHAR(8)",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_users_payment_binding_schema skipped: %s", e)


async def ensure_users_group_channel_limits_schema(engine: AsyncEngine) -> None:
    """Раздельные лимиты users: group_limit / channel_limit (+ бэкфилл из chat_limit)."""
    stmts = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS group_limit INTEGER DEFAULT 3",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS channel_limit INTEGER DEFAULT 1",
        "UPDATE users SET group_limit = COALESCE(NULLIF(group_limit, 0), NULLIF(chat_limit, 0), 3)",
        "UPDATE users SET channel_limit = COALESCE(NULLIF(channel_limit, 0), CASE WHEN lower(coalesce(tariff, 'free')) IN ('premium','pro','business') THEN 20 ELSE 1 END)",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_users_group_channel_limits_schema skipped: %s", e)


async def ensure_chat_spike_alerts_schema(engine: AsyncEngine) -> None:
    """Таблица активных флагов риска по чатам для UI."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS chat_spike_alerts (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL UNIQUE,
            spam_count INTEGER NOT NULL DEFAULT 0,
            joins_count INTEGER NOT NULL DEFAULT 0,
            window_min INTEGER NOT NULL DEFAULT 35,
            last_triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_spike_alert_chat ON chat_spike_alerts (chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_spike_alerts_chat_id ON chat_spike_alerts (chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_spike_alerts_expires_at ON chat_spike_alerts (expires_at)",
        "CREATE INDEX IF NOT EXISTS ix_chat_spike_alerts_last_triggered_at ON chat_spike_alerts (last_triggered_at)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_chat_spike_alerts_schema skipped: %s", e)


async def ensure_rules_spam_spike_columns(engine: AsyncEngine) -> None:
    """Настройки всплеска спама на уровне rules (порог/окно/уведомление делегата)."""
    stmts = (
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS spam_spike_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS spam_spike_min_deletes INTEGER DEFAULT 15",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS spam_spike_window_minutes INTEGER DEFAULT 35",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS spam_spike_notify_managers BOOLEAN DEFAULT TRUE",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
            # Нормализуем дефолт колонки для уже существующих БД.
            await conn.execute(text("ALTER TABLE rules ALTER COLUMN spam_spike_min_deletes SET DEFAULT 15"))
            # Подстраховка для старых пустых/некорректных значений.
            await conn.execute(
                text(
                    "UPDATE rules SET spam_spike_min_deletes = 15 "
                    "WHERE spam_spike_min_deletes IS NULL OR spam_spike_min_deletes <= 0 OR spam_spike_min_deletes = 10"
                )
            )
    except Exception as e:
        log.warning("ensure_rules_spam_spike_columns skipped: %s", e)


async def ensure_admin_dispatch_bucket_unique(engine: AsyncEngine) -> None:
    """Уникальность bucket-рассылок, чтобы напоминания не дублировались между воркерами."""
    stmts = (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_dispatch_template_target_bucket "
        "ON admin_message_dispatch_logs (template_id, target_tg_id, event_bucket) "
        "WHERE event_bucket IS NOT NULL",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_admin_dispatch_bucket_unique skipped: %s", e)


async def ensure_app_settings_schema(engine: AsyncEngine) -> None:
    """KV-хранилище runtime-флагов приложения."""
    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR(64) PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_app_settings_schema skipped: %s", e)


async def ensure_join_captcha_schema(engine: AsyncEngine) -> None:
    """Капча при входе: колонки rules + таблица активных сессий."""
    rule_cols = (
        ("join_captcha_enabled", "BOOLEAN", "FALSE"),
        ("join_captcha_ttl_minutes", "INTEGER", "3"),
        ("join_captcha_kind", "VARCHAR(32)", "'button'"),
        ("join_captcha_prefer_dm", "BOOLEAN", "FALSE"),
    )
    for col_name, col_type, default in rule_cols:
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
        except Exception as e:
            log.warning("ensure_join_captcha_schema rules.%s: %s", col_name, e)

    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS join_captcha_sessions (
            id SERIAL PRIMARY KEY,
            token VARCHAR(20) NOT NULL UNIQUE,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            kind VARCHAR(32) NOT NULL,
            correct_idx INTEGER NOT NULL DEFAULT 0,
            options_json TEXT,
            message_chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_join_captcha_token ON join_captcha_sessions (token)",
        "CREATE INDEX IF NOT EXISTS ix_join_captcha_chat_id ON join_captcha_sessions (chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_join_captcha_chat_user ON join_captcha_sessions (chat_id, user_id)",
        "CREATE INDEX IF NOT EXISTS ix_join_captcha_expires_at ON join_captcha_sessions (expires_at)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_join_captcha_schema table skipped: %s", e)


async def ensure_chat_reputation_schema(engine: AsyncEngine) -> None:
    """Карма в группах: флаг в rules + таблицы слов, очков и событий."""
    rule_cols = (
        ("reputation_enabled", "BOOLEAN", "FALSE"),
    )
    for col_name, col_type, default in rule_cols:
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
        except Exception as e:
            log.warning("ensure_chat_reputation_schema rules.%s: %s", col_name, e)

    sql_blocks = (
        """
        CREATE TABLE IF NOT EXISTS chat_reputation_words (
            chat_id BIGINT NOT NULL,
            word VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (chat_id, word)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_reputation_scores (
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (chat_id, user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_reputation_events (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            from_user_id BIGINT NOT NULL,
            to_user_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_chat_reputation_words_chat ON chat_reputation_words (chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_reputation_scores_chat_score ON chat_reputation_scores (chat_id, score DESC)",
        "CREATE INDEX IF NOT EXISTS ix_chat_reputation_events_pair_time ON chat_reputation_events (chat_id, from_user_id, to_user_id, created_at DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_reputation_events_msg_pair ON chat_reputation_events (chat_id, message_id, from_user_id, to_user_id)",
    )
    try:
        async with engine.begin() as conn:
            for sql in sql_blocks:
                await conn.execute(text(sql))
    except Exception as e:
        log.warning("ensure_chat_reputation_schema table skipped: %s", e)


async def ensure_rules_post_rules_columns(engine: AsyncEngine) -> None:
    """Правила в комментарии канала и в группе: шаблоны + базовые опции."""
    statements = (
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_text TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_buttons_json TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_photo_path VARCHAR(512)",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_photo_file_id VARCHAR(512)",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_delete_window_sec INTEGER DEFAULT 0",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_autopost_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_channel_autopost_times_json TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_text TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_buttons_json TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_photo_path VARCHAR(512)",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_photo_file_id VARCHAR(512)",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_autopost_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_autopost_times_json TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_pin_on_send BOOLEAN DEFAULT TRUE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_delete_pin_notice BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_event_on_trigger BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_event_on_punish BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_event_trigger_every_n INTEGER DEFAULT 1",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_event_punish_every_n INTEGER DEFAULT 1",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_event_trigger_acc INTEGER DEFAULT 0",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_event_punish_acc INTEGER DEFAULT 0",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS rules_group_active_draft_id VARCHAR(128)",
    )
    try:
        async with engine.begin() as conn:
            for sql in statements:
                await conn.execute(text(sql))
        log.info("ensure_rules_post_rules_columns: ok")
    except Exception as e:
        log.warning("ensure_rules_post_rules_columns skipped: %s", e)


async def ensure_channel_rule_drafts_schema(engine: AsyncEngine) -> None:
    """Серверные черновики правил комментариев канала (синхронизация между устройствами)."""
    stmts = (
        """
        CREATE TABLE IF NOT EXISTS channel_rule_drafts (
            id SERIAL PRIMARY KEY,
            owner_user_id BIGINT NOT NULL,
            discussion_chat_id BIGINT NOT NULL,
            draft_id VARCHAR(96) NOT NULL,
            name VARCHAR(48) NOT NULL DEFAULT 'Черновик',
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            text_value TEXT NOT NULL DEFAULT '',
            delete_window_sec INTEGER NOT NULL DEFAULT 0,
            buttons_json TEXT NOT NULL DEFAULT '[]',
            manual_thread_id VARCHAR(64) NOT NULL DEFAULT '',
            photo_data_url TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at_ms BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_channel_rule_drafts_owner_chat_draft UNIQUE (owner_user_id, discussion_chat_id, draft_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_channel_rule_drafts_owner_chat ON channel_rule_drafts (owner_user_id, discussion_chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_channel_rule_drafts_updated ON channel_rule_drafts (updated_at_ms DESC)",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
        log.info("ensure_channel_rule_drafts_schema: ok")
    except Exception as e:
        log.warning("ensure_channel_rule_drafts_schema skipped: %s", e)


async def ensure_moderation_logs_detail_column(engine: AsyncEngine) -> None:
    """Backfill schema for moderation_logs.detail used by activity journal."""
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE moderation_logs ADD COLUMN IF NOT EXISTS detail VARCHAR(2000)")
            )
        log.info("ensure_moderation_logs_detail_column: ok")
    except Exception as e:
        log.warning("ensure_moderation_logs_detail_column skipped: %s", e)


async def ensure_user_post_rules_drafts_json_column(engine: AsyncEngine) -> None:
    """Черновики правил группы в Mini App — JSON на пользователя (синхронизация устройств)."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS post_rules_drafts_json TEXT"))
        log.info("ensure_user_post_rules_drafts_json_column: ok")
    except Exception as e:
        log.warning("ensure_user_post_rules_drafts_json_column skipped: %s", e)


async def ensure_users_delegate_broadcast_payer_column(engine: AsyncEngine) -> None:
    """Кто платит AURUM за рассылку делегата: owner | delegate | delegate_first."""
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS delegate_broadcast_payer "
                    "VARCHAR(24) NOT NULL DEFAULT 'delegate_first'"
                )
            )
        log.info("ensure_users_delegate_broadcast_payer_column: ok")
    except Exception as e:
        log.warning("ensure_users_delegate_broadcast_payer_column skipped: %s", e)


async def ensure_admin_incident_feed_schema(engine: AsyncEngine) -> None:
    """Журнал сбоев API для вкладки Guard Pulse (простым языком для владельца)."""
    stmts = (
        """
        CREATE TABLE IF NOT EXISTS admin_incident_feed (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            kind VARCHAR(32) NOT NULL DEFAULT 'http_error',
            method VARCHAR(16) NOT NULL DEFAULT '',
            path VARCHAR(512) NOT NULL DEFAULT '',
            status_code INTEGER NOT NULL DEFAULT 500,
            summary_ru TEXT NOT NULL DEFAULT '',
            detail_snippet VARCHAR(2000)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_admin_incident_feed_created_at ON admin_incident_feed (created_at DESC)",
        "ALTER TABLE admin_incident_feed ADD COLUMN IF NOT EXISTS severity VARCHAR(16) NOT NULL DEFAULT 'warn'",
        "ALTER TABLE admin_incident_feed ADD COLUMN IF NOT EXISTS category VARCHAR(64) NOT NULL DEFAULT 'api'",
        "ALTER TABLE admin_incident_feed ADD COLUMN IF NOT EXISTS affected_telegram_ids_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE admin_incident_feed ADD COLUMN IF NOT EXISTS affected_count INTEGER NOT NULL DEFAULT 0",
    )
    try:
        async with engine.begin() as conn:
            for sql in stmts:
                await conn.execute(text(sql))
        log.info("ensure_admin_incident_feed_schema: ok")
    except Exception as e:
        log.warning("ensure_admin_incident_feed_schema skipped: %s", e)
