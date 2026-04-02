from enum import Enum

from pydantic import BaseModel


class PatternConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PatternDetectionRequest(BaseModel):
    url: str
    # Optional user-supplied regex; must have exactly one capture group
    # containing the chapter identifier, e.g. r"chapter-(\d+)"
    manual_regex: str | None = None


class PatternDetectionResult(BaseModel):
    # Human-readable template with {n} placeholder, e.g. .../chapter-{n}
    url_template: str | None
    # Regex (group 1 = chapter identifier), e.g. chapter-(\d+(?:\.\d+)?[a-z]?)
    chapter_regex: str | None
    # Chapter identifier extracted from the submitted URL, e.g. "183"
    current_chapter: str | None
    confidence: PatternConfidence
    # One of: keyword_match | trailing_number | query_param | manual | none
    strategy_used: str
    # "AUTO" or "MANUAL"
    pattern_source: str
