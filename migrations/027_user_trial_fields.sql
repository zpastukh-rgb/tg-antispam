-- Этап 1 Premium-функционала: новые поля пользователя для 10-дневного триала.
-- Окно активации = 10 дней с first_start_at, после активации Premium на 10 дней
-- с момента активации. trial_reminder_last_day_sent — отслеживание дедупа DM.
-- ensure_defaults.py применит это идемпотентно; файл — на случай ручного применения.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS trial_used                     BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS trial_activated_at             TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS trial_reminder_last_day_sent   INTEGER     NOT NULL DEFAULT 0;

-- Бэкфилл: пользователи, у которых уже был «автотриал» через первый /start
-- (subscription_source='trial' и/или сейчас активный trial-Premium) — помечаем
-- их как уже использовавших триал, чтобы они не получили его повторно.
UPDATE users
SET    trial_used = TRUE,
       trial_activated_at = COALESCE(trial_activated_at, first_start_at)
WHERE  trial_used = FALSE
  AND  (subscription_source = 'trial'
        OR (subscription_until IS NOT NULL
            AND subscription_until > NOW()
            AND tariff IN ('premium','pro','business')
            AND subscription_source IS NULL));
