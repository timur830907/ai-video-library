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

# Встроенная подробная база классических произведений
CLASSIC_BOOKS_DB = {
    "capital": {
        "keywords": ["capital", "маркс", "marx", "капитал"],
        "title": "Капитал (Das Kapital) — Подробный конспект и главные идеи",
        "author": "Карл Маркс (Karl Marx)",
        "text": (
            "«Капитал» (нем. Das Kapital) — главный труд Карла Маркса по политической экономии, "
            "содержащий критический анализ капиталистической системы и механизмов её функционирования.\n\n"
            "ОСНОВНЫЕ ПОЛОЖЕНИЯ И ГЛАВЫ:\n\n"
            "1. Товар и деньги.\n"
            "Богатство обществ, в которых господствует капиталистический способ производства, "
            "выступает как «огромное скопление товаров». Товар обладает потребительной стоимостью "
            "(способностью удовлетворять человеческую потребность) и меновой стоимостью "
            "(пропорцией, в которой один товар обменивается на другой). В основе стоимости лежит "
            "абстрактный человеческий труд, затраченный на производство товара.\n\n"
            "2. Превращение денег в капитал.\n"
            "Всеобщая формула капитала: Д — Т — Д' (Деньги — Товар — Деньги с приростом). "
            "Первоначальная сумма денег увеличивается на величину прибавочной стоимости. Источником "
            "прибавочной стоимости является покупка специфического товара — рабочей силы, способной "
            "создавать стоимость больше собственной стоимости.\n\n"
            "3. Производство абсолютной и относительной прибавочной стоимости.\n"
            "Абсолютная прибавочная стоимость получаются путем удлинения рабочего дня. Относительная "
            "прибавочная стоимость возникает за счет сокращения необходимого рабочего времени при "
            "росте производительности труда и внедрении новых технологий.\n\n"
            "4. Заработная плата и накопление капитала.\n"
            "Заработная плата выступает как превращенная форма стоимости рабочей силы. Накопление "
            "капитала приводит к росту органического строения капитала, что ведет к образованию "
            "резервной армии труда (безработице) и циклическим экономическим кризисам."
        )
    },
    "war_and_peace": {
        "keywords": ["война и мир", "war and peace", "толстой", "tolstoy"],
        "title": "Война и мир",
        "author": "Лев Толстой",
        "text": (
            "«Война и мир» — роман-эпопея Льва Николаевича Толстого, описывающий события "
            "воин против Наполеона 1805–1812 годов.\n\n"
            "Сюжет охватывает судьбы сотен героев, но в центре внимания остаются несколько семей: "
            "Ростовы, Болконские, Безуховы и Курагины. Через поиск смысла жизни Пьером Безуховым "
            "и Андреем Болконским автор раскрывает глубокие философские вопросы о роли личности в истории, "
            "природе патриотизма, любви, смерти и духовного перерождения."
        )
    },
    "crime": {
        "keywords": ["преступление", "достоевский", "dostoevsky", "punishment"],
        "title": "Преступление и наказание",
        "author": "Фёдор Достоевский",
        "text": (
            "Социально-философский и психологический роман Фёдора Михайловича Достоевского.\n\n"
            "Главный герой, бывший студент Родион Раскольников, создает теорию о делении людей "
            "на «вошь дрожащую» и «право имеющих». Чтобы проверить свою идею, он совершает убийство "
            "процентщицы. Однако духовные муки, совесть и встреча с Соней Мармеладовой заставляют "
            "его пройти через искреннее раскаяние и путь к нравственному возрождению."
        )
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
    return text.replace('\r', '').strip()


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

    # 1. Сначала проверяем встроенную локальную базу (гарантирует подробный текст)
    for key, item in CLASSIC_BOOKS_DB.items():
        if any(kw in clean_query for kw in item["keywords"]):
            return {
                "title": item["title"],
                "author": item["author"],
                "voice": detect_voice(query),
                "text": item["text"]
            }

    # 2. Поиск полного текста страницы из Русской Викитеки (Wikisource)
    try:
        ws_url = f"https://ru.wikisource.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_query)}&format=json"
        async with httpx.AsyncClient(headers={"User-Agent": "AILibraryApp/1.0"}, follow_redirects=True) as client:
            resp = await client.get(ws_url, timeout=6.0)
            if resp.status_code == 200:
                results = resp.json().get("query", {}).get("search", [])
                if results:
                    page_title = results[0]["title"]
                    content_url = f"https://ru.wikisource.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={urllib.parse.quote(page_title)}&format=json"
                    c_resp = await client.get(content_url, timeout=6.0)
                    if c_resp.status_code == 200:
                        pages = c_resp.json().get("query", {}).get("pages", {})
                        for p_id, p_data in pages.items():
                            full_text = p_data.get("extract", "")
                            if len(full_text) > 200:
                                return {
                                    "title": page_title,
                                    "author": "Викитека (Общественное достояние)",
                                    "voice": detect_voice(query),
                                    "text": full_text[:8000]  # Извлекаем объемный фрагмент до 8000 символов
                                }
    except Exception as e:
        print("Wikisource error:", e)

    # 3. Поиск статьи из Википедии через Wikipedia Extract API
    try:
        search_url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_query)}&format=json"
        async with httpx.AsyncClient(headers={"User-Agent": "AILibraryApp/1.0"}, follow_redirects=True) as client:
            resp = await client.get(search_url, timeout=6.0)
            if resp.status_code == 200:
                search_results = resp.json().get("query", {}).get("search", [])
                if search_results:
                    first_title = search_results[0]["title"]
                    sum_url = f"https://ru.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={urllib.parse.quote(first_title)}&format=json"
                    sum_resp = await client.get(sum_url, timeout=6.0)
                    if sum_resp.status_code == 200:
                        pages = sum_resp.json().get("query", {}).get("pages", {})
                        for p_id, p_data in pages.items():
                            extract = p_data.get("extract", "")
                            if extract and len(extract) > 100:
                                return {
                                    "title": first_title,
                                    "author": "Энциклопедический фонд",
                                    "voice": detect_voice(query),
                                    "text": extract[:8000]
                                }
    except Exception as e:
        print("Wiki search error:", e)

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

    # Разбиваем текст по абзацам и строкам для красивого форматирования в PDF
    paragraphs = text.split("\n")
    for paragraph in paragraphs:
        if not paragraph.strip():
            y -= 10
            continue

        words = paragraph.split()
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
            y -= 15

        if y < 50:
            c.showPage()
            c.setFont(font_name, 10)
            y = height - 50

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
            "author": "Литературный архив",
            "voice": voice,
            "text": (
                f"Развернутое произведение по запросу «{clean_genre_key}».\n\n"
                f"В данном разделе представлены ключевые характеристики произведения, его фабула и концепция.\n"
                + (f"Главный персонаж: {hero}.\n" if hero else "")
                + (f"Исторический сеттинг и атмосфера: {setting}.\n" if setting else "")
            )
        }
    else:
        if hero:
            book["title"] = f"{book['title']} (Версия с {hero})"
            book["text"] = f"[Персонализированный вариант для: {hero}" + (f" | Сеттинг: {setting}" if setting else "") + f"]\n\n" + book["text"]

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