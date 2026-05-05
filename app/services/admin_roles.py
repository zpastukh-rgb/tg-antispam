"""Полные права администратора (ENV + флаг в БД). Используется API и фоновые задачи без циклического импорта routes."""

from __future__ import annotations

import os

from app.db.models import User

# Владелец по умолчанию (@pastukh_viscera); дублируйте в ADMIN_TELEGRAM_IDS на проде при желании.
DEFAULT_ADMIN_TELEGRAM_IDS: frozenset[int] = frozenset({834702612})


def _parse_int_set(raw: str | None) -> set[int]:
    vals: set[int] = set()
    for part in (raw or "").split(","):
        p = part.strip()
        if not p:
            continue
        try:
            vals.add(int(p))
        except Exception:
            continue
    return vals


def _parse_str_set(raw: str | None) -> set[str]:
    vals: set[str] = set()
    for part in (raw or "").split(","):
        p = part.strip().lstrip("@").lower()
        if p:
            vals.add(p)
    return vals


def is_full_admin_user(user: User, telegram_user_id: int) -> bool:
    allowed_ids = _parse_int_set(os.getenv("ADMIN_TELEGRAM_IDS")) | set(DEFAULT_ADMIN_TELEGRAM_IDS)
    allowed_usernames = _parse_str_set(os.getenv("ADMIN_USERNAMES")) | {"pastukh_viscera"}
    username = str(getattr(user, "username", "") or "").strip().lstrip("@").lower()
    if bool(getattr(user, "is_admin", False)):
        return True
    if int(telegram_user_id) in allowed_ids:
        return True
    if username in allowed_usernames:
        return True
    return False
