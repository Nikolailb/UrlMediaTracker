"""Shared extracted chapter evidence (REQ-016)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChapterLink:
    chapter: str
    url: str
    group: str | None = None
    source_page: str | None = None


@dataclass
class Extraction:
    state: str
    method: str
    latest: ChapterLink | None = None
    links: list[ChapterLink] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    confidence: str = "LOW"
    warnings: list[str] = field(default_factory=list)
    last_page_url: str | None = None
    checked_page_url: str | None = None
    title: str | None = None
    cover_url: str | None = None
    first_url: str | None = None
    group_labels: dict[str, str] = field(default_factory=dict)
