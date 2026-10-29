import os
import json
import logging
from typing import Set
import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skyping")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "")
UPPTIME_STATUS_URL = os.getenv("UPPTIME_STATUS_URL", "")

app = FastAPI(title="SkyPing Backend")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML")) if BOT_TOKEN else None
dp = Dispatcher() if bot else None
redis_client = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None

# Хранение в Redis:
# Ключ: "subs:<ServiceName>" -> Set(chat_id)

async def add_sub(chat_id: str, service: str):
    if redis_client:
        await redis_client.sadd(f"subs:{service}", chat_id)
        await redis_client.sadd(f"user:{chat_id}", service)

async def remove_sub(chat_id: str, service: str):
    if redis_client:
        await redis_client.srem(f"subs:{service}", chat_id)
        await redis_client.srem(f"user:{chat_id}", service)

async def get_user_subs(chat_id: str) -> Set[str]:
    if redis_client:
        return await redis_client.smembers(f"user:{chat_id}")
    return set()

async def broadcast(service: str, text: str):
    if not bot or not redis_client: return
    subscribers = await redis_client.smembers(f"subs:{service}")
    for cid in subscribers:
        try: await bot.send_message(chat_id=cid, text=text)
        except Exception as e: logger.error(f"Err to {cid}: {e}")

# ── Эндпоинты ──
@app.get("/health")
async def health(): return {"status": "ok"}

@app.post("/webhook/upptime")
async def upptime_webhook(request: Request):
    payload = await request.json()
    status = (payload.get("status") or "").lower()
    name = payload.get("service_name") or "Сервис"
    cause = payload.get("cause") or "уточняется"
    
    if status == "down":
        await broadcast(name, f"⚠️ <b>{name}</b> недоступен.\nПричина: {cause}\nМы сообщим, когда заработает.")
    elif status == "up":
        await broadcast(name, f"✅ <b>{name}</b> снова работает!")
    return {"ok": True}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    update = types.Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}

# ── Хэндлеры ──
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_id = str(message.chat.id)
    
    # Проверяем, пришел ли юзер по Deep Link (например, /start sub_Госуслуги)
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("sub_"):
        service_name = args[1].replace("sub_", "").replace("%20", " ")
        await add_sub(chat_id, service_name)
        await message.answer(f"✅ Вы подписались на уведомления для <b>{service_name}</b>!\n\nНажмите /mysubs, чтобы посмотреть все подписки.")
        return

    # Обычный старт
    await message.answer(
        "👋 Привет! Я слежу за доступностью сервисов.\n\n"
        "Выберите сервисы на сайте, или используйте /mysubs, чтобы управлять подписками."
    )

@dp.message(Command("mysubs"))
async def cmd_mysubs(message: types.Message):
    chat_id = str(message.chat.id)
    subs = await get_user_subs(chat_id)
    
    if not subs:
        await message.answer("У вас пока нет подписок. Нажмите кнопку 'Уведомлять' на сайте.")
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ Отписаться от {s}", callback_data=f"unsub_{s}")] for s in subs
    ])
    await message.answer("Ваши подписки:\n" + "\n".join([f"• {s}" for s in subs]), reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("unsub_"))
async def process_unsub(callback: types.CallbackQuery):
    service = callback.data.replace("unsub_", "")
    await remove_sub(str(callback.message.chat.id), service)
    await callback.answer(f"Вы отписались от {service}")
    await callback.message.edit_text(f"✅ Вы больше не получаете уведомления для <b>{service}</b>.")

@app.on_event("startup")
async def startup():
    if bot and os.getenv("RENDER_EXTERNAL_URL"):
        await bot.set_webhook(f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook/telegram")
