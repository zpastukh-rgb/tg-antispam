-- Промокоды: одна активация на пользователя (не одна на весь код).
-- Запуск: python -m scripts.run_migration 010

CREATE TABLE IF NOT EXISTS promo_code_redemptions (
    id SERIAL PRIMARY KEY,
    promo_code_id INTEGER NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
    telegram_user_id BIGINT NOT NULL,
    redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_promo_code_user UNIQUE (promo_code_id, telegram_user_id)
);

CREATE INDEX IF NOT EXISTS idx_promo_redemptions_promo ON promo_code_redemptions(promo_code_id);
CREATE INDEX IF NOT EXISTS idx_promo_redemptions_user ON promo_code_redemptions(telegram_user_id);

-- Уже «использованные» глобально коды: переносим в per-user, чтобы тот пользователь не активировал повторно.
INSERT INTO promo_code_redemptions (promo_code_id, telegram_user_id, redeemed_at)
SELECT id, used_by_user_id, COALESCE(used_at, NOW())
FROM promo_codes
WHERE used_by_user_id IS NOT NULL
ON CONFLICT (promo_code_id, telegram_user_id) DO NOTHING;
