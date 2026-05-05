#!/usr/bin/env bash
# Подставить основную БД Railway (плагин Postgres) в бот и API через Variable Reference.
# Не трогает секреты вручную — строка берётся у Postgres в том же проекте.
#
# Один раз:
#   npm i -g @railway/cli
#   cd telegram-antispam-guardian
#   railway login
#   railway link    # выбери этот проект (любой сервис — дальше всё по -s)
#
# Запуск:
#   ./scripts/railway_wire_railway_postgres.sh
#
# Если плагин БД называется не «Postgres» (смотри карточку в Railway):
#   POSTGRES_SERVICE_NAME=PostgreSQL ./scripts/railway_wire_railway_postgres.sh
#
# Другая среда (не production):
#   RAILWAY_ENVIRONMENT=staging ./scripts/railway_wire_railway_postgres.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v railway >/dev/null 2>&1; then
  echo "Установи CLI: npm i -g @railway/cli"
  exit 1
fi

POSTGRES_SERVICE_NAME="${POSTGRES_SERVICE_NAME:-Postgres}"
BOT_SERVICE_NAME="${BOT_SERVICE_NAME:-tg-antispam}"
API_SERVICE_NAME="${API_SERVICE_NAME:-zealous-bravery}"
RAILWAY_ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"

# Railway подставит значение при деплое; имя сервиса слева должно совпадать с карточкой в UI.
REF='${{'"${POSTGRES_SERVICE_NAME}"'.DATABASE_URL}}'

echo "Используем reference: ${REF}"
echo "Среда: ${RAILWAY_ENVIRONMENT}"
echo ""

railway_env=( -e "$RAILWAY_ENVIRONMENT" )

for svc in "$BOT_SERVICE_NAME" "$API_SERVICE_NAME"; do
  echo ">>> $svc : DATABASE_URL"
  railway variable set DATABASE_URL="$REF" -s "$svc" "${railway_env[@]}" --skip-deploys
  echo ">>> $svc : удалить PII_DATABASE_URL (если есть)"
  railway variable delete PII_DATABASE_URL -s "$svc" "${railway_env[@]}" 2>/dev/null || true
done

echo ""
echo ">>> Redeploy бот и API (без -e: в твоей версии CLI redeploy не принимает --environment)"
railway redeploy -s "$BOT_SERVICE_NAME" -y
railway redeploy -s "$API_SERVICE_NAME" -y

echo ""
echo "Готово. Логи: Railway → tg-antispam → Deployments."
