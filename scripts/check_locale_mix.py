#!/usr/bin/env python3
"""Dev-скрипт: ищет кириллицу в исходниках вне файлов локалей.

Назначение: видеть TODO по переводу — где ещё остался хардкод RU‑текста на бэке.
Не падает (exit 0): просто печатает список нарушений. В CI можно завернуть в must-fail.

Запуск:
    python -m scripts.check_locale_mix          # все файлы
    python -m scripts.check_locale_mix app/api  # отдельная директория

Конфиг:
    EXCLUDE_DIRS  — каталоги, которые игнорируем (venv, миграции, тесты, текстовые
                    словари локалей и moderation roots — там по дизайну есть RU).
    EXCLUDE_FILES — точечные исключения (брендовые тексты, словари локалей).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Кириллический паттерн с обрамляющим контекстом (имя файла:строка:текст).
CYRILLIC_RE = re.compile(r"[А-яЁёА-я]+")

EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    "static",
    # i18n‑словари — там кириллица по дизайну.
    os.path.join("app", "i18n"),
    # Бот‑тексты ещё переводим итеративно; не шумим.
    os.path.join("app", "texts"),
    # Дефолтные корни модерации (RU‑часть остаётся).
    # Сам файл проверяем, но эти константы пропускаем через EXCLUDE_FILES.
}

EXCLUDE_FILES = {
    # Эти модули содержат RU‑константы (словари модерации, бренды).
    os.path.join("app", "db", "ensure_defaults.py"),
    os.path.join("app", "moderation_lexicon.py"),
    os.path.join("scripts", "seed_profanity.py"),
    os.path.join("scripts", "check_locale_mix.py"),
    os.path.join("app", "handlers", "moderation.py"),
}

ALLOWED_EXTS = {".py"}


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix not in ALLOWED_EXTS:
            continue
        rel = str(path.relative_to(root))
        parts = set(rel.split(os.sep))
        # имя любой части пути совпадает с записью в EXCLUDE_DIRS
        if parts & {p for p in EXCLUDE_DIRS if os.sep not in p}:
            continue
        # точечный префикс ("app/i18n", "app/texts") — пропускаем целиком
        if any(rel.startswith(p + os.sep) or rel == p for p in EXCLUDE_DIRS if os.sep in p):
            continue
        if rel in EXCLUDE_FILES:
            continue
        yield path, rel


def _scan_file(path: Path, rel: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for i, line in enumerate(text.splitlines(), start=1):
        if CYRILLIC_RE.search(line):
            out.append((i, line.strip()[:180]))
    return out


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    total = 0
    files_count = 0
    for path, rel in _iter_files(root):
        hits = _scan_file(path, rel)
        if not hits:
            continue
        files_count += 1
        print(f"\n# {rel} — RU mix ({len(hits)} line(s))")
        for ln, snippet in hits[:10]:
            print(f"  {ln}: {snippet}")
        if len(hits) > 10:
            print(f"  … +{len(hits) - 10} more")
        total += len(hits)
    print(f"\nSummary: {total} RU-mix line(s) in {files_count} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
