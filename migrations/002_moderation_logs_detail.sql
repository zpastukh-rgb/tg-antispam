-- Триггер срабатывания для отчётов Mini App (стоп-слово, ссылка и т.д.).
-- Выполните один раз на существующей БД. Если колонка уже есть — пропустите ошибку «duplicate column».

ALTER TABLE moderation_logs ADD COLUMN detail VARCHAR(2000);
