from __future__ import annotations

import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import delete, select

from app.db.session import get_session
from app.db.models import Chat, StopWord

from app.utils.admins import is_admin
from app.utils.stealth import reply_stealth

router = Router()


STOP_WORD_MAX_LEN = 64


def norm_word(s: str) -> str:
    """Одна запись стоп-слова/фразы: как в API (_norm_stopword), длина ограничена полем БД."""
    s = (s or "").strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:STOP_WORD_MAX_LEN]


def split_stopword_cli_arg(arg: str) -> list[str]:
    """
    Несколько стоп-записей — только через запятую.
    Без запятой вся строка — одна фраза (в т.ч. с пробелами), а не набор слов по пробелам.
    """
    raw = (arg or "").strip()
    if not raw:
        return []
    if "," in raw:
        parts = raw.split(",")
    else:
        parts = [raw]
    out: list[str] = []
    for p in parts:
        w = norm_word(p)
        if w:
            out.append(w)
    return out


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
            "➕ Одно слово или фраза: /addword казино или /addword не звоните мне\n"
            "➕ Несколько записей через запятую: /addword казино, ставки, не звоните мне\n"
            "➖ Удалить: /delword казино\n"
            "📋 Список: /words"
        )
        return

    text = "📋 Стоп-слова:\n" + "\n".join(f"• {w}" for w in words[:200])
    if len(words) > 200:
        text += f"\n…и ещё {len(words) - 200}"

    text += "\n\n➕ /addword слово, фраза с пробелами или несколько через запятую\n➖ /delword — так же"
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
            "/addword не звоните мне\n"
            "или несколько через запятую:\n"
            "/addword казино, ставки, не звоните мне"
        )
        return

    words = split_stopword_cli_arg(raw[1])

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

    try:
        from app.handlers.moderation import invalidate_stopwords_cache

        invalidate_stopwords_cache(int(message.chat.id))
    except Exception:
        pass

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
            "/delword не звоните мне\n"
            "или несколько через запятую:\n"
            "/delword казино, ставки, не звоните мне"
        )
        return

    words = split_stopword_cli_arg(raw[1])

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

    try:
        from app.handlers.moderation import invalidate_stopwords_cache

        invalidate_stopwords_cache(int(message.chat.id))
    except Exception:
        pass

    await reply_stealth(
        message,
        "✅ Готово. Удалил (если было):\n" + "\n".join(f"• {w}" for w in words) + "\n\nСписок: /words"
    )
