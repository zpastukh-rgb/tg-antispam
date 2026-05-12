"""Серверный i18n для бота, API и сервисов.

Принципы:
- Один источник истины: словари в ru.py / en.py.
- Точечные ключи: "bot.welcome.title", "inline.protection.open", "billing.premium.extend".
- Безопасный fallback: если ключа нет в выбранной локали — берём из ru, если нет и там — возвращаем сам ключ.
- Поддержка `{var}` через str.format_map(SafeDict): отсутствующие переменные не валят рендер.
"""

from __future__ import annotations

from typing import Any, Iterable

from . import en as _en
from . import ru as _ru

SUPPORTED: tuple[str, ...] = ("ru", "en")
DEFAULT_LOCALE: str = "ru"

_DICTS: dict[str, dict[str, Any]] = {
    "ru": _ru.MESSAGES,
    "en": _en.MESSAGES,
}


class _SafeDict(dict):
    def __missing__(self, key):  # type: ignore[override]
        return "{" + key + "}"


def normalize_locale(value: str | None) -> str:
    """Приводит произвольную строку (`en-US`, `EN`, `ru-RU`) к одной из SUPPORTED.

    Если не распознано — DEFAULT_LOCALE.
    """
    norm = _try_normalize_locale(value)
    return norm if norm in SUPPORTED else DEFAULT_LOCALE


def _try_normalize_locale(value: str | None) -> str | None:
    """Безопасное «угадывание»: возвращает None для пустых/неизвестных значений.

    Используется в negotiate_locale, чтобы корректно переходить к следующему
    источнику языка, если первый источник пустой.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s.startswith("en"):
        return "en"
    if s.startswith("ru"):
        return "ru"
    # Регионы СНГ — оставляем RU по умолчанию для непустых, но «нестандартных» значений.
    if s in {"uk", "be", "kk", "ky", "uz"}:
        return "ru"
    return None


def negotiate_locale(
    user_locale: str | None,
    telegram_language_code: str | None = None,
    *,
    default: str = DEFAULT_LOCALE,
) -> str:
    """Источники: явный выбор пользователя -> Telegram language_code -> default."""
    for candidate in (user_locale, telegram_language_code):
        norm = _try_normalize_locale(candidate)
        if norm in SUPPORTED:
            return norm
    return default


def _lookup(table: dict[str, Any], key: str) -> Any:
    """Доступ к словарю через точечный ключ `a.b.c`."""
    cur: Any = table
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def t(locale: str | None, key: str, **params: Any) -> str:
    """Вернуть локализованную строку. Никогда не кидает исключений."""
    loc = normalize_locale(locale)
    value = _lookup(_DICTS.get(loc, {}), key)
    if value is None and loc != DEFAULT_LOCALE:
        value = _lookup(_DICTS.get(DEFAULT_LOCALE, {}), key)
    if value is None:
        return key
    if not isinstance(value, str):
        return str(value)
    if not params:
        return value
    try:
        return value.format_map(_SafeDict(params))
    except Exception:
        return value


def tn(locale: str | None, base_key: str, count: int, **params: Any) -> str:
    """Простая поддержка множественного числа без icu: ключи `base_key.one`/`.few`/`.many`/`.other`."""
    loc = normalize_locale(locale)
    n = int(count)
    suffix: str
    if loc == "ru":
        n_mod10 = n % 10
        n_mod100 = n % 100
        if n_mod10 == 1 and n_mod100 != 11:
            suffix = "one"
        elif 2 <= n_mod10 <= 4 and not (12 <= n_mod100 <= 14):
            suffix = "few"
        else:
            suffix = "many"
    else:
        suffix = "one" if n == 1 else "other"
    key = f"{base_key}.{suffix}"
    res = t(loc, key, count=n, **params)
    if res == key:
        # Если перевода под суффикс нет — fallback на ".other".
        return t(loc, f"{base_key}.other", count=n, **params)
    return res


def available_locales() -> Iterable[str]:
    return tuple(SUPPORTED)


__all__ = (
    "DEFAULT_LOCALE",
    "SUPPORTED",
    "available_locales",
    "negotiate_locale",
    "normalize_locale",
    "t",
    "tn",
)
