"""Тексты публичных сообщений Guard в группах: публичные алерты и дежурная ротация.

Локаль берётся из языка владельца чата (User.language). Версии ru / en.
"""

from __future__ import annotations

from typing import Final

# --- Публичные алерты (стиль guard / medium / soft) ---

_PUBLIC_ALERT_POOLS_RU: Final[dict[str, list[str]]] = {
    "spam_guard": [
        "😈 Guard зачистил спам. Чат дышит свободнее.",
        "🧹 Спам снесён. Помойка закрыта.",
        "🚫 Ещё пачка мусора уничтожена.",
        (
            "⚔ Guard уничтожил спам.\n\n"
            "Сообщение удалено.\n\n"
            "Если спам усилится —\n"
            "Premium даст расширенные режимы защиты и настройки."
        ),
        "😈 Очередной «гений маркетинга» отправился в корзину к предыдущим.",
        "🗑 Спам? Guard уже кормит рыбок. Тебе не досталось.",
        "⚰ Мусорное сообщение лежит там, где ему и положено — вне чата.",
        "🧨 Ещё одна попытка засорить эфир растворилась с саркастичной улыбкой Guard.",
        "🔥 Шум отключён. Тишина — золото, а ты был бронзой.",
    ],
    "link_guard": [
        "🔗 Левые ссылки срезаны. Проход закрыт.",
        "⚔ Guard распилил очередную партию ссылок.",
        "🚫 Ссылочный мусор ликвидирован.",
        "🔗 Ссылку? Сюда. С контентом? Нет. Иди лечить кликбейт.",
        "🪚 Реклама под видом «полезной» ссылки — Guard срежет без анестезии.",
        "🚷 Этот URL не пропустят даже с подкупом. Дорога закрыта.",
        "💀 Левый домен ушёл в никуда. Скажи спасибо, что не тебя.",
    ],
    "bad_guard": [
        "🤬 Матершинник был снесён. Следи за языком.",
        "🪓 Грязный язык зачищен.",
        "😈 Guard не любит словесную помойку.",
        "🤭 Словечки выбирал с душой? Guard вернул эстетику: молчание.",
        "🥶 Мат — не аргумент. Это стало твоим уроком на сегодня.",
        "👋 Грязный словарный запас отправлен в отпуск без содержания.",
        "🙃 Вульгарность выключена админом по умолчанию — то есть нами.",
    ],
    "mute_guard": [
        "🔇 Нарушитель притих. В чате снова порядок.",
        "⛓ Один шумный пассажир отправлен остывать.",
        "🔇 Пора поговорить с тишиной один на один. Она умнее.",
        "⏸ Режим «подумаешь» включён. Выйдешь, когда выйдешь.",
        "🤐 Теперь ты аудитория. Сиди красиво.",
    ],
    "ban_guard": [
        "☠ Спамер выброшен за борт.",
        "🚪 Ещё один мусорный гость вылетел из чата.",
        "🚁 Вылет конечной: не сюда, не к нам, вообще никуда обратно.",
        "📦 Упаковали и выставили за дверь. Без возврата и обмена.",
    ],
    "gen_guard": [
        "😈 Guard продолжает зачистку.",
        "🛡 Порядок восстановлен.",
        "🚫 Ещё одна партия мусора уничтожена.",
        "😏 Правила не спорят с нарушителями — они их пылесосят.",
        "🛡 Guard снова взял в руки веник. Кто следующий в швабру?",
    ],
    "spam_med": [
        "Спам удалён. Спасибо за порядок в чате.",
        "Лишнее сообщение убрано модерацией.",
        "Сообщение не прошло фильтр и было удалено.",
    ],
    "link_med": [
        "Сообщение со ссылкой удалено по правилам чата.",
        "Ссылка не разрешена — сообщение снято.",
    ],
    "bad_med": [
        "Сообщение с ненормативной лексикой удалено.",
        "Нарушение правил по языку — пост убран.",
    ],
    "mute_med": [
        "Участник ограничен по правилам чата.",
        "Применено временное ограничение.",
    ],
    "ban_med": [
        "Участник исключён из чата по правилам.",
        "Доступ участника к чату прекращён.",
    ],
    "gen_med": [
        "Сообщение обработано модерацией.",
        "Правила чата применены.",
    ],
    "spam_soft": [
        "Мы убрали сообщение, которое не подошло по правилам. Если вопросы — напишите админам.",
        "Одно сообщение удалено, чтобы чат оставался комфортным.",
    ],
    "link_soft": [
        "Сообщение со ссылкой снято — так настроена защита чата.",
    ],
    "bad_soft": [
        "Сообщение снято: в чате действует фильтр по выражениям.",
    ],
    "mute_soft": [
        "Участнику временно ограничили отправку сообщений.",
    ],
    "ban_soft": [
        "Участник покинул чат по решению защиты.",
    ],
    "gen_soft": [
        "Защита чата обработала нарушение.",
        "Сообщение не прошло проверку и было убрано.",
    ],
}

_PUBLIC_ALERT_POOLS_EN: Final[dict[str, list[str]]] = {
    "spam_guard": [
        "😈 Guard cleared spam. The chat can breathe easier.",
        "🧹 Spam removed. Dumpster’s shut.",
        "🚫 Another batch of junk destroyed.",
        (
            "⚔ Guard nuked the spam.\n\n"
            "The message is gone.\n\n"
            "If it gets worse — Premium unlocks stronger modes and settings."
        ),
        "😈 Another “marketing genius” went to the recycle bin with the rest.",
        "🗑 Spam? Guard’s already feeding the fish. None left for you.",
        "⚰ Trash posts belong outside the chat — and that’s where this one is.",
        "🧨 Another attempt to clog the feed dissolved with Guard’s smirk.",
        "🔥 Noise off. Silence is gold — that message wasn’t.",
    ],
    "link_guard": [
        "🔗 Shady links trimmed. Passage closed.",
        "⚔ Guard sliced another batch of links.",
        "🚫 Link spam eliminated.",
        "🔗 A link? Here. Real content? Nope. Go fix your clickbait.",
        "🪚 Ads dressed as “helpful” links — Guard cuts without anesthesia.",
        "🚷 This URL won’t get through — even with a bribe. Road closed.",
        "💀 Bad domain went nowhere. Count yourself lucky it wasn’t you.",
    ],
    "bad_guard": [
        "🤬 Profanity post removed. Watch your language.",
        "🪓 Foul language scrubbed.",
        "😈 Guard doesn’t do verbal landfills.",
        "🤭 Picked nasty words with care? Guard restored the aesthetic: silence.",
        "🥶 Swearing isn’t an argument — lesson of the day delivered.",
        "👋 Nasty vocabulary sent on unpaid leave.",
        "🙃 Vulgarity disabled by default — that’s us.",
    ],
    "mute_guard": [
        "🔇 Offender went quiet. Order restored.",
        "⛓ One loud passenger sent to cool off.",
        "🔇 Time for a one-on-one with silence. It’s smarter.",
        "⏸ “Think about it” mode on. You’ll leave when you’re ready.",
        "🤐 You’re the audience now. Behave.",
    ],
    "ban_guard": [
        "☠ Spammer thrown overboard.",
        "🚪 Another junk guest bounced from the chat.",
        "🚁 Final destination: not here, not to us, not back.",
        "📦 Packed and left at the door. No returns.",
    ],
    "gen_guard": [
        "😈 Guard keeps cleaning house.",
        "🛡 Order restored.",
        "🚫 Another load of junk destroyed.",
        "😏 Rules don’t argue with violators — they vacuum them up.",
        "🛡 Guard grabbed the broom again. Who’s next for the mop?",
    ],
    "spam_med": [
        "Spam removed. Thanks for keeping the chat tidy.",
        "Extra message removed by moderation.",
        "The message failed the filter and was deleted.",
    ],
    "link_med": [
        "Link message removed per chat rules.",
        "Link not allowed — message removed.",
    ],
    "bad_med": [
        "Profanity message removed.",
        "Language rule broken — post removed.",
    ],
    "mute_med": [
        "Member restricted per chat rules.",
        "A temporary restriction was applied.",
    ],
    "ban_med": [
        "Member removed from the chat per rules.",
        "The member’s access to the chat was ended.",
    ],
    "gen_med": [
        "Message handled by moderation.",
        "Chat rules were applied.",
    ],
    "spam_soft": [
        "We removed a message that didn’t fit the rules. Questions? Contact the admins.",
        "One message was deleted to keep the chat comfortable.",
    ],
    "link_soft": [
        "Link message removed — that’s how protection is set for this chat.",
    ],
    "bad_soft": [
        "Message removed: expression filter is active in this chat.",
    ],
    "mute_soft": [
        "The member’s ability to send messages was temporarily limited.",
    ],
    "ban_soft": [
        "The member left the chat as decided by protection.",
    ],
    "gen_soft": [
        "Chat protection handled the violation.",
        "The message didn’t pass review and was removed.",
    ],
}

GUARDIAN_PERIODIC_TEXTS_RU: Final[list[str]] = [
    "😈 AntiSpam Guard на месте.\nПока всё спокойно.\nСпамеров не обнаружено.\nНо если появятся — разберусь.",
    "🛡 AntiSpam Guard проверил чат.\nСпам не обнаружен.\nМожно продолжать общаться спокойно.",
    "😈 Я здесь.\nСлежу за ссылками,\nботами\nи подозрительными сообщениями.\nЕсли кто-то решит спамить — долго не проживёт.",
    "🛡 Guard проверяет чат.\nЕсли заметите странные ссылки — можете не переживать.\nЯ их тоже вижу.",
    "😈 AntiSpam Guard на дежурстве.\nПорядок в чате поддерживается автоматически.",
]

GUARDIAN_PERIODIC_TEXTS_EN: Final[list[str]] = [
    "😈 AntiSpam Guard is here.\nAll quiet for now.\nNo spammers spotted.\nIf they show up — I’ll handle it.",
    "🛡 AntiSpam Guard checked the chat.\nNo spam found.\nYou can keep chatting peacefully.",
    "😈 I’m watching.\nLinks, bots,\nand suspicious messages.\nIf someone spams — they won’t last long.",
    "🛡 Guard is watching the chat.\nWeird links?\nDon’t worry — I see them too.",
    "😈 AntiSpam Guard on duty.\nOrder in the chat stays automatic.",
]


def public_alert_pools(locale: str) -> dict[str, list[str]]:
    from app.i18n import normalize_locale

    loc = normalize_locale(locale)
    return dict(_PUBLIC_ALERT_POOLS_EN if loc == "en" else _PUBLIC_ALERT_POOLS_RU)


def guardian_periodic_texts(locale: str) -> list[str]:
    from app.i18n import normalize_locale

    loc = normalize_locale(locale)
    return list(GUARDIAN_PERIODIC_TEXTS_EN if loc == "en" else GUARDIAN_PERIODIC_TEXTS_RU)
