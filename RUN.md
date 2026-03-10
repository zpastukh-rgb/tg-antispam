# Как запустить проект по шагам

## 0. Виртуальное окружение (рекомендуется на Windows)

Чтобы не было ошибок вида `Could not install packages due to an OSError` (блокировка файлов в системном Python), используй **venv** — зависимости поставятся в папку проекта.

В корне проекта выполни **один раз**:

**PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Git Bash / MINGW64:**
```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
```

Если в PowerShell ругается на выполнение скриптов: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`, затем снова `.\venv\Scripts\Activate.ps1`.

Дальше в этом же терминале (или в новых — в Git Bash снова вызывай `source venv/Scripts/activate`, в PowerShell — `.\venv\Scripts\Activate.ps1`) запускай бота и API. В начале строки должно быть `(venv)`.

---

## 1. База данных (PostgreSQL)

**Вариант A — через Docker (проще всего):**

```bash
docker compose up -d postgres
```

Дождись запуска контейнера. БД будет на `localhost:5432`.

**Вариант B — локальный PostgreSQL:**  
Создай БД и пользователя, затем в `.env` укажи:

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/DBNAME
```

---

## 2. Переменные окружения

В корне проекта нужен файл **`.env`** (или используй **`.env.docker`** для Docker-бота) с переменными:

- `BOT_TOKEN` — токен бота от @BotFather  
- `DATABASE_URL` — строка подключения к PostgreSQL  

Для **локального** запуска (не Docker) в `.env` укажи БД так:

```
BOT_TOKEN=твой_токен_бота
DATABASE_URL=postgresql+asyncpg://antispam_user:antispam_pass@localhost:5432/antispam
```

Если БД в Docker, а бот запускаешь на хосте — хост БД будет `localhost`. Если и бот в Docker — в `.env.docker` оставь `@postgres:5432`.

---

## 3. Миграции БД (если таблиц ещё нет)

Один раз применить миграции:

**Windows (PowerShell):**

```powershell
Get-Content "migrations\001_add_user_and_is_log_chat.sql" | docker compose exec -T postgres psql -U antispam_user -d antispam
Get-Content "migrations\002_public_alerts.sql" | docker compose exec -T postgres psql -U antispam_user -d antispam
Get-Content "migrations\003_reminders_and_guardian_messages.sql" | docker compose exec -T postgres psql -U antispam_user -d antispam
Get-Content "migrations\004_protection_panel_tz.sql" | docker compose exec -T postgres psql -U antispam_user -d antispam
```

**macOS / Linux:**

```bash
for f in migrations/00*.sql; do docker compose exec -T postgres psql -U antispam_user -d antispam < "$f"; done
```

Если PostgreSQL не в Docker — выполняй SQL через свой клиент (`psql` или GUI), подставляя свои учётные данные.

---

## 4. Запуск бота

**Через Docker:**

```bash
docker compose up -d bot
```

**Локально (из корня проекта):**

Сначала активируй venv (см. шаг 0), затем:

```bash
python -m app.main
```

Бот начнёт polling. В логах должно быть что-то вроде: «AntiSpam Guardian запущен».

---

## 5. Запуск API (для Mini App)

API нужен, чтобы панель (webapp) получала данные. Запускается **отдельно** от бота.

В корне проекта (с активированным venv — шаг 0):

```bash
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Проверка: открой в браузере `http://localhost:8000/api/health` — должен вернуться `{"status":"ok"}`.

---

## 6. Запуск фронта (Mini App / админка)

Открой **второй** терминал, перейди в каталог webapp:

```bash
cd webapp
npm install
npm run dev
```

Откроется, например, `http://localhost:5173`.

Чтобы фронт ходил в твой API, в каталоге `webapp` создай файл **`.env`**:

```
VITE_API_BASE_URL=http://localhost:8000
```

Перезапусти `npm run dev` после создания или изменения `.env`.

---

## 7. Итог: что у тебя запущено

| Сервис        | Команда / способ              | Порт / где        |
|---------------|-------------------------------|-------------------|
| PostgreSQL    | `docker compose up -d postgres` | 5432              |
| Бот           | `python -m app.main` или Docker | —                 |
| API           | `uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000` | 8000  |
| Фронт (панель)| `cd webapp && npm run dev`    | 5173 (Vite)       |

---

## 8. Проверка Mini App в Telegram

1. В @BotFather настрой Mini App: укажи URL страницы, где открывается панель (после деплоя по HTTPS).  
2. В боте добавь кнопку или команду, которая открывает этот URL (например, через `WebAppInfo`).  
3. Открывай панель из Telegram — тогда в запросы попадёт `initData`, и API сможет авторизовать пользователя.

Для локальной проверки без Telegram можно в URL панели добавить тестовый параметр, но полная авторизация работает только при открытии из бота (с настоящим `initData`).
