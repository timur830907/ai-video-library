import os
import uuid
import asyncio
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from gtts import gTTS

# Автоматическое создание папки для статических файлов
os.makedirs("static", exist_ok=True)

app = FastAPI(title="AI Video Library API")

# Настройка CORS для работы с GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение статической папки для раздачи аудиофайлов
app.mount("/static", StaticFiles(directory="static"), name="static")


class GenerateRequest(BaseModel):
    user_id: str
    genre: str


# Фейковое хранилище пользователей и периода подписки
users_db = {
    "user_github_demo": {"days_left": 30}
}


@app.get("/")
def root():
    return {"status": "ok", "message": "AI Video Library Backend is running!"}


@app.post("/generate")
async def generate_content(req: GenerateRequest):
    # Проверка подписки / триала
    user = users_db.get(req.user_id, {"days_left": 30})
    if user["days_left"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription expired"
        )

    # Генерация текста на основе выбранного жанра
    genre_content = {
        "Фантастика": {
            "title": "Звездный рубеж",
            "author": "ИИ Фантаст",
            "text": "Корабль 'Гелиос' вышел из гиперпространства на орбите неизвестной планеты. Детекторы зафиксировали странный сигнал из глубин кратера."
        },
        "Детектив": {
            "title": "Тайна вечернего экспресса",
            "author": "ИИ Детектив",
            "text": "Дождь стучал по стеклу купе. Сыщик внимательно осмотрел оставленный на столе конверт с сургучной печатью."
        },
        "Романтика": {
            "title": "Встреча у моря",
            "author": "ИИ Романтик",
            "text": "Закат окрасил волны в золотистый цвет. Океанский бриз приносил прохладу, пока они молча шли по песчаному берегу."
        },
        "Ужасы": {
            "title": "Шепот в темноте",
            "author": "ИИ Хоррор",
            "text": "Старый дом скрипел под порывами ветра. Из подвала донесся тихий, но отчетливый звук шагов."
        }
    }

    book_info = genre_content.get(
        req.genre,
        {
            "title": "Сгенерированная история",
            "author": "ИИ Автор",
            "text": f"История в жанре {req.genre}."
        }
    )

    # Генерация аудиозаписи с помощью gTTS (Google Text-to-Speech)
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)
    
    tts = gTTS(text=book_info["text"], lang="ru")
    tts.save(audio_path)

    # Пример ссылки на фоновое видео (Pexels / CDN)
    video_url = "https://assets.mixkit.co/videos/preview/mixkit-starry-night-sky-with-a-flying-meteor-42864-large.mp4"

    return {
        "book": book_info,
        "audio_url": f"/static/{audio_filename}",
        "video_url": video_url
    }