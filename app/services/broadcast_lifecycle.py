"""Остановка рассылок и автопоста при истечении Premium."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminBroadcast, AdminBroadcastSchedule, AutopostCampaign

log = logging.getLogger(__name__)


def _stop_autopost_json(raw: str | None) -> tuple[str | None, bool]:
    if not raw:
        return raw, False
    try:
        ap = json.loads(raw)
    except Exception:
        return raw, False
    if not isinstance(ap, dict):
        return raw, False
    rs = str(ap.get("runState") or "").lower()
    if rs not in ("running", "paused"):
        return raw, False
    ap["runState"] = "stopped"
    state = ap.get("_state")
    if isinstance(state, dict):
        state["stop_reason"] = "premium_expired"
    else:
        ap["_state"] = {"stop_reason": "premium_expired"}
    return json.dumps(ap, ensure_ascii=False), True


async def stop_user_broadcast_automation(session: AsyncSession, owner_telegram_id: int) -> int:
    """Останавливает автопост и отменяет отложенные рассылки владельца без Premium."""
    tid = int(owner_telegram_id)
    stopped = 0

    bc_rows = (
        await session.execute(select(AdminBroadcast).where(AdminBroadcast.admin_telegram_id == tid))
    ).scalars().all()
    for row in bc_rows:
        new_json, changed = _stop_autopost_json(getattr(row, "autopost_json", None))
        if changed:
            row.autopost_json = new_json
            stopped += 1

    apc_rows = (
        await session.execute(select(AutopostCampaign).where(AutopostCampaign.admin_telegram_id == tid))
    ).scalars().all()
    for row in apc_rows:
        new_json, changed = _stop_autopost_json(getattr(row, "autopost_json", None))
        if changed:
            row.autopost_json = new_json
            stopped += 1

    sched_rows = (
        await session.execute(
            select(AdminBroadcastSchedule).where(
                AdminBroadcastSchedule.admin_telegram_id == tid,
                AdminBroadcastSchedule.status == "pending",
            )
        )
    ).scalars().all()
    for sched in sched_rows:
        sched.status = "failed"
        sched.error_message = "premium_expired"
        stopped += 1

    if stopped:
        log.info("broadcast automation stopped for uid=%s items=%s", tid, stopped)
    return stopped
