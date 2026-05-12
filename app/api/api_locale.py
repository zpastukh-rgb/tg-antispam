# app/api/api_locale.py
"""Локаль для текстов HTTPException Mini App: Accept-Language → i18n api.errors.*."""

from __future__ import annotations

import contextvars

from starlette.requests import Request

from app.i18n import negotiate_locale, t as i18n_t

API_LOCALE_CTX: contextvars.ContextVar[str] = contextvars.ContextVar("api_locale", default="ru")


def _locale_from_request(request: Request) -> str:
    raw = (request.headers.get("accept-language") or "").strip()
    first = raw.split(",")[0].split(";")[0].strip() if raw else ""
    return negotiate_locale(None, first if first else None)


def set_request_api_locale(request: Request) -> contextvars.Token[str]:
    return API_LOCALE_CTX.set(_locale_from_request(request))


def reset_request_api_locale(token: contextvars.Token[str]) -> None:
    API_LOCALE_CTX.reset(token)


def current_api_locale() -> str:
    return API_LOCALE_CTX.get()


def err_detail(key: str, **kwargs: object) -> str:
    """Текст ошибки API по ключу `api.errors.<key>`."""
    return i18n_t(current_api_locale(), f"api.errors.{key}", **kwargs)
