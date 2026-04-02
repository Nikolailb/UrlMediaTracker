from datetime import datetime

from pydantic import BaseModel

from models.item import PatternSource, CheckStrategy, ItemCategory


class ItemCreate(BaseModel):
    url: str
    title: str | None = None
    manual_regex: str | None = None
    check_interval_min: int = 60
    toc_url: str | None = None
    category: ItemCategory | None = None


class ItemUpdate(BaseModel):
    title: str | None = None
    manual_regex: str | None = None
    check_interval_min: int | None = None
    current_chapter: str | None = None
    is_active: bool | None = None
    toc_url: str | None = None
    check_strategy: CheckStrategy | None = None
    category: ItemCategory | None = None


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
    current_chapter: str | None
    latest_chapter: str | None
    check_interval_min: int
    last_checked_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    user_id: str | None
    has_unread: bool | None = None

    model_config = {"from_attributes": True}


class MarkReadRequest(BaseModel):
    chapter: str


class NextChapterResponse(BaseModel):
    item_id: str
    next_chapter: str | None
    next_url: str | None
    message: str
