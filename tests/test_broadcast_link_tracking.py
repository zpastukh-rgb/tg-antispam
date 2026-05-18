"""Трекинг ссылок в HTML-теле рассылки."""

import os

from app.services.admin_broadcast import wrap_broadcast_html_body


def test_wrap_broadcast_html_body_tracks_text_link(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    html = '<a href="https://example.com/page">Купить</a>'
    out = wrap_broadcast_html_body(
        html,
        broadcast_id=7,
        target_kind="group",
        target_id=-100123,
    )
    assert "/api/public/broadcast/click?" in out
    assert "b=7" in out
    assert "example.com/page" in out


def test_wrap_broadcast_html_body_tracks_tme_in_text(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    html = '<a href="https://t.me/mychannel">Канал</a>'
    out = wrap_broadcast_html_body(
        html,
        broadcast_id=1,
        target_kind="group",
        target_id=-1,
    )
    assert "/api/public/broadcast/click?" in out


def test_wrap_broadcast_html_body_noop_without_base(monkeypatch):
    monkeypatch.delenv("BROADCAST_TRACK_BASE_URL", raising=False)
    monkeypatch.delenv("GUARD_API_BASE_URL", raising=False)
    html = '<a href="https://example.com">x</a>'
    out = wrap_broadcast_html_body(html, broadcast_id=1, target_kind="group", target_id=-1)
    assert out == html
