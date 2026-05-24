"""Тесты CAS и сетевой проверки массового входа."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.cas_check import _cache, is_user_cas_banned
from app.services.network_join_filter import (
    count_distinct_chats_in_window,
    is_network_mass_joiner,
    record_network_join,
)
from app.db.models import NetworkJoinEvent


def _rule(**kwargs):
    defaults = dict(
        join_filter_network_mass_join=True,
        join_filter_network_join_threshold=4,
        join_filter_network_join_window_minutes=10,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_cas_banned_from_api():
    _cache.clear()
    payload = {"ok": True, "result": {"user_id": 999, "offenses": 1}}

    class FakeResp:
        async def json(self, content_type=None):
            return payload

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def get(self, url, params=None, headers=None):
            class Ctx:
                async def __aenter__(self):
                    return FakeResp()

                async def __aexit__(self, *args):
                    return None

            return Ctx()

    with patch("app.services.cas_check.aiohttp.ClientSession", return_value=FakeSession()):
        assert await is_user_cas_banned(999) is True
        assert await is_user_cas_banned(999) is True  # cache


@pytest.mark.asyncio
async def test_cas_clean_from_api():
    _cache.clear()
    payload = {"ok": False, "description": "Record not found."}

    class FakeResp:
        async def json(self, content_type=None):
            return payload

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def get(self, url, params=None, headers=None):
            class Ctx:
                async def __aenter__(self):
                    return FakeResp()

                async def __aexit__(self, *args):
                    return None

            return Ctx()

    with patch("app.services.cas_check.aiohttp.ClientSession", return_value=FakeSession()):
        assert await is_user_cas_banned(1001) is False


@pytest.mark.asyncio
async def test_network_mass_joiner(db_session):
    uid = 555001
    now = datetime.now(timezone.utc)
    for cid in (-1001, -1002, -1003, -1004):
        db_session.add(
            NetworkJoinEvent(
                user_id=uid,
                chat_id=cid,
                joined_at=now - timedelta(minutes=2),
            )
        )
    await db_session.commit()
    cnt = await count_distinct_chats_in_window(db_session, uid, 10)
    assert cnt == 4
    assert await is_network_mass_joiner(db_session, uid, _rule()) is True
    assert await is_network_mass_joiner(db_session, uid, _rule(join_filter_network_mass_join=False)) is False


@pytest.mark.asyncio
async def test_record_network_join(db_session):
    await record_network_join(db_session, 777, -2001)
    await db_session.commit()
    cnt = await count_distinct_chats_in_window(db_session, 777, 10)
    assert cnt == 1
