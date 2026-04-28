-- Реальные клики/переходы по ссылкам рассылки + охват аудитории (member_count).

ALTER TABLE admin_broadcast_runs
  ADD COLUMN IF NOT EXISTS audience_total INTEGER NOT NULL DEFAULT 0;

ALTER TABLE admin_broadcast_runs
  ADD COLUMN IF NOT EXISTS audience_ok INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS admin_broadcast_clicks (
  id SERIAL PRIMARY KEY,
  broadcast_id INTEGER NOT NULL REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
  target_kind VARCHAR(16) NOT NULL DEFAULT 'user',
  target_id BIGINT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_broadcast_id
  ON admin_broadcast_clicks (broadcast_id);

CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_target_kind
  ON admin_broadcast_clicks (target_kind);

CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_target_id
  ON admin_broadcast_clicks (target_id);

CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_created_at
  ON admin_broadcast_clicks (created_at);
