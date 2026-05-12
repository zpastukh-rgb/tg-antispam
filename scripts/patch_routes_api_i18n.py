#!/usr/bin/env python3
"""One-shot: replace Russian HTTPException detail strings with err_detail(...) in routes.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "app" / "api" / "routes.py"

# (old, new) — longer olds first where relevant
REPLACEMENTS: list[tuple[str, str]] = [
    (
        'detail=f"Недостаточно AURUM: нужно {amount:g} ✨, у вас {round(s_bal, 2)} ✨"',
        'detail=err_detail("aurum_insufficient", need=f"{amount:g}", have=f"{round(s_bal, 2)}")',
    ),
    (
        'detail=f"Не более {USER_GLOBAL_BAD_URL_MAX} шаблонов в личной базе"',
        'detail=err_detail("user_global_url_limit", max=USER_GLOBAL_BAD_URL_MAX)',
    ),
    (
        'detail=f"Лимит доверенных ссылок для этого чата: {max_d}. С Premium у владельца — до 100."',
        'detail=err_detail("trusted_domain_limit", max_d=max_d)',
    ),
    (
        'detail=f"Лимит доверенных пользователей: {max_u}. Premium у владельца — до 100."',
        'detail=err_detail("trusted_user_limit", max_u=max_u)',
    ),
    (
        'detail=f"Лимит чёрного списка: {max_bl} записей."',
        'detail=err_detail("link_blacklist_limit", max_bl=max_bl)',
    ),
    (
        'detail=f"Минимальная сумма вывода {_PARTNER_PAYOUT_MIN_RUB:.0f} ₽"',
        'detail=err_detail("partner_payout_min", min_rub=f"{_PARTNER_PAYOUT_MIN_RUB:.0f}")',
    ),
    (
        'detail=f"Не удалось обработать изображение: {e}"',
        'detail=err_detail("image_process_failed", error=str(e))',
    ),
    (
        'detail="Нельзя пригласить: пользователь не распознан. Нужен действующий Telegram ID или @username пользователя, который уже запускал Guard."',
        'detail=err_detail("invite_unrecognized")',
    ),
    (
        'detail="Пользователь не найден в Guard. Пусть сначала запустит бота (/start), затем повторите приглашение."',
        'detail=err_detail("invite_user_start_first")',
    ),
    (
        'detail="Черновики слишком объёмные: сократите текст или удалите встроенные изображения из шаблонов."',
        'detail=err_detail("drafts_too_large")',
    ),
    (
        'detail="Не удалось распознать пользователя. Укажите Telegram ID или @username (пользователь должен хотя бы раз запустить Guard)."',
        'detail=err_detail("trusted_user_resolve_failed")',
    ),
    (
        'detail="Нужен Premium, полный доступ администратора или менеджерство в чужом чате"',
        'detail=err_detail("premium_admin_or_manager")',
    ),
    (
        'detail="Нужен Premium или полный доступ администратора"',
        'detail=err_detail("premium_or_admin")',
    ),
    (
        'detail=str(e) or "Ошибка платёжной системы"',
        'detail=str(e) or err_detail("payment_provider_error")',
    ),
]

SIMPLE: list[tuple[str, str]] = [
    ('detail="Требуются accept_bundle и accept_pd"', 'detail=err_detail("accept_bundle_pd")'),
    ('detail="Укажите другой Telegram id менеджера"', 'detail=err_detail("manager_other_tid")'),
    ('detail="Сумма от 0.01 до 1 000 000 000 AURUM"', 'detail=err_detail("aurum_amount_range")'),
    ('detail="Пользователь не найден среди менеджеров ваших чатов"', 'detail=err_detail("manager_not_in_list")'),
    ('detail="Некорректный шаблон. Примеры: evil.com, t.me/spam_channel"', 'detail=err_detail("url_template_invalid")'),
    ('detail="Шаблон уже в вашей базе"', 'detail=err_detail("user_url_template_duplicate")'),
    ('detail="Функция доступна только на Premium"', 'detail=err_detail("premium_only")'),
    ('detail="Выберите хотя бы одно право для админа."', 'detail=err_detail("admin_pick_right")'),
    (
        'detail="Пользователь не админ в этом чате/канале. Сначала выдайте ему админку в Telegram."',
        'detail=err_detail("invite_target_not_tg_admin")',
    ),
    ('detail="Для этого чата нужен Premium"', 'detail=err_detail("chat_needs_premium")'),
    ('detail="Нужен image-файл"', 'detail=err_detail("need_image_file")'),
    ('detail="Пустой файл"', 'detail=err_detail("empty_file")'),
    ('detail="Файл слишком большой (до 8MB)"', 'detail=err_detail("file_too_big_8mb")'),
    ('detail="Файл слишком большой (до 20MB)"', 'detail=err_detail("file_too_big_20mb")'),
    ('detail="Изображение слишком тяжелое после обработки"', 'detail=err_detail("image_too_heavy_after_process")'),
    ('detail="Некорректный чат"', 'detail=err_detail("invalid_chat")'),
    (
        'detail="Не удалось выполнить разбан в Telegram (права бота или пользователь не в бане)."',
        'detail=err_detail("telegram_unban_failed")',
    ),
    (
        'detail="Не удалось снять ограничения в Telegram (права бота или статус участника)."',
        'detail=err_detail("telegram_unrestrict_failed")',
    ),
    (
        'detail="target должен быть group или channel_comments"',
        'detail=err_detail("rules_target_type_invalid")',
    ),
    ('detail="Текст правил для группы пуст"', 'detail=err_detail("rules_group_text_empty")'),
    ('detail="Текст правил для комментариев пуст"', 'detail=err_detail("rules_comments_text_empty")'),
    (
        'detail="message_thread_id обязателен для channel_comments"',
        'detail=err_detail("message_thread_required")',
    ),
    ('detail="Не удалось отправить правила в Telegram"', 'detail=err_detail("rules_telegram_send_failed")'),
    (
        'detail="Некорректная запись. Примеры: vk.com, youtube.com, t.me/your_channel"',
        'detail=err_detail("trusted_domain_invalid")',
    ),
    ('detail="Домен уже в списке"', 'detail=err_detail("trusted_domain_duplicate")'),
    ('detail="Пользователь уже в списке"', 'detail=err_detail("trusted_user_duplicate")'),
    ('detail="Некорректный target_user_id"', 'detail=err_detail("target_user_id_invalid")'),
    ('detail="Нужен @username канала"', 'detail=err_detail("channel_username_required")'),
    ('detail="Некорректный @username канала"', 'detail=err_detail("channel_username_invalid")'),
    ('detail="Канал уже в доверенных"', 'detail=err_detail("trusted_channel_duplicate")'),
    ('detail="Некорректный channel_username"', 'detail=err_detail("channel_username_bad")'),
    (
        'detail="Чёрный список ссылок доступен только при Premium у владельца чата."',
        'detail=err_detail("link_blacklist_premium_only")',
    ),
    (
        'detail="Некорректный фрагмент. Примеры: spam.com, t.me/spam_channel"',
        'detail=err_detail("link_blacklist_fragment_invalid")',
    ),
    ('detail="Уже в списке"', 'detail=err_detail("link_blacklist_duplicate")'),
    ('detail="Укажите реквизиты для выплаты"', 'detail=err_detail("partner_payout_details_required")'),
    ('detail="Недостаточно доступного баланса"', 'detail=err_detail("partner_balance_insufficient")'),
    ('detail="Недопустимый статус"', 'detail=err_detail("partner_invalid_status")'),
    ('detail="Заявка не найдена"', 'detail=err_detail("partner_request_not_found")'),
    (
        'detail="scope=all: недостаточно прав (доступны только ваши группы)"',
        'detail=err_detail("scope_all_chats_forbidden")',
    ),
    ('detail="scope=all: недостаточно прав"', 'detail=err_detail("scope_all_forbidden")'),
    ('detail="Нет доступа"', 'detail=err_detail("access_denied")'),
    ('detail="Неизвестное действие"', 'detail=err_detail("unknown_action")'),
    ('detail="Пользователь не найден"', 'detail=err_detail("user_not_found")'),
    ('detail="Нет доступа к чату"', 'detail=err_detail("no_chat_access")'),
    (
        'detail="Некорректный период: начало позже конца"',
        'detail=err_detail("period_start_after_end")',
    ),
    ('detail="Период не более 400 суток"', 'detail=err_detail("period_max_400_days")'),
    ('detail="Нужны корректные from_ts и to_ts"', 'detail=err_detail("analytics_ts_invalid")'),
    (
        'detail="Интервал не более ~49 часов для детализации"',
        'detail=err_detail("analytics_interval_max_hours")',
    ),
    ('detail="Введите корректный email"', 'detail=err_detail("email_invalid")'),
    ('detail="Платеж не найден"', 'detail=err_detail("payment_not_found")'),
    (
        'detail="Сервис отправки чеков на email временно недоступен"',
        'detail=err_detail("receipt_email_unavailable")',
    ),
    ('detail="Не удалось отправить чек"', 'detail=err_detail("receipt_send_failed")'),
    ('detail="Платежи не настроены"', 'detail=err_detail("payments_not_configured")'),
    ('detail="Недопустимый период"', 'detail=err_detail("invalid_subscription_period")'),
    ('detail="Тестовая оплата недоступна"', 'detail=err_detail("test_payment_forbidden")'),
    (
        'detail="Токены доступны только при активной подписке"',
        'detail=err_detail("tokens_need_active_subscription")',
    ),
    ('detail="Недопустимый пакет токенов"', 'detail=err_detail("invalid_token_pack")'),
    ('detail="Нет доступа к этому посту"', 'detail=err_detail("no_access_to_post")'),
    (
        'detail="Укажите anchor_broadcast_id — черновик для ротации постов в кампании"',
        'detail=err_detail("anchor_broadcast_required")',
    ),
    ('detail="Черновик не найден или недоступен"', 'detail=err_detail("draft_not_found_or_denied")'),
    (
        'detail="Сначала задайте anchor_broadcast_id (якорный черновик для ротации)"',
        'detail=err_detail("set_anchor_first")',
    ),
    (
        'detail="Сначала остановите автопост кампании (runState: stopped)"',
        'detail=err_detail("stop_autopost_first")',
    ),
    (
        'detail="Нельзя менять шаблон во время активной рассылки"',
        'detail=err_detail("cannot_change_template_active_send")',
    ),
    (
        'detail="Нельзя менять медиа во время активной рассылки"',
        'detail=err_detail("cannot_change_media_active_send")',
    ),
    ('detail="Файл слишком большой"', 'detail=err_detail("file_too_large")'),
    (
        'detail="GIF отключены. Используйте PNG/JPEG/MP4/MP3 и другие поддерживаемые форматы."',
        'detail=err_detail("gif_disabled")',
    ),
    ('detail="Файл не найден"', 'detail=err_detail("attach_not_found")'),
    (
        'detail="Нельзя удалить во время активной рассылки"',
        'detail=err_detail("cannot_delete_during_active_send")',
    ),
    ('detail="Недопустимый тип отправки"', 'detail=err_detail("invalid_send_type")'),
    (
        'detail="Для Premium доступна рассылка только в ваши группы (не в личку и не «всё»)."',
        'detail=err_detail("premium_broadcast_groups_only")',
    ),
    (
        'detail="Неверные id чатов: для групп укажите chat_id супергруппы (обычно отрицательное число)"',
        'detail=err_detail("invalid_group_chat_ids")',
    ),
    (
        'detail="Нет групп для отправки (проверьте выбор или подключите группу к боту)"',
        'detail=err_detail("no_groups_to_send")',
    ),
    ('detail="Рассылка уже выполняется"', 'detail=err_detail("broadcast_already_running")'),
    ('detail="Нужен текст или загруженное медиа"', 'detail=err_detail("need_text_or_media")'),
    ('detail="BOT_TOKEN не задан"', 'detail=err_detail("bot_token_not_configured")'),
    ('detail="Шаблон уже в базе"', 'detail=err_detail("admin_global_template_duplicate")'),
]

ALL = REPLACEMENTS + SIMPLE


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if "err_detail(" in text and 'from app.api.api_locale import err_detail' in text:
        pass
    for old, new in sorted(ALL, key=lambda x: -len(x[0])):
        if old not in text:
            print("SKIP (missing):", old[:70])
            continue
        text = text.replace(old, new)
    PATH.write_text(text, encoding="utf-8")
    print("OK", PATH)


if __name__ == "__main__":
    main()
