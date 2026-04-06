# app/texts/bot_intro.py
"""Текст приветствия /start и описания бота в профиле Telegram (BotFather / setMyDescription)."""

# Полный текст в ЛС при /start (до ~4096 символов у Telegram)
START_INTRO_TEXT = (
    "Привет! 👋\n\n"
    "Я - *AntiSpam Guard* 🛡️\n"
    "Я стою на защите твоей группы. Спамерам здесь не выжить.\n\n"
    "🔥 Что ты получаешь:\n"
    "• чистый чат без мусора, ссылок и рейдов\n"
    "• жёсткий фильтр схем, подработок, казино и ставок\n"
    "• сильные инструменты модерации в руках админа\n"
    "• простое управление прямо в мини-приложении Telegram\n\n"
    "⚡ Ты задаёшь правила - я исполняю без жалости к спаму.\n"
    "Большой функционал, понятные кнопки, быстрый контроль без рутины.\n\n"
    "🚀 Первый в мире Guard-формат: админ командует, спамеры исчезают."
)

# Профиль бота: не длиннее 512 символов (ограничение Telegram setMyDescription)
BOT_TELEGRAM_DESCRIPTION = (
    "🔥 Первый в мире AntiSpam Guard 🛡️\n"
    "Спамерам не выжить: режу ссылки, казино, мутные схемы и рейды.\n"
    "Управление через мини-приложение Telegram - быстро и удобно.\n\n"
    "Ты командуешь защитой, Guard держит порядок 24/7."
)

# Короткое описание в поиске / шапке: не длиннее 120 символов (setMyShortDescription)
BOT_TELEGRAM_SHORT_DESCRIPTION = (
    "AntiSpam Guard: первый в мире формат, где спамерам не выжить. Полный контроль в Mini App."
)

BOT_TELEGRAM_NAME = "AntiSpam Guard"

assert len(BOT_TELEGRAM_DESCRIPTION) <= 512, len(BOT_TELEGRAM_DESCRIPTION)
assert len(BOT_TELEGRAM_SHORT_DESCRIPTION) <= 120, len(BOT_TELEGRAM_SHORT_DESCRIPTION)
