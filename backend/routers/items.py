"""Authorized item, progress, check, and legacy import/export routes."""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
import httpx
from sqlalchemy.orm import Session

from database import get_db
from models.check_log import ChapterCheckLog
from models.item import CheckStrategy, TrackedItem
from schemas.item import ItemCreate, ItemRead, ItemUpdate, MarkReadRequest, NextChapterResponse
from services.auth import Identity, IdentityDep, owner_id
from services.checking.orchestrator import MANUAL_CHECK_COOLDOWN_SECONDS, _last_manual_check, check_item
from services.pattern_detection import build_chapter_url, detect_pattern
from services.checking.http import UnsafeSource, safe_get
from services.checking.sites.freewebnovel import series_url as freewebnovel_series_url, chapter_template as freewebnovel_template
from services.covers import cover_path, save_cover, fetch_cover, MAX_UPLOAD

router = APIRouter(prefix="/items", tags=["items"])
DbDep = Annotated[Session, Depends(get_db)]


def _visible_query(db: Session, identity: Identity, requested_owner: str | None = None):
    owner = owner_id(identity, requested_owner)
    query = db.query(TrackedItem).filter(TrackedItem.user_id == owner)
    if identity.session.safe_view_enabled:
        query = query.filter(TrackedItem.is_sensitive.is_(False))
    return query


def _get_or_404(item_id: str, db: Session, identity: Identity) -> TrackedItem:
    item = _visible_query(db, identity).filter(TrackedItem.id == item_id).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    return item


def _has_unread(item: TrackedItem) -> bool | None:
    if item.latest_chapter is None:
        return None
    if item.current_chapter is None or not item.current_chapter.strip():
        try:
            return float(item.latest_chapter) >= 1
        except ValueError:
            return None
    try:
        return float(item.latest_chapter) > float(item.current_chapter)
    except ValueError:
        return item.latest_chapter != item.current_chapter


def _to_read(item: TrackedItem) -> ItemRead:
    data = {col.name: getattr(item, col.name) for col in item.__table__.columns}
    for field in ("last_checked_at", "latest_chapter_at", "created_at", "updated_at"):
        value = data.get(field)
        if isinstance(value, datetime) and value.tzinfo is None:
            data[field] = value.replace(tzinfo=timezone.utc)
    return ItemRead.model_validate({**data, "has_unread": _has_unread(item)})


@router.post("", response_model=ItemRead, status_code=201)
async def create_item(payload: ItemCreate, db: DbDep, identity: IdentityDep):
    # REQ-004: a chapter example supplies the link pattern, never reading progress.
    detection = detect_pattern(payload.chapter_url or payload.url, payload.manual_regex)
    series_url = freewebnovel_series_url(payload.url)
    template = (freewebnovel_template(series_url)
                if series_url and payload.strategy_override in {None, "FREEWEBNOVEL"}
                else detection.url_template)
    toc_url = payload.toc_url or (payload.url if payload.chapter_url else None)
    inferred_chapter = None if payload.chapter_url else detection.current_chapter
    item = TrackedItem(
        id=str(uuid.uuid4()), user_id=identity.library_user_id,
        title=payload.title, original_url=payload.url, series_url=series_url,
        url_template=template, chapter_regex=detection.chapter_regex,
        pattern_source=detection.pattern_source,
        current_chapter=payload.current_chapter or inferred_chapter,
        latest_chapter=payload.latest_chapter or inferred_chapter,
        check_interval_min=payload.check_interval_min,
        toc_url=toc_url, category=payload.category,
        note=payload.note, is_sensitive=payload.is_sensitive,
        strategy_override=payload.strategy_override,
        check_strategy=(CheckStrategy.TOC_THEN_PROBE if toc_url else CheckStrategy.INCREMENTAL_PROBE),
    )
    if item.is_sensitive and identity.session.safe_view_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reveal sensitive entries before creating one.")
    db.add(item)
    db.commit()
    item.cover_filename = await fetch_cover(series_url or payload.url)
    if item.cover_filename:
        db.commit()
    db.refresh(item)
    return _to_read(item)


@router.get("", response_model=list[ItemRead])
def list_items(db: DbDep, identity: IdentityDep, user_id: str | None = None, active_only: bool = False):
    query = _visible_query(db, identity, user_id)
    if active_only:
        query = query.filter(TrackedItem.is_active.is_(True))
    return [_to_read(item) for item in query.order_by(TrackedItem.created_at.desc()).all()]


@router.get("/export")
def export_items(db: DbDep, identity: IdentityDep):
    """Legacy JSON export of currently visible items; full archive is separate."""
    return [{key: getattr(item, key) for key in (
        "title", "original_url", "url_template", "chapter_regex", "pattern_source",
        "check_strategy", "toc_url", "category", "current_chapter", "latest_chapter",
        "check_interval_min", "is_active", "note", "is_sensitive")}
        for item in _visible_query(db, identity).order_by(TrackedItem.created_at).all()]


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: str, db: DbDep, identity: IdentityDep):
    return _to_read(_get_or_404(item_id, db, identity))


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: str, payload: ItemUpdate, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_sensitive") and identity.session.safe_view_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reveal sensitive entries before marking one sensitive.")
    manual_regex = data.pop("manual_regex", None)
    if manual_regex:
        detection = detect_pattern(item.original_url, manual_regex)
        item.url_template = detection.url_template
        item.chapter_regex = detection.chapter_regex
        item.pattern_source = detection.pattern_source
    if "toc_url" in data and "check_strategy" not in data:
        item.check_strategy = CheckStrategy.TOC_SCRAPER if data["toc_url"] else CheckStrategy.INCREMENTAL_PROBE
    if "latest_chapter" in data and item.pending_latest_chapter:
        item.dismissed_candidate = item.pending_latest_chapter if data["latest_chapter"] != item.pending_latest_chapter else None
        item.pending_latest_chapter = None
        item.pending_chapter_url = None
    for key, value in data.items():
        setattr(item, key, value)
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _to_read(item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    old_cover = item.cover_filename
    db.delete(item)
    db.commit()
    if old_cover:
        cover_path(old_cover).unlink(missing_ok=True)


@router.get("/{item_id}/cover")
def get_cover(item_id: str, db: DbDep, identity: IdentityDep, user_id: str | None = None):
    item = _visible_query(db, identity, user_id).filter(TrackedItem.id == item_id).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cover not found.")
    if not item.cover_filename or not cover_path(item.cover_filename).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cover not found.")
    return FileResponse(cover_path(item.cover_filename), media_type="image/jpeg",
                        headers={"Cache-Control": "private, no-store"})


@router.post("/{item_id}/cover", response_model=ItemRead)
async def upload_cover(item_id: str, db: DbDep, identity: IdentityDep, file: UploadFile = File()):
    item = _get_or_404(item_id, db, identity)
    raw = await file.read(MAX_UPLOAD + 1)
    try:
        filename = save_cover(raw)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    old = item.cover_filename
    item.cover_filename = filename
    db.commit()
    if old:
        cover_path(old).unlink(missing_ok=True)
    db.refresh(item)
    return _to_read(item)


class CoverUrlRequest(BaseModel):
    url: str


@router.post("/{item_id}/cover-url", response_model=ItemRead)
async def set_cover_url(item_id: str, payload: CoverUrlRequest, db: DbDep, identity: IdentityDep):
    """Fetch and normalize a public image without exposing the browser to the remote URL."""
    item = _get_or_404(item_id, db, identity)
    try:
        response_status, _, raw, headers = await safe_get(payload.url, max_bytes=MAX_UPLOAD + 1)
        if response_status != 200:
            raise ValueError(f"Image URL returned HTTP {response_status}.")
        if not headers.get("content-type", "").lower().startswith("image/"):
            raise ValueError("URL did not return an image.")
        if len(raw) > MAX_UPLOAD:
            raise ValueError("Cover exceeds 5 MB.")
        filename = save_cover(raw)
    except (UnsafeSource, httpx.RequestError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)[:200]) from exc
    old = item.cover_filename
    item.cover_filename = filename
    try:
        db.commit()
    except Exception:
        db.rollback()
        cover_path(filename).unlink(missing_ok=True)
        raise
    if old:
        cover_path(old).unlink(missing_ok=True)
    db.refresh(item)
    return _to_read(item)


@router.delete("/{item_id}/cover", status_code=204)
def remove_cover(item_id: str, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    old = item.cover_filename
    item.cover_filename = None
    db.commit()
    if old:
        cover_path(old).unlink(missing_ok=True)


@router.get("/{item_id}/next", response_model=NextChapterResponse)
def get_next_chapter(item_id: str, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    if not item.url_template or "{n}" not in item.url_template:
        return NextChapterResponse(item_id=item_id, next_chapter=None, next_url=None,
                                   message="A chapter URL pattern is needed to open the next chapter.")
    try:
        # REQ-011: no saved progress starts with chapter 1 without recording a read.
        next_num = str(int(float(item.current_chapter)) + 1) if item.current_chapter else "1"
        if item.latest_chapter and float(next_num) > float(item.latest_chapter):
            return NextChapterResponse(item_id=item_id, next_chapter=None, next_url=None,
                                       message="You are up to date!")
    except ValueError:
        return NextChapterResponse(item_id=item_id, next_chapter=None, next_url=None,
                                   message="Chapter number cannot be incremented automatically.")
    return NextChapterResponse(item_id=item_id, next_chapter=next_num,
                               next_url=build_chapter_url(item.url_template, next_num),
                               message="Next chapter URL generated.")


@router.post("/{item_id}/mark-read", response_model=ItemRead)
def mark_read(item_id: str, payload: MarkReadRequest, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    item.current_chapter = payload.chapter
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _to_read(item)


@router.post("/{item_id}/check")
async def trigger_check(item_id: str, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    now = datetime.now(timezone.utc)
    last = _last_manual_check.get(item_id)
    if last and (now - last).total_seconds() < MANUAL_CHECK_COOLDOWN_SECONDS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Wait before checking again.")
    _last_manual_check[item_id] = now
    log = await check_item(item, db)
    return {"success": log.success, "outcome": log.outcome,
            "previous_latest_chapter": log.previous_latest_chapter,
            "new_latest_chapter": log.new_latest_chapter,
            "pending_chapter": log.pending_chapter, "error_message": log.error_message}


@router.post("/check-all")
async def trigger_check_all(db: DbDep, identity: IdentityDep):
    items = _visible_query(db, identity).filter(TrackedItem.is_active.is_(True)).all()
    results = []
    for item in items:
        log = await check_item(item, db, bypass_rate_limit=True)
        results.append({"item_id": item.id, "title": item.title, "success": log.success,
                        "outcome": log.outcome, "new_latest_chapter": log.new_latest_chapter})
    return {"checked": len(results), "results": results}


@router.get("/{item_id}/history")
def get_check_history(item_id: str, db: DbDep, identity: IdentityDep, limit: int = 20):
    _get_or_404(item_id, db, identity)
    logs = db.query(ChapterCheckLog).filter(ChapterCheckLog.item_id == item_id).order_by(
        ChapterCheckLog.checked_at.desc()).limit(max(1, min(limit, 100))).all()
    return [{"id": log.id, "checked_at": log.checked_at.replace(tzinfo=timezone.utc).isoformat()
             if log.checked_at.tzinfo is None else log.checked_at.isoformat(),
             "success": log.success, "outcome": log.outcome,
             "previous_latest_chapter": log.previous_latest_chapter,
             "new_latest_chapter": log.new_latest_chapter,
             "pending_chapter": log.pending_chapter,
             "error_message": log.error_message} for log in logs]


@router.post("/{item_id}/resolve-pending", response_model=ItemRead)
def resolve_pending(item_id: str, chapter: Annotated[str, Body(embed=True)], db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    if not item.pending_latest_chapter:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending result.")
    item.dismissed_candidate = item.pending_latest_chapter if chapter != item.pending_latest_chapter else None
    item.latest_chapter = chapter
    item.pending_latest_chapter = None
    item.pending_chapter_url = None
    item.latest_chapter_at = datetime.now(timezone.utc)
    item.last_outcome = "RESOLVED"
    db.commit()
    db.refresh(item)
    return _to_read(item)


def _bulk_items(ids: list[str], db: Session, identity: Identity):
    return _visible_query(db, identity).filter(TrackedItem.id.in_(ids)).all()


@router.post("/bulk-delete")
def bulk_delete(ids: Annotated[list[str], Body()], db: DbDep, identity: IdentityDep):
    items = _bulk_items(ids, db, identity)
    for item in items:
        db.delete(item)
    db.commit()
    return {"deleted": len(items)}


@router.post("/bulk-pause")
def bulk_pause(ids: Annotated[list[str], Body()], db: DbDep, identity: IdentityDep):
    items = _bulk_items(ids, db, identity)
    for item in items:
        item.is_active = False
    db.commit()
    return {"paused": len(items)}


@router.post("/bulk-resume")
def bulk_resume(ids: Annotated[list[str], Body()], db: DbDep, identity: IdentityDep):
    items = _bulk_items(ids, db, identity)
    for item in items:
        item.is_active = True
    db.commit()
    return {"resumed": len(items)}


@router.post("/import", status_code=201)
def import_items(records: Annotated[list[dict], Body()], db: DbDep, identity: IdentityDep):
    if len(records) > 1000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Import has too many entries.")
    existing = {url for (url,) in db.query(TrackedItem.original_url).filter(
        TrackedItem.user_id == identity.library_user_id).all()}
    created = skipped = 0
    pending: list[TrackedItem] = []
    for rec in records:
        url = str(rec.get("original_url", "")).strip()
        if not url:
            skipped += 1
            continue
        try:
            ItemCreate(url=url, toc_url=rec.get("toc_url"))
            if rec.get("url_template"):
                ItemCreate.web_url(str(rec["url_template"]).replace("{n}", "1"))
            if rec.get("check_strategy", "INCREMENTAL_PROBE") not in {s.value for s in CheckStrategy}:
                raise ValueError("Invalid checker strategy.")
        except (ValidationError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Import contains an invalid entry.") from exc
        if url in existing:
            skipped += 1
            continue
        item = TrackedItem(id=str(uuid.uuid4()), user_id=identity.library_user_id,
                           title=rec.get("title"), original_url=url,
                           url_template=rec.get("url_template"),
                           chapter_regex=rec.get("chapter_regex"),
                           pattern_source=rec.get("pattern_source", "AUTO"),
                           check_strategy=rec.get("check_strategy", "INCREMENTAL_PROBE"),
                           toc_url=rec.get("toc_url"), category=rec.get("category"),
                           current_chapter=rec.get("current_chapter"),
                           latest_chapter=rec.get("latest_chapter"),
                           check_interval_min=int(rec.get("check_interval_min") or 60),
                           is_active=bool(rec.get("is_active", True)),
                           is_sensitive=bool(rec.get("is_sensitive", False)), note=rec.get("note"))
        pending.append(item)
        existing.add(url)
        created += 1
    db.add_all(pending)
    db.commit()
    return {"created": created, "skipped": skipped}
