-- Капча при нарушении правил медиа (отдельно от join_captcha при входе)
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_captcha_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_captcha_ttl_minutes INTEGER DEFAULT 3;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_captcha_kind VARCHAR(32) DEFAULT 'button';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_captcha_prefer_dm BOOLEAN DEFAULT FALSE;
