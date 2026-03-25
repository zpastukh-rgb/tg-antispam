from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Проверить права (в группе)", callback_data="check_rights")
    kb.button(text="ℹ️ Как подключить", callback_data="how_to")
    kb.adjust(1)
    return kb.as_markup()