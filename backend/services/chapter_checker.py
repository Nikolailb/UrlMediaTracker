"""
Chapter checker service.

Checks a TrackedItem for newly available chapters and persists a ChapterCheckLog.

Strategies are pluggable via BaseCheckStrategy — drop in a new class and
register it in STRATEGY_REGISTRY to add site-specific scrapers later.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from models.check_log import ChapterCheckLog
from models.item import TrackedItem
from services.pattern_detection import build_chapter_url

logger = logging.getLogger(__name__)


def _normalise_probe_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def _redirect_kept_same_target(requested_url: str, final_url: str) -> bool:
    return _normalise_probe_url(requested_url) == _normalise_probe_url(final_url)


# ---------------------------------------------------------------------------
# Concurrency guard — limit simultaneous outbound check requests
# ---------------------------------------------------------------------------
# Initialised lazily so it is always created on the running event loop.
_semaphore: asyncio.Semaphore | None = None
MAX_CONCURRENT_CHECKS = 5


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore  # noqa: PLW0603
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    return _semaphore


# ---------------------------------------------------------------------------
# Per-item rate limiter — prevents hammering via the manual /check endpoint
# ---------------------------------------------------------------------------
# Maps item_id → last manually triggered check datetime (UTC)
_last_manual_check: dict[str, datetime] = {}
MANUAL_CHECK_COOLDOWN_SECONDS = 60


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
    max_probe_duration_seconds: float = 60.0
    # URL of a table-of-contents page used by ToCScraperStrategy.
    toc_url: str | None = None
    # Phrases that indicate a soft 404.
    content_error_phrases: tuple[str, ...] = field(
        default_factory=lambda: (
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
            "moved permanently",
            "404 not found",
        )
    )
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


@retry(
    retry=retry_if_exception_type(httpx.RequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
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
        if resp.status_code >= 300:
            logger.debug("Probe got HTTP %s for %s", resp.status_code, url)
            return False
        final_url = str(resp.url)
        if resp.history and not _redirect_kept_same_target(url, final_url):
            logger.debug(
                "Probe redirected away from chapter URL: %s -> %s", url, final_url
            )
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


class ToCScraperStrategy(BaseCheckStrategy):
    """
    Finds the latest chapter by fetching a table-of-contents page and
    scanning every href attribute for URLs that match the item's
    url_template pattern.

    This is the correct approach for sites where chapter URL IDs are not
    sequentially numbered (e.g. they are global post IDs shared across many
    stories).  Sequential probing would wander off into unrelated content.

    The match regex is derived directly from url_template by escaping the
    static parts and replacing ``{n}`` with a numeric capture group — no
    site-specific knowledge is required beyond the ToC URL.

    Only the first page of the ToC is fetched.  Because most sites list
    newest chapters first, page 1 already contains the highest ID.
    """

    _HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)

    async def find_latest_chapter(
        self,
        current_latest: str,
        url_template: str,
        config: CheckerConfig,
    ) -> str | None:
        if not config.toc_url:
            logger.warning("ToCScraperStrategy: no toc_url in config — cannot scrape.")
            return None

        # Build a match regex from the url_template.
        # Split on the {n} placeholder so we can escape both halves safely.
        parts = url_template.split("{n}", 1)
        if len(parts) != 2:
            logger.warning(
                "ToCScraperStrategy: url_template %r has no {n} placeholder.",
                url_template,
            )
            return None

        pattern = re.compile(
            re.escape(parts[0]) + r"(\d+(?:\.\d+)?[a-z]?)" + re.escape(parts[1]),
            re.IGNORECASE,
        )

        async with httpx.AsyncClient(
            timeout=config.timeout,
            follow_redirects=True,
            headers={"User-Agent": "ChapterTracker/1.0 (chapter availability check)"},
        ) as client:
            try:
                resp = await client.get(config.toc_url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "ToCScraperStrategy: HTTP %s fetching ToC %s",
                    exc.response.status_code,
                    config.toc_url,
                )
                return None
            except httpx.RequestError as exc:
                logger.warning(
                    "ToCScraperStrategy: network error fetching ToC %s: %s",
                    config.toc_url,
                    exc,
                )
                return None

        ids: list[float] = []
        for href_m in self._HREF_RE.finditer(resp.text):
            chapter_m = pattern.search(href_m.group(1))
            if chapter_m:
                try:
                    ids.append(float(chapter_m.group(1)))
                except ValueError:
                    pass

        if not ids:
            logger.debug(
                "ToCScraperStrategy: no chapter hrefs matched on %s", config.toc_url
            )
            return None

        max_id = max(ids)
        try:
            current_f = float(current_latest)
        except (ValueError, TypeError):
            current_f = -1.0

        if max_id <= current_f:
            return None

        # Return as int string when the value is whole, else keep decimal
        return str(int(max_id)) if max_id == int(max_id) else str(max_id)


class FallbackStrategy(BaseCheckStrategy):
    """
    Meta-strategy that tries an ordered list of strategies in sequence.

    Returns the result of the first strategy that produces a non-None value.
    If all strategies return None the method returns None.

    Used for the ``TOC_THEN_PROBE`` preset: scan the table of contents page
    first (fast, exact), then fall back to sequential HTTP probing when no
    ToC URL is configured or the ToC scan yields nothing.
    """

    def __init__(self, strategies: list[BaseCheckStrategy]) -> None:
        self._strategies = strategies

    async def find_latest_chapter(
        self,
        current_latest: str,
        url_template: str,
        config: CheckerConfig,
    ) -> str | None:
        for strategy in self._strategies:
            result = await strategy.find_latest_chapter(
                current_latest, url_template, config
            )
            if result is not None:
                return result
        return None


STRATEGY_REGISTRY: dict[str, BaseCheckStrategy] = {
    "INCREMENTAL_PROBE": IncrementalProbeStrategy(),
    "TOC_SCRAPER": ToCScraperStrategy(),
    "TOC_THEN_PROBE": FallbackStrategy(
        [ToCScraperStrategy(), IncrementalProbeStrategy()]
    ),
}


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


async def check_item(
    item: TrackedItem,
    db: Session,
    config: CheckerConfig | None = None,
    *,
    bypass_rate_limit: bool = False,
) -> ChapterCheckLog:
    """
    Run a chapter check for *item*, persist a ChapterCheckLog, and update
    ``item.latest_chapter`` and ``item.last_checked_at`` if new content
    is found.

    Always returns the log entry regardless of success/failure.
    Set ``bypass_rate_limit=True`` for scheduler-triggered checks (not user-
    initiated) so the cooldown only applies to manual /check calls.
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
            toc_url=item.toc_url,
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

    strategy = STRATEGY_REGISTRY.get(item.check_strategy, IncrementalProbeStrategy())

    async with _get_semaphore():
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
                item.latest_chapter_at = datetime.now(timezone.utc)
            item.last_checked_at = datetime.now(timezone.utc)
            log.success = True
            # Reset failure tracking on success
            item.consecutive_failures = 0
            item.last_error = None
        except asyncio.TimeoutError:
            logger.warning(
                "Probe for item %s (%s) exceeded %ss wall-clock limit and was cancelled.",
                item.id,
                item.title,
                config.max_probe_duration_seconds,
            )
            msg = (
                f"Probe timed out after {config.max_probe_duration_seconds:.0f}s. "
                "Consider reducing coarse_step or max_coarse_steps."
            )
            log.error_message = msg
            item.consecutive_failures = (item.consecutive_failures or 0) + 1
            item.last_error = msg
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)[:999]
            log.error_message = msg
            item.consecutive_failures = (item.consecutive_failures or 0) + 1
            item.last_error = msg
            logger.exception("Unexpected error while checking item %s", item.id)

    db.add(log)
    db.commit()
    db.refresh(item)
    db.refresh(log)
    return log
