"""Чтение/запись персональных полей пользователя во второй БД (ВДС / РФ)."""

from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from app.db.models import User
from app.db.pii_models import PiiBase, UserPersonalProfile
from app.db.pii_session import PiiAsyncSessionLocal, pii_engine, pii_storage_enabled

log = logging.getLogger(__name__)


async def ensure_pii_schema() -> None:
    """Создать таблицы в БД ПДн (без миграций Alembic — только create_all)."""
    if not pii_engine:
        return
    async with pii_engine.begin() as conn:
        await conn.run_sync(PiiBase.metadata.create_all)


async def pii_upsert_profile(
    session: AsyncSession,
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    """Записать/обновить профиль в БД ПДн."""
    tid = int(telegram_id)
    u = (username or "").strip() or None
    fn = (first_name or "").strip() or None
    stmt = (
        pg_insert(UserPersonalProfile)
        .values(telegram_id=tid, username=u, first_name=fn)
        .on_conflict_do_update(
            index_elements=[UserPersonalProfile.telegram_id],
            set_={
                "username": u,
                "first_name": fn,
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(stmt)


async def pii_get_row(session: AsyncSession, telegram_id: int) -> UserPersonalProfile | None:
    return (
        await session.execute(select(UserPersonalProfile).where(UserPersonalProfile.telegram_id == int(telegram_id)).limit(1))
    ).scalar_one_or_none()


async def pii_map_username_lowers_to_telegram_ids(usernames_lower: Sequence[str]) -> dict[str, int]:
    """Несколько @username (lower) → telegram_id для кармы/репутации при PII."""
    if not pii_storage_enabled() or not usernames_lower:
        return {}
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in usernames_lower:
        u = str(raw or "").strip().lower().lstrip("@")
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    if not uniq:
        return {}
    async with PiiAsyncSessionLocal() as pii_sess:
        res = await pii_sess.execute(
            select(UserPersonalProfile.telegram_id, UserPersonalProfile.username).where(
                func.lower(UserPersonalProfile.username).in_(uniq)
            )
        )
    out: dict[str, int] = {}
    for tid, username in res.all():
        k = str(username or "").strip().lower().lstrip("@")
        if k and int(tid or 0) > 0:
            out[k] = int(tid)
    return out


async def pii_find_telegram_id_by_username_lower(session: AsyncSession, username_lower: str) -> int | None:
    """Поиск по @username (уже lower, без @)."""
    un = (username_lower or "").strip().lower().lstrip("@")
    if not un:
        return None
    row = (
        await session.execute(
            select(UserPersonalProfile.telegram_id).where(func.lower(UserPersonalProfile.username) == un).limit(1)
        )
    ).first()
    if not row:
        return None
    return int(row[0])


def hydrate_user_from_pii_row(user: User, row: UserPersonalProfile | None) -> None:
    """Подставить в ORM-объект User значения из ПДн без пометки «грязным» для основной сессии."""
    if row is None:
        attributes.set_committed_value(user, "username", None)
        attributes.set_committed_value(user, "first_name", None)
        return
    attributes.set_committed_value(user, "username", row.username)
    attributes.set_committed_value(user, "first_name", row.first_name)


async def hydrate_users_from_pii(users: Sequence[User]) -> None:
    """Пакетно подтянуть username/first_name из ПДн для списка User (основная сессия не трогается)."""
    if not pii_storage_enabled() or not users:
        return
    ids = sorted({int(getattr(u, "telegram_id", 0) or 0) for u in users if int(getattr(u, "telegram_id", 0) or 0) > 0})
    if not ids:
        return
    async with PiiAsyncSessionLocal() as pii_sess:
        res = await pii_sess.execute(select(UserPersonalProfile).where(UserPersonalProfile.telegram_id.in_(ids)))
        by_tid = {int(r.telegram_id): r for r in res.scalars().all()}
    for u in users:
        tid = int(getattr(u, "telegram_id", 0) or 0)
        hydrate_user_from_pii_row(u, by_tid.get(tid))


async def clear_main_user_pii_columns(main_session: AsyncSession, user: User) -> None:
    """Убрать дубликаты ПДн из основной таблицы users (после переноса на ВДС)."""
    if not pii_storage_enabled():
        return
    uid = int(getattr(user, "id", 0) or 0)
    if uid <= 0:
        return
    await main_session.execute(
        update(User).where(User.id == uid).values(username=None, first_name=None),
    )


async def resolve_username_lookup(
    main_session: AsyncSession,
    username_lower: str,
) -> User | None:
    """Найти User по username: при PII — из второй БД, иначе из основной."""
    un = (username_lower or "").strip().lower().lstrip("@")
    if not un:
        return None
    if pii_storage_enabled():
        async with PiiAsyncSessionLocal() as pii_sess:
            tid = await pii_find_telegram_id_by_username_lower(pii_sess, un)
        if not tid:
            return None
        u = (await main_session.execute(select(User).where(User.telegram_id == int(tid)).limit(1))).scalar_one_or_none()
        if u:
            async with PiiAsyncSessionLocal() as pii_sess:
                row = await pii_get_row(pii_sess, int(tid))
            hydrate_user_from_pii_row(u, row)
        return u
    return (
        await main_session.execute(select(User).where(func.lower(User.username) == un).limit(1))
    ).scalar_one_or_none()
