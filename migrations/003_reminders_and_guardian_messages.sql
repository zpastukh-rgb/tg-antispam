-- ТЗ Напоминания и сообщения Guardian: напоминания пользователю, Guardian-сообщения в группах
-- User: первое /start, этапы напоминаний, напоминание про чат отчётов
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_start_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_stage INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reports_reminder_sent_at TIMESTAMP WITH TIME ZONE;

-- Rule: Guardian сообщения (раз в 3 дня в группе), ограничение 72ч
ALTER TABLE rules ADD COLUMN IF NOT EXISTS guardian_messages_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS last_guardian_message_at TIMESTAMP WITH TIME ZONE;

-- Chat: активность для проверки «≥10 сообщений за сутки» (обновляется при модерации)
ALTER TABLE chats ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP WITH TIME ZONE;

-- ТЗ Автоматические отчёты: дайджест в чат отчётов раз в сутки
ALTER TABLE rules ADD COLUMN IF NOT EXISTS auto_reports_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS last_auto_report_at TIMESTAMP WITH TIME ZONE;
