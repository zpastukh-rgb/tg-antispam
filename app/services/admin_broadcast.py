"""Рассылка постов из админки всем пользователям бота (личные сообщения)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import date
from urllib.parse import urlencode
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    WebAppInfo,
)
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AdminBroadcast,
    AdminBroadcastDelivery,
    AdminBroadcastMedia,
    AdminBroadcastRun,
    AutopostCampaign,
    Chat,
    User,
    ChatManager,
)

log = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = int(os.getenv("BROADCAST_MAX_UPLOAD_MB", "50")) * 1024 * 1024
_SEND_DELAY_SEC = float(os.getenv("BROADCAST_SEND_DELAY_SEC", "0.005"))
_PROGRESS_COMMIT_EVERY = int(os.getenv("BROADCAST_PROGRESS_COMMIT_EVERY", "10"))


def broadcast_upload_root() -> Path:
    raw = (os.getenv("BROADCAST_UPLOAD_DIR") or "").strip()
    if raw:
        p = Path(raw)
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(gettempdir()) / "antispam_broadcast_uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def normalize_keyboard_rows(raw_rows: Any) -> str | None:
    if not raw_rows:
        return None
    rows_out: list[list[dict[str, Any]]] = []
    if not isinstance(raw_rows, list):
        return None
    for row in raw_rows:
        if not isinstance(row, list):
            continue
        btns: list[dict[str, Any]] = []
        for b in row:
            if not isinstance(b, dict):
                continue
            text = str(b.get("text") or "").strip()
            if not text:
                continue
            item: dict[str, Any] = {"text": text}
            if b.get("url"):
                item["url"] = str(b["url"]).strip()
            elif b.get("web_app_url"):
                item["web_app"] = {"url": str(b["web_app_url"]).strip()}
            elif b.get("callback_data"):
                item["callback_data"] = str(b["callback_data"])[:64]
            else:
                continue
            btns.append(item)
        if btns:
            rows_out.append(btns)
    if not rows_out:
        return None
    return json.dumps({"rows": rows_out}, ensure_ascii=False)


def keyboard_markup_from_json(s: str | None) -> InlineKeyboardMarkup | None:
    if not s:
        return None
    try:
        data = json.loads(s)
    except Exception:
        return None
    rows = data.get("rows") or []
    kb: list[list[InlineKeyboardButton]] = []
    for row in rows:
        line: list[InlineKeyboardButton] = []
        for b in row:
            text = b.get("text")
            if not text:
                continue
            if b.get("url"):
                line.append(InlineKeyboardButton(text=text, url=b["url"]))
            elif b.get("web_app") and isinstance(b["web_app"], dict) and b["web_app"].get("url"):
                line.append(InlineKeyboardButton(text=text, web_app=WebAppInfo(url=b["web_app"]["url"])))
            elif b.get("callback_data"):
                line.append(InlineKeyboardButton(text=text, callback_data=str(b["callback_data"])[:64]))
        if line:
            kb.append(line)
    return InlineKeyboardMarkup(inline_keyboard=kb) if kb else None


# Префикс трекинга callback-кнопок рассылки (до 64 байт: bcM:{id}:{idx})
BROADCAST_TRACKED_CALLBACK_PREFIX = "bcM:"


def list_broadcast_callback_payloads_for_layout(keyboard_json: str | None, *, layout_group: bool) -> list[str]:
    """Тот же порядок callback-кнопок, что у keyboard_for_target → _track_keyboard_markup (только payload до обёртки)."""
    kb = keyboard_markup_from_json(keyboard_json)
    if not kb:
        return []
    kb2 = keyboard_for_target(kb, "group") if layout_group else kb
    if not kb2:
        return []
    out: list[str] = []
    for row in kb2.inline_keyboard or []:
        for b in row:
            txt = str(getattr(b, "text", "") or "").strip()
            if not txt:
                continue
            if getattr(b, "web_app", None) and getattr(getattr(b, "web_app", None), "url", None):
                continue
            if getattr(b, "url", None):
                continue
            cb = getattr(b, "callback_data", None)
            if cb:
                out.append(str(cb)[:64])
    return out


def keyboard_for_target(base: InlineKeyboardMarkup | None, target_kind: str) -> InlineKeyboardMarkup | None:
    if not base:
        return None
    if str(target_kind or "") != "group":
        return base
    # WebApp-кнопки невалидны в группах: преобразуем их в обычные URL-кнопки.
    rows: list[list[InlineKeyboardButton]] = []
    for row in (base.inline_keyboard or []):
        line: list[InlineKeyboardButton] = []
        for b in row:
            txt = str(getattr(b, "text", "") or "").strip()
            if not txt:
                continue
            wa = getattr(b, "web_app", None)
            if wa and getattr(wa, "url", None):
                line.append(InlineKeyboardButton(text=txt, url=str(wa.url)))
                continue
            if getattr(b, "url", None):
                line.append(InlineKeyboardButton(text=txt, url=str(b.url)))
                continue
            if getattr(b, "callback_data", None):
                line.append(InlineKeyboardButton(text=txt, callback_data=str(b.callback_data)[:64]))
                continue
        if line:
            rows.append(line)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def _broadcast_click_track_base() -> str:
    raw = (
        os.getenv("BROADCAST_TRACK_BASE_URL")
        or os.getenv("GUARD_API_BASE_URL")
        or os.getenv("VITE_API_BASE_URL")
        or os.getenv("MINI_APP_URL")
        or os.getenv("WEBAPP_URL")
        or ""
    )
    return str(raw or "").strip().rstrip("/")


def broadcast_url_tracking_configured() -> bool:
    """True, если URL-кнопки рассылки смогут вести через /api/public/broadcast/click (нужен публичный базовый URL API)."""
    return bool(_broadcast_click_track_base())


def _wrap_tracked_url(
    url: str,
    *,
    broadcast_id: int,
    target_kind: str,
    target_id: int,
) -> str:
    src = str(url or "").strip()
    if not src:
        return src
    if not (src.startswith("http://") or src.startswith("https://")):
        return src
    base = _broadcast_click_track_base()
    if not base:
        return src
    qs = urlencode(
        {
            "b": int(broadcast_id),
            "k": str(target_kind or "user")[:16],
            "t": int(target_id),
            "u": src,
        }
    )
    return f"{base}/api/public/broadcast/click?{qs}"


def _track_keyboard_markup(
    base: InlineKeyboardMarkup | None,
    *,
    broadcast_id: int,
    target_kind: str,
    target_id: int,
) -> InlineKeyboardMarkup | None:
    if not base:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    cb_flat = 0
    for row in (base.inline_keyboard or []):
        line: list[InlineKeyboardButton] = []
        for b in row:
            txt = str(getattr(b, "text", "") or "").strip()
            if not txt:
                continue
            wa = getattr(b, "web_app", None)
            if wa and getattr(wa, "url", None):
                line.append(
                    InlineKeyboardButton(
                        text=txt,
                        url=_wrap_tracked_url(
                            str(wa.url),
                            broadcast_id=int(broadcast_id),
                            target_kind=str(target_kind),
                            target_id=int(target_id),
                        ),
                    )
                )
                continue
            if getattr(b, "url", None):
                line.append(
                    InlineKeyboardButton(
                        text=txt,
                        url=_wrap_tracked_url(
                            str(b.url),
                            broadcast_id=int(broadcast_id),
                            target_kind=str(target_kind),
                            target_id=int(target_id),
                        ),
                    )
                )
                continue
            if getattr(b, "callback_data", None):
                idx = cb_flat
                cb_flat += 1
                token = f"{BROADCAST_TRACKED_CALLBACK_PREFIX}{int(broadcast_id)}:{idx}"
                if len(token) > 64:
                    log.warning("broadcast callback token > 64, tracking disabled for this button bid=%s", broadcast_id)
                    line.append(InlineKeyboardButton(text=txt, callback_data=str(b.callback_data)[:64]))
                else:
                    line.append(InlineKeyboardButton(text=txt, callback_data=token))
                continue
        if line:
            rows.append(line)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def parse_mode_or_none(raw: str | None) -> str | None:
    if not raw:
        return None
    m = str(raw).strip()
    if not m or m.lower() == "none":
        return None
    allowed = {"HTML", "Markdown", "MarkdownV2"}
    if m not in allowed:
        return None
    return m


def _truncate(s: str, n: int) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


async def upload_to_storage_get_file_id(
    bot: Bot,
    storage_chat_id: int,
    media_kind: str,
    data: bytes,
    filename: str,
) -> str | None:
    bio = BufferedInputFile(data, filename=filename or "file.bin")
    try:
        if media_kind == "photo":
            m = await bot.send_photo(storage_chat_id, photo=bio)
            if m.photo:
                return m.photo[-1].file_id
        elif media_kind == "video":
            m = await bot.send_video(storage_chat_id, video=bio)
            if m.video:
                return m.video.file_id
        elif media_kind == "animation":
            m = await bot.send_animation(storage_chat_id, animation=bio)
            if m.animation:
                return m.animation.file_id
        elif media_kind == "document":
            m = await bot.send_document(storage_chat_id, document=bio)
            if m.document:
                return m.document.file_id
        elif media_kind == "audio":
            m = await bot.send_audio(storage_chat_id, audio=bio)
            if m.audio:
                return m.audio.file_id
    except Exception as e:
        log.warning("broadcast storage upload failed: %s", e)
    return None


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
    for i in range(0, len(items), max(1, size)):
        out.append(items[i : i + max(1, size)])
    return out


def _input_media_item(
    media: dict[str, Any],
    *,
    caption: str | None = None,
    parse_mode: str | None = None,
):
    kind = str(media.get("kind") or "photo")
    source = media.get("file_id") or BufferedInputFile(media["bytes"], filename=media.get("name") or "file.bin")
    if kind == "video":
        return InputMediaVideo(media=source, caption=caption, parse_mode=parse_mode)
    if kind == "audio":
        return InputMediaAudio(media=source, caption=caption, parse_mode=parse_mode)
    if kind == "document" or kind == "animation":
        return InputMediaDocument(media=source, caption=caption, parse_mode=parse_mode)
    return InputMediaPhoto(media=source, caption=caption, parse_mode=parse_mode)


async def _send_single_media(
    bot: Bot,
    chat_id: int,
    media: dict[str, Any],
    *,
    caption: str | None = None,
    parse_mode: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    kind = str(media.get("kind") or "photo")
    def _source():
        fid = media.get("file_id")
        if fid:
            return fid
        return BufferedInputFile(media["bytes"], filename=media.get("name") or "file.bin")

    async def _do_send(cap: str | None, pm: str | None, rm: InlineKeyboardMarkup | None):
        source = _source()
        if kind == "photo":
            await bot.send_photo(chat_id, source, caption=cap, parse_mode=pm if cap else None, reply_markup=rm)
            return
        if kind == "video":
            await bot.send_video(chat_id, source, caption=cap, parse_mode=pm if cap else None, reply_markup=rm)
            return
        if kind == "audio":
            await bot.send_audio(chat_id, source, caption=cap, parse_mode=pm if cap else None, reply_markup=rm)
            return
        if kind == "animation":
            await bot.send_animation(chat_id, source, caption=cap, parse_mode=pm if cap else None, reply_markup=rm)
            return
        await bot.send_document(chat_id, source, caption=cap, parse_mode=pm if cap else None, reply_markup=rm)

    # Поэтапная деградация: с кнопками+rich -> с кнопками+plain -> без кнопок+plain -> без всего.
    if caption:
        plain = re.sub(r"<[^>]+>", "", str(caption or "")).strip()[:1024]
    else:
        plain = None
    attempts: list[tuple[str | None, str | None, InlineKeyboardMarkup | None]] = [
        (caption, parse_mode if caption else None, reply_markup),
        (plain or None, None, reply_markup),
        (plain or None, None, None),
        (None, None, None),
    ]
    last_error: Exception | None = None
    for cap_i, pm_i, rm_i in attempts:
        try:
            await _do_send(cap_i, pm_i, rm_i)
            return
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error
    raise RuntimeError("send single media failed")


async def _send_text_with_fallback(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    plain = re.sub(r"<[^>]+>", "", str(text or "")).strip()[:4096]
    attempts: list[tuple[str, str | None, InlineKeyboardMarkup | None]] = [
        (text, parse_mode, reply_markup),
        (plain or text, None, reply_markup),
        (plain or text, None, None),
    ]
    last_error: Exception | None = None
    for txt, pm, rm in attempts:
        try:
            await bot.send_message(chat_id, txt, parse_mode=pm, reply_markup=rm)
            return
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error
    raise RuntimeError("send text failed")


async def _send_media_album_or_fallback(
    bot: Bot,
    chat_id: int,
    media_items: list[dict[str, Any]],
    *,
    caption: str | None,
    parse_mode: str | None,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    """
    Отправка 2+ медиа с инлайн-кнопками у первого сообщения:
    - первое медиа: caption + inline keyboard;
    - остальные: album (sendMediaGroup) чанками по 10.
    Если Telegram отвергает sendMediaGroup (смешанный/проблемный набор) —
    fallback на отправку по одному в исходном порядке.
    """
    if not media_items:
        return

    first_item = media_items[0]
    rest_items = media_items[1:]
    try:
        await _send_single_media(
            bot,
            chat_id,
            first_item,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        if not rest_items:
            return
        for group in _chunks(rest_items, 10):
            media_group = []
            for m in group:
                media_group.append(_input_media_item(m, caption=None, parse_mode=None))
            await bot.send_media_group(chat_id, media=media_group)
    except Exception as e:
        log.warning("broadcast send_media_group fallback chat=%s: %s", chat_id, e)
        sent_caption = False
        for idx, m in enumerate(media_items):
            cap_i = caption if (not sent_caption and idx == 0) else None
            parse_i = parse_mode if cap_i else None
            rm_i = reply_markup if idx == 0 else None
            await _send_single_media(
                bot,
                chat_id,
                m,
                caption=cap_i,
                parse_mode=parse_i,
                reply_markup=rm_i,
            )
            if cap_i:
                sent_caption = True
        return


def sanitize_autopost_state(raw: Any) -> dict[str, Any]:
    """Внутреннее состояние планировщика (_state) — только доверенные ключи."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k in ("day", "next_slot", "rot_i", "plan_sig"):
        if k not in raw:
            continue
        v = raw[k]
        if k == "day" and isinstance(v, str):
            out[k] = v[:16]
        elif k == "plan_sig" and isinstance(v, str):
            out[k] = v[:120]
        elif k in ("next_slot", "rot_i"):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
    return out


def normalize_autopost_payload(raw: Any) -> dict[str, Any] | None:
    """Валидация настроек автопостинга для сохранения в БД (JSON)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    rs = str(raw.get("runState") or "stopped").strip().lower()
    if rs not in ("stopped", "running", "paused"):
        rs = "stopped"
    mode = str(raw.get("scheduleMode") or "every_day").strip().lower()
    if mode not in ("every_day", "weekdays"):
        mode = "every_day"
    wd_raw = raw.get("weekdays")
    weekdays: list[int] = []
    if isinstance(wd_raw, list):
        for x in wd_raw:
            try:
                d = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= d <= 6:
                weekdays.append(d)
    weekdays = sorted(set(weekdays))
    if mode == "every_day":
        weekdays = [0, 1, 2, 3, 4, 5, 6]
    elif not weekdays:
        weekdays = [0, 1, 2, 3, 4]
    try:
        posts = int(raw.get("postsPerDay") or 1)
    except (TypeError, ValueError):
        posts = 1
    posts = max(1, min(288, posts))
    ws = str(raw.get("windowStart") or "10:00").strip()[:8] or "10:00"
    we = str(raw.get("windowEnd") or "21:00").strip()[:8] or "21:00"
    spread = raw.get("spreadInWindow")
    spread_b = True if spread is None else bool(spread)
    g_ids: list[int] = []
    g_raw = raw.get("group_chat_ids")
    if isinstance(g_raw, list):
        for x in g_raw[:500]:
            try:
                v = int(x)
            except (TypeError, ValueError):
                continue
            if v < 0:
                g_ids.append(v)
    g_ids = sorted(set(g_ids))
    ch_ids: list[int] = []
    ch_raw = raw.get("channel_chat_ids")
    if isinstance(ch_raw, list):
        for x in ch_raw[:500]:
            try:
                v = int(x)
            except (TypeError, ValueError):
                continue
            if v < 0:
                ch_ids.append(v)
    ch_ids = sorted(set(ch_ids))
    use_all_posts = raw.get("use_all_broadcasts")
    use_all_b = bool(use_all_posts) if use_all_posts is not None else False
    br_raw = raw.get("broadcast_ids")
    b_ids: list[int] = []
    if isinstance(br_raw, list) and not use_all_b:
        for x in br_raw[:50]:
            try:
                v = int(x)
            except (TypeError, ValueError):
                continue
            if v > 0:
                b_ids.append(v)
    b_ids = sorted(set(b_ids))
    tz_raw = str(raw.get("timezone") or "").strip()[:80]
    tz_use = tz_raw or "Europe/Moscow"
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(tz_use)
    except Exception:
        tz_use = "Europe/Moscow"
    tgt = str(raw.get("autopost_target") or raw.get("target") or "groups").strip().lower()
    if tgt not in ("groups", "users"):
        tgt = "groups"
    ch_off = raw.get("autopost_channels_disabled")
    channels_disabled_b = bool(ch_off) if ch_off is not None else False
    start_date = str(raw.get("startDate") or "").strip()[:10]
    if start_date:
        try:
            y, m, d = start_date.split("-")
            _ = date(int(y), int(m), int(d))
        except Exception:
            start_date = ""
    return {
        "runState": rs,
        "scheduleMode": mode,
        "weekdays": weekdays,
        "postsPerDay": posts,
        "windowStart": ws,
        "windowEnd": we,
        "timezone": tz_use,
        "spreadInWindow": spread_b,
        "autopost_target": tgt,
        # Пустой список = при автопосте/рассылке в группы — все активные группы этого бота (как раньше).
        "group_chat_ids": g_ids,
        "channel_chat_ids": ch_ids,
        # Если true — автопост не уходит в каналы (список channel_chat_ids в пресете сохраняется для снятия галочки).
        "autopost_channels_disabled": channels_disabled_b,
        # Ротация постов: все черновики или явный список id (включая текущий при сохранении на сервере).
        "use_all_broadcasts": use_all_b,
        "broadcast_ids": [] if use_all_b else b_ids,
        # Локальная дата старта в timezone кампании (YYYY-MM-DD). Пусто = старт сразу.
        "startDate": start_date,
    }


async def finalize_autopost_json_for_owner(
    session: AsyncSession,
    *,
    viewer_telegram_id: int,
    owner_telegram_id: int,
    anchor_broadcast_id: int,
    allow_scope_all_for_owner: bool,
    force_groups_target: bool,
    ap_raw: Any,
    existing_autopost_json: str | None,
) -> dict[str, Any]:
    """Нормализация и фильтрация id для сохранения autopost (черновик или кампания)."""
    prev_state: dict | None = None
    prev_run_state = ""
    if existing_autopost_json:
        try:
            prev_ap = json.loads(existing_autopost_json)
            if isinstance(prev_ap, dict):
                prev_run_state = str(prev_ap.get("runState") or "").lower()
                if isinstance(prev_ap.get("_state"), dict):
                    prev_state = prev_ap.get("_state")
        except Exception:
            prev_state = None
    ap = normalize_autopost_payload(ap_raw)
    if ap is None:
        raise ValueError("autopost: неверный формат")
    if str(ap.get("runState") or "").lower() == "stopped":
        ap.pop("_state", None)
    elif str(ap.get("runState") or "").lower() == "running" and prev_run_state == "stopped":
        ap["_state"] = {}
    elif prev_state:
        ap["_state"] = sanitize_autopost_state(prev_state)
    ap["group_chat_ids"] = await filter_group_chat_ids_for_broadcast(
        session,
        owner_telegram_id,
        allow_all_groups=allow_scope_all_for_owner,
        raw_ids=ap.get("group_chat_ids"),
        dest_kind="group",
    )
    ap["channel_chat_ids"] = await filter_group_chat_ids_for_broadcast(
        session,
        owner_telegram_id,
        allow_all_groups=allow_scope_all_for_owner,
        raw_ids=ap.get("channel_chat_ids"),
        dest_kind="channel",
    )
    use_all_b, b_ids = await filter_autopost_broadcast_refs(
        session,
        owner_telegram_id,
        int(anchor_broadcast_id),
        use_all=bool(ap.get("use_all_broadcasts")),
        raw_ids=ap.get("broadcast_ids"),
        allow_any_broadcast=allow_scope_all_for_owner,
    )
    ap["use_all_broadcasts"] = use_all_b
    ap["broadcast_ids"] = b_ids
    if force_groups_target:
        ap["autopost_target"] = "groups"
    return ap


async def filter_autopost_broadcast_refs(
    session: AsyncSession,
    viewer_telegram_id: int,
    current_broadcast_id: int,
    *,
    use_all: bool,
    raw_ids: list[int] | None,
    allow_any_broadcast: bool,
) -> tuple[bool, list[int]]:
    """Возвращает (use_all, ids). При use_all список id пустой; иначе — валидные id постов одного владельца (или любые при allow_any_broadcast)."""
    if use_all:
        return True, []
    cleaned = sorted({int(x) for x in (raw_ids or []) if int(x) > 0})[:50]
    if not cleaned:
        return False, [int(current_broadcast_id)]
    q = select(AdminBroadcast.id).where(AdminBroadcast.id.in_(cleaned))
    if not allow_any_broadcast:
        q = q.where(AdminBroadcast.admin_telegram_id == int(viewer_telegram_id))
    res = await session.execute(q)
    ok = sorted({int(x[0]) for x in res.all()})
    if int(current_broadcast_id) not in ok:
        ok.append(int(current_broadcast_id))
    return False, sorted(set(ok))


async def filter_group_chat_ids_for_broadcast(
    session: AsyncSession,
    viewer_telegram_id: int,
    *,
    allow_all_groups: bool,
    raw_ids: list[int] | None,
    dest_kind: str = "any",
) -> list[int]:
    """Оставляет только id чатов, которые есть в БД у этого бота и разрешены для данного админа."""
    if not raw_ids:
        return []
    cleaned = sorted({int(x) for x in raw_ids if int(x) < 0})[:500]
    if not cleaned:
        return []
    kind = (dest_kind or "any").strip().lower()
    if kind == "group":
        kind_clause = or_(Chat.chat_kind.is_(None), Chat.chat_kind == "group")
    elif kind == "channel":
        kind_clause = Chat.chat_kind == "channel"
    else:
        kind_clause = or_(Chat.chat_kind.is_(None), Chat.chat_kind.in_(("group", "channel")))
    q = select(Chat.id).where(
        Chat.is_active.is_(True),
        Chat.is_log_chat.is_(False),
        Chat.id.in_(cleaned),
        kind_clause,
    )
    if not allow_all_groups:
        sub = select(ChatManager.chat_id).where(ChatManager.user_id == int(viewer_telegram_id)).subquery()
        q = q.where(or_(Chat.owner_user_id == int(viewer_telegram_id), Chat.id.in_(select(sub.c.chat_id))))
    res = await session.execute(q)
    ok = {int(x[0]) for x in res.all()}
    return sorted(ok & set(cleaned))


def broadcast_row_to_dict(row: AdminBroadcast) -> dict[str, Any]:
    kbd = None
    if row.keyboard_json:
        try:
            kbd = json.loads(row.keyboard_json)
        except Exception:
            kbd = None
    media_items: list[dict[str, Any]] = []
    media_rel = getattr(row, "media_items", None)
    if media_rel:
        media_items = [
            {
                "id": int(m.id),
                "media_kind": str(m.media_kind or "photo"),
                "media_original_name": str(m.media_original_name or ""),
                "has_file_id": bool(m.telegram_file_id),
            }
            for m in media_rel
        ]
    autopost: dict[str, Any] | None = None
    raw_ap = getattr(row, "autopost_json", None)
    if raw_ap:
        try:
            parsed = json.loads(raw_ap) if isinstance(raw_ap, str) else None
            if isinstance(parsed, dict):
                autopost = normalize_autopost_payload(parsed)
        except Exception:
            autopost = None
    return {
        "id": row.id,
        "title": row.title or "",
        "body_text": row.body_text or "",
        "parse_mode": row.parse_mode,
        "keyboard": kbd,
        "media_kind": row.media_kind or "none",
        "media_original_name": row.media_original_name or "",
        "media_items": media_items,
        "has_media_file": bool(row.media_local_name),
        "telegram_file_id": bool(row.telegram_file_id),
        "status": row.status,
        "admin_telegram_id": int(row.admin_telegram_id),
        "recipient_total": int(row.recipient_total or 0),
        "recipient_ok": int(row.recipient_ok or 0),
        "recipient_fail": int(row.recipient_fail or 0),
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "autopost": autopost,
    }


async def broadcast_ids_in_autopost_rotations(session: AsyncSession, owner_telegram_id: int) -> set[int]:
    """ID постов (якорь + ротация), которые входят в хотя бы одну автокампанию владельца."""
    cq = await session.execute(
        select(AutopostCampaign).where(AutopostCampaign.admin_telegram_id == int(owner_telegram_id))
    )
    camps = list(cq.scalars().all())
    linked: set[int] = set()
    all_drafts_cache: set[int] | None = None

    for camp in camps:
        ap_dict = None
        raw_ap = getattr(camp, "autopost_json", None) or ""
        if raw_ap:
            try:
                parsed = json.loads(raw_ap) if isinstance(raw_ap, str) else None
                if isinstance(parsed, dict):
                    ap_dict = normalize_autopost_payload(parsed)
            except Exception:
                ap_dict = None
        anchor = int(getattr(camp, "anchor_broadcast_id", 0) or 0)
        rot: set[int] = set()
        if anchor > 0:
            rot.add(anchor)
        if ap_dict:
            if bool(ap_dict.get("use_all_broadcasts")):
                if all_drafts_cache is None:
                    dq = await session.execute(
                        select(AdminBroadcast.id).where(
                            AdminBroadcast.admin_telegram_id == int(owner_telegram_id),
                            AdminBroadcast.status == "draft",
                        )
                    )
                    all_drafts_cache = {int(x[0]) for x in dq.all()}
                rot |= all_drafts_cache or set()
            else:
                for raw in ap_dict.get("broadcast_ids") or []:
                    try:
                        x = int(raw)
                        if x > 0:
                            rot.add(x)
                    except (TypeError, ValueError):
                        pass
        linked |= rot
    return linked


async def _bid_in_autopost_rotation(
    session: AsyncSession, owner_telegram_id: int, bid: int
) -> bool:
    """Проверка по одному id: входит ли пост в ротацию хотя бы одной автокампании.

    Без сборки полного множества id — для GET одного поста вместо тяжёлого
    ``broadcast_ids_in_autopost_rotations`` по всем постам.
    """
    bid = int(bid)
    cq = await session.execute(
        select(AutopostCampaign).where(AutopostCampaign.admin_telegram_id == int(owner_telegram_id))
    )
    camps = list(cq.scalars().all())
    all_drafts_cache: set[int] | None = None

    for camp in camps:
        anchor = int(getattr(camp, "anchor_broadcast_id", 0) or 0)
        if anchor == bid:
            return True
        ap_dict = None
        raw_ap = getattr(camp, "autopost_json", None) or ""
        if raw_ap:
            try:
                parsed = json.loads(raw_ap) if isinstance(raw_ap, str) else None
                if isinstance(parsed, dict):
                    ap_dict = normalize_autopost_payload(parsed)
            except Exception:
                ap_dict = None
        if ap_dict:
            if bool(ap_dict.get("use_all_broadcasts")):
                if all_drafts_cache is None:
                    dq = await session.execute(
                        select(AdminBroadcast.id).where(
                            AdminBroadcast.admin_telegram_id == int(owner_telegram_id),
                            AdminBroadcast.status == "draft",
                        )
                    )
                    all_drafts_cache = {int(x[0]) for x in dq.all()}
                if bid in (all_drafts_cache or set()):
                    return True
            else:
                for raw in ap_dict.get("broadcast_ids") or []:
                    try:
                        if int(raw) == bid:
                            return True
                    except (TypeError, ValueError):
                        pass
    return False


async def broadcast_list_origins_for_rows(
    session: AsyncSession,
    owner_telegram_id: int,
    rows: list[AdminBroadcast] | tuple[AdminBroadcast, ...],
) -> dict[int, str]:
    """Для списка постов: one_shot | autopost | mixed — по run_source и ротации автокампаний."""
    row_list = list(rows)
    ids = [int(r.id) for r in row_list]
    if not ids:
        return {}
    rq = await session.execute(
        select(AdminBroadcastRun.broadcast_id, AdminBroadcastRun.run_source).where(
            AdminBroadcastRun.broadcast_id.in_(ids)
        )
    )
    per: dict[int, set[str]] = {}
    for bid, rs in rq.all():
        raw = str(rs or "").strip().lower() or "manual"
        cat = "autopost" if raw == "autopost" else "manual"
        per.setdefault(int(bid), set()).add(cat)

    # Один пост (GET /admin/broadcasts/:id): не тянем полный набор id из всех ротаций.
    one_in_rot: bool | None = None
    in_rot: set[int] = set()
    if len(row_list) == 1:
        one_in_rot = await _bid_in_autopost_rotation(session, int(owner_telegram_id), int(row_list[0].id))
    else:
        in_rot = await broadcast_ids_in_autopost_rotations(session, int(owner_telegram_id))
    out: dict[int, str] = {}
    for r in row_list:
        bid = int(r.id)
        srcs = per.get(bid, set())
        has_ap = "autopost" in srcs
        has_mn = "manual" in srcs
        if has_ap and has_mn:
            out[bid] = "mixed"
        elif has_ap:
            out[bid] = "autopost"
        elif has_mn:
            out[bid] = "one_shot"
        else:
            if one_in_rot is not None:
                out[bid] = "autopost" if one_in_rot else "one_shot"
            else:
                out[bid] = "autopost" if bid in in_rot else "one_shot"
    return out


async def run_broadcast_job(
    broadcast_id: int,
    target: str = "users",
    target_chat_ids: list[int] | None = None,
    *,
    keep_draft_after: bool = False,
    run_source: str = "manual",
) -> None:
    from app.db.session import get_session

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        log.error("run_broadcast_job: BOT_TOKEN missing")
        return

    bot = Bot(token=token)
    try:
        session = await get_session()
        async with session:
            row = await session.get(AdminBroadcast, int(broadcast_id))
            if not row or row.status != "sending":
                return

            storage_raw = (os.getenv("BROADCAST_STORAGE_CHAT_ID") or "").strip()
            storage_id = int(storage_raw) if storage_raw else 0

            media_rows_q = await session.execute(
                select(AdminBroadcastMedia)
                .where(AdminBroadcastMedia.broadcast_id == int(row.id))
                .order_by(AdminBroadcastMedia.id.asc())
            )
            media_rows = media_rows_q.scalars().all()
            if not media_rows and (row.media_kind or "none").lower() != "none" and row.media_local_name:
                # Legacy single-file fallback.
                media_rows = [
                    AdminBroadcastMedia(
                        broadcast_id=int(row.id),
                        media_kind=str(row.media_kind or "photo"),
                        media_local_name=str(row.media_local_name),
                        media_original_name=str(row.media_original_name or row.media_local_name),
                        telegram_file_id=row.telegram_file_id,
                    )
                ]
            prepared_media: list[dict[str, Any]] = []
            for m in media_rows:
                mk = str(m.media_kind or "photo").lower()
                if mk == "animation":
                    mk = "document"
                fid = str(m.telegram_file_id or "").strip() or None
                raw_bytes: bytes | None = None
                raw_name: str | None = None
                if not fid:
                    path = broadcast_upload_root() / str(m.media_local_name or "")
                    if not path.is_file():
                        continue
                    raw_bytes = path.read_bytes()
                    raw_name = str(m.media_local_name or "")
                    if storage_id and isinstance(m, AdminBroadcastMedia):
                        new_fid = await upload_to_storage_get_file_id(bot, storage_id, mk, raw_bytes, raw_name)
                        if new_fid:
                            m.telegram_file_id = new_fid
                            session.add(m)
                            await session.commit()
                            fid = new_fid
                prepared_media.append({"kind": mk, "file_id": fid, "bytes": raw_bytes, "name": raw_name})
            pm = parse_mode_or_none(row.parse_mode)
            kb = keyboard_markup_from_json(row.keyboard_json)
            text = row.body_text or ""
            text_msg = _truncate(text, 4096)
            cap = _truncate(text, 1024) if prepared_media else None

            recipients: list[tuple[int, str]] = []
            target_mode = (target or "users").strip().lower()
            if target_mode in ("users", "all"):
                res_users = await session.execute(
                    select(User.telegram_id).where(User.status == "active", User.telegram_id > 0)
                )
                recipients.extend((int(x[0]), "user") for x in res_users.all())
            if target_mode in ("groups", "all"):
                if target_chat_ids:
                    recipients.extend((int(x), "group") for x in target_chat_ids if int(x) != 0)
                else:
                    res_chats = await session.execute(
                        select(Chat.id).where(
                            Chat.is_active.is_(True),
                            Chat.is_log_chat.is_(False),
                            Chat.id < 0,
                            or_(Chat.chat_kind.is_(None), Chat.chat_kind == "group"),
                        )
                    )
                    recipients.extend((int(x[0]), "group") for x in res_chats.all())
            # remove duplicates while keeping deterministic order
            dedup: dict[int, str] = {}
            for rid, rkind in recipients:
                if rid not in dedup:
                    dedup[rid] = rkind
            recipients = [(rid, dedup[rid]) for rid in dedup.keys()]
            users_count = sum(1 for _, k in recipients if str(k) == "user")
            groups_count = sum(1 for _, k in recipients if str(k) == "group")
            log.warning(
                "broadcast recipients prepared: id=%s target=%s total=%s users=%s groups=%s",
                int(row.id),
                target_mode,
                len(recipients),
                users_count,
                groups_count,
            )

            row.recipient_total = len(recipients)
            row.recipient_ok = 0
            row.recipient_fail = 0
            await session.commit()

            ok = 0
            fail = 0
            audience_total = 0
            audience_ok = 0
            first_fail: str | None = None
            batch_id = uuid.uuid4().hex
            delivery_enabled = False
            delivery_has_batch_id = False
            delivery_has_target_id = False
            delivery_has_error_message = False
            try:
                col_q = await session.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'admin_broadcast_delivery'
                        """
                    )
                )
                cols = {str(x[0] or "") for x in col_q.all()}
                required = {"broadcast_id", "target_kind", "ok"}
                delivery_enabled = required.issubset(cols)
                delivery_has_batch_id = "batch_id" in cols
                delivery_has_target_id = "target_id" in cols
                delivery_has_error_message = "error_message" in cols
            except Exception:
                delivery_enabled = False
                delivery_has_batch_id = False
                delivery_has_target_id = False
                delivery_has_error_message = False

            async def _insert_delivery(ok_value: bool, err_text: str | None, target_value: int):
                nonlocal delivery_enabled
                if not delivery_enabled:
                    return
                cols = ["broadcast_id"]
                vals = [":broadcast_id"]
                params: dict[str, Any] = {"broadcast_id": int(row.id)}
                if delivery_has_batch_id:
                    cols.append("batch_id")
                    vals.append(":batch_id")
                    params["batch_id"] = batch_id
                cols.append("target_kind")
                vals.append(":target_kind")
                params["target_kind"] = target_kind
                if delivery_has_target_id:
                    cols.append("target_id")
                    vals.append(":target_id")
                    params["target_id"] = int(target_value)
                cols.append("ok")
                vals.append(":ok")
                params["ok"] = bool(ok_value)
                if delivery_has_error_message:
                    cols.append("error_message")
                    vals.append(":error_message")
                    params["error_message"] = (str(err_text or "")[:1000] if err_text else None)
                try:
                    await session.execute(
                        text(
                            f"INSERT INTO admin_broadcast_delivery ({', '.join(cols)}) "
                            f"VALUES ({', '.join(vals)})"
                        ),
                        params,
                    )
                except Exception as ie:
                    delivery_enabled = False
                    log.warning("broadcast delivery logging disabled (schema mismatch): %s", ie)
            processed = 0
            commit_every = max(1, _PROGRESS_COMMIT_EVERY)
            for tid, target_kind in recipients:
                try:
                    kb_target = keyboard_for_target(kb, target_kind)
                    kb_target = _track_keyboard_markup(
                        kb_target,
                        broadcast_id=int(row.id),
                        target_kind=str(target_kind),
                        target_id=int(tid),
                    )
                    target_audience = 1
                    if str(target_kind) == "group":
                        try:
                            target_audience = max(1, int(await bot.get_chat_member_count(int(tid))))
                        except Exception:
                            target_audience = 1
                    audience_total += int(target_audience)
                    if not prepared_media:
                        await _send_text_with_fallback(
                            bot,
                            tid,
                            text_msg,
                            parse_mode=pm,
                            reply_markup=kb_target,
                        )
                    else:
                        # 1 media -> keep keyboard on media message.
                        if len(prepared_media) == 1:
                            m = prepared_media[0]
                            await _send_single_media(
                                bot,
                                tid,
                                m,
                                caption=cap or None,
                                parse_mode=pm if cap else None,
                                reply_markup=kb_target,
                            )
                        else:
                            await _send_media_album_or_fallback(
                                bot,
                                tid,
                                prepared_media,
                                caption=cap or None,
                                parse_mode=pm if cap else None,
                                reply_markup=kb_target,
                            )
                    ok += 1
                    audience_ok += int(target_audience)
                    await _insert_delivery(True, None, int(tid))
                except Exception as e:
                    fail += 1
                    if not first_fail:
                        first_fail = str(e)
                    if fail <= 3:
                        log.debug("broadcast skip user %s: %s", tid, e)
                    await _insert_delivery(False, str(e), int(tid))
                processed += 1
                if processed % commit_every == 0:
                    row_prog = await session.get(AdminBroadcast, int(broadcast_id))
                    if row_prog:
                        row_prog.recipient_ok = ok
                        row_prog.recipient_fail = fail
                        session.add(row_prog)
                    await session.commit()
                if _SEND_DELAY_SEC > 0:
                    await asyncio.sleep(_SEND_DELAY_SEC)

            row2 = await session.get(AdminBroadcast, int(broadcast_id))
            if row2:
                row2.recipient_ok = ok
                row2.recipient_fail = fail
                if keep_draft_after:
                    row2.status = "draft"
                    row2.sent_at = datetime_now()
                    row2.error_message = (first_fail or "")[:2000] if fail else None
                else:
                    row2.status = "sent"
                    row2.sent_at = datetime_now()
                    row2.error_message = (first_fail or "")[:2000] if fail else None
                session.add(
                    AdminBroadcastRun(
                        broadcast_id=int(row2.id),
                        target_kind=target_mode,
                        recipient_total=int(len(recipients)),
                        recipient_ok=int(ok),
                        recipient_fail=int(fail),
                        audience_total=int(audience_total),
                        audience_ok=int(audience_ok),
                        sent_at=datetime_now(),
                        run_source=str(run_source or "manual")[:16],
                    )
                )
                await session.commit()
                log.warning(
                    "broadcast completed: id=%s target=%s ok=%s fail=%s keep_draft=%s",
                    int(broadcast_id),
                    target_mode,
                    ok,
                    fail,
                    keep_draft_after,
                )
    except Exception as e:
        log.exception("run_broadcast_job failed")
        try:
            session = await get_session()
            async with session:
                row = await session.get(AdminBroadcast, int(broadcast_id))
                if row:
                    row.status = "draft" if keep_draft_after else "failed"
                    row.error_message = str(e)[:2000]
                    await session.commit()
        except Exception:
            pass
    finally:
        await bot.session.close()


def datetime_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def safe_media_kind(v: str) -> str | None:
    s = (v or "").strip().lower()
    if s in ("photo", "video", "document", "audio"):
        return s
    return None


def guess_media_kind_from_name(name: str, content_type: str | None = None) -> str:
    """Определяет тип медиа для Telegram: фото как sendPhoto, GIF как animation, не документ."""
    n = (name or "").lower()
    if re.search(r"\.gif$", n):
        return "document"
    if re.search(r"\.(jpg|jpeg|png|webp|bmp|heic|heif|jfif|avif)$", n):
        return "photo"
    if re.search(r"\.(mp4|mov|webm|mkv|m4v)$", n):
        return "video"
    if re.search(r"\.(mp3|wav|m4a|aac|ogg|flac)$", n):
        return "audio"
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct == "image/gif":
        return "document"
    if ct.startswith("image/"):
        return "photo"
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    return "document"


def new_local_filename(original: str) -> str:
    ext = Path(original or "").suffix.lower()
    if ext not in (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".mp4",
        ".mov",
        ".webm",
        ".mkv",
        ".m4v",
        ".pdf",
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".ogg",
        ".flac",
        ".heic",
        ".heif",
        ".bmp",
        ".jfif",
        ".avif",
    ):
        ext = ".bin"
    return f"{uuid.uuid4().hex}{ext}"
