#!/usr/bin/env bash
# Задаёт подключение бота на Railway к PostgreSQL на твоём VDS.
#
# Один раз:
#   npm i -g @railway/cli
#   cd telegram-antispam-guardian
#   railway login
#   railway link          # проект + сервис БОТА
#
# Способ A — DATABASE_URL (пароль без проблемных символов или см. способ B):
#   export DATABASE_URL='postgresql://guard:ПАРОЛЬ@157.22.200.153:5432/guard'
#   ./scripts/railway_set_vds_database.sh
#
# Способ B — без URL (удобно для любого пароля):
#   ./scripts/railway_set_vds_database.sh --pg
#   (скрипт спросит значения или возьми из env: PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE)
#
# В Dashboard удали Reference на старый Railway Postgres (или переменную DATABASE_URL от него).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v railway >/dev/null 2>&1; then
  echo "Установи CLI: npm i -g @railway/cli"
  exit 1
fi

set_vars_stdin() {
  local key="$1"
  local val="$2"
  printf '%s' "$val" | railway variable set "$key" --stdin
}

if [[ "${1:-}" == "--pg" ]]; then
  PGHOST="${PGHOST:?Задай PGHOST (IP VDS)}"
  PGPORT="${PGPORT:-5432}"
  PGUSER="${PGUSER:?Задай PGUSER}"
  PGPASSWORD="${PGPASSWORD:?Задай PGPASSWORD}"
  PGDATABASE="${PGDATABASE:?Задай PGDATABASE}"

  set_vars_stdin "PGHOST" "$PGHOST"
  set_vars_stdin "PGPORT" "$PGPORT"
  set_vars_stdin "PGUSER" "$PGUSER"
  set_vars_stdin "PGPASSWORD" "$PGPASSWORD"
  set_vars_stdin "PGDATABASE" "$PGDATABASE"

  echo "Записаны PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE."
  echo "Удали переменную DATABASE_URL в Railway, если она всё ещё указывает на старый Railway Postgres (иначе она перекроет PG*)."
else
  [[ -n "${DATABASE_URL:-}" ]] || {
    echo "Задай DATABASE_URL"
    echo "  export DATABASE_URL='postgresql://USER:PASS@HOST:5432/DB'"
    exit 1
  }
  set_vars_stdin "DATABASE_URL" "$DATABASE_URL"
fi

echo "Готово. Проверь Variables в Railway → Redeploy бота."
