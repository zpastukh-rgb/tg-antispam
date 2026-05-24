"""Тесты фильтрации входящих пользователей."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.join_filter import (
    evaluate_join_name_filter,
    join_close_entry_action,
    name_has_cjk,
    name_has_rtl_script,
    name_has_zalgo,
    name_looks_spammy,
    name_matches_stopwords,
    parse_name_stopwords,
    user_display_blob,
)


def _rule(**kwargs):
    defaults = dict(
        join_filter_enabled=True,
        join_filter_arab=False,
        join_filter_cjk=False,
        join_filter_zalgo=False,
        join_filter_spam_nick=False,
        join_filter_require_username=False,
        join_filter_name_stopwords_enabled=False,
        join_filter_name_stopwords=None,
        join_filter_close_entry=False,
        join_filter_close_action="kick",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _user(**kwargs):
    defaults = dict(first_name="Alex", last_name="", username="alex_ok", full_name="Alex")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_user_display_blob_combines_fields():
    u = _user(first_name="Ivan", last_name="Petrov", username="ivan_p")
    assert "Ivan" in user_display_blob(u)
    assert "Petrov" in user_display_blob(u)
    assert "ivan_p" in user_display_blob(u)


def test_rtl_and_cjk_detection():
    assert name_has_rtl_script("محمد") is True
    assert name_has_rtl_script("John") is False
    assert name_has_cjk("王小明") is True
    assert name_has_cjk("Anna") is False


def test_zalgo_and_spam_nick():
    zalgo = "A" + "\u0300" * 5
    assert name_has_zalgo(zalgo) is True
    assert name_looks_spammy("☬☭🔥💎") is True
    assert name_looks_spammy("Normal Name") is False


def test_parse_and_match_stopwords():
    words = parse_name_stopwords("spam, casino ,SPAM")
    assert words == ["spam", "casino"]
    assert name_matches_stopwords("User Casino Bot", words) == "casino"
    assert name_matches_stopwords("Clean Name", words) is None


def test_evaluate_disabled_returns_none():
    u = _user(first_name="محمد")
    rule = _rule(join_filter_enabled=False, join_filter_arab=True)
    assert evaluate_join_name_filter(u, rule) is None


def test_evaluate_arab_filter():
    u = _user(first_name="محمد", username=None)
    rule = _rule(join_filter_arab=True)
    assert evaluate_join_name_filter(u, rule) == "arab"


def test_evaluate_require_username():
    u = _user(username=None)
    rule = _rule(join_filter_require_username=True)
    assert evaluate_join_name_filter(u, rule) == "no_username"


def test_evaluate_name_stopword():
    u = _user(first_name="Crypto King")
    rule = _rule(
        join_filter_name_stopwords_enabled=True,
        join_filter_name_stopwords="crypto, casino",
    )
    assert evaluate_join_name_filter(u, rule) == "name_stopword:crypto"


def test_join_close_entry_action():
    assert join_close_entry_action(_rule(join_filter_close_action="kick")) == "kick"
    assert join_close_entry_action(_rule(join_filter_close_action="ban")) == "ban"
    assert join_close_entry_action(_rule(join_filter_close_action="unknown")) == "kick"
