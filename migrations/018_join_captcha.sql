-- Капча при входе: настройки в rules + таблица активных сессий
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_captcha_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_captcha_ttl_minutes INTEGER DEFAULT 3;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_captcha_kind VARCHAR(32) DEFAULT 'button';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_captcha_prefer_dm BOOLEAN DEFAULT FALSE;

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
);
CREATE INDEX IF NOT EXISTS ix_join_captcha_token ON join_captcha_sessions (token);
CREATE INDEX IF NOT EXISTS ix_join_captcha_chat_id ON join_captcha_sessions (chat_id);
CREATE INDEX IF NOT EXISTS ix_join_captcha_chat_user ON join_captcha_sessions (chat_id, user_id);
CREATE INDEX IF NOT EXISTS ix_join_captcha_expires_at ON join_captcha_sessions (expires_at);
