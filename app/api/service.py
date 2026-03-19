# app/api/service.py
"""Данные для API: чаты, правила, пользователь (без привязки к боту)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone, timedelta

from app.db.models import Chat, Rule, UserContext, ChatManager, StopWord, ProfanityWord, PromoCode, User
from app.services.user_service import get_or_create_user, can_add_chat, TARIFF_CHAT_LIMITS


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


def _norm_profanity(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    return s[:64]


async def list_profanity(session: AsyncSession, limit: int = 500) -> list[dict]:
    """Список матерных слов (глобальная таблица)."""
    res = await session.execute(
        select(ProfanityWord.word).order_by(ProfanityWord.word.asc()).limit(limit)
    )
    return [{"word": row[0]} for row in res.all()]


async def add_profanity(session: AsyncSession, word: str) -> bool:
    """Добавить слово в таблицу мата. Возвращает True если добавлено."""
    w = _norm_profanity(word)
    if not w:
        return False
    existing = await session.get(ProfanityWord, w)
    if existing:
        return False
    session.add(ProfanityWord(word=w))
    await session.commit()
    return True


async def remove_profanity(session: AsyncSession, word: str) -> bool:
    """Удалить слово из таблицы мата. Возвращает True если удалено."""
    w = _norm_profanity(word)
    if not w:
        return False
    row = await session.get(ProfanityWord, w)
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def apply_promo_code(session: AsyncSession, user_id: int, code: str) -> tuple[bool, str]:
    """
    Активировать промокод для пользователя.
    Returns: (success, message).
    """
    from sqlalchemy import select
    code_clean = (code or "").strip().upper()
    if not code_clean:
        return False, "Введите промокод"
    res = await session.execute(select(PromoCode).where(PromoCode.code == code_clean).limit(1))
    promo = res.scalar_one_or_none()
    if not promo:
        return False, "Промокод не найден"
    if promo.used_at is not None:
        return False, "Промокод уже использован"
    res_user = await session.execute(select(User).where(User.telegram_id == user_id).limit(1))
    user = res_user.scalar_one_or_none()
    if not user:
        return False, "Пользователь не найден"
    user.tariff = promo.tariff or "premium"
    if promo.days and promo.days > 0:
        user.subscription_until = datetime.now(timezone.utc) + timedelta(days=promo.days)
    else:
        user.subscription_until = None  # бессрочно
    user.chat_limit = TARIFF_CHAT_LIMITS.get(user.tariff, 20)
    promo.used_at = datetime.now(timezone.utc)
    promo.used_by_user_id = user_id
    await session.commit()
    days_msg = f" на {promo.days} дн." if promo.days else ""
    return True, f"Premium активирован{days_msg}"


async def copy_rule_to_chat(session: AsyncSession, source_chat_id: int, target_chat_id: int) -> Rule:
    """Перенести настройки (Rule) из source_chat_id в target_chat_id. Возвращает правило целевого чата."""
    source = await session.get(Rule, source_chat_id)
    if not source:
        raise ValueError("Source chat has no rule")
    target = await get_or_create_rule(session, target_chat_id)
    # Копируем все поля кроме chat_id и created_at
    skip = {"chat_id", "created_at"}
    for col in Rule.__table__.columns:
        if col.name in skip:
            continue
        setattr(target, col.name, getattr(source, col.name))
    await session.commit()
    await session.refresh(target)
    return target
