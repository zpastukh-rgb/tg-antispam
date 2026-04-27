"""Глобальные шаблоны «плохих» URL: общая база для чатов с включённой проверкой."""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GlobalBadUrlPattern, UserGlobalBadUrlPattern

log = logging.getLogger(__name__)

_CACHE_TS = 0.0
_CACHE_PATTERNS: tuple[str, ...] = ()
_TTL_SEC = 60.0


def invalidate_global_bad_url_cache() -> None:
    """Сбросить кэш после правок админом."""
    global _CACHE_TS, _CACHE_PATTERNS
    _CACHE_TS = 0.0
    _CACHE_PATTERNS = ()


async def get_global_bad_url_patterns(session: AsyncSession) -> tuple[str, ...]:
    """Все активные шаблоны (lowercase), с TTL-кэшем."""
    global _CACHE_TS, _CACHE_PATTERNS
    now = time.time()
    if _CACHE_PATTERNS and now - _CACHE_TS < _TTL_SEC:
        return _CACHE_PATTERNS
    try:
        res = await session.execute(
            select(GlobalBadUrlPattern.pattern).order_by(GlobalBadUrlPattern.pattern.asc())
        )
        _CACHE_PATTERNS = tuple(str(r[0]).strip().lower() for r in res.all() if r[0])
        _CACHE_TS = now
    except Exception as e:
        log.warning("get_global_bad_url_patterns: %s", e)
        _CACHE_PATTERNS = ()
    return _CACHE_PATTERNS


async def get_effective_global_bad_url_patterns(
    session: AsyncSession,
    owner_telegram_id: int,
    *,
    owner_is_full_admin: bool,
) -> tuple[str, ...]:
    """
    Шаблоны для проверки «глобальная база» у чатов владельца:
    - GlobalBadUrlPattern — только если владелец полный админ (общая база не уходит обычным юзерам);
    - UserGlobalBadUrlPattern — личная база владельца (Premium / кабинет).
    """
    merged: set[str] = set()
    if owner_is_full_admin:
        merged.update(await get_global_bad_url_patterns(session))
    tid = int(owner_telegram_id or 0)
    if tid > 0:
        try:
            res = await session.execute(
                select(UserGlobalBadUrlPattern.pattern)
                .where(UserGlobalBadUrlPattern.owner_telegram_id == tid)
                .order_by(UserGlobalBadUrlPattern.pattern.asc())
            )
            merged.update(str(r[0]).strip().lower() for r in res.all() if r[0])
        except Exception as e:
            log.warning("get_effective_global_bad_url_patterns user part: %s", e)
    return tuple(sorted(merged))
