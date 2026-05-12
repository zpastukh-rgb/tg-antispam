# app/i18n/http_api_ui.py
"""Тексты Mini App API (JSON/DM), ключи api.ui.* — RU/EN."""

from __future__ import annotations

RU: dict[str, str] = {
    "service_starting": "Сервис запускается",
    "spike_rec_no_rule_1": "Включите режим новичков.",
    "spike_rec_no_rule_2": "Включите режим тишины после входа.",
    "spike_rec_no_rule_3": "Проверьте наказание: delete/mute/ban.",
    "spike_rec_newbie": "Включите режим новичков (усиление первых сообщений).",
    "spike_rec_silence": "Задайте режим тишины после вступления.",
    "spike_rec_captcha": "Включите капчу на первое сообщение.",
    "spike_rec_antinakrutka": "Включите антинакрутку на массовые входы.",
    "spike_rec_fallback": "Проверьте пороги стоп-слов, ссылок и медиа-фильтра.",
    "partner_risk_large_amount": "Большая сумма для ручной проверки",
    "partner_risk_incomplete_requisites": "Неполные реквизиты",
    "partner_risk_duplicate_requisites": "Реквизиты уже использовались другим аккаунтом",
    "partner_dm_payout_submitted": (
        "📨 Заявка на вывод принята.\n\n"
        "Сумма: {amount} ₽\n"
        "Статус: на рассмотрении.\n"
        "Ориентир выплаты: следующий понедельник ({monday}).\n"
        "Мы уведомим вас после обработки."
    ),
    "partner_dm_payout_paid": (
        "✅ Выплата одобрена и переведена.\n\n"
        "Сумма: {amount} ₽\n"
        "Осталось к выводу: {remaining} ₽\n\n"
        "Проверьте поступление средств по вашим реквизитам."
    ),
    "partner_kb_open_partner": "Открыть партнёрку",
    "tmpl_event_manual": "Ручной (только хранение/редактирование)",
    "tmpl_event_owner_daily_report": "Суточная сводка владельцу",
    "tmpl_event_window_group_joins": "Вступления в группы (окно)",
    "tmpl_event_window_starts": "Нажали /start (окно)",
    "tmpl_event_window_payments": "Оплаты (окно)",
    "tmpl_event_window_referral_shares": "Шеры рефералки (окно)",
    "tmpl_target_owner_admin": "Владелец/админ в личку",
    "ops_diag_db_slow": "База данных отвечает медленно — возможна нехватка ресурсов.",
    "ops_diag_payouts": "Много открытых заявок на выплаты — проверьте обработку выплат.",
    "ops_diag_moderation": "Сильный всплеск модерации — возможна атака/рейд в чатах.",
    "ops_diag_rw_token": (
        "Guard Pulse / перезапуск: создайте токен в Railway → Account → Tokens, "
        "добавьте в сервис API переменную RAILWAY_API_TOKEN (или RAILWAY_TOKEN). См. DEPLOY-RAILWAY.md."
    ),
    "ops_diag_rw_env": (
        "Guard Pulse / перезапуск: нет RAILWAY_ENVIRONMENT_ID (на Railway он обычно приходит сам; "
        "локально задайте вручную или смотрите DEPLOY-RAILWAY.md)."
    ),
    "ops_diag_rw_services": (
        "Guard Pulse / перезапуск: задайте UUID сервисов RAILWAY_SERVICE_ID_BOT, "
        "RAILWAY_SERVICE_ID_API, RAILWAY_SERVICE_ID_WEBAPP (Settings → service → ID). См. DEPLOY-RAILWAY.md."
    ),
    "ops_diag_ok": "Система работает стабильно. Критичных отклонений не обнаружено.",
    "referral_access_months": "{months} мес.",
    "referral_access_no_period": "без активного периода",
    "promo_purpose_with_days": "Активация {tariff} на {days} дн.",
    "promo_purpose_no_expiry": "Активация {tariff} без срока",
    "manager_invite_dm": (
        "✅ Вас добавили админом в кабинет Guard.\n\n"
        "Откройте Mini App и перейдите в «Подключённые чаты» → «Доступы»."
    ),
    "manager_invite_open_access": "🛡 Открыть доступы Guard",
    "rules_draft_template_default": "Шаблон",
    "channel_rule_draft_default": "Черновик",
    "activity_risk_ok": "в норме",
    "activity_risk_moderate": "умеренно",
    "activity_risk_attack": "группа под нагрузкой",
    "activity_bar_scale_note_a": (
        "100% = максимум событий в одном слоте выбранного периода (не лимит Telegram)."
    ),
    "activity_bar_scale_note_b": (
        "100% полоски = самый загруженный слот в выбранном периоде (относительная шкала, не лимит Telegram)."
    ),
    "mod_cat_links": "Ссылки",
    "mod_cat_media": "Медиа / стикеры",
    "mod_cat_buttons": "Сообщения с кнопками",
    "mod_cat_mentions": "Упоминания",
    "mod_cat_stopwords": "Стоп-слова",
    "mod_cat_profanity": "Мат (словарь)",
    "mod_cat_jobs": "Подработки",
    "mod_cat_casino": "Казино / ставки",
    "mod_cat_politics": "Анти-политика",
    "mod_cat_religion": "Религия",
    "mod_cat_esoteric": "Эзотерика / магия",
    "mod_cat_silence": "Режим тишины",
    "mod_cat_newbie_mode": "Срабатывания для новичков",
    "mod_cat_antinakrutka": "Антинакрутка",
    "mod_cat_global_antispam": "Глобальная антиспам база",
    "mod_cat_note_not_in_stats": "События не пишутся в эту статистику",
    "session_device_default": "Устройство",
    "receipt_email_subject": "Чек оплаты Guard",
    "receipt_user_fallback": "Пользователь",
    "receipt_email_body": (
        "Чек оплаты Guard\n\n"
        "Покупатель: {fio}\n"
        "Дата: {created}\n"
        "Сумма: {amount:.2f} RUB\n"
        "Период: {months} мес.\n"
        "Способ оплаты: {provider}\n"
        "ID платежа: {pay_ext}\n"
    ),
    "yookassa_cap_hint_not_configured": "Платежи для этого режима не настроены.",
    "yookassa_cap_hint_recurring_env": "Recurring отмечен как включённый в настройках окружения.",
    "yookassa_cap_hint_observed": "Обнаружены успешные привязки карты в базе.",
    "yookassa_cap_hint_unknown": (
        "Привязки пока не наблюдались. Если LIVE ругается на recurring — подключите у YooMoney менеджера."
    ),
    "broadcast_click_button": "Кнопка",
    "broadcast_click_button_n": "Кнопка #{n}",
    "autopost_campaign_default_title": "Кампания {seq}",
    "token_pack_tag_popular": "Популярно",
    "token_pack_tag_value": "Выгодно",
    "token_pack_savings": "Экономия {saved} ₽",
}

EN: dict[str, str] = {
    "service_starting": "Service is starting",
    "spike_rec_no_rule_1": "Enable newbie mode.",
    "spike_rec_no_rule_2": "Enable post-join silence mode.",
    "spike_rec_no_rule_3": "Check punishment mode: delete/mute/ban.",
    "spike_rec_newbie": "Enable newbie mode (stronger checks on first messages).",
    "spike_rec_silence": "Set post-join silence mode.",
    "spike_rec_captcha": "Enable captcha on the first message.",
    "spike_rec_antinakrutka": "Enable anti-farm for mass joins.",
    "spike_rec_fallback": "Review stop-word, link, and media filter thresholds.",
    "partner_risk_large_amount": "Large amount — manual review",
    "partner_risk_incomplete_requisites": "Incomplete payout details",
    "partner_risk_duplicate_requisites": "These details were already used by another account",
    "partner_dm_payout_submitted": (
        "📨 Payout request received.\n\n"
        "Amount: {amount} ₽\n"
        "Status: under review.\n"
        "Target payout: next Monday ({monday}).\n"
        "We will notify you when it is processed."
    ),
    "partner_dm_payout_paid": (
        "✅ Payout approved and sent.\n\n"
        "Amount: {amount} ₽\n"
        "Still available to withdraw: {remaining} ₽\n\n"
        "Please check your payout method for the transfer."
    ),
    "partner_kb_open_partner": "Open partner dashboard",
    "tmpl_event_manual": "Manual (store/edit only)",
    "tmpl_event_owner_daily_report": "Daily owner summary",
    "tmpl_event_window_group_joins": "Group joins (window)",
    "tmpl_event_window_starts": "/start taps (window)",
    "tmpl_event_window_payments": "Payments (window)",
    "tmpl_event_window_referral_shares": "Referral shares (window)",
    "tmpl_target_owner_admin": "Owner/admin in DM",
    "ops_diag_db_slow": "Database is slow — possible resource pressure.",
    "ops_diag_payouts": "Many open payout requests — check payout processing.",
    "ops_diag_moderation": "Heavy moderation spike — possible raid or attack in chats.",
    "ops_diag_rw_token": (
        "Guard Pulse / redeploy: create a token in Railway → Account → Tokens, "
        "set RAILWAY_API_TOKEN (or RAILWAY_TOKEN) on the API service. See DEPLOY-RAILWAY.md."
    ),
    "ops_diag_rw_env": (
        "Guard Pulse / redeploy: RAILWAY_ENVIRONMENT_ID is missing (Railway usually injects it; "
        "set locally or see DEPLOY-RAILWAY.md)."
    ),
    "ops_diag_rw_services": (
        "Guard Pulse / redeploy: set RAILWAY_SERVICE_ID_BOT, RAILWAY_SERVICE_ID_API, "
        "RAILWAY_SERVICE_ID_WEBAPP (Settings → service → ID). See DEPLOY-RAILWAY.md."
    ),
    "ops_diag_ok": "System looks healthy. No critical anomalies detected.",
    "referral_access_months": "{months} mo.",
    "referral_access_no_period": "no active period",
    "promo_purpose_with_days": "{tariff} activated for {days} days",
    "promo_purpose_no_expiry": "{tariff} activated with no fixed end date",
    "manager_invite_dm": (
        "✅ You were added as admin in the Guard dashboard.\n\n"
        "Open the Mini App and go to Connected chats → Access."
    ),
    "manager_invite_open_access": "🛡 Open Guard access",
    "rules_draft_template_default": "Template",
    "channel_rule_draft_default": "Draft",
    "activity_risk_ok": "healthy",
    "activity_risk_moderate": "moderate",
    "activity_risk_attack": "under load",
    "activity_bar_scale_note_a": (
        "100% = max events in a single slot for the selected period (not a Telegram limit)."
    ),
    "activity_bar_scale_note_b": (
        "100% bar length = busiest slot in the selected period (relative scale, not a Telegram limit)."
    ),
    "mod_cat_links": "Links",
    "mod_cat_media": "Media / stickers",
    "mod_cat_buttons": "Messages with buttons",
    "mod_cat_mentions": "Mentions",
    "mod_cat_stopwords": "Stop words",
    "mod_cat_profanity": "Profanity (dictionary)",
    "mod_cat_jobs": "Job spam",
    "mod_cat_casino": "Gambling / betting",
    "mod_cat_politics": "Anti-politics filter",
    "mod_cat_religion": "Religion",
    "mod_cat_esoteric": "Esoterics / magic",
    "mod_cat_silence": "Silence mode",
    "mod_cat_newbie_mode": "Newbie-mode hits",
    "mod_cat_antinakrutka": "Anti-farm (mass joins)",
    "mod_cat_global_antispam": "Global antispam database",
    "mod_cat_note_not_in_stats": "Events are not written into this statistic",
    "session_device_default": "Device",
    "receipt_email_subject": "Guard payment receipt",
    "receipt_user_fallback": "Customer",
    "receipt_email_body": (
        "Guard payment receipt\n\n"
        "Customer: {fio}\n"
        "Date: {created}\n"
        "Amount: {amount:.2f} RUB\n"
        "Period: {months} mo.\n"
        "Payment method: {provider}\n"
        "Payment ID: {pay_ext}\n"
    ),
    "yookassa_cap_hint_not_configured": "Payments are not configured for this mode.",
    "yookassa_cap_hint_recurring_env": "Recurring is marked enabled in environment settings.",
    "yookassa_cap_hint_observed": "Successful card bindings were observed in the database.",
    "yookassa_cap_hint_unknown": (
        "No bindings observed yet. If LIVE complains about recurring, ask your YooMoney account manager."
    ),
    "broadcast_click_button": "Button",
    "broadcast_click_button_n": "Button #{n}",
    "autopost_campaign_default_title": "Campaign {seq}",
    "token_pack_tag_popular": "Popular",
    "token_pack_tag_value": "Best value",
    "token_pack_savings": "Save {saved} ₽",
}
