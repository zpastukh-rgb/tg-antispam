# tests/test_moderation_logic.py
"""Тесты логики модерации: stopword_hit, profanity_hit, normalize."""

from __future__ import annotations

import pytest

# Импорты из moderation (чистые функции без session)
from app.handlers.moderation import (
    stopword_hit,
    profanity_hit,
    jobs_offer_hit,
    normalize_spam_text,
    token_set,
)
from app.handlers.moderation import normalize


def test_normalize():
    assert normalize("  Привет  ") == "привет"
    assert normalize("Ёжик") == "ежик"


def test_token_set():
    assert "hello" in token_set("hello world")
    assert "привет" in token_set("привет пока")


def test_stopword_hit():
    assert stopword_hit("привет мир", {"спам"}, None) is None
    assert stopword_hit("привет спам мир", {"спам"}, None) == "спам"
    assert stopword_hit("привет спам", set(), None) is None


def test_profanity_hit():
    assert profanity_hit("нормальный текст", set(), None) is None
    assert profanity_hit("текст с матом тут", {"мат"}, None) == "мат"
    assert profanity_hit("мат", {"мат"}, None) == "мат"


def test_profanity_hit_roots_and_phrases():
    # Корневое срабатывание: префикс / составной токен (в «хуевишна» подстроки «хуй» нет — это другое слово)
    assert profanity_hit("хуйня мадам", {"хуй"}, None) == "хуй"
    assert profanity_hit("подработки без вложений тут", {"подработк"}, None) == "подработк"
    # Фраза
    assert profanity_hit("это легкий заработок без вложений", {"легкий заработок"}, None) == "легкий заработок"


def test_profanity_hit_false_positives_delivery_and_ship():
    # «ставк» внутри «доставка» — не казино
    assert profanity_hit("нужна доставка в краснотурьинск советская 62", {"ставк"}, None) is None
    assert profanity_hit("ставки на футбол сегодня", {"ставк"}, None) == "ставк"
    # «бля» в «корабля» — не мат
    assert profanity_hit("мира 76 подъезд от корабля до вокзала", {"бля"}, None) is None
    assert profanity_hit("блять тут шум", {"бля"}, None) == "бля"


def test_profanity_hit_casino_brand_prefixes():
    assert profanity_hit("париж красивый город", {"пари"}, None) is None
    assert profanity_hit("паритет сторон соблюден", {"пари"}, None) is None
    assert profanity_hit("парикмахерская рядом", {"пари"}, None) is None
    assert profanity_hit("париматч зеркало", {"пари"}, None) == "пари"
    assert profanity_hit("леонид пришёл", {"леон"}, None) is None
    assert profanity_hit("леон букмекер", {"леон"}, None) == "леон"
    assert profanity_hit("тотальный контроль", {"тотал"}, None) is None
    assert profanity_hit("тотал больше 2 5", {"тотал"}, None) == "тотал"


def test_jobs_offer_hit_patterns():
    msg = "Всем привет, нужны пару людей, можно зарабатывать 300к, смотри в био"
    assert jobs_offer_hit(msg.lower(), msg.lower()) == "jobs_offer_pattern"
    msg2 = "хочешь заработать больше чем сейчас смотри в био"
    assert jobs_offer_hit(msg2.lower(), msg2.lower()) == "jobs_offer_pattern"
    clean = "Всем привет, завтра встреча в 12:00, обсудим новости проекта"
    assert jobs_offer_hit(clean.lower(), clean.lower()) is None


def test_normalize_spam_text_obfuscation():
    assert "заработок" in normalize_spam_text("з@р@б0т0к")
    assert "в лс" in normalize_spam_text("в л.с")
    assert "заработок" in normalize_spam_text("зapaбoтok")


# -------------------------------------------------------------------------
# Гранулярные тогглы по типам медиа (filter_media_*).
# -------------------------------------------------------------------------


class _StubRule:
    """Минимальный «правило»-объект, поддерживающий getattr() для нужных тогглов."""

    def __init__(self, **kwargs):
        # Все 9 тогглов по умолчанию False, заодно сохраняем переопределения.
        for f in (
            "filter_media_photos",
            "filter_media_videos",
            "filter_media_stickers",
            "filter_media_animations",
            "filter_media_voice",
            "filter_media_video_notes",
            "filter_media_audio",
            "filter_media_custom_emoji",
            "filter_media_plain_emoji",
        ):
            setattr(self, f, kwargs.get(f, False))


class _StubMessage:
    """Минимальное «сообщение»-объект с произвольными атрибутами."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        # Поля, к которым обращается matched_media_kind через getattr.
        for k in (
            "photo",
            "video",
            "sticker",
            "animation",
            "voice",
            "video_note",
            "audio",
            "entities",
            "caption_entities",
        ):
            if not hasattr(self, k):
                setattr(self, k, None)


def test_any_granular_media_enabled_default_false():
    from app.handlers.moderation import any_granular_media_enabled

    rule = _StubRule()
    assert any_granular_media_enabled(rule) is False


def test_any_granular_media_enabled_any_true():
    from app.handlers.moderation import any_granular_media_enabled

    assert any_granular_media_enabled(_StubRule(filter_media_photos=True)) is True
    assert any_granular_media_enabled(_StubRule(filter_media_custom_emoji=True)) is True


def test_matched_media_kind_photos():
    from app.handlers.moderation import matched_media_kind

    rule = _StubRule(filter_media_photos=True)
    msg = _StubMessage(photo=[{"file_id": "x"}])
    assert matched_media_kind(msg, rule) == "photos"
    # Если фото есть, но тоггл выключен — не срабатывает.
    rule_off = _StubRule()
    assert matched_media_kind(msg, rule_off) is None


def test_matched_media_kind_stickers_only():
    from app.handlers.moderation import matched_media_kind

    rule = _StubRule(filter_media_stickers=True)
    sticker_msg = _StubMessage(sticker={"file_id": "s"})
    photo_msg = _StubMessage(photo=[{"file_id": "p"}])
    assert matched_media_kind(sticker_msg, rule) == "stickers"
    assert matched_media_kind(photo_msg, rule) is None  # фото не должно цеплять стикер-тоггл


def test_matched_media_kind_custom_emoji_in_entities():
    from app.handlers.moderation import matched_media_kind

    class _Ent:
        def __init__(self, t):
            self.type = t

    rule = _StubRule(filter_media_custom_emoji=True)
    msg = _StubMessage(entities=[_Ent("bold"), _Ent("custom_emoji")])
    assert matched_media_kind(msg, rule) == "custom_emoji"

    msg2 = _StubMessage(entities=[_Ent("bold")])
    assert matched_media_kind(msg2, rule) is None


def test_matched_media_kind_priority_photos_before_videos():
    """Если в сообщении одновременно фото и видео и оба тоггла включены — берём фото (первое в порядке).
    Порядок проверки фиксирован: photos → videos → stickers → animations → voice → video_notes → audio → custom_emoji.
    """
    from app.handlers.moderation import matched_media_kind

    rule = _StubRule(filter_media_photos=True, filter_media_videos=True)
    msg = _StubMessage(photo=[{"x": 1}], video={"y": 1})
    assert matched_media_kind(msg, rule) == "photos"


def test_matched_media_kind_returns_none_when_no_toggles():
    from app.handlers.moderation import matched_media_kind

    rule = _StubRule()  # все выкл
    msg = _StubMessage(photo=[{"x": 1}], video={"y": 1}, sticker={"z": 1})
    assert matched_media_kind(msg, rule) is None


def test_matched_media_kind_plain_emoji_in_text():
    """Обычные Unicode-эмодзи в тексте ловятся через filter_media_plain_emoji."""
    from app.handlers.moderation import matched_media_kind

    rule_on = _StubRule(filter_media_plain_emoji=True)
    rule_off = _StubRule()

    # Простой смайл-эмотикон
    assert matched_media_kind(_StubMessage(text="Привет 😀"), rule_on) == "plain_emoji"
    # Дингбат / misc symbol
    assert matched_media_kind(_StubMessage(text="OK ✅"), rule_on) == "plain_emoji"
    # Флаг (regional indicators)
    assert matched_media_kind(_StubMessage(text="🇷🇺 привет"), rule_on) == "plain_emoji"
    # Эмодзи в caption тоже считаются
    assert matched_media_kind(_StubMessage(caption="фото с 🎉"), rule_on) == "plain_emoji"
    # Чистый текст без эмодзи — не ловим
    assert matched_media_kind(_StubMessage(text="привет мир"), rule_on) is None
    # Выключенный тоггл — не ловим даже если есть эмодзи
    assert matched_media_kind(_StubMessage(text="😀"), rule_off) is None


def test_plain_emoji_does_not_false_positive_on_punctuation():
    """Обычные знаки препинания / латиница / кириллица — не эмодзи."""
    from app.handlers.moderation import matched_media_kind

    rule = _StubRule(filter_media_plain_emoji=True)
    for txt in ("hello world!", "цена 100$", "тут — тире", "вопрос?", "@user"):
        assert matched_media_kind(_StubMessage(text=txt), rule) is None


def test_matched_media_kind_free_ignores_premium_granules():
    """Без Premium учитываются только фото/видео/стикеры; анимации и остальное — нет."""
    from app.handlers.moderation import matched_media_kind

    rule_anim = _StubRule(filter_media_animations=True)
    assert matched_media_kind(_StubMessage(animation={"file_id": "a"}), rule_anim, owner_premium_features=False) is None
    assert matched_media_kind(_StubMessage(animation={"file_id": "a"}), rule_anim, owner_premium_features=True) == "animations"

    rule_st = _StubRule(filter_media_stickers=True)
    assert (
        matched_media_kind(_StubMessage(sticker={"file_id": "s"}), rule_st, owner_premium_features=False) == "stickers"
    )


def test_any_granular_media_free_tier():
    from app.handlers.moderation import any_granular_media_free_tier

    assert any_granular_media_free_tier(_StubRule()) is False
    assert any_granular_media_free_tier(_StubRule(filter_media_photos=True)) is True
    assert any_granular_media_free_tier(_StubRule(filter_media_animations=True)) is False




class _MentionRule:
    """Stub rule с гранулярными mention-полями (по умолчанию все False)."""

    def __init__(self, **kwargs):
        for f in (
            "filter_mention_users",
            "filter_mention_bots",
            "filter_mention_channels",
            "filter_mention_text_mention",
            "filter_mention_hashtags",
            "filter_mention_bot_commands",
            "filter_mention_cashtags",
            "filter_mention_emails",
            "filter_mention_mass_enabled",
        ):
            setattr(self, f, kwargs.get(f, False))
        # Порог для массовых: дефолт 5, можно переопределить.
        setattr(self, "filter_mention_mass_threshold", int(kwargs.get("filter_mention_mass_threshold", 5)))


class _Entity:
    def __init__(self, type_, offset, length, user=None):
        self.type = type_
        self.offset = offset
        self.length = length
        self.user = user


class _MentionMessage:
    def __init__(self, text=None, caption=None, entities=None, caption_entities=None):
        self.text = text
        self.caption = caption
        self.entities = entities or []
        self.caption_entities = caption_entities or []


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


import asyncio


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# Используем asyncio.run, чтобы каждый тест был независим.
def _run_sync(coro):
    return asyncio.run(coro)


def test_username_heuristic_kind_bot():
    from app.handlers.moderation import _username_heuristic_kind

    # Эвристика ловит только суффикс «bot» — для @BotFather нужен API.
    assert _username_heuristic_kind("@my_bot") == "bot"
    assert _username_heuristic_kind("supercoolbot") == "bot"
    assert _username_heuristic_kind("@user123") is None
    assert _username_heuristic_kind("BotFather") is None  # эвристика не ловит — нужен API
    assert _username_heuristic_kind("") is None


def test_classify_username_falls_back_to_user_when_bot_is_none():
    from app.handlers.moderation import _classify_username

    # Без bot и без bot-suffix → 'user'.
    assert _run_sync(_classify_username("alice", None)) == "user"


def test_classify_username_bot_suffix_short_circuits_no_api():
    from app.handlers.moderation import _classify_username

    # 'somebot' — эвристика срабатывает, до API дело не доходит даже если bot=None.
    assert _run_sync(_classify_username("somebot", None)) == "bot"


def test_matched_mention_kind_user_mention_off_returns_none():
    from app.handlers.moderation import matched_mention_kind

    text = "hey @alice cool"
    ent = _Entity("mention", text.index("@"), len("@alice"))
    msg = _MentionMessage(text=text, entities=[ent])
    rule = _MentionRule()
    assert _run_sync(matched_mention_kind(msg, rule, bot=None)) is None


def test_matched_mention_kind_user_mention_on_returns_users():
    from app.handlers.moderation import matched_mention_kind

    text = "hey @alice cool"
    ent = _Entity("mention", text.index("@"), len("@alice"))
    msg = _MentionMessage(text=text, entities=[ent])
    rule = _MentionRule(filter_mention_users=True)
    assert _run_sync(matched_mention_kind(msg, rule, bot=None)) == "users"


def test_matched_mention_kind_bot_via_heuristic():
    from app.handlers.moderation import matched_mention_kind

    text = "ping @SuperBot now"
    ent = _Entity("mention", text.index("@"), len("@SuperBot"))
    msg = _MentionMessage(text=text, entities=[ent])
    # Только bots включён — должен поймать благодаря 'bot'-суффиксу.
    rule = _MentionRule(filter_mention_bots=True)
    assert _run_sync(matched_mention_kind(msg, rule, bot=None)) == "bots"
    # Если боты выкл, а users включены — НЕ должен срабатывать на bot-юзернейм.
    rule_users_only = _MentionRule(filter_mention_users=True)
    assert _run_sync(matched_mention_kind(msg, rule_users_only, bot=None)) is None


def test_matched_mention_kind_text_mention():
    from app.handlers.moderation import matched_mention_kind

    class _U:
        def __init__(self, is_bot=False):
            self.is_bot = is_bot
            self.id = 123

    text = "Hello Alice"
    # text_mention перекрывает «Alice» (5 char от offset 6)
    ent = _Entity("text_mention", text.index("Alice"), len("Alice"), user=_U(is_bot=False))
    msg = _MentionMessage(text=text, entities=[ent])
    # Когда text_mention тоггл включён — ловим
    assert _run_sync(matched_mention_kind(msg, _MentionRule(filter_mention_text_mention=True), bot=None)) == "text_mention"
    # Если же это бот И bots тоггл включён — приоритет «bots»
    ent_bot = _Entity("text_mention", text.index("Alice"), len("Alice"), user=_U(is_bot=True))
    msg2 = _MentionMessage(text=text, entities=[ent_bot])
    assert _run_sync(matched_mention_kind(msg2, _MentionRule(filter_mention_bots=True), bot=None)) == "bots"


def test_matched_mention_kind_hashtag_cashtag_email():
    from app.handlers.moderation import matched_mention_kind

    txt = "skidka #promo $BTC mail user@x.io"
    e_hash = _Entity("hashtag", txt.index("#"), len("#promo"))
    e_cash = _Entity("cashtag", txt.index("$"), len("$BTC"))
    e_mail = _Entity("email", txt.index("user@"), len("user@x.io"))
    msg = _MentionMessage(text=txt, entities=[e_hash, e_cash, e_mail])

    assert _run_sync(matched_mention_kind(msg, _MentionRule(filter_mention_hashtags=True), bot=None)) == "hashtags"
    assert _run_sync(matched_mention_kind(msg, _MentionRule(filter_mention_cashtags=True), bot=None)) == "cashtags"
    assert _run_sync(matched_mention_kind(msg, _MentionRule(filter_mention_emails=True), bot=None)) == "emails"
    assert _run_sync(matched_mention_kind(msg, _MentionRule(), bot=None)) is None


def test_matched_mention_kind_bot_command_only_to_other_bot():
    from app.handlers.moderation import matched_mention_kind

    rule = _MentionRule(filter_mention_bot_commands=True)
    # Команда нашему боту (без @) — не запрещаем
    txt1 = "/start"
    e1 = _Entity("bot_command", 0, len("/start"))
    assert _run_sync(matched_mention_kind(_MentionMessage(text=txt1, entities=[e1]), rule, bot=None)) is None
    # Команда чужому боту — запрещаем
    txt2 = "/buy@spambot now"
    e2 = _Entity("bot_command", 0, len("/buy@spambot"))
    assert _run_sync(matched_mention_kind(_MentionMessage(text=txt2, entities=[e2]), rule, bot=None)) == "bot_commands"


def test_matched_mention_kind_mass_threshold():
    from app.handlers.moderation import matched_mention_kind

    text = "a @b @c @d @e @f"
    ents = []
    pos = 0
    for token in ("@b", "@c", "@d", "@e", "@f"):
        idx = text.index(token, pos)
        ents.append(_Entity("mention", idx, len(token)))
        pos = idx + len(token)
    msg = _MentionMessage(text=text, entities=ents)

    rule_off = _MentionRule(filter_mention_mass_enabled=False, filter_mention_mass_threshold=3)
    assert _run_sync(matched_mention_kind(msg, rule_off, bot=None)) is None

    rule_on = _MentionRule(filter_mention_mass_enabled=True, filter_mention_mass_threshold=5)
    # Ровно 5 — порог, должно сработать.
    assert _run_sync(matched_mention_kind(msg, rule_on, bot=None)) == "mass"

    rule_high = _MentionRule(filter_mention_mass_enabled=True, filter_mention_mass_threshold=10)
    # Меньше порога — не срабатывает.
    assert _run_sync(matched_mention_kind(msg, rule_high, bot=None)) is None


def test_any_granular_mention_enabled_default_false():
    from app.handlers.moderation import any_granular_mention_enabled

    assert any_granular_mention_enabled(_MentionRule()) is False


def test_any_granular_mention_enabled_any_field_true():
    from app.handlers.moderation import any_granular_mention_enabled

    assert any_granular_mention_enabled(_MentionRule(filter_mention_users=True)) is True
    assert any_granular_mention_enabled(_MentionRule(filter_mention_mass_enabled=True)) is True


# -------------------------------------------------------------------------
# Гранулярные тогглы по типу кнопок (filter_button_*).
# -------------------------------------------------------------------------


class _ButtonRule:
    """Stub rule с гранулярными button-полями (по умолчанию все False)."""

    def __init__(self, **kwargs):
        for f in (
            "filter_button_url",
            "filter_button_callback",
            "filter_button_web_app",
            "filter_button_switch_inline",
            "filter_button_login",
            "filter_button_pay",
            "filter_button_copy_text",
            "filter_button_reply",
            "filter_button_mass_enabled",
        ):
            setattr(self, f, kwargs.get(f, False))
        setattr(self, "filter_button_mass_threshold", int(kwargs.get("filter_button_mass_threshold", 5)))


class _Btn:
    """Stub aiogram InlineKeyboardButton — выставляем только нужные поля."""

    def __init__(
        self,
        *,
        url=None,
        callback_data=None,
        web_app=None,
        switch_inline_query=None,
        switch_inline_query_current_chat=None,
        switch_inline_query_chosen_chat=None,
        login_url=None,
        pay=None,
        copy_text=None,
    ):
        self.url = url
        self.callback_data = callback_data
        self.web_app = web_app
        self.switch_inline_query = switch_inline_query
        self.switch_inline_query_current_chat = switch_inline_query_current_chat
        self.switch_inline_query_chosen_chat = switch_inline_query_chosen_chat
        self.login_url = login_url
        self.pay = pay
        self.copy_text = copy_text


class _ReplyMarkup:
    def __init__(self, *, inline_keyboard=None, keyboard=None):
        self.inline_keyboard = inline_keyboard
        self.keyboard = keyboard


class _BtnMessage:
    def __init__(self, *, inline_keyboard=None, keyboard=None):
        if inline_keyboard is None and keyboard is None:
            self.reply_markup = None
        else:
            self.reply_markup = _ReplyMarkup(inline_keyboard=inline_keyboard, keyboard=keyboard)


def test_matched_button_kind_no_markup_returns_none():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage()
    rule = _ButtonRule(filter_button_url=True)
    assert matched_button_kind(msg, rule) is None


def test_matched_button_kind_url_off_returns_none():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(url="https://example.com")]])
    rule = _ButtonRule()  # все выкл
    assert matched_button_kind(msg, rule) is None


def test_matched_button_kind_url_on_returns_url():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(url="https://example.com")]])
    rule = _ButtonRule(filter_button_url=True)
    assert matched_button_kind(msg, rule) == "url"


def test_matched_button_kind_callback():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(callback_data="vote_yes")]])
    assert matched_button_kind(msg, _ButtonRule(filter_button_callback=True)) == "callback"
    assert matched_button_kind(msg, _ButtonRule(filter_button_url=True)) is None


def test_matched_button_kind_web_app():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(web_app=object())]])
    assert matched_button_kind(msg, _ButtonRule(filter_button_web_app=True)) == "web_app"
    assert matched_button_kind(msg, _ButtonRule()) is None


def test_matched_button_kind_switch_inline_ignored_without_premium():
    """На FREE гранула switch-inline в правиле не должна матчиться."""
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(switch_inline_query="x")]])
    rule = _ButtonRule(filter_button_switch_inline=True)
    assert matched_button_kind(msg, rule, owner_premium_features=False) is None


def test_matched_button_kind_reply_ignored_without_premium():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(keyboard=[[object()]])
    assert (
        matched_button_kind(msg, _ButtonRule(filter_button_reply=True), owner_premium_features=False) is None
    )


def test_matched_button_kind_mass_ignored_without_premium():
    from app.handlers.moderation import matched_button_kind

    row = [_Btn(callback_data=f"c{i}") for i in range(5)]
    msg = _BtnMessage(inline_keyboard=[row])
    rule = _ButtonRule(filter_button_mass_enabled=True, filter_button_mass_threshold=3)
    assert matched_button_kind(msg, rule) == "mass"
    assert matched_button_kind(msg, rule, owner_premium_features=False) is None


def test_matched_button_kind_switch_inline_variants():
    from app.handlers.moderation import matched_button_kind

    for kwargs in (
        {"switch_inline_query": "search "},
        {"switch_inline_query_current_chat": ""},
        {"switch_inline_query_chosen_chat": object()},
    ):
        msg = _BtnMessage(inline_keyboard=[[_Btn(**kwargs)]])
        assert (
            matched_button_kind(msg, _ButtonRule(filter_button_switch_inline=True))
            == "switch_inline"
        )
        assert matched_button_kind(msg, _ButtonRule()) is None


def test_matched_button_kind_login():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(login_url=object())]])
    assert matched_button_kind(msg, _ButtonRule(filter_button_login=True)) == "login"
    assert matched_button_kind(msg, _ButtonRule()) is None


def test_matched_button_kind_pay():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(pay=True)]])
    assert matched_button_kind(msg, _ButtonRule(filter_button_pay=True)) == "pay"
    assert matched_button_kind(msg, _ButtonRule()) is None


def test_matched_button_kind_copy_text():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(inline_keyboard=[[_Btn(copy_text=object())]])
    assert matched_button_kind(msg, _ButtonRule(filter_button_copy_text=True)) == "copy_text"
    assert matched_button_kind(msg, _ButtonRule()) is None


def test_matched_button_kind_reply_keyboard():
    from app.handlers.moderation import matched_button_kind

    msg = _BtnMessage(keyboard=[[object()]])
    assert matched_button_kind(msg, _ButtonRule(filter_button_reply=True)) == "reply"
    assert matched_button_kind(msg, _ButtonRule()) is None
    # Reply-флаг НЕ срабатывает на inline_keyboard.
    msg2 = _BtnMessage(inline_keyboard=[[_Btn(url="https://x")]])
    assert matched_button_kind(msg2, _ButtonRule(filter_button_reply=True)) is None


def test_matched_button_kind_mass_threshold():
    from app.handlers.moderation import matched_button_kind

    # 5 callback-кнопок в одном ряду.
    row = [_Btn(callback_data=f"c{i}") for i in range(5)]
    msg = _BtnMessage(inline_keyboard=[row])

    rule_off = _ButtonRule(filter_button_mass_enabled=False, filter_button_mass_threshold=3)
    assert matched_button_kind(msg, rule_off) is None

    rule_on_th5 = _ButtonRule(filter_button_mass_enabled=True, filter_button_mass_threshold=5)
    assert matched_button_kind(msg, rule_on_th5) == "mass"

    rule_on_th10 = _ButtonRule(filter_button_mass_enabled=True, filter_button_mass_threshold=10)
    assert matched_button_kind(msg, rule_on_th10) is None


def test_matched_button_kind_mass_threshold_multi_row():
    from app.handlers.moderation import matched_button_kind

    # 3 ряда × 3 кнопки = 9 штук.
    rows = [[_Btn(url=f"https://x{i}/{j}") for j in range(3)] for i in range(3)]
    msg = _BtnMessage(inline_keyboard=rows)
    rule_mass = _ButtonRule(filter_button_mass_enabled=True, filter_button_mass_threshold=8)
    assert matched_button_kind(msg, rule_mass) == "mass"


def test_any_granular_button_enabled():
    from app.handlers.moderation import any_granular_button_enabled

    assert any_granular_button_enabled(_ButtonRule()) is False
    assert any_granular_button_enabled(_ButtonRule(filter_button_url=True)) is True
    assert any_granular_button_enabled(_ButtonRule(filter_button_mass_enabled=True)) is True
    assert any_granular_button_enabled(_ButtonRule(filter_button_reply=True)) is True


# -------------------------------------------------------------------------
# Гранулярные тогглы по типу sender_chat / forward (модалка «Сообщения от каналов»).
# -------------------------------------------------------------------------


class _ChannelPostRule:
    """Stub rule с гранулярными channel_post-полями (по умолчанию все False)."""

    def __init__(self, **kwargs):
        for f in (
            "filter_channel_post_channels",
            "filter_channel_post_groups",
            "filter_channel_post_anon_admin",
            "filter_channel_post_fwd_channel",
            "filter_channel_post_fwd_group",
            "filter_channel_post_no_username",
            "filter_channel_post_hidden_fwd",
        ):
            setattr(self, f, kwargs.get(f, False))


class _SenderChat:
    def __init__(self, *, id=0, type="channel", username=None):
        self.id = id
        self.type = type
        self.username = username


class _ForwardOrigin:
    """Stub MessageOrigin: type='channel'/'chat'/'hidden_user'/'user'."""

    def __init__(self, *, type="channel", chat=None):
        self.type = type
        self.chat = chat


class _CPMessage:
    def __init__(
        self,
        *,
        sender_chat=None,
        forward_from_chat=None,
        forward_origin=None,
    ):
        self.sender_chat = sender_chat
        self.forward_from_chat = forward_from_chat
        self.forward_origin = forward_origin


CHAT_ID = -100123456789


def test_matched_channel_post_kind_no_sender_no_forward_returns_none():
    from app.handlers.moderation import matched_channel_post_kind

    msg = _CPMessage()
    rule = _ChannelPostRule(filter_channel_post_channels=True)
    assert matched_channel_post_kind(msg, rule, CHAT_ID) is None


def test_matched_channel_post_kind_channel_off_returns_none():
    from app.handlers.moderation import matched_channel_post_kind

    msg = _CPMessage(sender_chat=_SenderChat(id=-100222, type="channel", username="spamchan"))
    rule = _ChannelPostRule()
    assert matched_channel_post_kind(msg, rule, CHAT_ID) is None


def test_matched_channel_post_kind_channel_on_returns_channels():
    from app.handlers.moderation import matched_channel_post_kind

    msg = _CPMessage(sender_chat=_SenderChat(id=-100222, type="channel", username="spamchan"))
    rule = _ChannelPostRule(filter_channel_post_channels=True)
    assert matched_channel_post_kind(msg, rule, CHAT_ID) == "channels"


def test_matched_channel_post_kind_groups():
    from app.handlers.moderation import matched_channel_post_kind

    msg = _CPMessage(sender_chat=_SenderChat(id=-100333, type="supergroup", username="othergrp"))
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_groups=True), CHAT_ID) == "groups"
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_channels=True), CHAT_ID) is None


def test_matched_channel_post_kind_anon_admin():
    from app.handlers.moderation import matched_channel_post_kind

    # sender_chat.id == chat_id → анонимный админ группы.
    msg = _CPMessage(sender_chat=_SenderChat(id=CHAT_ID, type="supergroup", username="ownchat"))
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_anon_admin=True), CHAT_ID) == "anon_admin"
    # Если anon_admin выкл — НЕ должен срабатывать groups, даже если он включён,
    # потому что это собственный чат.
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_groups=True), CHAT_ID) is None


def test_matched_channel_post_kind_no_username_priority():
    from app.handlers.moderation import matched_channel_post_kind

    # channel без username — флаг no_username приоритетнее channels.
    msg = _CPMessage(sender_chat=_SenderChat(id=-100444, type="channel", username=None))
    rule_both = _ChannelPostRule(filter_channel_post_channels=True, filter_channel_post_no_username=True)
    assert matched_channel_post_kind(msg, rule_both, CHAT_ID) == "no_username"
    # Если no_username выкл — срабатывает channels.
    rule_only_channels = _ChannelPostRule(filter_channel_post_channels=True)
    assert matched_channel_post_kind(msg, rule_only_channels, CHAT_ID) == "channels"


def test_matched_channel_post_kind_no_username_free_tier_falls_through_to_channels():
    """Без Premium флаг no_username игнорируется — срабатывает channels."""
    from app.handlers.moderation import matched_channel_post_kind

    msg = _CPMessage(sender_chat=_SenderChat(id=-100444, type="channel", username=None))
    rule_both = _ChannelPostRule(filter_channel_post_channels=True, filter_channel_post_no_username=True)
    assert matched_channel_post_kind(msg, rule_both, CHAT_ID, owner_premium_features=False) == "channels"


def test_matched_channel_post_kind_fwd_requires_premium():
    from app.handlers.moderation import matched_channel_post_kind

    fwd = _SenderChat(id=-100555, type="channel", username="newschan")
    msg = _CPMessage(forward_from_chat=fwd)
    rule = _ChannelPostRule(filter_channel_post_fwd_channel=True)
    assert matched_channel_post_kind(msg, rule, CHAT_ID) == "fwd_channel"
    assert matched_channel_post_kind(msg, rule, CHAT_ID, owner_premium_features=False) is None


def test_matched_channel_post_kind_hidden_requires_premium():
    from app.handlers.moderation import matched_channel_post_kind

    msg = _CPMessage(forward_origin=_ForwardOrigin(type="hidden_user", chat=None))
    rule = _ChannelPostRule(filter_channel_post_hidden_fwd=True)
    assert matched_channel_post_kind(msg, rule, CHAT_ID) == "hidden_fwd"
    assert matched_channel_post_kind(msg, rule, CHAT_ID, owner_premium_features=False) is None


def test_matched_channel_post_kind_fwd_channel_only_when_no_sender_chat():
    from app.handlers.moderation import matched_channel_post_kind

    fwd = _SenderChat(id=-100555, type="channel", username="newschan")
    # Через forward_from_chat (старый aiogram).
    msg = _CPMessage(forward_from_chat=fwd)
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_fwd_channel=True), CHAT_ID) == "fwd_channel"
    # Через forward_origin.chat (новый aiogram v3).
    msg2 = _CPMessage(forward_origin=_ForwardOrigin(type="channel", chat=fwd))
    assert matched_channel_post_kind(msg2, _ChannelPostRule(filter_channel_post_fwd_channel=True), CHAT_ID) == "fwd_channel"


def test_matched_channel_post_kind_fwd_group():
    from app.handlers.moderation import matched_channel_post_kind

    fwd = _SenderChat(id=-100666, type="supergroup", username="othergrp")
    msg = _CPMessage(forward_from_chat=fwd)
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_fwd_group=True), CHAT_ID) == "fwd_group"
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_fwd_channel=True), CHAT_ID) is None


def test_matched_channel_post_kind_hidden_fwd():
    from app.handlers.moderation import matched_channel_post_kind

    msg = _CPMessage(forward_origin=_ForwardOrigin(type="hidden_user", chat=None))
    assert matched_channel_post_kind(msg, _ChannelPostRule(filter_channel_post_hidden_fwd=True), CHAT_ID) == "hidden_fwd"
    assert matched_channel_post_kind(msg, _ChannelPostRule(), CHAT_ID) is None


def test_matched_channel_post_kind_sender_chat_blocks_fwd_check():
    """Если есть sender_chat — форварды НЕ проверяем (это другая ветка)."""
    from app.handlers.moderation import matched_channel_post_kind

    # sender_chat = group (включен groups), forward_from_chat = channel (НЕ должен сработать).
    msg = _CPMessage(
        sender_chat=_SenderChat(id=-100777, type="supergroup", username="g"),
        forward_from_chat=_SenderChat(id=-100888, type="channel", username="c"),
    )
    rule = _ChannelPostRule(filter_channel_post_groups=True, filter_channel_post_fwd_channel=True)
    # Срабатывает groups (sender_chat), не fwd_channel.
    assert matched_channel_post_kind(msg, rule, CHAT_ID) == "groups"


def test_any_granular_channel_post_enabled():
    from app.handlers.moderation import any_granular_channel_post_enabled

    assert any_granular_channel_post_enabled(_ChannelPostRule()) is False
    assert any_granular_channel_post_enabled(_ChannelPostRule(filter_channel_post_channels=True)) is True
    assert any_granular_channel_post_enabled(_ChannelPostRule(filter_channel_post_hidden_fwd=True)) is True
    assert any_granular_channel_post_enabled(_ChannelPostRule(filter_channel_post_anon_admin=True)) is True
