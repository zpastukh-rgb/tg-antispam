-- Запрет пересылок и цитирования извне
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_forward_block_channels BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_forward_block_chats BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_forward_block_bots BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_forward_block_users BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_forward_block_with_links BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_forward_block_stories BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS filter_forward_block_with_button BOOLEAN DEFAULT FALSE;
