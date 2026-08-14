from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid

app = FastAPI(title="Tani Downloader API")

DOWNLOAD_DIR = "/tmp/tani_downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


class MediaRequest(BaseModel):
    url: str


def validate_url(url: str):
    url = url.strip()

    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL"
        )

    return url


def get_platform(info):
    extractor = (
        info.get("extractor_key")
        or info.get("extractor")
        or ""
    )

    return extractor


def create_ydl_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,

        # Prefer MP4 when available.
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "best[ext=mp4]/"
            "best"
        ),

        "merge_output_format": "mp4",

        # Avoid unnecessary interactive behaviour.
        "noprogress": True,
    }


@app.get("/")
def home():
    return {
        "status": "online",
        "service": "Tani Downloader API",
        "supported": [
            "YouTube",
            "TikTok",
            "Facebook",
            "Instagram",
            "Snapchat"
        ]
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.post("/resolve")
def resolve_media(request: MediaRequest):
    url = validate_url(request.url)

    options = create_ydl_options()
    options["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

            direct_url = info.get("url")

            if not direct_url:
                formats = info.get("formats", [])

                # Find the best usable single media URL.
                for fmt in reversed(formats):
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
                "platform": get_platform(info),
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
def download_media(request: MediaRequest):
    url = validate_url(request.url)

    job_id = str(uuid.uuid4())

    output_template = os.path.join(
        DOWNLOAD_DIR,
        job_id + ".%(ext)s"
    )

    options = create_ydl_options()
    options["outtmpl"] = output_template

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=True
            )

            filename = ydl.prepare_filename(info)

        # yt-dlp can merge/convert to mp4, so check the
        # actual generated file and possible mp4 variant.
        if not os.path.exists(filename):
            base, _ = os.path.splitext(filename)
            mp4_filename = base + ".mp4"

            if os.path.exists(mp4_filename):
                filename = mp4_filename
            else:
                raise Exception(
                    "Downloaded file was not created"
                )

        return FileResponse(
            path=filename,
            media_type="video/mp4",
            filename=os.path.basename(filename)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(e)}"
        )
