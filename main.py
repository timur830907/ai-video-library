import os
import re
import uuid
import random
import httpx
import edge_tts
from fastapi import FastAPI
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

# Словарь поисковых ключей для Google Books
GENRE_QUERIES = {
    "Фантастика": "sci-fi fiction",
    "Детектив": "detective mystery",
    "Романтика": "romance novel",
    "Ужасы": "horror fiction",
    "Приключения": "adventure novel",
    "Фэнтези": "fantasy novel",
    "Киберпанк": "cyberpunk fiction",
    "Научпоп": "science non-fiction",
    "История": "history novel",
    "Психология": "psychology self-help",
    "Бизнес": "business management",
    "Философия": "philosophy thought"
}

def clean_text(text: str) -> str:
    """Удаляет HTML-теги и лишние спецсимволы из текста Google Books"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

async def fetch_google_book(genre: str):
    query = GENRE_QUERIES.get(genre, genre)
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=ru&maxResults=40"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None
            
            data = response.json()
            items = data.get("items", [])
            if not items:
                return None
            
            # Фильтруем книги, у которых есть нормальное описание
            valid_items = []
            for item in items:
                info = item.get("volumeInfo", {})
                desc = info.get("description", "")
                if len(desc) > 50:
                    valid_items.append(item)
            
            if not valid_items:
                valid_items = items

            selected = random.choice(valid_items)
            info = selected.get("volumeInfo", {})
            
            title = info.get("title", "Неизвестное название")
            authors = ", ".join(info.get("authors", ["Неизвестный автор"]))
            raw_desc = info.get("description", "")
            
            cleaned_desc = clean_text(raw_desc)
            if not cleaned_desc:
                cleaned_desc = f"Прекрасный роман '{title}' от автора {authors}. Книга рассказывает увлекательную историю в жанре {genre}."

            # Если описание слишком короткое, дополняем его структуры для полноценной озвучки
            if len(cleaned_desc) < 200:
                cleaned_desc += (
                    f" В этой книге автор {authors} погружает читателя в уникальную атмосферу жанра {genre}. "
                    f"Каждая страница произведения пропитана глубокими эмоциями и неожиданными поворотами сюжета, "
                    f"заставляя переосмыслить привычные вещи и затаив дыхание следить за развитием событий."
                )

            return {
                "title": title,
                "author": authors,
                "text": cleaned_desc
            }
    except Exception as e:
        print(f"Error fetching Google Books: {e}")
        return None

VIDEO_SOURCES = [
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4"
]

@app.get("/")
def root():
    return {"status": "ok", "message": "API with Google Books and EdgeTTS active"}

@app.post("/generate")
async def generate_content(req: GenerateRequest):
    book_info = await fetch_google_book(req.genre)
    
    if not book_info:
        book_info = {
            "title": "Хроники далеких миров",
            "author": "Аркадий Стругацкий",
            "text": "Экспедиционный корпус достиг границы неизведанного сектора галактики. На поверхности планеты были обнаружены следы древней цивилизации, опередившей человечество на миллионы лет. Исследователям предстоит разгадать тайну оставленных артефактов и понять причины исчезновения их создателей."
        }

    # Генерация озвучки
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)

    try:
        communicate = edge_tts.Communicate(book_info["text"], voice="ru-RU-DmitryNeural")
        await communicate.save(audio_path)
    except Exception as e:
        print(f"TTS generation error: {e}")

    return {
        "book": book_info,
        "audio_url": f"/static/{audio_filename}",
        "video_url": random.choice(VIDEO_SOURCES)
    }