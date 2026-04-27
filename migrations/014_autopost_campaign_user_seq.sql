-- Порядковый номер кампании у каждого admin_telegram_id (для отображения «Кампания 1» и т.д.).
ALTER TABLE autopost_campaigns ADD COLUMN IF NOT EXISTS user_seq INTEGER;

UPDATE autopost_campaigns c
SET user_seq = s.rn
FROM (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY admin_telegram_id ORDER BY id) AS rn
    FROM autopost_campaigns
) s
WHERE c.id = s.id AND c.user_seq IS NULL;
