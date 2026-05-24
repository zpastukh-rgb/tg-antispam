"""Индивидуальные наказания по фильтрам и режим action_mode=off."""

from __future__ import annotations

import json
from typing import Any

VALID_ACTIONS = frozenset({"delete", "mute", "kick", "ban", "observe"})


def _normalize_action_mode(raw: str | None) -> str:
    v = str(raw or "").strip().lower()
    if not v or v in ("inherit", "default", "global"):
        return ""
    if v == "off" or v in ("выкл", "only_filters", "per_filter", "filters_only"):
        return "off"
    if v == "observe" or "log_only" in v:
        return "observe"
    if v == "kick" or "кик" in v:
        return "kick"
    if v == "ban" or "бан" in v:
        return "ban"
    if v == "mute" or "мут" in v:
        return "mute"
    if v == "delete" or "удал" in v:
        return "delete"
    return "delete"


def _parse_stored_action(raw: str) -> str:
    v = str(raw or "").strip().lower()
    if v in VALID_ACTIONS:
        return v
    normalized = _normalize_action_mode(v)
    if normalized not in VALID_ACTIONS:
        return ""
    if normalized == "delete" and v not in ("delete",) and "удал" not in v:
        return ""
    return normalized


def load_filter_actions(rule: Any) -> dict[str, str]:
    raw = getattr(rule, "filter_actions_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in data.items():
            key = str(k or "").strip()
            if not key:
                continue
            act = _parse_stored_action(str(v or ""))
            if act in VALID_ACTIONS:
                out[key] = act
        return out
    except Exception:
        return {}


def dump_filter_actions(actions: dict[str, str]) -> str | None:
    clean = {k: v for k, v in actions.items() if k and v in VALID_ACTIONS}
    if not clean:
        return None
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))


def reason_to_action_key(reason: str) -> str:
    r = str(reason or "").strip()
    if r.endswith("_newbie"):
        r = r[: -len("_newbie")]
    return r


def resolve_violation_action(
    rule: Any,
    reason: str,
    *,
    default_mute: int = 30,
) -> tuple[str, int]:
    """
    Выбор наказания для срабатывания фильтра.
    - override из filter_actions_json по ключу reason (например mech_flood)
    - если action_mode=off и override нет — только delete (без мута/бана)
    - иначе — глобальный action_mode
    """
    global_raw = str(getattr(rule, "action_mode", "delete") or "delete").strip().lower()
    global_off = global_raw == "off"
    global_mode = _normalize_action_mode(global_raw) if not global_off else ""

    mute = max(1, min(1440, int(getattr(rule, "mute_minutes", default_mute) or default_mute)))

    overrides = load_filter_actions(rule)
    key = reason_to_action_key(reason)
    ov = overrides.get(key)
    if ov and ov in VALID_ACTIONS:
        return ov, mute

    if key == "mech_flood":
        from app.services.flood_filter import normalize_flood_action

        fa = normalize_flood_action(getattr(rule, "mech_filter_flood_action", None))
        if fa in VALID_ACTIONS:
            return fa, mute

    if global_off:
        return "delete", mute

    if global_mode in VALID_ACTIONS:
        return global_mode, mute
    return "delete", mute
