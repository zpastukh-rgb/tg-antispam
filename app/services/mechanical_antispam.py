"""Механический антиспам: apk, гостевые боты, подмена символов, текстовый спам."""

from __future__ import annotations

import json
import re
from typing import Any

from aiogram.types import Message

from app.services.join_filter import name_has_zalgo

_MIXED_SCRIPT_WORD = re.compile(
    r"(?<![\w/])(?=[^\s]*[a-zA-Z])(?=[^\s]*[а-яА-ЯёЁ])[^\s]{2,}",
    re.UNICODE,
)
_CHAR_REPEAT = re.compile(r"(.)\1{5,}", re.DOTALL)


def any_mech_filter_enabled(rule: Any) -> bool:
    return bool(
        getattr(rule, "mech_filter_block_apk", False)
        or getattr(rule, "mech_filter_guest_bots", False)
        or getattr(rule, "mech_filter_symbol_subst", False)
        or getattr(rule, "mech_filter_text_spam", False)
        or getattr(rule, "mech_filter_strict_edit", False)
    )


def any_mech_filter_free_tier(rule: Any) -> bool:
    return bool(
        getattr(rule, "mech_filter_block_apk", False)
        or getattr(rule, "mech_filter_guest_bots", False)
    )


def mech_filter_applies(rule: Any, *, owner_premium_features: bool) -> bool:
    if owner_premium_features:
        return any_mech_filter_enabled(rule)
    return any_mech_filter_free_tier(rule)


def _trusted_bot_usernames(rule: Any) -> set[str]:
    raw = getattr(rule, "mention_trusted_bots_json", None)
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x).strip().lower().lstrip("@") for x in data if str(x).strip()}
    except Exception:
        pass
    return set()


def is_apk_document(message: Message) -> bool:
    doc = getattr(message, "document", None)
    if not doc:
        return False
    fn = str(getattr(doc, "file_name", "") or "").lower()
    if fn.endswith(".apk"):
        return True
    mime = str(getattr(doc, "mime_type", "") or "").lower()
    return mime in (
        "application/vnd.android.package-archive",
        "application/vnd.android.package",
    )


def is_guest_bot_message(message: Message, rule: Any) -> bool:
    user = getattr(message, "from_user", None)
    if not user or not bool(getattr(user, "is_bot", False)):
        return False
    uname = str(getattr(user, "username", "") or "").lower().lstrip("@")
    if uname:
        from app.handlers.moderation import product_bot_username_norm

        if uname == product_bot_username_norm():
            return False
        if uname in _trusted_bot_usernames(rule):
            return False
    return True


def has_symbol_substitution(text: str) -> bool:
    if not text or len(text.strip()) < 4:
        return False
    from app.handlers.moderation import normalize, normalize_spam_text

    norm = normalize(text)
    loose = normalize_spam_text(text)
    compact_norm = re.sub(r"\s+", "", norm)
    compact_loose = re.sub(r"\s+", "", loose)
    if compact_loose and compact_loose != compact_norm:
        return True
    if _MIXED_SCRIPT_WORD.search(text):
        return True
    return False


def has_text_spam_patterns(text: str) -> bool:
    if not text:
        return False
    s = text.strip()
    if len(s) >= 15:
        letters = [c for c in s if c.isalpha()]
        if len(letters) >= 10:
            upper = sum(1 for c in letters if c.isupper())
            if upper / len(letters) >= 0.75:
                return True
    if _CHAR_REPEAT.search(s):
        return True
    if name_has_zalgo(s):
        return True
    return False


def matched_mech_filter_kind(
    message: Message,
    rule: Any,
    *,
    edited: bool = False,
    owner_premium_features: bool = True,
) -> str | None:
    if not mech_filter_applies(rule, owner_premium_features=owner_premium_features):
        return None

    if bool(getattr(rule, "mech_filter_strict_edit", False)) and owner_premium_features and edited:
        return "strict_edit"

    if bool(getattr(rule, "mech_filter_block_apk", False)) and is_apk_document(message):
        return "apk"

    if bool(getattr(rule, "mech_filter_guest_bots", False)) and is_guest_bot_message(message, rule):
        return "guest_bot"

    text = str(getattr(message, "text", "") or getattr(message, "caption", "") or "")
    if owner_premium_features:
        if bool(getattr(rule, "mech_filter_symbol_subst", False)) and has_symbol_substitution(text):
            return "symbol_subst"
        if bool(getattr(rule, "mech_filter_text_spam", False)) and has_text_spam_patterns(text):
            return "text_spam"

    return None
