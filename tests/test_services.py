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
    is_trial_active,
    is_trial_eligible,
    trial_active_remaining_days,
    trial_window_remaining_days,
    TRIAL_DAYS,
    TRIAL_WINDOW_DAYS,
    TRIAL_SUBSCRIPTION_SOURCE,
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


# === Premium-триал (7 дней): хелперы =========================================

@pytest.mark.asyncio
async def test_trial_eligible_fresh_after_first_start(db_session):
    """Свежий FREE-юзер с first_start_at сегодня: окно открыто → eligible=True."""
    u = await get_or_create_user(db_session, 9101)
    u.first_start_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert is_trial_eligible(u) is True
    assert is_trial_active(u) is False
    assert trial_window_remaining_days(u) == TRIAL_WINDOW_DAYS


@pytest.mark.asyncio
async def test_trial_not_eligible_before_first_start(db_session):
    """Юзер без /start: first_start_at=None → eligible=False (окно ещё не открыто)."""
    u = await get_or_create_user(db_session, 9102)
    assert u.first_start_at is None
    assert is_trial_eligible(u) is False


@pytest.mark.asyncio
async def test_trial_not_eligible_when_window_closed(db_session):
    """Окно активации закрылось через TRIAL_WINDOW_DAYS дней с /start."""
    u = await get_or_create_user(db_session, 9103)
    u.first_start_at = datetime.now(timezone.utc) - timedelta(days=TRIAL_WINDOW_DAYS + 1)
    await db_session.commit()
    assert trial_window_remaining_days(u) == 0
    assert is_trial_eligible(u) is False


@pytest.mark.asyncio
async def test_trial_not_eligible_when_already_used(db_session):
    """trial_used=True → больше не eligible (даже если окно открыто)."""
    u = await get_or_create_user(db_session, 9104)
    now = datetime.now(timezone.utc)
    u.first_start_at = now
    u.trial_used = True
    u.trial_activated_at = now
    await db_session.commit()
    assert is_trial_eligible(u) is False


@pytest.mark.asyncio
async def test_trial_not_eligible_when_paid_subscription(db_session):
    """Активная платная подписка → триал недоступен."""
    u = await get_or_create_user(db_session, 9105)
    now = datetime.now(timezone.utc)
    u.first_start_at = now
    u.subscription_source = "payment"
    u.subscription_until = now + timedelta(days=30)
    await db_session.commit()
    assert is_trial_eligible(u) is False


@pytest.mark.asyncio
async def test_trial_active_after_activation(db_session):
    """После активации: trial_used=True, subscription_source='trial', активный sub_until."""
    u = await get_or_create_user(db_session, 9106)
    now = datetime.now(timezone.utc)
    u.first_start_at = now
    u.trial_used = True
    u.trial_activated_at = now
    u.subscription_source = TRIAL_SUBSCRIPTION_SOURCE
    u.subscription_until = now + timedelta(days=TRIAL_DAYS)
    u.tariff = Tariff.PREMIUM.value
    await db_session.commit()
    assert is_trial_active(u) is True
    # Остаток ровно ~TRIAL_DAYS (с округлением вверх по секундам).
    remaining = trial_active_remaining_days(u)
    assert remaining in (TRIAL_DAYS, TRIAL_DAYS - 1)


@pytest.mark.asyncio
async def test_trial_gift_aurum_granted_once(db_session):
    """При активации триала — 100 AURUM один раз."""
    from app.services.user_service import TRIAL_GIFT_AURUM, grant_trial_gift_aurum

    u = await get_or_create_user(db_session, 9110)
    ok1, amt1 = await grant_trial_gift_aurum(db_session, u)
    await db_session.commit()
    assert ok1 is True
    assert amt1 == TRIAL_GIFT_AURUM
    assert float(u.aurum_credits or 0) == TRIAL_GIFT_AURUM
    ok2, amt2 = await grant_trial_gift_aurum(db_session, u)
    await db_session.commit()
    assert ok2 is False
    assert amt2 == 0.0
    assert float(u.aurum_credits or 0) == TRIAL_GIFT_AURUM


@pytest.mark.asyncio
async def test_trial_inactive_after_expiry(db_session):
    """Триал истёк: subscription_until < now → is_trial_active=False."""
    u = await get_or_create_user(db_session, 9107)
    now = datetime.now(timezone.utc)
    u.first_start_at = now - timedelta(days=TRIAL_DAYS + 5)
    u.trial_used = True
    u.trial_activated_at = now - timedelta(days=TRIAL_DAYS + 1)
    u.subscription_source = TRIAL_SUBSCRIPTION_SOURCE
    u.subscription_until = now - timedelta(hours=1)
    await db_session.commit()
    assert is_trial_active(u) is False
    assert trial_active_remaining_days(u) == 0


@pytest.mark.asyncio
async def test_trial_window_decays_each_day(db_session):
    """Окно активации сокращается на ~1 день в сутки от first_start_at."""
    u = await get_or_create_user(db_session, 9108)
    now = datetime.now(timezone.utc)
    u.first_start_at = now - timedelta(days=3)
    await db_session.commit()
    # Прошло 3 суток → осталось TRIAL_WINDOW_DAYS - 3.
    assert trial_window_remaining_days(u) == TRIAL_WINDOW_DAYS - 3


# === Pure-функции выбора для DM-серий триала ===================================

class _TrialUserStub:
    """Лёгкий стаб юзера — достаточно атрибутов для функций выбора."""

    def __init__(
        self,
        *,
        telegram_id: int = 1,
        first_start_at: datetime | None = None,
        trial_used: bool = False,
        trial_activated_at: datetime | None = None,
        trial_reminder_last_day_sent: int = 0,
        subscription_source: str | None = None,
        subscription_until: datetime | None = None,
        tariff: str = "free",
        language: str | None = "ru",
    ) -> None:
        self.telegram_id = telegram_id
        self.first_start_at = first_start_at
        self.trial_used = trial_used
        self.trial_activated_at = trial_activated_at
        self.trial_reminder_last_day_sent = trial_reminder_last_day_sent
        self.subscription_source = subscription_source
        self.subscription_until = subscription_until
        self.tariff = tariff
        self.language = language


def test_select_pre_trial_targets_picks_users_in_open_window():
    """Свежий FREE-юзер на дне N=9 — попадает в выборку, текст для N=9."""
    from app.services.reminders import _select_pre_trial_targets

    now = datetime.now(timezone.utc)
    u_ok = _TrialUserStub(telegram_id=10, first_start_at=now - timedelta(days=1))
    u_used = _TrialUserStub(telegram_id=11, first_start_at=now - timedelta(days=1), trial_used=True)
    u_no_start = _TrialUserStub(telegram_id=12)
    u_paid = _TrialUserStub(
        telegram_id=13,
        first_start_at=now - timedelta(days=1),
        subscription_source="payment",
        subscription_until=now + timedelta(days=30),
    )
    u_window_closed = _TrialUserStub(telegram_id=14, first_start_at=now - timedelta(days=11))
    out = list(_select_pre_trial_targets([u_ok, u_used, u_no_start, u_paid, u_window_closed], now))
    ids = [(u.telegram_id, n) for u, n in out]
    assert (10, 9) in ids  # только u_ok
    assert len(ids) == 1


def test_select_pre_trial_targets_skips_day_10_freshly_started():
    """День 0 = N=10: свеже-стартанувший юзер пропускается, чтобы не заваливать сразу."""
    from app.services.reminders import _select_pre_trial_targets

    now = datetime.now(timezone.utc)
    u_fresh = _TrialUserStub(telegram_id=21, first_start_at=now - timedelta(minutes=1))
    out = list(_select_pre_trial_targets([u_fresh], now))
    assert out == []


def test_select_pre_trial_targets_dedupe_via_last_day_sent():
    """Если уже отправляли на N=7 — повторно не выбираем; на N=6 — выбираем."""
    from app.services.reminders import _select_pre_trial_targets

    now = datetime.now(timezone.utc)
    u_dedup = _TrialUserStub(
        telegram_id=31,
        first_start_at=now - timedelta(days=3),
        trial_reminder_last_day_sent=7,
    )
    out = list(_select_pre_trial_targets([u_dedup], now))
    assert out == []
    # На следующий день N=6 — выбираем (last_sent=7 != 6).
    u_dedup2 = _TrialUserStub(
        telegram_id=32,
        first_start_at=now - timedelta(days=4),
        trial_reminder_last_day_sent=7,
    )
    out2 = list(_select_pre_trial_targets([u_dedup2], now))
    ids = [(u.telegram_id, n) for u, n in out2]
    assert (32, 6) in ids


def test_select_in_trial_targets_picks_active_trial():
    """Активный триал с остатком ~9 целых суток — попадает в выборку.

    `trial_active_remaining_days` использует math.ceil, поэтому надо брать
    sub_until чуть меньше 9 суток вперёд (ceil(8.96) = 9).
    """
    from app.services.reminders import _select_in_trial_targets

    now = datetime.now(timezone.utc)
    u_active = _TrialUserStub(
        telegram_id=41,
        first_start_at=now - timedelta(days=1),
        trial_used=True,
        trial_activated_at=now - timedelta(days=1),
        subscription_source="trial",
        subscription_until=now + timedelta(days=8, hours=23),
        tariff="premium",
    )
    out = list(_select_in_trial_targets([u_active], now))
    ids = [(u.telegram_id, n) for u, n in out]
    assert (41, 9) in ids


def test_select_in_trial_targets_dedupe_negative_marker():
    """Если уже отправляли in-trial с last_day=-7 — повторно не выбираем."""
    from app.services.reminders import _select_in_trial_targets

    now = datetime.now(timezone.utc)
    # ~7 целых суток остатка: ceil(6.96) = 7.
    u_dedup = _TrialUserStub(
        telegram_id=51,
        first_start_at=now - timedelta(days=3),
        trial_used=True,
        trial_activated_at=now - timedelta(days=3),
        subscription_source="trial",
        subscription_until=now + timedelta(days=6, hours=23),
        tariff="premium",
        trial_reminder_last_day_sent=-7,
    )
    out = list(_select_in_trial_targets([u_dedup], now))
    assert out == []


def test_select_in_trial_targets_skips_freshly_activated():
    """Только что активирован (N=10) — пропускаем, не заваливаем в день активации."""
    from app.services.reminders import _select_in_trial_targets

    now = datetime.now(timezone.utc)
    u_fresh = _TrialUserStub(
        telegram_id=61,
        first_start_at=now - timedelta(minutes=10),
        trial_used=True,
        trial_activated_at=now - timedelta(minutes=5),
        subscription_source="trial",
        subscription_until=now + timedelta(days=10),
        tariff="premium",
    )
    out = list(_select_in_trial_targets([u_fresh], now))
    assert out == []


def test_select_in_trial_targets_skips_inactive_trial():
    """Триал истёк (subscription_until < now) — не выбираем."""
    from app.services.reminders import _select_in_trial_targets

    now = datetime.now(timezone.utc)
    u_expired = _TrialUserStub(
        telegram_id=71,
        first_start_at=now - timedelta(days=15),
        trial_used=True,
        trial_activated_at=now - timedelta(days=11),
        subscription_source="trial",
        subscription_until=now - timedelta(hours=1),
        tariff="premium",
    )
    out = list(_select_in_trial_targets([u_expired], now))
    assert out == []


def test_trial_window_text_specific_overrides_generic():
    """Для каждого N=1..9 берётся specific-текст, для других — generic с {n}."""
    from app.services.reminders import _trial_window_text

    # N=9 — специфичный текст в i18n
    txt9 = _trial_window_text("ru", 9)
    assert "9 дней" in txt9 or "9 дн" in txt9
    # generic тоже должен содержать число (для непредвиденных n, например 5):
    # для N=5 у нас есть specific, так что проверим что N=5 даёт специфичный
    txt5 = _trial_window_text("ru", 5)
    assert "5 дн" in txt5


def test_trial_active_text_renders_for_all_days():
    """In-trial: текст для N=1..9 должен возвращать непустую строку, не равную ключу."""
    from app.services.reminders import _trial_active_text

    for n in range(1, 10):
        txt = _trial_active_text("ru", n)
        assert txt
        assert not txt.startswith("reminders.")
        # Английская версия тоже не должна падать
        en = _trial_active_text("en", n)
        assert en
        assert not en.startswith("reminders.")
