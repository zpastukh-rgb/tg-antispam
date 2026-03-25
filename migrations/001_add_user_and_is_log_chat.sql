-- Миграция: User, Payment, Chat.is_log_chat
-- Выполни если панель не открывается после обновления (таблица users / колонка is_log_chat отсутствуют).
-- PostgreSQL.

-- 1) Колонка is_log_chat в chats (если её ещё нет)
ALTER TABLE chats ADD COLUMN IF NOT EXISTS is_log_chat BOOLEAN DEFAULT FALSE;

-- 2) Таблица users (create_all создаёт при старте бота; если бот уже запускался до добавления модели — создай вручную)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    tariff VARCHAR(32) DEFAULT 'free',
    chat_limit INTEGER DEFAULT 1,
    subscription_until TIMESTAMP WITH TIME ZONE,
    is_admin BOOLEAN DEFAULT FALSE,
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users(telegram_id);

-- 3) Таблица payments (задел под оплату)
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(8) DEFAULT 'RUB',
    months INTEGER NOT NULL,
    tariff VARCHAR(32) NOT NULL,
    status VARCHAR(32) DEFAULT 'pending',
    provider VARCHAR(64),
    payment_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_payments_user_id ON payments(user_id);
