-- Гранулярные тогглы по типу кнопок (url/callback/web_app/switch_inline/login/pay/copy_text/reply/mass).
-- См. ChatRule.filter_button_* и moderation.matched_button_kind() — отдельный verdict для каждого включённого типа.
-- ensure_defaults.py добавляет эти же колонки идемпотентно при старте; этот файл — на случай ручного применения.

ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_url BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_callback BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_web_app BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_switch_inline BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_login BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_pay BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_copy_text BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_reply BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_mass_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_button_mass_threshold INTEGER DEFAULT 5;
