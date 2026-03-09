-- ТЗ доработка раздела «Защита»: капча на первое сообщение, фильтры (режимы ссылки/медиа/кнопки, капча по времени, вход, тишина, защита от спама)
ALTER TABLE rules ADD COLUMN IF NOT EXISTS first_message_captcha_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_links_mode VARCHAR(16) DEFAULT 'forbid';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_media_mode VARCHAR(16) DEFAULT 'allow';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_buttons_mode VARCHAR(16) DEFAULT 'allow';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS all_captcha_minutes INTEGER DEFAULT 0;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS delete_join_messages BOOLEAN DEFAULT TRUE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS silence_minutes INTEGER DEFAULT 0;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS master_anti_spam BOOLEAN DEFAULT TRUE;
