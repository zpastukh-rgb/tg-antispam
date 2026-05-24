-- CAS (Combot Anti-Spam) + проверка массового входа по сети Guard
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_filter_cas BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_filter_network_mass_join BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_filter_network_join_threshold INTEGER DEFAULT 4;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_filter_network_join_window_minutes INTEGER DEFAULT 10;

CREATE TABLE IF NOT EXISTS network_join_events (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_network_join_events_user_joined
    ON network_join_events (user_id, joined_at DESC);
