from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.auth import current_identity
from services.checking.http import _challenge, diagnose_url
from services.checking.browser import browser_enabled_for
from services.checking.selector import _checker_get
from services.checking.sites.freewebnovel import series_url as freewebnovel_series_url, chapter_template as freewebnovel_template, parse_freewebnovel
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
    if series_url and (access["state"] == "REACHABLE" or
                       access["state"] in {"LIKELY_CLOUDFLARE", "INCONCLUSIVE", "TIMEOUT"} and
                       browser_enabled_for(series_url)):
        try:
            status, _, body, headers = await _checker_get(series_url, purpose="SITE_SCRAPER")
            if 200 <= status < 300 and not _challenge(status, body, headers):
                found = parse_freewebnovel(body.decode("utf-8", "replace"), series_url)
                if access["state"] != "REACHABLE":
                    access = {"state": "REACHABLE_VIA_BROWSER", "status_code": status,
                              "final_url": series_url}
        except Exception:
            pass
    return {"access": access, "title": found.get("title"),
            "current_chapter": detection.current_chapter,
            "latest_chapter": found.get("chapter"),
            "cover_url": found.get("cover_url"),
            "checker": "FREEWEBNOVEL" if series_url else ("TOC_SCRAPER" if not detection.url_template else "INCREMENTAL_PROBE"),
            "url_template": freewebnovel_template(series_url) or detection.url_template}
