"""Validated, normalized local cover storage."""
import io
import os
import uuid
import warnings
from html.parser import HTMLParser
from pathlib import Path

from config import settings

MAX_UPLOAD = 5_000_000


class _CoverMetaParser(HTMLParser):
    """Read only the image metadata used for optional automatic covers (REQ-010)."""
    def __init__(self):
        super().__init__()
        self.cover: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            data = dict(attrs)
            if data.get("property") == "og:image" or data.get("name") == "image":
                self.cover = data.get("content")


def cover_root() -> Path:
    if settings.COVER_DIR == "./covers" and settings.DATABASE_URL.startswith("sqlite:////data/"):
        return Path("/data/covers")
    return Path(settings.COVER_DIR)


def cover_path(filename: str) -> Path:
    if not filename or filename != Path(filename).name or not filename.endswith(".jpg"):
        raise ValueError("Invalid cover filename.")
    return cover_root() / filename


def save_cover(raw: bytes) -> str:
    if len(raw) > MAX_UPLOAD:
        raise ValueError("Cover exceeds 5 MB.")
    from PIL import Image, UnidentifiedImageError
    try:
        Image.MAX_IMAGE_PIXELS = 25_000_000
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Use JPEG, PNG, or WebP.")
            if image.width * image.height > 25_000_000:
                raise ValueError("Cover dimensions are too large.")
            image.load()
            image = image.convert("RGB")
            image.thumbnail((1200, 1600))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Invalid image file.") from exc
    directory = cover_root()
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    temporary = directory / f".{filename}.tmp"
    image.save(temporary, format="JPEG", quality=85, optimize=True)
    os.replace(temporary, directory / filename)
    return filename


async def fetch_cover(source_url: str) -> str | None:
    from services.checking.http import safe_get
    from urllib.parse import urljoin
    try:
        status, final_url, body, _ = await safe_get(source_url)
        if status >= 400:
            return None
        parser = _CoverMetaParser()
        parser.feed(body.decode("utf-8", "replace"))
        if not parser.cover:
            return None
        image_url = urljoin(final_url, parser.cover)
        status, _, raw, headers = await safe_get(image_url, max_bytes=MAX_UPLOAD + 1)
        if status != 200 or not headers.get("content-type", "").lower().startswith("image/"):
            return None
        return save_cover(raw)
    except Exception:
        return None
