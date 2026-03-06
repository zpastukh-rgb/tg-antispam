from aiogram.utils.keyboard import InlineKeyboardBuilder

CB_UNBAN = "log:unban"
CB_UNMUTE = "log:unmute"


def make_log_kb(mode: str, chat_id: int, user_id: int):
    b = InlineKeyboardBuilder()

    if mode == "ban":
        b.button(
            text="✅ Разбанить",
            callback_data=f"{CB_UNBAN}:{chat_id}:{user_id}"
        )

    if mode == "mute":
        b.button(
            text="🔊 Размутить",
            callback_data=f"{CB_UNMUTE}:{chat_id}:{user_id}"
        )

    b.adjust(2)
    return b.as_markup()
