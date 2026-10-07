"""Scribble Hub series reader (REQ-019).

The first ToC page is newest-first; its row order is a release position, while
chapter titles and opaque URL IDs are not. The remaining pages load by AJAX.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from services.checking.browser import BrowserFetchError, browser_get
from services.checking.http import _challenge, safe_get
from services.checking.results import ChapterLink, Extraction

METHOD = "SCRIBBLEHUB"
MAX_PAGE_BYTES = 1_000_000
_SERIES_PATH = re.compile(r"/series/([0-9]+)(?:/[a-z0-9-]+)?/?", re.I)
_READ_PATH = re.compile(r"/read/([0-9]+)-[a-z0-9-]+/chapter/([0-9]+)/?", re.I)


def series_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or
                (parts.hostname or "").lower() not in {"scribblehub.com", "www.scribblehub.com"} or
                parts.port or parts.username or parts.password):
            return None
    except ValueError:
        return None
    series = _SERIES_PATH.fullmatch(parts.path)
    chapter = _READ_PATH.fullmatch(parts.path)
    fiction_id = series.group(1) if series else chapter.group(1) if chapter else None
    return f"https://www.scribblehub.com/series/{fiction_id}/" if fiction_id else None


def _chapter_url(base: str, href: str) -> str | None:
    absolute = urljoin(base, href)
    parts = urlsplit(absolute)
    match = _READ_PATH.fullmatch(parts.path)
    if (parts.scheme != "https" or parts.hostname != "www.scribblehub.com" or
            parts.port or parts.query or parts.fragment or not match or
            match.group(1) != base.rstrip("/").rsplit("/", 1)[-1]):
        return None
    return absolute


class _SeriesPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.count_text: str | None = None
        self._read_depth = 0
        self.first_url: str | None = None
        self._toc_depth = 0
        self._row: dict[str, str | None] | None = None
        self.rows: list[dict[str, str | None]] = []
        self.selected_page_size: int | None = None
        self._inside_show_select = False

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        classes = set(data.get("class", "").split())
        if tag == "meta":
            key = data.get("property") or data.get("name")
            if key:
                self.meta[key.lower()] = data.get("content", "")
        if tag == "span" and "cnt_toc" in classes and self.count_text is None:
            self.count_text = ""
        if tag == "div":
            if self._read_depth:
                self._read_depth += 1
            elif "read_buttons" in classes:
                self._read_depth = 1
        if tag == "a" and self._read_depth and not self.first_url:
            self.first_url = data.get("href")
        if tag == "select" and data.get("id") == "show_chapters":
            self._inside_show_select = True
        if tag == "option" and self._inside_show_select and "selected" in data:
            value = data.get("value", "")
            self.selected_page_size = int(value) if value.isdigit() else None
        if tag == "ol" and "toc_ol" in classes:
            self._toc_depth += 1
        if tag == "li" and self._toc_depth and "toc_w" in classes:
            self._row = {"order": data.get("order"), "url": None}
        if tag == "a" and self._row is not None and "toc_a" in classes:
            self._row["url"] = data.get("href")

    def handle_data(self, data):
        if self.count_text == "":
            self.count_text = data.strip()

    def handle_endtag(self, tag):
        if tag == "li" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        if tag == "ol" and self._toc_depth:
            self._toc_depth -= 1
        if tag == "select":
            self._inside_show_select = False
        if tag == "div" and self._read_depth:
            self._read_depth -= 1


def parse_scribblehub(html: str, url: str) -> Extraction:
    base = series_url(url)
    if not base:
        return Extraction("UNSUPPORTED", METHOD)
    page = _SeriesPage()
    page.feed(html)
    canonical = page.meta.get("og:url")
    if canonical and series_url(canonical) != base:
        return Extraction("CONTRADICTORY", METHOD, warnings=["Page series ID differs from the requested ID."])
    if not page.count_text or not page.count_text.isdigit():
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Series ToC count is missing."])
    count = int(page.count_text)
    if count < 1:
        return Extraction("EMPTY", METHOD, warnings=["Series ToC has no releases."])
    if not page.rows:
        return Extraction("CHANGED_LAYOUT", METHOD, warnings=["Series ToC rows are missing."])
    if page.selected_page_size and len(page.rows) != min(count, page.selected_page_size):
        return Extraction("TRUNCATED", METHOD, warnings=["First ToC page has fewer rows than advertised."])
    links: list[ChapterLink] = []
    for row in page.rows:
        order, href = row["order"], row["url"]
        chapter_url = _chapter_url(base, href) if href else None
        if not order or not order.isdigit() or not chapter_url:
            return Extraction("TRUNCATED", METHOD, warnings=["A ToC row has no valid position or series link."])
        links.append(ChapterLink(order, chapter_url, source_page=base))
    positions = [int(link.chapter) for link in links]
    if positions != list(range(count, count - len(links), -1)) or len({link.url for link in links}) != len(links):
        return Extraction("CONTRADICTORY", METHOD, warnings=["ToC order or chapter IDs are inconsistent."])
    first = _chapter_url(base, page.first_url) if page.first_url else None
    return Extraction("OK", METHOD, links[0], links[:4], confidence="HIGH",
                      title=page.meta.get("og:title") or page.meta.get("twitter:title") or None,
                      cover_url=page.meta.get("og:image") or None,
                      first_url=first, checked_page_url=base)


async def fetch_scribblehub(url: str) -> tuple[int, str, bytes, dict[str, str], bool]:
    """Read one series page; use the guarded browser only after direct failure."""
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
