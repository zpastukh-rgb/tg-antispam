-- Уникальность (chat_id, message_id) для учёта реакций на рассылку.
-- ensure_defaults уже создаёт UNIQUE INDEX ux_admin_broadcast_sent_messages_chat_msg.
-- Приложение использует ON CONFLICT (chat_id, message_id), совместимо с индексом и constraint.

CREATE TABLE IF NOT EXISTS admin_broadcast_sent_messages (
  id SERIAL PRIMARY KEY,
  broadcast_id INTEGER NOT NULL REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
  chat_id BIGINT NOT NULL,
  message_id BIGINT NOT NULL,
  target_kind VARCHAR(16) NOT NULL DEFAULT 'group',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_admin_broadcast_sent_messages_chat_msg
  ON admin_broadcast_sent_messages (chat_id, message_id);

CREATE INDEX IF NOT EXISTS ix_admin_broadcast_sent_messages_broadcast_id
  ON admin_broadcast_sent_messages (broadcast_id);
