import os
import re
import uuid
from fastapi import FastAPI
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


class GenerateRequest(BaseModel):
    user_id: str = "user1"
    genre: str


# База уникальных готовых текстов для каждого жанра
DETAILED_STORIES = {
    "Фантастика": {
        "title": "Звездные скитальцы",
        "author": "Аркадий Стругацкий",
        "voice": "ru-RU-DmitryNeural",
        "text": (
            "Флагманский исследовательский крейсер вышел из гиперпространственного прыжка у самой границы сектора Орион. "
            "Перед экипажем простиралась безымянная планета, окутанная плотным слоем фиолетовой атмосферы. "
            "Детекторы зафиксировали регулярный импульсный сигнал из глубин тектонического разлома. "
            "Капитан отдал приказ спустить разведывательный модуль. Команда понимала, что данный сигнал не мог "
            "быть естественного происхождения: это было древнее послание цивилизации, опередившей человечество на миллионы лет. "
            "Каждый шаг по поверхности неизвестного мира приближал исследователей к разгадке величайшей тайны галактики."
        )
    },
    "Комедия": {
        "title": "Операция 'Неуклюжий агент'",
        "author": "Марк Твен",
        "voice": "ru-RU-DmitryNeural",
        "text": (
            "Попытка незаметно внедрить нового сотрудника в отдел продаж провалилась в первые же пять минут. "
            "Сначала он случайно перепутал кабинеты и провел часовую презентацию маркетинговой стратегии перед курьерами. "
            "Затем, пытаясь исправить ситуацию, пролил кофе на главный сервер компании, вызвав перезагрузку всей сети. "
            "Однако благодаря невероятной харизме и непоколебимому оптимизму, к концу дня его назначили руководителем антикризисного комитета."
        )
    },
    "Боевик": {
        "title": "Захват высоты 404",
        "author": "Джон Хантер",
        "voice": "ru-RU-DmitryNeural",
        "text": (
            "Взрыв прогремел на верхнем этаже комплекса, разбив панорамные стекла и озарив ночное небо вспышкой. "
            "Спецотряд заблокировал все выходы, но у группы эвакуации оставался последний шанс прорваться через крышу. "
            "Перезарядив автомат и проверив связь с пилотом вертолета, командир отдал сигнал к началу операции. "
            "Под непрерывным перекрестным огнем бойцы двигались от укрытия к укрытию, преодолевая сопротивление противника."
        )
    },
    "Триллер": {
        "title": "Шепот из полутьмы",
        "author": "Стивен Кинг",
        "voice": "ru-RU-DmitryNeural",
        "text": (
            "Телефонный звонок раздался в три часа ночи, разрушив тишину пустой квартиры. "
            "Детектив поднял трубку и услышал лишь тяжелое дыхание и знакомый шепот, который он надеялся больше никогда не услышать. "
            "Загадочный аноним знал детали дела десятилетней давности, о которых не упоминалось ни в одном официальном отчете. "
            "Собрав вещи за считанные минуты, детектив отправился на заброшенную пристань."
        )
    },
    "История": {
        "title": "Падение древней цитадели",
        "author": "Виктор Летописец",
        "voice": "ru-RU-DmitryNeural",
        "text": (
            "Строительство древней крепости продолжалось уже более двух десятилетий. "
            "Тысячи мастеров и архитекторов возводили монументальные стены, предназначенные выдержать любые осады. "
            "Правитель лично прибыл на осмотр укреплений перед началом весеннего похода. "
            "От решений, принятых на этом военном совете, зависела судьба целого государства на сотни лет вперед."
        )
    },
    "Наука": {
        "title": "Загадки квантового мира",
        "author": "Профессор Кварк",
        "voice": "ru-RU-DmitryNeural",
        "text": (
            "Изучение квантовой запутанности открывает перед человечеством фундаментальные тайны устроения Вселенной. "
            "Эксперименты показывают, что частицы могут мгновенно реагировать на состояния друг друга вне зависимости от расстояния. "
            "Это явление ставит под вопрос классические представления о пространстве и времени. "
            "Разработка квантовых компьютеров превращает теоретическую физику в основу технологий будущего."
        )
    },
    "Sci-Fi": {
        "title": "Chronicles of Deep Space",
        "author": "Arthur C. Clarke",
        "voice": "en-US-ChristopherNeural",
        "text": (
            "The flagship research vessel emerged from hyperspace at the outer boundary of Sector 7. "
            "Before the crew lay an uncharted planet, shrouded in a dense layer of violet clouds. "
            "Sensors immediately detected a rhythmic artificial signal originating from deep inside a massive crater. "
            "The captain issued the order to prepare the reconnaissance shuttle for landing."
        )
    },
    "Detective": {
        "title": "The Midnight Express Mystery",
        "author": "Sherlock Holmes",
        "voice": "en-US-ChristopherNeural",
        "text": (
            "Rain lashed against the windows of the midnight train as it sped through the dark countryside. "
            "The compartment door was locked from the inside, yet the professor had vanished without a trace. "
            "Only a sealed envelope remained on the table, containing coordinates to an abandoned lighthouse."
        )
    },
    "Horror": {
        "title": "Shadows of the Fog",
        "author": "H.P. Lovecraft",
        "voice": "en-US-ChristopherNeural",
        "text": (
            "An eerie stillness hung over the coastal town as the thick grey fog rolled in from the sea. "
            "Old lanterns flickered along the deserted cobblestone streets, casting long unnerving shadows. "
            "Those who stayed outside past midnight reported hearing strange whispers rising from the ocean depths."
        )
    },
    "Қазақ әдебиеті": {
        "title": "Дала дауылдары",
        "author": "Мұхтар Әуезов",
        "voice": "kk-KZ-DauletNeural",
        "text": (
            "Ұлан-байтақ кең далада соққан суық жел түнгі аспанды бұлтпен торлады. "
            "Қараңғы түнде алыстан ұлыған бөрінің даусы естіліп, ауыл шетіндегі заңғар таулардың етегіне тарады. "
            "Жас жылқышы ат үстінде отырып, айналаға жіті көз тастады. "
            "Осы бір түнде даланың ұлы сыры мен батырлардың көне аңыздары қайта жаңғырғандай болды."
        )
    },
    "Дала сыры": {
        "title": "Көшпенділер жолы",
        "author": "Ілияс Есенберлин",
        "voice": "kk-KZ-DauletNeural",
        "text": (
            "Күн ұясына батқан сәтте сары дала алтын түске бөленді. "
            "Көш керуені тау бөктерімен өтіп, жаңа қонысқа қарай бағыт алды. "
            "Ақсақалдардың айтқан нақыл сөздері мен батырлар жыры ұрпақтан-ұрпаққа жалғасып келеді. "
            "Әрбір төбе мен өзен бойы тарихи оқиғалардың куәсі болған киелі мекен."
        )
    }
}


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


@app.post("/generate")
async def generate_content(req: GenerateRequest):
    raw_query = req.genre.strip()
    clean_genre_key = raw_query.split(" (")[0].strip()
    
    book = None
    
    # 1. Если это точный жанр из нашего списка — берём готовый уникальный сюжет
    if clean_genre_key in DETAILED_STORIES:
        book = DETAILED_STORIES[clean_genre_key]
    else:
        # 2. Если пользователь ввёл название книги в поиск — ищем через API
        book = await search_free_book_google(raw_query)
        
    # 3. Резерв, если в поиске ничего не найдено
    if not book:
        voice = detect_voice(raw_query)
        book = {
            "title": f"Произведение: {clean_genre_key}",
            "author": "Мировая библиотека",
            "voice": voice,
            "text": (
                f"Вы выбрали произведение по запросу '{clean_genre_key}'. "
                "Это захватывающая история с оригинальным сюжетом и глубоким смыслом. "
                "Вы можете сохранить полный текст книги в виде PDF файла для комфортного чтения."
            )
        }

    # 4. Озвучка EdgeTTS
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)
    communicate = edge_tts.Communicate(book["text"][:3000], voice=book["voice"])
    await communicate.save(audio_path)

    # 5. Генерация PDF
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