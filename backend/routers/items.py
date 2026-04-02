import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.item import CheckStrategy, TrackedItem
from schemas.item import (
    ItemCreate,
    ItemRead,
    ItemUpdate,
    MarkReadRequest,
    NextChapterResponse,
)
from services.chapter_checker import check_item
from services.pattern_detection import build_chapter_url, detect_pattern

router = APIRouter(prefix="/items", tags=["items"])
DbDep = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_or_404(item_id: str, db: Session) -> TrackedItem:
    item = db.get(TrackedItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return item


def _has_unread(item: TrackedItem) -> bool | None:
    if item.current_chapter is None or item.latest_chapter is None:
        return None
    try:
        return float(item.latest_chapter) > float(item.current_chapter)
    except ValueError:
        return item.latest_chapter != item.current_chapter


def _to_read(item: TrackedItem) -> ItemRead:
    data = {col.name: getattr(item, col.name) for col in item.__table__.columns}
    # SQLite returns naive datetimes even when the column has timezone=True.
    # Normalise them to UTC-aware so Pydantic serialises them with +00:00,
    # which prevents browsers from treating them as local time.
    for field in ("last_checked_at", "created_at", "updated_at"):
        val = data.get(field)
        if isinstance(val, datetime) and val.tzinfo is None:
            data[field] = val.replace(tzinfo=timezone.utc)
    return ItemRead.model_validate({**data, "has_unread": _has_unread(item)})


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: DbDep):
    detection = detect_pattern(payload.url, payload.manual_regex)
    item = TrackedItem(
        id=str(uuid.uuid4()),
        title=payload.title,
        original_url=payload.url,
        url_template=detection.url_template,
        chapter_regex=detection.chapter_regex,
        pattern_source=detection.pattern_source,
        current_chapter=detection.current_chapter,
        # Assume the submitted chapter is the latest known on first add
        latest_chapter=detection.current_chapter,
        check_interval_min=payload.check_interval_min,
        toc_url=payload.toc_url,
        category=payload.category,
        # Auto-select strategy: use ToC scraper when a ToC URL is provided
        check_strategy=(
            CheckStrategy.TOC_SCRAPER if payload.toc_url else CheckStrategy.INCREMENTAL_PROBE
        ),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_read(item)


@router.get("", response_model=list[ItemRead])
def list_items(
    db: DbDep,
    user_id: str | None = None,
    active_only: bool = False,
):
    q = db.query(TrackedItem)
    if user_id:
        q = q.filter(TrackedItem.user_id == user_id)
    if active_only:
        q = q.filter(TrackedItem.is_active.is_(True))
    return [_to_read(i) for i in q.order_by(TrackedItem.created_at.desc()).all()]


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: str, db: DbDep):
    return _to_read(_get_or_404(item_id, db))


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: str, payload: ItemUpdate, db: DbDep):
    item = _get_or_404(item_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    # Re-run pattern detection when a new manual regex is supplied
    manual_regex = update_data.pop("manual_regex", None)
    if manual_regex:
        detection = detect_pattern(item.original_url, manual_regex)
        item.url_template = detection.url_template
        item.chapter_regex = detection.chapter_regex
        item.pattern_source = detection.pattern_source

    # When toc_url is being set/cleared, auto-adjust the strategy unless the
    # caller explicitly supplied a check_strategy in the same request.
    if "toc_url" in update_data and "check_strategy" not in update_data:
        new_toc = update_data["toc_url"]
        if new_toc and item.check_strategy != CheckStrategy.TOC_SCRAPER:
            item.check_strategy = CheckStrategy.TOC_SCRAPER
        elif not new_toc and item.check_strategy == CheckStrategy.TOC_SCRAPER:
            item.check_strategy = CheckStrategy.INCREMENTAL_PROBE

    for key, value in update_data.items():
        setattr(item, key, value)

    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _to_read(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: str, db: DbDep):
    item = _get_or_404(item_id, db)
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


@router.get("/{item_id}/next", response_model=NextChapterResponse)
def get_next_chapter(item_id: str, db: DbDep):
    item = _get_or_404(item_id, db)

    if not item.url_template:
        return NextChapterResponse(
            item_id=item_id,
            next_chapter=None,
            next_url=None,
            message="No URL template — cannot determine next chapter.",
        )

    if item.current_chapter is None:
        return NextChapterResponse(
            item_id=item_id,
            next_chapter=None,
            next_url=None,
            message="No current chapter recorded yet.",
        )

    # Check whether the user is already up to date
    if item.latest_chapter is not None:
        try:
            if float(item.current_chapter) >= float(item.latest_chapter):
                return NextChapterResponse(
                    item_id=item_id,
                    next_chapter=None,
                    next_url=None,
                    message="You are up to date!",
                )
        except ValueError:
            if item.current_chapter == item.latest_chapter:
                return NextChapterResponse(
                    item_id=item_id,
                    next_chapter=None,
                    next_url=None,
                    message="You are up to date!",
                )

    try:
        next_num = str(int(float(item.current_chapter)) + 1)
    except ValueError:
        return NextChapterResponse(
            item_id=item_id,
            next_chapter=None,
            next_url=None,
            message="Current chapter is non-numeric; cannot auto-increment.",
        )

    return NextChapterResponse(
        item_id=item_id,
        next_chapter=next_num,
        next_url=build_chapter_url(item.url_template, next_num),
        message="Next chapter URL generated.",
    )


@router.post("/{item_id}/mark-read", response_model=ItemRead)
def mark_read(item_id: str, payload: MarkReadRequest, db: DbDep):
    item = _get_or_404(item_id, db)
    item.current_chapter = payload.chapter
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _to_read(item)


# ---------------------------------------------------------------------------
# Manual update checks
# ---------------------------------------------------------------------------


@router.post("/{item_id}/check", response_model=dict)
async def trigger_check(item_id: str, db: DbDep):
    item = _get_or_404(item_id, db)
    log = await check_item(item, db)
    return {
        "success": log.success,
        "previous_latest_chapter": log.previous_latest_chapter,
        "new_latest_chapter": log.new_latest_chapter,
        "error_message": log.error_message,
    }


@router.post("/check-all", response_model=dict)
async def trigger_check_all(db: DbDep):
    items = db.query(TrackedItem).filter(TrackedItem.is_active.is_(True)).all()
    results = []
    for item in items:
        log = await check_item(item, db)
        results.append(
            {
                "item_id": item.id,
                "title": item.title,
                "success": log.success,
                "new_latest_chapter": log.new_latest_chapter,
            }
        )
    return {"checked": len(results), "results": results}
