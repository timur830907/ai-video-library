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
    clean_query = query.split("(")[0].strip()
    encoded_query = urllib.parse.quote(clean_query)
    
    # 1. Попытка поиска через Google Books API
    gb_url = f"https://www.googleapis.com/books/v1/volumes?q={encoded_query}&maxResults=5"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            resp = await client.get(gb_url, timeout=7.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    info = item.get("volumeInfo", {})
                    title = info.get("title", clean_query)
                    authors = ", ".join(info.get("authors", []))
                    desc = info.get("description", "")
                    snippet = item.get("searchInfo", {}).get("textSnippet", "")
                    
                    text_content = desc if desc else snippet
                    if text_content and len(clean_html(text_content)) > 20:
                        return {
                            "title": title,
                            "author": authors if authors else "Классическое произведение",
                            "voice": detect_voice(query),
                            "text": clean_html(text_content)
                        }
                    elif title:
                        cat = ", ".join(info.get("categories", ["Мировая литература"]))
                        date = info.get("publishedDate", "")
                        return {
                            "title": title,
                            "author": authors if authors else "Авторы мирового фонда",
                            "voice": detect_voice(query),
                            "text": f"Книга «{title}» ({authors}). Категория: {cat}. Дата издания: {date}. "
                                    f"Данное фундаментальное произведение вошло в международные каталоги литературы."
                        }
    except Exception as e:
        print("Google Books Error:", e)

    # 2. Попытка поиска через Open Library API (если Google Books ничего не вернул)
    try:
        ol_url = f"https://openlibrary.org/search.json?q={encoded_query}&limit=3"
        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            resp = await client.get(ol_url, timeout=7.0)
            if resp.status_code == 200:
                docs = resp.json().get("docs", [])
                if docs:
                    doc = docs[0]
                    title = doc.get("title", clean_query)
                    authors = ", ".join(doc.get("author_name", []))
                    first_sentence = doc.get("first_sentence", [])
                    sentence_text = " ".join(first_sentence) if isinstance(first_sentence, list) else str(first_sentence)
                    
                    body_text = sentence_text if sentence_text else f"Известное фундаментальное произведение «{title}» автора {authors}."
                    return {
                        "title": title,
                        "author": authors if authors else "Классика литературы",
                        "voice": detect_voice(query),
                        "text": body_text
                    }
    except Exception as e:
        print("Open Library Error:", e)

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
        hero_text = hero if hero else "Главный герой"
        book = {
            "title": f"Произведение: {clean_genre_key}",
            "author": "Мировая библиотека",
            "voice": voice,
            "text": f"Книга по запросу «{clean_genre_key}». Сеттинг: {setting if setting else 'Классика'}. Герой: {hero_text}."
        }
    else:
        if hero:
            book["title"] = f"{book['title']} (Версия с {hero})"
            book["text"] = f"[Персонализация: {hero}" + (f" | Сеттинг: {setting}" if setting else "") + f"]\n\n" + book["text"]

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