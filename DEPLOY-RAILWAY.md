# Деплой на Railway

## Подключение нового Git-репозитория

В корне проекта (уже с настроенным git):

```bash
# Добавить новый репозиторий как remote (например с именем new)
git remote add new https://github.com/reprobate-music/tg-antispam.git

# Запушить все ветки и теги
git push -u new main
# если основная ветка у тебя master:
# git push -u new master
```

Чтобы **полностью переехать** на новый репо (старый больше не использовать):

```bash
git remote remove origin
git remote rename new origin
git push -u origin main
```

Дальше клонируй уже с нового URL: `git clone https://github.com/reprobate-music/tg-antispam.git`

---

## Railway: бот

1. В [Railway](https://railway.app) создай проект, выбери **Deploy from GitHub repo** и укажи `reprobate-music/tg-antispam`.

2. Добавь **PostgreSQL** (Add Service → Database → PostgreSQL).

3. В сервисе бота открой **Variables**:
   - `BOT_TOKEN` — токен от @BotFather (значение вручную).
   - Подключение к БД — **один из вариантов**:
     - **Reference** `DATABASE_URL` из сервиса PostgreSQL (Add Reference → Postgres → DATABASE_URL). Если после деплоя будет ошибка «Name or service not known», используй вариант ниже.
     - **Надёжный вариант:** добавь по Reference из Postgres переменные **PGHOST**, **PGPORT**, **PGUSER**, **PGPASSWORD**, **PGDATABASE** (те же имена). Код сам соберёт строку подключения из них. Так хост и порт точно подставятся из БД.
   - Не используй в URL переменную **PORT** приложения — только порт БД (5432).

4. В **Settings** сервиса приложения укажи:
   - **Build Command:** `pip install -r requirements.txt` (или оставь авто)
   - **Start Command:** `python -m app.main`  
   Либо используй **Procfile**: Railway подхватит `worker: python -m app.main` и запустит его как worker.

5. Деплой запустится по push в выбранную ветку. Если после `git push` бот не обновился: в Railway открой сервис бота → **Deployments** → убедись, что последний деплой после твоего push; при необходимости нажми **Redeploy** (или включи **Auto Deploy** в Settings).

---

## Запуск миграций БД на Railway

Миграции добавляют новые колонки в таблицы (например, `filter_links_mode`, `master_anti_spam`). Запускать их нужно **один раз** после деплоя или при обновлении кода с новыми миграциями.

### Способ 1: через Railway Dashboard

В сервисе **PostgreSQL** во вкладке **Data** в Railway часто **нет** кнопки Query/Console — встроенный SQL-редактор там не предусмотрен. В этом случае используй **Способ 2 (DBeaver)** или Способ 3 (psql).

### Способ 2: DBeaver (без установки PostgreSQL, только одна программа)

[DBeaver](https://dbeaver.io/download/) — бесплатный клиент для БД (Windows/Mac/Linux). Через него подключаешься к Postgres на Railway и выполняешь SQL из файлов миграций.

1. Установи [DBeaver Community](https://dbeaver.io/download/) (достаточно одной установки).
2. В Railway открой сервис **PostgreSQL** → вкладка **Variables** (или **Connect**). Скопируй **DATABASE_PUBLIC_URL** или **DATABASE_URL**.  
   Если есть только приватный URL — в **Connect** посмотри, есть ли публичный хост/порт для подключения извне; при необходимости включи **Public Networking** / TCP Proxy для Postgres в настройках сервиса.
3. В DBeaver: **База данных** → **Новое подключение** → **PostgreSQL**. Вставь данные из URL:
   - Хост, порт, база, пользователь, пароль — всё есть в строке вида `postgresql://user:password@host:port/railway`.
4. Подключись к базе, затем **SQL Editor** → **New SQL Script** (или Ctrl+]). Вставь содержимое файла `migrations/004_protection_panel_tz.sql` и нажми **Execute** (Ctrl+Enter).
5. Аналогично можно выполнить остальные миграции из папки `migrations/` по очереди.

### Способ 3: с локального компьютера через psql

1. В Railway открой сервис **PostgreSQL** → вкладка **Variables** или **Connect**.
2. Скопируй **DATABASE_URL** или **DATABASE_PUBLIC_URL** (публичный URL нужен для подключения с твоего ПК). Если видишь только приватный URL — в **Connect** иногда есть строка для подключения извне.
3. Установи [psql](https://www.postgresql.org/download/) (или используй уже установленный PostgreSQL).
4. В терминале из **корня проекта** выполни (подставь свой URL в кавычки):

```bash
# Одна миграция (подставь свой URL из Railway)
psql "postgresql://postgres:ПАРОЛЬ@host.railway.app:ПОРТ/railway" -f migrations/004_protection_panel_tz.sql

# Все миграции по порядку (если их несколько)
psql "postgresql://..." -f migrations/001_add_user_and_is_log_chat.sql
psql "postgresql://..." -f migrations/002_public_alerts.sql
psql "postgresql://..." -f migrations/003_reminders_and_guardian_messages.sql
psql "postgresql://..." -f migrations/004_protection_panel_tz.sql
psql "postgresql://..." -f migrations/005_free_tariff_3_chats.sql
```

На Windows в PowerShell URL в кавычках может требовать экранирования; можно задать переменную:

```powershell
$env:DATABASE_URL = "postgresql://postgres:xxx@xxx.railway.app:5432/railway"
Get-Content migrations\004_protection_panel_tz.sql | psql $env:DATABASE_URL
```

### Способ 4: Railway CLI (нужен установленный psql)

Команды `railway run psql ...` и `railway connect` требуют **установленного на твоём ПК клиента PostgreSQL (psql)**. Если видишь ошибку *«psql не является внутренней или внешней командой»* — значит psql не установлен.

**Вариант А — не ставить psql:** выполни миграцию через **Способ 1 (Dashboard)** или **Способ 2**, предварительно скопировав `DATABASE_PUBLIC_URL` из Railway вручную.

**Вариант Б — поставить psql, потом использовать CLI:**

1. Установи [PostgreSQL для Windows](https://www.postgresql.org/download/windows/) (или только [Command Line Tools](https://www.postgresql.org/download/windows/)) и добавь `bin` в PATH.
2. В папке проекта: `railway link` → выбери проект и сервис (бот или Postgres).
3. Выполни (в PowerShell подставь URL вручную, если `$env:DATABASE_URL` пустой):

```powershell
# Сначала скопируй DATABASE_URL из Railway (Postgres → Variables) и подставь ниже
railway run psql $env:DATABASE_URL -f migrations/004_protection_panel_tz.sql
```

Если Railway подставляет переменные в `railway run`, достаточно:

```bash
railway run psql $DATABASE_URL -f migrations/004_protection_panel_tz.sql
```

(На Windows в CMD используй `%DATABASE_URL%` вместо `$DATABASE_URL`.)

### Способ 3b: скрипт в репозитории (Railway run без psql)

В проекте есть скрипт, который выполняет миграцию по номеру. `railway run` подставляет переменные БД из твоего проекта, но **команда выполняется локально** — нужен Python с зависимостями (venv) и **доступный с твоего ПК** URL базы.

1. В папке проекта: **активируй venv**, затем `railway link` — выбери проект и **сервис PostgreSQL** (не бот и не API). Так подставятся переменные с **DATABASE_PUBLIC_URL**, по которому можно подключиться с твоего компьютера. (Если привязать бота/API, часто подставляется только приватный DATABASE_URL — с ПК к нему не подключиться, будет ошибка `getaddrinfo failed`.)
2. Запусти миграцию (в том же терминале, где активирован venv):

```powershell
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
railway run python -m scripts.run_migration 005
```

```bash
# Linux / Mac
source venv/bin/activate
railway run python -m scripts.run_migration 005
```

Если venv ещё нет: `python -m venv venv`, активируй, затем `pip install -r requirements.txt`, после этого команду выше.

Чтобы выполнить несколько миграций подряд:

```bash
railway run python -m scripts.run_migration 001
railway run python -m scripts.run_migration 002
railway run python -m scripts.run_migration 003
railway run python -m scripts.run_migration 004
railway run python -m scripts.run_migration 005
```

Скрипт ищет файл `migrations/<номер>_*.sql` (например, `005_free_tariff_3_chats.sql`) и выполняет его SQL против базы из переменных Railway.

---

## Всё на Railway: бот + API + фронт (3 сервиса)

В одном проекте Railway — три сервиса из одного репозитория: **бот**, **API**, **фронт**.

---

### Сервис 1: Бот (уже есть)

- **Root Directory:** пусто (корень репо).
- **Variables:** `BOT_TOKEN`, ссылки на Postgres: `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`.
- **Start Command:** `python -m app.main` (или через Procfile: `worker: python -m app.main`).

---

### Сервис 2: API (бэкенд для панели)

1. В том же проекте нажми **Add Service** → **GitHub Repo** → выбери тот же репозиторий.
2. **Settings:**
   - **Root Directory:** пусто (корень).
   - **Build Command:** `pip install -r requirements.txt` (или оставь авто).
   - **Start Command:** `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT`
3. **Variables:** те же, что у бота: `BOT_TOKEN` (обязателен — для проверки init data и для ссылки «Добавить бота в группу» во фронте), Reference из Postgres — `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` (или один Reference `DATABASE_URL`).
4. **Settings** → **Networking** → **Generate Domain.** Запомни URL API, например: `https://tg-antispam-api-production-xxxx.up.railway.app`

---

### Сервис 3: Фронт (Mini App)

1. **Add Service** → **GitHub Repo** → тот же репо.
2. **Settings:**
   - **Root Directory:** `webapp` (важно — сборка из папки webapp).
   - **Build Command:** `npm ci && npm run build`
   - **Start Command:** `npx serve -s dist -l $PORT`  
     (флаг `-s` — SPA: все маршруты отдают `index.html`; `$PORT` задаёт Railway.)
3. **Variables:**
   - `VITE_API_BASE_URL` = **URL твоего API** из шага «Сервис 2» (например `https://tg-antispam-api-production-xxxx.up.railway.app`).  
     Эта переменная подставляется при **сборке**, поэтому после первого деплоя API нужно прописать сюда реальный URL и заново задеплоить фронт.
4. **Networking** → **Generate Domain.** Это и есть URL Mini App для BotFather и для кнопки в боте.

---

### Порядок и проверка

1. Задеплой **API** (сервис 2), сгенерируй домен, скопируй URL.
2. В сервисе **фронта** (3) задай `VITE_API_BASE_URL` = URL API, сохрани, задеплой фронт.
3. В **BotFather** → твой бот → Bot Settings → Menu Button или Configure Mini App — укажи URL фронта (домен сервиса 3).
4. В боте добавь кнопку/команду, открывающую этот URL (Mini App). При открытии из Telegram в запросы попадёт `initData`, API сможет авторизовать пользователя.

**CORS:** в API по умолчанию `CORS_ORIGINS=*`. Если захочешь ограничить доменом фронта, в сервисе API добавь переменную `CORS_ORIGINS=https://твой-фронт-url.up.railway.app`.

---

## Как добавить ссылку на фронт (Mini App) в BotFather

Нужен **публичный HTTPS-URL** твоего фронта (сервис 3 на Railway), например:  
`https://tg-antispam-web-production-xxxx.up.railway.app`

### Вариант 1: Кнопка меню (Menu Button)

При открытии чата с ботом под полем ввода можно показать кнопку, которая открывает Mini App.

1. Открой [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправь команду **`/mybots`**.
3. Выбери своего бота из списка.
4. Нажми **Bot Settings** (Настройки бота).
5. Выбери **Menu Button** (Кнопка меню).
6. Выбери **Configure menu button** (Настроить кнопку меню).
7. **BotFather попросит URL** — отправь ссылку на фронт **одной строкой**, без пробелов, например:
   ```
   https://tg-antispam-web-production-xxxx.up.railway.app
   ```
8. При необходимости BotFather попросит текст кнопки — можно написать, например: **«Открыть панель»** или **«Панель управления»**.

После этого в чате с ботом под полем ввода появится кнопка (часто синяя «Web App» / «Открыть»), по нажатию откроется твой фронт в Mini App.

---

### Вариант 2: Команда /panel в боте

У тебя уже есть команда в коде (например `/panel` или через `/start`). Можно оставить команду, которая **отправляет пользователю кнопку** с ссылкой на Mini App (InlineKeyboard с `WebAppInfo`). Тогда пользователь нажимает кнопку и открывается фронт. В этом случае в BotFather **не обязательно** настраивать Menu Button — достаточно, чтобы в боте по команде показывалась кнопка с твоим URL.  
Если хочешь, чтобы панель открывалась ещё и **главной кнопкой под полем ввода** — настрой Menu Button по варианту 1.

---

### Вариант 3: Описание и ссылка в профиле бота

В BotFather: **Bot Settings** → **Edit Bot Description** / **Edit About** — в описание можно добавить текст вроде: «Панель: https://твой-фронт.up.railway.app». Это не открывает Mini App автоматически, но даёт пользователю ссылку. Для полноценного Mini App лучше использовать вариант 1 или кнопку в чате (вариант 2).

---

**Итог:** быстрее всего — в BotFather: **Menu Button** → **Configure** → вставить URL фронта (Railway, сервис 3). Тогда у пользователей в чате с ботом появится кнопка для открытия панели.
