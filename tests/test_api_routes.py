# tests/test_api_routes.py
"""Тесты API маршрутов: без init_data запросы должны возвращать 401/403/422."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_api_me_requires_init_data(client):
    resp = client.get("/api/me")
    assert resp.status_code in (401, 422, 403)


def test_api_profanity_requires_auth(client):
    resp = client.get("/api/profanity")
    assert resp.status_code in (401, 422, 403)


def test_api_promo_apply_requires_auth(client):
    resp = client.post("/api/promo/apply", json={"code": "TEST"})
    assert resp.status_code in (401, 422, 403)
