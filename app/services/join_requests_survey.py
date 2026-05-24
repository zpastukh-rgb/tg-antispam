"""Опросник для заявок на вступление: парсинг вопросов и проверка ответов."""

from __future__ import annotations

import json
import re
from typing import Any

JOIN_REQUEST_MODES = frozenset({"off", "auto", "survey_auto", "survey_manual"})
JOIN_REQUEST_REPORT_MODES = frozenset({"off", "brief", "full"})

DEFAULT_WELCOME_RU = (
    "{name}! Администратор группы «{chat}» установил опрос на вход по заявкам. "
    "Пожалуйста, пройдите его, чтобы получить доступ."
)
DEFAULT_WELCOME_EN = (
    "{name}! The admin of «{chat}» set a join questionnaire. "
    "Please complete it to get access."
)
DEFAULT_DONE_RU = "Спасибо! Ваши ответы приняты."
DEFAULT_DONE_EN = "Thank you! Your answers have been received."

_MAX_BUTTONS_PER_ROW = 2
_MAX_BUTTON_ROWS = 3
_MAX_BUTTON_LABEL = 64


def normalize_mode(raw: str | None) -> str:
    m = str(raw or "off").strip().lower()
    if m == "on":
        return "auto"
    return m if m in JOIN_REQUEST_MODES else "off"


def normalize_report_mode(raw: str | None) -> str:
    m = str(raw or "full").strip().lower()
    return m if m in JOIN_REQUEST_REPORT_MODES else "full"


def _normalize_button_url(raw: str) -> str | None:
    u = str(raw or "").strip()
    if not u:
        return None
    low = u.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return u[:512]
    if low.startswith("t.me/") or low.startswith("telegram.me/"):
        return f"https://{u.lstrip('/')}"[:512]
    if u.startswith("tg://"):
        return u[:512]
    return None


def _parse_button_token(token: str) -> dict[str, str] | None:
    s = str(token or "").strip()
    if not s or "=" not in s:
        return None
    label, url = s.split("=", 1)
    label = label.strip()[:_MAX_BUTTON_LABEL]
    url = _normalize_button_url(url)
    if not label or not url:
        return None
    return {"text": label, "url": url}


def parse_button_rows(raw_lines: list[str]) -> list[list[dict[str, str]]]:
    """Строки B: → ряды inline-кнопок. В одной строке B: кнопки через && (до 2 в ряд)."""
    rows: list[list[dict[str, str]]] = []
    for line in raw_lines:
        s = str(line or "").strip()
        if not s:
            continue
        row: list[dict[str, str]] = []
        for part in s.split("&&"):
            btn = _parse_button_token(part)
            if btn:
                row.append(btn)
            if len(row) >= _MAX_BUTTONS_PER_ROW:
                break
        if row:
            rows.append(row)
        if len(rows) >= _MAX_BUTTON_ROWS:
            break
    return rows


def button_rows_to_text(rows: list[list[dict[str, str]]]) -> str:
    parts: list[str] = []
    for row in rows[:_MAX_BUTTON_ROWS]:
        tokens: list[str] = []
        for btn in row[:_MAX_BUTTONS_PER_ROW]:
            text = str(btn.get("text") or "").strip()
            url = str(btn.get("url") or "").strip()
            if text and url:
                tokens.append(f"{text}={url}")
        if tokens:
            parts.append(" && ".join(tokens))
    return "\n".join(parts)


def parse_questions_text(raw: str | None) -> list[dict[str, Any]]:
    """
    Формат (каждый вопрос):
    Q: текст вопроса
    A: ответ1; ответ2; ответ3
    B: Правила=https://t.me/rules&&Канал=https://t.me/channel
    """
    if not raw:
        return []
    text = str(raw).replace("\r\n", "\n").strip()
    if not text:
        return []
    blocks = re.split(r"\n\s*\n+", text)
    out: list[dict[str, Any]] = []
    for block in blocks:
        q_line = ""
        a_line = ""
        b_lines: list[str] = []
        for line in block.split("\n"):
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            if low.startswith("q:"):
                q_line = s[2:].strip()
            elif low.startswith("a:"):
                a_line = s[2:].strip()
            elif low.startswith("b:"):
                b_lines.append(s[2:].strip())
            elif not q_line:
                q_line = s
            elif not a_line:
                a_line = s
        if not q_line:
            continue
        answers = [p.strip().lower() for p in re.split(r"[;|]", a_line) if p.strip()]
        answers = [a for a in answers if a][:5]
        if answers:
            item: dict[str, Any] = {"text": q_line[:500], "answers": answers}
            btn_rows = parse_button_rows(b_lines)
            if btn_rows:
                item["buttons"] = btn_rows
            out.append(item)
    return out[:5]


def questions_to_text(questions: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for q in questions[:5]:
        text = str(q.get("text") or "").strip()
        ans = q.get("answers") or []
        if not text or not ans:
            continue
        block = f"Q: {text}\nA: {'; '.join(str(a) for a in ans[:5])}"
        btn_text = button_rows_to_text(q.get("buttons") or [])
        if btn_text:
            for b_line in btn_text.split("\n"):
                if b_line.strip():
                    block += f"\nB: {b_line.strip()}"
        parts.append(block)
    return "\n\n".join(parts)


def answer_matches(user_text: str, accepted: list[str]) -> bool:
    blob = (user_text or "").strip().lower().replace("ё", "е")
    if not blob:
        return False
    for a in accepted:
        aa = str(a or "").strip().lower().replace("ё", "е")
        if aa and aa == blob:
            return True
    return False


def load_answers_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def dump_answers_json(answers: list[str]) -> str:
    return json.dumps(answers[:20], ensure_ascii=False)


def welcome_text(rule: Any, *, name: str, chat_title: str, locale: str = "ru") -> str:
    custom = str(getattr(rule, "join_requests_welcome_text", "") or "").strip()
    if custom:
        return (
            custom.replace("{name}", name)
            .replace("{chat}", chat_title)
            .replace("{chat_title}", chat_title)
        )
    tpl = DEFAULT_WELCOME_RU if locale.startswith("ru") else DEFAULT_WELCOME_EN
    return tpl.format(name=name, chat=chat_title, chat_title=chat_title)


def done_text(rule: Any, *, locale: str = "ru") -> str:
    custom = str(getattr(rule, "join_requests_done_text", "") or "").strip()
    if custom:
        return custom
    return DEFAULT_DONE_RU if locale.startswith("ru") else DEFAULT_DONE_EN
