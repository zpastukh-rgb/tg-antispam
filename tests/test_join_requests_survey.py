"""Tests for join request survey parsing and validation."""

from types import SimpleNamespace

from app.services.join_requests_survey import (
    answer_matches,
    button_rows_to_text,
    done_text,
    normalize_mode,
    normalize_report_mode,
    parse_button_rows,
    parse_questions_text,
    questions_to_text,
    welcome_text,
)


def test_normalize_mode():
    assert normalize_mode("auto") == "auto"
    assert normalize_mode("on") == "auto"
    assert normalize_mode("survey_auto") == "survey_auto"
    assert normalize_mode("bogus") == "off"
    assert normalize_mode(None) == "off"


def test_normalize_report_mode():
    assert normalize_report_mode("full") == "full"
    assert normalize_report_mode("brief") == "brief"
    assert normalize_report_mode("off") == "off"
    assert normalize_report_mode("x") == "full"


def test_parse_questions_text_qa_format():
    raw = """Q: Напишите нечётное число от 3 до 7
A: 3; 5; 7

Q: Слово не ..., вылетит — не поймаешь
A: воробей; Vorobey"""
    qs = parse_questions_text(raw)
    assert len(qs) == 2
    assert qs[0]["text"].startswith("Напишите")
    assert qs[0]["answers"] == ["3", "5", "7"]
    assert qs[1]["answers"] == ["воробей", "vorobey"]


def test_parse_questions_text_limits():
    blocks = []
    for i in range(8):
        blocks.append(f"Q: Question {i}\nA: ok{i}")
    qs = parse_questions_text("\n\n".join(blocks))
    assert len(qs) == 5
    assert qs[-1]["text"] == "Question 4"


def test_questions_to_text_roundtrip():
    raw = "Q: One\nA: a; b\n\nQ: Two\nA: c"
    qs = parse_questions_text(raw)
    back = questions_to_text(qs)
    qs2 = parse_questions_text(back)
    assert len(qs2) == 2
    assert qs2[0]["answers"] == ["a", "b"]


def test_parse_question_buttons():
    raw = """Q: Прочитайте правила
A: понимаю
B: Правила=https://t.me/rules&&Канал=https://t.me/channel"""
    qs = parse_questions_text(raw)
    assert len(qs) == 1
    assert qs[0]["buttons"] == [
        [
            {"text": "Правила", "url": "https://t.me/rules"},
            {"text": "Канал", "url": "https://t.me/channel"},
        ]
    ]


def test_parse_button_rows_tme_shorthand():
    rows = parse_button_rows(["FAQ=t.me/faq"])
    assert rows == [[{"text": "FAQ", "url": "https://t.me/faq"}]]


def test_questions_with_buttons_roundtrip():
    raw = """Q: Test
A: ok
B: Rules=https://example.com/rules"""
    qs = parse_questions_text(raw)
    back = questions_to_text(qs)
    qs2 = parse_questions_text(back)
    assert qs2[0]["buttons"][0][0]["text"] == "Rules"
    assert qs2[0]["buttons"][0][0]["url"] == "https://example.com/rules"


def test_button_rows_to_text():
    rows = [[{"text": "A", "url": "https://a.com"}, {"text": "B", "url": "https://b.com"}]]
    assert button_rows_to_text(rows) == "A=https://a.com && B=https://b.com"


def test_answer_matches_case_and_yo():
    assert answer_matches("5", ["3", "5", "7"])
    assert answer_matches("  Воробей ", ["воробей"])
    assert answer_matches("ёжик", ["ежик"])
    assert not answer_matches("", ["a"])
    assert not answer_matches("wrong", ["a", "b"])


def test_welcome_and_done_defaults():
    rule = SimpleNamespace(join_requests_welcome_text=None, join_requests_done_text=None)
    w = welcome_text(rule, name="Alex", chat_title="Test", locale="ru")
    assert "Alex" in w
    assert "Test" in w
    assert done_text(rule, locale="ru") == "Спасибо! Ваши ответы приняты."


def test_welcome_and_done_custom():
    rule = SimpleNamespace(
        join_requests_welcome_text="Hi {name} from {chat}",
        join_requests_done_text="Done!",
    )
    assert welcome_text(rule, name="A", chat_title="G", locale="en") == "Hi A from G"
    assert done_text(rule, locale="en") == "Done!"
