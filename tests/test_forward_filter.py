"""Тесты фильтра пересылок и цитат."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.forward_filter import (
    any_granular_forward_filter_enabled,
    is_outside_forward_or_quote,
    matched_forward_filter_kind,
    resolve_outside_origin,
)


def _rule(**kwargs):
    defaults = dict(
        filter_forward_block_channels=False,
        filter_forward_block_chats=False,
        filter_forward_block_bots=False,
        filter_forward_block_users=False,
        filter_forward_block_with_links=False,
        filter_forward_block_stories=False,
        filter_forward_block_with_button=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class _Chat:
    def __init__(self, cid: int, ctype: str = "channel"):
        self.id = cid
        self.type = ctype


class _User:
    def __init__(self, uid: int, *, is_bot: bool = False):
        self.id = uid
        self.is_bot = is_bot


class _Origin:
    def __init__(self, otype: str, chat=None, sender_user=None):
        self.type = otype
        self.chat = chat
        self.sender_user = sender_user


class _Msg:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_resolve_forward_from_channel():
    msg = _Msg(forward_origin=_Origin("channel", chat=_Chat(-100111, "channel")))
    kind, cid = resolve_outside_origin(msg)
    assert kind == "channel"
    assert cid == -100111


def test_matched_forward_block_channel():
    msg = _Msg(forward_origin=_Origin("channel", chat=_Chat(-100222, "channel")))
    rule = _rule(filter_forward_block_channels=True)
    assert matched_forward_filter_kind(msg, rule, -100999) == "channels"


def test_same_chat_forward_not_outside():
    cid = -100999
    msg = _Msg(forward_origin=_Origin("chat", chat=_Chat(cid, "supergroup")))
    assert is_outside_forward_or_quote(msg, cid) is False


def test_with_links_modifier():
    msg = _Msg(
        forward_origin=_Origin("user", sender_user=_User(42)),
        text="see https://example.com",
        entities=[SimpleNamespace(type="url", offset=4, length=19)],
    )
    rule = _rule(filter_forward_block_with_links=True)

    def has_links(m):
        return True

    assert matched_forward_filter_kind(msg, rule, -1, has_links_fn=has_links) == "with_links"


def test_any_granular_enabled():
    assert any_granular_forward_filter_enabled(_rule()) is False
    assert any_granular_forward_filter_enabled(_rule(filter_forward_block_users=True)) is True
