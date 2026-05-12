# CHANGELOG

## RU/EN i18n + EN moderation dictionaries

### Что сделано

#### База данных
- Колонка `users.language CHAR(8) NOT NULL DEFAULT 'ru'` в модели `User`.
- Идемпотентная миграция `ensure_users_language_column` подключена в `app/api/main.py` и `app/main.py`.
- Колонка `profanity_words.lang VARCHAR(8) NOT NULL DEFAULT 'any'` в модели `ProfanityWord` +
  миграция `ensure_profanity_lang_column`.

#### Backend i18n
- Новый пакет `app/i18n/` с `t(lang, key, **params)`, `tn(...)` (плюрализация),
  `negotiate_locale(user, tg_code)` и словарями `ru.py`, `en.py`.
- Кэш с TTL `app/services/user_locale.py` — `get_user_language`, `set_user_language`,
  `lang_from_update`, `invalidate`.

#### API
- `GET /api/me` теперь возвращает `language`.
- Новый `PATCH /api/me/language` — валидирует `ru | en`, обновляет БД, инвалидирует кэш.
- Клиент: `api.meSetLanguage(lang)` в `webapp/src/api/client.js`.

#### Frontend
- Установлен `vue-i18n@9` (composition mode).
- `webapp/src/i18n/` с `ru.js`, `en.js`, инициализацией и хелпером `setLocale()`.
- `webapp/src/main.js` подключает i18n.
- `webapp/src/router/index.js` — `meta.titleKey` вместо хардкода.
- `webapp/src/App.vue` синхронизирует язык с `/api/me` при mount.
- `webapp/src/views/SettingsView.vue` `panel='languagePick'`:
  при выборе языка вызывается `api.meSetLanguage`, обновляется `i18n.locale`,
  `<html lang>` и `localStorage`. Тост успеха выводится на новом языке.
- Переведены брендовые/общие компоненты: `AppHeader`, `AppBottomNav`, `AppSidebar`
  (через i18n‑ключи `nav.*`, `common.*`, `app.*`), title‑меты роутов.
- Заголовки и hub `SettingsView` переведены, `panelTitle()` использует i18n.

#### Bot
- `/guard_lang` (`app/handlers/panel_dm.py`) — полноценный выбор RU/EN
  через inline‑клавиатуру и колбэк `p:lang:set:<code>`, сохраняет
  выбор в БД и инвалидирует кэш `user_locale`.
- `app/handlers/start.py` — `/start` выводит локализованный intro
  (`_start_text_for(message)`), banner caption тоже локализован.

#### Moderation EN
- В `app/db/ensure_defaults.py` добавлены `DEFAULT_*_ROOTS_EN` и `DEFAULT_*_ROOTS_FULL`
  для: profanity, racism, nazi, vulgar, politics, religion, esoteric, insult, casino, jobs, ads.
- `app/handlers/moderation.py` импортирует FULL‑группы через `as` — RU‑логика не меняется,
  но evaluate теперь ловит и английские варианты (`fuck`, `nigger`, `nazi`, `porn`, `politic`,
  `religion`, `tarot`, `idiot`, `casino`, `make money fast`, `discount`, …).
- `scripts/seed_profanity.py` — добавлены ключевые EN‑слова в `profanity_words`.
- `app/moderation_lexicon.py` — расширен `GOOD_TOKENS_IGNORE_ALL_ROOTS` нейтральными
  EN‑токенами (assistance, cocktail, prediction, between, …), чтобы EN‑корни не
  ловили бытовые слова.

#### Anti‑mix dev‑скрипты
- `scripts/check_locale_mix.py` — печатает оставшийся RU‑хардкод в `app/**` (кроме
  `app/i18n`, `app/texts`, словарей).
- `webapp/scripts/check_locale_mix.mjs` + npm‑скрипт `npm run check:locale-mix`.

### Ручные e2e‑сценарии (для регрессии)

1. **Новый пользователь EN/RU**
   - С language_code=`ru` — приветствие /start приходит на RU, Mini App открывается на RU.
   - С language_code=`en` (новый пользователь, в БД ещё нет языка) — приветствие /start
     приходит на EN, Mini App открывается на EN сразу.

2. **Переключение в SettingsView**
   - Settings → Profile → «Язык приложения» → выбрать English.
   - В UI сразу меняются `nav.*`, заголовки настроек, тост "Language updated: English".
   - Перезагрузить Mini App — язык остаётся EN (из `users.language`).

3. **Повторный заход в Mini App**
   - Закрыть и заново открыть приложение → язык подтягивается из `/api/me`.

4. **`/start` после смены языка**
   - После выбора EN отправить `/start` в боте — текст приветствия на EN.

5. **Inline callback `cmd_guard_lang`**
   - В личке боту `/guard_lang` → инлайн "Русский / English" → выбрать → текст
     `bot.lang_cmd.saved` на выбранном языке + кэш обновлён.

6. **Inline колбэки panel_dm**
   - Главное меню в боте работает в RU и EN (кнопки берутся через `t(lang, "inline.main_menu.*")` —
     где они подключены; глубокие inline ещё могут быть RU, по `check_locale_mix.py` видно TODO).

7. **Модерация EN‑сообщений** (тестовые сообщения в защищённой группе)
   - Реклама: `Best discount today, link in bio` — фильтр «Реклама/Подработки» срабатывает.
   - Оскорбления: `you are an idiot` — фильтр «Оскорбления» срабатывает.
   - Политика: `the new president sanctions` — фильтр «Анти‑политика» срабатывает.
   - Расизм: `nigger`, `kike` — фильтр «Антирасист» срабатывает.
   - Религия: `church and christianity` — фильтр «Религия» срабатывает.

8. **Регресс RU‑модерации**
   - Старые RU‑сообщения (мат, реклама, политика, оскорбления) — продолжают ловиться.
   - Бытовые EN‑слова (`assistance`, `cocktail`, `prediction`, `between`) НЕ ловятся.

### Известные TODO (следующая итерация)

- Сплошной перевод оставшихся views (DashboardView, ProtectionView, ChatsView,
  ReportsView, BillingView, OwnerCabinet*, AdminView). Архитектура и ключи
  готовы — см. `webapp/src/i18n/ru.js` и `webapp/src/i18n/en.js`.
- Перевод service‑текстов (`reminders`, `public_alerts`, `admin_broadcast`,
  `spam_spike_notify`, …). Бот компилируется и работает на RU; локализация
  inline‑клавиатур делается итеративно через `t(lang, "inline.*")`.
- Расширить `app/texts/bot_intro.py` и `app/texts/guardian_billing.py` так,
  чтобы они стали фасадами над `t()` (сейчас они оставлены без изменений и
  читаются как RU‑фолбэк).
- `panel_dm.show_panel`: внутри ещё много RU‑строк, постепенно мигрируем
  на `t(user_lang, "inline.main_menu.*")`.
