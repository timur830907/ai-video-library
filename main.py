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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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

# Функция создания PDF-файла для скачивания
def create_pdf(filename: str, title: str, author: str, text: str):
    pdf_path = os.path.join("static", filename)
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    # Заголовок и автор
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, title)
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, f"Author: {author}")
    c.line(50, height - 80, width - 50, height - 80)
    
    # Отрисовка текста с переносом строк
    c.setFont("Helvetica", 10)
    y = height - 100
    words = text.split()
    line = ""
    for word in words:
        if len(line + " " + word) < 80:
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

# Уникальные объёмные главы для всех жанров (длительная озвучка)
DETAILED_STORIES = {
    "Фантастика": {
        "title": "Звездные скитальцы: Глава 1",
        "author": "Аркадий Стругацкий",
        "voice": "ru-RU-DmitryNeural",
        "text": (
            "Флагманский исследовательский крейсер вышел из гиперпространственного прыжка у самой границы сектора Орион. "
            "Перед экипажем простиралась безымянная планета, окутанная плотным слоем фиолетовой атмосферы. "
            "Детекторы зафиксировали регулярный импульсный сигнал из глубин тектонического разлома. "
            "Капитан отдал приказ спустить разведывательный модуль. Команда понимала, что данный сигнал не мог "
            "быть естественного происхождения: это было древнее послание цивилизации, опередившей человечество на миллионы лет. "
            "Каждый шаг по поверхности неизвестного мира приближал исследователей к разгадке величайшей тайны галактики. "
            "Анализаторы атмосферы показали наличие неизвестных изотопов, а сканеры засекли подземные структуры гигантских размеров."
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
            "Однако благодаря невероятной харизме и непоколебимому оптимизму, к концу дня его назначили руководителем антикризисного комитета. "
            "На первом же совещании с инвесторами он уронил главный микрофон, но озвученная им в шутку фраза принесла компании миллионный контракт."
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
            "Под непрерывным перекрестным огнем бойцы двигались от укрытия к укрытию, преодолевая сопротивление превосходящих сил противника. "
            "Скупые секунды решали исход всей военной кампании. Позади оставались горящие переходы, а впереди ждала посадочная площадка."
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
            "Собрав вещи за считанные минуты, детектив отправился на заброшенную пристань. "
            "Каждый шаг по тёмным улицам сопровождался чувством, что за ним пристально наблюдают из затененных переулков."
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
            "От решений, принятых на этом военном совете, зависела судьба целого государства на сотни лет вперед. "
            "Летописи сохранили имена тех, кто стоял у истоков создания великой империи и защищал её границы от иноземных завоевателей."
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
            "Разработка квантовых компьютеров и новых методов передачи данных превращает теоретическую физику "
            "в основу технологий будущего, способных кардинально изменить информационные системы."
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
            "The captain issued the order to prepare the reconnaissance shuttle for landing. "
            "The silence on the bridge was deafening as everyone realized the signal could not be natural."
        )
    },
    "Detective": {
        "title": "The Midnight Express Mystery",
        "author": "Sherlock Holmes",
        "voice": "en-US-ChristopherNeural",
        "text": (
            "Rain lashed against the windows of the midnight train as it sped through the dark countryside. "
            "The compartment door was locked from the inside, yet the professor had vanished without a trace. "
            "Only a sealed envelope remained on the table, containing coordinates to an abandoned lighthouse. "
            "Every clue pointed to a meticulously engineered plot that began years ago."
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

VIDEO_SOURCES = [
    "https://vjs.zencdn.net/v/oceans.mp4",
    "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
]

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/generate")
async def generate_content(req: GenerateRequest):
    # Очищаем название жанра от скобок (RU, EN, KK)
    clean_genre_key = req.genre.split(" (")[0].strip()
    
    # Получаем книгу из нашей точно настроенной базы по ключу жанра
    story = DETAILED_STORIES.get(clean_genre_key, DETAILED_STORIES["Фантастика"])

    # 1. Генерация аудио через EdgeTTS
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)
    communicate = edge_tts.Communicate(story["text"], voice=story["voice"])
    await communicate.save(audio_path)

    # 2. Генерация PDF-документа книги для скачивания
    pdf_filename = f"book_{uuid.uuid4().hex[:8]}.pdf"
    pdf_url = create_pdf(pdf_filename, story["title"], story["author"], story["text"])

    return {
        "book": {
            "title": story["title"],
            "author": story["author"],
            "text": story["text"]
        },
        "audio_url": f"/static/{audio_filename}",
        "pdf_url": pdf_url,
        "video_url": random.choice(VIDEO_SOURCES)
    }