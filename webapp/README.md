# AntiSpam Guardian — Mini App (админ-панель)

Vue 3 + Vite + Tailwind CSS. Адаптивная панель с сайдбаром, сменой темы и разделами бота. Данные загружаются с бэкенд-API по заголовку `X-Telegram-Init-Data`.

## Запуск

```bash
npm install
npm run dev   # разработка
npm run build # сборка в dist/
npm run preview # просмотр собранного
```

## Подключение к API

Бэкенд API запускается отдельно (из корня проекта):

```bash
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Для локальной разработки, если фронт на другом порту, создайте в `webapp/` файл `.env`:

```
VITE_API_BASE_URL=http://localhost:8000
```

В Telegram Mini App initData передаётся автоматически; при открытии не из Telegram данные не будут загружаться (или передайте `?tgWebAppData=...` для теста).

## Структура

- **Header**: логотип Guardian, меню (мобильные), переключатель темы.
- **Sidebar**: Главная, Подключённые чаты, Защита, Отчёты, Тариф и оплата, Подключить чат.
- **Контент**: данные с `/api/me`, `/api/chats`, `/api/chat/:id`, `/api/billing` и т.д.

Сборка: `dist/` — статика для размещения по HTTPS (Telegram Mini App).
