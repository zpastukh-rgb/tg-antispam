# tests/test_debug_webapp_client_log.py
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.debug_webapp_client_log import router as debug_webapp_client_log_router


@pytest.fixture
def debug_client(monkeypatch):
    monkeypatch.delenv("GUARD_WEBAPP_DEBUG_LOG_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(debug_webapp_client_log_router)
    return TestClient(app)


def test_webapp_client_log_disabled_without_token(debug_client):
    r = debug_client.post(
        "/api/debug/webapp-client-log",
        json={"kind": "filter-chain", "scope": "x"},
        headers={"X-Guard-Webapp-Debug-Token": "x" * 16},
    )
    assert r.status_code == 404


def test_webapp_client_log_wrong_token(monkeypatch):
    monkeypatch.setenv("GUARD_WEBAPP_DEBUG_LOG_TOKEN", "right_secret_12345678")
    app = FastAPI()
    app.include_router(debug_webapp_client_log_router)
    c = TestClient(app)
    r = c.post(
        "/api/debug/webapp-client-log",
        json={"kind": "filter-chain"},
        headers={"X-Guard-Webapp-Debug-Token": "wrong_secret_12345678"},
    )
    assert r.status_code == 404


def test_webapp_client_log_ok(monkeypatch):
    tok = "ok_secret_abcdefgh"
    monkeypatch.setenv("GUARD_WEBAPP_DEBUG_LOG_TOKEN", tok)
    app = FastAPI()
    app.include_router(debug_webapp_client_log_router)
    c = TestClient(app)
    r = c.post(
        "/api/debug/webapp-client-log",
        json={"kind": "filter-chain", "scope": "polyfill", "msg": "tap"},
        headers={"X-Guard-Webapp-Debug-Token": tok},
    )
    assert r.status_code == 204


def test_webapp_client_log_ok_via_init(monkeypatch):
    monkeypatch.delenv("GUARD_WEBAPP_DEBUG_LOG_TOKEN", raising=False)
    import app.api.debug_webapp_client_log as dbg

    monkeypatch.setattr(dbg, "get_telegram_user_id", lambda s: 424242 if s == "signed_stub" else None)
    app = FastAPI()
    app.include_router(debug_webapp_client_log_router)
    c = TestClient(app)
    r = c.post(
        "/api/debug/webapp-client-log",
        json={"kind": "filter-chain", "scope": "Protection"},
        headers={"X-Telegram-Init-Data": "signed_stub"},
    )
    assert r.status_code == 204
