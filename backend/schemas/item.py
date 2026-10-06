from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_validator
from typing import Literal
from urllib.parse import urlsplit

from models.item import PatternSource, CheckStrategy, ItemCategory


class ItemCreate(BaseModel):
    url: str
    chapter_url: str | None = None
    title: str | None = None
    manual_regex: str | None = Field(
        default=None,
        validation_alias=AliasChoices("manual_regex", "custom_regex"),
    )
    check_interval_min: int = 360
    toc_url: str | None = None
    category: ItemCategory | None = None
    is_sensitive: bool = False
    note: str | None = Field(default=None, max_length=2000)
    strategy_override: Literal["FREEWEBNOVEL", "COMIX", "TOC_SCRAPER", "INCREMENTAL_PROBE", "TOC_THEN_PROBE"] | None = None
    current_chapter: str | None = None
    latest_chapter: str | None = None
    preferred_group: str | None = Field(default=None, max_length=200)
    toc_example_urls: list[str] = Field(default_factory=list, max_length=2)
    toc_row_html: str | None = Field(default=None, max_length=5000)

    @field_validator("url", "chapter_url", "toc_url")
    @classmethod
    def web_url(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parts = urlsplit(value)
                valid = parts.scheme in {"http", "https"} and bool(parts.hostname) and not parts.username and not parts.password
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("Use an HTTP(S) URL without credentials.")
        return value

    @field_validator("toc_example_urls")
    @classmethod
    def example_urls(cls, value: list[str]) -> list[str]:
        return [cls.web_url(url) for url in value]


class ItemUpdate(BaseModel):
    title: str | None = None
    chapter_url: str | None = None
    manual_regex: str | None = Field(
        default=None,
        validation_alias=AliasChoices("manual_regex", "custom_regex"),
    )
    check_interval_min: int | None = None
    current_chapter: str | None = None
    is_active: bool | None = None
    toc_url: str | None = None
    check_strategy: CheckStrategy | None = None
    category: ItemCategory | None = None
    is_sensitive: bool | None = None
    note: str | None = Field(default=None, max_length=2000)
    latest_chapter: str | None = None
    strategy_override: Literal["FREEWEBNOVEL", "COMIX", "TOC_SCRAPER", "INCREMENTAL_PROBE", "TOC_THEN_PROBE"] | None = None
    preferred_group: str | None = Field(default=None, max_length=200)
    toc_example_urls: list[str] | None = Field(default=None, max_length=2)
    toc_row_html: str | None = Field(default=None, max_length=5000)

    @field_validator("toc_url", "chapter_url")
    @classmethod
    def web_url(cls, value: str | None) -> str | None:
        return ItemCreate.web_url(value)

    @field_validator("toc_example_urls")
    @classmethod
    def example_urls(cls, value: list[str] | None) -> list[str] | None:
        return ItemCreate.example_urls(value) if value is not None else None


class ItemRead(BaseModel):
    id: str
    title: str | None
    original_url: str
    url_template: str | None
    chapter_regex: str | None
    pattern_source: PatternSource
    check_strategy: str
    toc_url: str | None
    category: str | None
    series_url: str | None
    strategy_override: str | None
    is_sensitive: bool
    note: str | None
    cover_filename: str | None
    pending_latest_chapter: str | None
    pending_chapter_url: str | None
    dismissed_candidate: str | None
    last_outcome: str | None
    current_chapter: str | None
    latest_chapter: str | None
    latest_chapter_url: str | None
    first_chapter_url: str | None
    preferred_group: str | None
    toc_example_urls: list[str] = []
    toc_row_class: str | None
    toc_latest_page_url: str | None
    check_interval_min: int
    last_checked_at: datetime | None
    latest_chapter_at: datetime | None
    consecutive_failures: int
    last_error: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    user_id: str | None
    has_unread: bool | None = None
    check_config_changed: bool = False

    model_config = {"from_attributes": True}


class MarkReadRequest(BaseModel):
    chapter: str


class NextChapterResponse(BaseModel):
    item_id: str
    next_chapter: str | None
    next_url: str | None
    message: str
    destination: Literal["CHAPTER", "TOC", "NONE"] = "NONE"
