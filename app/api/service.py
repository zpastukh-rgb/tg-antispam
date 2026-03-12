# app/api/service.py
"""Данные для API: чаты, правила, пользователь (без привязки к боту)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, Rule, UserContext, ChatManager, StopWord
from app.services.user_service import get_or_create_user, can_add_chat


async def get_managed_chats(session: AsyncSession, user_id: int) -> list[Chat]:
    """Защищаемые чаты пользователя (владелец или менеджер)."""
    sub = select(ChatManager.chat_id).where(ChatManager.user_id == user_id).subquery()
    res = await session.execute(
        select(Chat)
        .where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            (Chat.owner_user_id == user_id) | (Chat.id.in_(select(sub.c.chat_id))),
        )
        .order_by(Chat.id.asc())
    )
    return list(res.scalars().all())


async def get_pending_chats(session: AsyncSession, user_id: int) -> list[Chat]:
    """Чаты, куда пользователь добавил бота, но ещё не подключил (is_active=False)."""
    res = await session.execute(
        select(Chat)
        .where(
            Chat.owner_user_id == user_id,
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == False,  # noqa: E712
        )
        .order_by(Chat.id.desc())
    )
    return list(res.scalars().all())


async def get_or_create_rule(session: AsyncSession, chat_id: int) -> Rule:
    """Правило для чата (создаёт запись при отсутствии)."""
    rule = await session.get(Rule, chat_id)
    if rule:
        return rule
    rule = Rule(chat_id=chat_id)
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def get_selected_chat_id(session: AsyncSession, user_id: int) -> int | None:
    """Выбранный чат пользователя (UserContext)."""
    ctx = await session.get(UserContext, user_id)
    return int(ctx.selected_chat_id) if ctx and ctx.selected_chat_id else None


async def set_selected_chat(session: AsyncSession, user_id: int, chat_id: int | None) -> None:
    """Установить выбранный чат."""
    ctx = await session.get(UserContext, user_id)
    if not ctx:
        ctx = UserContext(user_id=user_id, selected_chat_id=chat_id)
        session.add(ctx)
    else:
        ctx.selected_chat_id = chat_id
    await session.commit()


async def user_can_access_chat(session: AsyncSession, user_id: int, chat_id: int) -> bool:
    """Проверка: пользователь владелец или менеджер чата."""
    chats = await get_managed_chats(session, user_id)
    return any(c.id == chat_id for c in chats)


def _norm_stopword(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    return s[:64]  # модель: String(64)


async def count_stopwords(session: AsyncSession, chat_id: int) -> int:
    """Количество стоп-слов чата."""
    from sqlalchemy import func
    r = await session.execute(select(func.count()).select_from(StopWord).where(StopWord.chat_id == chat_id))
    return r.scalar() or 0


async def list_stopwords(session: AsyncSession, chat_id: int) -> list[str]:
    """Список стоп-слов чата (отсортированы)."""
    res = await session.execute(
        select(StopWord.word).where(StopWord.chat_id == chat_id).order_by(StopWord.word.asc())
    )
    return [row[0] for row in res.all()]


async def add_stopword(session: AsyncSession, chat_id: int, word: str) -> bool:
    """Добавить стоп-слово. Возвращает True если добавлено, False если уже было."""
    w = _norm_stopword(word)
    if not w:
        return False
    exists = await session.execute(
        select(StopWord).where(StopWord.chat_id == chat_id, StopWord.word == w).limit(1)
    )
    if exists.scalar_one_or_none():
        return False
    session.add(StopWord(chat_id=chat_id, word=w))
    await session.commit()
    return True


async def delete_stopword(session: AsyncSession, chat_id: int, word: str) -> bool:
    """Удалить стоп-слово. Возвращает True если удалено."""
    from sqlalchemy import delete as sql_delete
    w = _norm_stopword(word)
    if not w:
        return False
    await session.execute(sql_delete(StopWord).where(StopWord.chat_id == chat_id, StopWord.word == w))
    await session.commit()
    return True
