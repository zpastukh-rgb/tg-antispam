"""Единые правила кредитной политики Guard."""

from __future__ import annotations

REFERRAL_LEVEL_RATES = (
    (1, 0.15),
    (2, 0.10),
    (3, 0.05),
)
PARTNER_TOKEN_RUB_RATE = 2.0  # 1 партнерский токен = 2 RUB

# ИИ: сначала AURUM, при необходимости — credits_balance (если остался после миграций). Рассылки — только AURUM.
AI_SPEND_PRIORITY = ("aurum_credits", "credits_balance")

