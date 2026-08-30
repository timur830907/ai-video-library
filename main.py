@app.post("/generate")
async def generate_content(req: GenerateRequest):
    query = req.genre.strip()
    
    # 1. Поиск книги через API
    book = await search_free_book_google(query)
    
    # 2. Взнос из базового резерва, если поиск пуст
    if not book:
        lang_code, voice = detect_language_and_voice(query)
        book = {
            "title": f"Результат по запросу: {query}",
            "author": "Библиотечный фонд",
            "voice": voice,
            "text": (
                f"Вы искали: '{query}'. По данному запросу сформирован ознакомительный материал. "
                "Каждая страница содержит важные сведения, позволяющие глубже погрузиться в тему. "
                "Вы можете скачать данный материал в формате PDF для удобного чтения."
            )
        }

    # 3. Генерация аудио через EdgeTTS
    audio_text = book["text"][:3000]
    audio_filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = os.path.join("static", audio_filename)
    
    communicate = edge_tts.Communicate(audio_text, voice=book["voice"])
    await communicate.save(audio_path)

    # 4. Генерация PDF
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