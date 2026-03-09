# app/services/public_alerts.py
"""Публичные сообщения Guardian раз в N удалений (ТЗ ПРАВКИ 2)."""

from __future__ import annotations

import random
from datetime import datetime, timezone

# Фразы по категориям (стиль AntiSpam Guardian)
SPAM_MESSAGES = [
    "😈 Guardian зачистил спам. Чат дышит свободнее.",
    "🧹 Спам снесён. Помойка закрыта.",
    "🚫 Ещё пачка мусора уничтожена.",
]
LINK_MESSAGES = [
    "🔗 Левые ссылки срезаны. Проход закрыт.",
    "⚔ Guardian распилил очередную партию ссылок.",
    "🚫 Ссылочный мусор ликвидирован.",
]
BAD_WORDS_MESSAGES = [
    "🤬 Матершинник был снесён. Следи за языком.",
    "🪓 Грязный язык зачищен.",
    "😈 Guardian не любит словесную помойку.",
]
MUTE_MESSAGES = [
    "🔇 Нарушитель притих. В чате снова порядок.",
    "⛓ Один шумный пассажир отправлен остывать.",
]
BAN_MESSAGES = [
    "☠ Спамер выброшен за борт.",
    "🚪 Ещё один мусорный гость вылетел из чата.",
]
GENERIC_MESSAGES = [
    "😈 Guardian продолжает зачистку.",
    "🛡 Порядок восстановлен.",
    "🚫 Ещё одна партия мусора уничтожена.",
]

# Маппинг reason -> категория
REASON_TO_CATEGORY = {
    "stopword": "spam",
    "stopword_newbie": "spam",
    "link": "link",
    "link_newbie": "link",
    "mention": "generic",
    "mention_newbie": "generic",
    "spam": "spam",
    "edited_clean": "generic",
}

# Счётчик удалений по чату (in-memory, сбрасывается при рестарте)
_DELETE_COUNTER: dict[int, int] = {}


def _get_phrase(reason: str, action: str = "delete") -> str:
    if action == "mute":
        return random.choice(MUTE_MESSAGES)
    if action == "ban":
        return random.choice(BAN_MESSAGES)
    cat = REASON_TO_CATEGORY.get(reason, "generic")
    if cat == "spam":
        return random.choice(SPAM_MESSAGES)
    if cat == "link":
        return random.choice(LINK_MESSAGES)
    if cat == "bad_words":
        return random.choice(BAD_WORDS_MESSAGES)
    return random.choice(GENERIC_MESSAGES)


async def maybe_send_public_alert(bot, chat_id: int, rule, reason: str, action: str, session) -> None:
    """
    После успешного удаления: увеличить счётчик; при достижении N и интервала — отправить фразу в чат.
    """
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

    phrase = _get_phrase(reason, action)
    try:
        await bot.send_message(chat_id, phrase)
    except Exception:
        return

    _DELETE_COUNTER[chat_id] = 0
    rule.public_alerts_last_sent_at = now
    await session.commit()
