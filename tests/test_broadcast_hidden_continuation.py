"""Скрытое продолжение в клавиатуре рассылки."""

from app.services.admin_broadcast import (
    BROADCAST_HIDDEN_CONTINUATION_PREFIX,
    BROADCAST_TRACKED_CALLBACK_PREFIX,
    build_tracked_keyboard_markup,
    list_broadcast_callback_payloads_for_layout,
    list_hidden_continuation_configs,
    normalize_keyboard_rows,
)


def test_normalize_keyboard_hidden_continuation():
    raw = [
        [
            {
                "text": "Читать",
                "hidden_continuation": {
                    "non_member_text": "Подпишитесь",
                    "member_text": "Продолжение",
                },
                "style": "primary",
            }
        ]
    ]
    stored = normalize_keyboard_rows(raw)
    assert stored
    assert "hidden_continuation" in stored
    configs = list_hidden_continuation_configs(stored)
    assert len(configs) == 1
    assert configs[0]["non_member_text"] == "Подпишитесь"
    assert configs[0]["member_text"] == "Продолжение"


def test_build_tracked_keyboard_emits_bc_hc_token(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    raw = [
        [
            {
                "text": "Дальше",
                "hidden_continuation": {
                    "non_member_text": "A",
                    "member_text": "B",
                },
            },
            {"text": "OK", "callback_data": "x"},
        ]
    ]
    kbd_json = normalize_keyboard_rows(raw)
    markup = build_tracked_keyboard_markup(
        kbd_json,
        broadcast_id=42,
        target_kind="group",
        target_id=-1001,
        autopost_campaign_id=7,
    )
    assert markup is not None
    flat = [b for row in markup.inline_keyboard for b in row]
    assert len(flat) == 2
    assert str(flat[0].callback_data).startswith(BROADCAST_HIDDEN_CONTINUATION_PREFIX)
    assert str(flat[0].callback_data) == "bcHC:42:7:0"
    assert str(flat[1].callback_data).startswith(BROADCAST_TRACKED_CALLBACK_PREFIX)


def test_callback_payload_list_skips_hidden_continuation():
    raw = [
        [
            {
                "text": "Дальше",
                "hidden_continuation": {"non_member_text": "A", "member_text": "B"},
            },
            {"text": "Act", "callback_data": "do_it"},
        ]
    ]
    kbd_json = normalize_keyboard_rows(raw)
    payloads = list_broadcast_callback_payloads_for_layout(kbd_json, layout_group=True)
    assert payloads == ["do_it"]
