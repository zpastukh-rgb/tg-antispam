#!/usr/bin/env python3
"""
Запуск миграции из папки migrations/ на той БД, что задана в DATABASE_URL (или PG*).
Использование:
  # Локально: сначала активируй venv (venv\\Scripts\\activate на Windows)
  python -m scripts.run_migration 005

  # На Railway (переменные БД подставятся автоматически):
  railway run python -m scripts.run_migration 005
"""
from __future__ import annotations

import asyncio
import glob
import os
import sys

# Корень проекта = родитель папки scripts
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# Проверка: зависимости должны быть установлены (venv или pip install -r requirements.txt)
try:
    import sqlalchemy  # noqa: F401
except ModuleNotFoundError:
    print("Ошибка: не найден модуль sqlalchemy. Активируй виртуальное окружение проекта:")
    print("  Windows (PowerShell):  .\\venv\\Scripts\\Activate.ps1")
    print("  Windows (cmd):         venv\\Scripts\\activate.bat")
    print("  Linux/Mac:             source venv/bin/activate")
    print("Затем:  pip install -r requirements.txt   и снова запусти скрипт.")
    sys.exit(1)


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

    # Для локального railway run нужен DATABASE_PUBLIC_URL (приватный хост не резолвится с ПК)
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = (
        os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_PRIVATE_URL")
    )
    if not url or ("${{" in url or "}}" in url):
        pg_host = os.getenv("PGHOST")
        pg_port = os.getenv("PGPORT", "5432")
        pg_user = os.getenv("PGUSER")
        pg_pass = os.getenv("PGPASSWORD", "")
        pg_db = os.getenv("PGDATABASE", "railway")
        if pg_host and pg_user:
            from urllib.parse import quote_plus
            safe_pass = quote_plus(pg_pass) if pg_pass else ""
            url = f"postgresql://{pg_user}:{safe_pass}@{pg_host}:{pg_port}/{pg_db}"
    if not url:
        print("Ошибка: не задан DATABASE_URL или DATABASE_PUBLIC_URL. Для локального запуска привяжись к сервису Postgres и используй DATABASE_PUBLIC_URL.")
        sys.exit(1)
    if url.startswith("postgresql://") and "postgresql+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]

    engine = create_async_engine(url, echo=False)
    def _sql_chunk_without_leading_line_comments(chunk: str) -> str:
        """Убрать строки-комментарии -- только в начале блока (до первого оператора)."""
        lines_out: list[str] = []
        started = False
        for line in chunk.replace("\r\n", "\n").split("\n"):
            s = line.strip()
            if not s:
                if started:
                    lines_out.append(line)
                continue
            if s.startswith("--") and not started:
                continue
            started = True
            lines_out.append(line)
        return "\n".join(lines_out).strip()

    async with engine.begin() as conn:
        # Несколько операторов в файле — разбиваем по ; и выполняем по одному
        for raw in sql_stripped.replace("\r\n", "\n").split(";"):
            part = _sql_chunk_without_leading_line_comments(raw.strip())
            if not part or part.startswith("--"):
                continue
            if not part.endswith(";"):
                part = part + ";"
            await conn.execute(text(part))

    print("Готово.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
