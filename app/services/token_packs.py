"""Пакеты токенов (₽ с маркетинговыми скидками). Единый источник для YooKassa и API."""

from __future__ import annotations

from app.i18n import normalize_locale, t as i18n_t

# tokens -> price RUB (целые; 6 пакетов, 2 «доп.» в UI). Ниже старых цен → больше экономия при базе 2 ₽/токен.
TOKEN_PACK_PRICES_RUB: dict[int, float] = {
    250: 490.0,
    500: 990.0,
    1000: 1440.0,
    2000: 2740.0,
    5000: 6190.0,
    10000: 11290.0,
}

# Крупные пакеты: в интерфейсе по умолчанию скрыты, раскрываются кнопкой
TOKEN_PACK_EXTRA: frozenset[int] = frozenset({5000, 10000})

# Пакеты с маркетинговым тегом на карточке (текст — api.ui.token_pack_tag_*)
TOKEN_PACK_TAG: dict[int, str] = {
    1000: "popular",
    10000: "value",
}

ALLOWED_TOKEN_PACKS: frozenset[int] = frozenset(TOKEN_PACK_PRICES_RUB.keys())

# Ориентир «без скидки» для бейджа экономии: 1 AURUM = 2 ₽ → экономия = токены×2 − цена пакета.
TOKEN_LIST_RUB_PER_TOKEN = 2.0

# Пакеты без углового бейджа «Экономия»: минимальный вход и пакет 500 токенов.
TOKEN_PACK_NO_SAVINGS_BADGE: frozenset[int] = frozenset({250, 500})


def token_pack_tag_for_ui(tokens: int, locale: str | None) -> str | None:
    """Локализованный тег для Mini App (или None)."""
    t = int(tokens)
    kind = TOKEN_PACK_TAG.get(t)
    if not kind:
        return None
    loc = normalize_locale(locale)
    if kind == "popular":
        return i18n_t(loc, "api.ui.token_pack_tag_popular")
    if kind == "value":
        return i18n_t(loc, "api.ui.token_pack_tag_value")
    return None


def pack_savings_label_rub(tokens: int, locale: str | None = None) -> str | None:
    """Экономия в ₽ от базы 2 ₽/токен; на 250 и 500 бейдж не показываем."""
    t = int(tokens)
    price = float(TOKEN_PACK_PRICES_RUB.get(t) or 0.0)
    if t <= 0 or price <= 0:
        return None
    if t in TOKEN_PACK_NO_SAVINGS_BADGE:
        return None
    nominal = float(t) * TOKEN_LIST_RUB_PER_TOKEN
    saved = int(round(nominal - price))
    if saved <= 0:
        return None
    loc = normalize_locale(locale)
    return i18n_t(loc, "api.ui.token_pack_savings", saved=saved)


def pack_discount_label(tokens: int, locale: str | None = None) -> str | None:
    """Совместимость: раньше проценты, теперь то же, что pack_savings_label_rub."""
    return pack_savings_label_rub(tokens, locale)
