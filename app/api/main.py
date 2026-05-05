# app/api/main.py
"""FastAPI приложение для Mini App (REST API)."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.auth import get_telegram_user_id
from app.api.routes import router
from app.db.ensure_defaults import (
    ensure_chats_chat_kind_column,
    ensure_chats_linked_discussion_chat_id_column,
    ensure_chats_linked_channel_chat_id_column,
    ensure_default_trial_promo,
    ensure_default_admin_promo_codes,
    ensure_default_token_aurum_promo_codes,
    ensure_disable_legacy_simple_promo_codes,
    ensure_owner_forever_promo,
    ensure_default_profanity_roots,
    ensure_default_comeback_promo,
    ensure_referral_credits_schema,
    ensure_users_legal_consent_columns,
    ensure_promo_codes_grant_schema,
    ensure_credit_ledger_schema,
    ensure_partner_payouts_schema,
    ensure_partner_commissions_schema,
    ensure_partner_token_rate_v2,
    ensure_subscription_token_rate_v2,
    ensure_subscription_credits_merged_to_aurum_v1,
    ensure_rules_public_alerts_columns,
    ensure_rules_guardian_periodic_columns,
    ensure_users_comeback_offer_column,
    ensure_rules_filter_links_scope_column,
    ensure_rules_filter_links_mode_width,
    ensure_link_blacklist_schema,
    ensure_global_bad_url_patterns_schema,
    ensure_user_global_bad_url_patterns_schema,
    ensure_rules_use_global_bad_urls_column,
    ensure_rules_hard_dictionary_independent_v1,
    ensure_admin_broadcasts_schema,
    ensure_autopost_campaigns_schema,
    ensure_admin_insights_schema,
    ensure_chat_manager_invites_schema,
    ensure_spam_spike_notify_schema,
    ensure_payments_receipt_url_schema,
    ensure_users_subscription_source_schema,
    ensure_users_subscription_activated_at_schema,
    ensure_users_payment_binding_schema,
    ensure_users_yookassa_autorenew_columns,
    ensure_users_group_channel_limits_schema,
    ensure_chat_spike_alerts_schema,
    ensure_rules_spam_spike_columns,
    ensure_admin_dispatch_bucket_unique,
    ensure_app_settings_schema,
    ensure_join_captcha_schema,
    ensure_chat_reputation_schema,
    ensure_rules_post_rules_columns,
    ensure_channel_rule_drafts_schema,
    ensure_moderation_logs_detail_column,
    ensure_user_post_rules_drafts_json_column,
    ensure_users_delegate_broadcast_payer_column,
    ensure_admin_incident_feed_schema,
)
from app.db.session import engine
from app.services.admin_diagnostics_service import (
    extract_init_data_header_from_request_headers,
    record_http_server_error,
    record_unhandled_api_exception,
)

log = logging.getLogger(__name__)


class _QuietUvicornAccessFilter(logging.Filter):
    """Не пишем access-строки для частых polling-запросов Mini App (Railway лимит ~500 лог/с)."""

    _SKIP_SUBSTR = ("/api/presence/ping", "/api/alerts/spike")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for s in self._SKIP_SUBSTR:
            if s in msg:
                return False
        return True


def _install_noisy_access_log_filter() -> None:
    acc = logging.getLogger("uvicorn.access")
    if any(isinstance(f, _QuietUvicornAccessFilter) for f in acc.filters):
        return
    acc.addFilter(_QuietUvicornAccessFilter())


_install_noisy_access_log_filter()


def _is_startup_exempt_path(path: str) -> bool:
    """Маршруты, доступные до завершения фонового прогрева БД (health, документация, корень для Railway)."""
    if path in ("/", "/health", "/api/health"):
        return True
    if path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/redoc"):
        return True
    return False


class _StartupGateMiddleware(BaseHTTPMiddleware):
    """Пока идёт фоновый прогрев БД — остальные маршруты 503, чтобы не ловить гонки."""

    async def dispatch(self, request: Request, call_next):
        if _is_startup_exempt_path(request.url.path):
            return await call_next(request)
        if not getattr(request.app.state, "api_ready", False):
            return JSONResponse({"detail": "Service is starting"}, status_code=503)
        return await call_next(request)


async def _pii_schema_background() -> None:
    """PII на ВДС не должен блокировать готовность API (503 у Mini App → нули на главной)."""
    try:
        from app.services.pii_user_store import ensure_pii_schema

        await ensure_pii_schema()
    except Exception:
        log.warning("ensure_pii_schema failed (опционально PII_DATABASE_URL)", exc_info=True)


async def _run_api_startup_ensures(app: FastAPI) -> None:
    if engine is None:
        return
    asyncio.create_task(_pii_schema_background())
    try:
        await ensure_rules_public_alerts_columns(engine)
        await ensure_rules_guardian_periodic_columns(engine)
        await ensure_users_comeback_offer_column(engine)
        await ensure_rules_filter_links_scope_column(engine)
        await ensure_rules_filter_links_mode_width(engine)
        await ensure_link_blacklist_schema(engine)
        await ensure_global_bad_url_patterns_schema(engine)
        await ensure_user_global_bad_url_patterns_schema(engine)
        await ensure_rules_use_global_bad_urls_column(engine)
        await ensure_chats_chat_kind_column(engine)
        await ensure_chats_linked_discussion_chat_id_column(engine)
        await ensure_chats_linked_channel_chat_id_column(engine)
        await ensure_promo_codes_grant_schema(engine)
        await ensure_default_trial_promo(engine)
        await ensure_default_admin_promo_codes(engine)
        await ensure_referral_credits_schema(engine)
        await ensure_users_legal_consent_columns(engine)
        await ensure_default_token_aurum_promo_codes(engine)
        await ensure_disable_legacy_simple_promo_codes(engine)
        await ensure_default_comeback_promo(engine)
        await ensure_owner_forever_promo(engine)
        await ensure_default_profanity_roots(engine)
        await ensure_credit_ledger_schema(engine)
        await ensure_partner_payouts_schema(engine)
        await ensure_partner_commissions_schema(engine)
        await ensure_partner_token_rate_v2(engine)
        await ensure_subscription_token_rate_v2(engine)
        await ensure_subscription_credits_merged_to_aurum_v1(engine)
        await ensure_rules_hard_dictionary_independent_v1(engine)
        await ensure_admin_broadcasts_schema(engine)
        await ensure_autopost_campaigns_schema(engine)
        await ensure_admin_insights_schema(engine)
        await ensure_chat_manager_invites_schema(engine)
        await ensure_spam_spike_notify_schema(engine)
        await ensure_payments_receipt_url_schema(engine)
        await ensure_users_subscription_source_schema(engine)
        await ensure_users_subscription_activated_at_schema(engine)
        await ensure_users_payment_binding_schema(engine)
        await ensure_users_yookassa_autorenew_columns(engine)
        await ensure_users_group_channel_limits_schema(engine)
        await ensure_chat_spike_alerts_schema(engine)
        await ensure_rules_spam_spike_columns(engine)
        await ensure_admin_dispatch_bucket_unique(engine)
        await ensure_app_settings_schema(engine)
        await ensure_join_captcha_schema(engine)
        await ensure_chat_reputation_schema(engine)
        await ensure_rules_post_rules_columns(engine)
        await ensure_channel_rule_drafts_schema(engine)
        await ensure_moderation_logs_detail_column(engine)
        await ensure_user_post_rules_drafts_json_column(engine)
        await ensure_users_delegate_broadcast_payer_column(engine)
        await ensure_admin_incident_feed_schema(engine)
    except Exception:
        log.exception("API startup ensures failed")
    else:
        # Автопостинг раньше крутился только в процессе бота (app.main). На Railway API и бот часто
        # раздельные сервисы — без тиков здесь рассылка никогда не стартовала. Нужен BOT_TOKEN для Telegram.
        if (os.getenv("BOT_TOKEN") or "").strip():
            from app.services.autopost_loop import autopost_loop

            asyncio.create_task(autopost_loop(interval_sec=30.0))
            log.info("autopost_loop started from API worker (BOT_TOKEN set; duplicate bot worker uses PG advisory lock)")
        else:
            log.warning(
                "autopost_loop not started on API: BOT_TOKEN unset. Add BOT_TOKEN to this service or rely on bot process (python -m app.main)."
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Время старта этого воркера API (Guard Pulse / ops health). Не локальный терминал — тот процесс, что отвечает на HTTP.
    app.state.api_boot_at = datetime.now(timezone.utc)
    # Раньше api_ready=False до конца долгих миграций → Mini App ловил 503 на /api/me и оставался с нулями на главной.
    app.state.api_ready = True
    asyncio.create_task(_run_api_startup_ensures(app))
    yield


app = FastAPI(
    title="AntiSpam Guard API",
    description="REST API для Mini App панели управления",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(_StartupGateMiddleware)

# Mini App может открываться с другого origin. Нельзя одновременно allow_origins=["*"] и
# allow_credentials=True — Starlette падает при старте (uvicorn сразу выходит → 502 у прокси).
# Авторизация через заголовок X-Telegram-Init-Data, не через cookie — credentials не нужны.
_raw_cors = os.getenv("CORS_ORIGINS", "*").split(",")
_cors_origins = [o.strip() for o in _raw_cors if o.strip()]
if not _cors_origins:
    _cors_origins = ["*"]
_cors_credentials = False if _cors_origins == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _AdminIncidentLogMiddleware(BaseHTTPMiddleware):
    """Пишет в admin_incident_feed ответы 5xx по /api/* (кроме прогрева 503) — журнал для владельца в Guard Pulse."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            sc = int(getattr(response, "status_code", 0) or 0)
            path = request.url.path or ""
            if sc == 503 or sc < 500 or not path.startswith("/api/"):
                return response
            if path.startswith("/api/admin/diagnostics/"):
                return response
            tg: list[int] = []
            st = getattr(request.state, "telegram_user_id", None)
            if st:
                try:
                    tg.append(int(st))
                except Exception:
                    pass
            await record_http_server_error(
                request.method,
                path,
                sc,
                detail_snippet=None,
                init_data_header=None,
                telegram_ids=tg or None,
            )
        except Exception:
            log.exception("AdminIncidentLogMiddleware")
        return response


class _AttachTelegramUserAndLogUnhandledMiddleware(BaseHTTPMiddleware):
    """
    Самый внешний слой: вытаскивает telegram id из X-Telegram-Init-Data (для журнала) и
    пишет в БД необработанные исключения по /api/* (иначе 5xx-middleware их не видит).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        if path.startswith("/api/"):
            h = extract_init_data_header_from_request_headers(request.headers)
            if h:
                try:
                    tid = get_telegram_user_id(h)
                    if tid:
                        request.state.telegram_user_id = int(tid)
                except Exception:
                    pass
        try:
            return await call_next(request)
        except RequestValidationError:
            raise
        except HTTPException:
            raise
        except Exception as exc:
            if path.startswith("/api/"):
                tid = getattr(request.state, "telegram_user_id", None)
                try:
                    await record_unhandled_api_exception(request.method, path, exc, tid)
                except Exception:
                    log.exception("record_unhandled_api_exception failed")
            raise


app.add_middleware(_AdminIncidentLogMiddleware)
app.add_middleware(_AttachTelegramUserAndLogUnhandledMiddleware)


@app.get("/")
async def root():
    """Корень: часть платформ шлёт GET / как health — отвечаем сразу, без ожидания прогрева."""
    return {"status": "ok", "service": "antispam-guardian-api"}


@app.get("/health")
@app.get("/api/health")
async def health():
    """Проверка доступности API (и /health для прокси/Railway)."""
    return {"status": "ok"}


app.include_router(router)
