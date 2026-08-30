import os
import re
import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edge_tts
import httpx
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Хранилище сгенерированных книг в памяти для галереи и 공유 по ID
BOOKS_DATABASE = {}


class GenerateRequest(BaseModel):
    user_id: str = "user1"
    genre: str
    hero_name: Optional[str] = ""
    theme_setting: Optional[str] = ""


def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).replace('\n', ' ').strip()


def detect_voice(query: str):
    q_lower = query.lower()
    if "(kk)" in q_lower or "қазақ" in q_lower or "дала" in q_lower:
        return "kk-KZ-DauletNeural"
    elif "(en)" in q_lower or "sci-fi" in q_lower or "detective" in q_lower or "horror" in q_lower:
        return "en-US-ChristopherNeural"
    else:
        return "ru-RU-DmitryNeural"


async def search_free_book_google(query: str):
    clean_query = query.split("(")[0].strip()
    url = f"https://www.googleapis.com/books/v1/volumes?q={clean_query}&maxResults=3"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    info = item.get("volumeInfo", {})
                    desc = info.get("description", "")
                    if desc and len(desc) > 80:
                        return {
                            "title": info.get("title", clean_query),
                            "author": ", ".join(info.get("authors", ["Известный автор"])),
                            "voice": detect_voice(query),
                            "text": clean_html(desc)
                        }
    except Exception:
        pass
    return None


def create_pdf(filename: str, title: str, author: str, text: str) -> str:
    pdf_path = os.path.join("static", filename)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, title[:60])
    
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 70, f"Author: {author[:60]}")
    c.line(50, height - 80, width - 50, height - 80)
    
    c.setFont("Helvetica", 10)
    y = height - 100
    
    words = text.split()
    line = ""
    for word in words:
        if len(line + " " + word) < 75:
            line += " " + word if line else word
        else:
            c.drawString(50, y, line)
            y -= 15
            line = word
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 50
    if line:
        c.drawString(50, y, line)
        
    c.save()
    return f"/static/{filename}"


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.get("/recent")
def get_recent_books():
    # Возвращает список последних созданных книг
    return list(BOOKS_DATABASE.values())[-6:][::-1]


@app.get("/book/{book_id}")
def get_book_by_id(book_id: str):
    if book_id in BOOKS_DATABASE:
        return BOOKS_DATABASE[book_id]
    raise HTTPException(status_code=404, detail="Книга не найдена")


@app.post("/generate")
async def generate_content(req: GenerateRequest):
    raw_query = req.genre.strip()
    clean_genre_key = raw_query.split(" (")[0].strip()
    hero = req.hero_name.strip() if req.hero_name else "Главный герой"
    setting = req.theme_setting.strip() if req.theme_setting else "Наши дни"
    
    # 1. Загрузка или генерация базового текста
    book = await search_free_book_google(raw_query)
    voice = detect_voice(raw_query)

    if not book:
        book = {
            "title": f"Приключения {hero} в мире {clean_genre_key}",
            "author": "ИИ Нейросеть",
            "voice": voice,
            "text": (
                f"Эпоха: {setting}. "
                f"В центре событий оказался {hero}. Всё началось незаметно, когда неожиданный поворот судьбы "
                f"поставил перед персонажем задачу невероятной сложности. Проходя через испытания жанра {clean_genre_key}, "
                f"{hero} открывает новые грани своих возможностей и движется навстречу своей главной цели."
            )
        }
    else:
        # Если персонализация включена, адаптируем текст под главного героя
        if req.hero_name:
            book["title"] = f"{book['title']} (Спецвыпуск с {hero})"
            book["text"] = f"[Герой: {hero} | Эпоха: {setting}] " + book["text"]

    book_id = uuid.uuid4().hex[:8]

    # 2. Озвучка EdgeTTS
    audio_filename = f"audio_{book_id}.mp3"
    audio_path = os.path.join("static", audio_filename)
    communicate = edge_tts.Communicate(book["text"][:3000], voice=book["voice"])
    await communicate.save(audio_path)

    # 3. Генерация PDF
    pdf_filename = f"book_{book_id}.pdf"
    pdf_url = create_pdf(pdf_filename, book["title"], book["author"], book["text"])

    response_data = {
        "id": book_id,
        "book": {
            "title": book["title"],
            "author": book["author"],
            "text": book["text"]
        },
        "audio_url": f"/static/{audio_filename}",
        "pdf_url": pdf_url
    }

    # Сохраняем в галерею
    BOOKS_DATABASE[book_id] = response_data
    return response_data