"""Тесты индивидуальных наказаний и флуда."""

from types import SimpleNamespace

from app.services.filter_actions import load_filter_actions, resolve_violation_action
from app.services.flood_filter import (
    _normalize_flood_text,
    _text_hash,
    normalize_flood_action,
    normalize_flood_mode,
)
from app.services.mechanical_antispam import any_mech_filter_enabled


def test_resolve_global_delete():
    rule = SimpleNamespace(action_mode="mute", mute_minutes=30, filter_actions_json=None)
    act, mute = resolve_violation_action(rule, "stopword")
    assert act == "mute"
    assert mute == 30


def test_resolve_global_off_fallback_delete():
    rule = SimpleNamespace(
        action_mode="off",
        mute_minutes=30,
        filter_actions_json=None,
        mech_filter_flood_action="mute",
    )
    act, _ = resolve_violation_action(rule, "mech_flood")
    assert act == "mute"


def test_resolve_flood_dedicated_action():
    rule = SimpleNamespace(
        action_mode="delete",
        mute_minutes=30,
        filter_actions_json=None,
        mech_filter_flood_action="ban",
    )
    act, _ = resolve_violation_action(rule, "mech_flood")
    assert act == "ban"


def test_resolve_per_filter_override():
    rule = SimpleNamespace(
        action_mode="ban",
        mute_minutes=30,
        filter_actions_json='{"mech_flood":"mute","stopword":"observe"}',
        mech_filter_flood_action="ban",
    )
    act, _ = resolve_violation_action(rule, "mech_flood")
    assert act == "mute"
    act2, _ = resolve_violation_action(rule, "stopword_newbie")
    assert act2 == "observe"


def test_resolve_global_off_with_override():
    rule = SimpleNamespace(
        action_mode="off",
        mute_minutes=15,
        filter_actions_json='{"mech_apk":"ban"}',
    )
    act, mute = resolve_violation_action(rule, "mech_apk")
    assert act == "ban"
    assert mute == 15


def test_load_filter_actions_skips_invalid():
    rule = SimpleNamespace(filter_actions_json='{"mech_flood":"mute","bad":"nope"}')
    assert load_filter_actions(rule) == {"mech_flood": "mute"}


def test_filter_actions_merge_independent_of_flood_action():
    """Regression: filter_actions must save without mech_filter_flood_action in PATCH body."""
    from app.services.filter_actions import dump_filter_actions

    rule = SimpleNamespace(filter_actions_json='{"mech_flood":"mute"}')
    body = {"filter_actions": {"mech_apk": "ban", "mech_flood": "mute"}}
    current = load_filter_actions(rule)
    valid = frozenset({"delete", "mute", "kick", "ban", "observe"})
    for k, val in body["filter_actions"].items():
        key = str(k or "").strip()
        if not key:
            continue
        if val in (None, "", "inherit", "default", "global"):
            current.pop(key, None)
            continue
        act = str(val or "").strip().lower()
        if act in valid:
            current[key] = act
        else:
            current.pop(key, None)
    rule.filter_actions_json = dump_filter_actions(current)
    assert load_filter_actions(rule) == {"mech_flood": "mute", "mech_apk": "ban"}


def test_flood_text_normalize_and_hash():
    a = _normalize_flood_text("  Привет   Мир  ")
    b = _normalize_flood_text("привет мир")
    assert a == b
    assert _text_hash(a) == _text_hash(b)


def test_flood_mode_and_action_normalize():
    assert normalize_flood_mode("strict") == "strict"
    assert normalize_flood_mode("строгий") == "strict"
    assert normalize_flood_mode("") == "soft"
    assert normalize_flood_action("ban") == "ban"
    assert normalize_flood_action("заглушка") == "mute"


def test_any_mech_filter_excludes_flood():
    rule = SimpleNamespace(
        mech_filter_block_apk=False,
        mech_filter_guest_bots=False,
        mech_filter_symbol_subst=False,
        mech_filter_text_spam=False,
        mech_filter_strict_edit=False,
        mech_filter_flood_enabled=True,
    )
    assert any_mech_filter_enabled(rule) is False
