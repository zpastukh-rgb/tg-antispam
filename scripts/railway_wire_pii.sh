#!/usr/bin/env bash
# Записать PII_DATABASE_URL на ВДС в сервисы бота и API в Railway + redeploy.
# Строка не попадает в history, если передаёшь через файл или --stdin.
#
# Предусловия: npm i -g @railway/cli, railway login, railway link (как в railway_wire_railway_postgres.sh)
#
# Вариант A — из env (в той же сессии shell):
#   export PII_DATABASE_URL='postgresql+asyncpg://USER:PASS@IP_ВДС:5432/guardian_pii'
#   ./scripts/railway_wire_pii.sh
#
# Вариант B — из файла (первая строка — полный URL, или строка вида PII_DATABASE_URL=...):
#   echo 'postgresql+asyncpg://...' > ~/.config/guard-pii.url   # chmod 600
#   ./scripts/railway_wire_pii.sh ~/.config/guard-pii.url
#
# Вариант C — вставить URL один раз с клавиатуры, не оставляя в history:
#   ./scripts/railway_wire_pii.sh --stdin
#   (вставь URL, Enter, Ctrl-D)
#
# Опционально: POSTGRES_SERVICE_NAME, BOT_SERVICE_NAME, API_SERVICE_NAME, RAILWAY_ENVIRONMENT

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v railway >/dev/null 2>&1; then
  echo "Установи CLI: npm i -g @railway/cli"
  exit 1
fi

BOT_SERVICE_NAME="${BOT_SERVICE_NAME:-tg-antispam}"
API_SERVICE_NAME="${API_SERVICE_NAME:-zealous-bravery}"
RAILWAY_ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"
railway_env=( -e "$RAILWAY_ENVIRONMENT" )

read_pii_url() {
  local raw=""
  if [[ "${1:-}" == "--stdin" ]]; then
    echo "Вставь PII_DATABASE_URL одной строкой, затем Enter и Ctrl-D:" >&2
    raw="$(cat)"
  elif [[ -n "${1:-}" && -f "${1}" ]]; then
    raw="$(head -n 1 "$1" | tr -d '\r')"
    if [[ "$raw" == PII_DATABASE_URL=* ]]; then
      raw="${raw#PII_DATABASE_URL=}"
      raw="${raw#\"}"
      raw="${raw%\"}"
      raw="${raw#\'}"
      raw="${raw%\'}"
    fi
  fi
  raw="${raw:-${PII_DATABASE_URL:-}}"
  raw="$(echo -n "$raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  printf '%s' "$raw"
}

URL="$(read_pii_url "${1:-}")"
if [[ -z "$URL" ]]; then
  echo "Нет URL. Задай export PII_DATABASE_URL=... или:" >&2
  echo "  $0 путь/к/файлу_с_url" >&2
  echo "  $0 --stdin" >&2
  exit 1
fi

if [[ "$URL" == *postgres.railway.internal* ]] || [[ "$URL" == *postgres.railway.app* ]]; then
  echo "Ошибка: PII должен указывать на ВДС, а не на Railway Postgres." >&2
  exit 1
fi

if [[ "$URL" != postgresql+asyncpg://* ]] && [[ "$URL" != postgresql://* ]]; then
  echo "Предупреждение: ожидается postgresql:// или postgresql+asyncpg:// ..." >&2
fi

set_pii_stdin() {
  local svc="$1"
  printf '%s' "$URL" | railway variable set PII_DATABASE_URL --stdin -s "$svc" "${railway_env[@]}" --skip-deploys
}

echo ">>> Записываю PII_DATABASE_URL (stdin) в $BOT_SERVICE_NAME и $API_SERVICE_NAME, среда $RAILWAY_ENVIRONMENT"
set_pii_stdin "$BOT_SERVICE_NAME"
set_pii_stdin "$API_SERVICE_NAME"

echo ""
echo ">>> Redeploy бот и API"
railway redeploy -s "$BOT_SERVICE_NAME" -y
railway redeploy -s "$API_SERVICE_NAME" -y

echo ""
echo "Готово. На ВДС открой порт 5432 для IP Railway; проверка: railway variable list -s $BOT_SERVICE_NAME --kv | grep PII"
