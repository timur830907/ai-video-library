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


async def search_free_book_google(query: str):
    clean_query = query.split("(")[0].strip()
    url = f"https://www.googleapis.com/books/v1/volumes?q={clean_query}&maxResults=5&langRestrict=ru"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=7.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    info = item.get("volumeInfo", {})
                    title = info.get("title", clean_query)
                    authors = ", ".join(info.get("authors", [])) or "Классический автор"
                    desc = info.get("description", "")
                    snippet = item.get("searchInfo", {}).get("textSnippet", "")
                    
                    full_text = desc if desc else snippet
                    
                    if full_text:
                        return {
                            "title": title,
                            "author": authors,
                            "voice": detect_voice(query),
                            "text": clean_html(full_text)
                        }
                    else:
                        categories = ", ".join(info.get("categories", ["Художественная литература"]))
                        pub_date = info.get("publishedDate", "Не указан")
                        return {
                            "title": title,
                            "author": authors,
                            "voice": detect_voice(query),
                            "text": f"Произведение «{title}» (Автор: {authors}). Категория: {categories}. Дата публикации / издания: {pub_date}. "
                                    f"Это выдающееся литературное произведение из мировой базы данных Google Books."
                        }
    except Exception as e:
        print("Google Books API Error:", e)
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
    
    book = await search_free_book_google(raw_query)
    voice = detect_voice(raw_query)

    if not book:
        clean_genre_key = raw_query.split(" (")[0].strip()
        hero_text = hero if hero else "Главный герой"
        book = {
            "title": f"Приключения {hero_text} в мире {clean_genre_key}",
            "author": "ИИ Нейросеть",
            "voice": voice,
            "text": (
                f"В центре событий оказался {hero_text}. В сеттинге '{setting if setting else 'Наши дни'}' "
                f"персонаж проходит через ключевые испытания жанра {clean_genre_key}."
            )
        }
    else:
        if hero:
            book["title"] = f"{book['title']} (Спецверсия)"
            book["text"] = f"[Адаптация для: {hero}" + (f" | Сеттинг: {setting}" if setting else "") + f"]\n\n" + book["text"]

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