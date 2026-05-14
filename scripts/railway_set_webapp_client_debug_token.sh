#!/usr/bin/env bash
# Поставить GUARD_WEBAPP_DEBUG_LOG_TOKEN на API и WebApp в Railway (одинаковый токен).
# После деплоя тапы в Mini App шлют логи на API → смотри: railway logs -f -s API
#
# Предусловия:
#   npm i -g @railway/cli
#   cd telegram-antispam-guardian
#   railway login
#   railway link   # проект (любой сервис)
#
# Запуск:
#   ./scripts/railway_set_webapp_client_debug_token.sh
#
# Имена сервисов как в твоём проекте (см. smoke_railway_health.sh); переопредели при необходимости:
#   API_SERVICE_NAME=zealous-bravery WEBAPP_SERVICE_NAME=accomplished-cat ./scripts/railway_set_webapp_client_debug_token.sh
#
# Свой токен (≥8 символов), не генерировать:
#   GUARD_WEBAPP_DEBUG_LOG_TOKEN='мой_секрет' ./scripts/railway_set_webapp_client_debug_token.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v railway >/dev/null 2>&1; then
  echo "Установи CLI: npm i -g @railway/cli" >&2
  exit 1
fi

API_SERVICE_NAME="${API_SERVICE_NAME:-zealous-bravery}"
WEBAPP_SERVICE_NAME="${WEBAPP_SERVICE_NAME:-accomplished-cat}"
RAILWAY_ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"
railway_env=( -e "$RAILWAY_ENVIRONMENT" )

TOKEN="${GUARD_WEBAPP_DEBUG_LOG_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    TOKEN="$(openssl rand -hex 16)"
  else
    TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  fi
fi
if [[ "${#TOKEN}" -lt 8 ]]; then
  echo "GUARD_WEBAPP_DEBUG_LOG_TOKEN должен быть не короче 8 символов." >&2
  exit 1
fi

set_railway_var() {
  local svc="$1"
  local key="$2"
  echo ">>> $svc : $key"
  printf '%s' "$TOKEN" | railway variable set "$key" --stdin -s "$svc" "${railway_env[@]}" --skip-deploys
}

set_railway_var "$API_SERVICE_NAME" GUARD_WEBAPP_DEBUG_LOG_TOKEN
set_railway_var "$WEBAPP_SERVICE_NAME" GUARD_WEBAPP_DEBUG_LOG_TOKEN

echo ""
echo ">>> redeploy $API_SERVICE_NAME"
railway redeploy -s "$API_SERVICE_NAME" -y

echo ">>> redeploy $WEBAPP_SERVICE_NAME"
railway redeploy -s "$WEBAPP_SERVICE_NAME" -y

echo ""
echo "Готово. Живой лог (открой Mini App в Telegram, тыкай плитки «Защита»):"
echo "  ./scripts/railway_tail_webapp_client_logs.sh"
echo "  # или: railway logs -f -s $API_SERVICE_NAME"
echo ""
echo "В логах ищи logger: guard.webapp_client — строки [webapp-client] …"
