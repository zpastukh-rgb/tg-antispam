-- Гранулярные тогглы по типу упоминаний (юзеры/боты/каналы/text_mention/hashtags/bot_commands/cashtags/emails/mass).
-- См. ChatRule.filter_mention_* и moderation.matched_mention_kind() — отдельный verdict для каждого включённого типа.
-- ensure_defaults.py добавляет эти же колонки идемпотентно при старте; этот файл — на случай ручного применения.

ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_users BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_bots BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_channels BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_text_mention BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_hashtags BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_bot_commands BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_cashtags BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_emails BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_mass_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_mention_mass_threshold INTEGER DEFAULT 5;
