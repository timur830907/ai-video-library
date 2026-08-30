import os
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edge_tts
import httpx
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = FastAPI()

# Разрешаем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем папку static для файлов (аудио и PDF)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


class GenerateRequest(BaseModel):
    user_id: str = "user1"
    genre: str


def detect_language_and_voice(query: str):
    q_lower = query.lower()
    if "(kk)" in q_lower or "қазақ" in q_lower or "дала" in q_lower:
        return "kk", "kk-KZ-AigulNeural"
    elif "(en)" in q_lower or "sci-fi" in q_lower or "detective" in q_lower or "horror" in q_lower:
        return "en", "en-US-AriaNeural"
    else:
        return "ru", "ru-RU-SvetlanaNeural"


async def search_free_book_google(query: str):
    clean_query = query.split("(")[0].strip()
    url = f"https://www.googleapis.com/books/v1/volumes?q={clean_query}&maxResults=1"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                if "items" in data and len(data["items"]) > 0:
                    item = data["items"][0]["volumeInfo"]
                    title = item.get("title", clean_query)
                    authors = ", ".join(item.get("authors", ["Неизвестный автор"]))
                    description = item.get("description", "")
                    
                    if len(description) < 100:
                        description = (
                            f"Книга '{title}' автора {authors}. "
                            "Данное произведение представляет собой выдающийся образец своего жанра. "
                            "Оно погружает читателя в уникальную атмосферу и захватывающий сюжет от начала до самого конца."
                        )
                    
                    _, voice = detect_language_and_voice(query)
                    return {
                        "title": title,
                        "author": authors,
                        "voice": voice,
                        "text": description
                    }
    except Exception:
        pass
    return None


def create_pdf(filename: str, title: str, author: str, text: str) -> str:
    pdf_path = os.path.join("static", filename)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    # Заголовок
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, title[:50])
    
    # Автор
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, f"Author: {author}")
    
    # Текст книги
    c.setFont("Helvetica", 10)
    y = height - 100
    
    # Простая разбивка текста на строки
    words = text.split()
    line = ""
    for word in words:
        if len(line + " " + word) < 80:
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
    return {"status": "ok", "message": "Book AI Backend Active"}


@app.post("/generate")
async def generate_content(req: GenerateRequest):
    query = req.genre.strip()
    
    # 1. Поиск книги через API
    book = await search_free_book_google(query)
    
    # 2. Резервный вариант, если ничего не найдено
    if not book:
        _, voice = detect_language_and_voice(query)
        book = {
            "title": f"Результат по запросу: {query}",
            "author": "Библиотечный фонд",
            "voice": voice,
            "text": (
                f"Вы искали: '{query}'. По данному запросу сформирован ознакомительный материал. "
                "Каждая страница содержит важные сведения, позволяющие глубже погрузиться в тему. "
                "Вы можете скачать данный материал в формате PDF для удобного чтения."
            )
        }

    # 3. Генерация аудио через EdgeTTS
    audio_text = book["text"][:3000]
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)
    
    communicate = edge_tts.Communicate(audio_text, voice=book["voice"])
    await communicate.save(audio_path)

    # 4. Генерация PDF
    pdf_filename = f"book_{uuid.uuid4().hex[:8]}.pdf"
    pdf_url = create_pdf(pdf_filename, book["title"], book["author"], book["text"])

    return {
        "book": {
            "title": book["title"],
            "author": book["author"],
            "text": book["text"]
        },
        "audio_url": f"/static/{audio_filename}",
        "pdf_url": pdf_url
    }