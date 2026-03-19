#!/usr/bin/env python3
"""
Сидер: заполнить таблицу profanity_words распространёнными матерными словами.
Запуск: python -m scripts.seed_profanity
Использует DATABASE_URL / DATABASE_PUBLIC_URL.
"""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Наиболее распространённые матерные слова (русский язык, в нижнем регистре, без ё)
PROFANITY_WORDS = [
    "бля", "блядь", "блядина", "блядский", "блядство", "блядун", "блядюга",
    "выебан", "выебать", "выблядок", "выёбываться",
    "гондон", "гондончик",
    "дерьмо", "дерьмовый",
    "долбоёб", "долбоящер",
    "ебал", "ебать", "ебёт", "ебись", "ебля", "ебло", "ебнутый", "ебучий",
    "заебал", "заебать", "заебись", "заёб", "заёбистый",
    "мудак", "мудила", "мудозвон", "мудоёб",
    "наебал", "наебать", "наебнулся", "наёб",
    "нехуй", "нихуя", "нихуя себе",
    "объебал", "объебать", "отъебись", "отъебу",
    "педик", "педераст", "педики",
    "пидор", "пидорас", "пидрила", "пидрило", "пидруга",
    "пизда", "пиздануть", "пиздато", "пиздец", "пиздить", "пиздоватый",
    "пиздой", "пиздюк", "пиздюлей", "пиздюли", "пиздюлина", "пиздюга", "пиздюк",
    "пиздя", "пиздятина", "подъеб", "подъебать", "подъебка",
    "поеб", "поёбать", "похуй", "похую",
    "приёб", "приебать", "приёбываться",
    "проеб", "проебать", "проёб",
    "разъеб", "разъебать", "разъебай", "разъебись",
    "съебать", "съебись",
    "сука", "суки", "сукин", "сукины", "сучара", "сучий",
    "трахать", "трахнул", "трахнула",
    "уебал", "уебать", "уёбище", "уёбок",
    "хуй", "хуя", "хуёв", "хуёвый", "хуев", "хуем", "хуеньки", "хуеплёт",
    "хуила", "хуило", "хуище", "хуйло", "хуйня", "хуйнуть", "хуяк", "хуякать",
    "хуярить", "хуярь", "хуясе", "хуячить",
    "хер", "херня",
    "шалава", "шлюха", "шлюхи",
    "ёб", "ёбаный", "ёбанный", "ёбанат", "ёбана", "ёбнул", "ёбнутый", "ёбушка",
]


async def main() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = (
        os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_PRIVATE_URL")
    )
    if not url:
        print("Задайте DATABASE_URL или DATABASE_PUBLIC_URL")
        sys.exit(1)
    if url.startswith("postgresql://") and "postgresql+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]

    engine = create_async_engine(url, echo=False)
    normalized = set()
    for w in PROFANITY_WORDS:
        n = (w or "").strip().lower().replace("ё", "е")[:64]
        if n:
            normalized.add(n)

    async with engine.begin() as conn:
        for word in sorted(normalized):
            try:
                await conn.execute(
                    text(
                        "INSERT INTO profanity_words (word) VALUES (:w) ON CONFLICT (word) DO NOTHING"
                    ),
                    {"w": word},
                )
            except Exception as e:
                print(f"Skip {word}: {e}")
    print(f"Готово. Загружено/пропущено дубликатов: {len(normalized)} слов.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
