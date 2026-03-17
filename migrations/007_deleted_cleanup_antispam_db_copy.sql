-- Очистка от удалённых: учёт участников чата
CREATE TABLE IF NOT EXISTS chat_seen_members (
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (chat_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_chat_seen_members_chat ON chat_seen_members(chat_id);

-- Антиспам база пользователей (общая для бота)
CREATE TABLE IF NOT EXISTS global_antispam_users (
    user_id BIGINT NOT NULL PRIMARY KEY,
    reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Правило: использовать глобальную антиспам базу при входе
ALTER TABLE rules ADD COLUMN IF NOT EXISTS use_global_antispam_db BOOLEAN DEFAULT FALSE;
