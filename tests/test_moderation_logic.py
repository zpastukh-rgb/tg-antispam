# tests/test_moderation_logic.py
"""Тесты логики модерации: stopword_hit, profanity_hit, normalize."""

from __future__ import annotations

import pytest

# Импорты из moderation (чистые функции без session)
from app.handlers.moderation import (
    stopword_hit,
    profanity_hit,
    jobs_offer_hit,
    normalize_spam_text,
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


def test_profanity_hit_roots_and_phrases():
    # Корневое срабатывание: префикс / составной токен (в «хуевишна» подстроки «хуй» нет — это другое слово)
    assert profanity_hit("хуйня мадам", {"хуй"}, None) == "хуй"
    assert profanity_hit("подработки без вложений тут", {"подработк"}, None) == "подработк"
    # Фраза
    assert profanity_hit("это легкий заработок без вложений", {"легкий заработок"}, None) == "легкий заработок"


def test_profanity_hit_false_positives_delivery_and_ship():
    # «ставк» внутри «доставка» — не казино
    assert profanity_hit("нужна доставка в краснотурьинск советская 62", {"ставк"}, None) is None
    assert profanity_hit("ставки на футбол сегодня", {"ставк"}, None) == "ставк"
    # «бля» в «корабля» — не мат
    assert profanity_hit("мира 76 подъезд от корабля до вокзала", {"бля"}, None) is None
    assert profanity_hit("блять тут шум", {"бля"}, None) == "бля"


def test_profanity_hit_casino_brand_prefixes():
    assert profanity_hit("париж красивый город", {"пари"}, None) is None
    assert profanity_hit("паритет сторон соблюден", {"пари"}, None) is None
    assert profanity_hit("парикмахерская рядом", {"пари"}, None) is None
    assert profanity_hit("париматч зеркало", {"пари"}, None) == "пари"
    assert profanity_hit("леонид пришёл", {"леон"}, None) is None
    assert profanity_hit("леон букмекер", {"леон"}, None) == "леон"
    assert profanity_hit("тотальный контроль", {"тотал"}, None) is None
    assert profanity_hit("тотал больше 2 5", {"тотал"}, None) == "тотал"


def test_jobs_offer_hit_patterns():
    msg = "Всем привет, нужны пару людей, можно зарабатывать 300к, смотри в био"
    assert jobs_offer_hit(msg.lower(), msg.lower()) == "jobs_offer_pattern"
    msg2 = "хочешь заработать больше чем сейчас смотри в био"
    assert jobs_offer_hit(msg2.lower(), msg2.lower()) == "jobs_offer_pattern"
    clean = "Всем привет, завтра встреча в 12:00, обсудим новости проекта"
    assert jobs_offer_hit(clean.lower(), clean.lower()) is None


def test_normalize_spam_text_obfuscation():
    assert "заработок" in normalize_spam_text("з@р@б0т0к")
    assert "в лс" in normalize_spam_text("в л.с")
    assert "заработок" in normalize_spam_text("зapaбoтok")
