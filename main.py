import os
import re
import uuid
import urllib.parse
from typing import Optional
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

FONT_PATH = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))

BOOKS_DATABASE = {}

# Встроенная локальная база популярных книг на случай проблем с внешними сетью/API
CLASSIC_BOOKS_DB = {
    "капитал": {
        "title": "Капитал (Das Kapital)",
        "author": "Карл Маркс",
        "text": "«Капитал» — главный труд Карла Маркса по политической экономии, содержащий критический анализ капитализма. В этой работе исследуются товарное производство, добавочная стоимость, закон стоимости, распределение дохода и динамика экономических процессов в обществе."
    },
    "война и мир": {
        "title": "Война и мир",
        "author": "Лев Толстой",
        "text": "«Война и мир» — роман-эпопея Льва Николаевича Толстого, описывающий события войн против Наполеона 1805–1812 годов. Через истории семей Ростовских, Болконских и Безуховых автор исследует философию истории, смысл жизни, любовь и судьбы народа."
    },
    "преступление и наказание": {
        "title": "Преступление и наказание",
        "author": "Фёдор Достоевский",
        "text": "Роман Фёдора Михайловича Достоевского о молодом студенте Родионе Раскольникове, решившемся на убийство ради проверки своей теории о «необыкновенных людях». Произведение раскрывает глубокий психологизм, мотивы вины и путь к духовному возрождению."
    },
    "мастер и маргарита": {
        "title": "Мастер и Маргарита",
        "author": "Михаил Булгаков",
        "text": "Роман Михаила Булгакова, соединяющий в себе сатиру на советскую Москву 1930-х годов, философскую притчу о Понтии Пилате и историю безусловной любви Маргариты и Мастера."
    }
}


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


async def search_free_book(query: str):
    clean_query = query.split("(")[0].strip().lower()
    
    # 1. Проверяем точные совпадения по локальной базе
    for k, v in CLASSIC_BOOKS_DB.items():
        if k in clean_query:
            return {
                "title": v["title"],
                "author": v["author"],
                "voice": detect_voice(query),
                "text": v["text"]
            }

    # 2. Поиск через Wikipedia API (надежно работает на серверах Render)
    try:
        wiki_url = f"https://ru.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query.split('(')[0].strip())}"
        async with httpx.AsyncClient(headers={"User-Agent": "AILibraryApp/1.0"}, follow_redirects=True) as client:
            resp = await client.get(wiki_url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get("extract", "")
                title = data.get("title", query)
                if extract and len(extract) > 30:
                    return {
                        "title": title,
                        "author": "Классическая литература / Википедия",
                        "voice": detect_voice(query),
                        "text": extract
                    }
    except Exception as e:
        print("Wiki search error:", e)

    # 3. Резервный поиск через Google Books API
    try:
        gb_url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(query.split('(')[0].strip())}&maxResults=3"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(gb_url)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    info = item.get("volumeInfo", {})
                    desc = info.get("description", "")
                    if desc:
                        return {
                            "title": info.get("title", query),
                            "author": ", ".join(info.get("authors", ["Известный автор"])),
                            "voice": detect_voice(query),
                            "text": clean_html(desc)
                        }
    except Exception as e:
        print("Google Books Error:", e)

    return None


def create_pdf(filename: str, title: str, author: str, text: str) -> str:
    pdf_path = os.path.join("static", filename)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    font_name = "DejaVuSans" if os.path.exists(FONT_PATH) else "Helvetica"
    
    c.setFont(font_name, 14)
    c.drawString(50, height - 50, title[:60])
    
    c.setFont(font_name, 11)
    c.drawString(50, height - 70, f"Автор: {author[:60]}")
    c.line(50, height - 80, width - 50, height - 80)
    
    c.setFont(font_name, 10)
    y = height - 100
    
    words = text.split()
    line = ""
    for word in words:
        if len(line + " " + word) < 65:
            line += " " + word if line else word
        else:
            c.drawString(50, y, line)
            y -= 15
            line = word
            if y < 50:
                c.showPage()
                c.setFont(font_name, 10)
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
    return list(BOOKS_DATABASE.values())[-6:][::-1]


@app.get("/book/{book_id}")
def get_book_by_id(book_id: str):
    if book_id in BOOKS_DATABASE:
        return BOOKS_DATABASE[book_id]
    raise HTTPException(status_code=404, detail="Книга не найдена")


@app.post("/generate")
async def generate_content(req: GenerateRequest):
    raw_query = req.genre.strip()
    hero = req.hero_name.strip() if req.hero_name else ""
    setting = req.theme_setting.strip() if req.theme_setting else ""
    
    book = await search_free_book(raw_query)
    voice = detect_voice(raw_query)

    if not book:
        clean_genre_key = raw_query.split(" (")[0].strip()
        book = {
            "title": f"Произведение: {clean_genre_key}",
            "author": "Литературный обзор",
            "voice": voice,
            "text": f"Обзорное произведение по теме «{clean_genre_key}». " + (f"Главный герой: {hero}. " if hero else "") + (f"Эпоха: {setting}." if setting else "")
        }
    else:
        if hero:
            book["title"] = f"{book['title']} (Версия с {hero})"
            book["text"] = f"[Персонализированная адаптация для: {hero}" + (f" | Сеттинг: {setting}" if setting else "") + f"]\n\n" + book["text"]

    book_id = uuid.uuid4().hex[:8]

    audio_filename = f"audio_{book_id}.mp3"
    audio_path = os.path.join("static", audio_filename)
    communicate = edge_tts.Communicate(book["text"][:3000], voice=book["voice"])
    await communicate.save(audio_path)

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

    BOOKS_DATABASE[book_id] = response_data
    return response_data