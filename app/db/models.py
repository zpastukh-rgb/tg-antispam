# app/db/models.py

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Text,
    func,
    String,
    UniqueConstraint,
    Integer,
    ForeignKey,
    Index
)

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# =========================================================
# ENUMS
# =========================================================

class ActionMode(str, enum.Enum):
    delete = "delete"
    mute = "mute"
    ban = "ban"
    observe = "observe"


class Tariff(str, enum.Enum):
    FREE = "free"
    PREMIUM = "premium"
    # Оставлены для обратной совместимости, считаются как premium
    PRO = "pro"
    BUSINESS = "business"


# =========================================================
# BASE
# =========================================================

class Base(DeclarativeBase):
    pass


# =========================================================
# USER (SaaS-пользователь, подписка, лимиты)
# =========================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tariff: Mapped[str] = mapped_column(String(32), default=Tariff.FREE.value)
    chat_limit: Mapped[int] = mapped_column(Integer, default=3)
    group_limit: Mapped[int] = mapped_column(Integer, default=3)
    channel_limit: Mapped[int] = mapped_column(Integer, default=1)
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Первый успешный платёж по подписке (premium), не сбрасывается при продлении/докупе периода.
    subscription_activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_source: Mapped[str | None] = mapped_column(String(32), nullable=True)  # payment | promo | trial | admin | system
    payment_method_bound: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_method_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # ЮKassa автоплатежи: id сохранённого способа оплаты (payment_method.id из API), режим последней оплаты
    yookassa_payment_method_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    yookassa_last_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)  # live | test
    subscription_autorenew_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    autorenew_last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active")

    # ТЗ Напоминания: первое /start, этапы напоминаний (0=none, 1=12h, 2=24h, 3=3d, 4=done)
    first_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_stage: Mapped[int] = mapped_column(Integer, default=0)
    reports_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credits_balance: Mapped[float] = mapped_column(default=0.0)
    aurum_credits: Mapped[float] = mapped_column(default=0.0)
    bonus_credits: Mapped[float] = mapped_column(default=0.0)
    referred_by_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    ref_invited_count: Mapped[int] = mapped_column(Integer, default=0)
    ref_start_count: Mapped[int] = mapped_column(Integer, default=0)
    ref_share_count: Mapped[int] = mapped_column(Integer, default=0)
    ref_paid_count: Mapped[int] = mapped_column(Integer, default=0)
    ref_sales_total: Mapped[float] = mapped_column(default=0.0)
    ref_earned_credits: Mapped[float] = mapped_column(default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    last_webapp_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comeback_offer_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Mini App: черновики «правила в группе» (JSON-массив), синхронизация между устройствами одного tg-аккаунта.
    post_rules_drafts_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Legal gate (Mini App): фиксация согласий на сервере для админки.
    legal_bundle_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_pd_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)

    # Кто платит AURUM за рассылку, когда постит делегат (менеджер) в чужие чаты: owner | delegate | delegate_first
    delegate_broadcast_payer: Mapped[str] = mapped_column(String(24), default="delegate_first")


# =========================================================
# REFERRAL SHARE EVENTS (события «поделился рефералкой»)
# =========================================================

class ReferralShareHit(Base):
    __tablename__ = "referral_share_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# ADMIN MESSAGE TEMPLATES (шаблоны системных сообщений)
# =========================================================

class AdminMessageTemplate(Base):
    __tablename__ = "admin_message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    event_key: Mapped[str] = mapped_column(String(64), default="manual")
    target_kind: Mapped[str] = mapped_column(String(32), default="owner_admin")
    trigger_hours: Mapped[int] = mapped_column(Integer, default=24)
    min_count: Mapped[int] = mapped_column(Integer, default=1)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    schedule_time_hm: Mapped[str | None] = mapped_column(String(5), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# =========================================================
# ADMIN MESSAGE DISPATCH LOGS (антидубли отправок)
# =========================================================

class AdminMessageDispatchLog(Base):
    __tablename__ = "admin_message_dispatch_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, index=True)
    target_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    event_bucket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpamSpikeNotifySent(Base):
    """Антидубли: одно личное уведомление о всплеске спама на получателя/чат/час (UTC)."""

    __tablename__ = "spam_spike_notify_sent"
    __table_args__ = (
        UniqueConstraint("recipient_telegram_id", "chat_id", "bucket_key", name="uq_spam_spike_dm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    bucket_key: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpamSpikeGroupPingSent(Base):
    """Не чаще одного служебного сообщения в группу за чат/час при всплеске спама."""

    __tablename__ = "spam_spike_group_ping_sent"
    __table_args__ = (UniqueConstraint("chat_id", "bucket_key", name="uq_spam_spike_group_ping"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    bucket_key: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSpikeAlert(Base):
    """Активный флаг «чат под угрозой» для UI (TTL ~1 час)."""

    __tablename__ = "chat_spike_alerts"
    __table_args__ = (
        UniqueConstraint("chat_id", name="uq_chat_spike_alert_chat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    spam_count: Mapped[int] = mapped_column(Integer, default=0)
    joins_count: Mapped[int] = mapped_column(Integer, default=0)
    window_min: Mapped[int] = mapped_column(Integer, default=35)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =========================================================
# CHAT (главная таблица: защищаемые и лог-чаты)
# =========================================================

class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # кто подключил чат (владелец)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    # True = эта группа только лог-чат (зарегистрирована через /setlog)
    is_log_chat: Mapped[bool] = mapped_column(Boolean, default=False)

    # куда слать логи (только для защищаемых чатов)
    log_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # включен ли антиспам (для защищаемых)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # служебные данные
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # group — защищаемая группа/супергруппа; channel — только рассылка (не в лимите «чатов защиты»)
    chat_kind: Mapped[str] = mapped_column(String(16), default="group")

    # Для chat_kind=channel: id супергруппы обсуждения (getChat.linked_chat), чтобы делегат канала имел доступ к API правил комментариев.
    linked_discussion_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Для группы/супергруппы: id привязанного канала (getChat.linked_chat.type=channel) — обратная связь для Mini App без повторного getChat.
    linked_channel_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # статистика
    messages_checked: Mapped[int] = mapped_column(Integer, default=0)
    messages_deleted: Mapped[int] = mapped_column(Integer, default=0)
    users_banned: Mapped[int] = mapped_column(Integer, default=0)

    # ТЗ Напоминания: активность чата для сообщений Guard раз в 3 дня (обновляется при модерации)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


# =========================================================
# CHANNEL (если бот работает с каналами)
# =========================================================

class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    # discussion group
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# =========================================================
# RULES (настройки антиспама)
# =========================================================

class Rule(Base):
    __tablename__ = "rules"

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True
    )

    # фильтры
    filter_links: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_mentions: Mapped[bool] = mapped_column(Boolean, default=False)

    # режим наказания
    action_mode: Mapped[str] = mapped_column(
        String(16),
        default=ActionMode.delete.value
    )

    mute_minutes: Mapped[int] = mapped_column(Integer, default=60)

    # защита
    anti_edit: Mapped[bool] = mapped_column(Boolean, default=False)

    # новичок режим
    newbie_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    newbie_minutes: Mapped[int] = mapped_column(Integer, default=10)

    # логи
    log_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Публичные сообщения Guard раз в N удалений (ТЗ ПРАВКИ 2)
    public_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    public_alerts_every_n: Mapped[int] = mapped_column(Integer, default=5)
    public_alerts_min_interval_sec: Mapped[int] = mapped_column(Integer, default=300)
    public_alerts_style: Mapped[str] = mapped_column(String(16), default="guard")
    public_alerts_last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ТЗ Напоминания: сообщения Guard в группе (по умолчанию раз в 24ч на Free)
    guardian_messages_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    guardian_periodic_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    guardian_periodic_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    last_guardian_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ТЗ Автоматические отчёты: дайджест в чат отчётов раз в сутки
    auto_reports_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_auto_report_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ТЗ доработка Защита: капча на первое сообщение, фильтры (режимы allow/captcha/forbid)
    first_message_captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    filter_links_mode: Mapped[str] = mapped_column(String(32), default="forbid")
    # all = весь чат и комментарии; channel_comments_only = только треды постов канала (для форум-обсуждений)
    filter_links_scope: Mapped[str] = mapped_column(String(32), default="all")
    filter_media_mode: Mapped[str] = mapped_column(String(16), default="allow")
    filter_buttons_mode: Mapped[str] = mapped_column(String(16), default="allow")
    all_captcha_minutes: Mapped[int] = mapped_column(Integer, default=0)
    delete_join_messages: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_left_messages: Mapped[bool] = mapped_column(Boolean, default=True)
    silence_minutes: Mapped[int] = mapped_column(Integer, default=0)
    master_anti_spam: Mapped[bool] = mapped_column(Boolean, default=True)

    # Антинакрутка: оповещение и реакция на массовый вход
    antinakrutka_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    antinakrutka_joins_threshold: Mapped[int] = mapped_column(Integer, default=10)
    antinakrutka_window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    antinakrutka_action: Mapped[str] = mapped_column(String(32), default="alert")  # alert | alert_restrict
    antinakrutka_restrict_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # Всплеск спама: подсветка «чат под угрозой» + уведомления владельцу/делегату.
    spam_spike_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    spam_spike_min_deletes: Mapped[int] = mapped_column(Integer, default=15)
    spam_spike_window_minutes: Mapped[int] = mapped_column(Integer, default=35)
    spam_spike_notify_managers: Mapped[bool] = mapped_column(Boolean, default=True)

    # Антиспам база: проверять вступивших по общей базе пользователей
    use_global_antispam_db: Mapped[bool] = mapped_column(Boolean, default=False)
    # Глобальная база плохих URL: дополнительно к режиму ссылок (или режим allow_except_global)
    use_global_bad_urls: Mapped[bool] = mapped_column(Boolean, default=False)
    # Сообщения от имени каналов/чатов в группе: отдельный фильтр.
    # Если включён, Guard режет sender_chat (кроме доверенных @username из whitelist ниже).
    filter_channel_posts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # delete | ban (банит именно sender_chat в группе, не пользователя).
    filter_channel_posts_action: Mapped[str] = mapped_column(String(16), default="delete")

    # Guard жёсткий словарь: мат / подработки / казино / реклама / обзывательства /
    # антирасист / антифашист / антипошлость
    filter_profanity_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_jobs_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_casino_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_ads_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    filter_insults_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    filter_racism_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    filter_nazi_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    filter_vulgar_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Репутация (карма) за благодарности в группе.
    reputation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Капча при входе в группу (до прохождения проверки)
    join_captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    join_captcha_ttl_minutes: Mapped[int] = mapped_column(Integer, default=3)
    join_captcha_kind: Mapped[str] = mapped_column(String(32), default="button")
    join_captcha_prefer_dm: Mapped[bool] = mapped_column(Boolean, default=False)
    # Приветствие новых участников (по чату).
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON: [[{"text":"...", "url":"..."}], ...]
    welcome_buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Локальный путь до фото приветствия.
    welcome_photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Лимит приветствий: не чаще N сообщений в минуту (0 = без лимита).
    welcome_max_per_min: Mapped[int] = mapped_column(Integer, default=0)
    # Тихий режим при рейде: не отправлять приветствия при массовом входе.
    welcome_silent_on_raid: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_raid_threshold: Mapped[int] = mapped_column(Integer, default=8)
    welcome_raid_window_minutes: Mapped[int] = mapped_column(Integer, default=2)
    # Отправлять приветствие каждому N-му вступившему (1 = каждому).
    welcome_every_n_joins: Mapped[int] = mapped_column(Integer, default=1)

    # Правила: отдельные сценарии для комментариев канала и для группы.
    rules_channel_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rules_channel_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_channel_buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_channel_photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rules_channel_photo_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Окно удаления первых комментариев (сек), чтобы первым оставался комментарий с правилами.
    rules_channel_delete_window_sec: Mapped[int] = mapped_column(Integer, default=0)
    rules_channel_autopost_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON список времени ["09:00", "18:30"] для автопостинга правил в комментарии.
    rules_channel_autopost_times_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    rules_group_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rules_group_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_group_buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_group_photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rules_group_photo_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rules_group_autopost_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON список времени ["10:00", "16:00", "22:00"] для автопостинга правил в группу.
    rules_group_autopost_times_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_group_pin_on_send: Mapped[bool] = mapped_column(Boolean, default=True)
    # После закрепления правил — удалить сервисное «закрепил(а) сообщение» (ручная и автоотправка).
    rules_group_delete_pin_notice: Mapped[bool] = mapped_column(Boolean, default=False)
    # Автоотправка правил в группу после модерации: счётчики «каждые N срабатываний / наказаний».
    rules_group_event_on_trigger: Mapped[bool] = mapped_column(Boolean, default=False)
    rules_group_event_on_punish: Mapped[bool] = mapped_column(Boolean, default=False)
    rules_group_event_trigger_every_n: Mapped[int] = mapped_column(Integer, default=1)
    rules_group_event_punish_every_n: Mapped[int] = mapped_column(Integer, default=1)
    rules_group_event_trigger_acc: Mapped[int] = mapped_column(Integer, default=0)
    rules_group_event_punish_acc: Mapped[int] = mapped_column(Integer, default=0)
    # Какой черновик Mini App (id в post_rules_drafts) «запущен» в Telegram для группы; сам контент в rules_group_*.
    rules_group_active_draft_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# =========================================================
# JOIN CAPTCHA (активная проверка вступившего)
# =========================================================


class JoinCaptchaSession(Base):
    """Одна незавершённая капча: callback по token + проверка user_id нажимающего."""

    __tablename__ = "join_captcha_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    correct_idx: Mapped[int] = mapped_column(Integer, default=0)
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (Index("ix_join_captcha_chat_user", "chat_id", "user_id"),)


# =========================================================
# CHAT SEEN MEMBER (для очистки от удалённых аккаунтов)
# =========================================================

class ChatSeenMember(Base):
    """Участники, которых видели в чате (сообщения или вход). Нужны для проверки на удалённые аккаунты."""
    __tablename__ = "chat_seen_members"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatReputationWord(Base):
    """Кастомные слова благодарности для конкретного чата."""

    __tablename__ = "chat_reputation_words"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    word: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatReputationScore(Base):
    """Накопленная карма пользователя в конкретном чате."""

    __tablename__ = "chat_reputation_scores"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatReputationEvent(Base):
    """События начислений кармы (анти-дубликаты / кулдаун)."""

    __tablename__ = "chat_reputation_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    from_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    to_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# PROFANITY WORDS (общая таблица матерных слов для фильтра)
# =========================================================

class ProfanityWord(Base):
    """Глобальный список матерных слов для фильтрации сообщений."""
    __tablename__ = "profanity_words"

    word: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# GLOBAL ANTISPAM USER (общая база по всем группам бота)
# =========================================================

class GlobalAntispamUser(Base):
    """Глобальный чёрный список пользователей: проверка при вступлении в любую группу."""
    __tablename__ = "global_antispam_users"

    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, primary_key=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# GLOBAL BAD URL (общие запрещённые фрагменты URL для всех чатов с включённой проверкой)
# =========================================================


class GlobalBadUrlPattern(Base):
    """Глобальные шаблоны «плохих» ссылок (подстрока в URL, lowercase в БД). Управляет только полный админ."""

    __tablename__ = "global_bad_url_patterns"
    __table_args__ = (UniqueConstraint("pattern", name="uq_global_bad_url_pattern"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(255), index=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserGlobalBadUrlPattern(Base):
    """Персональная «глобальная» база URL владельца (Telegram id): для всех его чатов с включённой проверкой."""

    __tablename__ = "user_global_bad_url_patterns"
    __table_args__ = (UniqueConstraint("owner_telegram_id", "pattern", name="uq_user_global_bad_url_owner_pattern"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    pattern: Mapped[str] = mapped_column(String(255), index=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# WHITELIST DOMAIN
# =========================================================

class WhitelistDomain(Base):
    __tablename__ = "whitelist_domains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    domain: Mapped[str] = mapped_column(String(255), index=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "domain", name="uq_whitelist_domain"),
    )


# =========================================================
# WHITELIST USERS
# =========================================================

class WhitelistUser(Base):
    __tablename__ = "whitelist_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_whitelist_user"),
    )


# =========================================================
# WHITELIST SENDER CHATS (сообщения от имени каналов/чатов)
# =========================================================
class WhitelistSenderChat(Base):
    __tablename__ = "whitelist_sender_chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_username: Mapped[str] = mapped_column(String(255), index=True)  # lowercase, без @
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("chat_id", "channel_username", name="uq_whitelist_sender_chat"),
    )


# =========================================================
# LINK BLACKLIST (Premium: запрещённые фрагменты URL → бан)
# =========================================================


class LinkBlacklist(Base):
    """Чёрный список фрагментов ссылок для чата (вхождение в URL, без учёта регистра)."""

    __tablename__ = "link_blacklist"
    __table_args__ = (UniqueConstraint("chat_id", "pattern", name="uq_link_blacklist_chat_pattern"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    pattern: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# STOP WORDS
# =========================================================

class StopWord(Base):
    __tablename__ = "stop_words"

    # Integer: в SQLite с BIGINT autoincrement иногда не заполняется id при INSERT.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    word: Mapped[str] = mapped_column(String(64), index=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "word", name="uq_stopword_chat_word"),
    )


# =========================================================
# USER CONTEXT (панель управления)
# =========================================================

class UserContext(Base):
    __tablename__ = "user_context"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    selected_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


# =========================================================
# OWNER JOIN REPORT SETTINGS (дайджест вступлений в группы владельца)
# =========================================================

class OwnerJoinReportSetting(Base):
    __tablename__ = "owner_join_report_settings"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    periods_csv: Mapped[str] = mapped_column(String(64), default="")  # day,3d,week,month (CSV)
    last_sent_day_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_3d_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_week_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_month_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# =========================================================
# CHAT MANAGERS
# =========================================================

class ChatManager(Base):
    __tablename__ = "chat_managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True
    )

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    added_by: Mapped[int] = mapped_column(BigInteger)

    # Делегированные права. Для chat_kind='group' релевантны protection/broadcast/reports.
    # Для chat_kind='channel' релевантны broadcast/first_post_settings.
    can_protection: Mapped[bool] = mapped_column(Boolean, default=False)
    can_broadcast: Mapped[bool] = mapped_column(Boolean, default=False)
    can_reports: Mapped[bool] = mapped_column(Boolean, default=False)
    can_first_post_settings: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_manager"),
    )


# =========================================================
# CHAT MANAGER INVITES (приглашения админов в кабинет чата)
# =========================================================

class ChatManagerInvite(Base):
    __tablename__ = "chat_manager_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True,
    )
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    target_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    target_username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    connected_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="sent")  # sent|connecting|connected

    # Делегированные права (зеркалят ChatManager).
    can_protection: Mapped[bool] = mapped_column(Boolean, default=False)
    can_broadcast: Mapped[bool] = mapped_column(Boolean, default=False)
    can_reports: Mapped[bool] = mapped_column(Boolean, default=False)
    can_first_post_settings: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "owner_user_id", "target_telegram_id", name="uq_chat_manager_invite_tg"),
    )


# =========================================================
# NEW MEMBERS (режим новичка)
# =========================================================

class NewMember(Base):
    __tablename__ = "new_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    joined_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_new_member"),
    )


class MemberLeft(Base):
    """Журнал выходов участников: каждая строка — событие leave/kick."""
    __tablename__ = "member_left"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    left_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_member_left_chat_time", "chat_id", "left_at"),
    )


class ChatActivityEvent(Base):
    """Журнал любой активности (сообщений) для аналитики.

    Пишется в moderation handler по каждому входящему сообщению — независимо от того,
    было ли оно удалено. Используется для подсчёта «всех сообщений» и активных юзеров.
    """
    __tablename__ = "chat_activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_chat_activity_chat_time", "chat_id", "created_at"),
    )


# =========================================================
# AUDIT LOG (история действий бота)
# =========================================================

class ModerationLog(Base):
    __tablename__ = "moderation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    action: Mapped[str] = mapped_column(String(32))

    reason: Mapped[str | None] = mapped_column(String(255))

    # Конкретный триггер: стоп-слово, URL, фрагмент и т.п. (как Verdict.details в лог-чате).
    detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    message_text: Mapped[str | None] = mapped_column(String(2000))

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        Index("idx_modlog_chat", "chat_id"),
    )


# =========================================================
# PROMO CODE (промокоды для активации Premium / пробного периода)
# =========================================================

class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tariff: Mapped[str] = mapped_column(String(32), default=Tariff.PREMIUM.value)  # premium, premium_trial
    days: Mapped[int] = mapped_column(Integer, default=0)  # 0 = бессрочно до явной отмены, 3 = пробный 3 дня
    grant_tokens: Mapped[float] = mapped_column(default=0.0)  # +subscription tokens
    grant_aurum: Mapped[float] = mapped_column(default=0.0)  # +AURUM
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromoCodeRedemption(Base):
    """Один пользователь (telegram_id) — не более одной активации данного промокода."""

    __tablename__ = "promo_code_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_code_id", "telegram_user_id", name="uq_promo_code_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# PAYMENT (история оплат, задел под интеграцию)
# =========================================================

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)

    amount: Mapped[float] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    months: Mapped[int] = mapped_column(Integer)
    tariff: Mapped[str] = mapped_column(String(32))

    status: Mapped[str] = mapped_column(String(32), default="pending")
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CreditLedger(Base):
    """История начислений/списаний кредитов."""
    __tablename__ = "credit_ledger"
    __table_args__ = (
        UniqueConstraint("user_id", "external_key", name="uq_credit_ledger_user_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta: Mapped[float] = mapped_column(nullable=False)  # +начисление / -списание
    reason: Mapped[str] = mapped_column(String(64), default="adjust")
    external_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartnerPayoutRequest(Base):
    """Заявка партнера на вывод средств в RUB."""
    __tablename__ = "partner_payout_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount_rub: Mapped[float] = mapped_column(nullable=False)
    method: Mapped[str] = mapped_column(String(32), default="sbp")
    requisites: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new")  # new|approved|paid|rejected|frozen
    risk_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payout_notice_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PartnerCommission(Base):
    """Начисления по партнерской программе (уровни 1-3)."""
    __tablename__ = "partner_commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    payment_id: Mapped[int] = mapped_column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[float] = mapped_column(nullable=False)
    sales_amount_rub: Mapped[float] = mapped_column(nullable=False)
    reward_amount_rub: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|available|paid|cancelled
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =========================================================
# ADMIN BROADCAST (рассылка постов из админки)
# =========================================================


class AdminBroadcast(Base):
    __tablename__ = "admin_broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    parse_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    keyboard_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_kind: Mapped[str] = mapped_column(String(32), default="none")
    media_local_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    last_target: Mapped[str | None] = mapped_column(String(16), nullable=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    recipient_total: Mapped[int] = mapped_column(Integer, default=0)
    recipient_ok: Mapped[int] = mapped_column(Integer, default=0)
    recipient_fail: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    autopost_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_items: Mapped[list["AdminBroadcastMedia"]] = relationship(
        back_populates="broadcast",
        cascade="all, delete-orphan",
        order_by="AdminBroadcastMedia.id",
    )


class AdminBroadcastMedia(Base):
    __tablename__ = "admin_broadcast_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_broadcasts.id", ondelete="CASCADE"), index=True)
    media_kind: Mapped[str] = mapped_column(String(32), default="photo")
    media_local_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    broadcast: Mapped[AdminBroadcast] = relationship(back_populates="media_items")


class AdminBroadcastDelivery(Base):
    __tablename__ = "admin_broadcast_delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_broadcasts.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    target_kind: Mapped[str] = mapped_column(String(16), default="user", index=True)  # user | group
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AdminBroadcastRun(Base):
    __tablename__ = "admin_broadcast_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_broadcasts.id", ondelete="CASCADE"), index=True)
    target_kind: Mapped[str] = mapped_column(String(16), default="users", index=True)  # users | groups | all
    recipient_total: Mapped[int] = mapped_column(Integer, default=0)
    recipient_ok: Mapped[int] = mapped_column(Integer, default=0)
    recipient_fail: Mapped[int] = mapped_column(Integer, default=0)
    # Реальный охват аудитории в выбранных чатах/каналах (member_count) + users (по 1).
    audience_total: Mapped[int] = mapped_column(Integer, default=0)
    audience_ok: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # manual | autopost


class AdminBroadcastClick(Base):
    __tablename__ = "admin_broadcast_clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_broadcasts.id", ondelete="CASCADE"), index=True)
    target_kind: Mapped[str] = mapped_column(String(16), default="user", index=True)  # user | group
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AutopostCampaign(Base):
    """Независимое расписание автопоста (не привязано к черновику в редакторе)."""

    __tablename__ = "autopost_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # Порядковый номер кампании у владельца на момент создания (1, 2, 3…); не глобальный id
    user_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    # Черновик для filter_autopost_broadcast_refs (ротация); при удалении поста — SET NULL, задайте заново в UI
    anchor_broadcast_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    autopost_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
