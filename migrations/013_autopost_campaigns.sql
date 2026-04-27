-- Независимые кампании автопоста (дублирует ensure_autopost_campaigns_schema на API-старте).
-- PostgreSQL.

CREATE TABLE IF NOT EXISTS autopost_campaigns (
    id SERIAL PRIMARY KEY,
    admin_telegram_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    anchor_broadcast_id INTEGER,
    autopost_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_autopost_campaigns_admin_telegram_id ON autopost_campaigns (admin_telegram_id);
CREATE INDEX IF NOT EXISTS ix_autopost_campaigns_anchor_broadcast_id ON autopost_campaigns (anchor_broadcast_id);
