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

# Расширенная карта ключевых слов (включая латиницу и транслит)
CLASSIC_BOOKS_DB = {
    "capital": {
        "keywords": ["capital", "маркс", "marx", "капитал"],
        "title": "Капитал (Das Kapital)",
        "author": "Карл Маркс (Karl Marx)",
        "text": "«Капитал» — фундаментальный труд Карла Маркса по политической экономии, посвященный критическому анализу капиталистической системы. В книге подробно рассматриваются понятия товара, стоимости, добавочной стоимости, накопления капитала и экономических законов развития общества."
    },
    "war_and_peace": {
        "keywords": ["война и мир", "war and peace", "толстой", "tolstoy"],
        "title": "Война и мир",
        "author": "Лев Толстой",
        "text": "Роман-эпопея Льва Николаевича Толстого, охватывающий период наполеоновских войн. Труд глубинно раскрывает судьбы русского общества, философию истории, психологию личности и жизненный путь главных героев — Пьера Безухова, Андрея Болконского и Наташи Ростовой."
    },
    "crime": {
        "keywords": ["преступление", "достоевский", "dostoevsky", "punishment"],
        "title": "Преступление и наказание",
        "author": "Фёдор Достоевский",
        "text": "Роман о психологических исканиях и нравственном кризисе Родиона Раскольникова. Труд исследует грани человеческой морали, искупления и душевного возрождения."
    }
}


class GenerateRequest(BaseModel):
    user_id: str = "user1"
    genre: str
    hero_name: Optional[str] = ""
    theme_setting: Optional[str] = ""


def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    text = re.sub(cleanr, '', raw_html)
    return text.replace('\n', ' ').strip()


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
    
    # 1. Поиск по локальной базе с сопоставлением ключевых слов (транслит / опечатки)
    for key, item in CLASSIC_BOOKS_DB.items():
        if any(kw in clean_query for kw in item["keywords"]):
            return {
                "title": item["title"],
                "author": item["author"],
                "voice": detect_voice(query),
                "text": item["text"]
            }

    # 2. Полнотекстовый поиск Wikipedia Search API (исправляет опечатки)
    try:
        search_url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_query)}&format=json"
        async with httpx.AsyncClient(headers={"User-Agent": "AILibraryApp/1.0"}, follow_redirects=True) as client:
            resp = await client.get(search_url, timeout=5.0)
            if resp.status_code == 200:
                search_results = resp.json().get("query", {}).get("search", [])
                if search_results:
                    first_title = search_results[0]["title"]
                    snippet = clean_html(search_results[0].get("snippet", ""))
                    
                    # Запрашиваем полный summary по найденной статье
                    sum_url = f"https://ru.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(first_title)}"
                    sum_resp = await client.get(sum_url, timeout=5.0)
                    if sum_resp.status_code == 200:
                        extract = sum_resp.json().get("extract", "")
                        if extract and len(extract) > 40:
                            return {
                                "title": first_title,
                                "author": "Энциклопедия / Классический фонд",
                                "voice": detect_voice(query),
                                "text": extract
                            }
                    if snippet and len(snippet) > 30:
                        return {
                            "title": first_title,
                            "author": "Литературная справка",
                            "voice": detect_voice(query),
                            "text": f"Обзор произведения «{first_title}»: {snippet}..."
                        }
    except Exception as e:
        print("Wiki search error:", e)

    # 3. Резервный поиск через Google Books API
    try:
        gb_url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(clean_query)}&maxResults=3"
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
            "title": f"Литературный обзор: {clean_genre_key}",
            "author": "Мировая библиотека",
            "voice": voice,
            "text": (
                f"Произведение по запросу «{clean_genre_key}». "
                f"В рамках темы рассмотрены ключевые аспекты жанра и сюжетные линии. "
                + (f"Главный персонаж: {hero}. " if hero else "")
                + (f"Сеттинг: {setting}." if setting else "")
            )
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