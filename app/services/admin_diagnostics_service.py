"""
Журнал сбоев для владельца: запись инцидентов, сводка уровней (ok / warn / critical), уведомления в Telegram.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_telegram_user_id
from app.db.session import engine
from app.services.telegram_notify import send_user_dm_with_result

log = logging.getLogger(__name__)

_notify_state: dict[str, Any] = {
    "last_level": "ok",
    "last_sent_at": 0.0,
    "last_sent_bucket": "",
}


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


def _mini_app_root_url() -> str:
    return (os.getenv("MINI_APP_URL") or os.getenv("WEBAPP_URL") or "").strip().rstrip("/")


def _guard_pulse_webapp_url() -> str | None:
    base = _mini_app_root_url()
    if not base:
        return None
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}tab=ops&ops=journal"


def _parse_admin_ids_env() -> set[int]:
    out: set[int] = set()
    for part in (os.getenv("ADMIN_TELEGRAM_IDS") or "").split(","):
        p = (part or "").strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except Exception:
            continue
    return out


async def _admin_notify_telegram_ids(session: AsyncSession) -> list[int]:
    """Кому слать алерты: ADMIN_TELEGRAM_IDS + пользователи с полными правами админа в БД."""
    ids: set[int] = set(_parse_admin_ids_env())
    try:
        from sqlalchemy import select
        from app.db.models import User
        from app.services.admin_roles import is_full_admin_user

        res = await session.execute(select(User))
        for u in res.scalars().all():
            try:
                tid = int(getattr(u, "telegram_id", 0) or 0)
                if tid > 0 and is_full_admin_user(u, tid):
                    ids.add(tid)
            except Exception:
                continue
    except Exception:
        log.exception("admin notify ids from db failed")
    return sorted(ids)


def _json_ids(ids: list[int]) -> str:
    clean = sorted({int(x) for x in (ids or []) if int(x) > 0})[:80]
    return json.dumps(clean, ensure_ascii=False)


def _row_severity(affected_count: int, category: str, status_code: int) -> str:
    if affected_count >= 12 or (category == "api" and status_code >= 500 and affected_count >= 6):
        return "critical"
    if affected_count >= 2 or category in ("payment", "telegram_api", "broadcast", "moderation", "bot"):
        return "warn"
    if category == "api" and status_code >= 500:
        return "warn"
    return "warn"


def _compute_level(distinct_users: int, total_incidents: int, by_cat: dict[str, int]) -> tuple[str, list[str]]:
    """
    Уровень за окно: ok | warn | critical + строки для UI/Telegram.
    Пороги настраиваются ENV.
    """
    w_u = _env_int("DIAGNOSTICS_WARN_DISTINCT_USERS", 3)
    w_i = _env_int("DIAGNOSTICS_WARN_INCIDENTS", 10)
    c_u = _env_int("DIAGNOSTICS_CRIT_DISTINCT_USERS", 10)
    c_i = _env_int("DIAGNOSTICS_CRIT_INCIDENTS", 35)

    pay_n = int(by_cat.get("payment", 0) or 0)
    lines: list[str] = []
    if total_incidents <= 0:
        return "ok", ["За выбранное окно записей в журнале сбоев нет — по этому каналу всё спокойно."]

    if pay_n >= 3:
        lines.append(f"Оплаты / уведомления после оплаты: {pay_n} записей — проверьте ЮKassa и доставку сообщений в ЛС.")

    crit = distinct_users >= c_u or total_incidents >= c_i or pay_n >= 6
    warn = distinct_users >= w_u or total_incidents >= w_i or pay_n >= 1

    soft_ok = (not crit) and (not warn) and total_incidents > 0
    if soft_ok:
        return (
            "ok",
            [
                f"В журнале {total_incidents} запис(ей), уникальных пользователей ≈ {distinct_users}. "
                "Это ниже порогов «требует внимания» — можно просто держать в уме.",
            ],
        )

    if crit:
        lines.insert(
            0,
            f"Много затронутых аккаунтов или событий: пользователей ≈ {distinct_users}, записей {total_incidents}. "
            "Смотрите журнал Guard Pulse и логи API.",
        )
        return "critical", lines[:6]
    if warn:
        lines.insert(
            0,
            f"Есть отклонения: пользователей в журнале ≈ {distinct_users}, записей {total_incidents}. "
            "Откройте журнал и при необходимости логи Railway.",
        )
        return "warn", lines[:6]

    return "ok", []


async def fetch_diagnostics_summary(session: AsyncSession, window_hours: int = 24) -> dict[str, Any]:
    wh = max(1, min(int(window_hours or 24), 168))
    interval_sql = f"interval '{int(wh)} hours'"
    q_distinct = text(
        f"""
        SELECT COUNT(DISTINCT elem::bigint) AS n
        FROM admin_incident_feed r
        CROSS JOIN LATERAL jsonb_array_elements_text(
            COALESCE(NULLIF(TRIM(r.affected_telegram_ids_json), '')::jsonb, '[]'::jsonb)
        ) AS elem
        WHERE r.created_at >= NOW() - {interval_sql}
          AND elem ~ '^[0-9]+$'
        """
    )
    r1 = await session.execute(q_distinct)
    distinct_users = int((r1.mappings().first() or {}).get("n") or 0)

    q_tot = text(
        f"""
        SELECT COUNT(*)::int AS n FROM admin_incident_feed r
        WHERE r.created_at >= NOW() - {interval_sql}
        """
    )
    r2 = await session.execute(q_tot)
    total_incidents = int((r2.mappings().first() or {}).get("n") or 0)

    q_cat = text(
        f"""
        SELECT COALESCE(NULLIF(TRIM(r.category), ''), 'api') AS cat, COUNT(*)::int AS c
        FROM admin_incident_feed r
        WHERE r.created_at >= NOW() - {interval_sql}
        GROUP BY 1
        """
    )
    r3 = await session.execute(q_cat)
    by_cat: dict[str, int] = {}
    for row in r3.mappings().all():
        by_cat[str(row["cat"] or "api")] = int(row["c"] or 0)

    level, lines_ru = _compute_level(distinct_users, total_incidents, by_cat)

    return {
        "window_hours": wh,
        "level": level,
        "distinct_users_affected": distinct_users,
        "total_incidents": total_incidents,
        "by_category": by_cat,
        "lines_ru": lines_ru,
        "thresholds": {
            "warn_distinct_users": _env_int("DIAGNOSTICS_WARN_DISTINCT_USERS", 3),
            "warn_incidents": _env_int("DIAGNOSTICS_WARN_INCIDENTS", 10),
            "crit_distinct_users": _env_int("DIAGNOSTICS_CRIT_DISTINCT_USERS", 10),
            "crit_incidents": _env_int("DIAGNOSTICS_CRIT_INCIDENTS", 35),
        },
    }


async def fetch_diagnostics_feed(
    session: AsyncSession,
    *,
    limit: int,
    q: str | None,
) -> list[dict[str, Any]]:
    lim = min(max(int(limit), 1), 200)
    raw_q = (q or "").strip()
    params: dict[str, Any] = {"lim": lim}

    if raw_q:
        q2 = raw_q.lstrip("@").lower()
        params["needle"] = q2
        params["needle_num"] = q2 if q2.isdigit() else "-1"
        sql = text(
            """
            WITH matched AS (
                SELECT u.telegram_id::text AS tid
                FROM users u
                WHERE (
                    (:needle_num <> '-1' AND u.telegram_id::text = :needle_num)
                    OR (LOWER(COALESCE(u.username, '')) = :needle)
                    OR (LOWER(COALESCE(u.first_name, '')) LIKE '%' || :needle || '%')
                )
                LIMIT 200
            )
            SELECT r.id, r.created_at, r.kind, r.method, r.path, r.status_code, r.summary_ru, r.detail_snippet,
                   COALESCE(NULLIF(TRIM(r.severity), ''), 'warn') AS severity,
                   COALESCE(NULLIF(TRIM(r.category), ''), 'api') AS category,
                   COALESCE(r.affected_count, 0) AS affected_count,
                   COALESCE(NULLIF(TRIM(r.affected_telegram_ids_json), ''), '[]') AS affected_telegram_ids_json
            FROM admin_incident_feed r
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    COALESCE(NULLIF(TRIM(r.affected_telegram_ids_json), ''), '[]')::jsonb
                ) AS e(tid),
                matched m
                WHERE e.tid = m.tid
            )
            ORDER BY r.id DESC
            LIMIT :lim
            """
        )
    else:
        sql = text(
            """
            SELECT r.id, r.created_at, r.kind, r.method, r.path, r.status_code, r.summary_ru, r.detail_snippet,
                   COALESCE(NULLIF(TRIM(r.severity), ''), 'warn') AS severity,
                   COALESCE(NULLIF(TRIM(r.category), ''), 'api') AS category,
                   COALESCE(r.affected_count, 0) AS affected_count,
                   COALESCE(NULLIF(TRIM(r.affected_telegram_ids_json), ''), '[]') AS affected_telegram_ids_json
            FROM admin_incident_feed r
            ORDER BY r.id DESC
            LIMIT :lim
            """
        )

    res = await session.execute(sql, params)

    def _fmt_dt(dt):
        if dt is None:
            return ""
        try:
            if hasattr(dt, "astimezone"):
                return dt.astimezone(__import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
        return str(dt)

    items: list[dict[str, Any]] = []
    for row in res.mappings().all():
        items.append({
            "id": int(row["id"]),
            "created_at": _fmt_dt(row["created_at"]),
            "kind": str(row["kind"] or ""),
            "method": str(row["method"] or ""),
            "path": str(row["path"] or ""),
            "status_code": int(row["status_code"] or 0),
            "summary_ru": str(row["summary_ru"] or ""),
            "detail_snippet": str(row["detail_snippet"] or ""),
            "severity": str(row["severity"] or "warn"),
            "category": str(row["category"] or "api"),
            "affected_count": int(row["affected_count"] or 0),
            "affected_telegram_ids_json": str(row["affected_telegram_ids_json"] or "[]"),
        })
    return items


async def _maybe_notify_owners(session: AsyncSession, summary: dict[str, Any]) -> None:
    if (os.getenv("DIAGNOSTICS_TELEGRAM_ALERTS", "1").strip().lower() in ("0", "false", "no")):
        return
    level = str(summary.get("level") or "ok")
    if level == "ok":
        _notify_state["last_level"] = "ok"
        return

    cooldown = float(_env_int("DIAGNOSTICS_NOTIFY_COOLDOWN_SEC", 1200))
    now = time.monotonic()
    bucket = f"{level}:{summary.get('window_hours', 24)}"
    if (
        _notify_state.get("last_sent_bucket") == bucket
        and now - float(_notify_state.get("last_sent_at") or 0) < cooldown
    ):
        return

    targets = await _admin_notify_telegram_ids(session)
    if not targets:
        log.warning("DIAGNOSTICS: no admin telegram ids for alert (set ADMIN_TELEGRAM_IDS or is_admin in DB)")
        return

    lines = summary.get("lines_ru") or []
    body = "\n".join(str(x) for x in lines if x)
    emoji = "🔴" if level == "critical" else "🟠"
    title = "критично" if level == "critical" else "нужно внимание"
    text_plain = (
        f"{emoji} Guard Pulse — {title}\n\n"
        f"Окно: {summary.get('window_hours', 24)} ч\n"
        f"Пользователей в журнале (уник.): ≈ {summary.get('distinct_users_affected', 0)}\n"
        f"Записей: {summary.get('total_incidents', 0)}\n\n"
        f"{body}\n\n"
        "Откройте мини-приложение → Guard Pulse → Журнал сбоев."
    )

    web_url = _guard_pulse_webapp_url()
    reply_markup = None
    if web_url:
        reply_markup = {"inline_keyboard": [[{"text": "📊 Открыть Guard Pulse", "web_app": {"url": web_url}}]]}

    for tid in targets:
        try:
            await send_user_dm_with_result(
                int(tid),
                text_plain,
                parse_mode=None,
                reply_markup=reply_markup,
            )
        except Exception:
            log.exception("diagnostic notify to %s failed", tid)

    _notify_state["last_level"] = level
    _notify_state["last_sent_at"] = now
    _notify_state["last_sent_bucket"] = bucket


def schedule_diagnostics_notify() -> None:
    """Фон: пересчитать сводку и при warn/critical уведомить владельцев (с антиспамом)."""

    async def _job() -> None:
        if engine is None:
            return
        try:
            from app.db.session import AsyncSessionLocal

            if AsyncSessionLocal is None:
                return
            async with AsyncSessionLocal() as session:
                summary = await fetch_diagnostics_summary(session, window_hours=24)
                await _maybe_notify_owners(session, summary)
        except Exception:
            log.exception("schedule_diagnostics_notify failed")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_job())
    except RuntimeError:
        try:
            asyncio.run(_job())
        except Exception:
            log.exception("diagnostics notify (no running loop)")


async def record_unhandled_api_exception(
    method: str,
    path: str,
    exc: BaseException,
    telegram_user_id: int | None,
) -> None:
    """Необработанное исключение в обработчике FastAPI (до формирования ответа)."""
    import traceback

    msg = f"{type(exc).__name__}: {str(exc)[:400]}"
    tb = traceback.format_exc()[-1200:]
    ids = [int(telegram_user_id)] if telegram_user_id and int(telegram_user_id) > 0 else []
    await record_user_incident(
        kind="unhandled_exception",
        category="api",
        summary_ru=(
            f"В API при обработке {method} {path} произошло необработанное исключение. "
            "Смотрите detail_snippet и полный стек в логах Railway (сервис API → Deploy → Logs)."
        ),
        telegram_ids=ids,
        detail_snippet=f"{msg}\n---\n{tb}"[:1900],
        method=method,
        path=path,
        status_code=500,
    )


async def record_http_server_error(
    method: str,
    path: str,
    status_code: int,
    detail_snippet: Optional[str] = None,
    *,
    init_data_header: str | None = None,
    telegram_ids: list[int] | None = None,
) -> None:
    if engine is None:
        return
    m = (method or "")[:16].upper()
    p = (path or "")[:512]
    sc = int(status_code or 500)
    tg_ids: list[int] = []
    if telegram_ids:
        for x in telegram_ids:
            try:
                xi = int(x)
                if xi > 0 and xi not in tg_ids:
                    tg_ids.append(xi)
            except Exception:
                continue
    if init_data_header:
        tid = get_telegram_user_id(init_data_header)
        if tid and int(tid) not in tg_ids:
            tg_ids.append(int(tid))
    aff_json = _json_ids(tg_ids)
    affected_count = len(json.loads(aff_json))
    cat = "api"
    sev = _row_severity(affected_count, cat, sc)
    summary_ru = (
        f"Сервер ответил кодом {sc} на {m} {p}. "
        "Пользователь мог увидеть ошибку в мини-приложении. "
        "Сопоставьте время с логами API на Railway."
    )
    if affected_count:
        summary_ru += f" Зафиксирован Telegram id пользователя: {tg_ids[0]}."
    snip = (detail_snippet or "").strip()[:800] or None
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO admin_incident_feed "
                    "(kind, method, path, status_code, summary_ru, detail_snippet, severity, category, affected_telegram_ids_json, affected_count) "
                    "VALUES ('http_error', :method, :path, :status_code, :summary_ru, :detail_snippet, :severity, :category, :aff, :acount)"
                ),
                {
                    "method": m,
                    "path": p,
                    "status_code": sc,
                    "summary_ru": summary_ru[:4000],
                    "detail_snippet": snip,
                    "severity": sev,
                    "category": cat,
                    "aff": aff_json,
                    "acount": affected_count,
                },
            )
    except Exception:
        log.exception("admin_incident_feed http insert failed path=%s status=%s", p, sc)
        return
    schedule_diagnostics_notify()


async def record_user_incident(
    *,
    kind: str,
    category: str,
    summary_ru: str,
    telegram_ids: list[int],
    detail_snippet: str | None = None,
    method: str = "",
    path: str = "",
    status_code: int = 0,
) -> None:
    """Ручная запись проблемы пользователя (оплата, Telegram API, рассылка, модерация…)."""
    if engine is None:
        return
    k = (kind or "user").strip()[:32] or "user"
    cat = (category or "other").strip()[:64] or "other"
    aff_json = _json_ids(telegram_ids)
    affected_count = len(json.loads(aff_json))
    sev = _row_severity(affected_count, cat, int(status_code or 0))
    m = (method or "")[:16].upper()
    p = (path or "")[:512]
    sc = int(status_code or 0)
    snip = (detail_snippet or "").strip()[:800] or None
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO admin_incident_feed "
                    "(kind, method, path, status_code, summary_ru, detail_snippet, severity, category, affected_telegram_ids_json, affected_count) "
                    "VALUES (:kind, :method, :path, :status_code, :summary_ru, :detail_snippet, :severity, :category, :aff, :acount)"
                ),
                {
                    "kind": k,
                    "method": m,
                    "path": p,
                    "status_code": sc,
                    "summary_ru": (summary_ru or "")[:4000],
                    "detail_snippet": snip,
                    "severity": sev,
                    "category": cat,
                    "aff": aff_json,
                    "acount": affected_count,
                },
            )
    except Exception:
        log.exception("admin_incident_feed user incident insert failed")
        return
    schedule_diagnostics_notify()


def extract_init_data_header_from_request_headers(headers: Any) -> str | None:
    try:
        v = headers.get("X-Telegram-Init-Data") or headers.get("x-telegram-init-data")
        return str(v) if v else None
    except Exception:
        return None
