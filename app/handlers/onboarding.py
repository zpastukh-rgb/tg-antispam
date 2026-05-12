from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Any
from collections import OrderedDict

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ChatType

from app.i18n import t as _i18n_t
from app.services.user_locale import get_user_language as _get_user_lang

router = Router()
logger = logging.getLogger(__name__)

# =========================================================
# CALLBACK KEYS
# =========================================================

CB_START = "ob:start"
CB_ADD_CHAT = "ob:add_chat"
CB_LOGS = "ob:logs"
CB_TEST = "ob:test"
CB_PANEL = "ob:open_panel"

# =========================================================
# CACHE
# =========================================================

ONBOARD_MSG_CACHE: "OrderedDict[int, Tuple[int, datetime]]" = OrderedDict()

CACHE_MAX = 2000
CACHE_TTL = timedelta(days=3)


def _cache_set(user_id: int, msg_id: int):

    now = datetime.now(timezone.utc)

    ONBOARD_MSG_CACHE[user_id] = (msg_id, now)
    ONBOARD_MSG_CACHE.move_to_end(user_id)

    for uid in list(ONBOARD_MSG_CACHE.keys()):

        _, ts = ONBOARD_MSG_CACHE[uid]

        if now - ts > CACHE_TTL:
            ONBOARD_MSG_CACHE.pop(uid, None)

    while len(ONBOARD_MSG_CACHE) > CACHE_MAX:
        ONBOARD_MSG_CACHE.popitem(last=False)


def _cache_get(user_id: int) -> Optional[int]:

    item = ONBOARD_MSG_CACHE.get(user_id)

    if not item:
        return None

    msg_id, ts = item
    now = datetime.now(timezone.utc)

    if now - ts > CACHE_TTL:
        ONBOARD_MSG_CACHE.pop(user_id, None)
        return None

    ONBOARD_MSG_CACHE.move_to_end(user_id)

    return msg_id


async def _actor_lang(actor: Any) -> str:
    if not actor:
        return "ru"
    tid = getattr(actor, "id", None)
    if not tid:
        return "ru"
    code = getattr(actor, "language_code", None)
    return await _get_user_lang(int(tid), fallback_tg_language_code=str(code) if code else None)


async def _edit_or_send(message: Message, text: str, kb, *, for_user_id: int):

    msg_id = _cache_get(for_user_id)
    chat_id = message.chat.id if message.chat else for_user_id

    if msg_id:

        try:

            await message.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return

        except Exception:
            pass

    m = await message.answer(text, parse_mode="Markdown", reply_markup=kb)

    _cache_set(for_user_id, m.message_id)


# =========================================================
# KEYBOARDS
# =========================================================

def kb_start(lang: str):

    ob = "bot.onboarding"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_i18n_t(lang, f"{ob}.btn_connect"),
                    callback_data=CB_ADD_CHAT,
                )
            ],
            [
                InlineKeyboardButton(
                    text=_i18n_t(lang, f"{ob}.btn_panel"),
                    callback_data=CB_PANEL,
                )
            ],
            [
                InlineKeyboardButton(
                    text=_i18n_t(lang, f"{ob}.btn_reports"),
                    callback_data=CB_LOGS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=_i18n_t(lang, f"{ob}.btn_test"),
                    callback_data=CB_TEST,
                )
            ],
        ]
    )


def kb_back(lang: str):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_i18n_t(lang, "bot.onboarding.btn_back"),
                    callback_data=CB_START,
                )
            ]
        ]
    )


# =========================================================
# START SCREEN
# =========================================================

async def render_start(message: Message, actor):

    lang = await _actor_lang(actor)
    text = _i18n_t(lang, "bot.onboarding.intro")
    uid = int(getattr(actor, "id", 0) or 0)
    if uid <= 0:
        return
    await _edit_or_send(message, text, kb_start(lang), for_user_id=uid)


@router.callback_query(F.data == CB_START)
async def cb_start(cb: CallbackQuery):

    await cb.answer()

    if not cb.from_user or not cb.message:
        return

    await render_start(cb.message, cb.from_user)


# =========================================================
# ADD CHAT
# =========================================================

@router.callback_query(F.data == CB_ADD_CHAT)
async def cb_add_chat(cb: CallbackQuery):

    await cb.answer()

    if not cb.from_user or not cb.message:
        return

    lang = await _actor_lang(cb.from_user)
    text = _i18n_t(lang, "bot.onboarding.add_chat")

    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb_back(lang),
    )


# =========================================================
# LOGS
# =========================================================

@router.callback_query(F.data == CB_LOGS)
async def cb_logs(cb: CallbackQuery):

    await cb.answer()

    if not cb.from_user or not cb.message:
        return

    lang = await _actor_lang(cb.from_user)
    text = _i18n_t(lang, "bot.onboarding.logs")

    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb_back(lang),
    )


# =========================================================
# TEST
# =========================================================

@router.callback_query(F.data == CB_TEST)
async def cb_test(cb: CallbackQuery):

    await cb.answer()

    if not cb.from_user or not cb.message:
        return

    lang = await _actor_lang(cb.from_user)
    text = _i18n_t(lang, "bot.onboarding.test")

    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb_back(lang),
    )


# =========================================================
# PANEL
# =========================================================

@router.callback_query(F.data == CB_PANEL)
async def cb_panel(cb: CallbackQuery):

    await cb.answer()

    from app.handlers.panel_dm import show_panel

    await show_panel(cb.bot, cb.from_user.id)


# =========================================================
# /SETLOG
# =========================================================

@router.message(Command(commands=["setlog"], ignore_mention=True))
async def setlog_command(message: Message):
    """ТЗ Отчёты: /setlog убран — подсказка про панель."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not message.from_user:
        return
    try:
        await message.delete()
    except Exception:
        pass
    lang = await _actor_lang(message.from_user)
    await message.answer(
        _i18n_t(lang, "bot.onboarding.setlog_reply"),
        parse_mode="Markdown",
    )


# =========================================================
# /CHECK
# =========================================================

@router.message(Command(commands=["check"], ignore_mention=True))
async def check_command(message: Message):
    """ТЗ ЧЕККК: /check только как fallback — подсказка про панель."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not message.from_user:
        return

    try:
        await message.delete()
    except Exception:
        pass

    lang = await _actor_lang(message.from_user)
    text = _i18n_t(lang, "bot.onboarding.check_reply").format(
        btn_add=_i18n_t(lang, "bot.start.btn_add_bot"),
        btn_connect=_i18n_t(lang, "bot.start.btn_connect"),
    )
    await message.answer(text, parse_mode="Markdown")
