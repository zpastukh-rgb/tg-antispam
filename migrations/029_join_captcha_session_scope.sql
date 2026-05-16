-- Разделение сценариев капчи: вход (join) и нарушение фильтра медиа (filter_media)
ALTER TABLE join_captcha_sessions ADD COLUMN IF NOT EXISTS captcha_scope VARCHAR(16) DEFAULT 'join';
