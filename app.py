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


@app.post("/resolve")
def resolve_media(request: DownloadRequest):
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

            direct_url = info.get("url")

            if not direct_url:
                for fmt in reversed(info.get("formats", [])):
                    if fmt.get("url"):
                        direct_url = fmt["url"]
                        break

            if not direct_url:
                raise HTTPException(
                    status_code=404,
                    detail="No direct media stream"
                )

            return {
                "success": True,
                "title": info.get("title"),
                "platform": info.get("extractor_key"),
                "mimeType": info.get("mime_type"),
                "extension": info.get("ext"),
                "directMediaUrl": direct_url
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Media could not be resolved: {str(e)}"
        )


@app.post("/download")
def download_media(request: DownloadRequest):
    url = request.url.strip()

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL")

    job_id = str(uuid.uuid4())

    output_template = os.path.join(
        DOWNLOAD_DIR,
        job_id + ".%(ext)s"
    )

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
            raise Exception("Downloaded file was not created")

        return FileResponse(
            filename,
            media_type="video/mp4",
            filename=os.path.basename(filename)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(e)}"
        )
