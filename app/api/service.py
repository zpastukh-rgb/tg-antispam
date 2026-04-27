# app/api/service.py
"""Данные для API: чаты, правила, пользователь (без привязки к боту)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chat,
    Rule,
    UserContext,
    ChatManager,
    ChatManagerInvite,
    StopWord,
    ProfanityWord,
    PromoCode,
    PromoCodeRedemption,
    User,
    CreditLedger,
)

from app.db.ensure_defaults import (
    get_owner_forever_chat_limit,
    get_owner_forever_promo_code,
    get_repeatable_tokens2000_promo_code,
)
from app.services.user_service import (
    get_or_create_user,
    can_add_chat,
    TARIFF_CHAT_LIMITS,
    TARIFF_GROUP_LIMITS,
    TARIFF_CHANNEL_LIMITS,
)


async def get_managed_chats(session: AsyncSession, user_id: int) -> list[Chat]:
    """Защищаемые чаты пользователя (владелец или менеджер)."""
    manager_sub = select(ChatManager.chat_id).where(ChatManager.user_id == user_id)
    invite_sub = select(ChatManagerInvite.chat_id).where(
        ChatManagerInvite.status == "connected",
        (ChatManagerInvite.connected_user_id == user_id) | (ChatManagerInvite.target_telegram_id == user_id),
    )
    managed_sub = manager_sub.union(invite_sub).subquery()
    res = await session.execute(
        select(Chat)
        .where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            (Chat.owner_user_id == user_id) | (Chat.id.in_(select(managed_sub.c.chat_id))),
        )
        .order_by(Chat.id.asc())
    )
    return list(res.scalars().all())


async def get_pending_chats(session: AsyncSession, user_id: int) -> list[Chat]:
    """Чаты, куда пользователь добавил бота, но ещё не подключил (is_active=False)."""
    log_targets = select(Chat.log_chat_id).where(Chat.log_chat_id.is_not(None))
    res = await session.execute(
        select(Chat)
        .where(
            Chat.owner_user_id == user_id,
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == False,  # noqa: E712
            Chat.id.not_in(log_targets),
        )
        .order_by(Chat.id.desc())
    )
    return list(res.scalars().all())


async def get_or_create_rule(session: AsyncSession, chat_id: int) -> Rule:
    """Правило для чата (создаёт запись при отсутствии)."""
    rule = await session.get(Rule, chat_id)
    if rule:
        return rule
    rule = Rule(
        chat_id=chat_id,
        filter_profanity_enabled=True,
        filter_jobs_enabled=True,
        filter_casino_enabled=True,
    )
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
    """Проверка: пользователь владелец или менеджер чата.

    Дополнительно: владелец/менеджер **канала** с привязанной группой обсуждения получает доступ к API
    по id этой группы (правила комментариев хранятся на Rule(chat_id=группа обсуждения)).
    """
    chats = await get_managed_chats(session, user_id)
    cid = int(chat_id)
    if any(int(c.id) == cid for c in chats):
        return True
    for c in chats:
        if str(getattr(c, "chat_kind", "") or "").strip().lower() != "channel":
            continue
        lid = getattr(c, "linked_discussion_chat_id", None)
        if lid is not None and int(lid) == cid:
            return True
    return False


def _norm_stopword(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
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
    try:
        from app.handlers.moderation import invalidate_stopwords_cache

        invalidate_stopwords_cache(int(chat_id))
    except Exception:
        pass
    return True


async def delete_stopword(session: AsyncSession, chat_id: int, word: str) -> bool:
    """Удалить стоп-слово. Возвращает True если удалено."""
    from sqlalchemy import delete as sql_delete
    w = _norm_stopword(word)
    if not w:
        return False
    await session.execute(sql_delete(StopWord).where(StopWord.chat_id == chat_id, StopWord.word == w))
    await session.commit()
    try:
        from app.handlers.moderation import invalidate_stopwords_cache

        invalidate_stopwords_cache(int(chat_id))
    except Exception:
        pass
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


async def _lazy_ensure_owner_promo_row(session: AsyncSession, code_clean: str) -> None:
    """Строка владельца в promo_codes: если при старте не создалась — создаём при первом вводе кода."""
    if code_clean != get_owner_forever_promo_code():
        return
    await session.execute(
        text(
            """
            INSERT INTO promo_codes (code, tariff, days)
            VALUES (:code, 'premium', 0)
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {"code": code_clean},
    )


async def _lazy_ensure_repeatable_tokens2000_row(session: AsyncSession, code_clean: str) -> None:
    """Строка многоразового промо +2000 ⚡ (без redemptions)."""
    if code_clean != get_repeatable_tokens2000_promo_code():
        return
    await session.execute(
        text(
            """
            INSERT INTO promo_codes (code, tariff, days, grant_tokens, grant_aurum)
            VALUES (:code, 'free', -1, 2000.0, 0.0)
            ON CONFLICT (code) DO UPDATE
            SET tariff = EXCLUDED.tariff,
                days = EXCLUDED.days,
                grant_tokens = EXCLUDED.grant_tokens,
                grant_aurum = EXCLUDED.grant_aurum
            """
        ),
        {"code": code_clean},
    )


async def apply_promo_code(session: AsyncSession, user_id: int, code: str) -> tuple[bool, str]:
    """
    Активировать промокод для пользователя.
    Каждый пользователь (telegram_id) может активировать один и тот же код только один раз;
    другие пользователи тот же код активируют независимо.
    Returns: (success, message).
    """
    from sqlalchemy.exc import IntegrityError

    code_clean = (code or "").strip().upper()
    if not code_clean:
        return False, "Введите промокод"
    is_owner_forever = code_clean == get_owner_forever_promo_code()
    is_repeatable_tokens2000 = code_clean == get_repeatable_tokens2000_promo_code()
    await _lazy_ensure_owner_promo_row(session, code_clean)
    await _lazy_ensure_repeatable_tokens2000_row(session, code_clean)
    res = await session.execute(select(PromoCode).where(PromoCode.code == code_clean).limit(1))
    promo = res.scalar_one_or_none()
    if not promo:
        return False, "Промокод не найден"
    res_user = await session.execute(select(User).where(User.telegram_id == user_id).limit(1))
    user = res_user.scalar_one_or_none()
    if not user:
        return False, "Пользователь не найден"

    if not is_owner_forever and not is_repeatable_tokens2000:
        res_red = await session.execute(
            select(PromoCodeRedemption)
            .where(
                PromoCodeRedemption.promo_code_id == promo.id,
                PromoCodeRedemption.telegram_user_id == user_id,
            )
            .limit(1)
        )
        if res_red.scalar_one_or_none():
            return False, "Вы уже активировали этот промокод"

    now = datetime.now(timezone.utc)
    days = int(getattr(promo, "days", 0) or 0)
    tariff = str(getattr(promo, "tariff", "") or "").strip().lower()
    if days >= 0:
        user.tariff = tariff or "premium"
        user.subscription_source = "promo"
        if days > 0:
            base = user.subscription_until if user.subscription_until and user.subscription_until > now else now
            user.subscription_until = base + timedelta(days=days)
        else:
            user.subscription_until = None  # бессрочно
        user.chat_limit = TARIFF_CHAT_LIMITS.get(user.tariff, 20)
        user.group_limit = TARIFF_GROUP_LIMITS.get(user.tariff, 20)
        user.channel_limit = TARIFF_CHANNEL_LIMITS.get(user.tariff, 20)
        if is_owner_forever:
            user.chat_limit = get_owner_forever_chat_limit()
            user.group_limit = get_owner_forever_chat_limit()
            user.channel_limit = get_owner_forever_chat_limit()
    grant_tokens = round(float(getattr(promo, "grant_tokens", 0.0) or 0.0), 2)
    grant_aurum = round(float(getattr(promo, "grant_aurum", 0.0) or 0.0), 2)
    promo_aurum_total = round(grant_tokens + grant_aurum, 2)
    if promo_aurum_total > 0:
        user.aurum_credits = round(float(getattr(user, "aurum_credits", 0.0) or 0.0) + promo_aurum_total, 2)
        if is_repeatable_tokens2000:
            ek = f"promo:{code_clean}:{uuid.uuid4().hex}"[:128]
        else:
            ek = f"promo:{code_clean}:aurum"
        session.add(
            CreditLedger(
                user_id=int(user.id),
                delta=float(promo_aurum_total),
                reason="promo_aurum",
                external_key=ek,
            )
        )
    if not is_owner_forever and not is_repeatable_tokens2000:
        session.add(PromoCodeRedemption(promo_code_id=promo.id, telegram_user_id=user_id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if not is_owner_forever and not is_repeatable_tokens2000:
            return False, "Вы уже активировали этот промокод"
        return False, "Не удалось активировать промокод"
    days_msg = f" на {days} дн." if days > 0 else ""
    if is_owner_forever:
        return True, f"Тестовый Premium без срока (лимит чатов: {user.chat_limit})"
    if is_repeatable_tokens2000:
        return True, f"Начислено по промокоду: +{promo_aurum_total:g} ✨AURUM (можно вводить снова)"
    if days < 0:
        if promo_aurum_total > 0:
            return True, f"Начислено по промокоду: +{promo_aurum_total:g} ✨AURUM"
        return True, "Начислено по промокоду: бонусов нет"
    bonus_msg = ""
    if promo_aurum_total > 0:
        bonus_msg = f" (+{promo_aurum_total:g} ✨AURUM)"
    return True, f"Premium активирован{days_msg}{bonus_msg}"


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
