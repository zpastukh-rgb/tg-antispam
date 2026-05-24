-- Антинакрутка / антирейд: режим обороны и расширенные действия
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_lockdown_minutes INTEGER DEFAULT 0;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_pause_welcomes BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_force_captcha BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_cooldown_minutes INTEGER DEFAULT 5;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS antinakrutka_auto_silence_minutes INTEGER DEFAULT 0;
