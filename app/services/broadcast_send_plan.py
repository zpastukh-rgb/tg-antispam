"""Планирование рассылки: те же фильтры чатов, что в POST /send, и оценка для списания AURUM.

Правила списания (кратко для пользователя):
- Ручная рассылка в группы/каналы: **1 AURUM × число выбранных чатов** за один запуск. Участники чатов
  и «размер аудитории» не умножают стоимость. Полные админы — без списания.
- Автопост (ротация по расписанию): за **каждый слот** — та же формула по числу чатов в настройке
  этого автопоста (отдельной «предоплаты за день» пока нет).
- Списание **только** с баланса AURUM (`aurum_credits`). Старый `credits_balance` для рассылок не
  используется.

Кто платит: по умолчанию с того, кто нажал «Отправить». Если это **делегат** в чужих чатах одного
владельца — режим задаётся у владельца (`delegate_broadcast_payer`): всегда владелец, всегда делегат,
или сначала делегат при достаточном балансе, иначе владелец.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, CreditLedger, User, ChatManager

DELEGATE_BROADCAST_PAYER_VALUES = frozenset({"owner", "delegate", "delegate_first"})
DEFAULT_DELEGATE_BROADCAST_PAYER = "delegate_first"


@dataclass(frozen=True)
class BroadcastBillingPlan:
    """Кого списывать за рассылку и хватает ли AURUM. billing_detail — код для API/UI."""

    payer_user: User
    can_afford: bool
    billing_detail: str


def _chat_is_group_destination():
    """Группы/супергруппы для рассылки (не каналы). NULL chat_kind считаем группой."""
    return or_(Chat.chat_kind.is_(None), Chat.chat_kind == "group")


def _chat_is_group_or_channel_destination():
    return or_(Chat.chat_kind.is_(None), Chat.chat_kind.in_(("group", "channel")))


# Верхняя отсечка за один запуск/слот (защита от ошибочного «выбрать всё»).
BROADCAST_MAX_TOKENS = 2500


def broadcast_charge_tokens(*, full_admin: bool, n_users: int, n_groups: int) -> int:
    """
    Стоимость в AURUM за один запуск рассылки или один слот автопоста.

    n_users оставлен для совместимости вызовов; в тариф не входит (аудитория в личку для Premium
    недоступна). Считаем только n_groups — выбранные группы/каналы.
    """
    _ = n_users  # не тарифицируем
    if full_admin:
        return 0
    n_groups = max(0, int(n_groups))
    return min(BROADCAST_MAX_TOKENS, int(n_groups))


async def resolve_broadcast_target_chat_ids(
    session: AsyncSession,
    *,
    viewer_telegram_id: int,
    allow_all_groups: bool,
    target: str,
    body_chat_ids: list[int],
) -> list[int]:
    """Те же chat_id, что собирает POST /admin/broadcasts/.../send для targets groups/all."""
    mode = (target or "users").strip().lower()
    if mode not in {"groups", "all"}:
        return []
    target_chat_ids: list[int] = []
    if body_chat_ids:
        target_chat_ids = [int(x) for x in body_chat_ids if int(x) < 0]
        if not target_chat_ids:
            return []
        if allow_all_groups:
            q = select(Chat.id).where(
                Chat.is_active.is_(True),
                Chat.is_log_chat.is_(False),
                Chat.id < 0,
                Chat.id.in_(target_chat_ids),
                _chat_is_group_or_channel_destination(),
            )
            allowed = {int(x[0]) for x in (await session.execute(q)).all()}
            target_chat_ids = [x for x in target_chat_ids if int(x) in allowed]
        else:
            sub = select(ChatManager.chat_id).where(ChatManager.user_id == int(viewer_telegram_id)).subquery()
            own_q = await session.execute(
                select(Chat.id).where(
                    Chat.is_active.is_(True),
                    Chat.is_log_chat.is_(False),
                    Chat.id < 0,
                    or_(Chat.owner_user_id == int(viewer_telegram_id), Chat.id.in_(select(sub.c.chat_id))),
                    _chat_is_group_or_channel_destination(),
                )
            )
            own_ids = {int(x[0]) for x in own_q.all()}
            target_chat_ids = [x for x in target_chat_ids if int(x) in own_ids]
    else:
        if allow_all_groups:
            res = await session.execute(
                select(Chat.id).where(
                    Chat.is_active.is_(True),
                    Chat.is_log_chat.is_(False),
                    Chat.id < 0,
                    _chat_is_group_destination(),
                )
            )
            target_chat_ids = [int(x[0]) for x in res.all()]
        else:
            sub = select(ChatManager.chat_id).where(ChatManager.user_id == int(viewer_telegram_id)).subquery()
            own_q = await session.execute(
                select(Chat.id).where(
                    Chat.is_active.is_(True),
                    Chat.is_log_chat.is_(False),
                    Chat.id < 0,
                    or_(Chat.owner_user_id == int(viewer_telegram_id), Chat.id.in_(select(sub.c.chat_id))),
                    _chat_is_group_destination(),
                )
            )
            target_chat_ids = [int(x[0]) for x in own_q.all()]
    return target_chat_ids


async def estimate_recipient_counts(
    session: AsyncSession,
    *,
    target: str,
    target_chat_ids: list[int],
) -> tuple[int, int]:
    """Соответствует сбору получателей в run_broadcast_job (без дедупа пересечений — их нет между user tg id и group id)."""
    mode = (target or "users").strip().lower()
    n_users = 0
    n_groups = 0
    if mode in ("users", "all"):
        q = await session.execute(
            select(func.count()).select_from(User).where(User.status == "active", User.telegram_id > 0)
        )
        n_users = int(q.scalar() or 0)
    if mode in ("groups", "all"):
        if target_chat_ids:
            n_groups = len([int(x) for x in target_chat_ids if int(x) != 0])
        else:
            q = await session.execute(
                select(func.count()).select_from(Chat).where(
                    Chat.is_active.is_(True),
                    Chat.is_log_chat.is_(False),
                    Chat.id < 0,
                    _chat_is_group_destination(),
                )
            )
            n_groups = int(q.scalar() or 0)
    if mode == "users":
        return n_users, 0
    if mode == "groups":
        return 0, n_groups
    return n_users, n_groups


async def resolve_broadcast_billing_plan(
    session: AsyncSession,
    *,
    viewer: User,
    viewer_telegram_id: int,
    full_admin: bool,
    cost_tokens: int,
    resolved_chat_ids: list[int],
) -> BroadcastBillingPlan:
    """Кто платит AURUM за этот запуск (владелец чатов / делегат / приоритет)."""
    vt = int(viewer_telegram_id)
    if full_admin or int(cost_tokens) <= 0:
        return BroadcastBillingPlan(payer_user=viewer, can_afford=True, billing_detail="full_admin")
    cost = float(int(cost_tokens))
    cids = [int(x) for x in (resolved_chat_ids or []) if int(x) != 0]
    if not cids:
        au = float(getattr(viewer, "aurum_credits", 0.0) or 0.0)
        return BroadcastBillingPlan(
            payer_user=viewer,
            can_afford=au + 1e-9 >= cost,
            billing_detail="no_target_chats",
        )
    res = await session.execute(select(Chat.owner_user_id).where(Chat.id.in_(cids)))
    owners = {int(x[0]) for x in res.all()}
    if len(owners) != 1:
        au = float(getattr(viewer, "aurum_credits", 0.0) or 0.0)
        return BroadcastBillingPlan(
            payer_user=viewer,
            can_afford=au + 1e-9 >= cost,
            billing_detail="mixed_chat_owners",
        )
    owner_tid = next(iter(owners))
    if vt == owner_tid:
        au = float(getattr(viewer, "aurum_credits", 0.0) or 0.0)
        return BroadcastBillingPlan(
            payer_user=viewer,
            can_afford=au + 1e-9 >= cost,
            billing_detail="self_owner",
        )
    owner_row = (await session.execute(select(User).where(User.telegram_id == int(owner_tid)))).scalar_one_or_none()
    if not owner_row:
        au = float(getattr(viewer, "aurum_credits", 0.0) or 0.0)
        return BroadcastBillingPlan(
            payer_user=viewer,
            can_afford=au + 1e-9 >= cost,
            billing_detail="owner_row_missing",
        )
    mode = str(getattr(owner_row, "delegate_broadcast_payer", None) or DEFAULT_DELEGATE_BROADCAST_PAYER).strip().lower()
    if mode not in DELEGATE_BROADCAST_PAYER_VALUES:
        mode = DEFAULT_DELEGATE_BROADCAST_PAYER
    d_au = float(getattr(viewer, "aurum_credits", 0.0) or 0.0)
    o_au = float(getattr(owner_row, "aurum_credits", 0.0) or 0.0)
    if mode == "owner":
        return BroadcastBillingPlan(
            payer_user=owner_row,
            can_afford=o_au + 1e-9 >= cost,
            billing_detail="forced_owner",
        )
    if mode == "delegate":
        return BroadcastBillingPlan(
            payer_user=viewer,
            can_afford=d_au + 1e-9 >= cost,
            billing_detail="forced_delegate",
        )
    if d_au + 1e-9 >= cost:
        return BroadcastBillingPlan(payer_user=viewer, can_afford=True, billing_detail="delegate_first_delegate")
    if o_au + 1e-9 >= cost:
        return BroadcastBillingPlan(payer_user=owner_row, can_afford=True, billing_detail="delegate_first_owner")
    return BroadcastBillingPlan(payer_user=viewer, can_afford=False, billing_detail="delegate_first_insufficient")


async def debit_user_broadcast_tokens(
    session: AsyncSession,
    *,
    user: User,
    full_admin: bool,
    broadcast_id: int,
    cost_tokens: int,
    idempotency_key_base: str | None = None,
) -> tuple[float, float]:
    """
    Списывает AURUM за рассылку/слот автопоста только с `aurum_credits`.
    Полные админы — без списания. Возвращает (spent_aurum, spent_sub); spent_sub всегда 0.

    idempotency_key_base: если задан, при уже существующих проводках с тем же префиксом списание не повторяется
    (защита от повторного тика автопоста / ретраев).
    """
    if full_admin or int(cost_tokens) <= 0:
        return 0.0, 0.0
    base_raw = (idempotency_key_base or "").strip()
    if base_raw:
        base = base_raw[:100]
        dup = await session.execute(
            select(CreditLedger.id).where(
                CreditLedger.user_id == int(user.id),
                CreditLedger.external_key.startswith(base),
            ).limit(1)
        )
        if dup.scalar_one_or_none():
            return 0.0, 0.0
    cost = float(int(cost_tokens))
    aurum = float(getattr(user, "aurum_credits", 0.0) or 0.0)
    if aurum + 1e-9 < cost:
        raise ValueError("insufficient_tokens")
    if base_raw:
        suf_b = f"{base_raw[:100]}:b"[:128]
    else:
        idem = uuid.uuid4().hex[:20]
        suf_b = f"bc:{int(broadcast_id)}:a:{idem}"[:128]
    user.aurum_credits = round(aurum - cost, 4)
    session.add(
        CreditLedger(
            user_id=int(user.id),
            delta=-round(cost, 4),
            reason="broadcast_aurum",
            external_key=suf_b,
        )
    )
    session.add(user)
    return round(cost, 4), 0.0
