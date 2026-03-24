ALTER TABLE global_antispam_users ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);
ALTER TABLE global_antispam_users ADD COLUMN IF NOT EXISTS username VARCHAR(64);
-- Имя и username для отображения в антиспам-базе (UI)
