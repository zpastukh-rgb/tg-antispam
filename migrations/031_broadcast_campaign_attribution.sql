-- Привязка запусков и кликов к автокампании (черновик может быть общим).
ALTER TABLE admin_broadcast_runs ADD COLUMN IF NOT EXISTS autopost_campaign_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_admin_broadcast_runs_autopost_campaign_id
    ON admin_broadcast_runs (autopost_campaign_id)
    WHERE autopost_campaign_id IS NOT NULL;

ALTER TABLE admin_broadcast_clicks ADD COLUMN IF NOT EXISTS autopost_campaign_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_admin_broadcast_clicks_autopost_campaign_id
    ON admin_broadcast_clicks (autopost_campaign_id)
    WHERE autopost_campaign_id IS NOT NULL;
