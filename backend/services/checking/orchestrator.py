"""Check orchestration and persistence (REQ-005, REQ-008)."""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm import Session
from models.check_log import ChapterCheckLog
from models.item import TrackedItem
from services.checking.strategies.probe import CheckerConfig, IncrementalProbeStrategy, ProbeBlocked, ProbeFailed
logger = logging.getLogger(__name__)
_semaphore: asyncio.Semaphore | None = None
MAX_CONCURRENT_CHECKS = 5

def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    return _semaphore

_last_manual_check: dict[str, datetime] = {}
MANUAL_CHECK_COOLDOWN_SECONDS = 60

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

    if not item.is_active:
        log.error_message = "Item is inactive."
        log.outcome = "UNSUPPORTED"
        db.add(log)
        db.commit()
        return log

    from services.checking.selector import check_source

    async with _get_semaphore():
        try:
            result = await asyncio.wait_for(check_source(item, config), timeout=config.max_probe_duration_seconds)
            log.outcome = result.outcome
            item.last_outcome = result.outcome
            if result.outcome == "NEW" and result.chapter == item.dismissed_candidate:
                result.outcome = "UNCHANGED"
                log.outcome = item.last_outcome = "UNCHANGED"
            if result.outcome == "NEW" and result.chapter:
                suspicious = False
                if item.latest_chapter:
                    try:
                        previous = Decimal(item.latest_chapter)
                        candidate = Decimal(result.chapter)
                        suspicious = candidate - previous > 50 and candidate > previous * Decimal("1.25")
                    except InvalidOperation:
                        suspicious = True
                if suspicious:
                    item.pending_latest_chapter = result.chapter
                    item.pending_chapter_url = result.chapter_url
                    item.last_outcome = log.outcome = "PENDING"
                    log.pending_chapter = result.chapter
                else:
                    log.new_latest_chapter = result.chapter
                    item.latest_chapter = result.chapter
                    item.latest_chapter_url = result.chapter_url
                    item.latest_chapter_at = datetime.now(timezone.utc)
            elif result.outcome == "UNCHANGED" and result.chapter == item.latest_chapter and result.chapter_url:
                item.latest_chapter_url = result.chapter_url
            if result.first_url:
                item.first_chapter_url = result.first_url
            if result.toc_latest_page_url and result.method == "TOC_SCRAPER":
                item.toc_latest_page_url = result.toc_latest_page_url
            item.last_checked_at = datetime.now(timezone.utc)
            log.success = log.outcome in {"NEW", "UNCHANGED"}
            if result.outcome in {"NEW", "UNCHANGED", "PENDING"}:
                item.consecutive_failures = 0
                item.last_error = None
            elif result.outcome == "BLOCKED":
                item.last_error = result.detail or "Source appears blocked."
            elif result.outcome in {"FAILED", "UNSUPPORTED"}:
                item.consecutive_failures = (item.consecutive_failures or 0) + 1
                item.last_error = result.detail or result.outcome.title()
            log.error_message = item.last_error if not log.success else None
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
            log.outcome = item.last_outcome = "FAILED"
            item.consecutive_failures = (item.consecutive_failures or 0) + 1
            item.last_error = msg
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)[:999]
            log.error_message = msg
            log.outcome = item.last_outcome = "FAILED"
            item.consecutive_failures = (item.consecutive_failures or 0) + 1
            item.last_error = msg
            logger.exception("Unexpected error while checking item %s", item.id)

    db.add(log)
    db.commit()
    db.refresh(item)
    db.refresh(log)
    return log
