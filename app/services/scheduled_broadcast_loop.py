"""Фоновый цикл отложенных одноразовых рассылок (admin_broadcast_schedules)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminBroadcast, AdminBroadcastMedia, AdminBroadcastSchedule, User
from app.db.session import get_session
from app.services.admin_broadcast import run_broadcast_job
from app.services.admin_roles import is_full_admin_user
from app.services.broadcast_send_plan import (
    broadcast_charge_tokens,
    debit_user_broadcast_tokens,
    estimate_recipient_counts,
    resolve_broadcast_billing_plan,
    resolve_broadcast_target_chat_ids,
)
from app.api.service import get_managed_chats
from app.services.chat_owner_premium import user_effective_miniapp_premium
from app.services.user_service import get_or_create_user

log = logging.getLogger(__name__)

_SCHEDULED_BC_RUNTIME: dict[str, Any] = {
    "loop_started_at": None,
    "last_tick_at": None,
    "last_tick_ok_at": None,
    "ticks_total": 0,
    "lock_miss_total": 0,
    "last_error": None,
    "last_fire_at": None,
    "worker_label": (os.getenv("RAILWAY_REPLICA_ID") or os.getenv("RAILWAY_SERVICE_NAME") or os.getenv("HOSTNAME") or "local")[
        :80
    ],
    "bot_token_configured": bool((os.getenv("BOT_TOKEN") or "").strip()),
}

_SCHEDULED_BC_ADVISORY_LOCK_KEY = 402_119_331
_SCHEDULED_BC_MIN_LEAD = timedelta(minutes=2)
_SCHEDULED_BC_TICK_SEC = float(os.getenv("SCHEDULED_BC_TICK_SEC", "15") or "15")


def scheduled_broadcast_runtime_status() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    last_ok = _SCHEDULED_BC_RUNTIME.get("last_tick_ok_at")
    tick_stale = True
    if isinstance(last_ok, datetime):
        tick_stale = (now - last_ok).total_seconds() > max(120.0, _SCHEDULED_BC_TICK_SEC * 8)
    started = _SCHEDULED_BC_RUNTIME.get("loop_started_at")
    out: dict[str, Any] = {
        "worker_label": str(_SCHEDULED_BC_RUNTIME.get("worker_label") or "local"),
        "bot_token_configured": bool(_SCHEDULED_BC_RUNTIME.get("bot_token_configured")),
        "ticks_total": int(_SCHEDULED_BC_RUNTIME.get("ticks_total") or 0),
        "lock_miss_total": int(_SCHEDULED_BC_RUNTIME.get("lock_miss_total") or 0),
        "tick_stale": tick_stale,
        "loop_alive": isinstance(started, datetime) and not tick_stale,
        "last_error": _SCHEDULED_BC_RUNTIME.get("last_error"),
    }
    for k in ("loop_started_at", "last_tick_at", "last_tick_ok_at", "last_fire_at"):
        v = _SCHEDULED_BC_RUNTIME.get(k)
        out[k] = v.isoformat() if isinstance(v, datetime) else None
    return out


async def _scheduled_bc_try_advisory_lock(session: AsyncSession) -> bool:
    try:
        r = await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": int(_SCHEDULED_BC_ADVISORY_LOCK_KEY)})
        return bool(r.scalar())
    except Exception:
        return True


async def _scheduled_bc_release_advisory_lock(session: AsyncSession) -> None:
    try:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(_SCHEDULED_BC_ADVISORY_LOCK_KEY)})
    except Exception:
        pass


def _parse_chat_ids(raw: str | None) -> list[int]:
    try:
        data = json.loads(raw or "[]")
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[int] = []
    for x in data:
        try:
            v = int(x)
        except Exception:
            continue
        if v != 0:
            out.append(v)
    return out


async def _broadcast_access_for_schedule(session: AsyncSession, admin_tid: int) -> tuple[User, bool] | None:
    user = await get_or_create_user(session, admin_tid)
    if is_full_admin_user(user, admin_tid):
        return user, True
    now = datetime.now(timezone.utc)
    if user_effective_miniapp_premium(user, now):
        return user, False
    chats = await get_managed_chats(session, admin_tid)
    for c in chats:
        if int(getattr(c, "owner_user_id", 0) or 0) != admin_tid:
            return user, False
    return None


async def _fire_one_scheduled_broadcast(session: AsyncSession, sched: AdminBroadcastSchedule) -> bool:
    sid = int(sched.id)
    bid = int(sched.broadcast_id)
    admin_tid = int(sched.admin_telegram_id)
    target = str(sched.target_kind or "groups").strip().lower()
    body_chat_ids = _parse_chat_ids(sched.chat_ids_json)
    keep_draft_after = bool(getattr(sched, "keep_draft_after", True))

    access = await _broadcast_access_for_schedule(session, admin_tid)
    if not access:
        sched.status = "failed"
        sched.error_message = "premium_admin_or_manager"
        await session.commit()
        return False
    viewer, full = access
    allow_all_groups = is_full_admin_user(viewer, admin_tid)

    row = await session.get(AdminBroadcast, bid)
    if not row:
        sched.status = "failed"
        sched.error_message = "broadcast_not_found"
        await session.commit()
        return False

    if (row.status or "") == "sending":
        sched.status = "pending"
        await session.commit()
        return False

    if not full and target in ("users", "all"):
        sched.status = "failed"
        sched.error_message = "premium_broadcast_groups_only"
        await session.commit()
        return False

    target_chat_ids: list[int] = []
    if target in {"groups", "all"}:
        target_chat_ids = await resolve_broadcast_target_chat_ids(
            session,
            viewer_telegram_id=admin_tid,
            allow_all_groups=allow_all_groups,
            target=target,
            body_chat_ids=body_chat_ids,
        )
        if body_chat_ids and not target_chat_ids:
            sched.status = "failed"
            sched.error_message = "invalid_group_chat_ids"
            await session.commit()
            return False
        if target == "groups" and not target_chat_ids:
            sched.status = "failed"
            sched.error_message = "no_groups_to_send"
            await session.commit()
            return False

    text_ok = bool((row.body_text or "").strip())
    media_count_q = await session.execute(
        select(func.count()).select_from(AdminBroadcastMedia).where(AdminBroadcastMedia.broadcast_id == int(row.id))
    )
    media_ok = int(media_count_q.scalar() or 0) > 0 or (
        (row.media_kind or "none").lower() != "none" and bool(row.media_local_name)
    )
    if not text_ok and not media_ok:
        sched.status = "failed"
        sched.error_message = "need_text_or_media"
        await session.commit()
        return False

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        sched.status = "failed"
        sched.error_message = "bot_token_not_configured"
        await session.commit()
        return False

    n_users, n_groups = await estimate_recipient_counts(session, target=target, target_chat_ids=target_chat_ids)
    cost_tokens = broadcast_charge_tokens(n_users=n_users, n_groups=n_groups)
    if not full and int(cost_tokens) > 0:
        plan = await resolve_broadcast_billing_plan(
            session,
            viewer=viewer,
            viewer_telegram_id=admin_tid,
            full_admin=full,
            cost_tokens=int(cost_tokens),
            resolved_chat_ids=target_chat_ids,
        )
        if not plan.can_afford:
            sched.status = "failed"
            sched.error_message = "broadcast_aurum_insufficient"
            await session.commit()
            return False
        try:
            await debit_user_broadcast_tokens(
                session,
                user=plan.payer_user,
                full_admin=full,
                broadcast_id=int(row.id),
                cost_tokens=int(cost_tokens),
            )
        except ValueError:
            sched.status = "failed"
            sched.error_message = "broadcast_aurum_insufficient_debit"
            await session.commit()
            return False

    row.status = "sending"
    row.last_target = target
    row.sent_at = None
    row.recipient_ok = 0
    row.recipient_fail = 0
    row.error_message = None
    sched.status = "sent"
    sched.error_message = None
    await session.commit()

    asyncio.create_task(
        run_broadcast_job(
            bid,
            target,
            target_chat_ids,
            keep_draft_after=keep_draft_after,
            run_source="manual",
        )
    )
    _SCHEDULED_BC_RUNTIME["last_fire_at"] = datetime.now(timezone.utc)
    log.warning(
        "scheduled broadcast fired: schedule_id=%s broadcast_id=%s target=%s chats=%s",
        sid,
        bid,
        target,
        len(target_chat_ids),
    )
    return True


async def _process_due_scheduled_broadcasts(session: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    q = (
        select(AdminBroadcastSchedule)
        .where(
            AdminBroadcastSchedule.status == "pending",
            AdminBroadcastSchedule.scheduled_at <= now,
        )
        .order_by(AdminBroadcastSchedule.scheduled_at.asc())
        .limit(20)
    )
    rows = (await session.execute(q)).scalars().all()
    fired = 0
    for sched in rows:
        claim = await session.execute(
            update(AdminBroadcastSchedule)
            .where(
                AdminBroadcastSchedule.id == int(sched.id),
                AdminBroadcastSchedule.status == "pending",
            )
            .values(status="processing", updated_at=func.now())
        )
        await session.commit()
        if int(getattr(claim, "rowcount", 0) or 0) <= 0:
            continue
        await session.refresh(sched)
        try:
            if await _fire_one_scheduled_broadcast(session, sched):
                fired += 1
        except Exception as e:
            log.exception("scheduled broadcast fire failed: schedule_id=%s", sched.id)
            try:
                sched.status = "failed"
                sched.error_message = str(e)[:500]
                await session.commit()
            except Exception:
                await session.rollback()
    return fired


async def scheduled_broadcast_loop() -> None:
    _SCHEDULED_BC_RUNTIME["loop_started_at"] = datetime.now(timezone.utc)
    log.info("scheduled_broadcast_loop started (tick=%ss)", _SCHEDULED_BC_TICK_SEC)
    while True:
        _SCHEDULED_BC_RUNTIME["last_tick_at"] = datetime.now(timezone.utc)
        _SCHEDULED_BC_RUNTIME["ticks_total"] = int(_SCHEDULED_BC_RUNTIME.get("ticks_total") or 0) + 1
        try:
            session = await get_session()
            async with session:
                locked = await _scheduled_bc_try_advisory_lock(session)
                if not locked:
                    _SCHEDULED_BC_RUNTIME["lock_miss_total"] = int(_SCHEDULED_BC_RUNTIME.get("lock_miss_total") or 0) + 1
                else:
                    try:
                        await _process_due_scheduled_broadcasts(session)
                        _SCHEDULED_BC_RUNTIME["last_tick_ok_at"] = datetime.now(timezone.utc)
                        _SCHEDULED_BC_RUNTIME["last_error"] = None
                    finally:
                        await _scheduled_bc_release_advisory_lock(session)
        except Exception as e:
            _SCHEDULED_BC_RUNTIME["last_error"] = str(e)[:500]
            log.exception("scheduled_broadcast_loop tick error")
        await asyncio.sleep(_SCHEDULED_BC_TICK_SEC)
