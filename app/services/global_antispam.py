# app/services/global_antispam.py
"""Антиспам база пользователей: общая для бота по всем группам."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GlobalAntispamUser

logger = logging.getLogger(__name__)


def antispam_display_label(user_id: int, display_name: str | None, username: str | None) -> str:
    """Краткая подпись для UI: имя / @username / id."""
    dn = (display_name or "").strip()
    un = (username or "").strip().lstrip("@")
    if dn and un:
        return f"{dn} (@{un}) — {user_id}"
    if dn:
        return f"{dn} — {user_id}"
    if un:
        return f"@{un} — {user_id}"
    return str(user_id)


async def is_in_global_antispam(session: AsyncSession, user_id: int) -> bool:
    """Проверить, есть ли user_id в глобальной антиспам базе."""
    row = await session.get(GlobalAntispamUser, user_id)
    return row is not None


async def add_to_global_antispam(
    session: AsyncSession,
    user_id: int,
    reason: str | None = None,
    *,
    display_name: str | None = None,
    username: str | None = None,
) -> bool:
    """Добавить в базу. Возвращает True если добавлен, False если уже был."""
    if await session.get(GlobalAntispamUser, user_id):
        return False
    dn = (display_name or "").strip()[:255] or None
    un = (username or "").strip().lstrip("@")[:64] or None
    session.add(
        GlobalAntispamUser(
            user_id=user_id,
            reason=(reason or "").strip() or None,
            display_name=dn,
            username=un,
        )
    )
    await session.commit()
    return True


async def update_antispam_user_profile(
    session: AsyncSession,
    user_id: int,
    display_name: str | None,
    username: str | None,
) -> bool:
    row = await session.get(GlobalAntispamUser, user_id)
    if not row:
        return False
    dn = (display_name or "").strip()[:255] or None
    un = (username or "").strip().lstrip("@")[:64] or None
    if dn:
        row.display_name = dn
    if un:
        row.username = un
    await session.commit()
    return True


async def remove_from_global_antispam(session: AsyncSession, user_id: int) -> bool:
    """Удалить из базы. После удаления — unban во всех управляемых группах (можно снова зайти по ссылке)."""
    row = await session.get(GlobalAntispamUser, user_id)
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    try:
        from app.services.telegram_bot_api import unban_user_in_all_managed_groups

        await unban_user_in_all_managed_groups(session, user_id)
    except Exception as e:
        logger.warning("unban after global antispam remove uid=%s: %s", user_id, e)
    return True


async def list_global_antispam(session: AsyncSession, limit: int = 500) -> list[dict]:
    """Список записей: [{ user_id, reason, display_name, username, created_at }, ...]."""
    res = await session.execute(
        select(GlobalAntispamUser).order_by(GlobalAntispamUser.created_at.desc()).limit(limit)
    )
    rows = res.scalars().all()
    return [
        {
            "user_id": r.user_id,
            "reason": r.reason or "",
            "display_name": r.display_name or "",
            "username": r.username or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def list_global_antispam_for_api(session: AsyncSession, limit: int = 500) -> list[dict]:
    """Список для Mini App / панели: подтягивает имена из Telegram, если в БД пусто."""
    from app.services.telegram_bot_api import private_chat_profile, tg_get_chat

    items = await list_global_antispam(session, limit=limit)
    fetched = 0
    for it in items:
        if fetched >= 25:
            break
        if (it.get("display_name") or "").strip() or (it.get("username") or "").strip():
            continue
        uid = int(it["user_id"])
        info = await tg_get_chat(uid)
        disp, un = private_chat_profile(info)
        if disp or un:
            await update_antispam_user_profile(session, uid, disp, un)
            it["display_name"] = disp or ""
            it["username"] = un or ""
            fetched += 1
    for it in items:
        it["display_label"] = antispam_display_label(
            int(it["user_id"]),
            (it.get("display_name") or "").strip() or None,
            (it.get("username") or "").strip() or None,
        )
    return items
