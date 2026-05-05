#!/usr/bin/env bash
# Проверка БД с ноутбука без копипаста из UI: читает переменные через Railway CLI.
#
# Основная: сервис Postgres → DATABASE_PUBLIC_URL (иначе с Mac internal URL не пингуется).
# PII: сервис бота → PII_DATABASE_URL (ВДС по IP — с Mac ок).
#
# Нужны: railway login, railway link (проект), asyncpg в python (pip install -r requirements.txt).
#
# Опционально: RAILWAY_POSTGRES_SERVICE=Postgres  BOT_SERVICE_NAME=tg-antispam  RAILWAY_ENVIRONMENT=production

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v railway >/dev/null 2>&1; then
  echo "Установи CLI: npm i -g @railway/cli && railway link" >&2
  exit 1
fi

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

# stdin: kv; argv: ключи по приоритету (первый непустой)
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

echo ">>> Читаю переменные: Postgres-сервис [$PGSVC], бот [$BOTSVC]"
MAIN_URL="$(railway_kv "$PGSVC" | pick_kv DATABASE_PUBLIC_URL DATABASE_URL)"
PII_URL="$(railway_kv "$BOTSVC" | pick_kv PII_DATABASE_URL)"

if [[ -z "$MAIN_URL" ]]; then
  echo "Не найден DATABASE_PUBLIC_URL / DATABASE_URL у сервиса [$PGSVC]." >&2
  echo "Проверь имя сервиса БД в дашборде или: RAILWAY_POSTGRES_SERVICE=Имя $0" >&2
  exit 1
fi

if [[ "$MAIN_URL" == *railway.internal* ]]; then
  echo "Внимание: у Postgres только внутренний хост — с Mac проверка часто падает." >&2
  echo "В Railway у плагина Postgres добавь/скопируй DATABASE_PUBLIC_URL в Variables." >&2
fi

export DATABASE_URL="$MAIN_URL"
export PII_DATABASE_URL="$PII_URL"

PY=python3
[[ -x "${ROOT}/.venv/bin/python3" ]] && PY="${ROOT}/.venv/bin/python3"
echo ">>> Пинг БД ($PY scripts/check_db_urls.py)"
"$PY" scripts/check_db_urls.py
