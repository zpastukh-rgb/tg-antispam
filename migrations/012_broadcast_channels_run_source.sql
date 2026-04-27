-- Каналы как отдельные цели рассылки (chat_kind) + пометка запусков автопоста (run_source).
-- python -m scripts.run_migration 012

ALTER TABLE chats ADD COLUMN IF NOT EXISTS chat_kind VARCHAR(16) DEFAULT 'group';
UPDATE chats SET chat_kind = 'group' WHERE chat_kind IS NULL;

ALTER TABLE admin_broadcast_runs ADD COLUMN IF NOT EXISTS run_source VARCHAR(16);
UPDATE admin_broadcast_runs SET run_source = 'manual' WHERE run_source IS NULL;
