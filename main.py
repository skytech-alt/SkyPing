"""
SkyPing Backend — FastAPI на Render Free.
Принимает webhook от Upptime и Telegram, рассылает уведомления.
"""
import os, json, logging
from typing import Optional, Set
import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skyping")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "")
UPPTIME_STATUS_URL = os.getenv("UPPTIME_STATUS_URL", "")
SUBSCRIBERS_FILE = "subscribers.json"

app = FastAPI(title="SkyPing Backend")
bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

redis_client: Optional[redis.Redis] = None
if REDIS_URL:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

async def get_subscribers() -> Set[str]:
    if redis_client:
        return set(await redis_client.smembers("subscribers"))
    try:
        with open(SUBSCRIBERS_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

async def save_subscriber(chat_id: str) -> None:
    if redis_client:
        await redis_client.sadd("subscribers", chat_id)
    else:
        subs = await get_subscribers()
        subs.add(chat_id)
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(subs), f)

async def remove_subscriber(chat_id: str) -> None:
    if redis_client:
        await redis_client.srem("subscribers", chat_id)
    else:
        subs = await get_subscribers()
        subs.discard(chat_id)
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(subs), f)

async def broadcast(text: str) -> None:
    if not bot:
        logger.warning("BOT_TOKEN не задан")
        return
    for cid in await get_subscribers():
        try:
            await bot.send_message(chat_id=cid, text=text)
        except Exception as e:
            logger.error("send to %s: %s", cid, e)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/webhook/upptime")
async def upptime_webhook(request: Request):
    payload = await request.json()
    logger.info("Upptime payload: %s", payload)
    status = (payload.get("status") or payload.get("site", {}).get("status") or "").lower()
    name = payload.get("service_name") or payload.get("name") or "Сервис"
    cause = payload.get("cause") or "уточняется"
    if status == "down":
        await broadcast(f"⚠️ <b>{name}</b> недоступен. Причина: {cause}. Сообщим, когда заработает.")
    elif status == "up":
        await broadcast(f"✅ <b>{name}</b> снова работает!")
    return {"ok": True}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    if not dp or not bot:
        raise HTTPException(503, "Bot not configured")
    update = types.Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}

if dp:
    @dp.message(Command("start"))
    async def start(msg: types.Message):
        await save_subscriber(str(msg.chat.id))
        await msg.answer("👋 SkyPing на связи. /status — статус, /stop — отписка.")

    @dp.message(Command("stop"))
    async def stop(msg: types.Message):
        await remove_subscriber(str(msg.chat.id))
        await msg.answer("Отписались. /start — вернуться.")

    @dp.message(Command("status"))
    async def status(msg: types.Message):
        if not UPPTIME_STATUS_URL:
            await msg.answer("Источник статуса не настроен.")
            return
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                data = (await c.get(UPPTIME_STATUS_URL)).json()
        except Exception:
            await msg.answer("Не удалось получить статус.")
            return
        lines = ["📊 <b>Статус:</b>"]
        for svc in (data if isinstance(data, list) else data.get("services", [])):
            st = svc.get("status", "unknown")
            emoji = "🟢" if st == "up" else "🔴" if st == "down" else "⚪"
            lines.append(f"{emoji} {svc.get('name', '?')}")
        await msg.answer("\n".join(lines))

@app.on_event("startup")
async def startup():
    if bot and os.getenv("RENDER_EXTERNAL_URL"):
        await bot.set_webhook(f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook/telegram")

@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()
    if bot:
        await bot.session.close()
