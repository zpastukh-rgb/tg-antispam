-- Фильтр мата: таблица слов + колонка в rules. Промокоды для Premium.
-- Запуск: python -m scripts.run_migration 009

-- Общая таблица матерных слов
CREATE TABLE IF NOT EXISTS profanity_words (
    word VARCHAR(64) NOT NULL PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Включение фильтра мата в настройках чата
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_profanity_enabled BOOLEAN DEFAULT FALSE;

-- Промокоды (Premium, пробный период)
CREATE TABLE IF NOT EXISTS promo_codes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    tariff VARCHAR(32) DEFAULT 'premium',
    days INTEGER DEFAULT 0,
    used_at TIMESTAMP WITH TIME ZONE,
    used_by_user_id BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code);
