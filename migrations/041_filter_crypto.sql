-- Антикрипт в жёстком словаре
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_crypto_enabled BOOLEAN DEFAULT FALSE;
