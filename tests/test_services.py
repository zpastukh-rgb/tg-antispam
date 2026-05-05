# tests/test_services.py
"""Тесты сервисов: user_service, api.service (profanity, promo)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from datetime import datetime, timedelta, timezone

from app.db.models import User, Chat, Rule, ProfanityWord, PromoCode, PromoCodeRedemption, Tariff
from app.services.user_service import (
    get_or_create_user,
    can_add_chat,
    count_protected_chats,
    TARIFF_CHAT_LIMITS,
    ensure_user_chat_limit_synced_for_tariff,
    effective_chat_limit,
)
from app.api.service import (
    list_profanity,
    add_profanity,
    remove_profanity,
    apply_promo_code,
    get_or_create_rule,
    list_stopwords,
    add_stopword,
)
from app.db.ensure_defaults import get_repeatable_tokens2000_promo_code


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
    await get_or_create_user(db_session, 111)
    can_add, count, limit = await can_add_chat(db_session, 111)
    assert limit == TARIFF_CHAT_LIMITS["free"]
    assert count == 0
    assert can_add is True


@pytest.mark.asyncio
async def test_can_add_chat_premium_stale_db_limit_uses_tariff_floor(db_session):
    """Активный Premium: устаревший chat_limit в БД не должен резать квоту ниже тарифа."""
    u = await get_or_create_user(db_session, 77701)
    u.tariff = Tariff.PREMIUM.value
    u.chat_limit = 10
    u.subscription_until = datetime.now(timezone.utc) + timedelta(days=1)
    await db_session.commit()
    can_add, count, limit = await can_add_chat(db_session, 77701)
    assert count == 0
    assert limit >= int(TARIFF_CHAT_LIMITS[Tariff.PREMIUM.value])
    assert can_add is True
    res = await db_session.execute(select(User).where(User.telegram_id == 77701))
    u2 = res.scalar_one()
    assert int(u2.chat_limit or 0) >= int(TARIFF_CHAT_LIMITS[Tariff.PREMIUM.value])


@pytest.mark.asyncio
async def test_full_admin_free_preserves_custom_chat_limit(db_session):
    """Полный админ (is_admin): FREE + лимит 999 не сбрасывается ensure и участвует в can_add_chat."""
    u = await get_or_create_user(db_session, 88801)
    u.is_admin = True
    u.tariff = Tariff.FREE.value
    u.chat_limit = 999
    await db_session.commit()
    await ensure_user_chat_limit_synced_for_tariff(db_session, u)
    await db_session.refresh(u)
    assert int(u.chat_limit or 0) == 999
    assert effective_chat_limit(u, 88801) == 999
    can_add, count, limit = await can_add_chat(db_session, 88801)
    assert limit == 999
    assert count == 0
    assert can_add is True


@pytest.mark.asyncio
async def test_can_add_chat_free_normalizes_stale_high_limit(db_session):
    u = await get_or_create_user(db_session, 77702)
    u.tariff = Tariff.FREE.value
    u.chat_limit = 10
    await db_session.commit()
    can_add, count, limit = await can_add_chat(db_session, 77702)
    assert limit == int(TARIFF_CHAT_LIMITS[Tariff.FREE.value])
    assert count == 0
    assert can_add is True
    res = await db_session.execute(select(User).where(User.telegram_id == 77702))
    u2 = res.scalar_one()
    assert int(u2.chat_limit or 0) == int(TARIFF_CHAT_LIMITS[Tariff.FREE.value])


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
async def test_apply_promo_code_same_user_twice_fails(db_session):
    await get_or_create_user(db_session, 777)
    promo = PromoCode(code="TRIAL3", tariff="premium", days=3)
    db_session.add(promo)
    await db_session.commit()
    ok1, _ = await apply_promo_code(db_session, 777, "TRIAL3")
    assert ok1 is True
    ok2, msg2 = await apply_promo_code(db_session, 777, "TRIAL3")
    assert ok2 is False
    assert "уже" in msg2.lower()


@pytest.mark.asyncio
async def test_apply_owner_forever_promo_lazy_row(db_session, monkeypatch):
    """Без строки в promo_codes: создаётся при активации (как на проде после деплоя без рестарта ensure)."""
    monkeypatch.delenv("OWNER_FOREVER_PROMO_CODE", raising=False)
    monkeypatch.delenv("OWNER_FOREVER_CHAT_LIMIT", raising=False)
    await get_or_create_user(db_session, 501)
    ok, msg = await apply_promo_code(db_session, 501, "GUARDIAN_OWNER")
    assert ok is True
    assert "без срока" in msg.lower()
    res = await db_session.execute(select(User).where(User.telegram_id == 501))
    user = res.scalar_one_or_none()
    assert user is not None
    assert user.subscription_until is None
    assert user.chat_limit == 500


@pytest.mark.asyncio
async def test_apply_owner_forever_promo(db_session, monkeypatch):
    """Бессрочный тестовый промокод владельца: premium, без subscription_until, расширенный лимит чатов."""
    monkeypatch.delenv("OWNER_FOREVER_PROMO_CODE", raising=False)
    monkeypatch.delenv("OWNER_FOREVER_CHAT_LIMIT", raising=False)
    await get_or_create_user(db_session, 333)
    promo = PromoCode(code="GUARDIAN_OWNER", tariff="premium", days=0)
    db_session.add(promo)
    await db_session.commit()
    ok, msg = await apply_promo_code(db_session, 333, "guardian_owner")
    assert ok is True
    assert "без срока" in msg.lower()
    res = await db_session.execute(select(User).where(User.telegram_id == 333))
    user = res.scalar_one_or_none()
    assert user is not None
    assert user.tariff == "premium"
    assert user.subscription_until is None
    assert user.chat_limit == 500


@pytest.mark.asyncio
async def test_apply_owner_forever_promo_repeat_ok(db_session, monkeypatch):
    """GUARDIAN_OWNER можно вводить повторно (идемпотентно): после сброса или чтобы обновить лимиты."""
    monkeypatch.delenv("OWNER_FOREVER_PROMO_CODE", raising=False)
    await get_or_create_user(db_session, 334)
    promo = PromoCode(code="GUARDIAN_OWNER", tariff="premium", days=0)
    db_session.add(promo)
    await db_session.commit()
    ok1, _ = await apply_promo_code(db_session, 334, "GUARDIAN_OWNER")
    assert ok1 is True
    ok2, msg2 = await apply_promo_code(db_session, 334, "GUARDIAN_OWNER")
    assert ok2 is True
    assert "без срока" in str(msg2).lower()


@pytest.mark.asyncio
async def test_apply_repeatable_tokens2000_same_user_twice(db_session, monkeypatch):
    """Многоразовый промо +2000 ⚡: один пользователь может активировать повторно."""
    monkeypatch.delenv("REPEATABLE_TOKENS2000_PROMO_CODE", raising=False)
    code = get_repeatable_tokens2000_promo_code()
    await get_or_create_user(db_session, 4411)
    promo = PromoCode(code=code, tariff="free", days=-1, grant_tokens=2000.0, grant_aurum=0.0)
    db_session.add(promo)
    await db_session.commit()
    ok1, _ = await apply_promo_code(db_session, 4411, code)
    ok2, _ = await apply_promo_code(db_session, 4411, code)
    assert ok1 is True
    assert ok2 is True
    res = await db_session.execute(select(User).where(User.telegram_id == 4411))
    u = res.scalar_one()
    assert float(u.aurum_credits or 0) == 4000.0
    res_r = await db_session.execute(select(PromoCodeRedemption))
    assert len(list(res_r.scalars().all())) == 0


@pytest.mark.asyncio
async def test_apply_promo_code_two_different_users_same_code(db_session):
    await get_or_create_user(db_session, 601)
    await get_or_create_user(db_session, 602)
    promo = PromoCode(code="TRIAL3", tariff="premium", days=3)
    db_session.add(promo)
    await db_session.commit()
    ok_a, _ = await apply_promo_code(db_session, 601, "TRIAL3")
    ok_b, _ = await apply_promo_code(db_session, 602, "TRIAL3")
    assert ok_a is True
    assert ok_b is True
    res = await db_session.execute(select(PromoCodeRedemption))
    assert len(list(res.scalars().all())) == 2


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
