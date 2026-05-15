-- Гранулярные тогглы по типу медиа (фото/видео/стикеры/анимации/голос/кружки/аудио/custom emoji).
-- См. ChatRule.filter_media_* и moderation.py — отдельный verdict для каждого включённого типа.
-- ensure_defaults.py добавляет те же колонки идемпотентно при старте; этот файл — на случай ручного применения.

ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_photos BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_videos BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_stickers BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_animations BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_voice BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_video_notes BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_audio BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_custom_emoji BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_plain_emoji BOOLEAN DEFAULT FALSE;
