"""Тесты автоудаления комментариев по ключевым словам."""

from types import SimpleNamespace

from app.services.post_comment_keywords import (
    keyword_hit,
    load_post_comment_keywords,
    normalize_keywords_list,
    parse_keywords_raw,
)


def test_normalize_keywords_max_seven():
    items = [f"word{i}" for i in range(12)]
    out = normalize_keywords_list(items)
    assert len(out) == 7


def test_parse_keywords_comma():
    assert parse_keywords_raw("#промо, #реклама, 🏷️") == ["#промо", "#реклама", "🏷️"]


def test_keyword_hit_hashtag():
    assert keyword_hit("купи #промо сейчас", ["#промо"]) == "#промо"


def test_keyword_hit_word_boundary():
    assert keyword_hit("это реклама тут", ["реклама"]) == "реклама"
    assert keyword_hit("это антиреклама", ["реклама"]) is None


def test_load_from_json_rule():
    rule = SimpleNamespace(post_comment_keywords_json='["#ads","spam"]')
    assert load_post_comment_keywords(rule) == ["#ads", "spam"]
