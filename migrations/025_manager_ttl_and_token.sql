-- Фаза 2 «Админы чата»: TTL делегата + TTL приглашения + токен ссылки.
-- См. ChatManager.expires_at, ChatManagerInvite.expires_at/token.
-- ensure_defaults.py добавляет это идемпотентно при старте; файл — на случай ручного применения.

ALTER TABLE chat_managers ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL;
ALTER TABLE chat_manager_invites ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL;
ALTER TABLE chat_manager_invites ADD COLUMN IF NOT EXISTS token VARCHAR(64) NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_manager_invites_token
  ON chat_manager_invites (token)
  WHERE token IS NOT NULL;
