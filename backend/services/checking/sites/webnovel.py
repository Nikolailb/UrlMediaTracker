"""WebNovel book catalog reader (REQ-017).

WebNovel chapter IDs are opaque. Read the book-scoped catalog instead of
guessing URLs or probing sequential IDs.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

from services.checking.browser import BrowserFetchError, browser_get
from services.checking.http import _challenge, safe_get
from services.checking.results import ChapterLink, Extraction

METHOD = "WEBNOVEL"
MAX_PAGE_BYTES = 5_000_000
_BOOK_PATH = re.compile(r"/book/(?:[a-z0-9-]+_)?([0-9]+)(?:/([0-9]+)|/catalog)?/?", re.I)
_BAD_JS_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')


def series_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or
                (parts.hostname or "").lower() not in {"webnovel.com", "www.webnovel.com"} or
                parts.port or parts.username or parts.password or parts.query or parts.fragment):
            return None
    except ValueError:
        return None
    match = _BOOK_PATH.fullmatch(parts.path)
    return f"https://www.webnovel.com/book/{match.group(1)}" if match else None


class _BookPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.book_scripts: list[str] = []
        self._script: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "meta":
            key = data.get("property") or data.get("name")
            if key:
                self.meta[key.lower()] = data.get("content", "")
        if tag == "script":
            self._script = []

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            script = "".join(self._script)
            if "g_data.book" in script:
                self.book_scripts.append(script)
            self._script = None


def _chapter_id(value) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9]{8,25}", value) else None


def _link(base: str, entry: dict) -> ChapterLink | None:
    index = entry.get("chapterIndex")
    chapter_id = _chapter_id(entry.get("chapterId"))
    if not isinstance(index, int) or isinstance(index, bool) or index < 1 or not chapter_id:
        return None
    return ChapterLink(str(index), f"{base}/{chapter_id}", source_page=base)


def parse_webnovel(html: str, url: str) -> Extraction:
    base = series_url(url)
    if not base:
        return Extraction("UNSUPPORTED", METHOD)
    parser = _BookPage()
    parser.feed(html)
    if len(parser.book_scripts) != 1:
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Book catalog script is missing or ambiguous."])
    script = parser.book_scripts[0]
    match = re.search(r"\bg_data\.book\s*=\s*", script)
    if not match:
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Book catalog data is missing."])
    try:
        # WebNovel emits JavaScript-only escapes such as backslash-space in text.
        # Remove only escapes JSON cannot represent; never execute page script.
        data, _ = json.JSONDecoder().raw_decode(_BAD_JS_ESCAPE.sub("", script[match.end():]).lstrip())
    except (ValueError, TypeError):
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Book catalog data could not be decoded."])
    if not isinstance(data, dict):
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Book catalog has an unexpected shape."])
    info = data.get("bookInfo")
    if not isinstance(info, dict) or str(info.get("bookId")) != base.rsplit("/", 1)[-1]:
        return Extraction("CONTRADICTORY", METHOD, warnings=["Catalog book ID does not match the requested book."])
    volumes = data.get("volumeItems")
    last = data.get("lastChapterItem")
    if not isinstance(volumes, list) or not isinstance(last, dict):
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Chapter catalog or latest entry is missing."])
    entries = [entry for volume in volumes if isinstance(volume, dict)
               for entry in volume.get("chapterItems", []) if isinstance(entry, dict)]
    links = [_link(base, entry) for entry in entries]
    links = [link for link in links if link]
    if not links:
        return Extraction("EMPTY", METHOD, warnings=["No numbered chapters are present in this catalog."])
    latest = _link(base, last)
    maximum = max(links, key=lambda link: int(link.chapter))
    if not latest or latest != maximum:
        return Extraction("CONTRADICTORY", METHOD, warnings=["Latest chapter and catalog entries disagree."])
    first = min(links, key=lambda link: int(link.chapter))
    if first.chapter != "1" or info.get("firstChapterId") != first.url.rsplit("/", 1)[-1]:
        return Extraction("CONTRADICTORY", METHOD, warnings=["First chapter and catalog entries disagree."])
    # Auxiliary chapters may have index -1, so the total count is not a chapter number.
    cover = parser.meta.get("og:image") or None
    return Extraction("OK", METHOD, latest, [first, latest], confidence="HIGH",
                      title=info.get("bookName") or None, cover_url=cover,
                      first_url=first.url, checked_page_url=base)


async def fetch_webnovel(url: str) -> tuple[int, str, bytes, dict[str, str], bool]:
    """One direct request, with one browser retry only for a challenged source."""
    try:
        status, final, body, headers = await safe_get(url, max_bytes=MAX_PAGE_BYTES + 1)
    except (httpx.ConnectError, httpx.TimeoutException):
        status, final, body, headers = await browser_get(
            url, purpose="SITE_SCRAPER", max_bytes=MAX_PAGE_BYTES + 1)
        return status, final, body, headers, True
    if _challenge(status, body, headers):
        try:
            status, final, body, headers = await browser_get(
                url, purpose="SITE_SCRAPER", max_bytes=MAX_PAGE_BYTES + 1)
            return status, final, body, headers, True
        except BrowserFetchError as exc:
            if "too large" in str(exc).lower() or "size limit" in str(exc).lower():
                raise
            pass
    return status, final, body, headers, False
