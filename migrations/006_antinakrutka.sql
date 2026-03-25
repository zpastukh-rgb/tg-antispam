-- Антинакрутка: оповещение и реакция на массовый вход в группу/чат комментариев
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_joins_threshold INTEGER DEFAULT 10;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_window_minutes INTEGER DEFAULT 5;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_action VARCHAR(32) DEFAULT 'alert';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_restrict_minutes INTEGER DEFAULT 30;
