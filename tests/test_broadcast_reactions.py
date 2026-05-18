"""Тесты учёта emoji-реакций рассылки."""

from aiogram.types import ReactionTypeEmoji

from app.services.broadcast_reactions import added_reaction_keys, click_url_for_reaction_key, reaction_type_key


def test_reaction_type_key_emoji():
    assert reaction_type_key(ReactionTypeEmoji(emoji="👍")) == "emoji:👍"


def test_added_reaction_keys_new_only():
    old = [ReactionTypeEmoji(emoji="👍")]
    new = [ReactionTypeEmoji(emoji="👍"), ReactionTypeEmoji(emoji="❤️")]
    added = added_reaction_keys(old, new)
    assert added == ["emoji:❤️"]


def test_added_reaction_keys_from_empty():
    added = added_reaction_keys([], [ReactionTypeEmoji(emoji="🔥")])
    assert added == ["emoji:🔥"]


def test_click_url_for_reaction_key():
    assert click_url_for_reaction_key("emoji:👍").startswith("reaction:")
