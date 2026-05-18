"""Агрегаты партнёрской программы по уровням L1–L3 (сеть и комиссии) для API и DM-панели."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PartnerCommission, User
from app.services.chat_owner_premium import user_effective_miniapp_premium
from app.services.credit_policy import PARTNER_TOKEN_RUB_RATE, REFERRAL_LEVEL_RATES


def referral_partner_ui_max_levels(owner: User | None, now_utc: datetime | None = None) -> int:
    """Совпадает с правилами выплат PartnerCommission (L2/L3 только при Premium у партнёра)."""
    return 3 if user_effective_miniapp_premium(owner, now_utc or datetime.now(timezone.utc)) else 1


def reward_rub_to_partner_tokens(reward_rub: float) -> float:
    return round(float(reward_rub or 0.0) / float(PARTNER_TOKEN_RUB_RATE), 2)


async def referral_partner_dashboard_network(session: AsyncSession, viewer_tg_id: int) -> dict[str, Any]:
    """Размер деревьев: кого пригласили вы (L1), их приглашённые (L2), следующий слой (L3)."""
    l1_rows = (
        await session.execute(
            select(User.telegram_id).where(User.referred_by_tg_id == int(viewer_tg_id)),
        )
    ).all()
    l1_ids = sorted({int(r[0]) for r in l1_rows if r[0]})

    if not l1_ids:
        l2_ids: list[int] = []
    else:
        l2_rows = (
            await session.execute(
                select(User.telegram_id).where(User.referred_by_tg_id.in_(l1_ids)),
            )
        ).all()
        l2_ids = sorted({int(r[0]) for r in l2_rows if r[0]})

    if not l2_ids:
        l3_ids: list[int] = []
    else:
        l3_rows = (
            await session.execute(
                select(User.telegram_id).where(User.referred_by_tg_id.in_(l2_ids)),
            )
        ).all()
        l3_ids = sorted({int(r[0]) for r in l3_rows if r[0]})

    n1 = len(l1_ids)
    n2 = len(l2_ids)
    n3 = len(l3_ids)
    return {"l1": n1, "l2": n2, "l3": n3, "total": n1 + n2 + n3}


async def referral_partner_level_dashboard(session: AsyncSession, owner: User, viewer_tg_id: int) -> dict[str, Any]:
    """Агрегаты PartnerCommission по уровням (ожидание / подтверждено к использованию) + сеть."""
    pct_by_level = {lvl: int(round(rate * 100)) for lvl, rate in REFERRAL_LEVEL_RATES}
    default_rows = [
        {
            "level": lv,
            "percent": int(pct_by_level.get(lv, 0)),
            "pending": {"payments": 0, "sales_rub": 0.0, "reward_tokens": 0.0},
            "confirmed": {"payments": 0, "sales_rub": 0.0, "reward_tokens": 0.0},
        }
        for lv in (1, 2, 3)
    ]
    partner_level_stats = default_rows

    try:
        net = await referral_partner_dashboard_network(session, viewer_tg_id)
    except Exception:
        net = {"l1": 0, "l2": 0, "l3": 0, "total": 0}

    try:
        buckets: defaultdict[int, dict[str, dict[str, float | int]]] = defaultdict(
            lambda: {
                "pending": {"payments": 0, "sales_rub": 0.0, "reward_rub": 0.0},
                "confirmed": {"payments": 0, "sales_rub": 0.0, "reward_rub": 0.0},
            },
        )
        q = await session.execute(
            select(
                PartnerCommission.level,
                PartnerCommission.status,
                func.count(PartnerCommission.id),
                func.coalesce(func.sum(PartnerCommission.sales_amount_rub), 0.0),
                func.coalesce(func.sum(PartnerCommission.reward_amount_rub), 0.0),
            ).where(
                PartnerCommission.owner_user_id == int(owner.id),
                PartnerCommission.level.in_((1, 2, 3)),
                PartnerCommission.status.in_(("pending", "available", "paid")),
            ).group_by(
                PartnerCommission.level,
                PartnerCommission.status,
            ),
        )
        for level_raw, stat, cnt, sales_sum, rew_sum in q.all():
            lv = int(level_raw or 0)
            if lv not in (1, 2, 3):
                continue
            blk = buckets[lv]
            if stat == "pending":
                tgt = blk["pending"]
            elif stat in ("available", "paid"):
                tgt = blk["confirmed"]
            else:
                continue
            tgt["payments"] = int(tgt["payments"]) + int(cnt or 0)
            tgt["sales_rub"] = float(tgt["sales_rub"]) + float(sales_sum or 0.0)
            tgt["reward_rub"] = float(tgt["reward_rub"]) + float(rew_sum or 0.0)

        partner_level_stats = []
        for lv in (1, 2, 3):
            blk = buckets[lv]
            pnd = blk["pending"]
            cfd = blk["confirmed"]
            partner_level_stats.append(
                {
                    "level": lv,
                    "percent": int(pct_by_level.get(lv, 0)),
                    "pending": {
                        "payments": int(pnd["payments"]),
                        "sales_rub": round(float(pnd["sales_rub"]), 2),
                        "reward_tokens": reward_rub_to_partner_tokens(float(pnd["reward_rub"])),
                    },
                    "confirmed": {
                        "payments": int(cfd["payments"]),
                        "sales_rub": round(float(cfd["sales_rub"]), 2),
                        "reward_tokens": reward_rub_to_partner_tokens(float(cfd["reward_rub"])),
                    },
                },
            )
    except Exception:
        partner_level_stats = default_rows

    return {"partner_network": net, "partner_level_stats": partner_level_stats}
