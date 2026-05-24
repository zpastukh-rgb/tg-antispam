"""Tests for mechanical antispam filters."""

from types import SimpleNamespace

from app.services.mechanical_antispam import (
    has_symbol_substitution,
    has_text_spam_patterns,
    is_apk_document,
    matched_mech_filter_kind,
)


class _Doc:
    def __init__(self, file_name="", mime_type=""):
        self.file_name = file_name
        self.mime_type = mime_type


class _User:
    def __init__(self, *, is_bot=False, username=""):
        self.is_bot = is_bot
        self.username = username
        self.id = 123


class _Msg:
    def __init__(self, *, text="", document=None, from_user=None):
        self.text = text
        self.caption = ""
        self.document = document
        self.from_user = from_user


def test_is_apk_document():
    assert is_apk_document(_Msg(document=_Doc("app.apk"))) is True
    assert is_apk_document(_Msg(document=_Doc("x.bin", "application/vnd.android.package-archive"))) is True
    assert is_apk_document(_Msg(document=_Doc("readme.txt"))) is False


def test_has_symbol_substitution():
    assert has_symbol_substitution("зapaбoтok") is True
    assert has_symbol_substitution("обычный текст") is False


def test_has_text_spam_patterns():
    assert has_text_spam_patterns("ЭТО КРИЧАЩИЙ СПАМ ТЕКСТ!!!") is True
    assert has_text_spam_patterns("aaaaaaa") is True
    assert has_text_spam_patterns("спокойное сообщение") is False


def test_matched_mech_filter_apk():
    rule = SimpleNamespace(
        mech_filter_block_apk=True,
        mech_filter_guest_bots=False,
        mech_filter_symbol_subst=False,
        mech_filter_text_spam=False,
        mech_filter_strict_edit=False,
    )
    msg = _Msg(document=_Doc("x.apk"))
    assert matched_mech_filter_kind(msg, rule, owner_premium_features=True) == "apk"


def test_guest_bot_exempt_product_bot(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "GuardAntiSpam_Bot")

    rule = SimpleNamespace(
        mech_filter_block_apk=False,
        mech_filter_guest_bots=True,
        mech_filter_symbol_subst=False,
        mech_filter_text_spam=False,
        mech_filter_strict_edit=False,
        mention_trusted_bots_json='["HelperBot"]',
    )
    guest = _Msg(from_user=_User(is_bot=True, username="spam_bot"))
    ours = _Msg(from_user=_User(is_bot=True, username="GuardAntiSpam_Bot"))
    trusted = _Msg(from_user=_User(is_bot=True, username="HelperBot"))

    assert matched_mech_filter_kind(guest, rule, owner_premium_features=True) == "guest_bot"
    assert matched_mech_filter_kind(ours, rule, owner_premium_features=True) is None
    assert matched_mech_filter_kind(trusted, rule, owner_premium_features=True) is None
