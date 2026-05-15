# app/services/spam_spike_notify.py
"""DM-уведомления о всплеске спам-активности (только срабатывания спам-фильтров), с кнопкой Mini App."""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chat,
    ChatManager,
    ChatManagerInvite,
    ChatSpikeAlert,
    ModerationLog,
    NewMember,
    Rule,
    SpamSpikeGroupPingSent,
    SpamSpikeNotifySent,
    User,
)
from app.i18n import t
from app.services.chat_owner_locale import owner_locale_for_chat, user_locale
from app.services.chat_owner_premium import chat_owner_has_miniapp_premium
from app.services.telegram_notify import send_user_dm

logger = logging.getLogger(__name__)

_SPAM_REASON_BASES = (
    "stopword",
    "profanity",
    "jobs",
    "casino",
    "ads",
    "insult",
    "racism",
    "nazi",
    "vulgar",
    "link",
    "link_blacklist",
    "global_bad_url",
    "mention",
    "media",
    "buttons",
)
SPAM_MODERATION_REASONS: frozenset[str] = frozenset(
    [b for pair in ((x, f"{x}_newbie") for x in _SPAM_REASON_BASES) for b in pair]
)


def _utc_bucket_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y%m%d%H")


def _settings_hint_lines(rule: Rule | None, locale: str) -> list[str]:
    loc = locale
    if not rule:
        return [t(loc, "guard.spam_spike.hint_default")]
    lines: list[str] = []
    if not bool(getattr(rule, "newbie_enabled", False)):
        lines.append(t(loc, "guard.spam_spike.hint_newbie"))
    if int(getattr(rule, "silence_minutes", 0) or 0) <= 0:
        lines.append(t(loc, "guard.spam_spike.hint_silence"))
    if not bool(getattr(rule, "antinakrutka_enabled", False)):
        lines.append(t(loc, "guard.spam_spike.hint_antinakrutka"))
    if not bool(getattr(rule, "use_global_antispam_db", False)):
        lines.append(t(loc, "guard.spam_spike.hint_antispam_db"))
    if not bool(getattr(rule, "first_message_captcha_enabled", False)):
        lines.append(t(loc, "guard.spam_spike.hint_captcha"))
    if not lines:
        lines.append(t(loc, "guard.spam_spike.hint_fallback"))
    return lines[:5]


async def _startapp_link_for_bot(bot, section: str) -> str:
    me = await bot.get_me()
    uname = str(getattr(me, "username", "") or "").strip().lstrip("@")
    short_name = (os.getenv("MINI_APP_SHORT_NAME") or os.getenv("WEBAPP_SHORT_NAME") or "").strip().strip("/")
    safe_section = (section or "panel").strip() or "panel"
    if short_name:
        return f"https://t.me/{uname}/{short_name}?startapp={safe_section}"
    return f"https://t.me/{uname}?startapp={safe_section}"


async def _human_telegram_admin_count(bot, chat_id: int) -> int:
    """Сколько живых админов/создателей (не бот) в чате."""
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except Exception:
        return 0
    me = await bot.get_me()
    bid = int(getattr(me, "id", 0) or 0)
    n = 0
    for m in admins:
        u = getattr(m, "user", None)
        if not u or bool(getattr(u, "is_bot", False)):
            continue
        if int(getattr(u, "id", 0) or 0) == bid:
            continue
        st = str(getattr(m, "status", "") or "").lower()
        if st in ("creator", "administrator"):
            n += 1
    return n


async def _already_sent_dm(session: AsyncSession, recipient_tg: int, chat_id: int, bucket: str) -> bool:
    q = await session.execute(
        select(SpamSpikeNotifySent.id).where(
            SpamSpikeNotifySent.recipient_telegram_id == int(recipient_tg),
            SpamSpikeNotifySent.chat_id == int(chat_id),
            SpamSpikeNotifySent.bucket_key == bucket,
        ).limit(1)
    )
    return q.scalar_one_or_none() is not None


async def _already_group_ping(session: AsyncSession, chat_id: int, bucket: str) -> bool:
    q = await session.execute(
        select(SpamSpikeGroupPingSent.id).where(
            SpamSpikeGroupPingSent.chat_id == int(chat_id),
            SpamSpikeGroupPingSent.bucket_key == bucket,
        ).limit(1)
    )
    return q.scalar_one_or_none() is not None


async def trigger_spam_spike_for_chat(
    bot,
    session: AsyncSession,
    now: datetime,
    chat_id: int,
    *,
    spam_cnt: int,
    joins_cnt: int = 0,
    window_min: int = 35,
) -> None:
    """Принудительно зафиксировать spike по одному чату и разослать уведомления owner/manager."""
    cid = int(chat_id or 0)
    # У Telegram групп/супергрупп chat_id отрицательный (например -100...).
    # Отбрасывать нужно только нулевой/пустой id.
    if cid == 0:
        return
    bucket = _utc_bucket_key(now)
    await session.execute(delete(ChatSpikeAlert).where(ChatSpikeAlert.expires_at < now))
    await session.commit()

    chat_row = await session.get(Chat, cid)
    if not chat_row or not bool(getattr(chat_row, "is_active", True)) or bool(getattr(chat_row, "is_log_chat", False)):
        return

    expires_at = now + timedelta(hours=1)
    existing_alert = (
        await session.execute(
            select(ChatSpikeAlert).where(ChatSpikeAlert.chat_id == cid).limit(1)
        )
    ).scalar_one_or_none()
    if existing_alert:
        existing_alert.spam_count = int(spam_cnt)
        existing_alert.joins_count = int(joins_cnt)
        existing_alert.window_min = int(window_min)
        existing_alert.last_triggered_at = now
        existing_alert.expires_at = expires_at
    else:
        session.add(
            ChatSpikeAlert(
                chat_id=cid,
                spam_count=int(spam_cnt),
                joins_count=int(joins_cnt),
                window_min=int(window_min),
                last_triggered_at=now,
                expires_at=expires_at,
            )
        )
    await session.commit()

    rule = await session.get(Rule, cid)
    title = (chat_row.title or "").strip() or str(cid)
    title_h = html.escape(title)

    human_admins = 0
    if str(getattr(chat_row, "chat_kind", "group") or "group").lower() != "channel":
        human_admins = await _human_telegram_admin_count(bot, cid)

    admins_notified_in_chat = False
    if human_admins > 0:
        if await _already_group_ping(session, cid, bucket):
            admins_notified_in_chat = True
        else:
            owner_loc = await owner_locale_for_chat(session, cid)
            ping_text = t(owner_loc, "guard.spam_spike.group_ping")
            try:
                await bot.send_message(cid, ping_text, parse_mode="HTML", disable_web_page_preview=True)
                session.add(SpamSpikeGroupPingSent(chat_id=cid, bucket_key=bucket))
                await session.commit()
                admins_notified_in_chat = True
            except Exception as e:
                logger.debug("spam_spike group ping chat=%s: %s", cid, e)
                await session.rollback()
                admins_notified_in_chat = False

    owner_tid_raw = int(getattr(chat_row, "owner_user_id", 0) or 0)

    mgr_rows = (
        await session.execute(select(ChatManager.user_id).where(ChatManager.chat_id == cid))
    ).all()
    manager_ids_raw = {int(r[0]) for r in mgr_rows if r and int(r[0] or 0) > 0}
    # Фолбэк: если ChatManager отстал, добираем из connected инвайтов.
    inv_rows = (
        await session.execute(
            select(ChatManagerInvite.connected_user_id).where(
                ChatManagerInvite.chat_id == cid,
                ChatManagerInvite.status == "connected",
                ChatManagerInvite.connected_user_id.is_not(None),
            )
        )
    ).all()
    manager_ids_raw.update({int(r[0]) for r in inv_rows if r and int(r[0] or 0) > 0})
    inv_target_rows = (
        await session.execute(
            select(ChatManagerInvite.target_telegram_id).where(
                ChatManagerInvite.chat_id == cid,
                ChatManagerInvite.status == "connected",
                ChatManagerInvite.target_telegram_id.is_not(None),
            )
        )
    ).all()
    manager_ids_raw.update({int(r[0]) for r in inv_target_rows if r and int(r[0] or 0) > 0})
    manager_ids_raw = sorted(manager_ids_raw)

    # Нормализация: часть полей в БД исторически могла хранить users.id вместо telegram_id.
    raw_ids = {owner_tid_raw, *manager_ids_raw}
    raw_ids = {int(x) for x in raw_ids if int(x or 0) > 0}
    resolved_tid_by_raw: dict[int, int] = {}
    if raw_ids:
        # users.id имеет тип INTEGER (int32), users.telegram_id — BIGINT.
        # Нельзя класть большие telegram_id в users.id IN (...), иначе asyncpg DataError.
        int32_max = 2_147_483_647
        id_candidates = [x for x in raw_ids if x <= int32_max]
        tg_candidates = list(raw_ids)
        users = (
            await session.execute(
                select(User.id, User.telegram_id).where(
                    (User.id.in_(id_candidates) if id_candidates else false())
                    | (User.telegram_id.in_(tg_candidates))
                )
            )
        ).all()
        for uid, tg in users:
            uid_i = int(uid or 0)
            tg_i = int(tg or 0)
            if uid_i > 0 and tg_i > 0:
                resolved_tid_by_raw[uid_i] = tg_i
                resolved_tid_by_raw[tg_i] = tg_i

    def _as_tid(raw_id: int) -> int:
        rid = int(raw_id or 0)
        if rid <= 0:
            return 0
        mapped = int(resolved_tid_by_raw.get(rid, 0) or 0)
        if mapped > 0:
            return mapped
        # Фолбэк: большие идентификаторы обычно уже telegram_id.
        if rid >= 10_000_000:
            return rid
        return 0

    owner_tid = _as_tid(owner_tid_raw)
    # Fail-safe: владелец чата критичен для алерта.
    # Если нормализация не сработала (исторические данные), пробуем raw как telegram_id.
    if owner_tid <= 0 and owner_tid_raw > 0:
        owner_tid = int(owner_tid_raw)
    manager_ids = sorted({_as_tid(mid) for mid in manager_ids_raw if _as_tid(mid) > 0})
    notify_managers = bool(getattr(rule, "spam_spike_notify_managers", True))
    owner_premium_spike = await chat_owner_has_miniapp_premium(session, cid)
    if not owner_premium_spike:
        notify_managers = False
    utc_now = now.astimezone(timezone.utc)
    dm_bucket = bucket if owner_premium_spike else f"free_daily:{utc_now.strftime('%Y%m%d')}"

    protection_url = await _startapp_link_for_bot(bot, "protection")

    recipients: list[tuple[int, str]] = []
    if owner_tid > 0:
        recipients.append((owner_tid, "owner"))
    if notify_managers:
        for mid in manager_ids:
            if mid == owner_tid:
                continue
            recipients.append((mid, "manager"))

    for recipient_tid, role in recipients:
        if await _already_sent_dm(session, recipient_tid, cid, dm_bucket):
            continue

        loc = await user_locale(session, recipient_tid)
        hints = "\n".join(_settings_hint_lines(rule, loc))
        group_ping_line = t(loc, "guard.spam_spike.dm_group_ping_footer") if admins_notified_in_chat else ""
        who_line = (
            t(
                loc,
                "guard.spam_spike.dm_stats",
                chat_title=title_h,
                window_min=window_min,
                spam_cnt=int(spam_cnt),
                joins_cnt=int(joins_cnt),
                hints=hints,
            )
            + group_ping_line
        )
        text = t(loc, "guard.spam_spike.dm_title") + who_line
        open_url = protection_url
        btn_label = t(loc, "guard.spam_spike.btn_protection")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=btn_label, url=open_url)]]
        )
        try:
            await bot.send_message(
                int(recipient_tid),
                text,
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            session.add(
                SpamSpikeNotifySent(
                    recipient_telegram_id=int(recipient_tid),
                    chat_id=cid,
                    bucket_key=dm_bucket,
                )
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            try:
                fallback_ok = await send_user_dm(
                    int(recipient_tid),
                    text,
                    parse_mode="HTML",
                    reply_markup=kb.model_dump(exclude_none=True),
                )
            except Exception:
                fallback_ok = False
            if fallback_ok:
                try:
                    session.add(
                        SpamSpikeNotifySent(
                            recipient_telegram_id=int(recipient_tid),
                            chat_id=cid,
                            bucket_key=dm_bucket,
                        )
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                logger.info("spam_spike dm fallback ok to %s chat=%s", recipient_tid, cid)
            else:
                logger.warning("spam_spike dm to %s chat=%s failed (direct+fallback): %s", recipient_tid, cid, e)


async def run_spam_spike_owner_manager_alerts(bot, session: AsyncSession, now: datetime) -> None:
    # Порог/окно управляются в rules конкретного чата.
    min_joins = max(0, min(500, int(os.getenv("SPAM_SPIKE_MIN_JOINS", "3") or 3)))
    bucket = _utc_bucket_key(now)

    # Чистим истёкшие флаги, чтобы UI не показывал старые треугольники.
    await session.execute(delete(ChatSpikeAlert).where(ChatSpikeAlert.expires_at < now))
    await session.commit()

    active_chats = (
        await session.execute(
            select(Chat, Rule)
            .join(Rule, Chat.id == Rule.chat_id)
            .where(
                Chat.is_active == True,  # noqa: E712
                Chat.is_log_chat == False,  # noqa: E712
                Rule.spam_spike_enabled == True,  # noqa: E712
            )
        )
    ).all()
    if not active_chats:
        return

    for row in active_chats:
        chat_row, rule = row[0], row[1]
        chat_id = int(getattr(chat_row, "id", 0) or 0)
        if chat_id <= 0:
            continue
        window_min = max(5, min(180, int(getattr(rule, "spam_spike_window_minutes", 35) or 35)))
        min_deletes = max(2, min(50, int(getattr(rule, "spam_spike_min_deletes", 15) or 15)))
        since = now - timedelta(minutes=window_min)
        spam_cnt_q = await session.execute(
            select(func.count(ModerationLog.id)).where(
                ModerationLog.chat_id == int(chat_id),
                ModerationLog.created_at >= since,
                ModerationLog.reason.in_(list(SPAM_MODERATION_REASONS)),
                func.lower(ModerationLog.action).in_(("delete", "mute", "ban")),
            )
        )
        spam_cnt = int(spam_cnt_q.scalar() or 0)
        if spam_cnt < min_deletes:
            continue
        joins_q = await session.execute(
            select(func.count(NewMember.id)).where(
                NewMember.chat_id == int(chat_id),
                NewMember.joined_at >= since,
            )
        )
        joins_cnt = int(joins_q.scalar() or 0)
        if joins_cnt < min_joins and spam_cnt < max(min_deletes, 5):
            continue
        await trigger_spam_spike_for_chat(
            bot,
            session,
            now,
            int(chat_id),
            spam_cnt=spam_cnt,
            joins_cnt=joins_cnt,
            window_min=window_min,
        )
