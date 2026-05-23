"""Трекинг ссылок в HTML-теле и URL-кнопках рассылки."""

import os

from app.services.admin_broadcast import (
    _wrap_tracked_url,
    broadcast_open_url_for_click,
    http_telegram_url_to_tg_scheme,
    is_broadcast_telegram_http_url,
    strip_underline_inside_html_links,
    wrap_broadcast_html_body,
)


def test_strip_underline_inside_html_links():
    html = '<a href="https://example.com"><u>Купить</u></a>'
    assert strip_underline_inside_html_links(html) == '<a href="https://example.com">Купить</a>'


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
    assert "s=btn" not in out


def test_wrap_broadcast_html_body_keeps_tme_direct(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    html = '<a href="https://t.me/mychannel">Канал</a>'
    out = wrap_broadcast_html_body(
        html,
        broadcast_id=1,
        target_kind="group",
        target_id=-1,
    )
    assert "/api/public/broadcast/click?" not in out
    assert 'href="https://t.me/mychannel"' in out


def test_wrap_tracked_url_marks_keyboard_buttons(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    out = _wrap_tracked_url(
        "https://shop.example/item",
        broadcast_id=3,
        target_kind="group",
        target_id=-99,
        click_source="btn",
    )
    assert "s=btn" in out
    assert "/api/public/broadcast/click?" in out


def test_wrap_tracked_url_skips_tme_keyboard(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    src = "https://t.me/blog_pastukha/307"
    out = _wrap_tracked_url(
        src,
        broadcast_id=3,
        target_kind="group",
        target_id=-99,
        click_source="btn",
    )
    assert out == src
    assert "/api/public/broadcast/click?" not in out


def test_wrap_tracked_url_includes_campaign_id(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    out = _wrap_tracked_url(
        "https://shop.example/item",
        broadcast_id=3,
        target_kind="group",
        target_id=-99,
        click_source="btn",
        autopost_campaign_id=42,
    )
    assert "c=42" in out
    assert "b=3" in out


def test_wrap_tracked_url_tracks_play_store(monkeypatch):
    monkeypatch.setenv("BROADCAST_TRACK_BASE_URL", "https://api.example.com")
    src = "https://play.google.com/store/apps/details?id=org.telegram.messenger"
    out = _wrap_tracked_url(src, broadcast_id=1, target_kind="group", target_id=-1, click_source="btn")
    assert "/api/public/broadcast/click?" in out


def test_wrap_broadcast_html_body_noop_without_base(monkeypatch):
    monkeypatch.delenv("BROADCAST_TRACK_BASE_URL", raising=False)
    monkeypatch.delenv("GUARD_API_BASE_URL", raising=False)
    html = '<a href="https://example.com">x</a>'
    out = wrap_broadcast_html_body(html, broadcast_id=1, target_kind="group", target_id=-1)
    assert out == html


def test_http_telegram_url_to_tg_scheme():
    assert is_broadcast_telegram_http_url("https://t.me/foo")
    assert http_telegram_url_to_tg_scheme("https://t.me/blog_pastukha/305") == "tg://resolve?domain=blog_pastukha&post=305"
    assert http_telegram_url_to_tg_scheme("https://t.me/+AbCdEfGh") == "tg://join?invite=AbCdEfGh"
    assert http_telegram_url_to_tg_scheme("https://t.me/c/1770939454/23") == "tg://privatepost?channel=1770939454&post=23"
    assert broadcast_open_url_for_click("https://example.com/x") == "https://example.com/x"
    assert broadcast_open_url_for_click("https://t.me/foo/1").startswith("tg://")
