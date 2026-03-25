from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ChatMemberStatus


async def is_admin(message: Message) -> bool:
    """
    True если пользователь админ/владелец в текущей группе.
    """
    if not message.from_user:
        return False
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR)
    except TelegramBadRequest:
        return False
