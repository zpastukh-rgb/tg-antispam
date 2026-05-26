"""Фоновый цикл автопостинга — настройки в admin_broadcasts.autopost_json и в autopost_campaigns.autopost_json."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, text
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

_AUTOPOST_RUNTIME: dict[str, Any] = {
    "loop_started_at": None,
    "last_tick_at": None,
    "last_tick_ok_at": None,
    "ticks_total": 0,
    "lock_miss_total": 0,
    "last_error": None,
    "last_fire_at": None,
    "worker_label": (os.getenv("RAILWAY_REPLICA_ID") or os.getenv("RAILWAY_SERVICE_NAME") or os.getenv("HOSTNAME") or "local")[:80],
    "bot_token_configured": bool((os.getenv("BOT_TOKEN") or "").strip()),
}


def autopost_runtime_status() -> dict[str, Any]:
    """Снимок для /health и UI: жив ли фоновый тик расписания на этом воркере."""
    now = datetime.now(timezone.utc)
    last_ok = _AUTOPOST_RUNTIME.get("last_tick_ok_at")
    tick_stale = True
    if isinstance(last_ok, datetime):
        tick_stale = (now - last_ok).total_seconds() > 120.0
    started = _AUTOPOST_RUNTIME.get("loop_started_at")
    out: dict[str, Any] = {
        "worker_label": str(_AUTOPOST_RUNTIME.get("worker_label") or "local"),
        "bot_token_configured": bool(_AUTOPOST_RUNTIME.get("bot_token_configured")),
        "ticks_total": int(_AUTOPOST_RUNTIME.get("ticks_total") or 0),
        "lock_miss_total": int(_AUTOPOST_RUNTIME.get("lock_miss_total") or 0),
        "running_campaigns": int(_AUTOPOST_RUNTIME.get("running_campaigns") or 0),
        "tick_stale": tick_stale,
        "loop_alive": isinstance(started, datetime) and not tick_stale,
        "last_error": _AUTOPOST_RUNTIME.get("last_error"),
    }
    for k in ("loop_started_at", "last_tick_at", "last_tick_ok_at", "last_fire_at"):
        v = _AUTOPOST_RUNTIME.get(k)
        out[k] = v.isoformat() if isinstance(v, datetime) else None
    return out


# Один воркер на кластер (бот + API не дублируют тик); только PostgreSQL.
_AUTOPOST_ADVISORY_LOCK_KEY = 402_119_330

# Если последний слот пришёлся на конец окна, тик после закрытия окна всё ещё успевает отстрелять слот
# (иначе при интервале 30 с легко получить «9 из 10» за день).
_AUTOPOST_SLOT_GRACE = timedelta(hours=2)
# Слот пропущен дольше — не догоняем; ждём следующий или следующий календарный день.
_AUTOPOST_FIRE_GRACE = timedelta(minutes=15)
# Черновик в status=sending дольше — считаем зависшим (run_broadcast_job упал/рестарт).
_AUTOPOST_SENDING_STALE = timedelta(minutes=12)


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


def _clamp_dt_to_bounds(t: datetime, t0: datetime, t1: datetime) -> datetime:
    if t < t0:
        return t0
    if t > t1:
        return t1
    return t


def _first_post_anchor_datetime(for_day: date, tz, fp_hms: str) -> datetime | None:
    s = str(fp_hms or "").strip()
    if not s:
        return None
    h1, m1 = _parse_time_hm(s)
    try:
        return datetime(for_day.year, for_day.month, for_day.day, h1, m1, 0, tzinfo=tz)
    except (ValueError, TypeError):
        return None


def _segment_day_bounds_ordered(
    calendar_day: date,
    tz,
    segments_in: list[dict[str, Any]],
) -> list[tuple[int, datetime, datetime, dict[str, Any]]]:
    """Индекс исходного сегмента + [t0,t1] календарного дня для сортировки окон."""
    out: list[tuple[int, datetime, datetime, dict[str, Any]]] = []
    for i_seg, seg in enumerate(segments_in):
        if not isinstance(seg, dict):
            continue
        ws_i = str(seg.get("windowStart") or "09:00").strip()
        we_i = str(seg.get("windowEnd") or "21:00").strip()
        t0_i, t1_i = _day_window_bounds(calendar_day, tz, ws_i, we_i)
        out.append((i_seg, t0_i, t1_i, seg))
    out.sort(key=lambda x: x[1])
    return out


def _pick_anchor_segment_and_time(
    ordered: list[tuple[int, datetime, datetime, dict[str, Any]]],
    anchor_dt: datetime,
) -> tuple[int, datetime]:
    """Сегмент для якоря «первый пост» и фактическое время внутри окна (зазоры → начало следующего окна)."""
    if not ordered:
        return 0, anchor_dt
    if anchor_dt <= ordered[0][1]:
        return 0, ordered[0][1]
    if anchor_dt >= ordered[-1][2]:
        return len(ordered) - 1, _clamp_dt_to_bounds(anchor_dt, ordered[-1][1], ordered[-1][2])
    for idx, (_i0, t0, t1, _seg) in enumerate(ordered):
        if t0 <= anchor_dt <= t1:
            return idx, _clamp_dt_to_bounds(anchor_dt, t0, t1)
    for j in range(len(ordered) - 1):
        _ia, t0a, t1a, _sa = ordered[j]
        _ib, t0b, t1b, _sb = ordered[j + 1]
        if t1a < anchor_dt < t0b:
            return j + 1, t0b
    return 0, ordered[0][1]


def _compose_daily_fire_times_multi(
    *,
    tz,
    calendar_day: date,
    segments: list[dict[str, Any]],
    spread_b: bool,
    first_post_hms: str,
) -> list[datetime]:
    """Несколько окон за день: каждое окно — своё распределение; при spread один «первый пост дня»
    задаёт первый отправленный пост в том окне, куда попадает firstPostTime (или ближе к следующему окну)."""
    normed = [x for x in segments if isinstance(x, dict)]
    ordered = _segment_day_bounds_ordered(calendar_day, tz, normed)
    anchor_seg_order_idx: int | None = None
    anchor_inside: datetime | None = None
    if spread_b:
        fps = str(first_post_hms or "").strip()
        if fps:
            a = _first_post_anchor_datetime(calendar_day, tz, fps)
            if a:
                anchor_seg_order_idx, anchor_inside = _pick_anchor_segment_and_time(ordered, a)

    times: list[datetime] = []
    for ord_i, (_i_orig, t0_day, t1_day, seg) in enumerate(ordered):
        ws = str(seg.get("windowStart") or "09:00").strip()
        we = str(seg.get("windowEnd") or "21:00").strip()
        ni = max(1, min(288, int(seg.get("posts") or 1)))
        if (
            spread_b
            and anchor_seg_order_idx is not None
            and anchor_inside is not None
            and ord_i == anchor_seg_order_idx
        ):
            times.extend(
                _compose_daily_fire_times(
                    tz=tz,
                    calendar_day=calendar_day,
                    ws=ws,
                    we=we,
                    n=ni,
                    spread_b=True,
                    anchor_first_daily=True,
                    first_post_hms=f"{anchor_inside.hour:02d}:{anchor_inside.minute:02d}",
                )
            )
        else:
            times.extend(_fire_times_in_window(t0_day, t1_day, ni, spread=spread_b))
    times.sort()
    return times


def _compose_daily_fire_times(
    *,
    tz,
    calendar_day: date,
    ws: str,
    we: str,
    n: int,
    spread_b: bool,
    anchor_first_daily: bool,
    first_post_hms: str,
) -> list[datetime]:
    """При spread_b и anchor_first_daily: первый пост в first_post_hms (в пределах окна), остальные равномерно до конца окна.
    Без spread — прежняя схема t0…t1."""
    t0_day, t1_day = _day_window_bounds(calendar_day, tz, ws, we)
    if not spread_b:
        return _fire_times_in_window(t0_day, t1_day, n, spread=False)
    if not anchor_first_daily:
        return _fire_times_in_window(t0_day, t1_day, n, spread=True)
    t_first = _first_post_anchor_datetime(calendar_day, tz, first_post_hms)
    if not t_first:
        return _fire_times_in_window(t0_day, t1_day, n, spread=True)
    t_first = _clamp_dt_to_bounds(t_first, t0_day, t1_day)
    if n <= 1:
        return [t_first]
    t_lo = t_first + timedelta(minutes=1)
    if t_lo < t0_day:
        t_lo = t0_day
    if t_lo >= t1_day:
        return [t_first]
    remainder = _fire_times_in_window(t_lo, t1_day, n - 1, spread=True)
    if not remainder:
        return [t_first]
    return [t_first, *remainder]


def _ap_spread_in_window(ap: dict[str, Any]) -> bool:
    raw_spread = ap.get("spreadInWindow")
    return True if raw_spread is None else bool(raw_spread)


def _ap_weekdays_ok(ap: dict[str, Any], calendar_day: date) -> bool:
    wd = {int(x) for x in (ap.get("weekdays") or [])}
    if not wd:
        return True
    return int(calendar_day.weekday()) in wd


def compute_ap_fire_times_for_calendar_day(
    ap: dict[str, Any],
    calendar_day: date,
    tz,
) -> list[datetime]:
    """Плановые моменты отправки за календарный день (как в тике автопоста)."""
    ws = str(ap.get("windowStart") or "10:00")
    we = str(ap.get("windowEnd") or "21:00")
    spread_b = _ap_spread_in_window(ap)
    fp_hms = str(ap.get("firstPostTime") or ap.get("windowStart") or "10:00").strip()
    sw_any = ap.get("sendWindows")
    sw_segments: list[dict[str, Any]] = [x for x in sw_any if isinstance(x, dict)] if isinstance(sw_any, list) else []
    if len(sw_segments) >= 2:
        return _compose_daily_fire_times_multi(
            tz=tz,
            calendar_day=calendar_day,
            segments=sw_segments,
            spread_b=spread_b,
            first_post_hms=fp_hms,
        )
    if len(sw_segments) == 1:
        seg1 = sw_segments[0]
        ws = str(seg1.get("windowStart") or ws).strip()
        we = str(seg1.get("windowEnd") or we).strip()
        n1 = max(1, min(288, int(seg1.get("posts") or ap.get("postsPerDay") or 1)))
        return _compose_daily_fire_times(
            tz=tz,
            calendar_day=calendar_day,
            ws=ws,
            we=we,
            n=n1,
            spread_b=spread_b,
            anchor_first_daily=spread_b,
            first_post_hms=fp_hms,
        )
    n = max(1, min(288, int(ap.get("postsPerDay") or 1)))
    return _compose_daily_fire_times(
        tz=tz,
        calendar_day=calendar_day,
        ws=ws,
        we=we,
        n=n,
        spread_b=spread_b,
        anchor_first_daily=spread_b,
        first_post_hms=fp_hms,
    )


def _merge_slot_index_list(state: dict[str, Any], key: str, indices: list[int]) -> None:
    cur = {int(x) for x in (state.get(key) or []) if isinstance(x, (int, float, str))}
    for i in indices:
        try:
            cur.add(int(i))
        except (TypeError, ValueError):
            continue
    state[key] = sorted(x for x in cur if 0 <= x < 288)


def _prune_future_skipped_slots(
    state: dict[str, Any],
    fire_times: list[datetime],
    now_local: datetime,
) -> None:
    """Будущие слоты не должны оставаться в skipped_slots — только прошедшее время."""
    if not fire_times:
        state["skipped_slots"] = []
        return
    kept: list[int] = []
    for raw in state.get("skipped_slots") or []:
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(fire_times) and fire_times[idx] <= now_local:
            kept.append(idx)
    state["skipped_slots"] = sorted(set(kept))


def _resolve_schedule_calendar_day(ap: dict[str, Any], now_local: datetime, tz) -> date:
    """День расписания для _state: окно через полночь (09:00–04:00) после 00:00 ещё относится к вчера."""
    cal = now_local.date()
    yday = cal - timedelta(days=1)
    if _ap_weekdays_ok(ap, yday):
        y_times = compute_ap_fire_times_for_calendar_day(ap, yday, tz)
        if y_times:
            y_last = y_times[-1]
            if y_last.date() > yday and cal == y_last.date():
                if now_local <= y_last:
                    return yday
                if now_local <= y_last + _AUTOPOST_FIRE_GRACE:
                    return yday
    return cal


def advance_autopost_state_skip_past_slots_today(
    ap: dict[str, Any],
    *,
    now_local: datetime | None = None,
    abandon_rest_of_day_if_late_start: bool = False,
) -> None:
    """При запуске/возобновлении: не догонять прошлые слоты текущего дня.

    Если ``abandon_rest_of_day_if_late_start`` и сегодня ещё не было отправок —
    оставшиеся слоты текущего дня тоже пропускаем (следующий запуск — завтра по расписанию).
    """
    from zoneinfo import ZoneInfo

    if str(ap.get("runState") or "").lower() != "running":
        return
    state = ap.get("_state")
    if not isinstance(state, dict):
        ap["_state"] = {}
        state = ap["_state"]
    tz_name = str(ap.get("timezone") or "Europe/Moscow")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    if now_local is None:
        now_local = datetime.now(tz)
    elif now_local.tzinfo is None:
        now_local = now_local.replace(tzinfo=tz)
    else:
        now_local = now_local.astimezone(tz)
    sched_day = _resolve_schedule_calendar_day(ap, now_local, tz)
    day_key = sched_day.isoformat()
    if state.get("day") != day_key:
        state["day"] = day_key
        state["next_slot"] = 0
        state["skipped_slots"] = []
        state["sent_slots"] = []
    if not _ap_weekdays_ok(ap, sched_day):
        return
    fire_times = compute_ap_fire_times_for_calendar_day(ap, sched_day, tz)
    if not fire_times:
        return
    n = len(fire_times)
    ns = int(state.get("next_slot") or 0)
    skipped_now: list[int] = []
    sent_today = [int(x) for x in (state.get("sent_slots") or []) if isinstance(x, (int, float, str))]
    # Первый запуск дня без отправок — не догоняем прошлое сразу.
    # Уже идущий день — уважаем _AUTOPOST_FIRE_GRACE, как в тике (иначе save в 12:02 убивает слот 12:01).
    fresh_day_run = ns == 0 and not sent_today
    while ns < n:
        st = fire_times[ns]
        if st > now_local:
            break
        overdue = now_local - st
        if fresh_day_run or overdue > _AUTOPOST_FIRE_GRACE:
            skipped_now.append(ns)
            ns += 1
            continue
        break
    if skipped_now:
        _merge_slot_index_list(state, "skipped_slots", skipped_now)
    if (
        abandon_rest_of_day_if_late_start
        and skipped_now
        and not sent_today
        and ns < n
    ):
        remaining = list(range(ns, n))
        _merge_slot_index_list(state, "skipped_slots", remaining)
        state["next_slot"] = n
    else:
        state["next_slot"] = ns
    _prune_future_skipped_slots(state, fire_times, now_local)
    state.pop("run_catch_up_until", None)


def autopost_slot_status_today(ap: dict[str, Any]) -> dict[str, Any] | None:
    """Статус слотов за сегодня для UI (время, отправлено, пропущено)."""
    from zoneinfo import ZoneInfo

    if str(ap.get("runState") or "").lower() != "running":
        return None
    state = ap.get("_state")
    if not isinstance(state, dict):
        state = {}
    tz_name = str(ap.get("timezone") or "Europe/Moscow")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    now_local = datetime.now(tz)
    sched_day = _resolve_schedule_calendar_day(ap, now_local, tz)
    day_key = sched_day.isoformat()
    if not _ap_weekdays_ok(ap, sched_day):
        return None
    fire_times = compute_ap_fire_times_for_calendar_day(ap, sched_day, tz)
    if not fire_times:
        return None
    state_synced = str(state.get("day") or "") == day_key
    if state_synced:
        _prune_future_skipped_slots(state, fire_times, now_local)
    skipped = (
        {int(x) for x in (state.get("skipped_slots") or []) if isinstance(x, (int, float, str))}
        if state_synced
        else set()
    )
    sent = (
        {int(x) for x in (state.get("sent_slots") or []) if isinstance(x, (int, float, str))}
        if state_synced
        else set()
    )
    times = [f"{dt.hour:02d}:{dt.minute:02d}" for dt in fire_times]
    sent_list = sorted(i for i in sent if 0 <= i < len(times))
    skipped_list = sorted(i for i in skipped if 0 <= i < len(times))
    next_idx = int(state.get("next_slot") or 0) if state_synced else 0
    return {
        "day": day_key,
        "state_synced": state_synced,
        "times": times,
        "skipped_indices": skipped_list,
        "sent_indices": sent_list,
        "sent_times": [times[i] for i in sent_list],
        "skipped_times": [times[i] for i in skipped_list],
        "next_slot_index": next_idx,
        "next_slot_time": times[next_idx] if 0 <= next_idx < len(times) else None,
        "last_block_reason": str(state.get("last_block_reason") or "").strip() or None,
        "last_block": state.get("last_block") if isinstance(state.get("last_block"), dict) else None,
        "last_block_at": str(state.get("last_block_at") or "").strip() or None,
        "scheduler": autopost_runtime_status(),
    }


def _broadcast_has_sendable_content(row: AdminBroadcast, media_count: int) -> bool:
    text_ok = bool((row.body_text or "").strip())
    media_ok = media_count > 0 or ((row.media_kind or "none").lower() != "none" and bool(row.media_local_name))
    return text_ok or media_ok


async def _rotation_broadcast_ids(
    session: AsyncSession,
    admin_telegram_id: int,
    ap: dict[str, Any],
    *,
    rotation_first_bid: int = 0,
) -> list[int]:
    """Порядок broadcast_ids сохраняем как на клиенте; якорный id — первым (первое срабатывание с выбранным постом).

    Раньше `sorted(ids)` отправляло сначала черновик с меньшим id (часто пустой), а пост с медиа шёл вторым.
    """
    anchor = max(0, int(rotation_first_bid))

    def _dedupe_ordered(raw: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for x in raw:
            if x > 0 and x not in seen:
                seen.add(x)
                out.append(x)
        if anchor > 0 and anchor in out:
            return [anchor] + [x for x in out if x != anchor]
        return out

    if ap.get("use_all_broadcasts"):
        admin_id = int(admin_telegram_id)
        res = await session.execute(
            select(AdminBroadcast.id)
            .where(
                AdminBroadcast.admin_telegram_id == admin_id,
                AdminBroadcast.status.in_(("draft", "sending")),
                or_(
                    AdminBroadcast.cabinet_draft_scope == "autopost",
                    AdminBroadcast.cabinet_draft_scope.is_(None),
                ),
            )
            .order_by(AdminBroadcast.id.asc())
        )
        out = [int(x[0]) for x in res.all()]
        if anchor > 0 and anchor in out:
            return [anchor] + [x for x in out if x != anchor]
        return out
    ids_raw = [int(x) for x in (ap.get("broadcast_ids") or []) if int(x) > 0]
    return _dedupe_ordered(ids_raw)


async def _autopost_save_runtime_state(
    session: AsyncSession,
    persist_row: Any,
    ap: dict[str, Any],
    *,
    block_reason: str | None = None,
    block_extra: dict[str, Any] | None = None,
    clear_block: bool = False,
) -> None:
    state = ap.get("_state")
    if not isinstance(state, dict):
        return
    if clear_block:
        state.pop("last_block_reason", None)
        state.pop("last_block_at", None)
        state.pop("last_block", None)
    elif block_reason:
        state["last_block_reason"] = str(block_reason)[:120]
        state["last_block_at"] = datetime.now(timezone.utc).isoformat()
        if block_extra:
            state["last_block"] = block_extra
    persist_row.autopost_json = json.dumps(ap, ensure_ascii=False)
    await session.commit()


async def _autopost_pick_rotation_target(
    session: AsyncSession,
    *,
    owner_tid: int,
    ap: dict[str, Any],
    state: dict[str, Any],
    rotation_first_bid: int,
) -> tuple[AdminBroadcast | None, int, int, list[int]]:
    """Выбор поста из ротации; если один в sending — пробуем следующий."""
    ids = await _rotation_broadcast_ids(session, owner_tid, ap, rotation_first_bid=rotation_first_bid)
    if not ids:
        return None, 0, 0, []
    rot_start = int(state.get("rot_i") or 0) % len(ids)
    for offset in range(len(ids)):
        rot_i = (rot_start + offset) % len(ids)
        bid = int(ids[rot_i])
        target = await session.get(AdminBroadcast, bid)
        if not target:
            continue
        if await _autopost_unblock_stale_sending_broadcast(session, target):
            continue
        return target, bid, rot_i, ids
    return None, 0, rot_start, ids


async def _autopost_unblock_stale_sending_broadcast(session: AsyncSession, target: AdminBroadcast) -> bool:
    """True — черновик ещё в sending, слот пока пропускаем. False — можно слать (или сбросили зависший sending)."""
    st = (target.status or "").strip().lower()
    if st != "sending":
        return False
    uat = getattr(target, "updated_at", None)
    now_utc = datetime.now(timezone.utc)
    if uat is not None:
        if uat.tzinfo is None:
            uat = uat.replace(tzinfo=timezone.utc)
        age = now_utc - uat
        if age <= _AUTOPOST_SENDING_STALE:
            log.debug(
                "autopost wait broadcast=%s still sending age=%ss",
                int(target.id),
                int(age.total_seconds()),
            )
            return True
    log.warning(
        "autopost reset stale sending broadcast=%s updated_at=%s",
        int(target.id),
        uat,
    )
    target.status = "draft"
    err = (target.error_message or "").strip()
    if not err:
        target.error_message = "autopost_stale_sending_reset"
    session.add(target)
    await session.commit()
    return False


def _autopost_plan_signature_key(
    ap: dict[str, Any],
    *,
    ws: str,
    we: str,
    n: int,
    sig_sw: str,
    spread_b: bool,
) -> str:
    """Стабильный ключ расписания (hash, не обрезка — иначе каждый тик «менялся» plan и сбрасывался next_slot)."""
    raw = "|".join(
        [
            ws,
            we,
            str(ap.get("firstPostTime") or ""),
            str(n),
            sig_sw[:200],
            str(ap.get("timezone") or ""),
            str(ap.get("autopost_target") or "groups"),
            "1" if spread_b else "0",
            str(ap.get("startDate") or ""),
            str(ap.get("endDate") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def _autopost_process_one_loaded_ap(
    session: AsyncSession,
    *,
    owner_tid: int,
    idem_prefix: str,
    entity_pk: int,
    persist_row: Any,
    ap: dict[str, Any],
    rotation_first_bid: int = 0,
) -> None:
    """Один якорь или кампания: ap уже нормализован и содержит _state."""
    from zoneinfo import ZoneInfo

    from app.services.admin_roles import is_full_admin_user
    from app.services.chat_owner_premium import user_effective_miniapp_premium
    from app.services.user_service import get_or_create_user

    if str(ap.get("runState") or "").lower() != "running":
        return

    owner = await get_or_create_user(session, int(owner_tid))
    now_utc = datetime.now(timezone.utc)
    if not is_full_admin_user(owner, int(owner_tid)) and not user_effective_miniapp_premium(owner, now_utc):
        ap["runState"] = "stopped"
        state = ap.get("_state")
        if isinstance(state, dict):
            state["stop_reason"] = "premium_expired"
        else:
            ap["_state"] = {"stop_reason": "premium_expired"}
        persist_row.autopost_json = json.dumps(ap, ensure_ascii=False)
        await session.commit()
        return

    tz_name = str(ap.get("timezone") or "Europe/Moscow")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    now_local = datetime.now(tz)
    start_date: date | None = None
    start_date_raw = str(ap.get("startDate") or "").strip()
    if start_date_raw:
        try:
            sy, sm, sd = start_date_raw.split("-")
            start_date = date(int(sy), int(sm), int(sd))
        except Exception:
            start_date = None
        if start_date and now_local.date() < start_date:
            return
    end_date_raw = str(ap.get("endDate") or "").strip()
    if end_date_raw:
        try:
            ey, em, ed = end_date_raw.split("-")
            end_dt = date(int(ey), int(em), int(ed))
        except Exception:
            end_dt = None
        if end_dt and now_local.date() > end_dt:
            return

    sched_day = _resolve_schedule_calendar_day(ap, now_local, tz)
    if not _ap_weekdays_ok(ap, sched_day):
        return

    g_ids = [int(x) for x in (ap.get("group_chat_ids") or []) if int(x) < 0]
    c_ids = [int(x) for x in (ap.get("channel_chat_ids") or []) if int(x) < 0]
    if bool(ap.get("autopost_channels_disabled")):
        c_ids = []
    merged_ids = sorted(set(g_ids + c_ids))

    # Кампания (apc): без явно выбранных чатов не шлём в «все группы бота» — иначе 0 получателей в UI и отправка всем подряд.
    if idem_prefix == "apc" and not merged_ids:
        log.warning(
            "autopost campaign %s: нет групп/каналов в настройках — пропуск (укажите получателей в кампании)",
            entity_pk,
        )
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="no_destinations",
        )
        return

    ws = str(ap.get("windowStart") or "10:00")
    we = str(ap.get("windowEnd") or "21:00")
    sw_any = ap.get("sendWindows")
    sw_segments: list[dict[str, Any]] = [x for x in sw_any if isinstance(x, dict)] if isinstance(sw_any, list) else []

    fire_times = compute_ap_fire_times_for_calendar_day(ap, sched_day, tz)
    if not fire_times:
        return

    n = len(fire_times)

    try:
        sig_sw = json.dumps(sw_segments, ensure_ascii=False, sort_keys=True) if sw_segments else ""
    except Exception:
        sig_sw = str(sw_segments)

    state = ap["_state"]
    spread_b = _ap_spread_in_window(ap)
    plan_sig = _autopost_plan_signature_key(ap, ws=ws, we=we, n=n, sig_sw=sig_sw, spread_b=spread_b)
    stored_sig = str(state.get("plan_sig") or "")
    if stored_sig and (len(stored_sig) != 32 or not all(c in "0123456789abcdef" for c in stored_sig.lower())):
        state.pop("plan_sig", None)
    plan_changed = False
    if state.get("plan_sig") != plan_sig:
        state["plan_sig"] = plan_sig
        state["next_slot"] = 0
        state["skipped_slots"] = []
        state["sent_slots"] = []
        plan_changed = True

    day_key = sched_day.isoformat()
    day_changed = False
    if state.get("day") != day_key:
        state["day"] = day_key
        state["next_slot"] = 0
        state["skipped_slots"] = []
        state["sent_slots"] = []
        day_changed = True

    if plan_changed or day_changed:
        persist_row.autopost_json = json.dumps(ap, ensure_ascii=False)
        await session.commit()

    next_slot = int(state.get("next_slot") or 0)
    if next_slot >= n:
        return

    # Пропуск просроченных слотов без «догоняющей» пачки: отправляем только если опоздание ≤ grace.
    ns = next_slot
    late_skip: list[int] = []
    while ns < n:
        st = fire_times[ns]
        if st > now_local:
            break
        if (now_local - st) > _AUTOPOST_FIRE_GRACE:
            late_skip.append(ns)
            ns += 1
            continue
        break
    if late_skip:
        _merge_slot_index_list(state, "skipped_slots", late_skip)
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

    if len(sw_segments) >= 2:
        in_any = False
        for seg in sw_segments:
            if not isinstance(seg, dict):
                continue
            s_ws = str(seg.get("windowStart") or "09:00").strip()
            s_we = str(seg.get("windowEnd") or "21:00").strip()
            if _active_window_bounds(now_local, s_ws, s_we) is not None:
                in_any = True
                break
        if not in_any:
            grace_ok = slot_ready and (now_local - slot_time) <= _AUTOPOST_SLOT_GRACE and (
                slot_time.date() == now_local.date() or sched_day < now_local.date()
            )
            if not grace_ok:
                return
    else:
        bounds_active = _active_window_bounds(now_local, ws, we)
        if bounds_active is None:
            grace_ok = slot_ready and (now_local - slot_time) <= _AUTOPOST_SLOT_GRACE and (
                slot_time.date() == now_local.date() or sched_day < now_local.date()
            )
            if not grace_ok:
                return

    target, bid, rot_i, ids = await _autopost_pick_rotation_target(
        session,
        owner_tid=owner_tid,
        ap=ap,
        state=state,
        rotation_first_bid=rotation_first_bid,
    )
    if not ids:
        log.warning("autopost %s=%s: пустая ротация постов", idem_prefix, entity_pk)
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="empty_rotation",
        )
        return
    if not target:
        log.warning(
            "autopost %s=%s: все посты ротации заняты (sending), slot=%s",
            idem_prefix,
            entity_pk,
            next_slot,
        )
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="rotation_busy_sending",
            block_extra={"slot_index": int(next_slot)},
        )
        return

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

    mc_q = await session.execute(select(AdminBroadcastMedia).where(AdminBroadcastMedia.broadcast_id == int(target.id)))
    media_count = len(list(mc_q.scalars().all()))
    if not _broadcast_has_sendable_content(target, media_count):
        log.warning("autopost skip broadcast=%s: нет текста и медиа", bid)
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="empty_content",
            block_extra={"broadcast_id": int(bid)},
        )
        return

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
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="bot_token_missing",
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
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="recipients_filtered",
        )
        return
    if not resolved:
        log.warning("autopost %s=%s broadcast=%s: нет групп для отправки", idem_prefix, entity_pk, bid)
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="no_recipients",
        )
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
        await _autopost_save_runtime_state(
            session,
            persist_row,
            ap,
            block_reason="insufficient_aurum",
            block_extra={
                "need_tokens": int(cost),
                "have_aurum": float(getattr(billing_user, "aurum_credits", 0.0) or 0.0),
                "slot_index": int(next_slot),
            },
        )
        return

    _merge_slot_index_list(state, "sent_slots", [slot_firing])
    state["next_slot"] = next_slot + 1
    state["rot_i"] = rot_i + 1
    state.pop("run_catch_up_until", None)
    state.pop("last_block_reason", None)
    state.pop("last_block_at", None)
    state.pop("last_block", None)
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
    _AUTOPOST_RUNTIME["last_fire_at"] = datetime.now(timezone.utc)

    apc_id = int(entity_pk) if idem_prefix == "apc" else None
    asyncio.create_task(
        run_broadcast_job(
            int(bid),
            "groups",
            resolved,
            keep_draft_after=True,
            run_source="autopost",
            autopost_campaign_id=apc_id,
        ),
    )


async def autopost_tick_once() -> None:
    now_utc = datetime.now(timezone.utc)
    _AUTOPOST_RUNTIME["last_tick_at"] = now_utc
    session = await get_session()
    async with session:
        if not await _autopost_try_advisory_lock(session):
            _AUTOPOST_RUNTIME["lock_miss_total"] = int(_AUTOPOST_RUNTIME.get("lock_miss_total") or 0) + 1
            miss_n = int(_AUTOPOST_RUNTIME["lock_miss_total"])
            if miss_n == 1 or miss_n % 30 == 0:
                log.info(
                    "autopost_tick: advisory lock busy (another worker ticks?) miss=%s worker=%s",
                    miss_n,
                    _AUTOPOST_RUNTIME.get("worker_label"),
                )
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
                        rot = await _rotation_broadcast_ids(
                            session,
                            t,
                            ap,
                            rotation_first_bid=int(getattr(camp, "anchor_broadcast_id", 0) or 0),
                        )
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
                    rotation_first_bid=int(getattr(camp, "anchor_broadcast_id", 0) or 0),
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
                    rotation_first_bid=int(anchor.id),
                )

            _AUTOPOST_RUNTIME["last_tick_ok_at"] = datetime.now(timezone.utc)
            _AUTOPOST_RUNTIME["ticks_total"] = int(_AUTOPOST_RUNTIME.get("ticks_total") or 0) + 1
            _AUTOPOST_RUNTIME["last_error"] = None
            running_n = 0
            for camp in campaigns:
                raw_txt = (camp.autopost_json or "").strip()
                if not raw_txt:
                    continue
                try:
                    raw = json.loads(raw_txt)
                except Exception:
                    continue
                if isinstance(raw, dict) and str(raw.get("runState") or "").lower() == "running":
                    running_n += 1
            _AUTOPOST_RUNTIME["running_campaigns"] = running_n

        finally:
            await _autopost_advisory_unlock(session)


def autopost_tick_interval_sec(explicit: float | None = None) -> float:
    """Интервал опроса расписания. Меньше = ближе к минуте слота (но больше нагрузка на БД)."""
    if explicit is not None:
        try:
            return max(5.0, min(60.0, float(explicit)))
        except (TypeError, ValueError):
            pass
    raw = (os.getenv("AUTOPOST_TICK_SEC") or "10").strip()
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = 10.0
    return max(5.0, min(60.0, v))


async def autopost_loop(interval_sec: float | None = None) -> None:
    tick = autopost_tick_interval_sec(interval_sec)
    _AUTOPOST_RUNTIME["loop_started_at"] = datetime.now(timezone.utc)
    _AUTOPOST_RUNTIME["bot_token_configured"] = bool((os.getenv("BOT_TOKEN") or "").strip())
    log.info(
        "autopost_loop started worker=%s interval=%ss bot_token=%s",
        _AUTOPOST_RUNTIME.get("worker_label"),
        tick,
        "yes" if _AUTOPOST_RUNTIME["bot_token_configured"] else "NO",
    )
    print(
        f"autopost_loop started worker={_AUTOPOST_RUNTIME.get('worker_label')} interval={tick}s",
        flush=True,
    )
    tick_n = 0
    while True:
        try:
            await autopost_tick_once()
            tick_n += 1
            if tick_n == 1 or tick_n % 30 == 0:
                st = autopost_runtime_status()
                log.info(
                    "autopost_loop heartbeat tick=%s interval=%ss alive=%s lock_miss=%s",
                    tick_n,
                    tick,
                    st.get("loop_alive"),
                    st.get("lock_miss_total"),
                )
        except Exception as exc:
            _AUTOPOST_RUNTIME["last_error"] = str(exc)[:240]
            log.exception("autopost_tick_once")
        await asyncio.sleep(tick)
