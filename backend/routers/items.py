"""Authorized item, progress, check, and legacy import/export routes."""
import uuid
import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
import httpx
from sqlalchemy.orm import Session

from database import get_db
from models.check_log import ChapterCheckLog
from models.item import CheckStrategy, ItemCategory, ItemStatus, TrackedItem
from schemas.item import ItemCreate, ItemRead, ItemUpdate, MarkReadRequest, NextChapterResponse
from services.auth import Identity, IdentityDep, owner_id
from services.checking.orchestrator import MANUAL_CHECK_COOLDOWN_SECONDS, _last_manual_check, check_item
from services.pattern_detection import build_chapter_url, detect_pattern, unsafe_chapter_template
from services.checking.http import UnsafeSource, safe_get
from services.checking.sites.freewebnovel import series_url as freewebnovel_series_url, chapter_template as freewebnovel_template
from services.checking.sites.webnovel import series_url as webnovel_series_url
from services.checking.sites.royalroad import series_url as royalroad_series_url
from services.checking.sites.scribblehub import series_url as scribblehub_series_url
from services.checking.sites.comix import series_url as comix_series_url
from services.checking.strategies.toc import row_class_from_html, parse_toc_examples
from services.covers import cover_path, save_cover, fetch_cover, MAX_UPLOAD
from services.item_status import caught_up, reconcile_finished, set_status

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
    return ItemRead.model_validate({**data, "has_unread": _has_unread(item),
                                    "toc_example_urls": parse_toc_examples(item.toc_examples_json)})


def _chapter_examples(chapter_url: str | None, examples: list[str]) -> list[str]:
    """The advanced chapter URL is also the first ToC shape hint (REQ-016)."""
    return list(dict.fromkeys(([chapter_url] if chapter_url else []) + examples))[:2]


@router.post("", response_model=ItemRead, status_code=201)
async def create_item(payload: ItemCreate, db: DbDep, identity: IdentityDep):
    # REQ-004: a chapter example supplies the link pattern, never reading progress.
    detection = detect_pattern(payload.chapter_url or payload.url, payload.manual_regex)
    series_url = (freewebnovel_series_url(payload.url) or comix_series_url(payload.url) or
                  webnovel_series_url(payload.url) or royalroad_series_url(payload.url) or
                  scribblehub_series_url(payload.url))
    # REQ-020: suggest Novel for known prose sites only when no category was supplied.
    category = (ItemCategory.NOVEL if "category" not in payload.model_fields_set and
                (freewebnovel_series_url(payload.url) or webnovel_series_url(payload.url) or
                 royalroad_series_url(payload.url) or scribblehub_series_url(payload.url))
                else payload.category)
    has_opaque_site_ids = bool(webnovel_series_url(payload.url) or royalroad_series_url(payload.url) or
                               scribblehub_series_url(payload.url))
    template = (None if has_opaque_site_ids else
                freewebnovel_template(series_url)
                if series_url and payload.strategy_override in {None, "FREEWEBNOVEL"}
                else detection.url_template)
    toc_url = payload.toc_url or (series_url if has_opaque_site_ids else
                                  payload.url if payload.chapter_url or not detection.url_template else None)
    inferred_chapter = None if payload.chapter_url or has_opaque_site_ids else detection.current_chapter
    item = TrackedItem(
        id=str(uuid.uuid4()), user_id=identity.library_user_id,
        title=payload.title, original_url=payload.url, series_url=series_url,
        url_template=template, chapter_regex=detection.chapter_regex,
        pattern_source=detection.pattern_source,
        current_chapter=payload.current_chapter or inferred_chapter,
        latest_chapter=payload.latest_chapter or inferred_chapter,
        check_interval_min=payload.check_interval_min,
        toc_url=toc_url, category=category,
        note=payload.note, is_sensitive=payload.is_sensitive,
        preferred_group=payload.preferred_group,
        toc_examples_json=(json.dumps(_chapter_examples(payload.chapter_url, payload.toc_example_urls))
                           if payload.chapter_url or payload.toc_example_urls else None),
        toc_row_class=row_class_from_html(payload.toc_row_html),
        strategy_override=payload.strategy_override,
        check_strategy=(CheckStrategy.TOC_THEN_PROBE if toc_url else CheckStrategy.INCREMENTAL_PROBE),
    )
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
        query = query.filter(TrackedItem.status == ItemStatus.ONGOING.value)
    return [_to_read(item) for item in query.order_by(TrackedItem.created_at.desc()).all()]


@router.get("/export")
def export_items(db: DbDep, identity: IdentityDep):
    """Legacy JSON export of currently visible items; full archive is separate."""
    return [{key: getattr(item, key) for key in (
        "title", "original_url", "url_template", "chapter_regex", "pattern_source",
        "check_strategy", "toc_url", "category", "current_chapter", "latest_chapter",
        "check_interval_min", "is_active", "status", "note", "is_sensitive", "latest_chapter_url",
        "first_chapter_url", "preferred_group", "toc_examples_json", "toc_row_class")}
        for item in _visible_query(db, identity).order_by(TrackedItem.created_at).all()]


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: str, db: DbDep, identity: IdentityDep):
    return _to_read(_get_or_404(item_id, db, identity))


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: str, payload: ItemUpdate, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    before_detection = (
        item.url_template, item.chapter_regex, item.pattern_source, item.toc_url,
        item.strategy_override, item.check_strategy, item.preferred_group,
        item.toc_examples_json, item.toc_row_class,
    )
    data = payload.model_dump(exclude_unset=True)
    requested_status = data.pop("status", None)
    legacy_active = data.pop("is_active", None)
    manual_regex = data.pop("manual_regex", None)
    chapter_example = data.pop("chapter_url", None)
    example_urls = data.pop("toc_example_urls", None)
    row_html = data.pop("toc_row_html", None)
    if example_urls is not None:
        item.toc_examples_json = json.dumps(example_urls) if example_urls else None
    if chapter_example:
        hints = _chapter_examples(chapter_example, parse_toc_examples(item.toc_examples_json))
        item.toc_examples_json = json.dumps(hints)
    if row_html is not None:
        item.toc_row_class = row_class_from_html(row_html)
    if chapter_example:
        # REQ-004: editing a ToC-first item can replace its chapter-link
        # pattern without treating the example number as reading progress.
        try:
            detection = detect_pattern(chapter_example, manual_regex)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        item.url_template = detection.url_template
        item.chapter_regex = detection.chapter_regex
        item.pattern_source = detection.pattern_source
    elif manual_regex:
        example = (item.url_template.replace("{n}", item.latest_chapter or item.current_chapter or "1")
                   if item.url_template else (parse_toc_examples(item.toc_examples_json) or [item.original_url])[0])
        try:
            detection = detect_pattern(example, manual_regex)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        # REQ-016: a manual regex can identify real ToC links without a safe
        # one-placeholder URL template for sequential probing.
        item.url_template = detection.url_template
        item.chapter_regex = detection.chapter_regex
        item.pattern_source = detection.pattern_source
    if "toc_url" in data and "check_strategy" not in data:
        item.check_strategy = CheckStrategy.TOC_SCRAPER if data["toc_url"] else CheckStrategy.INCREMENTAL_PROBE
    if "toc_url" in data and data["toc_url"] != item.toc_url:
        item.toc_latest_page_url = None
    if "latest_chapter" in data and item.pending_latest_chapter:
        item.dismissed_candidate = item.pending_latest_chapter if data["latest_chapter"] != item.pending_latest_chapter else None
        item.pending_latest_chapter = None
        item.pending_chapter_url = None
    if "latest_chapter" in data and data["latest_chapter"] != item.latest_chapter:
        item.latest_chapter_url = None
    for key, value in data.items():
        setattr(item, key, value)
    if requested_status is not None:
        if requested_status == ItemStatus.FINISHED and (
            item.status not in {ItemStatus.COMPLETED.value, ItemStatus.FINISHED.value} or
            (item.status != ItemStatus.FINISHED.value and not caught_up(item.current_chapter, item.latest_chapter))
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Finish requires a Completed item caught up to a known latest chapter.")
        set_status(item, requested_status)
    elif legacy_active is not None:
        set_status(item, ItemStatus.ONGOING if legacy_active else ItemStatus.PAUSED)
    reconcile_finished(item)
    after_detection = (
        item.url_template, item.chapter_regex, item.pattern_source, item.toc_url,
        item.strategy_override, item.check_strategy, item.preferred_group,
        item.toc_examples_json, item.toc_row_class,
    )
    if after_detection != before_detection:
        # REQ-005/016: an old failure is about the previous checker settings.
        # The next scheduled or explicit check will produce the new status.
        item.last_outcome = None
        item.last_error = None
        item.consecutive_failures = 0
        item.last_checked_at = None
        item.pending_latest_chapter = None
        item.pending_chapter_url = None
        item.dismissed_candidate = None
        if item.toc_url != before_detection[3] or item.toc_examples_json != before_detection[7] or item.toc_row_class != before_detection[8]:
            item.toc_latest_page_url = None
        _last_manual_check.pop(item.id, None)
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _to_read(item).model_copy(update={"check_config_changed": after_detection != before_detection})


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
    toc = item.toc_url or item.series_url or item.original_url
    try:
        # REQ-011: no saved progress starts with chapter 1 without recording a read.
        next_num = str(int(float(item.current_chapter)) + 1) if item.current_chapter else "1"
        if item.latest_chapter and float(next_num) > float(item.latest_chapter):
            return NextChapterResponse(item_id=item_id, next_chapter=None, next_url=None,
                                       message="You are up to date!", destination="NONE")
    except ValueError:
        return NextChapterResponse(item_id=item_id, next_chapter=None, next_url=toc,
                                   message="Exact chapter unknown; opening the ToC.", destination="TOC")
    if (not (webnovel_series_url(item.series_url or item.original_url) or
             royalroad_series_url(item.series_url or item.original_url) or
             scribblehub_series_url(item.series_url or item.original_url)) and item.url_template and
            "{n}" in item.url_template and not unsafe_chapter_template(item.url_template)):
        return NextChapterResponse(item_id=item_id, next_chapter=next_num,
                                   next_url=build_chapter_url(item.url_template, next_num),
                                   message="Next chapter URL generated.", destination="CHAPTER")
    if next_num == "1" and item.first_chapter_url:
        return NextChapterResponse(item_id=item_id, next_chapter=next_num,
                                   next_url=item.first_chapter_url, message="Opening chapter 1.",
                                   destination="CHAPTER")
    if next_num == item.latest_chapter and item.latest_chapter_url:
        return NextChapterResponse(item_id=item_id, next_chapter=next_num,
                                   next_url=item.latest_chapter_url, message="Opening latest chapter.",
                                   destination="CHAPTER")
    return NextChapterResponse(item_id=item_id, next_chapter=next_num if item.latest_chapter else None,
                               next_url=toc, message="Exact chapter link unavailable; opening the ToC.",
                               destination="TOC")


@router.post("/{item_id}/mark-read", response_model=ItemRead)
def mark_read(item_id: str, payload: MarkReadRequest, db: DbDep, identity: IdentityDep):
    item = _get_or_404(item_id, db, identity)
    item.current_chapter = payload.chapter
    reconcile_finished(item)
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
    items = _visible_query(db, identity).filter(TrackedItem.status == ItemStatus.ONGOING.value).all()
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
    reconcile_finished(item)
    item.latest_chapter_url = item.pending_chapter_url if chapter == item.pending_latest_chapter else None
    item.pending_latest_chapter = None
    item.pending_chapter_url = None
    item.latest_chapter_at = datetime.now(timezone.utc)
    item.last_outcome = "RESOLVED"
    item.last_error = None
    item.consecutive_failures = 0
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
    changed = [item for item in items if item.status == ItemStatus.ONGOING.value]
    for item in changed:
        set_status(item, ItemStatus.PAUSED)
    db.commit()
    return {"paused": len(changed)}


@router.post("/bulk-resume")
def bulk_resume(ids: Annotated[list[str], Body()], db: DbDep, identity: IdentityDep):
    items = _bulk_items(ids, db, identity)
    changed = [item for item in items if item.status == ItemStatus.PAUSED.value]
    for item in changed:
        set_status(item, ItemStatus.ONGOING)
    db.commit()
    return {"resumed": len(changed)}


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
            imported_status = ItemStatus(rec.get("status") or ("ONGOING" if rec.get("is_active", True) else "PAUSED"))
            if imported_status == ItemStatus.FINISHED and not caught_up(rec.get("current_chapter"), rec.get("latest_chapter")):
                raise ValueError("Finished item is not caught up.")
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
                           check_interval_min=int(rec.get("check_interval_min") or 360),
                           status=imported_status.value, is_active=imported_status == ItemStatus.ONGOING,
                           is_sensitive=bool(rec.get("is_sensitive", False)), note=rec.get("note"))
        pending.append(item)
        existing.add(url)
        created += 1
    db.add_all(pending)
    db.commit()
    return {"created": created, "skipped": skipped}
