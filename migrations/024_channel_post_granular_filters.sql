-- Гранулярные тогглы для «Сообщения от каналов» (sender_chat / forward от каналов и групп).
-- См. ChatRule.filter_channel_post_* и moderation.matched_channel_post_kind().
-- ensure_defaults.py добавляет эти же колонки идемпотентно при старте; этот файл — на случай ручного применения.

ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_post_channels BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_post_groups BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_post_anon_admin BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_post_fwd_channel BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_post_fwd_group BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_post_no_username BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_channel_post_hidden_fwd BOOLEAN DEFAULT FALSE;
