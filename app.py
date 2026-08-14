from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import glob

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
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,

        # Prefer a single downloadable MP4 first.
        "format": (
            "best[ext=mp4]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "best"
        ),

        "merge_output_format": "mp4",

        # More compatible HTTP behaviour.
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },

        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,

        # Do not abort the whole extraction because of one unavailable format.
        "ignoreerrors": False,
    }

    if output_template:
        options["outtmpl"] = output_template

    return options


@app.get("/")
def home():
    return {
        "status": "online",
        "service": "Tani Downloader API",
        "version": "2.0",
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
    """
    Resolve metadata only.

    IMPORTANT:
    This endpoint does NOT depend on returning a direct media URL.
    The Android app should eventually use /download instead.
    """

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
            raise HTTPException(
                status_code=404,
                detail="Video information could not be found"
            )

        return {
            "success": True,
            "title": info.get("title"),
            "platform": get_platform(info),
            "extension": info.get("ext"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "message": "Media detected. Use /download to download."
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
    """
    Download the media on the server and return the actual file.

    The client does NOT download a direct TikTok/YouTube CDN URL.
    The server downloads the media first and then sends the file
    back to the client.
    """

    url = validate_url(request.url)

    job_id = str(uuid.uuid4())

    output_template = os.path.join(
        DOWNLOAD_DIR,
        job_id + ".%(ext)s"
    )

    options = create_ydl_options(output_template)

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=True
            )

            if not info:
                raise Exception(
                    "Extractor returned no media information"
                )

            prepared_filename = ydl.prepare_filename(info)

        # Look for the actual generated file.
        possible_files = []

        if os.path.exists(prepared_filename):
            possible_files.append(prepared_filename)

        base = os.path.splitext(prepared_filename)[0]

        for extension in [
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".m4a",
            ".avi"
        ]:
            possible_files.append(base + extension)

        # Also search by job ID in case yt-dlp changed the extension.
        possible_files.extend(
            glob.glob(
                os.path.join(
                    DOWNLOAD_DIR,
                    job_id + ".*"
                )
            )
        )

        filename = None

        for file_path in possible_files:
            if os.path.isfile(file_path):
                filename = file_path
                break

        if not filename:
            raise Exception(
                "Downloaded file was not created"
            )

        # Detect media type.
        extension = os.path.splitext(filename)[1].lower()

        media_types = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".m4a": "audio/mp4",
        }

        media_type = media_types.get(
            extension,
            "application/octet-stream"
        )

        return FileResponse(
            path=filename,
            media_type=media_type,
            filename=os.path.basename(filename)
        )

    except HTTPException:
        raise

    except Exception as e:
        error_text = str(e)

        # Give useful errors instead of hiding everything behind
        # an unexplained generic 500.
        if "403" in error_text:
            detail = (
                "The platform rejected the server download request "
                "(HTTP 403). The media requires a different extractor "
                "or access method."
            )

        elif "Sign in" in error_text or "login" in error_text.lower():
            detail = (
                "This media requires login/authentication and cannot "
                "be downloaded anonymously."
            )

        elif "Unsupported URL" in error_text:
            detail = (
                "This URL is not currently supported by yt-dlp."
            )

        else:
            detail = f"Download failed: {error_text}"

        raise HTTPException(
            status_code=502,
            detail=detail
        )
