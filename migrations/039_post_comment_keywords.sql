-- Автоудаление комментариев к постам канала по ключевым словам (Premium)
ALTER TABLE rules ADD COLUMN IF NOT EXISTS post_comment_keywords_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS post_comment_keywords_json TEXT DEFAULT NULL;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS post_comment_keywords_action VARCHAR(16) DEFAULT 'delete';
