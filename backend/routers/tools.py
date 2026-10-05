from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.auth import current_identity
from services.site_checker import diagnose_url, freewebnovel_series_url, freewebnovel_template, parse_freewebnovel, safe_get
from services.pattern_detection import detect_pattern

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(current_identity)])


class UrlInput(BaseModel):
    url: str


@router.post("/site-test")
async def site_test(payload: UrlInput):
    return await diagnose_url(payload.url)


@router.post("/preview")
async def preview(payload: UrlInput):
    detection = detect_pattern(payload.url)
    series_url = freewebnovel_series_url(payload.url)
    access = await diagnose_url(series_url or payload.url)
    found = {}
    if series_url and access["state"] == "REACHABLE":
        try:
            _, _, body, _ = await safe_get(series_url)
            found = parse_freewebnovel(body.decode("utf-8", "replace"), series_url)
        except Exception:
            pass
    return {"access": access, "title": found.get("title"),
            "current_chapter": detection.current_chapter,
            "latest_chapter": found.get("chapter"),
            "cover_url": found.get("cover_url"),
            "checker": "FREEWEBNOVEL" if series_url else ("TOC_SCRAPER" if not detection.url_template else "INCREMENTAL_PROBE"),
            "url_template": freewebnovel_template(series_url) or detection.url_template}
