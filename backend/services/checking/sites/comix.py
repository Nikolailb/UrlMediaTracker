"""Comix series metadata and optional rendered chapter-list reader (REQ-016)."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from services.checking.results import ChapterLink, Extraction
from services.checking.strategies.toc import _number

_SERIES = re.compile(r"/title/([a-z0-9]+-[a-z0-9-]+)(?:/\d+-chapter-[0-9]+(?:\.[0-9]+)?)?/?", re.I)


def series_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or (parts.hostname or "").lower() not in {"comix.to", "www.comix.to"}:
        return None
    if parts.port or parts.username or parts.password:
        return None
    match = _SERIES.fullmatch(parts.path)
    if not match:
        return None
    return urlunsplit(("https", "comix.to", "/title/" + match.group(1), "", ""))


class _InitialData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_data = False
        self.data = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "initial-data":
            self.in_data = True

    def handle_data(self, data):
        if self.in_data:
            self.data.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_data = False


def _series_link(base: str, candidate: str | None) -> str | None:
    if not isinstance(candidate, str) or not candidate:
        return None
    absolute = urljoin(base, candidate)
    parts = urlsplit(absolute)
    expected = urlsplit(base)
    if parts.scheme != "https" or parts.hostname != expected.hostname or not parts.path.startswith(expected.path + "/"):
        return None
    if parts.query or parts.fragment or not re.fullmatch(r"/\d+-chapter-\d+(?:\.\d+)?", parts.path[len(expected.path):], re.I):
        return None
    return absolute


def parse_comix(html: str, url: str) -> Extraction:
    base = series_url(url)
    if not base:
        return Extraction("UNSUPPORTED", "COMIX")
    parser = _InitialData()
    parser.feed(html)
    if not parser.data:
        return Extraction("EMPTY", "COMIX", warnings=["Comix initial page data is missing."])
    try:
        data = json.loads("".join(parser.data))
    except ValueError:
        return Extraction("CONTRADICTORY", "COMIX", warnings=["Comix page data is invalid."])
    slug = urlsplit(base).path.split("/")[2].split("-", 1)[0]
    queries = data.get("queries", {})
    detail = queries.get(json.dumps(["manga", "detail", slug], separators=(",", ":")))
    if not isinstance(detail, dict) or detail.get("hid") != slug:
        return Extraction("CONTRADICTORY", "COMIX", warnings=["Series identity did not match the page."])
    chapter = detail.get("latestChapter")
    if not isinstance(chapter, (int, float)) or chapter < 0:
        return Extraction("EMPTY", "COMIX", warnings=["No numeric latest chapter in series data."])
    chapter = str(int(chapter)) if int(chapter) == chapter else str(chapter)
    latest_url = _series_link(base, detail.get("latestChapterUrl"))
    first_url = _series_link(base, detail.get("firstChapterUrl"))
    if not latest_url or not re.search(r"-chapter-" + re.escape(chapter) + r"$", latest_url, re.I):
        return Extraction("CONTRADICTORY", "COMIX", warnings=["Latest chapter number and URL disagree."])
    group_data = queries.get(json.dumps(["manga", "groups", slug], separators=(",", ":")), [])
    groups = [str(group["id"]) for group in group_data if isinstance(group, dict) and group.get("id") is not None] if isinstance(group_data, list) else []
    labels = {str(group["id"]): str(group.get("name") or group["id"])
              for group in group_data if isinstance(group, dict) and group.get("id") is not None} if isinstance(group_data, list) else {}
    poster = detail.get("poster")
    cover = poster.get("large") if isinstance(poster, dict) else None
    link = ChapterLink(chapter, latest_url, None, base)
    return Extraction("OK", "COMIX", link, [link], groups, "HIGH", [],
                      title=detail.get("title"), cover_url=cover, first_url=first_url,
                      group_labels=labels)


class _RenderedRows(HTMLParser):
    def __init__(self, base: str):
        super().__init__()
        self.base = base
        self.rows: list[ChapterLink] = []
        self.stack: list[str] = []
        self.row_depth = 0
        self.chapter_href = None
        self.chapter_text = []
        self.group = None
        self.capture = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        classes = data.get("class", "").split()
        if tag not in {"meta", "link", "img", "input", "br", "hr", "source"}:
            self.stack.append(tag)
        if tag == "li" and "mchap-item" in classes:
            self.row_depth = len(self.stack)
            self.chapter_href = None
            self.chapter_text = []
            self.group = None
        if self.row_depth and tag == "a":
            if "mchap-row__primary" in classes:
                self.chapter_href = data.get("href")
                self.capture = "chapter"
            elif "mchap-row__group" in classes:
                m = re.fullmatch(r"/groups/(\d+)", data.get("href", ""))
                self.group = m.group(1) if m else None
                self.capture = "group"

    def handle_data(self, data):
        if self.capture == "chapter":
            self.chapter_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a":
            self.capture = None
        if tag == "li" and len(self.stack) == self.row_depth:
            if self.chapter_href:
                url = _series_link(self.base, self.chapter_href)
                chapter = _number(" ".join(self.chapter_text), url or self.chapter_href)
                if url and chapter:
                    self.rows.append(ChapterLink(chapter, url, self.group, self.base))
            self.row_depth = 0
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                del self.stack[i:]
                break


def merge_rendered_group(metadata: Extraction, rendered_html: str, base: str,
                         preferred_group: str | None) -> Extraction:
    """A rendered list is advisory; metadata remains authoritative."""
    if not preferred_group or metadata.state != "OK" or not metadata.latest:
        return metadata
    parser = _RenderedRows(base)
    parser.feed(rendered_html)
    choice = next((link for link in parser.rows
                   if link.chapter == metadata.latest.chapter and link.group == preferred_group), None)
    if choice:
        metadata.latest = choice
        metadata.links = parser.rows[:6]
    else:
        metadata.warnings.append("Preferred group's latest link was unavailable; using the series link.")
    return metadata
