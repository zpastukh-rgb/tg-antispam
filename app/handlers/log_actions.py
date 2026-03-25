from __future__ import annotations

from aiogram import Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, ChatPermissions

router = Router()

async def _is_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False

@router.callback_query(F.data.startswith("log:unban:"))
async def cb_unban(cb: CallbackQuery):
    await cb.answer()
    if not cb.from_user:
        return

    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer("Кривые данные 😈", show_alert=True)
        return

    chat_id = int(parts[2])
    user_id = int(parts[3])

    # только админы лог-группы
    if not await _is_admin(cb.bot, cb.message.chat.id, cb.from_user.id):
        await cb.answer("Только админы 😈", show_alert=True)
        return

    try:
        await cb.bot.unban_chat_member(chat_id, user_id)
        await cb.message.edit_text(cb.message.text + "\n\n✅ Разбан выполнен.", reply_markup=None)
    except Exception:
        await cb.answer("Не получилось (прав нет/лимит).", show_alert=True)

@router.callback_query(F.data.startswith("log:unmute:"))
async def cb_unmute(cb: CallbackQuery):
    await cb.answer()
    if not cb.from_user:
        return

    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer("Кривые данные 😈", show_alert=True)
        return

    chat_id = int(parts[2])
    user_id = int(parts[3])

    if not await _is_admin(cb.bot, cb.message.chat.id, cb.from_user.id):
        await cb.answer("Только админы 😈", show_alert=True)
        return

    try:
        await cb.bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True,
                                        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                                        can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                                        can_add_web_page_previews=True, can_change_info=False, can_invite_users=True,
                                        can_pin_messages=False, can_manage_topics=False),
        )
        await cb.message.edit_text(cb.message.text + "\n\n🔊 Размут выполнен.", reply_markup=None)
    except Exception:
        await cb.answer("Не получилось (прав нет/лимит).", show_alert=True)
