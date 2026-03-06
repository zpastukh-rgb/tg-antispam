# app/handlers/health.py
"""Команда /health для проверки работоспособности бота (в т.ч. в группах)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    """Отвечает в любом чате (группа/личка) — для healthcheck."""
    await message.reply("✅ OK")

