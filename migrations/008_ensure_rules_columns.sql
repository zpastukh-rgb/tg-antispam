-- Восстановление схемы: все колонки rules и таблицы из 006/007.
-- Если 006 и 007 уже применялись, команды с IF NOT EXISTS ничего не сломают.
-- Запуск: python -m scripts.run_migration 008  (или railway run python -m scripts.run_migration 008)

-- rules: антинакрутка (006)
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_joins_threshold INTEGER DEFAULT 10;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_window_minutes INTEGER DEFAULT 5;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_action VARCHAR(32) DEFAULT 'alert';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_restrict_minutes INTEGER DEFAULT 30;

-- rules: глобальная антиспам-база (007)
ALTER TABLE rules ADD COLUMN IF NOT EXISTS use_global_antispam_db BOOLEAN DEFAULT FALSE;

-- Таблицы из 007
CREATE TABLE IF NOT EXISTS chat_seen_members (
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (chat_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_chat_seen_members_chat ON chat_seen_members(chat_id);

CREATE TABLE IF NOT EXISTS global_antispam_users (
    user_id BIGINT NOT NULL PRIMARY KEY,
    reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
