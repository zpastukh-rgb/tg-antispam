#!/usr/bin/env bash
# Проверка /health бота, API и корня фронта. Домены берутся из Railway CLI (railway link в этом репо).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! command -v railway >/dev/null 2>&1; then
  echo "Нужен: npm i -g @railway/cli и railway link" >&2
  exit 1
fi
first_domain() {
  railway domain -s "$1" --json | python3 -c "import sys,json; d=json.load(sys.stdin).get('domains') or []; print(d[0].rstrip('/') if d else '')"
}
BOT="$(first_domain tg-antispam)"
API="$(first_domain zealous-bravery)"
WEB="$(first_domain accomplished-cat)"
if [[ -z "$BOT" || -z "$API" ]]; then
  echo "Не удалось получить домены (railway link? сервисы переименованы?)." >&2
  exit 1
fi
echo "Бот:    $BOT/health"
curl -sS -f "$BOT/health" | head -c 200
echo ""
echo "API:    $API/health"
curl -sS -f "$API/health" | head -c 200
echo ""
if [[ -n "$WEB" ]]; then
  echo "Webapp: $WEB/"
  curl -sS -o /dev/null -w "HTTP %{http_code}\n" -f "$WEB/" || true
fi
echo "OK — все curl завершились успешно."
