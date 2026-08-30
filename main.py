import os
import json
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import edge_tts
from google import genai
from google.genai import types as genai_types

app = FastAPI()

# Ключи (можно задать здесь или через переменные окружения)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# База пользователей (в будущем заменить на БД PostgreSQL / SQLite)
USERS_DB = {
    "test_user": {
        "created_at": datetime.now(),  # Дата регистрации
        "is_paid": False
    }
}

class GenerateRequest(BaseModel):
    user_id: str
    genre: str

# Функция проверки 30 дней бесплатного периода
def check_subscription(user_id: str):
    user = USERS_DB.get(user_id)
    if not user:
        # Автоматическая регистрация нового пользователя при первом запросе
        USERS_DB[user_id] = {"created_at": datetime.now(), "is_paid": False}
        return USERS_DB[user_id]
    
    days_passed = (datetime.now() - user["created_at"]).days
    if days_passed > 30 and not user["is_paid"]:
        raise HTTPException(
            status_code=402, 
            detail="30 дней бесплатного периода истекли. Оплатите подписку через Kaspi QR."
        )
    return user

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("index.html")

@app.post("/api/generate")
async def generate_content(req: GenerateRequest):
    # 1. Проверка подписки (30 дней)
    check_subscription(req.user_id)
    
    # 2. Генерация текста через Gemini API
    prompt = f"""Напиши отрывок из книги в жанре {req.genre}. 
    Верни JSON с ключами: "title", "author", "text" (текст 30-40 слов)."""
    
    response = await asyncio.to_thread(
        ai_client.models.generate_content,
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    book_data = json.loads(response.text)
    
    # 3. Озвучка (TTS)
    audio_path = f"static/audio_{req.user_id}.mp3"
    os.makedirs("static", exist_ok=True)
    
    text_to_speech = f"Книга {book_data['title']}. Автор {book_data['author']}. {book_data['text']}"
    communicate = edge_tts.Communicate(text_to_speech, "ru-RU-DmitryNeural")
    await communicate.save(audio_path)
    
    return {
        "status": "success",
        "book": book_data,
        "audio_url": f"/{audio_path}",
        # Ссылка на видео (тут подключается D-ID / HeyGen / Runway API)
        "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
    }

@app.post("/api/kaspi/pay")
async def create_kaspi_pay(user_id: str):
    # Генерация ссылки/QR Kaspi Pay
    return {
        "qr_url": f"https://kaspi.kz/pay/link?amount=2990&comment=Subscription_{user_id}"
    }

# Монтируем папку со статикой для отдачи аудио/видео файлов
app.mount("/static", StaticFiles(directory="static"), name="static")