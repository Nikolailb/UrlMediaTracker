"""Generic single-page ToC extraction (REQ-005)."""
import re
from decimal import Decimal
from urllib.parse import urljoin


def parse_toc(html: str, toc_url: str, url_template: str) -> tuple[str, str] | None:
    parts = url_template.split("{n}", 1)
    if len(parts) != 2:
        raise ValueError("Chapter template requires {n}.")
    pattern = re.compile(re.escape(parts[0]) + r"(\d+(?:\.\d+)?[a-z]?)" + re.escape(parts[1]), re.I)
    hrefs = re.findall(r'href=["\']([^"\']+)', html, re.I)
    chapters = [(match.group(1), absolute) for href in hrefs
                if (match := pattern.fullmatch(absolute := urljoin(toc_url, href)))]
    if not chapters:
        return None
    return max(chapters, key=lambda pair: (
        Decimal(re.match(r"\d+(?:\.\d+)?", pair[0]).group()), pair[0].lower()))
