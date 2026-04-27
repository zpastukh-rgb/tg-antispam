# app/services/public_alerts.py
"""Публичные сообщения Guard раз в N срабатываний модерации (ТЗ ПРАВКИ 2)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from aiogram.types import Message

from app.texts.guardian_billing import SPAM_DELETED_WITH_PREMIUM_HINT

# --- Стиль «Guard» (фирменный: жёстко, саркастично; плюс отдельные фразы ниже) ---
SPAM_GUARD = [
    "😈 Guard зачистил спам. Чат дышит свободнее.",
    "🧹 Спам снесён. Помойка закрыта.",
    "🚫 Ещё пачка мусора уничтожена.",
    SPAM_DELETED_WITH_PREMIUM_HINT,
    "😈 Очередной «гений маркетинга» отправился в корзину к предыдущим.",
    "🗑 Спам? Guard уже кормит рыбок. Тебе не досталось.",
    "⚰ Мусорное сообщение лежит там, где ему и положено — вне чата.",
    "🧨 Ещё одна попытка засорить эфир растворилась с саркастичной улыбкой Guard.",
    "🔥 Шум отключён. Тишина — золото, а ты был бронзой.",
]
LINK_GUARD = [
    "🔗 Левые ссылки срезаны. Проход закрыт.",
    "⚔ Guard распилил очередную партию ссылок.",
    "🚫 Ссылочный мусор ликвидирован.",
    "🔗 Ссылку? Сюда. С контентом? Нет. Иди лечить кликбейт.",
    "🪚 Реклама под видом «полезной» ссылки — Guard срежет без анестезии.",
    "🚷 Этот URL не пропустят даже с подкупом. Дорога закрыта.",
    "💀 Левый домен ушёл в никуда. Скажи спасибо, что не тебя.",
]
BAD_GUARD = [
    "🤬 Матершинник был снесён. Следи за языком.",
    "🪓 Грязный язык зачищен.",
    "😈 Guard не любит словесную помойку.",
    "🤭 Словечки выбирал с душой? Guard вернул эстетику: молчание.",
    "🥶 Мат — не аргумент. Это стало твоим уроком на сегодня.",
    "👋 Грязный словарный запас отправлен в отпуск без содержания.",
    "🙃 Вульгарность выключена админом по умолчанию — то есть нами.",
]
MUTE_GUARD = [
    "🔇 Нарушитель притих. В чате снова порядок.",
    "⛓ Один шумный пассажир отправлен остывать.",
    "🔇 Пора поговорить с тишиной один на один. Она умнее.",
    "⏸ Режим «подумаешь» включён. Выйдешь, когда выйдешь.",
    "🤐 Теперь ты аудитория. Сиди красиво.",
]
BAN_GUARD = [
    "☠ Спамер выброшен за борт.",
    "🚪 Ещё один мусорный гость вылетел из чата.",
    "🚁 Вылет конечной: не сюда, не к нам, вообще никуда обратно.",
    "📦 Упаковали и выставили за дверь. Без возврата и обмена.",
]
GEN_GUARD = [
    "😈 Guard продолжает зачистку.",
    "🛡 Порядок восстановлен.",
    "🚫 Ещё одна партия мусора уничтожена.",
    "😏 Правила не спорят с нарушителями — они их пылесосят.",
    "🛡 Guard снова взял в руки веник. Кто следующий в швабру?",
]

# --- Стиль «средне» ---
SPAM_MED = [
    "Спам удалён. Спасибо за порядок в чате.",
    "Лишнее сообщение убрано модерацией.",
    "Сообщение не прошло фильтр и было удалено.",
]
LINK_MED = [
    "Сообщение со ссылкой удалено по правилам чата.",
    "Ссылка не разрешена — сообщение снято.",
]
BAD_MED = [
    "Сообщение с ненормативной лексикой удалено.",
    "Нарушение правил по языку — пост убран.",
]
MUTE_MED = [
    "Участник ограничен по правилам чата.",
    "Применено временное ограничение.",
]
BAN_MED = [
    "Участник исключён из чата по правилам.",
    "Доступ участника к чату прекращён.",
]
GEN_MED = [
    "Сообщение обработано модерацией.",
    "Правила чата применены.",
]

# --- Стиль «мягко» ---
SPAM_SOFT = [
    "Мы убрали сообщение, которое не подошло по правилам. Если вопросы — напишите админам.",
    "Одно сообщение удалено, чтобы чат оставался комфортным.",
]
LINK_SOFT = [
    "Сообщение со ссылкой снято — так настроена защита чата.",
]
BAD_SOFT = [
    "Сообщение снято: в чате действует фильтр по выражениям.",
]
MUTE_SOFT = [
    "Участнику временно ограничили отправку сообщений.",
]
BAN_SOFT = [
    "Участник покинул чат по решению защиты.",
]
GEN_SOFT = [
    "Защита чата обработала нарушение.",
    "Сообщение не прошло проверку и было убрано.",
]

REASON_TO_CATEGORY = {
    "stopword": "spam",
    "stopword_newbie": "spam",
    "profanity": "bad_words",
    "profanity_newbie": "bad_words",
    "link": "link",
    "link_newbie": "link",
    "link_blacklist": "link",
    "link_blacklist_newbie": "link",
    "global_bad_url": "link",
    "global_bad_url_newbie": "link",
    "mention": "generic",
    "mention_newbie": "generic",
    "media": "generic",
    "media_newbie": "generic",
    "buttons": "generic",
    "buttons_newbie": "generic",
    "spam": "spam",
    "edited_clean": "generic",
}

_DELETE_COUNTER: dict[int, int] = {}
_LAST_PHRASE_IDX: dict[tuple[int, str, str, str], int] = {}


def _choice_from_pool(pool: list[str], *, chat_id: int = 0, key: tuple[int, str, str, str] | None = None) -> str:
    """
    Случайная фраза: secrets + смещение от id чата, чтобы у разных групп не «билась» одна и та же
    последовательность при одинаковых таймингах, при этом выбор остаётся непредсказуемым.
    """
    n = len(pool)
    if n == 0:
        return ""
    if n == 1:
        return pool[0]
    base = (secrets.randbelow(n) + (abs(int(chat_id or 0)) % n)) % n
    i = base
    if key is not None:
        prev = _LAST_PHRASE_IDX.get(key)
        if prev is not None and prev == i:
            # Избегаем одинаковых подряд в одном чате/категории/стиле.
            shift = 1 + secrets.randbelow(max(1, n - 1))
            i = (i + shift) % n
        _LAST_PHRASE_IDX[key] = i
    return pool[i]


def _style(rule) -> str:
    s = (getattr(rule, "public_alerts_style", None) or "guard").strip().lower()
    return s if s in ("soft", "medium", "guard") else "guard"


def _pick(
    rule,
    soft_l: list[str],
    med_l: list[str],
    guard_l: list[str],
    *,
    chat_id: int = 0,
    category: str = "generic",
    action: str = "delete",
) -> str:
    st = _style(rule)
    pool = soft_l if st == "soft" else med_l if st == "medium" else guard_l
    key = (int(chat_id or 0), st, category, action)
    return _choice_from_pool(pool, chat_id=chat_id, key=key)


def _get_phrase(rule, reason: str, action: str = "delete", *, chat_id: int = 0) -> str:
    if action == "mute":
        return _pick(rule, MUTE_SOFT, MUTE_MED, MUTE_GUARD, chat_id=chat_id, category="mute", action="mute")
    if action == "ban":
        return _pick(rule, BAN_SOFT, BAN_MED, BAN_GUARD, chat_id=chat_id, category="ban", action="ban")
    cat = REASON_TO_CATEGORY.get(reason, "generic")
    if cat == "spam":
        return _pick(rule, SPAM_SOFT, SPAM_MED, SPAM_GUARD, chat_id=chat_id, category="spam", action=action)
    if cat == "link":
        return _pick(rule, LINK_SOFT, LINK_MED, LINK_GUARD, chat_id=chat_id, category="link", action=action)
    if cat == "bad_words":
        return _pick(rule, BAD_SOFT, BAD_MED, BAD_GUARD, chat_id=chat_id, category="bad_words", action=action)
    return _pick(rule, GEN_SOFT, GEN_MED, GEN_GUARD, chat_id=chat_id, category="generic", action=action)


async def maybe_send_public_alert(
    bot,
    chat_id: int,
    rule,
    reason: str,
    action: str,
    session,
    *,
    source_message: Message | None = None,
) -> None:
    """
    После успешного удаления/наказания: счётчик по чату; при N срабатываниях и паузе — фраза в чат.
    Также нужен guardian_messages_enabled (общий флаг «сообщения Guard»).
    """
    if not getattr(rule, "guardian_messages_enabled", True):
        return
    if not getattr(rule, "public_alerts_enabled", False):
        return
    every_n = max(1, getattr(rule, "public_alerts_every_n", 5))
    min_interval_sec = max(0, getattr(rule, "public_alerts_min_interval_sec", 300))

    count = _DELETE_COUNTER.get(chat_id, 0) + 1
    _DELETE_COUNTER[chat_id] = count

    if count < every_n:
        return

    now = datetime.now(timezone.utc)
    last_sent = getattr(rule, "public_alerts_last_sent_at", None)
    if last_sent:
        delta = (now - last_sent).total_seconds()
        if delta < min_interval_sec:
            return

    phrase = _get_phrase(rule, reason, action, chat_id=chat_id)
    send_kwargs: dict = {}
    if source_message is not None:
        try:
            from aiogram.types import ReplyParameters

            r = getattr(source_message, "reply_to_message", None)
            if r and getattr(r, "sender_chat", None):
                st = str(getattr(r.sender_chat, "type", "") or "").lower()
                if st == "channel":
                    send_kwargs["reply_parameters"] = ReplyParameters(message_id=int(r.message_id))
            if "reply_parameters" not in send_kwargs:
                mtid = getattr(source_message, "message_thread_id", None)
                ch = getattr(source_message, "chat", None)
                if mtid is not None and getattr(ch, "is_forum", False):
                    send_kwargs["message_thread_id"] = int(mtid)
        except Exception:
            send_kwargs.clear()
    try:
        await bot.send_message(chat_id, phrase, **send_kwargs)
    except Exception:
        return

    _DELETE_COUNTER[chat_id] = 0
    rule.public_alerts_last_sent_at = now
    await session.commit()
