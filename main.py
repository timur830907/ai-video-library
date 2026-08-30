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
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

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

def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).replace('\n', ' ').strip()

def detect_language_and_voice(text_or_query: str):
    if any(c in text_or_query for c in "ӘәҒғҚқҢңӨөҰұҮүІіҺһ") or "қазақ" in text_or_query.lower():
        return "kk", "kk-KZ-DauletNeural"
    elif re.search(r'[a-zA-Z]', text_or_query) and not re.search(r'[а-яА-Я]', text_or_query):
        return "en", "en-US-ChristopherNeural"
    else:
        return "ru", "ru-RU-DmitryNeural"

def create_pdf(filename: str, title: str, author: str, text: str):
    pdf_path = os.path.join("static", filename)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, title[:60])
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, f"Author: {author[:60]}")
    c.line(50, height - 80, width - 50, height - 80)
    
    c.setFont("Helvetica", 10)
    y = height - 100
    words = text.split()
    line = ""
    for word in words:
        if len(line + " " + word) < 75:
            line += " " + word
        else:
            c.drawString(50, y, line.strip())
            y -= 15
            line = word
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 50
    if line:
        c.drawString(50, y, line.strip())
        
    c.save()
    return f"/static/{filename}"

async def search_free_book_google(query: str):
    clean_query = query.split(" (")[0].strip()
    lang_code, voice = detect_language_and_voice(clean_query)
    
    url = f"https://www.googleapis.com/books/v1/volumes?q={clean_query}&maxResults=10"
    
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                for item in items:
                    info = item.get("volumeInfo", {})
                    desc = info.get("description", "")
                    if desc and len(desc) > 80:
                        return {
                            "title": info.get("title", clean_query),
                            "author": ", ".join(info.get("authors", ["Известный автор"])),
                            "text": clean_html(desc),
                            "voice": voice
                        }
    except Exception as e:
        print(f"Search API Error: {e}")
    return None

VIDEO_SOURCES = [
    "https://vjs.zencdn.net/v/oceans.mp4",
    "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
]

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/generate")
async def generate_content(req: GenerateRequest):
    query = req.genre.strip()
    
    # 1. Сначала пробуем найти реальную книгу через Поиск API
    book = await search_free_book_google(query)
    
    # 2. Если поиск не вернул развернутый текст, используем встроенную базу по жанру
    if not book:
        lang_code, voice = detect_language_and_voice(query)
        book = {
            "title": f"Результат по запросу: {query}",
            "author": "Библиотечный фонд",
            "voice": voice,
            "text": (
                f"Вы искали: '{query}'. По данному запросу сформирована ознакомительная глава. "
                "Исследования открывают фундаментальные тайны устроения мира и истории. "
                "Каждая страница содержит важные сведения, позволяющие глубже погрузиться в выбранную тему. "
                "Вы можете скачать данный материал в формате PDF для удобного чтения на любом устройстве."
            )
        }

    # 3. Генерация аудио (для предотвращения сброса соединения на Render берется оптимизированный фрагмент)
    audio_text = book["text"][:3000] # Первые несколько тысяч символов для высокой скорости генерации
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)
    
    communicate = edge_tts.Communicate(audio_text, voice=book["voice"])
    await communicate.save(audio_path)

    # 4. Генерация PDF-книги без ограничений по длине
    pdf_filename = f"book_{uuid.uuid4().hex[:8]}.pdf"
    pdf_url = create_pdf(pdf_filename, book["title"], book["author"], book["text"])

    return {
        "book": {
            "title": book["title"],
            "author": book["author"],
            "text": book["text"]
        },
        "audio_url": f"/static/{audio_filename}",
        "pdf_url": pdf_url,
        "video_url": random.choice(VIDEO_SOURCES)
    }