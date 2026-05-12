"""Кэш языка пользователя для бота и сервисов.

Бот не должен дёргать БД на каждое сообщение, чтобы получить язык — кэшируем в RAM с TTL.

Контракт:
- get_user_language(tid) -> 'ru' | 'en' (всегда возвращает поддерживаемую локаль).
- set_user_language(tid, lang) — обновляет БД и инвалидирует кэш.
- invalidate(tid) — сбрасывает кэш у одного пользователя (вызывается из API при PATCH /api/me/language).
- lang_from_update(update) — удобный хелпер для aiogram-хендлеров.

Имена возвращаются нормализованные через app.i18n.normalize_locale.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select, update

from app.db.models import User
from app.db.session import AsyncSessionLocal
from app.i18n import DEFAULT_LOCALE, SUPPORTED, normalize_locale

log = logging.getLogger(__name__)

# TTL в секундах. Невелик: бот всё равно ловит инвалидацию при PATCH /api/me/language.
_TTL_SEC: int = 60

# tid -> (locale, expires_at_unix)
_cache: dict[int, tuple[str, float]] = {}


def _now() -> float:
    return time.monotonic()


def invalidate(telegram_id: int | None) -> None:
    """Удаляет запись из кэша. Безопасно для несуществующих ключей."""
    if not telegram_id:
        return
    _cache.pop(int(telegram_id), None)


def clear_cache() -> None:
    """Полный сброс — для тестов и фоновых задач."""
    _cache.clear()


async def _fetch_from_db(telegram_id: int) -> str:
    if AsyncSessionLocal is None:
        return DEFAULT_LOCALE
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(User.language).where(User.telegram_id == int(telegram_id))
            )
            row = res.first()
            value = row[0] if row else None
            return normalize_locale(value or DEFAULT_LOCALE)
    except Exception:
        log.debug("user_locale: fetch failed for tid=%s", telegram_id, exc_info=True)
        return DEFAULT_LOCALE


async def get_user_language(
    telegram_id: int | None,
    *,
    fallback_tg_language_code: str | None = None,
) -> str:
    """Возвращает 'ru' или 'en'. Никогда не кидает исключений."""
    if not telegram_id:
        return normalize_locale(fallback_tg_language_code or DEFAULT_LOCALE)
    tid = int(telegram_id)
    hit = _cache.get(tid)
    now = _now()
    if hit and hit[1] > now:
        return hit[0]
    locale = await _fetch_from_db(tid)
    if locale not in SUPPORTED:
        # Если в БД ещё нет записи — берём fallback по Telegram language_code.
        locale = normalize_locale(fallback_tg_language_code or DEFAULT_LOCALE)
    _cache[tid] = (locale, now + _TTL_SEC)
    return locale


async def set_user_language(telegram_id: int, locale: str) -> str:
    """Сохраняет язык в БД, инвалидирует кэш и возвращает нормализованное значение."""
    norm = normalize_locale(locale)
    if norm not in SUPPORTED:
        norm = DEFAULT_LOCALE
    if AsyncSessionLocal is None:
        return norm
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(User).where(User.telegram_id == int(telegram_id)).values(language=norm)
            )
            await session.commit()
    except Exception:
        log.warning("user_locale: write failed for tid=%s", telegram_id, exc_info=True)
    invalidate(int(telegram_id))
    _cache[int(telegram_id)] = (norm, _now() + _TTL_SEC)
    return norm


def _extract_tg_user(update_obj: Any) -> tuple[int | None, str | None]:
    """Достаёт (telegram_id, language_code) из aiogram Message / CallbackQuery / Update.

    Не зависит от конкретной модели aiogram — пробует общие пути.
    """
    if update_obj is None:
        return None, None
    user = getattr(update_obj, "from_user", None)
    if user is None:
        # aiogram Update wraps message/callback_query — пройдёмся по типичным полям.
        for field in ("message", "callback_query", "edited_message", "channel_post", "chat_member"):
            inner = getattr(update_obj, field, None)
            if inner is not None:
                user = getattr(inner, "from_user", None)
                if user is not None:
                    break
    if user is None:
        return None, None
    tid = getattr(user, "id", None)
    code = getattr(user, "language_code", None)
    return (int(tid) if tid else None), (str(code) if code else None)


async def lang_from_update(update_obj: Any) -> str:
    """Универсальный хелпер для хендлеров aiogram (Message/CallbackQuery/Update)."""
    tid, code = _extract_tg_user(update_obj)
    return await get_user_language(tid, fallback_tg_language_code=code)


__all__ = (
    "clear_cache",
    "get_user_language",
    "invalidate",
    "lang_from_update",
    "set_user_language",
)
