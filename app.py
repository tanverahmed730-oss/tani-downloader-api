from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import glob
import shutil

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
    return (
        info.get("extractor_key")
        or info.get("extractor")
        or "Unknown"
    )


def create_ydl_options(output_template=None):
    options = {
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,
        "noprogress": True,

        # Prefer MP4 when available.
        "format": (
            "best[ext=mp4]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "best"
        ),

        "merge_output_format": "mp4",

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },

        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,

        # Important for servers.
        "continuedl": True,

        # Don't download playlists.
        "noplaylist": True,

        # Keep the output clean.
        "overwrites": True,
    }

    if output_template:
        options["outtmpl"] = output_template

    return options


@app.get("/")
def home():
    return {
        "status": "online",
        "service": "Tani Downloader API",
        "version": "3.0",
        "endpoints": {
            "health": "/health",
            "resolve": "/resolve",
            "download": "/download"
        }
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "yt_dlp_version": getattr(
            yt_dlp.version,
            "__version__",
            "unknown"
        )
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

        if not info:
            raise Exception(
                "Extractor returned no media information"
            )

        return {
            "success": True,
            "title": info.get("title"),
            "platform": get_platform(info),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "extension": info.get("ext"),
            "message": "Media detected successfully."
        }

    except Exception as e:

        error = str(e)

        if "Sign in to confirm" in error:
            raise HTTPException(
                status_code=403,
                detail=(
                    "This media is currently protected by the "
                    "platform and requires authentication or "
                    "anti-bot verification. Anonymous download "
                    "is not available for this media."
                )
            )

        if "login" in error.lower() or "authentication" in error.lower():
            raise HTTPException(
                status_code=403,
                detail=(
                    "This media requires authentication. "
                    "Tani Downloader only supports publicly "
                    "accessible media without account login."
                )
            )

        if "403" in error:
            raise HTTPException(
                status_code=403,
                detail=(
                    "The platform rejected the media request "
                    "(HTTP 403). This is a platform-side "
                    "access restriction, not an Android app error."
                )
            )

        if "Unsupported URL" in error:
            raise HTTPException(
                status_code=400,
                detail="This URL is not supported."
            )

        raise HTTPException(
            status_code=502,
            detail=f"Media could not be resolved: {error}"
        )


@app.post("/download")
def download_media(request: MediaRequest):

    url = validate_url(request.url)

    job_id = str(uuid.uuid4())

    output_template = os.path.join(
        DOWNLOAD_DIR,
        job_id + ".%(ext)s"
    )

    options = create_ydl_options(
        output_template
    )

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            if not info:
                raise Exception(
                    "No media information returned."
                )

            prepared_filename = ydl.prepare_filename(
                info
            )

        # Find downloaded file.
        possible_files = []

        if os.path.isfile(prepared_filename):
            possible_files.append(
                prepared_filename
            )

        base = os.path.splitext(
            prepared_filename
        )[0]

        for extension in [
            ".mp4",
            ".webm",
            ".mkv",
            ".mov",
            ".avi",
            ".m4a",
            ".mp3"
        ]:
            possible_files.append(
                base + extension
            )

        possible_files.extend(
            glob.glob(
                os.path.join(
                    DOWNLOAD_DIR,
                    job_id + ".*"
                )
            )
        )

        filename = None

        for path in possible_files:
            if os.path.isfile(path):
                filename = path
                break

        if not filename:
            raise Exception(
                "Download completed but the output file "
                "could not be found."
            )

        extension = os.path.splitext(
            filename
        )[1].lower()

        media_types = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".m4a": "audio/mp4",
            ".mp3": "audio/mpeg"
        }

        media_type = media_types.get(
            extension,
            "application/octet-stream"
        )

        return FileResponse(
            path=filename,
            media_type=media_type,
            filename=os.path.basename(filename),
            background=None
        )

    except Exception as e:

        error = str(e)

        if "Sign in to confirm" in error:
            detail = (
                "This media requires authentication or "
                "anti-bot verification and cannot be "
                "downloaded anonymously."
            )

            raise HTTPException(
                status_code=403,
                detail=detail
            )

        if (
            "login" in error.lower()
            or "authentication" in error.lower()
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "This media requires authentication. "
                    "Only publicly accessible media can "
                    "be downloaded."
                )
            )

        if "403" in error:
            detail = (
                "The platform rejected the download request "
                "(HTTP 403). The media is currently protected "
                "or requires an access method not available "
                "to anonymous server downloads."
            )

            raise HTTPException(
                status_code=403,
                detail=detail
            )

        if "Unsupported URL" in error:
            raise HTTPException(
                status_code=400,
                detail="This URL is not supported."
            )

        raise HTTPException(
            status_code=502,
            detail=f"Download failed: {error}"
        )
