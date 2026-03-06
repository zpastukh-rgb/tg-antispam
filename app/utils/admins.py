from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


async def is_admin(message: Message) -> bool:
    """
    True если пользователь админ/владелец в текущей группе.
    """
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("creator", "administrator")
    except TelegramBadRequest:
        return False
