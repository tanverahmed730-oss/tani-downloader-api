from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid

app = FastAPI(title="Tani Downloader API")

DOWNLOAD_DIR = "/tmp/tani_downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


class DownloadRequest(BaseModel):
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


@app.post("/download")
def download_media(request: DownloadRequest):
    url = request.url.strip()

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL")

    job_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, job_id + ".%(ext)s")

    options = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "format": "best[ext=mp4]/best",
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if not os.path.exists(filename):
            raise HTTPException(
                status_code=500,
                detail="Downloaded file was not created"
            )

        return FileResponse(
            path=filename,
            media_type="video/mp4",
            filename=os.path.basename(filename)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Media could not be processed: {str(e)}"
        )
