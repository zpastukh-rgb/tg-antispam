#!/usr/bin/env python3
"""
Проверка: ПДн на ВДС (PII) + основная БД (Railway).

  export DATABASE_URL='postgresql://...'       # публичный Railway, см. check_db_urls_from_railway.sh
  export PII_DATABASE_URL='postgresql+asyncpg://...@ВДС/...'
  python3 scripts/verify_pii_split.py

Печатает агрегаты и последние обновления на ВДС без вывода самих ников/имён.
"""

from __future__ import annotations

import asyncio
import os
import sys


def _asyncpg_dsn(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("postgresql+asyncpg://"):
        return "postgresql://" + u.split("://", 1)[1]
    return u


async def _pii_report(url: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_dsn(url), timeout=20)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='user_personal_profiles' LIMIT 1"
        )
        if not exists:
            print("PII (ВДС): таблица user_personal_profiles НЕ найдена (первый старт бота/API создаст её).")
            return
        row = await conn.fetchrow(
            """
            SELECT COUNT(*)::bigint AS n,
                   COUNT(*) FILTER (WHERE username IS NOT NULL AND btrim(username) <> '')::bigint AS with_u,
                   COUNT(*) FILTER (WHERE first_name IS NOT NULL AND btrim(first_name) <> '')::bigint AS with_fn,
                   MAX(updated_at) AS last_upd
            FROM user_personal_profiles
            """
        )
        assert row
        print(
            f"PII (ВДС): строк в user_personal_profiles={row['n']}, "
            f"с username={row['with_u']}, с first_name={row['with_fn']}, "
            f"последнее updated_at={row['last_upd']}"
        )
        sample = await conn.fetch(
            """
            SELECT telegram_id,
                   (username IS NOT NULL AND btrim(username) <> '') AS has_u,
                   (first_name IS NOT NULL AND btrim(first_name) <> '') AS has_fn,
                   updated_at
            FROM user_personal_profiles
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 5
            """
        )
        if sample:
            print("PII (ВДС): последние 5 по updated_at (telegram_id, есть_ник, есть_имя, updated_at):")
            for r in sample:
                print(f"  {dict(r)}")
    finally:
        await conn.close()


async def _main_report(url: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_dsn(url), timeout=20)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users' LIMIT 1"
        )
        if not exists:
            print("MAIN (Railway): таблица users не найдена.")
            return
        row = await conn.fetchrow(
            """
            SELECT COUNT(*)::bigint AS total,
                   COUNT(*) FILTER (
                       WHERE username IS NOT NULL AND btrim(username) <> ''
                          OR first_name IS NOT NULL AND btrim(first_name) <> ''
                   )::bigint AS still_has_display
            FROM users
            """
        )
        assert row
        print(
            f"MAIN (Railway): users всего={row['total']}, "
            f"с ненулевым username или first_name в самой таблице users={row['still_has_display']} "
            f"(при активном PII после миграции/заходов это число обычно падает)"
        )
    finally:
        await conn.close()


async def amain() -> int:
    pii = (os.getenv("PII_DATABASE_URL") or "").strip()
    main = (os.getenv("DATABASE_URL") or os.getenv("MAIN_DATABASE_URL") or "").strip()
    if not pii:
        print("Задай PII_DATABASE_URL (строка на ВДС).", file=sys.stderr)
        return 2
    try:
        await _pii_report(pii)
    except Exception as e:
        print(f"FAIL PII (ВДС): {e}", file=sys.stderr)
        return 1
    if main:
        try:
            await _main_report(main)
        except Exception as e:
            print(f"FAIL MAIN (Railway): {e}", file=sys.stderr)
            return 1
    else:
        print("DATABASE_URL не задан — пропуск отчёта по основной БД (только PII).")
    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
