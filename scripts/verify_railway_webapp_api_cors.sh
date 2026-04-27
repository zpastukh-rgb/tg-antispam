#!/usr/bin/env bash
#
# Что делает скрипт (проверка Mini App ↔ API, логика как в DEPLOY-RAILWAY.md, раздел CORS):
#   1) Качает с фронта GET …/guard-api-config.js и вытаскивает значение window.__GUARD_API_BASE__
#      (его задаёт VITE_API_BASE_URL или GUARD_API_BASE_URL на сервисе WebApp при сборке/старте).
#   2) Делает GET {база API}/api/admin/ops/health с заголовком Origin: <полный URL WebApp>.
#   3) Смотрит заголовок Access-Control-Allow-Origin: должен быть * или тот же Origin, что у Mini App,
#      если в API ограничили CORS (переменная CORS_ORIGINS на сервисе API).
#
# Нужны в PATH: curl и python3. Для реальных https://… URL нужен сетевой доступ с машины, где запускаете скрипт.
#
# Запуск (подставьте свой домен WebApp):
#   WEBAPP_URL=https://….up.railway.app ./scripts/verify_railway_webapp_api_cors.sh
#   ./scripts/verify_railway_webapp_api_cors.sh https://….up.railway.app
#
# Дополнительно:
#   EXPECTED_API_URL=https://….up.railway.app — предупредит, если база из JS не совпала с ожидаемой.
#   API_BASE_URL=https://….up.railway.app — если в guard-api-config.js база пустая: проверить health/CORS
#      по этому URL API (домен из Railway → сервис API → Networking).
#
# В zsh не копируйте в терминал строки, начинающиеся с #, как отдельную команду — будет «command not found: #».
#

set -euo pipefail

WEBAPP_URL="${WEBAPP_URL:-${1:-}}"
WEBAPP_URL="${WEBAPP_URL%/}"

if [[ -z "$WEBAPP_URL" ]]; then
  echo "Задайте URL Mini App (сервис WebApp на Railway), например:" >&2
  echo "  WEBAPP_URL=https://....up.railway.app $0" >&2
  echo "  $0 https://....up.railway.app" >&2
  exit 2
fi

echo "WebApp: $WEBAPP_URL"

CFG="$(mktemp)"
trap 'rm -f "$CFG"' EXIT

if ! curl -sfSL "$WEBAPP_URL/guard-api-config.js" -o "$CFG"; then
  echo "ОШИБКА: не удалось скачать $WEBAPP_URL/guard-api-config.js" >&2
  exit 1
fi

API_FROM_JS="$(python3 -c "
import re, sys
raw = open(sys.argv[1], encoding='utf-8', errors='replace').read()
for pat in (
    r'__GUARD_API_BASE__\s*=\s*\"([^\"]*)\"\s*;',
    r\"__GUARD_API_BASE__\s*=\s*'([^']*)'\s*;\",
):
    m = re.search(pat, raw)
    if m:
        print(m.group(1).strip())
        sys.exit(0)
print('')
" "$CFG")"

if [[ -n "${EXPECTED_API_URL:-}" ]]; then
  EXPECTED_API_URL="${EXPECTED_API_URL%/}"
  if [[ "$API_FROM_JS" != "$EXPECTED_API_URL" ]]; then
    echo "ПРЕДУПРЕЖДЕНИЕ: в guard-api-config.js база API «${API_FROM_JS:-пусто}» ≠ EXPECTED_API_URL=$EXPECTED_API_URL" >&2
  fi
fi

if [[ -z "$API_FROM_JS" ]]; then
  echo "ОШИБКА: в guard-api-config.js пустой __GUARD_API_BASE__ — Mini App не знает URL API." >&2
  echo "  Railway → сервис WebApp → Variables: задайте GUARD_API_BASE_URL или VITE_API_BASE_URL = полный https://… вашего API, redeploy." >&2
  if [[ -n "${API_BASE_URL:-}" ]]; then
    API_BASE="${API_BASE_URL%/}"
    echo "  Временная проверка: используется переданный API_BASE_URL=$API_BASE" >&2
  else
    echo "  Либо повторите скрипт с: API_BASE_URL=https://ВАШ-API.up.railway.app (домен сервиса API)." >&2
    exit 1
  fi
else
  API_BASE="${API_FROM_JS%/}"
  echo "API из guard-api-config.js: $API_BASE"
fi

HDR="$(mktemp)"
trap 'rm -f "$CFG" "$HDR"' EXIT

HEALTH_URL="$API_BASE/api/admin/ops/health"
code="$(curl -sS -o /dev/null -w "%{http_code}" "$HEALTH_URL" -H "Origin: $WEBAPP_URL" -D "$HDR" || true)"

if [[ "$code" != "200" ]]; then
  echo "ОШИБКА: $HEALTH_URL вернул HTTP $code (ожидали 200). Проверьте URL API и деплой API." >&2
  exit 1
fi

acao="$(grep -i '^access-control-allow-origin:' "$HDR" | tail -1 | cut -d' ' -f2- | tr -d '\r' || true)"
acao="${acao//[[:space:]]/}"

if [[ -z "$acao" ]]; then
  echo "ПРЕДУПРЕЖДЕНИЕ: в ответе нет Access-Control-Allow-Origin. Браузер в Mini App может заблокировать запросы к другому хосту." >&2
  echo "  В сервисе API задайте CORS_ORIGINS с URL WebApp (или *) — см. DEPLOY-RAILWAY.md, раздел CORS." >&2
  exit 0
fi

if [[ "$acao" == "*" ]]; then
  echo "CORS: Access-Control-Allow-Origin = * (разрешено для любого Origin; для ограничения укажите домен WebApp в CORS_ORIGINS)."
elif [[ "$acao" == "$WEBAPP_URL" ]]; then
  echo "CORS: Access-Control-Allow-Origin совпадает с URL WebApp — ок."
else
  echo "ПРЕДУПРЕЖДЕНИЕ: Access-Control-Allow-Origin=$acao при Origin=$WEBAPP_URL — убедитесь, что в API в CORS_ORIGINS перечислен именно домен Mini App." >&2
fi

echo "Проверка завершена."
