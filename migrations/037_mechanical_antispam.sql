-- Механический антиспам (сообщения без ссылок): apk, гостевые боты, подмена символов, текстовый спам, строгая правка
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_block_apk BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_guest_bots BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_symbol_subst BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_text_spam BOOLEAN DEFAULT FALSE;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS mech_filter_strict_edit BOOLEAN DEFAULT FALSE;
