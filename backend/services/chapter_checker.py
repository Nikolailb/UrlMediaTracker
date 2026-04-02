"""
Chapter checker service.

Checks a TrackedItem for newly available chapters and persists a ChapterCheckLog.

Strategies are pluggable via BaseCheckStrategy — drop in a new class and
register it in STRATEGY_REGISTRY to add site-specific scrapers later.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from models.check_log import ChapterCheckLog
from models.item import TrackedItem
from services.pattern_detection import build_chapter_url

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class CheckerConfig:
    timeout: float = 10.0
    delay_seconds: float = 1.0
    max_probe_ahead: int = 10


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------


class BaseCheckStrategy(ABC):
    """
    Interface for chapter-detection strategies.

    Implement ``find_latest_chapter`` to probe a site in whatever way is
    most appropriate. Return the highest chapter identifier found (as a
    string), or ``None`` if nothing new was discovered.
    """

    @abstractmethod
    async def find_latest_chapter(
        self,
        current_latest: str,
        url_template: str,
        config: CheckerConfig,
    ) -> str | None: ...


# ---------------------------------------------------------------------------
# Built-in strategy: incremental HTTP probing
# ---------------------------------------------------------------------------


class IncrementalProbeStrategy(BaseCheckStrategy):
    """
    Probe chapter N+1, N+2, … using HTTP HEAD requests until a 4xx/5xx
    response is received or ``config.max_probe_ahead`` is exhausted.

    Works well for sites with sequential integer chapter numbering.
    For sites that block HEAD, a GET-based scraping strategy can be
    registered instead (see STRATEGY_REGISTRY below).
    """

    async def find_latest_chapter(
        self,
        current_latest: str,
        url_template: str,
        config: CheckerConfig,
    ) -> str | None:
        try:
            base_num = int(float(current_latest))
        except (ValueError, TypeError):
            logger.warning(
                "Cannot parse chapter number %r for incremental probe.", current_latest
            )
            return None

        found_latest: str | None = None

        async with httpx.AsyncClient(
            timeout=config.timeout,
            follow_redirects=True,
            headers={"User-Agent": "ChapterTracker/1.0 (chapter availability check)"},
        ) as client:
            for offset in range(1, config.max_probe_ahead + 1):
                candidate = str(base_num + offset)
                probe_url = build_chapter_url(url_template, candidate)
                try:
                    resp = await client.head(probe_url)
                    if resp.status_code < 400:
                        found_latest = candidate
                        logger.debug("Chapter %s exists at %s", candidate, probe_url)
                        await asyncio.sleep(config.delay_seconds)
                    else:
                        logger.debug(
                            "Chapter %s → HTTP %s, stopping probe.",
                            candidate,
                            resp.status_code,
                        )
                        break
                except httpx.RequestError as exc:
                    logger.warning("Network error probing %s: %s", probe_url, exc)
                    break

        return found_latest


# ---------------------------------------------------------------------------
# Strategy registry — add new strategies here
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, BaseCheckStrategy] = {
    "INCREMENTAL_PROBE": IncrementalProbeStrategy(),
}


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


async def check_item(
    item: TrackedItem,
    db: Session,
    config: CheckerConfig | None = None,
) -> ChapterCheckLog:
    """
    Run a chapter check for *item*, persist a ChapterCheckLog, and update
    ``item.latest_chapter`` and ``item.last_checked_at`` if new content
    is found.

    Always returns the log entry regardless of success/failure.
    """
    # Deferred import avoids a circular dependency at module load time
    from config import settings  # noqa: PLC0415

    if config is None:
        config = CheckerConfig(
            timeout=settings.PROBE_REQUEST_TIMEOUT,
            delay_seconds=settings.PROBE_DELAY_SECONDS,
            max_probe_ahead=settings.MAX_PROBE_AHEAD,
        )

    log = ChapterCheckLog(
        item_id=item.id,
        checked_at=datetime.now(timezone.utc),
        previous_latest_chapter=item.latest_chapter,
        success=False,
    )

    if not item.url_template:
        log.error_message = "No URL template — cannot probe for new chapters."
        db.add(log)
        db.commit()
        return log

    if not item.is_active:
        log.error_message = "Item is inactive."
        db.add(log)
        db.commit()
        return log

    strategy = STRATEGY_REGISTRY.get(
        item.check_strategy.value, IncrementalProbeStrategy()
    )

    try:
        new_latest = await strategy.find_latest_chapter(
            current_latest=item.latest_chapter or item.current_chapter or "0",
            url_template=item.url_template,
            config=config,
        )

        if new_latest is not None:
            log.new_latest_chapter = new_latest
            item.latest_chapter = new_latest

        item.last_checked_at = datetime.now(timezone.utc)
        log.success = True

    except Exception as exc:  # noqa: BLE001
        log.error_message = str(exc)[:999]
        logger.exception("Unexpected error while checking item %s", item.id)

    db.add(log)
    db.commit()
    db.refresh(item)
    db.refresh(log)
    return log
