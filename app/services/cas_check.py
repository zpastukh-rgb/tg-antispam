"""Проверка пользователя в базе Combot Anti-Spam (CAS)."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

CAS_API_BASE = os.getenv("CAS_API_URL", "https://api.cas.chat").rstrip("/")
CAS_USER_AGENT = os.getenv(
    "CAS_USER_AGENT",
    "AntiSpamGuardian/1.0 (Telegram bot; https://cas.chat)",
)
CAS_TIMEOUT_SEC = float(os.getenv("CAS_TIMEOUT", "5"))
CAS_CACHE_TTL_SEC = float(os.getenv("CAS_CACHE_TTL", "900"))

# user_id -> (is_banned, expires_at_unix)
_cache: dict[int, tuple[bool, float]] = {}


def _cache_get(user_id: int) -> Optional[bool]:
    row = _cache.get(int(user_id))
    if row is None:
        return None
    banned, exp = row
    if time.time() >= exp:
        _cache.pop(int(user_id), None)
        return None
    return banned


def _cache_set(user_id: int, banned: bool) -> None:
    _cache[int(user_id)] = (bool(banned), time.time() + CAS_CACHE_TTL_SEC)
    if len(_cache) > 50000:
        now = time.time()
        stale = [k for k, (_, exp) in _cache.items() if exp <= now]
        for k in stale[:10000]:
            _cache.pop(k, None)


async def is_user_cas_banned(user_id: int) -> Optional[bool]:
    """
    True — в CAS, False — чистый, None — ошибка API (fail-open: не кикаем).
    """
    uid = int(user_id)
    if uid <= 0:
        return False
    cached = _cache_get(uid)
    if cached is not None:
        return cached
    url = f"{CAS_API_BASE}/check"
    headers = {"User-Agent": CAS_USER_AGENT}
    try:
        timeout = aiohttp.ClientTimeout(total=CAS_TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params={"user_id": uid}, headers=headers) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:
        logger.debug("CAS check user=%s: %s", uid, e)
        return None
    if not isinstance(data, dict):
        return None
    ok = bool(data.get("ok"))
    if ok:
        _cache_set(uid, True)
        return True
    desc = str(data.get("description") or "").lower()
    if "not found" in desc or "no record" in desc:
        _cache_set(uid, False)
        return False
    logger.debug("CAS unexpected response user=%s: %s", uid, data)
    return None
