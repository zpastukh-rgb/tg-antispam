#!/usr/bin/env python3
"""
Запуск миграции из папки migrations/ на той БД, что задана в DATABASE_URL (или PG*).
Использование:
  python -m scripts.run_migration 005
  railway run python -m scripts.run_migration 005   # на Railway с подставленным DATABASE_URL
"""
from __future__ import annotations

import asyncio
import glob
import os
import sys

# Корень проекта = родитель папки scripts
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


async def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python -m scripts.run_migration <номер>   например: 005")
        sys.exit(1)

    num = sys.argv[1].strip().zfill(3)  # 5 -> 005
    pattern = os.path.join(ROOT, "migrations", f"{num}_*.sql")
    files = glob.glob(pattern)
    if not files:
        print(f"Миграция {num} не найдена: {pattern}")
        sys.exit(1)

    path = files[0]
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()

    # Убираем только комментарии в начале строк и пустые строки для лога; выполняем весь блок
    sql_stripped = sql.strip()
    if not sql_stripped:
        print("Файл миграции пуст.")
        sys.exit(1)

    print(f"Выполняю миграцию: {os.path.basename(path)}")

    # Подключаемся к БД так же, как приложение (те же переменные окружения)
    from sqlalchemy import text
    from app.db.session import engine

    async with engine.begin() as conn:
        # Несколько операторов в файле — разбиваем по ; и выполняем по одному
        for raw in sql_stripped.replace("\r\n", "\n").split(";"):
            part = raw.strip()
            if not part or part.startswith("--"):
                continue
            if not part.endswith(";"):
                part = part + ";"
            await conn.execute(text(part))

    print("Готово.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
