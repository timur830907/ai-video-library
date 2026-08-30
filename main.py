import os
import uuid
import random
import httpx
import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

os.makedirs("static", exist_ok=True)

app = FastAPI(title="AI Video Library API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

class GenerateRequest(BaseModel):
    user_id: str
    genre: str

# Функция обращения к Google Books API
async def fetch_google_book(genre: str):
    url = f"https://www.googleapis.com/books/v1/volumes?q=subject:{genre}&langRestrict=ru&maxResults=20"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code != 200:
            return None
        
        data = response.json()
        items = data.get("items", [])
        if not items:
            return None
        
        # Выбираем случайную книгу из 20 найденных
        item = random.choice(items)
        volume_info = item.get("volumeInfo", {})
        
        title = volume_info.get("title", "Неизвестное название")
        authors = ", ".join(volume_info.get("authors", ["Неизвестный автор"]))
        description = volume_info.get("description", "")
        
        # Если описания нет, пробуем выбрать другую книгу
        if not description:
            description = f"Книга '{title}' автора {authors} представлена в каталоге Google Books."
            
        return {
            "title": title,
            "author": authors,
            "text": description
        }

VIDEO_SOURCES = [
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4"
]

@app.get("/")
def root():
    return {"status": "ok", "message": "Backend running with Google Books API"}

@app.post("/generate")
async def generate_content(req: GenerateRequest):
    # 1. Запрашиваем реальную книгу из Google Books API
    book_info = await fetch_google_book(req.genre)
    
    # Резервный вариант, если Google API не вернул результат
    if not book_info:
        book_info = {
            "title": "Звездный рубеж",
            "author": "ИИ Фантаст",
            "text": "Исследовательский крейсер 'Гелиос' вышел из гиперпространственного прыжка на самом краю сектора 7."
        }

    # 2. Озвучиваем найденное описание книги через edge-tts
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)

    communicate = edge_tts.Communicate(book_info["text"], voice="ru-RU-DmitryNeural")
    await communicate.save(audio_path)

    # 3. Возвращаем результат
    return {
        "book": book_info,
        "audio_url": f"/static/{audio_filename}",
        "video_url": random.choice(VIDEO_SOURCES)
    }