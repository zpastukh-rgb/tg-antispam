#!/usr/bin/env bash
# Хвост логов API (куда пишутся webapp-client debug строки после railway_set_webapp_client_debug_token.sh).
#
#   ./scripts/railway_tail_webapp_client_logs.sh
#
# Другой сервис:
#   API_SERVICE_NAME=zealous-bravery ./scripts/railway_tail_webapp_client_logs.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v railway >/dev/null 2>&1; then
  echo "Установи CLI: npm i -g @railway/cli" >&2
  exit 1
fi

API_SERVICE_NAME="${API_SERVICE_NAME:-zealous-bravery}"

exec railway logs -f -s "$API_SERVICE_NAME"
