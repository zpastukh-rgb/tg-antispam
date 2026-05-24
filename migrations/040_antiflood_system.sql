-- Система «АнтиФлуд»: режим (строгий/мягкий), действие (бан/мут), учёт массовых сообщений
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_flood_mode VARCHAR(16) DEFAULT 'soft';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_flood_action VARCHAR(16) DEFAULT 'mute';

CREATE TABLE IF NOT EXISTS flood_rate_events (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_flood_rate_events_lookup
    ON flood_rate_events (chat_id, user_id, created_at DESC);
