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

5. Деплой запустится по push в выбранную ветку.

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
3. **Variables:** те же, что у бота: `BOT_TOKEN`, Reference из Postgres — `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` (или один Reference `DATABASE_URL`).
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
