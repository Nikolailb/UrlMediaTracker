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
    delay_seconds: float = 0.5
    coarse_step: int = 5
    max_coarse_steps: int = 100
    # Hard wall-clock cap on a single find_latest_chapter call (seconds).
    # Prevents a probe run from hanging indefinitely when a site returns
    # 200 for every URL or is extremely slow.
    max_probe_duration_seconds: float = 60.0
    # Phrases that indicate a soft 404 — the server returns 200 but the page
    # has no real chapter content. Matched case-insensitively against the
    # first ``probe_byte_limit`` bytes of the response body.
    content_error_phrases: tuple[str, ...] = (
        "chapter not available",
        "chapter missing",
        "chapter content is missing",
        "content is missing or does not exist",
        "chapter does not exist",
        "chapter not found",
        "page not found",
        "content not found",
        "no chapter found",
        "chapter unavailable",
    )
    # Maximum response bytes to read before stopping content inspection.
    # 32 KB is enough to reach the <body> of any page without downloading
    # the whole thing.
    probe_byte_limit: int = 32_768


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
# Content-aware probe helper
# ---------------------------------------------------------------------------


async def _probe(
    client: httpx.AsyncClient,
    url: str,
    config: CheckerConfig,
) -> bool:
    """
    Return ``True`` if *url* both responds with a success status code
    **and** appears to contain real chapter content.

    Uses a streaming GET so only the first ``config.probe_byte_limit``
    bytes are downloaded — enough to catch error banners in the page
    header without fetching the full HTML.

    Raises ``httpx.RequestError`` on network failures so callers can
    handle retries/logging uniformly.
    """
    async with client.stream("GET", url) as resp:
        if resp.status_code >= 400:
            return False
        raw = b""
        async for chunk in resp.aiter_bytes(chunk_size=4_096):
            raw += chunk
            if len(raw) >= config.probe_byte_limit:
                break
    text = raw.decode("utf-8", errors="replace").lower()
    return not any(phrase in text for phrase in config.content_error_phrases)


# ---------------------------------------------------------------------------
# Built-in strategy: incremental HTTP probing
# ---------------------------------------------------------------------------


class IncrementalProbeStrategy(BaseCheckStrategy):
    """
    Two-phase content-aware probe to find the latest available chapter.

    Phase 1 — coarse: probe N + STEP, N + 2*STEP, … until the first miss.
    This skips large gaps quickly (e.g. 100 new chapters in ~20 requests
    with the default step of 5).

    Phase 2 — fine: probe every integer in the window between the last
    coarse hit and the coarse miss to find the exact last chapter.

    Each probe is a streaming GET request. Only the first
    ``config.probe_byte_limit`` bytes are read, so large HTML pages are
    not downloaded in full. After receiving a 200, the response body is
    scanned for ``config.content_error_phrases`` to catch sites that
    return HTTP 200 for missing chapters (soft 404s).

    ``config.max_coarse_steps`` is a safety cap so a site that returns
    200 for everything cannot loop forever.
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

        step = max(1, config.coarse_step)
        found_latest: str | None = None

        async with httpx.AsyncClient(
            timeout=config.timeout,
            follow_redirects=True,
            headers={"User-Agent": "ChapterTracker/1.0 (chapter availability check)"},
        ) as client:

            # ------------------------------------------------------------------
            # Phase 1: coarse stepping — find the window [coarse_low, coarse_miss)
            # that contains the last available chapter.
            # ------------------------------------------------------------------
            coarse_low = base_num  # last confirmed-good chapter number
            coarse_miss = base_num + step  # first unconfirmed candidate

            for _ in range(config.max_coarse_steps):
                probe_url = build_chapter_url(url_template, str(coarse_miss))
                try:
                    exists = await _probe(client, probe_url, config)
                    if exists:
                        found_latest = str(coarse_miss)
                        coarse_low = coarse_miss
                        coarse_miss += step
                        logger.debug("Coarse hit: chapter %s exists.", coarse_low)
                        await asyncio.sleep(config.delay_seconds)
                    else:
                        logger.debug("Coarse miss: chapter %s.", coarse_miss)
                        break
                except httpx.RequestError as exc:
                    logger.warning("Network error probing %s: %s", probe_url, exc)
                    break

            # ------------------------------------------------------------------
            # Phase 2: fine stepping within (coarse_low, coarse_miss) — only
            # needed when the coarse step is > 1.
            # ------------------------------------------------------------------
            if step > 1:
                for num in range(coarse_low + 1, coarse_miss):
                    probe_url = build_chapter_url(url_template, str(num))
                    try:
                        exists = await _probe(client, probe_url, config)
                        if exists:
                            found_latest = str(num)
                            logger.debug("Fine hit: chapter %s exists.", num)
                            await asyncio.sleep(config.delay_seconds)
                        else:
                            logger.debug("Fine miss: chapter %s, done.", num)
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
            coarse_step=settings.PROBE_COARSE_STEP,
            max_coarse_steps=settings.MAX_COARSE_STEPS,
            max_probe_duration_seconds=settings.MAX_PROBE_DURATION_SECONDS,
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
        new_latest = await asyncio.wait_for(
            strategy.find_latest_chapter(
                current_latest=item.latest_chapter or item.current_chapter or "0",
                url_template=item.url_template,
                config=config,
            ),
            timeout=config.max_probe_duration_seconds,
        )
        if new_latest is not None:
            log.new_latest_chapter = new_latest
            item.latest_chapter = new_latest
        item.last_checked_at = datetime.now(timezone.utc)
        log.success = True
    except asyncio.TimeoutError:
        logger.warning(
            "Probe for item %s (%s) exceeded %ss wall-clock limit and was cancelled.",
            item.id,
            item.title,
            config.max_probe_duration_seconds,
        )
        log.error_message = (
            f"Probe timed out after {config.max_probe_duration_seconds:.0f}s. "
            "Consider reducing coarse_step or max_coarse_steps."
        )
    except Exception as exc:  # noqa: BLE001
        log.error_message = str(exc)[:999]
        logger.exception("Unexpected error while checking item %s", item.id)

    db.add(log)
    db.commit()
    db.refresh(item)
    db.refresh(log)
    return log
