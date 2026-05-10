#!/usr/bin/env bash
# Ручной запуск глобального post-commit (последний коммит в текущем репо).
# Использование из корня любого git-репозитория:
#   ./scripts/obsidian-append-changelog.sh
#   OBSIDIAN_VAULT=~/Obsidian/MyVault ./scripts/obsidian-append-changelog.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -e "$ROOT/.git" ]]; then
  echo "Не найден .git в $ROOT" >&2
  exit 1
fi
cd "$ROOT"
HOOK="${HOME}/.githooks/post-commit"
if [[ ! -x "$HOOK" ]]; then
  echo "Нет исполняемого $HOOK. Выполни: git config --global core.hooksPath ~/.githooks" >&2
  exit 1
fi
exec bash "$HOOK"
