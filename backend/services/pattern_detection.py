"""
Pattern detection service.

Given a URL, attempts to identify the chapter/episode identifier using a
ranked cascade of strategies:

  1. Keyword match   – recognises prefixes like chapter-, ep-, vol-, etc.  (HIGH confidence)
  2. Query parameter – numeric value in a known query-param name           (MEDIUM confidence)
  3. Trailing number – last path segment ends with a bare number           (MEDIUM confidence)

Query parameters are checked before the trailing-number fallback so that
URLs such as ``…/series-name-2?ep=1`` correctly identify ``ep=1`` as the
episode rather than picking up the season/ID suffix from the path.

A manual regex override (with exactly one capture group) can bypass all
auto-detection and is always returned with HIGH confidence.

For some sites (for example Webtoons), the canonical chapter identifier
lives in a query parameter like ``episode_no`` while the path segment is
just a redirectable slug. In those cases we prioritize specific query
parameter names before path keyword matching.
"""

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import parse_qs, urlparse


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class PatternConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class PatternDetectionResult:
    url_template: str | None  # e.g. https://example.com/novel/chapter-{n}
    chapter_regex: str | None  # e.g. chapter-(\d+(?:\.\d+)?[a-z]?)
    current_chapter: str | None  # e.g. "183"
    confidence: PatternConfidence
    strategy_used: str  # keyword_match | trailing_number | query_param | manual | none
    pattern_source: str  # AUTO | MANUAL


# ---------------------------------------------------------------------------
# Keyword patterns (ordered most-specific → least-specific)
# ---------------------------------------------------------------------------

CHAPTER_KEYWORDS: list[str] = [
    "chapter",
    "ch",
    "chap",
    "episode",
    "ep",
    "part",
    "volume",
    "vol",
    "page",
    "pg",
]

# Matches: keyword + optional separator + number + optional letter suffix
# e.g.  chapter-183  |  ch_12  |  episode.5  |  vol1  |  page2b
_KEYWORD_RE = re.compile(
    r"(?P<keyword>" + "|".join(CHAPTER_KEYWORDS) + r")"
    r"(?P<sep>[-_.]?)"
    r"(?P<number>\d+(?:\.\d+)?)"
    r"(?P<suffix>[a-z]?)",
    re.IGNORECASE,
)

# Trailing bare number at end of a path segment, e.g. .../183  or  .../12b
_TRAILING_NUMBER_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)(?P<suffix>[a-z]?)$",
    re.IGNORECASE,
)

# Common file extensions to strip before applying the trailing-number regex
_EXTENSION_RE = re.compile(r"\.(html?|php\d*|aspx?|jsp|shtml)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_pattern(url: str, manual_regex: str | None = None) -> PatternDetectionResult:
    """
    Detect the chapter pattern in *url*.

    If *manual_regex* is provided it is used directly; it must contain exactly
    one capture group that matches the chapter identifier.

    Raises ``ValueError`` if *manual_regex* is syntactically invalid.
    """
    if manual_regex:
        return _apply_manual_regex(url, manual_regex)
    return _auto_detect(url)


def build_chapter_url(url_template: str, chapter: str | int | float) -> str:
    """Replace the ``{n}`` placeholder in *url_template* with *chapter*."""
    return url_template.replace("{n}", str(chapter))


def extract_chapter_from_url(url: str, chapter_regex: str) -> str | None:
    """
    Extract the chapter identifier from *url* using *chapter_regex* (group 1).
    Returns ``None`` on no match or invalid regex.
    """
    try:
        m = re.search(chapter_regex, url, re.IGNORECASE)
        if m and m.lastindex and m.lastindex >= 1:
            return m.group(1)
    except re.error:
        pass
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_manual_regex(url: str, pattern: str) -> PatternDetectionResult:
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern: {exc}") from exc

    m = compiled.search(url)
    if not m or not m.lastindex:
        # Pattern compiled but didn't match (or has no groups) — still store it
        return PatternDetectionResult(
            url_template=None,
            chapter_regex=pattern,
            current_chapter=None,
            confidence=PatternConfidence.LOW,
            strategy_used="manual",
            pattern_source="MANUAL",
        )

    g1_start, g1_end = m.span(1)
    template = url[:g1_start] + "{n}" + url[g1_end:]
    return PatternDetectionResult(
        url_template=template,
        chapter_regex=pattern,
        current_chapter=m.group(1),
        confidence=PatternConfidence.HIGH,
        strategy_used="manual",
        pattern_source="MANUAL",
    )


def _auto_detect(url: str) -> PatternDetectionResult:
    parsed = urlparse(url)

    # Prioritize explicit ID parameters used by some readers where the path
    # is only a slug/canonical title that can redirect.
    result = _try_query_param(
        url, parsed.query, candidate_names=["episode_no", "chapter_no", "ep_no"]
    )
    if result:
        return result

    result = _try_keyword_match(url, parsed.path)
    if result:
        return result

    result = _try_query_param(url, parsed.query)
    if result:
        return result

    result = _try_trailing_number(url, parsed.path)
    if result:
        return result

    return PatternDetectionResult(
        url_template=None,
        chapter_regex=None,
        current_chapter=None,
        confidence=PatternConfidence.LOW,
        strategy_used="none",
        pattern_source="AUTO",
    )


def _try_keyword_match(url: str, path: str) -> PatternDetectionResult | None:
    """Strategy 1 — find a known keyword prefix followed by a number."""
    m = _KEYWORD_RE.search(path)
    if not m:
        return None

    keyword = m.group("keyword").lower()
    sep = m.group("sep")
    number = m.group("number")
    suffix = m.group("suffix")
    current_chapter = number + suffix if suffix else number

    # Build a stable, item-specific regex so future URLs can be parsed
    sep_pattern = re.escape(sep) if sep else r"[-_.]?"
    chapter_regex = rf"(?i){re.escape(keyword)}{sep_pattern}(\d+(?:\.\d+)?[a-z]?)"

    # Use the same regex on the full URL to get the exact span of group 1
    url_match = re.search(chapter_regex, url, re.IGNORECASE)
    if not url_match:
        return None

    g1_start, g1_end = url_match.span(1)
    template = url[:g1_start] + "{n}" + url[g1_end:]

    return PatternDetectionResult(
        url_template=template,
        chapter_regex=chapter_regex,
        current_chapter=current_chapter,
        confidence=PatternConfidence.HIGH,
        strategy_used="keyword_match",
        pattern_source="AUTO",
    )


def _try_trailing_number(url: str, path: str) -> PatternDetectionResult | None:
    """Strategy 2 — last path segment is (or ends with) a bare number,
    optionally followed by a file extension like .html."""
    segments = [s for s in path.rstrip("/").split("/") if s]
    if not segments:
        return None

    last = segments[-1]

    # Strip file extension so numbers like "3090461" in "3090461.html" are found
    ext_m = _EXTENSION_RE.search(last)
    bare = last[: ext_m.start()] if ext_m else last

    m = _TRAILING_NUMBER_RE.search(bare)
    if not m:
        return None

    number = m.group("number")
    suffix = m.group("suffix")
    current_chapter = number + suffix if suffix else number

    # Regex captures the trailing number in the last path segment,
    # tolerating an optional file extension after it.
    chapter_regex = r"/(\d+(?:\.\d+)?[a-z]?)(?:\.[a-z]{2,5})?(?:[/?#]|$)"

    # Locate the segment in the full URL to compute the replacement range.
    seg_pos = url.rfind("/" + last)
    if seg_pos == -1:
        return None

    num_offset = last.rfind(m.group(0))
    abs_start = seg_pos + 1 + num_offset  # +1 skips the leading "/"
    abs_end = abs_start + len(m.group(0))
    template = url[:abs_start] + "{n}" + url[abs_end:]

    return PatternDetectionResult(
        url_template=template,
        chapter_regex=chapter_regex,
        current_chapter=current_chapter,
        confidence=PatternConfidence.MEDIUM,
        strategy_used="trailing_number",
        pattern_source="AUTO",
    )


def _try_query_param(
    url: str,
    query: str,
    candidate_names: list[str] | None = None,
) -> PatternDetectionResult | None:
    """Strategy 3 — numeric chapter identifier in a known query-parameter name."""
    params = parse_qs(query)
    if candidate_names is None:
        candidate_names = [
            "chapter",
            "ch",
            "chap",
            "ep",
            "episode",
            "episode_no",
            "chapter_no",
            "ep_no",
            "page",
            "p",
            "num",
        ]

    for name in candidate_names:
        if name not in params:
            continue
        values = params[name]
        if not values or not re.match(r"^\d+(?:\.\d+)?$", values[0]):
            continue

        number = values[0]
        chapter_regex = rf"[?&]{re.escape(name)}=(\d+(?:\.\d+)?)"
        template = re.sub(
            rf"({re.escape(name)}=)\d+(?:\.\d+)?",
            r"\g<1>{n}",
            url,
        )
        return PatternDetectionResult(
            url_template=template,
            chapter_regex=chapter_regex,
            current_chapter=number,
            confidence=PatternConfidence.MEDIUM,
            strategy_used="query_param",
            pattern_source="AUTO",
        )

    return None
