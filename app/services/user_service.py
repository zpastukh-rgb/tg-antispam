# app/services/user_service.py
"""Сервис пользователя: создание, тариф, лимиты групп и каналов."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Chat, Tariff
from app.db.pii_session import PiiAsyncSessionLocal, pii_storage_enabled
from app.services.admin_roles import is_full_admin_user
from app.services.pii_user_store import pii_get_row, pii_upsert_profile

# Лимиты по тарифу (раздельно): FREE — 3 группы / 1 канал, Premium — 20 / 20.
TARIFF_CHAT_LIMITS = {
    Tariff.FREE.value: 3,
    Tariff.PREMIUM.value: 20,
    Tariff.PRO.value: 20,
    Tariff.BUSINESS.value: 20,
}
TARIFF_GROUP_LIMITS = {
    Tariff.FREE.value: 3,
    Tariff.PREMIUM.value: 20,
    Tariff.PRO.value: 20,
    Tariff.BUSINESS.value: 20,
}
TARIFF_CHANNEL_LIMITS = {
    Tariff.FREE.value: 1,
    Tariff.PREMIUM.value: 20,
    Tariff.PRO.value: 20,
    Tariff.BUSINESS.value: 20,
}

# 10-дневный Premium-триал. Окно активации — 10 дней с first_start_at; после нажатия
# «Активировать» юзер получает Premium на TRIAL_DAYS дней с момента активации (не с /start).
TRIAL_DAYS = 10
TRIAL_WINDOW_DAYS = 10
TRIAL_SUBSCRIPTION_SOURCE = "trial"


def _norm_un(v: str | None) -> str | None:
    s = (v or "").strip().lstrip("@").lower()
    return s or None


def _norm_fn(v: str | None) -> str | None:
    s = (v or "").strip()
    return s or None


def _profile_matches_mirror(
    user: User,
    username: str | None,
    first_name: str | None,
) -> bool:
    """Совпадение init_data с зеркалом в основной БД (Railway) — тогда ВДс не нужен."""
    if username is not None:
        if _norm_un(username) != _norm_un(getattr(user, "username", None)):
            return False
    if first_name is not None:
        if _norm_fn(first_name) != _norm_fn(getattr(user, "first_name", None)):
            return False
    return True


def _mirror_profile_on_user(user: User, username_v: str | None, first_name_v: str | None) -> None:
    """Дублируем ник/имя в основной таблице users для быстрых чтений (источник правды по-прежнему ПДн на ВДС)."""
    user.username = username_v
    user.first_name = first_name_v


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Получить или создать пользователя. По умолчанию FREE: группы=3, каналы=1."""
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = res.scalar_one_or_none()
    if user:
        # ПДн остаётся на ВДС; в основной БД дублируем ник/имя для чтения без RTT до РФ.
        # Если зеркало совпадает с init_data — в ПДн не ходим (типичный GET /api/me).
        skip_pii_roundtrip = False
        if pii_storage_enabled():
            has_mirror = bool(getattr(user, "username", None) or getattr(user, "first_name", None))
            if has_mirror and _profile_matches_mirror(user, username, first_name):
                skip_pii_roundtrip = True
            if not skip_pii_roundtrip:
                async with PiiAsyncSessionLocal() as pii_sess:
                    prow = await pii_get_row(pii_sess, int(telegram_id))
                    if prow is None and (getattr(user, "username", None) or getattr(user, "first_name", None)):
                        await pii_upsert_profile(
                            pii_sess,
                            int(telegram_id),
                            username=getattr(user, "username", None),
                            first_name=getattr(user, "first_name", None),
                        )
                        await pii_sess.commit()
                        prow = await pii_get_row(pii_sess, int(telegram_id))
                    cur_u = prow.username if prow else None
                    cur_fn = prow.first_name if prow else None
                    if username is not None:
                        cur_u = username
                    if first_name is not None:
                        cur_fn = first_name
                    if username is not None or first_name is not None:
                        await pii_upsert_profile(pii_sess, int(telegram_id), username=cur_u, first_name=cur_fn)
                        await pii_sess.commit()
                        prow = await pii_get_row(pii_sess, int(telegram_id))
                    if prow:
                        _mirror_profile_on_user(user, prow.username, prow.first_name)
                    else:
                        _mirror_profile_on_user(user, None, None)
        else:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
        # Старые записи могли иметь лимит 1; выравниваем FREE до актуального 3 (не трогаем полных админов с расширенным лимитом).
        tid = int(getattr(user, "telegram_id", 0) or 0)
        if not is_full_admin_user(user, tid):
            if (user.tariff or Tariff.FREE.value) == Tariff.FREE.value and int(
                getattr(user, "chat_limit", 0) or 0
            ) < TARIFF_CHAT_LIMITS[Tariff.FREE.value]:
                user.chat_limit = TARIFF_CHAT_LIMITS[Tariff.FREE.value]
            if int(getattr(user, "group_limit", 0) or 0) < TARIFF_GROUP_LIMITS[Tariff.FREE.value]:
                user.group_limit = TARIFF_GROUP_LIMITS[Tariff.FREE.value]
            if int(getattr(user, "channel_limit", 0) or 0) < TARIFF_CHANNEL_LIMITS[Tariff.FREE.value]:
                user.channel_limit = TARIFF_CHANNEL_LIMITS[Tariff.FREE.value]
        await session.commit()
        await session.refresh(user)
        return user

    user = User(
        telegram_id=telegram_id,
        username=None if pii_storage_enabled() else username,
        first_name=None if pii_storage_enabled() else first_name,
        tariff=Tariff.FREE.value,
        chat_limit=TARIFF_CHAT_LIMITS[Tariff.FREE.value],  # 1 чат
        group_limit=TARIFF_GROUP_LIMITS[Tariff.FREE.value],
        channel_limit=TARIFF_CHANNEL_LIMITS[Tariff.FREE.value],
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    if pii_storage_enabled():
        async with PiiAsyncSessionLocal() as pii_sess:
            await pii_upsert_profile(pii_sess, int(telegram_id), username=username, first_name=first_name)
            await pii_sess.commit()
            prow = await pii_get_row(pii_sess, int(telegram_id))
        if prow:
            _mirror_profile_on_user(user, prow.username, prow.first_name)
        await session.commit()
        await session.refresh(user)
    return user


def _is_paid_tariff_active(user: User, now: datetime) -> bool:
    """Совпадает с /api: Premium / pro / business с действующим сроком или бессрочно."""
    tariff = (getattr(user, "tariff", None) or "free").lower()
    sub_until = getattr(user, "subscription_until", None)
    if sub_until:
        if sub_until.tzinfo is None:
            sub_until = sub_until.replace(tzinfo=timezone.utc)
        if sub_until > now:
            return True
    if not sub_until and tariff in ("premium", "pro", "business"):
        return True
    return False


def trial_window_remaining_days(user: User, now: datetime | None = None) -> int:
    """Сколько целых суток ещё открыто окно активации триала.

    Окно — `TRIAL_WINDOW_DAYS` дней с `first_start_at` (включительно сегодняшний день).
    Если `first_start_at` не задан — окно «не открыто», считаем `TRIAL_WINDOW_DAYS`
    (это нормально для свежеприлетевших юзеров: первое /start обычно ставит
    `first_start_at` до того, как вызывается эта функция).
    Возвращает 0..TRIAL_WINDOW_DAYS.
    """
    now = now or datetime.now(timezone.utc)
    fsa = getattr(user, "first_start_at", None)
    if fsa is None:
        return TRIAL_WINDOW_DAYS
    if fsa.tzinfo is None:
        fsa = fsa.replace(tzinfo=timezone.utc)
    seconds_elapsed = (now - fsa).total_seconds()
    days_elapsed = int(seconds_elapsed // 86400)
    remaining = TRIAL_WINDOW_DAYS - days_elapsed
    if remaining < 0:
        return 0
    if remaining > TRIAL_WINDOW_DAYS:
        return TRIAL_WINDOW_DAYS
    return int(remaining)


def is_trial_eligible(user: User, now: datetime | None = None) -> bool:
    """Может ли юзер активировать 10-дневный триал прямо сейчас.

    Условия:
    1) `trial_used == False` (триал ещё не активировался);
    2) уже было первое /start (есть `first_start_at`);
    3) окно активации не закрылось (`trial_window_remaining_days > 0`);
    4) сейчас нет активной платной подписки (purchase/promo).
    """
    if bool(getattr(user, "trial_used", False)):
        return False
    if getattr(user, "first_start_at", None) is None:
        return False
    if trial_window_remaining_days(user, now) <= 0:
        return False
    src = (getattr(user, "subscription_source", None) or "").strip().lower()
    if src in ("payment", "promo"):
        return False
    return True


def is_trial_active(user: User, now: datetime | None = None) -> bool:
    """Идёт ли сейчас 10-дневный Premium-триал (активированный пользователем)."""
    now = now or datetime.now(timezone.utc)
    if not bool(getattr(user, "trial_used", False)):
        return False
    src = (getattr(user, "subscription_source", None) or "").strip().lower()
    if src != TRIAL_SUBSCRIPTION_SOURCE:
        return False
    sub_until = getattr(user, "subscription_until", None)
    if sub_until is None:
        return False
    if sub_until.tzinfo is None:
        sub_until = sub_until.replace(tzinfo=timezone.utc)
    return sub_until > now


def trial_active_remaining_days(user: User, now: datetime | None = None) -> int:
    """Сколько целых суток осталось в активном Premium-триале (0 если не активен)."""
    if not is_trial_active(user, now):
        return 0
    now = now or datetime.now(timezone.utc)
    sub_until = getattr(user, "subscription_until", None)
    if sub_until.tzinfo is None:
        sub_until = sub_until.replace(tzinfo=timezone.utc)
    seconds_left = (sub_until - now).total_seconds()
    if seconds_left <= 0:
        return 0
    import math
    return max(0, int(math.ceil(seconds_left / 86400)))


async def ensure_user_chat_limit_synced_for_tariff(session: AsyncSession, user: User) -> None:
    """
    Выровнять лимиты (group/channel) с тарифом:
    - активная подписка premium/pro/business — не ниже лимита тарифа в БД (убираем устаревшие 6, 10…);
    - FREE без подписки — chat_limit не выше бесплатного (чинит «залипшие» большие числа).
    Полный админ (ENV / is_admin): не перезаписываем chat_limit — квота задаётся вручную в БД.
    """
    tid = int(getattr(user, "telegram_id", 0) or 0)
    if tid and is_full_admin_user(user, tid):
        return
    now = datetime.now(timezone.utc)
    paid = _is_paid_tariff_active(user, now)
    t = (getattr(user, "tariff", None) or Tariff.FREE.value).lower()
    paid_tiers = (Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value)
    free_group_lim = int(TARIFF_GROUP_LIMITS[Tariff.FREE.value])
    free_channel_lim = int(TARIFF_CHANNEL_LIMITS[Tariff.FREE.value])

    if paid and t in paid_tiers:
        want_group = int(TARIFF_GROUP_LIMITS.get(t, TARIFF_GROUP_LIMITS[Tariff.PREMIUM.value]) or 20)
        want_channel = int(TARIFF_CHANNEL_LIMITS.get(t, TARIFF_CHANNEL_LIMITS[Tariff.PREMIUM.value]) or 20)
        cur_group = int(getattr(user, "group_limit", 0) or 0)
        cur_channel = int(getattr(user, "channel_limit", 0) or 0)
        changed = False
        if cur_group < want_group:
            user.group_limit = want_group
            changed = True
        if cur_channel < want_channel:
            user.channel_limit = want_channel
            changed = True
        if int(getattr(user, "chat_limit", 0) or 0) < want_group:
            user.chat_limit = want_group
            changed = True
        if changed:
            await session.commit()
            await session.refresh(user)
        return

    if t == Tariff.FREE.value:
        cur_group = int(getattr(user, "group_limit", 0) or 0)
        cur_channel = int(getattr(user, "channel_limit", 0) or 0)
        cur_chat = int(getattr(user, "chat_limit", 0) or 0)
        if cur_group != free_group_lim or cur_channel != free_channel_lim or cur_chat != free_group_lim:
            user.group_limit = free_group_lim
            user.channel_limit = free_channel_lim
            user.chat_limit = free_group_lim
            await session.commit()
            await session.refresh(user)


async def count_protected_chats(session: AsyncSession, telegram_id: int) -> int:
    """
    Чаты, которые идут в квоту: как get_managed_chats
    (владелец, ChatManager, принятое приглашение менеджера), без каналов-логов.
    """
    from app.db.models import ChatManager, ChatManagerInvite

    manager_sub = select(ChatManager.chat_id).where(ChatManager.user_id == telegram_id)
    invite_sub = select(ChatManagerInvite.chat_id).where(
        ChatManagerInvite.status == "connected",
        (ChatManagerInvite.connected_user_id == telegram_id) | (ChatManagerInvite.target_telegram_id == telegram_id),
    )
    managed_sub = manager_sub.union(invite_sub).subquery()
    log_targets = select(Chat.log_chat_id).where(Chat.log_chat_id.is_not(None))
    res = await session.execute(
        select(Chat)
        .where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            Chat.id.not_in(log_targets),
            or_(Chat.chat_kind.is_(None), Chat.chat_kind != "channel"),
            or_(
                Chat.owner_user_id == telegram_id,
                Chat.id.in_(select(managed_sub.c.chat_id)),
            ),
        )
    )
    return len(list(res.scalars().all()))


async def count_managed_chats_by_kind(session: AsyncSession, telegram_id: int) -> tuple[int, int]:
    """Возвращает (groups_count, channels_count) среди активных управляемых чатов."""
    from app.db.models import ChatManager, ChatManagerInvite

    manager_sub = select(ChatManager.chat_id).where(ChatManager.user_id == telegram_id)
    invite_sub = select(ChatManagerInvite.chat_id).where(
        ChatManagerInvite.status == "connected",
        (ChatManagerInvite.connected_user_id == telegram_id) | (ChatManagerInvite.target_telegram_id == telegram_id),
    )
    managed_sub = manager_sub.union(invite_sub).subquery()
    log_targets = select(Chat.log_chat_id).where(Chat.log_chat_id.is_not(None))
    res = await session.execute(
        select(Chat.id, Chat.chat_kind).where(
            Chat.is_log_chat == False,  # noqa: E712
            Chat.is_active == True,  # noqa: E712
            Chat.id.not_in(log_targets),
            or_(
                Chat.owner_user_id == telegram_id,
                Chat.id.in_(select(managed_sub.c.chat_id)),
            ),
        )
    )
    groups = 0
    channels = 0
    for _cid, kind in res.all():
        k = str(kind or "group").strip().lower()
        if k == "channel":
            channels += 1
        else:
            groups += 1
    return groups, channels


def _paid_chat_limit_floor(user: User) -> int:
    """Минимальный лимит чатов для строки с активной платной подпиской (по полю tariff)."""
    t = (getattr(user, "tariff", None) or Tariff.PREMIUM.value).lower()
    if t not in (Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value):
        t = Tariff.PREMIUM.value
    return int(TARIFF_CHAT_LIMITS.get(t, TARIFF_CHAT_LIMITS[Tariff.PREMIUM.value]) or 20)


def _paid_group_limit_floor(user: User) -> int:
    t = (getattr(user, "tariff", None) or Tariff.PREMIUM.value).lower()
    if t not in (Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value):
        t = Tariff.PREMIUM.value
    return int(TARIFF_GROUP_LIMITS.get(t, TARIFF_GROUP_LIMITS[Tariff.PREMIUM.value]) or 20)


def _paid_channel_limit_floor(user: User) -> int:
    t = (getattr(user, "tariff", None) or Tariff.PREMIUM.value).lower()
    if t not in (Tariff.PREMIUM.value, Tariff.PRO.value, Tariff.BUSINESS.value):
        t = Tariff.PREMIUM.value
    return int(TARIFF_CHANNEL_LIMITS.get(t, TARIFF_CHANNEL_LIMITS[Tariff.PREMIUM.value]) or 20)


def effective_chat_limit(user: User, telegram_user_id: int | None = None) -> int:
    """
    Лимит чатов для проверок и UI: тариф + подписка, либо значение из БД для полного админа.
    telegram_user_id — тот же id, что в init_data (обычно совпадает с user.telegram_id).
    """
    tid = int(telegram_user_id if telegram_user_id is not None else getattr(user, "telegram_id", 0) or 0)
    if tid and is_full_admin_user(user, tid):
        return max(int(getattr(user, "chat_limit", 0) or 0), 1)
    now = datetime.now(timezone.utc)
    if _is_paid_tariff_active(user, now):
        return max(int(getattr(user, "chat_limit", 0) or 0), _paid_chat_limit_floor(user))
    return int(TARIFF_CHAT_LIMITS[Tariff.FREE.value])


def effective_group_limit(user: User, telegram_user_id: int | None = None) -> int:
    tid = int(telegram_user_id if telegram_user_id is not None else getattr(user, "telegram_id", 0) or 0)
    if tid and is_full_admin_user(user, tid):
        return max(int(getattr(user, "group_limit", 0) or 0), 1)
    now = datetime.now(timezone.utc)
    if _is_paid_tariff_active(user, now):
        return max(int(getattr(user, "group_limit", 0) or 0), _paid_group_limit_floor(user))
    return int(TARIFF_GROUP_LIMITS[Tariff.FREE.value])


def effective_channel_limit(user: User, telegram_user_id: int | None = None) -> int:
    tid = int(telegram_user_id if telegram_user_id is not None else getattr(user, "telegram_id", 0) or 0)
    if tid and is_full_admin_user(user, tid):
        return max(int(getattr(user, "channel_limit", 0) or 0), 1)
    now = datetime.now(timezone.utc)
    if _is_paid_tariff_active(user, now):
        return max(int(getattr(user, "channel_limit", 0) or 0), _paid_channel_limit_floor(user))
    return int(TARIFF_CHANNEL_LIMITS[Tariff.FREE.value])


async def can_add_chat(session: AsyncSession, telegram_id: int) -> tuple[bool, int, int]:
    """
    Можно ли подключить ещё один чат.
    Returns: (can_add, current_count, limit).
    """
    user = await get_or_create_user(session, telegram_id)
    await ensure_user_chat_limit_synced_for_tariff(session, user)
    await session.refresh(user)
    groups_count, _channels_count = await count_managed_chats_by_kind(session, telegram_id)
    count = int(groups_count)
    limit = effective_group_limit(user, telegram_id)
    return (count < limit, count, limit)


async def can_add_channel(session: AsyncSession, telegram_id: int) -> tuple[bool, int, int]:
    """Можно ли подключить ещё один канал."""
    user = await get_or_create_user(session, telegram_id)
    await ensure_user_chat_limit_synced_for_tariff(session, user)
    await session.refresh(user)
    _groups_count, channels_count = await count_managed_chats_by_kind(session, telegram_id)
    limit = effective_channel_limit(user, telegram_id)
    return (int(channels_count) < limit, int(channels_count), int(limit))


async def can_add_chat_by_kind(session: AsyncSession, telegram_id: int, chat_kind: str) -> tuple[bool, int, int]:
    kind = str(chat_kind or "group").strip().lower()
    if kind == "channel":
        return await can_add_channel(session, telegram_id)
    return await can_add_chat(session, telegram_id)
