"""FreeWebNovel series-page ToC adapter (REQ-007).

The visible chapter list is paginated from chapter one. The page's own latest
metadata and six-latest section identify the newest chapter without walking pages.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit


def series_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or (parts.hostname or "").lower() not in {
        "freewebnovel.com", "www.freewebnovel.com"
    } or parts.port or parts.username or parts.password:
        return None
    match = re.fullmatch(r"/novel/([a-z0-9-]+)(?:/chapter-[0-9]+)?/?", parts.path, re.I)
    if not match:
        return None
    return urlunsplit(("https", "freewebnovel.com", f"/novel/{match.group(1)}", "", ""))


def chapter_template(url: str | None) -> str | None:
    return f"{url}/chapter-{{n}}" if url else None


class _SeriesParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.total = None
        self.latest_links = []
        self._div_depth = 0
        self._latest_depth = None
        self._href = None
        self._label = []
        self._h1 = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "meta":
            key = data.get("property") or data.get("name")
            if key:
                self.meta[key.lower()] = data.get("content", "")
        if tag == "div":
            self._div_depth += 1
            if "m-newest1" in data.get("class", "").split():
                self._latest_depth = self._div_depth
            if data.get("id") == "indexListPage":
                self.total = data.get("data-total-chapters")
        if tag == "a" and self._latest_depth is not None:
            self._href = data.get("href")
            self._label = []
        if tag == "h1" and not self.title:
            self._h1 = True

    def handle_data(self, data):
        if self._href:
            self._label.append(data)
        if self._h1:
            self.title += data.strip()

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.latest_links.append((self._href, "".join(self._label).strip()))
            self._href = None
        if tag == "h1":
            self._h1 = False
        if tag == "div":
            if self._latest_depth == self._div_depth:
                self._latest_depth = None
            self._div_depth -= 1


def _chapter(href: str, label: str, base: str) -> tuple[int, str] | None:
    absolute = urljoin(base, href)
    parts = urlsplit(absolute)
    match = re.fullmatch(re.escape(urlsplit(base).path) + r"/chapter-([0-9]+)/?", parts.path, re.I)
    label_match = re.search(r"\bchapter\s+([0-9]+)\b", label, re.I)
    if (not match or not label_match or int(match.group(1)) != int(label_match.group(1))
            or parts.scheme != "https" or parts.hostname != "freewebnovel.com"
            or parts.query or parts.fragment):
        return None
    return int(match.group(1)), absolute


def parse_freewebnovel(html: str, url: str) -> dict:
    base = series_url(url)
    if not base:
        raise ValueError("Not a FreeWebNovel series URL")
    parser = _SeriesParser()
    parser.feed(html)
    meta = parser.meta
    page_url = meta.get("og:url")
    if page_url and series_url(page_url) != base:
        return {"title": None, "cover_url": None, "chapter": None, "chapter_url": None}
    title = meta.get("og:title") or parser.title or None
    cover = meta.get("og:image") or meta.get("image")
    meta_chapter = _chapter(meta.get("og:novel:lastest_chapter_url", ""),
                            meta.get("og:novel:lastest_chapter_name", ""), base)
    latest = max(filter(None, (_chapter(href, label, base) for href, label in parser.latest_links)),
                 default=None)
    # A mismatch between independent page signals is not a trustworthy update.
    if meta_chapter and latest and meta_chapter[0] != latest[0]:
        chapter = None
    else:
        chapter = meta_chapter or latest
    if chapter and parser.total and parser.total.isdigit() and int(parser.total) != chapter[0]:
        chapter = None
    return {"title": title, "cover_url": urljoin(base, cover) if cover else None,
            "chapter": str(chapter[0]) if chapter else None,
            "chapter_url": chapter[1] if chapter else None}
