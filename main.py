import os
import uuid
import random
import edge_tts
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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

def generate_multilingual_story(genre: str):
    g = genre.strip().lower()

    # Казахский язык
    if "қазақ" in g or "эпос" in g or "детектив (kk)" in g or "романдар" in g:
        return {
            "title": "Көксерек пен Дала сыры",
            "author": "Мұхтар Әуезов",
            "voice": "kk-KZ-DauletNeural",
            "text": (
                "Ұлан-байтақ кең далада соққан суық жел түнгі аспанды бұлтпен торлады. "
                "Қараңғы түнде алыстан ұлыған бөрінің даусы естіліп, ауыл шетіндегі заңғар таулардың етегіне тарады. "
                "Жас жылқышы ат үстінде отырып, айналаға жіті көз тастады. "
                "Осы бір түнде даланың ұлы сыры мен батырлардың көне аңыздары қайта жаңғырғандай болды."
            )
        }

    # Английский язык
    elif "sci-fi" in g or "fantasy (en)" in g or "thriller (en)" in g or "english" in g:
        return {
            "title": "Chronicles of the Deep Space",
            "author": "Arthur C. Clarke",
            "voice": "en-US-ChristopherNeural",
            "text": (
                "The flagship research vessel emerged from hyperspace at the outer boundary of Sector 7. "
                "Before the crew lay an uncharted planet, shrouded in a dense layer of violet clouds. "
                "Sensors immediately detected a rhythmic artificial signal originating from deep inside a massive crater. "
                "The captain issued the order to prepare the reconnaissance shuttle for landing."
            )
        }

    # Русский язык (по умолчанию и для других жанров)
    elif "комед" in g:
        return {
            "title": "Операция 'Неуклюжий агент'",
            "author": "Марк Твен",
            "voice": "ru-RU-DmitryNeural",
            "text": (
                "Попытка незаметно внедрить нового сотрудника в отдел продаж провалилась в первые же пять минут. "
                "Сначала он случайно перепутал кабинеты и провел часовую презентацию перед курьерами. "
                "Затем, пытаясь исправить ситуацию, пролил кофе на главный сервер компании, вызвав перезагрузку всей сети."
            )
        }
    elif "боевик" in g:
        return {
            "title": "Последний рубеж обороны",
            "author": "Джон Хантер",
            "voice": "ru-RU-DmitryNeural",
            "text": (
                "Взрыв прогремел на верхнем этаже комплекса, разбив панорамные стекла и озарив ночное небо вспышкой. "
                "Спецотряд заблокировал все выходы, но у группы эвакуации оставался последний шанс прорваться через крышу. "
                "Перезарядив автомат, командир отдал сигнал к началу операции."
            )
        }
    elif "триллер" in g:
        return {
            "title": "Тень над городом",
            "author": "Стивен Кинг",
            "voice": "ru-RU-DmitryNeural",
            "text": (
                "Телефонный звонок раздался в три часа ночи, разрушив тишину пустой квартиры. "
                "Детектив поднял трубку и услышал лишь тяжелое дыхание и знакомый шепот. "
                "Загадочный аноним знал детали дела десятилетней давности, о которых не упоминалось ни в одном отчете."
            )
        }
    else:
        return {
            "title": "Звездные скитальцы",
            "author": "Аркадий Стругацкий",
            "voice": "ru-RU-DmitryNeural",
            "text": (
                "Флагманский исследовательский крейсер вышел из гиперпространственного прыжка у границы сектора Орион. "
                "Перед экипажем простиралась безымянная планета, окутанная плотным слоем фиолетовой атмосферы. "
                "Детекторы зафиксировали регулярный импульсный сигнал из глубин тектонического разлома."
            )
        }

VIDEO_SOURCES = [
    "https://vjs.zencdn.net/v/oceans.mp4",
    "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
]

@app.get("/")
def root():
    return {"status": "ok", "message": "Multilingual TTS API running"}

@app.post("/generate")
async def generate_content(req: GenerateRequest):
    story = generate_multilingual_story(req.genre)

    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)

    # Генерация озвучки с выбором соответствующего голоса и языка
    communicate = edge_tts.Communicate(story["text"], voice=story["voice"])
    await communicate.save(audio_path)

    return {
        "book": {
            "title": story["title"],
            "author": story["author"],
            "text": story["text"]
        },
        "audio_url": f"/static/{audio_filename}",
        "video_url": random.choice(VIDEO_SOURCES)
    }