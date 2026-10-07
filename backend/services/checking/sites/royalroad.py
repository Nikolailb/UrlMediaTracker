"""Royal Road fiction catalog reader (REQ-018).

The fiction ID is the stable source key. Chapter titles and URL slugs can
change or restart within a volume; the catalog's zero-based order is used.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from services.checking.browser import BrowserFetchError, browser_get
from services.checking.http import _challenge, safe_get
from services.checking.results import ChapterLink, Extraction

METHOD = "ROYALROAD"
MAX_PAGE_BYTES = 3_000_000
_FICTION_PATH = re.compile(r"/fiction/([0-9]+)(?:/([a-z0-9-]+))?(?:/chapter/([0-9]+)(?:/[a-z0-9-]+)?)?/?", re.I)
_CHAPTER_PATH = re.compile(r"/fiction/([0-9]+)/[a-z0-9-]+/chapter/([0-9]+)/[a-z0-9-]+/?", re.I)


def series_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or
                (parts.hostname or "").lower() not in {"royalroad.com", "www.royalroad.com"} or
                parts.port or parts.username or parts.password):
            return None
    except ValueError:
        return None
    match = _FICTION_PATH.fullmatch(parts.path)
    return f"https://www.royalroad.com/fiction/{match.group(1)}" if match else None


class _FictionPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.chapter_scripts: list[str] = []
        self._script: list[str] | None = None
        self.declared_count: int | None = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "meta":
            key = data.get("property") or data.get("name")
            if key:
                self.meta[key.lower()] = data.get("content", "")
        if data.get("id") == "chapters" and str(data.get("data-chapters", "")).isdigit():
            self.declared_count = int(data["data-chapters"])
        if tag == "script":
            self._script = []

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            script = "".join(self._script)
            if re.search(r"\bwindow\.chapters\s*=", script):
                self.chapter_scripts.append(script)
            self._script = None


def _chapter_link(base: str, entry: dict) -> ChapterLink | None:
    order, chapter_id, href = entry.get("order"), entry.get("id"), entry.get("url")
    if (not isinstance(order, int) or isinstance(order, bool) or order < 0 or
            not isinstance(chapter_id, int) or isinstance(chapter_id, bool) or chapter_id < 1 or
            not isinstance(href, str) or entry.get("hiddenCount") or
            entry.get("visible", 1) not in (1, True)):
        return None
    absolute = urljoin(base, href)
    parts = urlsplit(absolute)
    path = _CHAPTER_PATH.fullmatch(parts.path)
    if (parts.scheme != "https" or parts.hostname != "www.royalroad.com" or
            parts.query or parts.fragment or not path or path.group(1) != base.rsplit("/", 1)[-1] or
            int(path.group(2)) != chapter_id):
        return None
    return ChapterLink(str(order + 1), absolute, source_page=base)


def parse_royalroad(html: str, url: str) -> Extraction:
    base = series_url(url)
    if not base:
        return Extraction("UNSUPPORTED", METHOD)
    parser = _FictionPage()
    parser.feed(html)
    canonical = parser.meta.get("og:url")
    if canonical and series_url(canonical) != base:
        return Extraction("CONTRADICTORY", METHOD, warnings=["Page fiction ID differs from the requested ID."])
    if len(parser.chapter_scripts) != 1:
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Fiction chapter catalog is missing or ambiguous."])
    script = parser.chapter_scripts[0]
    match = re.search(r"\bwindow\.chapters\s*=\s*", script)
    try:
        entries, _ = json.JSONDecoder().raw_decode(script[match.end():].lstrip())
    except (ValueError, TypeError, AttributeError):
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Fiction chapter catalog could not be decoded."])
    if not isinstance(entries, list) or not entries:
        return Extraction("EMPTY", METHOD, warnings=["Fiction has no chapter entries."])
    links = [_chapter_link(base, entry) for entry in entries if isinstance(entry, dict)]
    if (len(links) != len(entries) or any(link is None for link in links) or
            parser.declared_count is not None and parser.declared_count != len(entries)):
        return Extraction("TRUNCATED", METHOD, warnings=["Some catalog chapters are hidden, invalid, or missing."])
    links.sort(key=lambda link: int(link.chapter))
    if [int(link.chapter) for link in links] != list(range(1, len(links) + 1)):
        return Extraction("CONTRADICTORY", METHOD, warnings=["Chapter order is duplicated or has gaps."])
    if len({entry["id"] for entry in entries}) != len(entries):
        return Extraction("CONTRADICTORY", METHOD, warnings=["Chapter IDs are duplicated."])
    return Extraction("OK", METHOD, links[-1], links[:2] + links[-2:], confidence="HIGH",
                      title=parser.meta.get("og:title") or parser.meta.get("twitter:title") or None,
                      cover_url=parser.meta.get("og:image") or None,
                      first_url=links[0].url, checked_page_url=base,
                      catalog_ids=[entry["id"] for entry in sorted(entries, key=lambda entry: entry["order"])])


async def fetch_royalroad(url: str) -> tuple[int, str, bytes, dict[str, str], bool]:
    """Read one public fiction page, retrying a challenge via the allowlisted browser."""
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
    return status, final, body, headers, False
