-- Бесплатный тариф: лимит 3 группы (было 1)
-- Обновляем существующих пользователей с тарифом free и лимитом < 3
UPDATE users
SET chat_limit = 3
WHERE (tariff = 'free' OR tariff IS NULL)
  AND (chat_limit IS NULL OR chat_limit < 3);
