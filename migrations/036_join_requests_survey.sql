-- Режимы работы с заявками на вступление (опрос в ЛС, отчёты админам)
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_requests_mode VARCHAR(24) DEFAULT 'off';
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_requests_welcome_text TEXT DEFAULT NULL;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_requests_done_text TEXT DEFAULT NULL;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_requests_questions_text TEXT DEFAULT NULL;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS join_requests_report_mode VARCHAR(16) DEFAULT 'full';

-- Миграция legacy: auto_approve -> mode auto
UPDATE rules SET join_requests_mode = 'auto'
WHERE COALESCE(auto_approve_join_requests, FALSE) = TRUE
  AND COALESCE(join_requests_mode, 'off') = 'off';

CREATE TABLE IF NOT EXISTS join_request_survey_sessions (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    question_index INTEGER NOT NULL DEFAULT 0,
    answers_json TEXT DEFAULT '[]',
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_join_request_survey_chat_user
    ON join_request_survey_sessions (chat_id, user_id);
