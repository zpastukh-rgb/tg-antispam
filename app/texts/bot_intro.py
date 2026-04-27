# app/texts/bot_intro.py
"""Текст приветствия /start и описания бота в профиле Telegram.

Картинка в карточке «Что умеет этот бот?» до кнопки «Начать» — это не сообщение из кода: её задаёт
@BotFather → /mybots → твой бот → Edit Bot → Edit Description Picture (фото, рекомендуемо 640×360).
Файл-образец в репозитории: static/welcome_banner.jpg. Текст ниже синхронизируется через setMyDescription
при старте бота (языки в app/main._sync_bot_profile).
"""

from pathlib import Path

_STATIC_ROOT = Path(__file__).resolve().parent.parent.parent / "static"
# Тот же файл можно загрузить в BotFather как Description Picture (см. модульный docstring выше).
WELCOME_BANNER_PATH = _STATIC_ROOT / "welcome_banner.jpg"
WELCOME_BANNER_CAPTION = "Служба заботы: @Help_guard"

# Полный текст в ЛС при /start (до ~4096 символов у Telegram)
START_INTRO_TEXT = (
    "Привет 👋\n\n"
    "Я [AntiSpam Guard](https://t.me/GuardAntiSpam_Bot) 🛡️\n\n"
    "Я держу порядок в группе\n"
    "Режу спам, ссылки, рейды, мутные схемы и лишний шум\n\n"
    "В Guard доступны\n"
    "Языки\n"
    "Донаты\n"
    "Реферальная программа\n"
    "Баланс счёта\n\n"
    "Инструкция находится в приложении под знаком *i*\n\n"
    "Служба заботы @Help_guard"
)

# Профиль бота: не длиннее 512 символов (ограничение Telegram setMyDescription)
BOT_TELEGRAM_DESCRIPTION = (
    "🔥 AntiSpam Guard — первый в мире формат серьёзной защиты чатов.\n\n"
    "Спам, ссылки, казино, скам, рейды, мутные схемы — режу и держу порядок.\n\n"
    "Гибкие настройки под любой тип группы: стоп-слова, антинакрутка, новички, жёсткий словарь, "
    "антиспам-база, отчёты админу — всё в Mini App, без рутины с командами.\n\n"
    "Добавь бота админом, нажми «Меню» и выставь правила под свой чат за минуты.\n\n"
    "Служба заботы: @Help_guard"
)

# Короткое описание в поиске / шапке: не длиннее 120 символов (setMyShortDescription)
BOT_TELEGRAM_SHORT_DESCRIPTION = (
    "Первый в мире AntiSpam Guard: гибкая защита группы в Mini App. @Help_guard"
)

BOT_TELEGRAM_NAME = "AntiSpam Guard"

assert len(BOT_TELEGRAM_DESCRIPTION) <= 512, len(BOT_TELEGRAM_DESCRIPTION)
assert len(BOT_TELEGRAM_SHORT_DESCRIPTION) <= 120, len(BOT_TELEGRAM_SHORT_DESCRIPTION)
