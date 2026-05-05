#!/usr/bin/env python3
"""
Перенос ПДн (username, first_name) из основной БД в PII-БД и очистка дубликатов в основной.

Запускай ПОСЛЕ того как:
  1) Основная БД уже на Railway (DATABASE_URL) и в ней актуальные данные (после pg_restore дампа с ВДС).
  2) На ВДС создана БД guardian_pii и пользователь guard_pii (как ты делал).
  3) В Railway у бота и API выставлен PII_DATABASE_URL на ВДС (деплой можно после этого скрипта).

Переменные окружения (или передай через аргументы):
  MAIN_DATABASE_URL  — основная (Railway), формат postgresql:// или postgresql+asyncpg://
  PII_DATABASE_URL    — ПДн на ВДС, тот же формат

Пример:
  export MAIN_DATABASE_URL='postgresql://...railway...'
  export PII_DATABASE_URL='postgresql+asyncpg://guard_pii:PASS@157.22.200.153:5432/guardian_pii'
  python3 scripts/split_pii_migrate.py --dry-run
  python3 scripts/split_pii_migrate.py

Скрипт идемпотентен: повторный запуск безопасен.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Нужен psycopg2: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


def _to_psycopg_dsn(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("postgresql+asyncpg://"):
        u = "postgresql://" + u.split("://", 1)[1]
    return u


def ensure_pii_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_personal_profiles (
            telegram_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            first_name VARCHAR(255),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="только показать сколько строк")
    ap.add_argument("--main", dest="main_url", default=os.getenv("MAIN_DATABASE_URL", ""))
    ap.add_argument("--pii", dest="pii_url", default=os.getenv("PII_DATABASE_URL", ""))
    args = ap.parse_args()

    main_raw = (args.main_url or os.getenv("DATABASE_URL", "")).strip()
    pii_raw = (args.pii_url or os.getenv("PII_DATABASE_URL", "")).strip()

    if not main_raw:
        print("Задай MAIN_DATABASE_URL или DATABASE_URL (основная Railway).", file=sys.stderr)
        return 2
    if not pii_raw:
        print("Задай PII_DATABASE_URL (ВДС guardian_pii).", file=sys.stderr)
        return 2

    main_dsn = _to_psycopg_dsn(main_raw)
    pii_dsn = _to_psycopg_dsn(pii_raw)

    main = psycopg2.connect(main_dsn)
    pii = psycopg2.connect(pii_dsn)
    try:
        mc = main.cursor()
        pc = pii.cursor()
        ensure_pii_table(pc)
        pii.commit()

        mc.execute(
            """
            SELECT telegram_id, username, first_name
            FROM users
            WHERE (username IS NOT NULL AND BTRIM(username) <> '')
               OR (first_name IS NOT NULL AND BTRIM(first_name) <> '')
            ORDER BY telegram_id
            """
        )
        rows = mc.fetchall()
        print(f"Найдено строк с ником/именем в основной БД: {len(rows)}")
        if args.dry_run:
            return 0

        if not rows:
            print("Нечего переносить.")
            return 0

        # upsert пачкой
        execute_values(
            pc,
            """
            INSERT INTO user_personal_profiles (telegram_id, username, first_name)
            VALUES %s
            ON CONFLICT (telegram_id) DO UPDATE SET
              username = EXCLUDED.username,
              first_name = EXCLUDED.first_name,
              updated_at = NOW()
            """,
            [
                (
                    int(r[0]),
                    (str(r[1]).strip()[:255] if r[1] is not None else None) or None,
                    (str(r[2]).strip()[:255] if r[2] is not None else None) or None,
                )
                for r in rows
            ],
        )
        pii.commit()

        tids = [int(r[0]) for r in rows]
        mc.execute(
            "UPDATE users SET username = NULL, first_name = NULL WHERE telegram_id = ANY(%s::bigint[])",
            (tids,),
        )
        main.commit()
        print(f"Перенесено в PII и очищено в основной: {len(rows)} пользователей.")
    finally:
        main.close()
        pii.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
