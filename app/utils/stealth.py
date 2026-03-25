import asyncio
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


async def reply_stealth(message: Message, text: str, ttl: int = 12):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    sent = await message.answer(text)

    await asyncio.sleep(ttl)
    try:
        await sent.delete()
    except TelegramBadRequest:
        pass
