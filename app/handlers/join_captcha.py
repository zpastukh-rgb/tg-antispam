# app/handlers/join_captcha.py
"""Капча при входе: все режимы (кнопки, счёт, эмодзи, цифры с картинкой, слово, отгадай слово, слово→эмодзи).
Текстовые ответы принимаю только от вступившего; inline — только его user_id на callback."""

from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import BaseFilter
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Chat,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)
from sqlalchemy import delete, select

from app.db.models import JoinCaptchaSession
from app.db.session import get_session
from app.i18n import DEFAULT_LOCALE, normalize_locale, t
from app.services.chat_owner_locale import owner_locale_for_chat, user_locale
from app.services.chat_owner_premium import chat_owner_has_miniapp_premium
from app.services.diagnostics_incidents import record_join_captcha_expire_delete_failed
from app.handlers.moderation import (
    _welcome_keyboard_from_json,
    _welcome_media_root,
    get_rule,
    is_admin,
)

logger = logging.getLogger(__name__)
router = Router(name="join_captcha")

CB_PREFIX = "jc:"

KIND_CALLBACK = frozenset({"button", "math", "emoji", "word_emoji"})
KIND_TEXT = frozenset({"digits", "word_send", "word_guess"})
ALL_KINDS = frozenset(KIND_CALLBACK | KIND_TEXT)

_FULL = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
)
# Полный запрет сообщений (кнопки/счёт/эмодзи — ответ только callback).
_MUTE_FULL = ChatPermissions(can_send_messages=False)
# Текстовая капча в группе: можно только обычное текстовое сообщение; медиа/стикеры/опросы — нет.
_MUTE_TEXT_ANSWER = ChatPermissions(
    can_send_messages=True,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

WORD_SEND_BANK = (
    "роман", "весна", "чай", "мост", "снег", "лава", "ключ", "вода", "луна", "поле",
    "звезда", "море", "лист", "камень", "ветер", "огонь", "песок", "река", "сокол", "трава",
)
WORD_GUESS_BANK = (
    "время", "осень", "книга", "мир", "ночь", "утро", "слово", "место", "дверь", "окно",
    "солнце", "зима", "лето", "весна", "дорога", "число", "ответ", "вопрос", "работа", "друг",
)
WORD_SEND_BANK_EN = (
    "spring", "river", "field", "stone", "flame", "quest", "light", "cloud", "eagle", "track",
    "silver", "amber", "forest", "harbor", "clever", "circle", "spirit", "garden", "rocket", "harvest",
)
WORD_GUESS_BANK_EN = (
    "bridge", "planet", "shadow", "canvas", "signal", "fusion", "orchard", "puzzle", "harvest", "meadow",
    "ember", "canvas", "window", "harbor", "silver", "thunder", "packet", "velvet", "compass", "moment",
)
# слово на экране → правильный эмодзи; остальные пять — отвлекающие
WORD_EMOJI_SETS = (
    ("Вишня", "🍒", ("🍐", "🍊", "🍇", "🍓", "🍋")),
    ("Яблоко", "🍎", ("🍐", "🍊", "🍌", "🍇", "🥝")),
    ("Морковь", "🥕", ("🌽", "🥦", "🧅", "🥔", "🍅")),
    ("Сыр", "🧀", ("🥛", "🧈", "🥚", "🥓", "🍞")),
    ("Рыба", "🐟", ("🐠", "🐡", "🦐", "🦀", "🐙")),
    ("Кот", "🐱", ("🐶", "🐰", "🐻", "🦊", "🐼")),
)

WORD_EMOJI_SETS_EN: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Cherry", "🍒", ("🍐", "🍊", "🍇", "🍓", "🍋")),
    ("Apple", "🍎", ("🍐", "🍊", "🍌", "🍇", "🥝")),
    ("Carrot", "🥕", ("🌽", "🥦", "🧅", "🥔", "🍅")),
    ("Cheese", "🧀", ("🥛", "🧈", "🥚", "🥓", "🍞")),
    ("Fish", "🐟", ("🐠", "🐡", "🦐", "🦀", "🐙")),
    ("Cat", "🐱", ("🐶", "🐰", "🐻", "🦊", "🐼")),
)


def _word_banks(locale: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, str, tuple[str, ...]], ...]]:
    """Слова и наборы word→emoji для RU/EN."""
    if normalize_locale(locale) == "en":
        return WORD_SEND_BANK_EN, WORD_GUESS_BANK_EN, WORD_EMOJI_SETS_EN
    return WORD_SEND_BANK, WORD_GUESS_BANK, WORD_EMOJI_SETS


def _gen_token() -> str:
    return secrets.token_hex(6)


def _cb_data(token: str, idx: int) -> str:
    return f"{CB_PREFIX}{token}:{idx}"


def _display_name(u: User, locale: str) -> str:
    loc = normalize_locale(locale)
    if u.first_name or u.last_name:
        return (f"{u.first_name or ''} {u.last_name or ''}").strip()
    if u.username:
        return f"@{u.username}"
    return t(loc, "guard.join_captcha.member")


def _pack_options(labels: list[str], expected: str | None = None, is_photo: bool = False) -> str:
    payload: dict[str, Any] = {"labels": labels}
    if expected is not None:
        payload["expected"] = expected
    if is_photo:
        payload["photo"] = True
    return json.dumps(payload, ensure_ascii=False)


def _unpack_options(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {"labels": []}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"labels": []}
    if isinstance(data, list):
        return {"labels": data}
    if isinstance(data, dict):
        return data
    return {"labels": []}


def _norm_user_answer(kind: str, raw: str) -> str:
    s = (raw or "").strip().lower().replace("ё", "е")
    if kind == "digits":
        return "".join(c for c in s if c.isdigit())
    return s


def _make_digits_png(digits: str) -> Optional[bytes]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    w, h = 220, 90
    img = Image.new("RGB", (w, h), color=(24, 24, 32))
    dr = ImageDraw.Draw(img)
    for _ in range(120):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        dr.point((x, y), fill=(random.randint(60, 140),) * 3)
    font = ImageFont.load_default()
    for path, size in (
        ("DejaVuSansMono.ttf", 40),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 40),
    ):
        try:
            font = ImageFont.truetype(path, size)
            break
        except OSError:
            continue
    tw = int(sum(font.getlength(c) for c in digits)) if hasattr(font, "getlength") else len(digits) * 22
    x0 = max(8, (w - tw) // 2)
    y0 = 22
    for i, ch in enumerate(digits):
        ox, oy = random.randint(-2, 2), random.randint(-2, 2)
        dr.text((x0 + ox + i * 44, y0 + oy), ch, fill=(230, 240, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _try_restrict(bot, chat_id: int, user_id: int, *, allow_plain_text: bool = False) -> bool:
    try:
        perms = _MUTE_TEXT_ANSWER if allow_plain_text else _MUTE_FULL
        await bot.restrict_chat_member(chat_id, user_id, permissions=perms)
        return True
    except Exception as e:
        logger.warning("join_captcha restrict %s/%s: %s", chat_id, user_id, e)
        return False


async def _unrestrict(bot, chat_id: int, user_id: int) -> None:
    try:
        await bot.restrict_chat_member(chat_id, user_id, permissions=_FULL)
    except Exception as e:
        logger.warning("join_captcha unrestrict %s/%s: %s", chat_id, user_id, e)


async def _delete_message_later(bot, chat_id: int, message_id: int, delay_sec: float) -> None:
    await asyncio.sleep(max(0.0, float(delay_sec)))
    try:
        await bot.delete_message(int(chat_id), int(message_id))
    except Exception:
        pass


async def _finish_success(
    bot,
    chat_id: int,
    user_id: int,
    message_chat_id: int,
    message_id: int,
    payload: dict[str, Any],
    *,
    captcha_scope: str = "join",
) -> None:
    try:
        await bot.delete_message(int(message_chat_id), int(message_id))
    except Exception:
        pass
    if (captcha_scope or "join") == "filter_media":
        try:
            async with await get_session() as session:
                loc = await owner_locale_for_chat(session, int(chat_id))
            ok_msg = await bot.send_message(int(chat_id), t(loc, "guard.filter_media_captcha.ok_passed"))
            ok_mid = int(getattr(ok_msg, "message_id", 0) or 0)
            if ok_mid > 0:
                asyncio.create_task(_delete_message_later(bot, int(chat_id), ok_mid, 3.0))
        except Exception as e:
            logger.warning("filter_media_captcha ok ack chat=%s user=%s err=%s", chat_id, user_id, e)
    else:
        sent_welcome = False
        try:
            sent_welcome = await _send_welcome_after_captcha(bot, chat_id, user_id)
        except Exception as e:
            logger.warning("welcome after captcha failed chat=%s user=%s err=%s", chat_id, user_id, e)
        if not sent_welcome:
            try:
                async with await get_session() as session:
                    loc = await owner_locale_for_chat(session, int(chat_id))
                ok_msg = await bot.send_message(int(chat_id), t(loc, "guard.join_captcha.ok_passed"))
                ok_mid = int(getattr(ok_msg, "message_id", 0) or 0)
                if ok_mid > 0:
                    asyncio.create_task(_delete_message_later(bot, int(chat_id), ok_mid, 3.0))
            except Exception:
                pass
    await _unrestrict(bot, chat_id, user_id)


async def _send_welcome_after_captcha(bot, chat_id: int, user_id: int) -> bool:
    async with await get_session() as session:
        rule = await get_rule(session, int(chat_id))
        if not bool(getattr(rule, "welcome_enabled", False)):
            return False
        raw_text = str(getattr(rule, "welcome_text", "") or "").strip()
        if not raw_text:
            return False
        # Защита от случайного "капча-ответа" в поле приветствия (частый кейс: "123").
        # Нормальные админские приветствия здесь не блокируем.
        if raw_text.isdigit() and len(raw_text) <= 6:
            logger.warning("skip numeric welcome_text after captcha chat=%s text=%r", chat_id, raw_text)
            return False
        try:
            user = await bot.get_chat_member(int(chat_id), int(user_id))
            u = getattr(user, "user", None)
        except Exception:
            u = None
        if not u:
            return False
        if bool(getattr(u, "is_bot", False)):
            return False
        try:
            chat_obj = await bot.get_chat(int(chat_id))
            chat_title = str(getattr(chat_obj, "title", "") or "")
        except Exception:
            chat_title = str(chat_id)
        uname = str(getattr(u, "username", "") or "").lstrip("@")
        username_display = f"@{uname}" if uname else ""
        txt = (
            raw_text
            .replace("{first_name}", html.escape(str(getattr(u, "first_name", "") or "друг"), quote=False))
            .replace(
                "{full_name}",
                html.escape(
                    str(getattr(u, "full_name", "") or getattr(u, "first_name", "") or "друг"),
                    quote=False,
                ),
            )
            .replace("{username}", html.escape(username_display, quote=False))
            .replace("{chat_title}", html.escape(chat_title, quote=False))
        )
        kb = _welcome_keyboard_from_json(getattr(rule, "welcome_buttons_json", None))
        sent_msg = None
        photo_fid = str(getattr(rule, "welcome_photo_file_id", "") or "").strip()
        photo_rel = str(getattr(rule, "welcome_photo_path", "") or "").strip()
        photo_src = None
        if photo_fid:
            photo_src = photo_fid
        elif photo_rel:
            fp = (_welcome_media_root() / photo_rel).resolve()
            root = _welcome_media_root().resolve()
            if (root in fp.parents or fp == root) and fp.exists() and fp.is_file():
                photo_src = BufferedInputFile(fp.read_bytes(), filename=fp.name)
        if photo_src:
            sent_msg = await bot.send_photo(
                int(chat_id),
                photo_src,
                caption=txt[:1024],
                parse_mode="HTML",
                reply_markup=kb,
            )
        else:
            sent_msg = await bot.send_message(int(chat_id), txt[:4000], parse_mode="HTML", reply_markup=kb)
        return bool(int(getattr(sent_msg, "message_id", 0) or 0) > 0)


async def active_join_text_captcha_row(message: Message) -> Optional[JoinCaptchaSession]:
    """Активная сессия текстовой капчи для этого апдейта (группа или ЛС с заданием)."""
    raw = (message.text or "").strip()
    if not raw or raw.startswith("/"):
        return None
    fu = message.from_user
    if not fu:
        return None
    uid = fu.id
    ct = message.chat.type
    now = datetime.now(timezone.utc)
    async with await get_session() as session:
        q = select(JoinCaptchaSession).where(
            JoinCaptchaSession.user_id == uid,
            JoinCaptchaSession.expires_at > now,
            JoinCaptchaSession.kind.in_(tuple(KIND_TEXT)),
        )
        if ct in (ChatType.GROUP, ChatType.SUPERGROUP):
            q = q.where(JoinCaptchaSession.chat_id == message.chat.id)
        elif ct == ChatType.PRIVATE:
            q = q.where(JoinCaptchaSession.message_chat_id == message.chat.id)
        else:
            return None
        q = q.order_by(JoinCaptchaSession.id.desc()).limit(1)
        return (await session.execute(q)).scalar_one_or_none()


class JoinCaptchaExpectsTextFilter(BaseFilter):
    """Есть активная текстовая капча для этого пользователя в этом чате."""

    async def __call__(self, message: Message) -> bool:
        return bool(await active_join_text_captcha_row(message))


@router.message(JoinCaptchaExpectsTextFilter(), F.text)
async def on_join_captcha_text(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    ct = message.chat.type
    now = datetime.now(timezone.utc)
    async with await get_session() as session:
        q = select(JoinCaptchaSession).where(
            JoinCaptchaSession.user_id == uid,
            JoinCaptchaSession.expires_at > now,
            JoinCaptchaSession.kind.in_(tuple(KIND_TEXT)),
        )
        if ct in (ChatType.GROUP, ChatType.SUPERGROUP):
            q = q.where(JoinCaptchaSession.chat_id == message.chat.id)
        elif ct == ChatType.PRIVATE:
            q = q.where(JoinCaptchaSession.message_chat_id == message.chat.id)
        else:
            return
        q = q.order_by(JoinCaptchaSession.id.desc()).limit(1)
        row = (await session.execute(q)).scalar_one_or_none()
        if not row:
            return
        kind = (row.kind or "").strip().lower()
        data = _unpack_options(row.options_json)
        expected = (data.get("expected") or "").strip().lower()
        got = _norm_user_answer(kind, message.text or "")
        exp_norm = _norm_user_answer(kind, expected)
        if got != exp_norm:
            try:
                await message.delete()
            except Exception:
                pass
            return
        chat_id = int(row.chat_id)
        target_uid = int(row.user_id)
        mcid = int(row.message_chat_id)
        mid = int(row.message_id)
        cscope = str(getattr(row, "captcha_scope", None) or "join")
        await session.delete(row)
        await session.commit()

    try:
        await message.delete()
    except Exception:
        pass
    await _finish_success(message.bot, chat_id, target_uid, mcid, mid, data, captcha_scope=cscope)


async def _materialize_join_style_captcha(
    bot,
    session,
    tg_chat: Chat,
    user: User,
    *,
    loc: str,
    ttl: int,
    kind: str,
    prefer_dm: bool,
    captcha_scope: str,
    send_bank: tuple[str, ...],
    guess_bank: tuple[str, ...],
    emoji_sets: tuple,
) -> None:
    chat_id = tg_chat.id
    user_id = user.id
    token = _gen_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    name = html.escape(_display_name(user, loc))

    options: list[str] = []
    correct_idx = 0
    text = ""
    kb: Optional[InlineKeyboardMarkup] = None
    options_payload = _pack_options([])
    photo_bytes: Optional[bytes] = None

    if kind == "button":
        labels = [(t(loc, "guard.join_captcha.btn_bot"), False), (t(loc, "guard.join_captcha.btn_human"), True)]
        random.shuffle(labels)
        options = [x[0] for x in labels]
        correct_idx = next(i for i, x in enumerate(labels) if x[1])
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=options[i], callback_data=_cb_data(token, i)) for i in range(2)]
            ]
        )
        text = t(loc, "guard.join_captcha.button_intro", name=name, ttl=ttl)
        options_payload = _pack_options(options)
    elif kind == "math":
        a, b = random.randint(3, 12), random.randint(3, 12)
        ans = a + b
        wrong: set[int] = set()
        while len(wrong) < 3:
            w = random.randint(2, 24)
            if w != ans:
                wrong.add(w)
        opts = list(wrong) + [ans]
        random.shuffle(opts)
        correct_idx = opts.index(ans)
        options = [str(x) for x in opts]
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=options[i], callback_data=_cb_data(token, i)) for i in range(4)]
            ]
        )
        text = t(loc, "guard.join_captcha.math", name=name, ttl=ttl, a=a, b=b)
        options_payload = _pack_options(options, expected=str(ans))
    elif kind == "emoji":
        pool = ["🐷", "⭐", "🔥", "❤️", "🌈", "☀️"]
        random.shuffle(pool)
        options = pool[:6]
        correct_idx = random.randint(0, 5)
        target = options[correct_idx]
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=options[0], callback_data=_cb_data(token, 0)),
                    InlineKeyboardButton(text=options[1], callback_data=_cb_data(token, 1)),
                    InlineKeyboardButton(text=options[2], callback_data=_cb_data(token, 2)),
                ],
                [
                    InlineKeyboardButton(text=options[3], callback_data=_cb_data(token, 3)),
                    InlineKeyboardButton(text=options[4], callback_data=_cb_data(token, 4)),
                    InlineKeyboardButton(text=options[5], callback_data=_cb_data(token, 5)),
                ],
            ]
        )
        text = t(loc, "guard.join_captcha.emoji", name=name, ttl=ttl, target=target)
        options_payload = _pack_options(options)
    elif kind == "word_emoji":
        w, ans_emoji, distr = random.choice(emoji_sets)
        pool = [ans_emoji] + list(distr)
        random.shuffle(pool)
        options = pool[:6]
        correct_idx = options.index(ans_emoji)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=options[0], callback_data=_cb_data(token, 0)),
                    InlineKeyboardButton(text=options[1], callback_data=_cb_data(token, 1)),
                    InlineKeyboardButton(text=options[2], callback_data=_cb_data(token, 2)),
                ],
                [
                    InlineKeyboardButton(text=options[3], callback_data=_cb_data(token, 3)),
                    InlineKeyboardButton(text=options[4], callback_data=_cb_data(token, 4)),
                    InlineKeyboardButton(text=options[5], callback_data=_cb_data(token, 5)),
                ],
            ]
        )
        text = t(loc, "guard.join_captcha.word_emoji", name=name, ttl=ttl, word=html.escape(w))
        options_payload = _pack_options(options)
    elif kind == "digits":
        digits = "".join(str(random.randint(0, 9)) for _ in range(4))
        photo_bytes = _make_digits_png(digits)
        text = t(loc, "guard.join_captcha.digits", name=name, ttl=ttl)
        options_payload = _pack_options([], expected=digits, is_photo=bool(photo_bytes))
        kb = None
    elif kind == "word_send":
        word = random.choice(send_bank)
        text = t(loc, "guard.join_captcha.word_send", name=name, ttl=ttl, word=html.escape(word))
        options_payload = _pack_options([], expected=word)
        kb = None
    else:  # word_guess
        word = random.choice(guess_bank)
        if len(word) < 4:
            long_choices = [w for w in guess_bank if len(w) >= 4]
            word = random.choice(long_choices) if long_choices else word
        pos = random.randint(0, len(word) - 1)
        masked = list(word)
        masked[pos] = "*"
        if len(word) >= 6 and random.random() < 0.35:
            pos2 = random.choice([i for i in range(len(word)) if i != pos])
            masked[pos2] = "*"
        hint = "".join(masked)
        text = t(loc, "guard.join_captcha.word_guess", name=name, ttl=ttl, hint=html.escape(hint))
        options_payload = _pack_options([], expected=word)
        kb = None

    restricted = await _try_restrict(bot, chat_id, user_id, allow_plain_text=(kind in KIND_TEXT))

    sent_msg: Any = None
    targets = ([user_id] if prefer_dm else []) + [chat_id]
    digits_plain = ""
    if kind == "digits":
        digits_plain = str(_unpack_options(options_payload).get("expected") or "")

    for target_cid in targets:
        try:
            if kind == "digits" and photo_bytes:
                sent_msg = await bot.send_photo(
                    target_cid,
                    photo=BufferedInputFile(photo_bytes, filename="captcha.png"),
                    caption=text,
                    parse_mode="HTML",
                )
            else:
                body = text
                if kind == "digits" and digits_plain:
                    body = text + f"\n\n<code>{html.escape(digits_plain)}</code>"
                sent_msg = await bot.send_message(
                    target_cid,
                    body,
                    parse_mode="HTML",
                    reply_markup=kb,
                    disable_web_page_preview=True,
                )
            if sent_msg:
                break
        except Exception as e:
            logger.debug("join_captcha send try cid=%s: %s", target_cid, e)
            sent_msg = None

    if kind == "digits" and not sent_msg:
        dfb = digits_plain or "0000"
        try:
            sent_msg = await bot.send_message(
                chat_id,
                t(
                    loc,
                    "guard.join_captcha.digits_plain_fallback",
                    name=name,
                    digits=html.escape(dfb),
                    ttl=ttl,
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("join_captcha digits emergency chat=%s: %s", chat_id, e)

    if not sent_msg:
        if restricted:
            await _unrestrict(bot, chat_id, user_id)
        return

    if kind == "digits":
        d = _unpack_options(options_payload)
        d["photo"] = bool(getattr(sent_msg, "photo", None))
        options_payload = json.dumps(d, ensure_ascii=False)

    message_chat_id = int(sent_msg.chat.id)
    message_id = int(sent_msg.message_id)

    sess = JoinCaptchaSession(
        token=token,
        chat_id=chat_id,
        user_id=user_id,
        kind=kind,
        correct_idx=correct_idx,
        options_json=options_payload,
        message_chat_id=message_chat_id,
        message_id=message_id,
        expires_at=expires_at,
        captcha_scope=(captcha_scope or "join"),
    )
    session.add(sess)
    await session.commit()

    delay_sec = float(ttl * 60)
    asyncio.create_task(_expire_join_captcha(bot, token, delay_sec))


async def maybe_start_join_captcha(bot, session, tg_chat: Chat, chat_row: Any, rule: Any, user: User) -> None:
    if not bool(getattr(rule, "join_captcha_enabled", False)):
        return
    if getattr(user, "is_bot", False):
        return
    if tg_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    chat_id = tg_chat.id
    user_id = user.id
    if await is_admin(bot, chat_id, user_id):
        return

    loc = await owner_locale_for_chat(session, int(chat_id))
    send_bank, guess_bank, emoji_sets = _word_banks(loc)

    ttl = max(1, min(5, int(getattr(rule, "join_captcha_ttl_minutes", 3) or 3)))
    kind = (getattr(rule, "join_captcha_kind", None) or "button").strip().lower()
    if kind not in ALL_KINDS:
        kind = "button"
    if not await chat_owner_has_miniapp_premium(session, int(chat_id)):
        kind = "button"
    prefer_dm = bool(getattr(rule, "join_captcha_prefer_dm", False))

    await session.execute(
        delete(JoinCaptchaSession).where(
            JoinCaptchaSession.chat_id == chat_id,
            JoinCaptchaSession.user_id == user_id,
        )
    )
    await session.flush()

    await _materialize_join_style_captcha(
        bot,
        session,
        tg_chat,
        user,
        loc=loc,
        ttl=ttl,
        kind=kind,
        prefer_dm=prefer_dm,
        captcha_scope="join",
        send_bank=send_bank,
        guess_bank=guess_bank,
        emoji_sets=emoji_sets,
    )


async def maybe_start_filter_media_captcha(bot, session, tg_chat: Chat, chat_row: Any, rule: Any, user: User) -> None:
    """Капча после нарушения гранулярного фильтра медиа: отдельные настройки filter_media_captcha_* в rules."""
    if not bool(getattr(rule, "filter_media_captcha_enabled", False)):
        return
    if getattr(user, "is_bot", False):
        return
    if tg_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    chat_id = tg_chat.id
    user_id = user.id
    if await is_admin(bot, chat_id, user_id):
        return

    loc = await owner_locale_for_chat(session, int(chat_id))
    send_bank, guess_bank, emoji_sets = _word_banks(loc)

    ttl = max(1, min(5, int(getattr(rule, "filter_media_captcha_ttl_minutes", 3) or 3)))
    kind = (getattr(rule, "filter_media_captcha_kind", None) or "button").strip().lower()
    if kind not in ALL_KINDS:
        kind = "button"
    if not await chat_owner_has_miniapp_premium(session, int(chat_id)):
        kind = "button"
    prefer_dm = bool(getattr(rule, "filter_media_captcha_prefer_dm", False))

    await session.execute(
        delete(JoinCaptchaSession).where(
            JoinCaptchaSession.chat_id == chat_id,
            JoinCaptchaSession.user_id == user_id,
        )
    )
    await session.flush()

    await _materialize_join_style_captcha(
        bot,
        session,
        tg_chat,
        user,
        loc=loc,
        ttl=ttl,
        kind=kind,
        prefer_dm=prefer_dm,
        captcha_scope="filter_media",
        send_bank=send_bank,
        guess_bank=guess_bank,
        emoji_sets=emoji_sets,
    )


async def _expire_join_captcha(bot, token: str, delay_sec: float) -> None:
    await asyncio.sleep(delay_sec)
    async with await get_session() as session:
        res = await session.execute(select(JoinCaptchaSession).where(JoinCaptchaSession.token == token).limit(1))
        row = res.scalar_one_or_none()
        if not row:
            return
        chat_id = int(row.chat_id)
        user_id = int(row.user_id)
        mcid = int(row.message_chat_id)
        mid = int(row.message_id)
        cscope = str(getattr(row, "captcha_scope", None) or "join")
        await session.delete(row)
        await session.commit()
    try:
        await bot.delete_message(mcid, mid)
    except TelegramForbiddenError as e:
        await record_join_captcha_expire_delete_failed(chat_id, user_id, mcid, mid, e)
    except TelegramBadRequest:
        pass
    except Exception as e:
        logger.debug("join_captcha expire delete_msg: %s", e)
        await record_join_captcha_expire_delete_failed(chat_id, user_id, mcid, mid, e)
    if cscope == "filter_media":
        try:
            await _unrestrict(bot, chat_id, user_id)
        except Exception:
            pass
        return
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
    except Exception as e:
        logger.debug("join_captcha expire kick %s/%s: %s", chat_id, user_id, e)
    try:
        await _unrestrict(bot, chat_id, user_id)
    except Exception:
        pass


@router.callback_query(F.data.startswith(CB_PREFIX))
async def on_join_captcha_cb(cb: CallbackQuery) -> None:
    if not cb.data or not cb.from_user:
        return
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[0] != "jc":
        return
    _, token, idx_raw = parts
    try:
        picked = int(idx_raw)
    except ValueError:
        await cb.answer()
        return

    async with await get_session() as session:
        res = await session.execute(select(JoinCaptchaSession).where(JoinCaptchaSession.token == token).limit(1))
        row = res.scalar_one_or_none()
        loc_fallback = DEFAULT_LOCALE
        if cb.from_user:
            loc_fallback = await user_locale(session, int(cb.from_user.id))
        if not row:
            await cb.answer(t(loc_fallback, "guard.join_captcha.cb_stale"), show_alert=True)
            return
        loc = await owner_locale_for_chat(session, int(row.chat_id))
        if (row.kind or "") not in KIND_CALLBACK:
            await cb.answer()
            return
        if datetime.now(timezone.utc) > row.expires_at:
            session.delete(row)
            await session.commit()
            await cb.answer(t(loc, "guard.join_captcha.cb_timeout"), show_alert=True)
            return

        uid = int(cb.from_user.id)
        if uid != int(row.user_id):
            await cb.answer(t(loc, "guard.join_captcha.cb_wrong_user"), show_alert=True)
            return

        if picked != int(row.correct_idx):
            await cb.answer(t(loc, "guard.join_captcha.cb_wrong_answer"), show_alert=True)
            return

        chat_id = int(row.chat_id)
        target_uid = int(row.user_id)
        mcid = int(row.message_chat_id)
        mid = int(row.message_id)
        payload = _unpack_options(row.options_json)
        cscope = str(getattr(row, "captcha_scope", None) or "join")
        session.delete(row)
        await session.commit()

    await cb.answer(t(loc, "guard.join_captcha.cb_ok"))
    await _finish_success(cb.bot, chat_id, target_uid, mcid, mid, payload, captcha_scope=cscope)
