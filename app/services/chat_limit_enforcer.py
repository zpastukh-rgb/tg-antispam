from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, Rule


async def enforce_owner_active_chat_limit(
    session: AsyncSession,
    owner_telegram_id: int,
    limit: int,
) -> dict[str, list[int]]:
    """
    Для владельца оставляет активными только первые `limit` чатов (по времени подключения).
    Остальные деактивирует (is_active=False) и снимает log_chat_id.
    """
    owner_id = int(owner_telegram_id or 0)
    cap = max(0, int(limit or 0))
    rows = (
        await session.execute(
            select(Chat)
            .where(
                Chat.owner_user_id == owner_id,
                Chat.is_log_chat == False,  # noqa: E712
            )
            .order_by(Chat.created_at.asc(), Chat.id.asc())
        )
    ).scalars().all()

    chat_ids = [int(getattr(c, "id", 0) or 0) for c in rows if int(getattr(c, "id", 0) or 0) > 0]
    rule_ids: set[int] = set()
    if chat_ids:
        rr = await session.execute(select(Rule.chat_id).where(Rule.chat_id.in_(chat_ids)))
        rule_ids = {int(x) for x in rr.scalars().all()}
    connected_rows = [c for c in rows if int(getattr(c, "id", 0) or 0) in rule_ids or bool(getattr(c, "is_active", False))]
    keep_ids = {int(c.id) for c in connected_rows[:cap] if int(getattr(c, "id", 0) or 0) != 0}
    kept: list[int] = []
    disabled: list[int] = []

    for c in rows:
        cid = int(getattr(c, "id", 0) or 0)
        if cid <= 0:
            continue
        if cid in keep_ids:
            # Первые N подключённых чатов остаются доступными.
            c.is_active = True
            kept.append(cid)
        else:
            # Всё сверх лимита — строго на паузу.
            c.is_active = False
            c.log_chat_id = None
            disabled.append(cid)
        session.add(c)

    return {"kept_chat_ids": kept, "disabled_chat_ids": disabled}


async def restore_owner_chats_after_premium(
    session: AsyncSession,
    owner_telegram_id: int,
) -> dict[str, list[int]]:
    """
    После возврата Premium включаем обратно «подключённые» чаты владельца:
    те, у которых уже есть Rule (чат уже был в защите ранее).
    """
    owner_id = int(owner_telegram_id or 0)
    rows = (
        await session.execute(
            select(Chat)
            .where(
                Chat.owner_user_id == owner_id,
                Chat.is_log_chat == False,  # noqa: E712
            )
            .order_by(Chat.created_at.asc(), Chat.id.asc())
        )
    ).scalars().all()
    chat_ids = [int(getattr(c, "id", 0) or 0) for c in rows if int(getattr(c, "id", 0) or 0) > 0]
    if not chat_ids:
        return {"restored_chat_ids": []}
    rr = await session.execute(select(Rule.chat_id).where(Rule.chat_id.in_(chat_ids)))
    rule_chat_ids = {int(x) for x in rr.scalars().all()}

    restored: list[int] = []
    for c in rows:
        cid = int(getattr(c, "id", 0) or 0)
        if cid <= 0 or cid not in rule_chat_ids:
            continue
        if not bool(getattr(c, "is_active", False)):
            c.is_active = True
            session.add(c)
        restored.append(cid)
    return {"restored_chat_ids": restored}

