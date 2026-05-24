"""Фильтр пересылок и цитирования сообщений извне чата."""

from __future__ import annotations

from typing import Any, Callable, Optional

from aiogram.types import Message


def any_granular_forward_filter_enabled(rule: Any) -> bool:
    return bool(
        getattr(rule, "filter_forward_block_channels", False)
        or getattr(rule, "filter_forward_block_chats", False)
        or getattr(rule, "filter_forward_block_bots", False)
        or getattr(rule, "filter_forward_block_users", False)
        or getattr(rule, "filter_forward_block_with_links", False)
        or getattr(rule, "filter_forward_block_stories", False)
        or getattr(rule, "filter_forward_block_with_button", False)
    )


def any_granular_forward_filter_free_tier(rule: Any) -> bool:
    return bool(
        getattr(rule, "filter_forward_block_channels", False)
        or getattr(rule, "filter_forward_block_chats", False)
    )


def forward_filter_applies(rule: Any, *, owner_premium_features: bool) -> bool:
    if owner_premium_features:
        return any_granular_forward_filter_enabled(rule)
    return any_granular_forward_filter_free_tier(rule)


def _origin_chat_id(origin: Any) -> int:
    ch = getattr(origin, "chat", None)
    if ch is not None:
        return int(getattr(ch, "id", 0) or 0)
    return 0


def _classify_origin(origin: Any, *, legacy_user: Any = None) -> Optional[str]:
    if origin is None:
        if legacy_user is not None:
            return "bot" if bool(getattr(legacy_user, "is_bot", False)) else "user"
        return None
    t = str(getattr(origin, "type", "") or "").lower()
    if t == "channel":
        return "channel"
    if t == "chat":
        return "chat"
    if t == "user":
        u = getattr(origin, "sender_user", None)
        if u is not None and bool(getattr(u, "is_bot", False)):
            return "bot"
        return "user"
    if t == "hidden_user":
        return "user"
    if t == "story":
        return "story"
    return None


def resolve_outside_origin(message: Message) -> tuple[Optional[str], int]:
    """Тип источника (channel/chat/bot/user/story) и chat_id источника (0 если нет)."""
    fo = getattr(message, "forward_origin", None)
    if fo is not None:
        return _classify_origin(fo), _origin_chat_id(fo)

    er = getattr(message, "external_reply", None)
    if er is not None:
        origin = getattr(er, "origin", None)
        return _classify_origin(origin), _origin_chat_id(origin)

    fc = getattr(message, "forward_from_chat", None)
    if fc is not None:
        ft = str(getattr(fc, "type", "") or "").lower()
        kind = "channel" if ft == "channel" else "chat"
        return kind, int(getattr(fc, "id", 0) or 0)

    fu = getattr(message, "forward_from", None)
    if fu is not None:
        kind = "bot" if bool(getattr(fu, "is_bot", False)) else "user"
        return kind, 0

    if getattr(message, "forward_sender_name", None):
        return "user", 0

    return None, 0


def is_outside_forward_or_quote(message: Message, chat_id: int) -> bool:
    kind, src_chat = resolve_outside_origin(message)
    if kind is None:
        return False
    if src_chat and int(src_chat) == int(chat_id):
        return False
    return True


def _has_inline_buttons(message: Message) -> bool:
    rm = getattr(message, "reply_markup", None)
    if rm is None:
        return False
    kb = getattr(rm, "inline_keyboard", None)
    return bool(kb)


def matched_forward_filter_kind(
    message: Message,
    rule: Any,
    chat_id: int,
    *,
    owner_premium_features: bool = True,
    has_links_fn: Callable[[Message], bool] | None = None,
) -> Optional[str]:
    """
    Возвращает ключ причины: channels|chats|bots|users|with_links|stories|with_button.
    True в rule = «запрещено» (удалять).
    """
    if not is_outside_forward_or_quote(message, chat_id):
        return None

    kind, _ = resolve_outside_origin(message)

    if kind == "channel" and bool(getattr(rule, "filter_forward_block_channels", False)):
        return "channels"
    if kind == "chat" and bool(getattr(rule, "filter_forward_block_chats", False)):
        return "chats"
    if (
        owner_premium_features
        and kind == "bot"
        and bool(getattr(rule, "filter_forward_block_bots", False))
    ):
        return "bots"
    if (
        owner_premium_features
        and kind == "user"
        and bool(getattr(rule, "filter_forward_block_users", False))
    ):
        return "users"
    if (
        owner_premium_features
        and kind == "story"
        and bool(getattr(rule, "filter_forward_block_stories", False))
    ):
        return "stories"

    if owner_premium_features and bool(getattr(rule, "filter_forward_block_with_links", False)):
        if has_links_fn and has_links_fn(message):
            return "with_links"

    if owner_premium_features and bool(getattr(rule, "filter_forward_block_with_button", False)):
        if _has_inline_buttons(message):
            return "with_button"

    return None
