"""Права бота при подключении группы — deep link, requestChat и проверки."""

from __future__ import annotations

from typing import Any

# t.me/{bot}?startgroup=connect&admin=...
GROUP_CONNECT_ADMIN_QUERY = "delete_messages+restrict_members+invite_users+pin_messages"

# Порядок проверки (после статуса administrator).
REQUIRED_FLAGS: tuple[tuple[str, str], ...] = (
    ("can_delete_messages", "bot_need_delete"),
    ("can_restrict_members", "bot_need_restrict"),
    ("can_invite_users", "bot_need_invite"),
    ("can_pin_messages", "bot_need_pin"),
)

BOT_ADMIN_RIGHTS_PAYLOAD: dict[str, Any] = {
    "is_anonymous": False,
    "can_manage_chat": False,
    "can_delete_messages": True,
    "can_manage_video_chats": False,
    "can_restrict_members": True,
    "can_promote_members": False,
    "can_change_info": False,
    "can_invite_users": True,
    "can_post_stories": False,
    "can_edit_stories": False,
    "can_delete_stories": False,
    "can_pin_messages": True,
}


def _member_status(member: Any) -> str:
    if member is None:
        return ""
    if isinstance(member, dict):
        return str(member.get("status") or "").lower()
    return str(getattr(member, "status", "") or "").lower()


def _member_flag(member: Any, name: str) -> bool:
    if member is None:
        return False
    if isinstance(member, dict):
        return bool(member.get(name))
    return bool(getattr(member, name, False))


def missing_connect_rights(member: Any) -> list[str]:
    """Список недостающих can_* флагов. Пустой список — всё ок (или creator)."""
    status = _member_status(member)
    if status == "creator":
        return []
    if status not in ("administrator", "creator"):
        return []
    missing: list[str] = []
    for flag, _ in REQUIRED_FLAGS:
        if not _member_flag(member, flag):
            missing.append(flag)
    return missing


def bot_is_group_admin(member: Any) -> bool:
    return _member_status(member) in ("administrator", "creator")


def bot_has_group_connect_rights(member: Any) -> bool:
    if not bot_is_group_admin(member):
        return False
    return not missing_connect_rights(member)


def first_missing_i18n_key(member: Any) -> str | None:
    if not bot_is_group_admin(member):
        return "bot_need_admin"
    missing = missing_connect_rights(member)
    if not missing:
        return None
    for flag, key in REQUIRED_FLAGS:
        if flag in missing:
            return key
    return "bot_need_rights"


def aiogram_bot_administrator_rights():
    from aiogram.types import ChatAdministratorRights

    return ChatAdministratorRights(**BOT_ADMIN_RIGHTS_PAYLOAD)


# Минимальные права пользователя в picker: без админки Telegram не даст выбрать чат.
USER_GROUP_ADMIN_RIGHTS_PAYLOAD: dict[str, Any] = {
    "is_anonymous": False,
    "can_manage_chat": False,
    "can_delete_messages": False,
    "can_manage_video_chats": False,
    "can_restrict_members": True,
    "can_promote_members": False,
    "can_change_info": False,
    "can_invite_users": False,
    "can_post_stories": False,
    "can_edit_stories": False,
    "can_delete_stories": False,
    "can_pin_messages": False,
}


def aiogram_user_group_administrator_rights():
    from aiogram.types import ChatAdministratorRights

    return ChatAdministratorRights(**USER_GROUP_ADMIN_RIGHTS_PAYLOAD)


# t.me/{bot}?startchannel=connect_channel&admin=...
CHANNEL_CONNECT_ADMIN_QUERY = "post_messages+edit_messages+delete_messages+invite_users"

CHANNEL_BOT_ADMIN_RIGHTS_PAYLOAD: dict[str, Any] = {
    "is_anonymous": False,
    "can_manage_chat": False,
    "can_delete_messages": True,
    "can_manage_video_chats": False,
    "can_restrict_members": False,
    "can_promote_members": False,
    "can_change_info": False,
    "can_invite_users": True,
    "can_post_stories": False,
    "can_edit_stories": False,
    "can_delete_stories": False,
    "can_pin_messages": False,
    "can_post_messages": True,
    "can_edit_messages": True,
}


def aiogram_channel_bot_administrator_rights():
    from aiogram.types import ChatAdministratorRights

    return ChatAdministratorRights(**CHANNEL_BOT_ADMIN_RIGHTS_PAYLOAD)


USER_CHANNEL_ADMIN_RIGHTS_PAYLOAD: dict[str, Any] = {
    "is_anonymous": False,
    "can_manage_chat": False,
    "can_delete_messages": False,
    "can_manage_video_chats": False,
    "can_restrict_members": False,
    "can_promote_members": False,
    "can_change_info": False,
    "can_invite_users": False,
    "can_post_stories": False,
    "can_edit_stories": False,
    "can_delete_stories": False,
    "can_pin_messages": False,
    "can_post_messages": True,
    "can_edit_messages": False,
}


def aiogram_user_channel_administrator_rights():
    from aiogram.types import ChatAdministratorRights

    return ChatAdministratorRights(**USER_CHANNEL_ADMIN_RIGHTS_PAYLOAD)
