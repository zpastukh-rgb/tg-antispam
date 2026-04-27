"""Фоновый цикл автопостинга — настройки в admin_broadcasts.autopost_json и в autopost_campaigns.autopost_json."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AdminBroadcast, AdminBroadcastMedia, AutopostCampaign
from app.db.session import get_session
from app.services.admin_broadcast import normalize_autopost_payload, run_broadcast_job, sanitize_autopost_state
from app.services.admin_roles import is_full_admin_user
from app.services.broadcast_send_plan import (
    broadcast_charge_tokens,
    debit_user_broadcast_tokens,
    estimate_recipient_counts,
    resolve_broadcast_target_chat_ids,
)
from app.services.user_service import get_or_create_user

log = logging.getLogger(__name__)

# Один воркер на кластер (бот + API не дублируют тик); только PostgreSQL.
_AUTOPOST_ADVISORY_LOCK_KEY = 402_119_330

# Если последний слот пришёлся на конец окна, тик после закрытия окна всё ещё успевает отстрелять слот
# (иначе при интервале 30 с легко получить «9 из 10» за день).
_AUTOPOST_SLOT_GRACE = timedelta(hours=2)
# Слот «устарел» дольше — не догоняем подряд (как пачка за минуту); пропускаем и идём к ближайшему в окне
_AUTOPOST_MISSED_MAX_LATE = timedelta(minutes=50)


async def _autopost_try_advisory_lock(session: AsyncSession) -> bool:
    bind = session.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return True
    try:
        r = await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _AUTOPOST_ADVISORY_LOCK_KEY})
        return bool(r.scalar())
    except Exception:
        log.debug("autopost: advisory lock unavailable", exc_info=True)
        return True


async def _autopost_advisory_unlock(session: AsyncSession) -> None:
    bind = session.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return
    try:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _AUTOPOST_ADVISORY_LOCK_KEY})
    except Exception:
        pass


def _parse_time_hm(s: str) -> tuple[int, int]:
    parts = (s or "00:00").strip().split(":", 1)
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return 0, 0
    return max(0, min(23, h)), max(0, min(59, m))


def _active_window_bounds(
    now_local: datetime,
    window_start: str,
    window_end: str,
) -> tuple[datetime, datetime] | None:
    """Окно [t0, t1] в локальном TZ, в которое попадает now_local (в т.ч. ночное через полночь)."""
    from zoneinfo import ZoneInfo

    tz = now_local.tzinfo or ZoneInfo("UTC")
    h1, m1 = _parse_time_hm(window_start)
    h2, m2 = _parse_time_hm(window_end)
    for day_off in (-1, 0, 1):
        base = now_local.date() + timedelta(days=day_off)
        t0 = datetime(base.year, base.month, base.day, h1, m1, 0, tzinfo=tz)
        t1 = datetime(base.year, base.month, base.day, h2, m2, 0, tzinfo=tz)
        if t1 <= t0:
            t1 += timedelta(days=1)
        if t0 <= now_local <= t1:
            return t0, t1
    return None


def _day_window_bounds(for_day: date, tz, window_start: str, window_end: str) -> tuple[datetime, datetime]:
    """Окно [t0, t1] для календарной даты (локальное время), без проверки «сейчас внутри»."""
    h1, m1 = _parse_time_hm(window_start)
    h2, m2 = _parse_time_hm(window_end)
    t0 = datetime(for_day.year, for_day.month, for_day.day, h1, m1, 0, tzinfo=tz)
    t1 = datetime(for_day.year, for_day.month, for_day.day, h2, m2, 0, tzinfo=tz)
    if t1 <= t0:
        t1 += timedelta(days=1)
    return t0, t1


def _fire_times_in_window(t0: datetime, t1: datetime, n: int, *, spread: bool = True) -> list[datetime]:
    """
    Моменты публикаций в окне [t0, t1].

    spread=True (как чекбокс «Равномерно»): шаг = длина_окна / n, посты в t0+step, t0+2*step, …, t1
    (первый не в самый старт окна — не срывает пачку «сразу всё в начале»).

    spread=False: старая схема — первая в t0, последняя в t1, шаг = окно/(n-1).
    """
    span = (t1 - t0).total_seconds()
    if n <= 0:
        return []
    if n == 1:
        if span <= 0:
            return [t0]
        if spread:
            return [t0 + timedelta(seconds=span / 2.0)]
        return [t0]
    if span <= 0:
        return [t0] * n
    if spread:
        return [t0 + timedelta(seconds=span * (k + 1) / n) for k in range(n)]
    return [t0 + timedelta(seconds=span * k / (n - 1)) for k in range(n)]


def _broadcast_has_sendable_content(row: AdminBroadcast, media_count: int) -> bool:
    text_ok = bool((row.body_text or "").strip())
    media_ok = media_count > 0 or ((row.media_kind or "none").lower() != "none" and bool(row.media_local_name))
    return text_ok or media_ok




async def _rotation_broadcast_ids(session: AsyncSession, admin_telegram_id: int, ap: dict[str, Any]) -> list[int]:
    if ap.get("use_all_broadcasts"):
        admin_id = int(admin_telegram_id)
        res = await session.execute(
            select(AdminBroadcast.id)
            .where(
                AdminBroadcast.admin_telegram_id == admin_id,
                AdminBroadcast.status == "draft",
            )
            .order_by(AdminBroadcast.id.asc())
        )
        return [int(x[0]) for x in res.all()]
    ids = [int(x) for x in (ap.get("broadcast_ids") or []) if int(x) > 0]
    return sorted(set(ids))


async def _autopost_process_one_loaded_ap(
    session: AsyncSession,
    *,
    owner_tid: int,
    idem_prefix: str,
    entity_pk: int,
    persist_row: Any,
    ap: dict[str, Any],
) -> None:
    """Один якорь или кампания: ap уже нормализован и содержит _state."""
    from zoneinfo import ZoneInfo

    if str(ap.get("runState") or "").lower() != "running":
        return

    tz_name = str(ap.get("timezone") or "Europe/Moscow")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    now_local = datetime.now(tz)
    if int(now_local.weekday()) not in {int(x) for x in (ap.get("weekdays") or [])}:
        return

    ws = str(ap.get("windowStart") or "10:00")
    we = str(ap.get("windowEnd") or "21:00")
    n = int(ap.get("postsPerDay") or 1)
    n = max(1, min(288, n))

    raw_spread = ap.get("spreadInWindow")
    spread_b = True if raw_spread is None else bool(raw_spread)

    t0, t1 = _day_window_bounds(now_local.date(), tz, ws, we)
    fire_times = _fire_times_in_window(t0, t1, n, spread=spread_b)
    if not fire_times:
        return

    state = ap["_state"]
    plan_sig = "|".join(
        [
            ws,
            we,
            str(n),
            str(ap.get("timezone") or ""),
            str(ap.get("autopost_target") or "groups"),
            "1" if spread_b else "0",
        ]
    )
    if state.get("plan_sig") != plan_sig:
        state["plan_sig"] = plan_sig[:120]
        state["next_slot"] = 0

    day_key = now_local.date().isoformat()
    if state.get("day") != day_key:
        state["day"] = day_key
        state["next_slot"] = 0

    next_slot = int(state.get("next_slot") or 0)
    if next_slot >= n:
        return

    # Пропуск «устаревших» слотов только при n>1: иначе при postsPerDay=1 один пропуск >50 мин
    # выставлял next_slot>=n и автопост молча не работал до следующего календарного дня.
    if n > 1:
        ns = next_slot
        while ns < n and (now_local - fire_times[ns]) > _AUTOPOST_MISSED_MAX_LATE:
            ns += 1
        if ns != next_slot:
            state["next_slot"] = ns
            persist_row.autopost_json = json.dumps(ap, ensure_ascii=False)
            await session.commit()
            if ns >= n:
                return
            next_slot = ns

    slot_time = fire_times[next_slot]
    slot_ready = slot_time <= now_local
    if not slot_ready:
        return

    bounds_active = _active_window_bounds(now_local, ws, we)
    if bounds_active is None:
        grace_ok = slot_ready and (now_local - slot_time) <= _AUTOPOST_SLOT_GRACE and slot_time.date() == now_local.date()
        if not grace_ok:
            return

    ids = await _rotation_broadcast_ids(session, owner_tid, ap)
    if not ids:
        log.warning("autopost %s=%s: пустая ротация постов", idem_prefix, entity_pk)
        return

    rot_i = int(state.get("rot_i") or 0) % len(ids)
    bid = ids[rot_i]
    log.info(
        "autopost rotation %s entity=%s owner=%s rot_i=%s len=%s ids=%s chosen_bid=%s slot=%s/%s",
        idem_prefix,
        entity_pk,
        owner_tid,
        rot_i,
        len(ids),
        ids[:30],
        bid,
        next_slot,
        n,
    )
    target = await session.get(AdminBroadcast, int(bid))
    if not target or (target.status or "") == "sending":
        return

    mc_q = await session.execute(select(AdminBroadcastMedia).where(AdminBroadcastMedia.broadcast_id == int(target.id)))
    media_count = len(list(mc_q.scalars().all()))
    if not _broadcast_has_sendable_content(target, media_count):
        log.warning("autopost skip broadcast=%s: нет текста и медиа", bid)
        return

    g_ids = [int(x) for x in (ap.get("group_chat_ids") or []) if int(x) < 0]
    c_ids = [int(x) for x in (ap.get("channel_chat_ids") or []) if int(x) < 0]
    if bool(ap.get("autopost_channels_disabled")):
        c_ids = []
    merged_ids = sorted(set(g_ids + c_ids))
    if not owner_tid:
        log.warning("autopost %s=%s: нет owner", idem_prefix, entity_pk)
        return

    bot_token = (os.getenv("BOT_TOKEN") or "").strip()
    if not bot_token:
        log.warning(
            "autopost %s=%s broadcast=%s: BOT_TOKEN не задан — отправка невозможна, слот пропущен без списания",
            idem_prefix,
            entity_pk,
            bid,
        )
        return

    billing_user = await get_or_create_user(session, owner_tid)
    full_owner = is_full_admin_user(billing_user, owner_tid)
    resolved = await resolve_broadcast_target_chat_ids(
        session,
        viewer_telegram_id=owner_tid,
        allow_all_groups=full_owner,
        target="groups",
        body_chat_ids=merged_ids,
    )
    if merged_ids and not resolved:
        log.warning("autopost %s=%s broadcast=%s: группы/каналы не прошли фильтр", idem_prefix, entity_pk, bid)
        return
    if not resolved:
        log.warning("autopost %s=%s broadcast=%s: нет групп для отправки", idem_prefix, entity_pk, bid)
        return

    _n_users, n_groups = await estimate_recipient_counts(session, target="groups", target_chat_ids=resolved)
    cost = broadcast_charge_tokens(n_users=_n_users, n_groups=n_groups)
    slot_firing = int(next_slot)
    idem_base = f"{idem_prefix}:{int(entity_pk)}:{int(bid)}:{day_key}:n{slot_firing}"

    try:
        await debit_user_broadcast_tokens(
            session,
            user=billing_user,
            full_admin=full_owner,
            broadcast_id=int(bid),
            cost_tokens=int(cost),
            idempotency_key_base=idem_base,
        )
    except ValueError:
        log.warning(
            "autopost insufficient tokens %s=%s broadcast=%s owner=%s need=%s aurum=%.2f",
            idem_prefix,
            entity_pk,
            bid,
            owner_tid,
            int(cost),
            float(getattr(billing_user, "aurum_credits", 0.0) or 0.0),
        )
        return

    state["next_slot"] = next_slot + 1
    state["rot_i"] = rot_i + 1
    persist_row.autopost_json = json.dumps(ap, ensure_ascii=False)

    target.status = "sending"
    target.last_target = "groups"
    target.sent_at = None
    target.recipient_ok = 0
    target.recipient_fail = 0
    target.error_message = None
    session.add(persist_row)
    session.add(target)
    session.add(billing_user)
    await session.commit()

    log.warning(
        "autopost fire %s=%s broadcast=%s slot=%s/%s groups=%s cost_tokens=%s idem=%s",
        idem_prefix,
        entity_pk,
        bid,
        next_slot + 1,
        n,
        len(resolved),
        int(cost),
        idem_base,
    )

    asyncio.create_task(
        run_broadcast_job(int(bid), "groups", resolved, keep_draft_after=True, run_source="autopost"),
    )


async def autopost_tick_once() -> None:
    session = await get_session()
    async with session:
        if not await _autopost_try_advisory_lock(session):
            return
        try:
            cq = await session.execute(
                select(AutopostCampaign).where(
                    AutopostCampaign.autopost_json.isnot(None),
                    AutopostCampaign.autopost_json != "",
                )
            )
            campaigns = list(cq.scalars().all())
            owners_with_running_campaign: set[int] = set()
            for camp in campaigns:
                raw_txt = (camp.autopost_json or "").strip()
                if not raw_txt:
                    continue
                try:
                    raw = json.loads(raw_txt)
                except Exception:
                    continue
                if not isinstance(raw, dict):
                    continue
                clean = {k: v for k, v in raw.items() if k != "_state"}
                ap = normalize_autopost_payload(clean)
                if not ap:
                    continue
                # Блокируем черновик только если кампания реально может крутить посты (иначе «зомби» running
                # с пустой ротацией глушит якорный автопост навсегда).
                if str(ap.get("runState") or "").lower() == "running":
                    t = int(getattr(camp, "admin_telegram_id", 0) or 0)
                    if t:
                        rot = await _rotation_broadcast_ids(session, t, ap)
                        if rot:
                            owners_with_running_campaign.add(t)
                prev_state = raw.get("_state")
                ap["_state"] = sanitize_autopost_state(prev_state) if isinstance(prev_state, dict) else {}
                owner_tid = int(getattr(camp, "admin_telegram_id", 0) or 0)
                await _autopost_process_one_loaded_ap(
                    session,
                    owner_tid=owner_tid,
                    idem_prefix="apc",
                    entity_pk=int(camp.id),
                    persist_row=camp,
                    ap=ap,
                )

            res = await session.execute(
                select(AdminBroadcast)
                .options(selectinload(AdminBroadcast.media_items))
                .where(AdminBroadcast.autopost_json.isnot(None))
                .where(AdminBroadcast.autopost_json != "")
            )
            anchors = list(res.scalars().all())
            for anchor in anchors:
                owner_tid_anc = int(getattr(anchor, "admin_telegram_id", 0) or 0)
                if owner_tid_anc and owner_tid_anc in owners_with_running_campaign:
                    log.debug(
                        "autopost skip draft anchor id=%s owner=%s: running autopost campaign takes precedence",
                        int(anchor.id),
                        owner_tid_anc,
                    )
                    continue
                raw_txt = (anchor.autopost_json or "").strip()
                if not raw_txt:
                    continue
                try:
                    raw = json.loads(raw_txt)
                except Exception:
                    continue
                if not isinstance(raw, dict):
                    continue
                clean = {k: v for k, v in raw.items() if k != "_state"}
                ap = normalize_autopost_payload(clean)
                if not ap:
                    continue
                prev_state = raw.get("_state")
                ap["_state"] = sanitize_autopost_state(prev_state) if isinstance(prev_state, dict) else {}
                await _autopost_process_one_loaded_ap(
                    session,
                    owner_tid=owner_tid_anc,
                    idem_prefix="apb",
                    entity_pk=int(anchor.id),
                    persist_row=anchor,
                    ap=ap,
                )

        finally:
            await _autopost_advisory_unlock(session)


async def autopost_loop(interval_sec: float = 30.0) -> None:
    log.info("autopost_loop started (interval=%ss)", interval_sec)
    while True:
        try:
            await autopost_tick_once()
        except Exception:
            log.exception("autopost_tick_once")
        await asyncio.sleep(max(10.0, float(interval_sec)))
