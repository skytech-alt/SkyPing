# SkyPing

Мониторинг доступности российских сервисов с уведомлениями в Telegram.

## Компоненты

- **Upptime** (GitHub Actions + GitHub Pages) — проверка URL каждые 5 минут.
- **Render (FastAPI)** — приём webhook'ов и рассылка в Telegram.
- **Vercel** — лендинг со статусом.
- **cron-job.org** — внешний пингер `/health`, чтобы Render не засыпал.

## Переменные окружения (Render)

- `BOT_TOKEN` — токен из @BotFather
- `REDIS_URL` — из Upstash (опционально)
- `UPPTIME_STATUS_URL` — `https://skytech-alt.github.io/SkyPing/api/status.json`

## Быстрый старт

1. Форкните этот репозиторий в Upptime.
2. Задеплойте `main.py` на Render.
3. Настройте cron-job.org на `GET /health` каждые 10 минут.
4. Задеплойте `index.html` на Vercel.
