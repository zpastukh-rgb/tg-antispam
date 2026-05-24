-- Флуд (повторы одного текста) + индивидуальные наказания по фильтрам
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_flood_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_flood_threshold INTEGER DEFAULT 3;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_flood_window_minutes INTEGER DEFAULT 5;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_actions_json TEXT DEFAULT NULL;

CREATE TABLE IF NOT EXISTS flood_text_events (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    text_norm_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_flood_text_events_lookup
    ON flood_text_events (chat_id, user_id, text_norm_hash, created_at DESC);
