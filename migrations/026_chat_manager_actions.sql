-- Фаза 3 «Админы чата»: журнал действий делегатов/владельца в чате
-- (activity-метрики + audit log). См. ChatManagerAction в models.py.
-- ensure_defaults.py создаёт это идемпотентно при старте; файл — на случай ручного применения.

CREATE TABLE IF NOT EXISTS chat_manager_actions (
    id              BIGSERIAL PRIMARY KEY,
    chat_id         BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL,
    action_kind     VARCHAR(64) NOT NULL,
    action_target   VARCHAR(128) NULL,
    action_meta     TEXT NULL,
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_chat_manager_actions_chat_id ON chat_manager_actions (chat_id);
CREATE INDEX IF NOT EXISTS ix_chat_manager_actions_user_id ON chat_manager_actions (user_id);
CREATE INDEX IF NOT EXISTS ix_chat_manager_actions_action_kind ON chat_manager_actions (action_kind);
CREATE INDEX IF NOT EXISTS ix_chat_manager_actions_created_at ON chat_manager_actions (created_at);
CREATE INDEX IF NOT EXISTS ix_chat_manager_actions_chat_created
  ON chat_manager_actions (chat_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_chat_manager_actions_chat_user_created
  ON chat_manager_actions (chat_id, user_id, created_at DESC);
