import httpx

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pydantic import Field

from services.auth import current_identity
from services.checking.http import _challenge, diagnose_url, UnsafeSource
from services.checking.browser import browser_enabled_for
from services.checking.selector import _checker_get
from services.checking.selector import extract_toc
from services.checking.sites.comix import series_url as comix_series_url, parse_comix, merge_rendered_group
from services.checking.strategies.toc import row_class_from_html
from services.checking.browser import browser_get, BrowserFetchError
from services.checking.http import validate_public_url
from services.checking.sites.freewebnovel import series_url as freewebnovel_series_url, chapter_template as freewebnovel_template, parse_freewebnovel
from services.pattern_detection import detect_pattern

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(current_identity)])


class UrlInput(BaseModel):
    url: str


class TocPreviewInput(BaseModel):
    url: str
    example_urls: list[str] = Field(default_factory=list, max_length=2)
    row_html: str | None = Field(default=None, max_length=5000)
    preferred_group: str | None = Field(default=None, max_length=200)


@router.post("/toc-preview")
async def toc_preview(payload: TocPreviewInput):
    # REQ-016: this is public source data, but the route still requires login.
    try:
        await validate_public_url(payload.url)
        for url in payload.example_urls:
            await validate_public_url(url)
    except (UnsafeSource, ValueError) as exc:
        return {"state": "REJECTED", "method": "TOC_SCRAPER", "warnings": [str(exc)]}
    comix = comix_series_url(payload.url)
    try:
        if comix:
            status, _, body, headers = await _checker_get(comix, purpose="SITE_SCRAPER")
            if _challenge(status, body, headers):
                return {"state": "BLOCKED", "method": "COMIX", "warnings": ["Likely browser challenge."]}
            if status >= 400 or len(body) >= 512_001:
                return {"state": "TRUNCATED" if len(body) >= 512_001 else "HTTP_ERROR",
                        "method": "COMIX", "warnings": ["Page unavailable or truncated."]}
            found = parse_comix(body.decode("utf-8", "replace"), comix)
            if found.state == "OK" and payload.preferred_group and browser_enabled_for(comix):
                try:
                    _, _, rendered, _ = await browser_get(comix, purpose="SITE_SCRAPER", wait_seconds=2)
                    merge_rendered_group(found, rendered.decode("utf-8", "replace"), comix, payload.preferred_group)
                except BrowserFetchError:
                    found.warnings.append("Preferred group could not be checked; using the series link.")
            elif found.state == "OK" and payload.preferred_group:
                found.warnings.append("Browser group lookup is not enabled; using the series link.")
        else:
            found = await extract_toc(payload.url, examples=payload.example_urls,
                                      row_class=row_class_from_html(payload.row_html),
                                      preferred_group=payload.preferred_group)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        return {"state": "TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "FAILED",
                "method": "COMIX" if comix else "TOC_SCRAPER", "warnings": ["Could not connect to the source."]}
    except (httpx.RequestError, UnsafeSource, ValueError) as exc:
        return {"state": "FAILED", "method": "COMIX" if comix else "TOC_SCRAPER",
                "warnings": [str(exc)[:200]]}
    return {"state": found.state, "method": found.method, "confidence": found.confidence,
            "latest_chapter": found.latest.chapter if found.latest else None,
            "latest_url": found.latest.url if found.latest else None,
            "first_url": found.first_url, "title": found.title, "cover_url": found.cover_url,
            "groups": found.groups,
            "group_labels": found.group_labels,
            "samples": [{"chapter": link.chapter, "url": link.url, "group": link.group,
                         "source_page": link.source_page} for link in found.links[:6]],
            "warnings": found.warnings}


@router.post("/site-test")
async def site_test(payload: UrlInput):
    return await diagnose_url(payload.url)


@router.post("/preview")
async def preview(payload: UrlInput):
    detection = detect_pattern(payload.url)
    series_url = freewebnovel_series_url(payload.url)
    comix = comix_series_url(payload.url)
    access = await diagnose_url(series_url or comix or payload.url)
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
    if comix and access["state"] == "REACHABLE":
        try:
            status, _, body, headers = await _checker_get(comix, purpose="SITE_SCRAPER")
            if 200 <= status < 300 and len(body) < 512_001 and not _challenge(status, body, headers):
                comix_result = parse_comix(body.decode("utf-8", "replace"), comix)
                if comix_result.state == "OK":
                    found = {"title": comix_result.title, "chapter": comix_result.latest.chapter,
                             "cover_url": comix_result.cover_url}
        except Exception:
            pass
    return {"access": access, "title": found.get("title"),
            "current_chapter": detection.current_chapter,
            "latest_chapter": found.get("chapter"),
            "cover_url": found.get("cover_url"),
            "checker": "FREEWEBNOVEL" if series_url else ("COMIX" if comix else
                       ("TOC_SCRAPER" if not detection.url_template else "INCREMENTAL_PROBE")),
            "url_template": freewebnovel_template(series_url) or detection.url_template}
