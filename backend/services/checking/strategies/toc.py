"""Extract series-scoped chapter links from an HTML ToC (REQ-016)."""
import json
import re
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from services.checking.results import ChapterLink, Extraction
from services.pattern_detection import detect_pattern

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


def query_identity_conflicts(source_query: str, candidate_query: str) -> bool:
    """Reject conflicting shared query values without assuming site-specific keys."""
    source = parse_qs(source_query)
    candidate = parse_qs(candidate_query)
    return any(candidate[key] != values for key, values in source.items()
               if key not in {"page", "p", "offset", "sort", "order"} and key in candidate)


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


def _example_path_patterns(examples: list[str], host: str, chapter_regex: str | None) -> list[tuple]:
    """Turn explicit chapter URLs into URL shapes; never derive these from the ToC path."""
    patterns = []
    for example in examples:
        if (urlsplit(example).hostname or "").lower() != host:
            continue
        detected = detect_pattern(example, chapter_regex)
        if not detected.url_template:
            continue
        template = urlsplit(detected.url_template)
        path = template.path.rstrip("/")
        if path.count("{n}") != 1:
            continue
        expression = re.escape(path).replace(r"\{n\}", r"\d+(?:\.\d+)?[a-z]?")
        patterns.append((re.compile(r"^" + expression + r"$", re.I),
                         template.scheme, template.netloc.lower(), parse_qs(template.query)))
    return patterns


def _matches_example(parts, patterns: list[tuple]) -> bool:
    query = parse_qs(parts.query)
    return any(parts.scheme == scheme and parts.netloc.lower() == netloc and
               pattern.fullmatch(parts.path.rstrip("/")) and
               all(query.get(key) == values for key, values in required_query.items())
               for pattern, scheme, netloc, required_query in patterns)


def parse_toc(html: str, toc_url: str, *, examples: list[str] | None = None,
              row_class: str | None = None, preferred_group: str | None = None,
              chapter_regex: str | None = None) -> Extraction:
    compiled = None
    if chapter_regex:
        try:
            compiled = re.compile(chapter_regex, re.I)
        except re.error as exc:
            return Extraction("CONTRADICTORY", "TOC_SCRAPER", warnings=[f"Invalid chapter regex: {exc}"])
        if compiled.groups != 1:
            return Extraction("CONTRADICTORY", "TOC_SCRAPER", warnings=["Chapter regex needs exactly one capture group."])
    page = _Page()
    page.feed(html)
    host = (urlsplit(toc_url).hostname or "").lower()
    source = urlsplit(toc_url)
    series_path = source.path.rstrip("/")
    # A list endpoint is often a sibling of its chapter URLs.
    if series_path.rsplit("/", 1)[-1].lower() in {"list", "chapters", "toc", "chapter-list"}:
        series_path = series_path.rsplit("/", 1)[0]
    example_paths = []
    for url in examples or []:
        parts = urlsplit(url)
        if (parts.hostname or "").lower() != host:
            continue
        parent = parts.path.rstrip("/").rsplit("/", 1)[0]
        if _NUMBER.search(parent.rsplit("/", 1)[-1]):
            parent = parent.rsplit("/", 1)[0]
        if parent == series_path or parent.startswith(series_path + "/"):
            example_paths.append(parent)
    prefix = series_path if not example_paths else min(example_paths, key=len)
    example_patterns = _example_path_patterns(examples or [], host, chapter_regex)
    candidates: list[ChapterLink] = []
    conflicts = 0
    for href, label, parents in page.anchors:
        absolute = urljoin(toc_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in {"http", "https"} or (parts.hostname or "").lower() != host:
            continue
        if not (parts.path.startswith(prefix + "/") or _matches_example(parts, example_patterns)):
            continue
        if query_identity_conflicts(source.query, parts.query):
            continue
        context = " ".join(node["class"] + " " + node["id"] for node in parents).lower()
        if any(bad in context for bad in _BAD_REGION):
            continue
        if row_class and not any(row_class in node["class"].split() for node in parents):
            continue
        if compiled:
            match = compiled.search(absolute)
            chapter = match.group(1).lower() if match else None
            displayed = _NUMBER.search(label)
            if chapter and displayed and chapter != displayed.group(1).lower():
                conflicts += 1
                continue
        else:
            chapter = _number(label, absolute)
        if chapter is None:
            if not compiled and _NUMBER.search(label):
                conflicts += 1
            continue
        group = next((node["group"] for node in reversed(parents) if node["group"]), None)
        candidates.append(ChapterLink(chapter, absolute, group, toc_url))
    pages = []
    for href, _, _ in page.anchors:
        link = urljoin(toc_url, href)
        if (urlsplit(link).hostname or "").lower() != host:
            continue
        if query_identity_conflicts(source.query, urlsplit(link).query):
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
