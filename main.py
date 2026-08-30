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

# Точная база произведений с развернутым содержанием
CLASSIC_BOOKS_DB = [
    {
        "keys": ["капитал", "capital", "маркс", "marx"],
        "title": "Капитал. Критика политической экономии",
        "author": "Карл Маркс",
        "text": (
            "ТОМ 1. ПРОЦЕСС ПРОИЗВОДСТВА КАПИТАЛА\n\n"
            "Глава 1. Товар и деньги\n"
            "Богатство обществ, в которых господствует капиталистический способ производства, "
            "выступает как «огромное скопление товаров». Товар есть прежде всего внешний предмет, "
            "вещь, которая благодаря своим свойствам удовлетворяет какие-либо человеческие потребности. "
            "Двоякая природа товара заключается в сочетании потребительной стоимости (полезности вещи) "
            "и меновой стоимости (количественного соотношения обмена).\n\n"
            "Глава 2. Превращение денег в капитал\n"
            "Всеобщая формула капитала: Д — Т — Д' (Деньги — Товар — Деньги с приростом). "
            "Первоначальная сумма денег увеличивается на величину прибавочной стоимости. Источником "
            "прибавочной стоимости является специфический товар — рабочая сила, потребительная стоимость "
            "которой обладает оригинальным свойством быть источником стоимости.\n\n"
            "Глава 3. Производство абсолютной и относительной прибавочной стоимости\n"
            "Абсолютная прибавочная стоимость производится путем прямого удлинения рабочего дня. "
            "Относительная прибавочная стоимость возникает за счет сокращения необходимого рабочего времени "
            "при росте производительности труда и развитии машин и крупной промышленности.\n\n"
            "Глава 4. Заработная плата и процесс накопления\n"
            "Заработная плата — это превращенная форма стоимости рабочей силы. Превращение прибавочной "
            "стоимости в капитал ведет к росту органического строения капитала и накоплению богатства "
            "на одном полюсе при одновременном накоплении нищеты и резервной армии труда на другом."
        )
    },
    {
        "keys": ["три мушкетера", "мушкетер", "dumas", "дюма"],
        "title": "Три мушкетёра",
        "author": "Александр Дюма",
        "text": (
            "Глава I. Три дара д’Артаньяна-отца\n\n"
            "В первый понедельник апреля 1625 года городок Мёнг был объят смятением. "
            "Юноша д’Артаньян на рыжем коне направлялся в Париж с 15 экю в кармане и рекомендательным "
            "письмом к капитану королевских мушкетеров господину де Тревилю.\n\n"
            "Глава II. Прием у господина де Тревиля\n"
            "Прибыв в штаб-квартиру мушкетеров, д’Артаньян сталкивается с Атосом, Портосом и Арамисом. "
            "По череде нелепых случайностей юноша вызывает на дуэль всех троих. На пустыре у монастыря "
            "Дешо появление гвардейцев кардинала Ришелье заставляет вчерашних соперников сражаться плечом к плечу.\n\n"
            "Девиз «Один за всех, и все за одного!» становится основой их союза в борьбе против интриг "
            "кардинала и миледи Винтер."
        )
    }
]


class GenerateRequest(BaseModel):
    user_id: str = "user1"
    genre: str
    hero_name: Optional[str] = ""
    theme_setting: Optional[str] = ""


def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).replace('\r', '').strip()


def detect_voice(query: str):
    q_lower = query.lower()
    if "(kk)" in q_lower or "қазақ" in q_lower or "дала" in q_lower:
        return "kk-KZ-DauletNeural"
    elif "(en)" in q_lower or "sci-fi" in q_lower or "detective" in q_lower or "horror" in q_lower:
        return "en-US-ChristopherNeural"
    else:
        return "ru-RU-DmitryNeural"


async def search_free_book(query: str, hero: str = "", setting: str = ""):
    clean_query = query.split("(")[0].strip().lower()

    # 1. Поиск по ключам в локальной базе (приоритет)
    for entry in CLASSIC_BOOKS_DB:
        if any(k in clean_query for k in entry["keys"]):
            return {
                "title": entry["title"],
                "author": entry["author"],
                "voice": detect_voice(query),
                "text": entry["text"]
            }

    # 2. Поиск через Wikipedia API с загрузкой текста
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Library/1.0"}
        search_url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_query)}&format=json"

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=6.0) as client:
            resp = await client.get(search_url)
            if resp.status_code == 200:
                results = resp.json().get("query", {}).get("search", [])
                if results:
                    page_title = results[0]["title"]
                    sum_url = f"https://ru.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={urllib.parse.quote(page_title)}&format=json"
                    sum_resp = await client.get(sum_url)
                    if sum_resp.status_code == 200:
                        pages = sum_resp.json().get("query", {}).get("pages", {})
                        for p_id, p_data in pages.items():
                            extract = p_data.get("extract", "")
                            if extract and len(extract) > 200:
                                return {
                                    "title": page_title,
                                    "author": "Мировая классика",
                                    "voice": detect_voice(query),
                                    "text": extract[:8000]
                                }
    except Exception as e:
        print("Wiki search error:", e)

    # 3. Универсальный текстовый блок для ненайденных запросов
    title_clean = query.split("(")[0].strip()
    return {
        "title": f"Обзор произведения: {title_clean}",
        "author": "Литературная библиотека",
        "voice": detect_voice(query),
        "text": (
            f"Аналитический обзор и содержание произведения «{title_clean}».\n\n"
            f"1. Введение и проблематика\n"
            f"Данная работа рассматривает ключевые аспекты и внутренние конфликты, "
            f"заложенные в основу концепции «{title_clean}»."
            + (f" В центре повествования находится {hero}." if hero else "")
            + (f" Действие развивается в условиях: {setting}." if setting else "") + "\n\n"
            f"2. Развитие темы и структура\n"
            f"Повествование строится на последовательном раскрытии основных тезисов, "
            f"сопровождающихся детализацией характеров и социальной обстановки. "
            f"Затрагиваются ключевые вопросы морали, социально-экономических условий и выбора."
        )
    }


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

    book = await search_free_book(raw_query, hero, setting)

    if hero and "Версия с" not in book["title"]:
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