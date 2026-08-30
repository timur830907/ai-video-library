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

def clean_html(raw_html: str) -> str:
    """Очищает полученный из API текст от тегов HTML"""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.replace('\n', ' ').strip()

def detect_language_and_voice(text_or_genre: str):
    """Определяет язык и соответствующий голосовой движок EdgeTTS"""
    # Казахский
    if any(c in text_or_genre for c in "ӘәҒғҚқҢңӨөҰұҮүІіҺһ") or "Қазақ" in text_or_genre or "Дала" in text_or_genre:
        return "kk", "kk-KZ-DauletNeural"
    # Английский
    elif re.search(r'[a-zA-Z]', text_or_genre) and not re.search(r'[а-яА-Я]', text_or_genre):
        return "en", "en-US-ChristopherNeural"
    # Русский (по умолчанию)
    else:
        return "ru", "ru-RU-DmitryNeural"

async def fetch_book_from_google(genre: str):
    lang_code, voice = detect_language_and_voice(genre)
    url = f"https://www.googleapis.com/books/v1/volumes?q={genre}&langRestrict={lang_code}&maxResults=20"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                valid_items = [i for i in items if i.get("volumeInfo", {}).get("description")]
                
                if valid_items:
                    chosen = random.choice(valid_items)["volumeInfo"]
                    desc = clean_html(chosen.get("description", ""))
                    if len(desc) > 50:
                        return {
                            "title": chosen.get("title", genre),
                            "author": ", ".join(chosen.get("authors", ["Неизвестный автор"])),
                            "text": desc,
                            "voice": voice
                        }
    except Exception as e:
        print(f"Google Books API Error: {e}")
        
    # Резервный развернутый вариант (если API отдал пустой ответ)
    if lang_code == "kk":
        return {
            "title": "Көксерек пен Дала сыры",
            "author": "Мұхтар Әуезов",
            "text": "Ұлан-байтақ кең далада соққан суық жел түнгі аспанды бұлтпен торлады. Қараңғы түнде алыстан ұлыған бөрінің даусы естіліп, ауыл шетіндегі заңғар таулардың етегіне тарады. Жас жылқышы ат үстінде отырып, айналаға жіті көз тастады. Осы бір түнде даланың ұлы сыры мен батырлардың көне аңыздары қайта жаңғырғандай болды.",
            "voice": voice
        }
    elif lang_code == "en":
        return {
            "title": "Chronicles of Deep Space",
            "author": "Arthur C. Clarke",
            "text": "The flagship research vessel emerged from hyperspace at the outer boundary of Sector 7. Before the crew lay an uncharted planet, shrouded in a dense layer of violet clouds. Sensors immediately detected a rhythmic artificial signal originating from deep inside a massive crater. The captain issued the order to prepare the reconnaissance shuttle for landing.",
            "voice": voice
        }
    else:
        return {
            "title": "Операция 'Неуклюжий агент'",
            "author": "Марк Твен",
            "text": "Попытка незаметно внедрить нового сотрудника в отдел продаж провалилась в первые же пять минут. Сначала он случайно перепутал кабинеты и провел часовую презентацию маркетинговой стратегии перед курьерами. Затем, пытаясь исправить ситуацию, пролил кофе на главный сервер компании, вызвав перезагрузку всей сети. Однако благодаря невероятной харизме, к концу дня его назначили руководителем антикризисного комитета.",
            "voice": voice
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
    book = await fetch_book_from_google(req.genre)

    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)

    # Генерация длительной озвучки на родном языке книги
    communicate = edge_tts.Communicate(book["text"], voice=book["voice"])
    await communicate.save(audio_path)

    return {
        "book": {
            "title": book["title"],
            "author": book["author"],
            "text": book["text"]
        },
        "audio_url": f"/static/{audio_filename}",
        "video_url": random.choice(VIDEO_SOURCES)
    }