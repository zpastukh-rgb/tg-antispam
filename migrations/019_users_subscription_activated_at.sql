-- Первый платёж по подписке: для экрана «дата активации» (не путать с датой последнего теста/докупа).
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_activated_at TIMESTAMPTZ;

UPDATE users u
SET subscription_activated_at = s.first_paid
FROM (
  SELECT user_id, MIN(created_at) AS first_paid
  FROM payments
  WHERE status = 'succeeded' AND tariff = 'premium'
  GROUP BY user_id
) s
WHERE u.id = s.user_id AND u.subscription_activated_at IS NULL;
