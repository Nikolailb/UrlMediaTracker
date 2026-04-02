from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

if TYPE_CHECKING:
    from models.user import User
    from models.check_log import ChapterCheckLog


class PatternSource(str, PyEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class CheckStrategy(str, PyEnum):
    INCREMENTAL_PROBE = "INCREMENTAL_PROBE"
    TOC_SCRAPER = "TOC_SCRAPER"


class ItemCategory(str, PyEnum):
    NOVEL = "Novel"
    LIGHT_NOVEL = "Light Novel"
    MANHWA = "Manhwa"
    MANHUA = "Manhua"
    MANGA = "Manga"
    WEBTOON = "Webtoon"
    PORNHWA = "Pornhwa"
    COMIC = "Comic"
    ANIME = "Anime"


class TrackedItem(Base):
    __tablename__ = "tracked_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_url: Mapped[str] = mapped_column(String(2000), nullable=False)

    # {n} placeholder template, e.g. https://example.com/novel/chapter-{n}
    url_template: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Regex with one capture group for the chapter identifier, e.g. chapter-(\d+)
    chapter_regex: Mapped[str | None] = mapped_column(String(500), nullable=True)

    pattern_source: Mapped[PatternSource] = mapped_column(
        Enum(PatternSource), default=PatternSource.AUTO, nullable=False
    )
    check_strategy: Mapped[str] = mapped_column(
        String(50), default=CheckStrategy.INCREMENTAL_PROBE, nullable=False
    )

    # Stored as strings to support decimals (12.5) and suffix variants (183b)
    current_chapter: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latest_chapter: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Optional table-of-contents URL used by ToCScraperStrategy
    toc_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Content category tag (free-text enum stored as String for forward compatibility)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)

    check_interval_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Nullable FK — no user in v1, but the column exists for future association
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    user: Mapped["User | None"] = relationship("User", back_populates="items")
    check_logs: Mapped[list["ChapterCheckLog"]] = relationship(
        "ChapterCheckLog", back_populates="item", cascade="all, delete-orphan"
    )
