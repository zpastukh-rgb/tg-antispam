from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import delete, select

from app.db.session import get_session
from app.db.models import Chat, StopWord

from app.utils.admins import is_admin
from app.utils.stealth import reply_stealth

router = Router()


def norm_word(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("ё", "е")
    return s


@router.message(Command("words"))
async def cmd_words(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Команда /words работает только в группе 🙂")
        return

    # только админы/владелец
    if not await is_admin(message):
        return

    async with await get_session() as session:
        chat = await session.get(Chat, message.chat.id)
        if not chat or not getattr(chat, "is_active", True):
            await reply_stealth(message, "Сначала сделай /check в этой группе.")
            return

        res = await session.execute(
            select(StopWord.word)
            .where(StopWord.chat_id == message.chat.id)
            .order_by(StopWord.word.asc())
        )
        words = [row[0] for row in res.all()]

    if not words:
        await reply_stealth(
            message,
            "📌 Стоп-слова пустые.\n\n"
            "➕ Добавить: /addword казино\n"
            "➕ Списком: /addword казино, ставки, реклама\n"
            "➖ Удалить: /delword казино\n"
            "📋 Список: /words"
        )
        return

    text = "📋 Стоп-слова:\n" + "\n".join(f"• {w}" for w in words[:200])
    if len(words) > 200:
        text += f"\n…и ещё {len(words) - 200}"

    text += "\n\n➕ /addword слово или список через запятую\n➖ /delword слово"
    await reply_stealth(message, text)


@router.message(Command("addword"))
async def cmd_addword(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Команда /addword работает только в группе 🙂")
        return

    # только админы/владелец
    if not await is_admin(message):
        return

    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await reply_stealth(
            message,
            "Напиши так:\n"
            "/addword казино\n"
            "или\n"
            "/addword казино, ставки, реклама"
        )
        return

    # делим по запятой или пробелу
    words_raw = raw[1].replace(",", " ").split()
    words = [norm_word(w) for w in words_raw if norm_word(w)]

    if not words:
        await reply_stealth(message, "Нет слов для добавления 🙂")
        return

    added = []

    async with await get_session() as session:
        chat = await session.get(Chat, message.chat.id)
        if not chat or not getattr(chat, "is_active", True):
            await reply_stealth(message, "Сначала сделай /check в этой группе.")
            return

        for word in words:
            exists = await session.execute(
                select(StopWord).where(
                    StopWord.chat_id == message.chat.id,
                    StopWord.word == word
                ).limit(1)
            )
            if not exists.scalar_one_or_none():
                session.add(StopWord(chat_id=message.chat.id, word=word))
                added.append(word)

        await session.commit()

    if added:
        await reply_stealth(message, "✅ Добавил:\n" + "\n".join(f"• {w}" for w in added))
    else:
        await reply_stealth(message, "Все эти слова уже были в списке 🙂")

@router.message(Command("delword"))
async def cmd_delword(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Команда /delword работает только в группе 🙂")
        return

    # только админы/владелец
    if not await is_admin(message):
        return

    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await reply_stealth(
            message,
            "Напиши так:\n"
            "/delword казино\n"
            "или\n"
            "/delword казино, ставки, реклама"
        )
        return

    # делим по запятой или пробелу
    words_raw = raw[1].replace(",", " ").split()
    words = [norm_word(w) for w in words_raw if norm_word(w)]

    if not words:
        await reply_stealth(message, "Нет слов для удаления 🙂")
        return

    async with await get_session() as session:
        chat = await session.get(Chat, message.chat.id)
        if not chat or not getattr(chat, "is_active", True):
            await reply_stealth(message, "Сначала сделай /check в этой группе.")
            return

        deleted_any = 0
        for word in words:
            res = await session.execute(
                delete(StopWord).where(
                    StopWord.chat_id == message.chat.id,
                    StopWord.word == word
                )
            )
            # res.rowcount может быть None в некоторых драйверах, поэтому считаем грубо:
            deleted_any += 1

        await session.commit()

    await reply_stealth(
        message,
        "✅ Готово. Удалил (если было):\n" + "\n".join(f"• {w}" for w in words) + "\n\nСписок: /words"
    )
