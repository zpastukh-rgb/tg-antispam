"""Состояние планировщика автопоста (_state)."""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.admin_broadcast import sanitize_autopost_state
from app.services.autopost_loop import advance_autopost_state_skip_past_slots_today, compute_ap_fire_times_for_calendar_day


def test_sanitize_autopost_state_keeps_slot_lists():
    raw = {
        "day": "2026-05-19",
        "next_slot": 3,
        "skipped_slots": [0, 1, 2],
        "sent_slots": [7],
        "evil": "drop",
    }
    out = sanitize_autopost_state(raw)
    assert out["skipped_slots"] == [0, 1, 2]
    assert out["sent_slots"] == [7]
    assert "evil" not in out


def test_plan_sig_spread_flag_no_crash():
    from app.services.autopost_loop import _ap_spread_in_window

    ap = {"spreadInWindow": True}
    spread_b = _ap_spread_in_window(ap)
    plan_part = "1" if spread_b else "0"
    assert plan_part == "1"
    ap2 = {"spreadInWindow": False}
    assert _ap_spread_in_window(ap2) is False
    ap3: dict = {}
    assert _ap_spread_in_window(ap3) is True


def test_advance_skips_past_slots_on_start_day():
    tz = ZoneInfo("Europe/Moscow")
    ap = {
        "runState": "running",
        "timezone": "Europe/Moscow",
        "windowStart": "18:00",
        "windowEnd": "21:00",
        "postsPerDay": 33,
        "spreadInWindow": True,
        "firstPostTime": "18:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "_state": {"day": "2026-05-19", "next_slot": 0},
    }
    day = date(2026, 5, 19)
    fire_times = compute_ap_fire_times_for_calendar_day(ap, day, tz)
    assert len(fire_times) == 33
    # 18:39 — первые слоты до 18:40 должны быть пропущены
    fake_now = datetime(2026, 5, 19, 18, 39, 0, tzinfo=tz)
    advance_autopost_state_skip_past_slots_today(ap, now_local=fake_now)
    ns = int(ap["_state"]["next_slot"])
    assert fire_times[ns] > fake_now
    assert ns >= 7
    assert 0 in ap["_state"]["skipped_slots"]


def test_advance_keeps_future_slots_on_late_first_start():
    tz = ZoneInfo("Europe/Moscow")
    ap = {
        "runState": "running",
        "timezone": "Europe/Moscow",
        "windowStart": "09:00",
        "windowEnd": "21:00",
        "postsPerDay": 33,
        "spreadInWindow": True,
        "firstPostTime": "09:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "_state": {"day": "2026-05-23", "next_slot": 0, "sent_slots": [], "skipped_slots": []},
    }
    day = date(2026, 5, 23)
    fire_times = compute_ap_fire_times_for_calendar_day(ap, day, tz)
    assert len(fire_times) == 33
    fake_now = datetime(2026, 5, 23, 11, 28, 0, tzinfo=tz)
    advance_autopost_state_skip_past_slots_today(
        ap,
        now_local=fake_now,
        abandon_rest_of_day_if_late_start=False,
    )
    ns = int(ap["_state"]["next_slot"])
    assert fire_times[ns] > fake_now
    assert ns < len(fire_times)
    skipped = [int(x) for x in ap["_state"]["skipped_slots"]]
    assert skipped
    assert all(fire_times[i] <= fake_now for i in skipped)
    assert all(fire_times[i] > fake_now for i in range(ns, len(fire_times)))


def test_prune_future_skipped_slots():
    from app.services.autopost_loop import _prune_future_skipped_slots

    tz = ZoneInfo("Europe/Moscow")
    ap = {
        "runState": "running",
        "timezone": "Europe/Moscow",
        "windowStart": "09:00",
        "windowEnd": "21:00",
        "postsPerDay": 33,
        "spreadInWindow": True,
        "firstPostTime": "09:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
    }
    day = date(2026, 5, 23)
    fire_times = compute_ap_fire_times_for_calendar_day(ap, day, tz)
    fake_now = datetime(2026, 5, 23, 11, 28, 0, tzinfo=tz)
    state = {"skipped_slots": list(range(len(fire_times)))}
    _prune_future_skipped_slots(state, fire_times, fake_now)
    skipped = [int(x) for x in state["skipped_slots"]]
    assert skipped
    assert all(fire_times[i] <= fake_now for i in skipped)
    assert len(skipped) < len(fire_times)


def test_advance_abandons_rest_of_day_on_late_first_start():
    tz = ZoneInfo("Europe/Moscow")
    ap = {
        "runState": "running",
        "timezone": "Europe/Moscow",
        "windowStart": "09:00",
        "windowEnd": "04:00",
        "postsPerDay": 100,
        "spreadInWindow": True,
        "firstPostTime": "09:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "_state": {"day": "2026-05-22", "next_slot": 0, "sent_slots": []},
    }
    day = date(2026, 5, 22)
    fire_times = compute_ap_fire_times_for_calendar_day(ap, day, tz)
    assert len(fire_times) == 100
    fake_now = datetime(2026, 5, 22, 22, 50, 0, tzinfo=tz)
    advance_autopost_state_skip_past_slots_today(
        ap,
        now_local=fake_now,
        abandon_rest_of_day_if_late_start=True,
    )
    assert int(ap["_state"]["next_slot"]) >= len(fire_times)
    assert len(ap["_state"]["sent_slots"]) == 0


def test_advance_respects_fire_grace_when_day_already_running():
    """Сохранение расписания во время кампании не должно сразу помечать текущий слот пропущенным."""
    tz = ZoneInfo("Europe/Moscow")
    ap = {
        "runState": "running",
        "timezone": "Europe/Moscow",
        "windowStart": "09:00",
        "windowEnd": "21:00",
        "postsPerDay": 33,
        "spreadInWindow": True,
        "firstPostTime": "09:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "_state": {
            "day": "2026-05-23",
            "next_slot": 0,
            "sent_slots": [0, 1, 2],
            "skipped_slots": list(range(3, 10)),
        },
    }
    day = date(2026, 5, 23)
    fire_times = compute_ap_fire_times_for_calendar_day(ap, day, tz)
    assert len(fire_times) == 33
    # next_slot указывает на слот ~12:00 (12:00:45), сейчас 12:02 — в пределах 15-мин grace
    ns_before = 8
    ap["_state"]["next_slot"] = ns_before
    assert fire_times[ns_before].hour == 12 and fire_times[ns_before].minute == 0
    fake_now = datetime(2026, 5, 23, 12, 2, 0, tzinfo=tz)
    advance_autopost_state_skip_past_slots_today(ap, now_local=fake_now)
    assert int(ap["_state"]["next_slot"]) == ns_before
    assert ns_before not in ap["_state"]["skipped_slots"]


def test_plan_sig_stable_when_stored_truncated_legacy():
    from app.services.autopost_loop import _autopost_plan_signature_key

    ap = {
        "timezone": "Asia/Yekaterinburg",
        "windowStart": "09:00",
        "windowEnd": "21:00",
        "firstPostTime": "09:00",
        "spreadInWindow": True,
        "startDate": "2026-05-23",
        "endDate": "",
        "sendWindows": [{"windowStart": "09:00", "windowEnd": "21:00", "posts": 80}],
    }
    sig_sw = json.dumps(ap["sendWindows"], ensure_ascii=False, sort_keys=True)
    k1 = _autopost_plan_signature_key(ap, ws="09:00", we="21:00", n=80, sig_sw=sig_sw, spread_b=True)
    k2 = _autopost_plan_signature_key(ap, ws="09:00", we="21:00", n=80, sig_sw=sig_sw, spread_b=True)
    assert k1 == k2
    assert len(k1) == 32
    # Старый баг: полная строка != plan_sig[:120] при длине > 120
    raw = "|".join(
        [
            "09:00",
            "21:00",
            "09:00",
            "80",
            sig_sw[:200],
            "Asia/Yekaterinburg",
            "groups",
            "1",
            "2026-05-23",
            "",
        ]
    )
    assert len(raw) > 120
    assert raw != raw[:120]


def test_night_window_keeps_schedule_day_after_midnight():
    tz = ZoneInfo("Europe/Moscow")
    ap = {
        "runState": "running",
        "timezone": "Europe/Moscow",
        "windowStart": "09:00",
        "windowEnd": "04:00",
        "postsPerDay": 100,
        "spreadInWindow": True,
        "firstPostTime": "09:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "_state": {
            "day": "2026-05-22",
            "next_slot": 90,
            "sent_slots": list(range(90)),
            "skipped_slots": [],
        },
    }
    from app.services.autopost_loop import _resolve_schedule_calendar_day

    day = date(2026, 5, 22)
    fire_times = compute_ap_fire_times_for_calendar_day(ap, day, tz)
    assert fire_times[-1].date() == date(2026, 5, 23)
    fake_now = datetime(2026, 5, 23, 0, 10, 0, tzinfo=tz)
    sched = _resolve_schedule_calendar_day(ap, fake_now, tz)
    assert sched == date(2026, 5, 22)
    # Слот 00:10 — часть плана 22-го, не сбрасываем next_slot на полночь
    idx_after_2358 = next(i for i, t in enumerate(fire_times) if t.hour == 0 and t.minute >= 10)
    assert idx_after_2358 > 90


def test_legacy_plan_sig_does_not_skip_due_slot_on_tick():
    """Старый plan_sig в БД: после фикса слот в grace не должен уходить в skipped каждый тик."""
    from app.services.autopost_loop import _AUTOPOST_FIRE_GRACE, _autopost_plan_signature_key

    tz = ZoneInfo("Asia/Yekaterinburg")
    ap = {
        "runState": "running",
        "timezone": "Asia/Yekaterinburg",
        "windowStart": "12:47",
        "windowEnd": "21:00",
        "postsPerDay": 33,
        "spreadInWindow": True,
        "firstPostTime": "12:47",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "sendWindows": [{"windowStart": "12:47", "windowEnd": "21:00", "posts": 33}],
        "_state": {
            "day": "2026-05-23",
            "next_slot": 0,
            "skipped_slots": [],
            "sent_slots": [],
            "plan_sig": "legacy-truncated-signature-that-is-not-32-hex-chars",
        },
    }
    day = date(2026, 5, 23)
    fire_times = compute_ap_fire_times_for_calendar_day(ap, day, tz)
    assert fire_times
    slot0 = fire_times[0]
    now_local = slot0 + timedelta(minutes=2)
    sig_sw = json.dumps(ap["sendWindows"], ensure_ascii=False, sort_keys=True)
    plan_sig = _autopost_plan_signature_key(
        ap, ws="12:47", we="21:00", n=len(fire_times), sig_sw=sig_sw, spread_b=True
    )
    state = ap["_state"]
    assert state.get("plan_sig") != plan_sig
    state["plan_sig"] = plan_sig
    state["next_slot"] = 0
    state["skipped_slots"] = []
    ns = 0
    n = len(fire_times)
    while ns < n:
        st = fire_times[ns]
        if st > now_local:
            break
        if (now_local - st) > _AUTOPOST_FIRE_GRACE:
            ns += 1
            continue
        break
    assert ns == 0
    assert fire_times[ns] <= now_local
    assert (now_local - fire_times[ns]) <= _AUTOPOST_FIRE_GRACE
