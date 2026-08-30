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

# Локальная база известных произведений
CLASSIC_BOOKS_DB = {
    "мушкетер": {
        "title": "Три мушкетёра",
        "author": "Александр Дюма",
        "text": (
            "Глава I. Д’Артаньян и три дара отца.\n\n"
            "В первый понедельник апреля 1825 года всё местечко Мёнг казалось взволнованным так, "
            "словно гугеноты собирались превратить его во второй Ла-Рошель. Юный д’Артаньян на своем "
            "желтом коне направлялся в Париж, имея при себе лишь 15 экю, письмо к господину де Тревилю "
            "и рецепт целебного бальзама.\n\n"
            "Прибыв в столицу, юноша сразу же сталкивается с прославленными королевскими мушкетерами: "
            "Атосом, Портосом и Арамисом. По случайности д’Артаньян назначает дуэль каждому из них с интервалом в один час. "
            "Однако появление гвардейцев кардинала Ришелье заставляет соперников объединиться.\n\n"
            "«Один за всех, и все за одного!» — этот девиз становится символом их нерушимой дружбы в борьбе "
            "против интриг кардинала и коварной Миледи."
        )
    },
    "capital": {
        "title": "Капитал (Das Kapital)",
        "author": "Карл Маркс",
        "text": (
            "Том первый. Процесс производства капитала.\n\n"
            "Богатство обществ, в которых господствует капиталистический способ производства, "
            "выступает как «огромное скопление товаров», а отдельный товар — как элементарная форма этого богатства.\n\n"
            "1. Товар и его двоякая природа: Потребительная стоимость и Стоимость.\n"
            "Товар есть прежде всего внешний предмет, вещь, которая благодаря своим свойствам удовлетворяет "
            "какие-либо человеческие потребности. Потребительная стоимость осуществляется лишь в пользовании или потреблении.\n\n"
            "2. Превращение денег в капитал.\n"
            "Купля и продажа рабочей силы. Капиталист находит на рынке специфический товар — способность к труду. "
            "В процессе использования этого товара создается прибавочная стоимость, составляющая основу капиталистического накопления."
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
    return re.sub(cleanr, '', raw_html).replace('\r', '').strip()


def detect_voice(query: str):
    q_lower = query.lower()
    if "(kk)" in q_lower or "қазақ" in q_lower or "дала" in q_lower:
        return "kk-KZ-DauletNeural"
    elif "(en)" in q_lower or "sci-fi" in q_lower or "detective" in q_lower or "horror" in q_lower:
        return "en-US-ChristopherNeural"
    else:
        return "ru-RU-DmitryNeural"


def generate_fallback_story(query: str, hero: str, setting: str) -> dict:
    """Генерирует качественный структурированный текст, если книга не найдена во внешних API"""
    title_clean = query.split("(")[0].strip()
    hero_str = hero if hero else "Главный герой"
    setting_str = setting if setting else "Классическая эпоха"

    story_text = (
        f"Глава 1. Начало истории «{title_clean}».\n\n"
        f"События разворачиваются в атмосфере, где преобладает {setting_str}. "
        f"{hero_str} отправляется в путь, не подозревая, какие испытания ждут его впереди.\n\n"
        f"Каждый шаг приближает разгадку основной тайны произведения. Встречи с соратниками и противниками "
        f"формируют характер персонажа и заставляют пересмотреть жизненные ориентиры. "
        f"Конфликт интересов и философские размышления о долге, чести и судьбе проходят красной нитью "
        f"через всё повествование.\n\n"
        f"Глава 2. Кульминация и повороты сюжета.\n\n"
        f"Напряжение достигает апогея. {hero_str} сталкивается с главным вызовом, требующим полного "
        f"самопожертвования и принятия сложного решения. В этом противостоянии раскрываются истинные мотивы всех участников событий."
    )

    return {
        "title": title_clean,
        "author": "Мировая библиотека",
        "text": story_text
    }


async def search_free_book(query: str, hero: str = "", setting: str = ""):
    clean_query = query.split("(")[0].strip().lower()

    # 1. Проверка встроенных популярных произведений
    for key, item in CLASSIC_BOOKS_DB.items():
        if key in clean_query or clean_query in item["title"].lower():
            return {
                "title": item["title"],
                "author": item["author"],
                "voice": detect_voice(query),
                "text": item["text"]
            }

    # 2. Поиск в русской Википедии с правильным заголовком User-Agent
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Library-App/1.0"}
        search_url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_query)}&format=json"
        
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=5.0) as client:
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
                            if extract and len(extract) > 150:
                                return {
                                    "title": page_title,
                                    "author": "Энциклопедический фонд",
                                    "voice": detect_voice(query),
                                    "text": extract[:6000]
                                }
    except Exception as e:
        print("Wiki search error:", e)

    # 3. Если ничего не найдено, генерируем подробную историю
    fallback = generate_fallback_story(query, hero, setting)
    fallback["voice"] = detect_voice(query)
    return fallback


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