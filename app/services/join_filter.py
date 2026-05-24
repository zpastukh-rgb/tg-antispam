"""Фильтрация пользователей при входе в группу (имя, @username, закрытие входа)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Optional

# RTL: арабский, иврит и смежные блоки
_RTL_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
    (0x0590, 0x05FF),
)

# CJK + японский + корейский
_CJK_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0x3040, 0x30FF),
    (0xAC00, 0xD7AF),
)

# «Спамные» символы в нике (как в типичных анти-рейд ботах)
_SPAM_NICK_CHARS = set("☬☭⚡️🔥💎🎰🃏💰💵💲🤑👑⭐✨💫🌟❤️💋🍑🍆")


def _char_in_ranges(ch: str, ranges: Iterable[tuple[int, int]]) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in ranges)


def name_has_rtl_script(text: str) -> bool:
    return any(_char_in_ranges(ch, _RTL_RANGES) for ch in (text or ""))


def name_has_cjk(text: str) -> bool:
    return any(_char_in_ranges(ch, _CJK_RANGES) for ch in (text or ""))


def name_has_zalgo(text: str, *, min_combining: int = 4, ratio: float = 0.28) -> bool:
    s = text or ""
    if not s:
        return False
    combining = sum(1 for c in s if unicodedata.combining(c))
    if combining >= min_combining:
        return True
    return combining / max(len(s), 1) >= ratio


def name_looks_spammy(text: str) -> bool:
    s = text or ""
    if not s:
        return False
    spam_hits = sum(1 for c in s if c in _SPAM_NICK_CHARS)
    if spam_hits >= 2:
        return True
    # Много подряд одинаковых символов / emoji
    if re.search(r"(.)\1{4,}", s):
        return True
    emoji_like = len(re.findall(r"[\U0001F300-\U0001FAFF]", s))
    return emoji_like >= 4


def parse_name_stopwords(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,;\n]+", str(raw))
    out: list[str] = []
    for p in parts:
        w = p.strip().lower()
        if len(w) >= 2 and w not in out:
            out.append(w)
    return out[:100]


def name_matches_stopwords(display_blob: str, words: list[str]) -> Optional[str]:
    if not words:
        return None
    blob = (display_blob or "").lower()
    if not blob:
        return None
    for w in words:
        if w and w in blob:
            return w
    return None


def user_display_blob(user: Any) -> str:
    parts = [
        str(getattr(user, "first_name", "") or ""),
        str(getattr(user, "last_name", "") or ""),
        str(getattr(user, "full_name", "") or ""),
        str(getattr(user, "username", "") or ""),
    ]
    return " ".join(p for p in parts if p).strip()


def evaluate_join_name_filter(user: Any, rule: Any) -> Optional[str]:
    """
    Возвращает код причины или None, если пропускаем.
    Требует join_filter_enabled на rule.
    """
    if not bool(getattr(rule, "join_filter_enabled", False)):
        return None
    blob = user_display_blob(user)
    if bool(getattr(rule, "join_filter_require_username", False)):
        uname = str(getattr(user, "username", "") or "").strip()
        if not uname:
            return "no_username"
    if bool(getattr(rule, "join_filter_arab", False)) and name_has_rtl_script(blob):
        return "arab"
    if bool(getattr(rule, "join_filter_cjk", False)) and name_has_cjk(blob):
        return "cjk"
    if bool(getattr(rule, "join_filter_zalgo", False)) and name_has_zalgo(blob):
        return "zalgo"
    if bool(getattr(rule, "join_filter_spam_nick", False)) and name_looks_spammy(blob):
        return "spam_nick"
    if bool(getattr(rule, "join_filter_name_stopwords_enabled", False)):
        words = parse_name_stopwords(getattr(rule, "join_filter_name_stopwords", None))
        hit = name_matches_stopwords(blob, words)
        if hit:
            return f"name_stopword:{hit}"
    return None


def join_close_entry_action(rule: Any) -> str:
    act = str(getattr(rule, "join_filter_close_action", "kick") or "kick").strip().lower()
    return "ban" if act == "ban" else "kick"
