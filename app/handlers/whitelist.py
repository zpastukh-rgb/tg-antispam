# app/handlers/whitelist.py

from __future__ import annotations

import re
from urllib.parse import urlsplit

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType, ChatMemberStatus

from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Chat, WhitelistDomain, WhitelistUser
from app.db.session import get_session


router = Router()


# =========================================================
# UTILS
# =========================================================

DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")
_TRUSTED_PATH_RE = re.compile(r"^[a-z0-9./+:_-]{3,255}$")


def normalize_domain(value: str) -> str:
    """
    Приводим домен к нормальному виду.
    https://google.com/ → google.com
    """
    v = (value or "").strip().lower()

    v = v.replace("https://", "")
    v = v.replace("http://", "")
    v = v.replace("www.", "")

    v = v.split("/")[0]

    return v


def normalize_trusted_link_pattern(value: str) -> str:
    """
    Доверенная ссылка/фрагмент для whitelist: домен (vk.com) или путь (t.me/my_channel).
    """
    v = (value or "").strip().lower()
    if not v:
        return ""
    # Поддержка полного URL: https://site.com/path?x=1 -> site.com/path
    # и строки без схемы: site.com/path -> site.com/path
    parse_src = v if "://" in v else f"https://{v}"
    try:
        parts = urlsplit(parse_src)
        host = (parts.netloc or "").strip().lower()
        path = (parts.path or "").strip().lower()
    except Exception:
        host, path = "", ""
    if host:
        host = host.lstrip("@")
        if host.startswith("www."):
            host = host[4:]
        v = f"{host}{path or ''}"
    else:
        v = v.replace("https://", "").replace("http://", "").replace("www.", "")
    v = v.rstrip("/").strip()
    if not v or len(v) > 255:
        return ""
    if "/" in v or v.startswith("t.me+"):
        if not _TRUSTED_PATH_RE.match(v):
            return ""
        return v
    return normalize_domain(v)


def is_valid_trusted_pattern(value: str) -> bool:
    """Допустимая запись в доверенные ссылки (домен или t.me/… / t.me+invite)."""
    s = normalize_trusted_link_pattern(value)
    if not s:
        return False
    if "/" in s or s.startswith("t.me+"):
        return True
    return bool(DOMAIN_RE.match(s))


async def is_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )
    except Exception:
        return False


async def ensure_chat(session, chat_id: int) -> bool:
    chat = await session.get(Chat, chat_id)
    return chat is not None


# =========================================================
# HELP
# =========================================================

@router.message(Command("wl"))
async def wl_help(message: Message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    await message.reply(
        "😈 *Whitelist — исключения*\n\n"
        "Разрешить домен:\n"
        "`/wl_add google.com`\n\n"
        "Удалить домен:\n"
        "`/wl_del google.com`\n\n"
        "Список доменов:\n"
        "`/wl_list`\n\n"
        "Разрешить пользователя:\n"
        "`/wl_user_add @username`\n\n"
        "Удалить пользователя:\n"
        "`/wl_user_del @username`",
        parse_mode="Markdown",
    )


# =========================================================
# DOMAIN ADD
# =========================================================

@router.message(Command("wl_add"))
async def wl_add(message: Message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if not message.from_user:
        return

    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await message.reply("Пример: `/wl_add google.com`", parse_mode="Markdown")
        return

    raw_pat = parts[1]
    domain = normalize_trusted_link_pattern(raw_pat)

    if not is_valid_trusted_pattern(raw_pat):
        await message.reply("❌ Некорректная запись. Примеры: google.com или t.me/my_channel")
        return

    async with await get_session() as session:

        if not await ensure_chat(session, message.chat.id):
            await message.reply("Сначала подключи чат через `/check`")
            return

        session.add(
            WhitelistDomain(
                chat_id=message.chat.id,
                domain=domain,
            )
        )

        try:
            await session.commit()

        except SQLAlchemyError:
            await session.rollback()
            await message.reply(f"⚠️ Уже есть в whitelist: {domain}")
            return

    await message.reply(f"✅ Домен разрешён: `{domain}`", parse_mode="Markdown")


# =========================================================
# DOMAIN DELETE
# =========================================================

@router.message(Command("wl_del"))
async def wl_del(message: Message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if not message.from_user:
        return

    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await message.reply("Пример: `/wl_del google.com`", parse_mode="Markdown")
        return

    domain = normalize_trusted_link_pattern(parts[1])
    if not domain:
        await message.reply("❌ Укажи тот же фрагмент, что в списке (домен или t.me/…)")
        return

    async with await get_session() as session:

        await session.execute(
            delete(WhitelistDomain).where(
                WhitelistDomain.chat_id == message.chat.id,
                WhitelistDomain.domain == domain,
            )
        )

        await session.commit()

    await message.reply(f"🗑 Удалил из whitelist: `{domain}`", parse_mode="Markdown")


# =========================================================
# DOMAIN LIST
# =========================================================

@router.message(Command("wl_list"))
async def wl_list(message: Message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    async with await get_session() as session:

        res = await session.execute(
            select(WhitelistDomain.domain)
            .where(WhitelistDomain.chat_id == message.chat.id)
            .order_by(WhitelistDomain.domain.asc())
        )

        domains = [row[0] for row in res.all()]

    if not domains:
        await message.reply("Whitelist пуст.")
        return

    text = "🌐 *Whitelist домены*\n\n"

    for d in domains[:100]:
        text += f"• `{d}`\n"

    await message.reply(text, parse_mode="Markdown")


# =========================================================
# USER ADD
# =========================================================

@router.message(Command("wl_user_add"))
async def wl_user_add(message: Message):

    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if not message.from_user:
        return

    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        await message.reply("Ответь на сообщение пользователя.")
        return

    target = message.reply_to_message.from_user

    async with await get_session() as session:

        session.add(
            WhitelistUser(
                chat_id=message.chat.id,
                user_id=target.id,
            )
        )

        try:
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            await message.reply("⚠️ Уже в whitelist.")
            return

    await message.reply(f"✅ Пользователь разрешён: `{target.id}`", parse_mode="Markdown")


# =========================================================
# USER DELETE
# =========================================================

@router.message(Command("wl_user_del"))
async def wl_user_del(message: Message):

    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if not message.from_user:
        return

    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        await message.reply("Ответь на сообщение пользователя.")
        return

    target = message.reply_to_message.from_user

    async with await get_session() as session:

        await session.execute(
            delete(WhitelistUser).where(
                WhitelistUser.chat_id == message.chat.id,
                WhitelistUser.user_id == target.id,
            )
        )

        await session.commit()

    await message.reply(f"🗑 Удалён из whitelist: `{target.id}`", parse_mode="Markdown")
