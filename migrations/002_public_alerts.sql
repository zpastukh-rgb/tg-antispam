-- Публичные сообщения Guardian раз в N удалений (ТЗ ПРАВКИ 2)
ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_every_n INTEGER DEFAULT 5;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_min_interval_sec INTEGER DEFAULT 300;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS public_alerts_last_sent_at TIMESTAMP WITH TIME ZONE;
