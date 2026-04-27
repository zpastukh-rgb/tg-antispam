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
);

CREATE INDEX IF NOT EXISTS ix_chat_spike_alerts_chat_id ON chat_spike_alerts (chat_id);
CREATE INDEX IF NOT EXISTS ix_chat_spike_alerts_expires_at ON chat_spike_alerts (expires_at);
CREATE INDEX IF NOT EXISTS ix_chat_spike_alerts_last_triggered_at ON chat_spike_alerts (last_triggered_at);
