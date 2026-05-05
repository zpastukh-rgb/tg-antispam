#!/usr/bin/env bash
# Полный дамп основной БД с ВДС (guard) и восстановление в Railway Postgres.
# Подставь свои URL/пароли. Требуются pg_dump и psql (brew install libpq на Mac).
set -euo pipefail

# === правь здесь ===
VDS_URL="${VDS_URL:-postgresql://guard:ПАРОЛЬ@157.22.200.153:5432/guard}"
RAILWAY_URL="${RAILWAY_URL:-postgresql://user:ПАРОЛЬ@containers-us-west-xxx.railway.app:5432/railway}"

DUMP="$(mktemp /tmp/guard_dump.XXXXXX.sql)"

echo "Дамп с ВДС -> $DUMP"
pg_dump --no-owner --no-acl --format=plain --dbname="$VDS_URL" >"$DUMP"

echo "Заливка в Railway (может занять время)..."
psql "$RAILWAY_URL" -v ON_ERROR_STOP=1 -f "$DUMP"

rm -f "$DUMP"
echo "Готово. Проверь в Railway Variables: DATABASE_URL указывает на этот же Railway Postgres."
