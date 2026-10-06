"""Extract series-scoped chapter links from an HTML ToC (REQ-016)."""
import json
import re
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from services.checking.results import ChapterLink, Extraction

_NUMBER = re.compile(r"\b(?:chapter|chap\.?|ch\.?|episode|ep\.?)\s*[#.: -]*\s*(\d+(?:\.\d+)?[a-z]?)\b", re.I)
_BAD_REGION = {"recommend", "related", "sidebar", "popular", "footer", "header", "comment"}


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[dict] = []
        self.anchors: list[tuple[str, str, list[dict]]] = []
        self._active: dict | None = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        node = {"tag": tag, "class": data.get("class", ""), "id": data.get("id", ""),
                "group": data.get("data-group") or data.get("data-group-id")}
        if tag == "a" and data.get("href"):
            self._active = {"href": data["href"], "text": [], "parents": self.stack.copy()}
        if tag not in {"meta", "link", "img", "input", "br", "hr", "source"}:
            self.stack.append(node)

    def handle_data(self, data):
        if self._active is not None:
            self._active["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._active is not None:
            a = self._active
            self.anchors.append((a["href"], " ".join(a["text"]).strip(), a["parents"]))
            self._active = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break


def _number(label: str, url: str) -> str | None:
    text = _NUMBER.search(label)
    path = _NUMBER.search(urlsplit(url).path.replace("-", " ").replace("_", " "))
    if text and path and text.group(1).lower() != path.group(1).lower():
        return None
    return (text or path).group(1).lower() if (text or path) else None


def _rank(chapter: str):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]?)", chapter, re.I)
    return (Decimal(m.group(1)), m.group(2)) if m else None


def row_class_from_html(snippet: str | None) -> str | None:
    if not snippet:
        return None
    m = re.search(r'<(?:li|tr|div)[^>]*class=["\']([^"\']+)', snippet, re.I)
    if not m:
        return None
    for token in m.group(1).split():
        if re.fullmatch(r"[a-zA-Z][\w-]{2,79}", token):
            return token
    return None


def parse_toc(html: str, toc_url: str, *, examples: list[str] | None = None,
              row_class: str | None = None, preferred_group: str | None = None) -> Extraction:
    page = _Page()
    page.feed(html)
    host = (urlsplit(toc_url).hostname or "").lower()
    series_path = urlsplit(toc_url).path.rstrip("/")
    example_paths = [urlsplit(url).path.rsplit("/", 1)[0] for url in (examples or [])
                     if (urlsplit(url).hostname or "").lower() == host]
    prefix = series_path if not example_paths else min(example_paths, key=len)
    candidates: list[ChapterLink] = []
    conflicts = 0
    for href, label, parents in page.anchors:
        absolute = urljoin(toc_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in {"http", "https"} or (parts.hostname or "").lower() != host:
            continue
        if not parts.path.startswith(prefix + "/"):
            continue
        context = " ".join(node["class"] + " " + node["id"] for node in parents).lower()
        if any(bad in context for bad in _BAD_REGION):
            continue
        if row_class and not any(row_class in node["class"].split() for node in parents):
            continue
        chapter = _number(label, absolute)
        if chapter is None:
            if _NUMBER.search(label):
                conflicts += 1
            continue
        group = next((node["group"] for node in reversed(parents) if node["group"]), None)
        candidates.append(ChapterLink(chapter, absolute, group, toc_url))
    pages = []
    for href, _, _ in page.anchors:
        link = urljoin(toc_url, href)
        if (urlsplit(link).hostname or "").lower() != host:
            continue
        try:
            number = int(parse_qs(urlsplit(link).query).get("page", [""])[0])
        except ValueError:
            continue
        if number > 1 and number <= 10000:
            pages.append((number, link))
    if not candidates:
        state = "CONTRADICTORY" if conflicts else ("CHANGED_LAYOUT" if row_class else "EMPTY")
        return Extraction(state, "TOC_SCRAPER",
                          warnings=["No trustworthy series chapter links were found."])
    ranked = [(link, _rank(link.chapter)) for link in candidates]
    if any(rank is None for _, rank in ranked):
        return Extraction("CONTRADICTORY", "TOC_SCRAPER", warnings=["Incomparable chapter labels."])
    highest = max(rank for _, rank in ranked)
    choices = [link for link, rank in ranked if rank == highest]
    latest = next((link for link in choices if link.group == preferred_group), None) or choices[0]
    unique = sorted({link.chapter for link in candidates}, key=lambda value: _rank(value), reverse=True)
    if conflicts:
        return Extraction("CONTRADICTORY", "TOC_SCRAPER", warnings=["Conflicting chapter label and URL."])
    return Extraction("OK", "TOC_SCRAPER", latest, candidates,
                      sorted({link.group for link in candidates if link.group}),
                      "HIGH" if len(unique) >= 2 else "MEDIUM",
                      ["Only one chapter link was found."] if len(unique) == 1 else [],
                      max(pages)[1] if pages else None)


def parse_toc_examples(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except ValueError:
        return []
