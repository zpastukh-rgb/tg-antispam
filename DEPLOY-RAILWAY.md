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

2. Добавь **PostgreSQL** (Add Service → Database → PostgreSQL). В настройках сервиса с БД скопируй переменную `DATABASE_URL` (или сформируй строку вида `postgresql+asyncpg://USER:PASSWORD@HOST:PORT/railway`).

3. В сервисе приложения (не БД) открой **Variables** и задай:
   - `BOT_TOKEN` — токен от @BotFather
   - `DATABASE_URL` — строка подключения к PostgreSQL (Railway подставит свою, если добавил плагин; для asyncpg замени схему на `postgresql+asyncpg://...`).

4. В **Settings** сервиса приложения укажи:
   - **Build Command:** `pip install -r requirements.txt` (или оставь авто)
   - **Start Command:** `python -m app.main`  
   Либо используй **Procfile**: Railway подхватит `worker: python -m app.main` и запустит его как worker.

5. Деплой запустится по push в выбранную ветку.

---

## API (Mini App) на Railway

Если нужен отдельный сервис для API (панель):

1. В том же проекте Railway добавь ещё один сервис из того же репо.
2. В **Settings** этого сервиса задай **Start Command:** `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT`
3. В **Variables** продублируй `BOT_TOKEN` и `DATABASE_URL`.
4. Railway выдаст URL (например `https://xxx.up.railway.app`). Для CORS в API можно задать переменную `CORS_ORIGINS=https://твой-miniapp-url`.

Фронт (webapp) собери отдельно (Vercel, Netlify или статика в другом сервисе) и укажи в нём `VITE_API_BASE_URL` на этот URL.
