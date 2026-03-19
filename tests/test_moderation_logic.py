# tests/test_moderation_logic.py
"""Тесты логики модерации: stopword_hit, profanity_hit, normalize."""

from __future__ import annotations

import pytest

# Импорты из moderation (чистые функции без session)
from app.handlers.moderation import (
    stopword_hit,
    profanity_hit,
    token_set,
)
from app.handlers.moderation import normalize


def test_normalize():
    assert normalize("  Привет  ") == "привет"
    assert normalize("Ёжик") == "ежик"


def test_token_set():
    assert "hello" in token_set("hello world")
    assert "привет" in token_set("привет пока")


def test_stopword_hit():
    assert stopword_hit("привет мир", {"спам"}, None) is None
    assert stopword_hit("привет спам мир", {"спам"}, None) == "спам"
    assert stopword_hit("привет спам", set(), None) is None


def test_profanity_hit():
    assert profanity_hit("нормальный текст", set(), None) is None
    assert profanity_hit("текст с матом тут", {"мат"}, None) == "мат"
    assert profanity_hit("мат", {"мат"}, None) == "мат"
