"""Versioned, password-confirmed account archive."""
import io
import json
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from models.item import TrackedItem
from services.auth import DbDep, IdentityDep, verify_password
from services.covers import cover_path, save_cover

router = APIRouter(prefix="/archive", tags=["archive"])
MAX_ARCHIVE = 100_000_000
FIELDS = ("title", "original_url", "url_template", "chapter_regex", "pattern_source",
          "check_strategy", "toc_url", "category", "current_chapter", "latest_chapter",
          "check_interval_min", "is_active", "note", "is_sensitive", "series_url",
          "strategy_override")


class ExportRequest(BaseModel):
    password: str


def _normalized(url: str) -> str:
    p = urlsplit(url.strip())
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("Invalid source URL.")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", p.query, ""))


@router.post("/export")
def export_archive(payload: ExportRequest, identity: IdentityDep, db: DbDep):
    if not verify_password(payload.password, identity.user.hashed_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password confirmation failed.")
    rows = db.query(TrackedItem).filter(TrackedItem.user_id == identity.library_user_id).order_by(TrackedItem.created_at).all()
    data = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"format": "urlmediatracker-account", "version": 1, "includes_sensitive": True}))
        for row in rows:
            entry = {key: getattr(row, key) for key in FIELDS}
            entry["pattern_source"] = row.pattern_source.value if hasattr(row.pattern_source, "value") else row.pattern_source
            entry["cover"] = None
            if row.cover_filename and cover_path(row.cover_filename).is_file():
                name = f"covers/{row.id}.jpg"
                archive.write(cover_path(row.cover_filename), name)
                entry["cover"] = name
            data.append(entry)
        archive.writestr("items.json", json.dumps(data, ensure_ascii=False))
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=tracker-account.zip",
                             "Cache-Control": "no-store"})


@router.post("/import", status_code=201)
async def import_archive(identity: IdentityDep, db: DbDep, file: UploadFile = File()):
    raw = await file.read(MAX_ARCHIVE + 1)
    if len(raw) > MAX_ARCHIVE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Archive too large.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if len(names) > 1200 or any(name.startswith("/") or ".." in Path(name).parts for name in names):
                raise ValueError("Invalid archive paths.")
            if sum(entry.file_size for entry in archive.infolist()) > MAX_ARCHIVE:
                raise ValueError("Archive expands beyond size limit.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest != {"format": "urlmediatracker-account", "version": 1, "includes_sensitive": True}:
                raise ValueError("Unsupported archive version.")
            records = json.loads(archive.read("items.json"))
            if not isinstance(records, list) or len(records) > 1000:
                raise ValueError("Invalid item list.")
            existing = {_normalized(url) for (url,) in db.query(TrackedItem.original_url).filter(
                TrackedItem.user_id == identity.library_user_id).all()}
            pending = []
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Invalid item record.")
                url = _normalized(str(record.get("original_url", "")))
                for key in ("series_url", "toc_url", "url_template"):
                    value = record.get(key)
                    if value is not None:
                        _normalized(str(value).replace("{n}", "1"))
                if record.get("strategy_override") not in {None, "FREEWEBNOVEL", "TOC_SCRAPER", "INCREMENTAL_PROBE", "TOC_THEN_PROBE"}:
                    raise ValueError("Invalid checker override.")
                if url in existing:
                    continue
                cover = record.get("cover")
                image = None
                if cover is not None:
                    if not isinstance(cover, str) or not cover.startswith("covers/") or cover not in names:
                        raise ValueError("Invalid cover reference.")
                    image = archive.read(cover)
                    if len(image) > 5_000_000:
                        raise ValueError("Cover exceeds size limit.")
                pending.append((record, image))
                existing.add(url)
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    created_files = []
    try:
        for record, image in pending:
            values = {key: record.get(key) for key in FIELDS}
            values["id"] = str(uuid.uuid4())
            values["user_id"] = identity.library_user_id
            values["pattern_source"] = values.get("pattern_source") or "AUTO"
            values["check_strategy"] = values.get("check_strategy") or "INCREMENTAL_PROBE"
            values["check_interval_min"] = int(values.get("check_interval_min") or 60)
            values["is_active"] = bool(values.get("is_active", True))
            values["is_sensitive"] = bool(values.get("is_sensitive", False))
            if image:
                values["cover_filename"] = save_cover(image)
                created_files.append(values["cover_filename"])
            db.add(TrackedItem(**values))
        db.commit()
    except Exception as exc:
        db.rollback()
        for name in created_files:
            cover_path(name).unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Archive could not be imported.") from exc
    return {"created": len(pending), "skipped": len(records) - len(pending)}
