#!/usr/bin/env bash
# Убедиться что ВДС (PII) отвечает и таблица персоналки жива; опционально сравнить с основной БД Railway.
# Читает переменные через Railway CLI (как check_db_urls_from_railway.sh).
#
#   cd telegram-antispam-guardian && ./scripts/verify_pii_from_railway.sh
#
# Нужны: railway link, venv с asyncpg (pip install asyncpg или requirements.txt).

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PGSVC="${RAILWAY_POSTGRES_SERVICE:-Postgres}"
BOTSVC="${BOT_SERVICE_NAME:-tg-antispam}"
ENVF=()
[[ -n "${RAILWAY_ENVIRONMENT:-}" ]] && ENVF=( -e "$RAILWAY_ENVIRONMENT" )

railway_kv() {
  local svc="$1"
  if [[ ${#ENVF[@]} -gt 0 ]] && railway variable list -s "$svc" "${ENVF[@]}" --kv 2>/dev/null; then
    return 0
  fi
  railway variable list -s "$svc" --kv
}

pick_kv() {
  python3 -c '
import sys
keys = sys.argv[1:]
d = {}
for line in sys.stdin:
    line = line.rstrip("\r\n")
    if not line or line.startswith("#"):
        continue
    i = line.find("=")
    if i <= 0:
        continue
    d[line[:i]] = line[i + 1 :]
for k in keys:
    v = (d.get(k) or "").strip()
    if v:
        print(v)
        break
' "$@"
}

MAIN_URL="$(railway_kv "$PGSVC" | pick_kv DATABASE_PUBLIC_URL DATABASE_URL)"
PII_URL="$(railway_kv "$BOTSVC" | pick_kv PII_DATABASE_URL)"

if [[ -z "$PII_URL" ]]; then
  echo "У бота [$BOTSVC] нет PII_DATABASE_URL — персоналка не на ВДС, только Railway." >&2
  exit 1
fi

export DATABASE_URL="${MAIN_URL:-}"
export PII_DATABASE_URL="$PII_URL"

PY=python3
[[ -x "${ROOT}/.venv/bin/python3" ]] && PY="${ROOT}/.venv/bin/python3"
echo ">>> verify_pii_split.py (PII обязателен, MAIN если есть public URL у Postgres)"
"$PY" scripts/verify_pii_split.py
