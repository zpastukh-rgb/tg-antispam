"""Заявки на вступление: автоприём, опрос в ЛС, ручное одобрение."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import BaseFilter
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import delete, select

from app.db.models import Chat, JoinRequestSurveySession, Rule, User
from app.db.session import get_session
from app.services.cas_check import is_user_cas_banned
from app.services.chat_owner_locale import owner_locale_for_chat
from app.services.chat_owner_premium import chat_owner_has_miniapp_premium
from app.services.global_antispam import is_in_global_antispam
from app.services.join_requests_survey import (
    answer_matches,
    done_text,
    dump_answers_json,
    load_answers_json,
    normalize_mode,
    normalize_report_mode,
    parse_questions_text,
    welcome_text,
)

logger = logging.getLogger(__name__)
router = Router(name="join_requests")

CB_PREFIX = "jr:"
_SURVEY_TTL_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _spam_block(session, user_id: int, rule: Rule, owner_premium: bool) -> str | None:
    if not owner_premium:
        return None
    if bool(getattr(rule, "use_global_antispam_db", False)):
        if await is_in_global_antispam(session, int(user_id)):
            return "global_antispam"
    if bool(getattr(rule, "join_filter_cas", False)):
        cas = await is_user_cas_banned(int(user_id))
        if cas is True:
            return "cas"
    return None


async def _get_session_row(session, chat_id: int, user_id: int) -> JoinRequestSurveySession | None:
    q = await session.execute(
        select(JoinRequestSurveySession).where(
            JoinRequestSurveySession.chat_id == int(chat_id),
            JoinRequestSurveySession.user_id == int(user_id),
        )
    )
    return q.scalar_one_or_none()


async def _upsert_survey_session(
    session,
    chat_id: int,
    user_id: int,
    *,
    question_index: int = 0,
    answers: list[str] | None = None,
) -> JoinRequestSurveySession:
    row = await _get_session_row(session, chat_id, user_id)
    exp = _now() + timedelta(hours=_SURVEY_TTL_HOURS)
    ans_json = dump_answers_json(answers or [])
    if row is None:
        row = JoinRequestSurveySession(
            chat_id=int(chat_id),
            user_id=int(user_id),
            question_index=int(question_index),
            answers_json=ans_json,
            expires_at=exp,
        )
        session.add(row)
    else:
        row.question_index = int(question_index)
        row.answers_json = ans_json
        row.expires_at = exp
    await session.commit()
    return row


async def _clear_survey_session(session, chat_id: int, user_id: int) -> None:
    await session.execute(
        delete(JoinRequestSurveySession).where(
            JoinRequestSurveySession.chat_id == int(chat_id),
            JoinRequestSurveySession.user_id == int(user_id),
        )
    )
    await session.commit()


async def _owner_telegram_id(session, chat_row: Chat) -> int | None:
    tid = int(getattr(chat_row, "owner_user_id", 0) or 0)
    return tid if tid > 0 else None


async def _send_admin_report(
    bot: Bot,
    session,
    chat_row: Chat,
    rule: Rule,
    user,
    answers: list[str],
    questions: list[dict],
) -> None:
    report_mode = normalize_report_mode(getattr(rule, "join_requests_report_mode", "full"))
    if report_mode == "off":
        return
    owner_tid = await _owner_telegram_id(session, chat_row)
    if not owner_tid:
        return
    uname = f"@{user.username}" if getattr(user, "username", None) else "—"
    name = html.escape(str(getattr(user, "full_name", "") or getattr(user, "first_name", "") or "User"))
    chat_title = html.escape(str(getattr(chat_row, "title", "") or chat_row.id))
    lines = [
        f"❗ <b>Новая заявка</b> · {chat_title}",
        f"👤 {name} · id <code>{user.id}</code> · {html.escape(uname)}",
    ]
    if report_mode == "full" and questions:
        lines.append("\n<b>Ответы на опрос:</b>")
        for i, q in enumerate(questions):
            ans = html.escape(answers[i] if i < len(answers) else "—")
            qtext = html.escape(str(q.get("text") or ""))
            lines.append(f"{i + 1}. {qtext}\n↳ <i>{ans}</i>")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"{CB_PREFIX}ok:{chat_row.id}:{user.id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"{CB_PREFIX}no:{chat_row.id}:{user.id}"),
            ],
            [
                InlineKeyboardButton(text="🔫 Забанить", callback_data=f"{CB_PREFIX}ban:{chat_row.id}:{user.id}"),
            ],
        ]
    )
    try:
        await bot.send_message(owner_tid, "\n".join(lines), reply_markup=kb)
    except Exception as e:
        logger.debug("join_request report owner=%s: %s", owner_tid, e)


async def _approve(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        await bot.approve_chat_join_request(int(chat_id), int(user_id))
        return True
    except TelegramForbiddenError:
        logger.warning("join_request approve forbidden chat=%s user=%s", chat_id, user_id)
    except TelegramBadRequest as e:
        logger.warning("join_request approve bad chat=%s user=%s: %s", chat_id, user_id, e)
    return False


async def _decline(bot: Bot, chat_id: int, user_id: int) -> None:
    try:
        await bot.decline_chat_join_request(int(chat_id), int(user_id))
    except Exception as e:
        logger.debug("join_request decline chat=%s user=%s: %s", chat_id, user_id, e)


async def _ban(bot: Bot, chat_id: int, user_id: int) -> None:
    try:
        await bot.ban_chat_member(int(chat_id), int(user_id))
    except Exception as e:
        logger.debug("join_request ban chat=%s user=%s: %s", chat_id, user_id, e)
    await _decline(bot, chat_id, user_id)


def _question_keyboard(q: dict) -> InlineKeyboardMarkup | None:
    rows = q.get("buttons") or []
    if not rows:
        return None
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        btns: list[InlineKeyboardButton] = []
        for btn in row:
            text = str(btn.get("text") or "").strip()
            url = str(btn.get("url") or "").strip()
            if text and url:
                btns.append(InlineKeyboardButton(text=text[:64], url=url))
        if btns:
            keyboard.append(btns)
    if not keyboard:
        return None
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def _send_question(bot: Bot, user_id: int, q: dict, idx: int, total: int) -> bool:
    text = f"❓ <b>Вопрос {idx + 1} из {total}</b>\n\n{html.escape(str(q.get('text') or ''))}"
    kb = _question_keyboard(q)
    try:
        await bot.send_message(int(user_id), text, reply_markup=kb)
        return True
    except TelegramForbiddenError:
        return False
    except Exception as e:
        logger.debug("join_request question dm user=%s: %s", user_id, e)
        return False


async def _start_survey(
    bot: Bot,
    session,
    chat_row: Chat,
    rule: Rule,
    user,
    *,
    locale: str,
) -> None:
    questions = parse_questions_text(getattr(rule, "join_requests_questions_text", None))
    if not questions:
        await _approve(bot, int(chat_row.id), int(user.id))
        return
    chat_title = str(getattr(chat_row, "title", "") or chat_row.id)
    name = str(getattr(user, "first_name", "") or "друг")
    intro = welcome_text(rule, name=name, chat_title=chat_title, locale=locale)
    try:
        await bot.send_message(int(user.id), intro)
    except TelegramForbiddenError:
        logger.info("join_request survey blocked bot user=%s chat=%s", user.id, chat_row.id)
        return
    except Exception as e:
        logger.debug("join_request welcome dm: %s", e)
        return
    await _upsert_survey_session(session, int(chat_row.id), int(user.id), question_index=0, answers=[])
    await _send_question(bot, int(user.id), questions[0], 0, len(questions))


@router.chat_join_request()
async def on_chat_join_request(event: ChatJoinRequest, bot: Bot) -> None:
    chat_id = int(event.chat.id)
    user = event.from_user
    if not user:
        return
    user_id = int(user.id)

    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
        if not chat_row or chat_row.is_log_chat or not bool(getattr(chat_row, "is_active", True)):
            return
        rule = await session.get(Rule, chat_id)
        if not rule:
            return

        mode = normalize_mode(getattr(rule, "join_requests_mode", None))
        if mode == "off" and bool(getattr(rule, "auto_approve_join_requests", False)):
            mode = "auto"
        if mode == "off":
            return

        owner_premium = await chat_owner_has_miniapp_premium(session, chat_id)
        locale = await owner_locale_for_chat(session, chat_id)

        if mode == "survey_manual" and not owner_premium:
            mode = "survey_auto"
        if mode in ("survey_auto", "survey_manual"):
            qs = parse_questions_text(getattr(rule, "join_requests_questions_text", None))
            max_q = 5 if owner_premium else 1
            if not qs:
                mode = "auto"
            elif len(qs) > max_q:
                # enforce limit by truncating in parser already
                pass

        spam = await _spam_block(session, user_id, rule, owner_premium)
        if spam:
            await _decline(bot, chat_id, user_id)
            return

        if mode == "auto":
            await _approve(bot, chat_id, user_id)
            return

        if mode in ("survey_auto", "survey_manual"):
            await _start_survey(bot, session, chat_row, rule, user, locale=locale)


async def _active_join_survey_row(user_id: int) -> JoinRequestSurveySession | None:
    """Активная сессия опроса по заявке (не истекла)."""
    async with await get_session() as session:
        q_sess = await session.execute(
            select(JoinRequestSurveySession)
            .where(JoinRequestSurveySession.user_id == int(user_id))
            .order_by(JoinRequestSurveySession.id.desc())
            .limit(1)
        )
        row = q_sess.scalar_one_or_none()
        if not row:
            return None
        exp = row.expires_at
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and _now() > exp:
            await _clear_survey_session(session, int(row.chat_id), int(user_id))
            return None
        return row


class JoinSurveyActiveFilter(BaseFilter):
    """ЛС: текст — только если пользователь проходит опрос по заявке на вступление."""

    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        if not user or user.is_bot:
            return False
        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            return False
        return bool(await _active_join_survey_row(int(user.id)))


@router.message(JoinSurveyActiveFilter(), F.chat.type == ChatType.PRIVATE, F.text)
async def on_survey_dm_answer(message: Message, bot: Bot) -> None:
    user = message.from_user
    if not user or user.is_bot:
        return
    user_id = int(user.id)
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    row = await _active_join_survey_row(user_id)
    if not row:
        return

    async with await get_session() as session:
        chat_row = await session.get(Chat, int(row.chat_id))
        rule = await session.get(Rule, int(row.chat_id))
        if not chat_row or not rule:
            await _clear_survey_session(session, int(row.chat_id), user_id)
            return

        mode = normalize_mode(getattr(rule, "join_requests_mode", None))
        if mode not in ("survey_auto", "survey_manual"):
            await _clear_survey_session(session, int(row.chat_id), user_id)
            return

        owner_premium = await chat_owner_has_miniapp_premium(session, int(row.chat_id))
        locale = await owner_locale_for_chat(session, int(row.chat_id))
        questions = parse_questions_text(getattr(rule, "join_requests_questions_text", None))
        max_q = 5 if owner_premium else 1
        questions = questions[:max_q]
        if not questions:
            await _clear_survey_session(session, int(row.chat_id), user_id)
            return

        idx = int(row.question_index or 0)
        if idx >= len(questions):
            await _clear_survey_session(session, int(row.chat_id), user_id)
            return

        if not answer_matches(text, questions[idx].get("answers") or []):
            try:
                await message.answer("❌ Неверный ответ. Попробуйте ещё раз.")
            except Exception:
                pass
            await _send_question(bot, user_id, questions[idx], idx, len(questions))
            return

        answers = load_answers_json(row.answers_json)
        answers.append(text.strip())
        next_idx = idx + 1
        if next_idx < len(questions):
            row.question_index = next_idx
            row.answers_json = dump_answers_json(answers)
            row.expires_at = _now() + timedelta(hours=_SURVEY_TTL_HOURS)
            await session.commit()
            await _send_question(bot, user_id, questions[next_idx], next_idx, len(questions))
            return

        await _clear_survey_session(session, int(row.chat_id), user_id)
        try:
            await message.answer(done_text(rule, locale=locale))
        except Exception:
            pass

        if mode == "survey_auto":
            spam = await _spam_block(session, user_id, rule, owner_premium)
            if spam:
                await _decline(bot, int(row.chat_id), user_id)
            else:
                await _approve(bot, int(row.chat_id), user_id)
            return

        await _send_admin_report(bot, session, chat_row, rule, user, answers, questions)


@router.callback_query(F.data.startswith(CB_PREFIX))
async def on_join_request_admin_cb(query: CallbackQuery, bot: Bot) -> None:
    data = str(query.data or "")
    parts = data.split(":")
    if len(parts) != 4:
        await query.answer("?")
        return
    action, chat_id_s, user_id_s = parts[1], parts[2], parts[3]
    try:
        chat_id = int(chat_id_s)
        target_uid = int(user_id_s)
    except ValueError:
        await query.answer("?")
        return

    actor = query.from_user
    if not actor:
        await query.answer()
        return

    async with await get_session() as session:
        chat_row = await session.get(Chat, chat_id)
        if not chat_row:
            await query.answer("Чат не найден")
            return
        owner_tid = await _owner_telegram_id(session, chat_row)
        if actor.id != owner_tid:
            res = await session.execute(select(User).where(User.telegram_id == actor.id).limit(1))
            u = res.scalar_one_or_none()
            if not u or not bool(getattr(u, "is_admin", False)):
                await query.answer("Нет прав", show_alert=True)
                return

    if action == "ok":
        ok = await _approve(bot, chat_id, target_uid)
        await query.answer("Одобрено" if ok else "Не удалось одобрить")
    elif action == "no":
        await _decline(bot, chat_id, target_uid)
        await query.answer("Отклонено")
    elif action == "ban":
        await _ban(bot, chat_id, target_uid)
        await query.answer("Забанен")
    else:
        await query.answer("?")
        return

    try:
        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
