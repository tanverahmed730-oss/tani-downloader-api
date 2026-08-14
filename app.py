from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="Tani Downloader API")


class ResolveRequest(BaseModel):
    url: str


@app.get("/")
def home():
    return {
        "status": "online",
        "service": "Tani Downloader API"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/resolve")
def resolve_media(request: ResolveRequest):
    url = request.url.strip()

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL")

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "format": "best[ext=mp4]/best",
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)

            formats = info.get("formats", [])

            if not formats:
                raise HTTPException(
                    status_code=404,
                    detail="No media formats found"
                )

            selected = None

            for fmt in reversed(formats):
                direct_url = fmt.get("url")
                if direct_url:
                    selected = fmt
                    break

            if not selected:
                raise HTTPException(
                    status_code=404,
                    detail="No direct media URL available"
                )

            return {
                "success": True,
                "title": info.get("title"),
                "platform": info.get("extractor_key"),
                "mimeType": selected.get("mime_type"),
                "extension": selected.get("ext"),
                "directMediaUrl": selected.get("url")
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Media could not be resolved: {str(e)}"
        )
