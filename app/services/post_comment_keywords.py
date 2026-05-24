"""Ключевые слова в комментариях к постам канала (только linked discussion)."""

from __future__ import annotations

import json
import re
from typing import Any

from aiogram.types import Message

MAX_KEYWORDS = 7
MIN_KEYWORD_LEN = 2


def parse_keywords_raw(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    s = str(raw).strip()
    if s.startswith("["):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return normalize_keywords_list([str(x) for x in data])
        except Exception:
            pass
    parts = re.split(r"[,;\n]+", s)
    return normalize_keywords_list(parts)


def normalize_keywords_list(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        w = str(item or "").strip()
        if len(w) < MIN_KEYWORD_LEN:
            continue
        key = w.lower().replace("ё", "е")
        if key in seen:
            continue
        seen.add(key)
        out.append(w[:128])
        if len(out) >= MAX_KEYWORDS:
            break
    return out


def load_post_comment_keywords(rule: Any) -> list[str]:
    raw = getattr(rule, "post_comment_keywords_json", None)
    if not raw:
        return []
    if isinstance(raw, list):
        return normalize_keywords_list([str(x) for x in raw])
    s = str(raw).strip()
    if s.startswith("["):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return normalize_keywords_list([str(x) for x in data])
        except Exception:
            return []
    return parse_keywords_raw(s)


def dump_post_comment_keywords(keywords: list[str]) -> str | None:
    clean = normalize_keywords_list(keywords)
    if not clean:
        return None
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower().replace("ё", "е")


def is_post_comment_thread(message: Message) -> bool:
    """Комментарий под постом канала (не «Общий» топик форума)."""
    from app.handlers.moderation import _is_channel_comment_context

    if _is_channel_comment_context(message):
        return True
    chat = getattr(message, "chat", None)
    if chat and bool(getattr(chat, "is_forum", False)):
        tid = getattr(message, "message_thread_id", None)
        if tid is not None and int(tid) > 1:
            return True
    return False


def keyword_hit(text: str, keywords: list[str]) -> str | None:
    if not text or not keywords:
        return None
    norm = _normalize_text(text)
    if not norm:
        return None
    for kw in keywords:
        w = str(kw or "").strip()
        if len(w) < MIN_KEYWORD_LEN:
            continue
        wn = _normalize_text(w)
        if not wn:
            continue
        if " " in wn or wn.startswith("#") or any(ord(c) > 0x1F300 for c in wn):
            if wn in norm:
                return w
            continue
        if re.search(rf"(?<![\w]){re.escape(wn)}(?![\w])", norm, flags=re.UNICODE):
            return w
    return None


def matched_post_comment_keyword(message: Message, rule: Any, text: str) -> str | None:
    if not bool(getattr(rule, "post_comment_keywords_enabled", False)):
        return None
    if not is_post_comment_thread(message):
        return None
    keywords = load_post_comment_keywords(rule)
    if not keywords:
        return None
    return keyword_hit(text, keywords)


def normalize_post_comment_action(raw: str | None) -> str:
    v = str(raw or "delete").strip().lower()
    if v in ("delete", "mute", "kick", "ban", "observe"):
        return v
    return "delete"
