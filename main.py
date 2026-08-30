async def search_free_book_google(query: str):
    clean_query = query.split("(")[0].strip()
    url = f"https://www.googleapis.com/books/v1/volumes?q={clean_query}&maxResults=5"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    info = item.get("volumeInfo", {})
                    desc = info.get("description", "")
                    if desc and len(desc) > 50:
                        return {
                            "title": info.get("title", clean_query),
                            "author": ", ".join(info.get("authors", ["Известный автор"])),
                            "voice": detect_voice(query),
                            "text": clean_html(desc)
                        }
    except Exception as e:
        print("Google Books API error:", e)
    return None