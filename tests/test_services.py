# tests/test_services.py
"""Тесты сервисов: user_service, api.service (profanity, promo)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import User, Chat, Rule, ProfanityWord, PromoCode
from app.services.user_service import get_or_create_user, can_add_chat, count_protected_chats, TARIFF_CHAT_LIMITS
from app.api.service import (
    list_profanity,
    add_profanity,
    remove_profanity,
    apply_promo_code,
    get_or_create_rule,
    list_stopwords,
    add_stopword,
)


@pytest.mark.asyncio
async def test_get_or_create_user(db_session):
    user = await get_or_create_user(db_session, 12345, username="test", first_name="Test")
    assert user is not None
    assert user.telegram_id == 12345
    assert user.username == "test"
    assert user.tariff == "free"
    assert user.chat_limit == TARIFF_CHAT_LIMITS["free"]


@pytest.mark.asyncio
async def test_can_add_chat_free_limit(db_session):
    user = await get_or_create_user(db_session, 111)
    can_add, count, limit = await can_add_chat(db_session, 111)
    assert limit == 1
    assert count == 0
    assert can_add is True


@pytest.mark.asyncio
async def test_profanity_list_add_remove(db_session):
    items = await list_profanity(db_session)
    assert items == []
    added = await add_profanity(db_session, "  testword  ")
    assert added is True
    items = await list_profanity(db_session)
    assert len(items) == 1
    assert items[0]["word"] == "testword"
    added2 = await add_profanity(db_session, "testword")
    assert added2 is False
    removed = await remove_profanity(db_session, "testword")
    assert removed is True
    items2 = await list_profanity(db_session)
    assert len(items2) == 0


@pytest.mark.asyncio
async def test_apply_promo_code_not_found(db_session):
    user = await get_or_create_user(db_session, 999)
    success, msg = await apply_promo_code(db_session, 999, "NOCODE")
    assert success is False
    assert "не найден" in msg or "Промокод" in msg or "не найден" in msg.lower()


@pytest.mark.asyncio
async def test_apply_promo_code_success(db_session):
    await get_or_create_user(db_session, 888)
    promo = PromoCode(code="TRIAL3", tariff="premium", days=3)
    db_session.add(promo)
    await db_session.commit()
    success, msg = await apply_promo_code(db_session, 888, "TRIAL3")
    assert success is True
    res = await db_session.execute(select(User).where(User.telegram_id == 888))
    user = res.scalar_one_or_none()
    assert user is not None
    assert user.tariff == "premium"
    assert user.subscription_until is not None
    assert user.chat_limit == 20


@pytest.mark.asyncio
async def test_rule_and_stopwords(db_session):
    chat_id = -100123
    db_session.add(Chat(id=chat_id, owner_user_id=1, is_log_chat=False, is_active=True))
    await db_session.commit()
    rule = await get_or_create_rule(db_session, chat_id)
    assert rule.chat_id == chat_id
    await add_stopword(db_session, chat_id, "spam")
    words = await list_stopwords(db_session, chat_id)
    assert "spam" in words
