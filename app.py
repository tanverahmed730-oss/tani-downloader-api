from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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

        file_size = os.path.getsize(filename)

        def file_stream():
            try:
                with open(filename, "rb") as file:
                    while True:
                        chunk = file.read(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    os.remove(filename)
                except Exception:
                    pass

        return StreamingResponse(
            file_stream(),
            media_type="video/mp4",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{os.path.basename(filename)}"',
                "Content-Length": str(file_size),
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(e)}"
        )
