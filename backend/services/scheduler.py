"""
Background scheduler.

Uses APScheduler's AsyncIOScheduler so it shares FastAPI's event loop.
Every 5 minutes it queries all active TrackedItems and runs a chapter
check for any that are overdue (based on their individual check_interval_min).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def run_due_checks() -> None:
    """Find all active items that are due for a check and run them."""
    # Deferred imports prevent circular deps and ensure the app is fully initialised
    from database import SessionLocal  # noqa: PLC0415
    from models.item import TrackedItem  # noqa: PLC0415
    from services.chapter_checker import check_item  # noqa: PLC0415

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        items: list[TrackedItem] = (
            db.query(TrackedItem).filter(TrackedItem.is_active.is_(True)).all()
        )

        due = [
            item
            for item in items
            if item.last_checked_at is None
            or (
                now
                - (
                    # SQLite returns naive datetimes; treat them as UTC
                    item.last_checked_at
                    if item.last_checked_at.tzinfo is not None
                    else item.last_checked_at.replace(tzinfo=timezone.utc)
                )
            )
            >= timedelta(minutes=item.check_interval_min)
        ]

        if not due:
            logger.debug("Scheduler: no items due for a check.")
            return

        logger.info("Scheduler: running checks for %d item(s).", len(due))
        tasks = [
            check_item(item, db, bypass_rate_limit=True)
            for item in due
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for item, result in zip(due, results):
            if isinstance(result, Exception):
                logger.error(
                    "Scheduler: check failed for item %s (%s): %s",
                    item.id,
                    item.title,
                    result,
                )
    finally:
        db.close()


def start_scheduler() -> None:
    scheduler.add_job(
        run_due_checks,
        trigger=IntervalTrigger(minutes=5),
        id="due_checks",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("Background scheduler started (poll interval: 5 min).")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
