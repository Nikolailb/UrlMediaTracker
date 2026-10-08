import httpx
from typing import Literal

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
from services.checking.sites.webnovel import series_url as webnovel_series_url, parse_webnovel, fetch_webnovel, MAX_PAGE_BYTES
from services.checking.sites.royalroad import series_url as royalroad_series_url, parse_royalroad, fetch_royalroad
from services.checking.sites.royalroad import MAX_PAGE_BYTES as ROYALROAD_MAX_PAGE_BYTES
from services.checking.sites.scribblehub import series_url as scribblehub_series_url, parse_scribblehub, fetch_scribblehub
from services.checking.sites.scribblehub import MAX_PAGE_BYTES as SCRIBBLEHUB_MAX_PAGE_BYTES
from services.pattern_detection import detect_pattern
from urllib.parse import urlsplit

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(current_identity)])


class UrlInput(BaseModel):
    url: str


class TocPreviewInput(BaseModel):
    url: str
    example_urls: list[str] = Field(default_factory=list, max_length=2)
    row_html: str | None = Field(default=None, max_length=5000)
    preferred_group: str | None = Field(default=None, max_length=200)
    chapter_regex: str | None = Field(default=None, max_length=500)
    strategy_override: Literal["AUTO", "COMIX", "FREEWEBNOVEL", "WEBNOVEL", "ROYALROAD", "SCRIBBLEHUB", "TOC_SCRAPER", "TOC_THEN_PROBE", "INCREMENTAL_PROBE"] = "AUTO"


@router.post("/toc-preview")
async def toc_preview(payload: TocPreviewInput):
    # REQ-016: this is public source data, but the route still requires login.
    try:
        await validate_public_url(payload.url)
        for url in payload.example_urls:
            await validate_public_url(url)
    except (UnsafeSource, ValueError) as exc:
        return {"state": "REJECTED", "method": "TOC_SCRAPER", "warnings": [str(exc)]}
    selected = payload.strategy_override
    comix = comix_series_url(payload.url)
    freewebnovel = freewebnovel_series_url(payload.url)
    webnovel = webnovel_series_url(payload.url)
    royalroad = royalroad_series_url(payload.url)
    scribblehub = scribblehub_series_url(payload.url)
    if selected == "INCREMENTAL_PROBE":
        return {"state": "UNSUPPORTED", "method": "INCREMENTAL_PROBE",
                "warnings": ["Sequential URL probing does not read a ToC. Preview its chapter URL pattern instead."]}
    if ((selected == "COMIX" and not comix) or (selected == "FREEWEBNOVEL" and not freewebnovel)
            or (selected == "WEBNOVEL" and not webnovel) or (selected == "ROYALROAD" and not royalroad)
            or (selected == "SCRIBBLEHUB" and not scribblehub)):
        return {"state": "UNSUPPORTED", "method": selected,
                "warnings": ["This site checker does not match the supplied series URL."]}
    use_comix = bool(comix and selected in {"AUTO", "COMIX"})
    use_freewebnovel = bool(freewebnovel and selected in {"AUTO", "FREEWEBNOVEL"})
    use_webnovel = bool(webnovel and selected in {"AUTO", "WEBNOVEL"})
    use_royalroad = bool(royalroad and selected in {"AUTO", "ROYALROAD"})
    use_scribblehub = bool(scribblehub and selected in {"AUTO", "SCRIBBLEHUB"})
    try:
        if use_comix:
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
        elif use_royalroad:
            status, _, body, headers, _ = await fetch_royalroad(royalroad)
            if len(body) > ROYALROAD_MAX_PAGE_BYTES:
                return {"state": "TRUNCATED", "method": "ROYALROAD", "warnings": ["Page exceeded the 3 MB limit."]}
            found = parse_royalroad(body.decode("utf-8", "replace"), royalroad) if status == 200 else None
            if found is None and _challenge(status, body, headers):
                return {"state": "BLOCKED", "method": "ROYALROAD", "warnings": ["Likely browser challenge."]}
            if found is None:
                return {"state": "HTTP_ERROR", "method": "ROYALROAD", "warnings": [f"HTTP {status}."]}
        elif use_scribblehub:
            status, _, body, headers, _ = await fetch_scribblehub(scribblehub)
            if len(body) > SCRIBBLEHUB_MAX_PAGE_BYTES:
                return {"state": "TRUNCATED", "method": "SCRIBBLEHUB", "warnings": ["Page exceeded the 1 MB limit."]}
            found = parse_scribblehub(body.decode("utf-8", "replace"), scribblehub) if status == 200 else None
            if found is None and _challenge(status, body, headers):
                return {"state": "BLOCKED", "method": "SCRIBBLEHUB", "warnings": ["Likely browser challenge."]}
            if found is None:
                return {"state": "HTTP_ERROR", "method": "SCRIBBLEHUB", "warnings": [f"HTTP {status}."]}
        elif use_webnovel:
            status, _, body, headers, _ = await fetch_webnovel(webnovel)
            if len(body) > MAX_PAGE_BYTES:
                return {"state": "TRUNCATED", "method": "WEBNOVEL", "warnings": ["Page exceeded the 5 MB limit."]}
            found = parse_webnovel(body.decode("utf-8", "replace"), webnovel) if status == 200 else None
            if found is None and _challenge(status, body, headers):
                return {"state": "BLOCKED", "method": "WEBNOVEL", "warnings": ["Likely browser challenge."]}
            if found is None:
                return {"state": "HTTP_ERROR", "method": "WEBNOVEL", "warnings": [f"HTTP {status}."]}
        elif use_freewebnovel:
            status, _, body, headers = await _checker_get(freewebnovel, purpose="SITE_SCRAPER")
            if _challenge(status, body, headers):
                return {"state": "BLOCKED", "method": "FREEWEBNOVEL", "warnings": ["Likely browser challenge."]}
            if status >= 400 or len(body) >= 512_001:
                return {"state": "TRUNCATED" if len(body) >= 512_001 else "HTTP_ERROR",
                        "method": "FREEWEBNOVEL", "warnings": ["Page unavailable or truncated."]}
            data = parse_freewebnovel(body.decode("utf-8", "replace"), freewebnovel)
            return {"state": "OK" if data.get("chapter") else "EMPTY", "method": "FREEWEBNOVEL",
                    "confidence": "HIGH" if data.get("chapter") else "LOW",
                    "latest_chapter": data.get("chapter"), "latest_url": data.get("chapter_url"),
                    "first_url": None, "title": data.get("title"), "cover_url": data.get("cover_url"),
                    "groups": [], "group_labels": {}, "samples": [],
                    "warnings": [] if data.get("chapter") else ["No consistent latest-chapter signals on the series page."]}
        else:
            found = await extract_toc(payload.url, examples=payload.example_urls,
                                      row_class=row_class_from_html(payload.row_html),
                                      preferred_group=payload.preferred_group,
                                      chapter_regex=payload.chapter_regex)
            if comix and found.state == "EMPTY":
                found.warnings.append("Comix loads chapter rows in the browser. Choose Automatic or Comix site checker instead of generic ToC scan.")
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        return {"state": "TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "FAILED",
                "method": "SCRIBBLEHUB" if use_scribblehub else "ROYALROAD" if use_royalroad else "WEBNOVEL" if use_webnovel else "COMIX" if use_comix else "FREEWEBNOVEL" if use_freewebnovel else "TOC_SCRAPER",
                "warnings": ["Could not connect to the source."]}
    except (httpx.RequestError, UnsafeSource, ValueError) as exc:
        return {"state": "FAILED", "method": "SCRIBBLEHUB" if use_scribblehub else "ROYALROAD" if use_royalroad else "WEBNOVEL" if use_webnovel else "COMIX" if use_comix else "FREEWEBNOVEL" if use_freewebnovel else "TOC_SCRAPER",
                "warnings": [str(exc)[:200]]}
    except BrowserFetchError as exc:
        return {"state": "TRUNCATED" if "too large" in str(exc).lower() else "FAILED",
                "method": "SCRIBBLEHUB" if use_scribblehub else "ROYALROAD" if use_royalroad else "WEBNOVEL", "warnings": [str(exc)[:200]]}
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
    webnovel = webnovel_series_url(payload.url)
    royalroad = royalroad_series_url(payload.url)
    scribblehub = scribblehub_series_url(payload.url)
    access = await diagnose_url(series_url or comix or webnovel or royalroad or scribblehub or payload.url)
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
    if comix and (access["state"] == "REACHABLE" or
                  access["state"] in {"LIKELY_CLOUDFLARE", "INCONCLUSIVE", "TIMEOUT"} and
                  browser_enabled_for(comix)):
        try:
            status, _, body, headers = await _checker_get(comix, purpose="SITE_SCRAPER")
            if 200 <= status < 300 and len(body) < 512_001 and not _challenge(status, body, headers):
                comix_result = parse_comix(body.decode("utf-8", "replace"), comix)
                if comix_result.state == "OK":
                    found = {"title": comix_result.title, "chapter": comix_result.latest.chapter,
                             "cover_url": comix_result.cover_url}
                    if access["state"] != "REACHABLE":
                        access = {"state": "REACHABLE_VIA_BROWSER", "status_code": status,
                                  "final_url": comix}
        except Exception:
            pass
    if webnovel and (access["state"] == "REACHABLE" or
                     access["state"] in {"LIKELY_CLOUDFLARE", "INCONCLUSIVE", "TIMEOUT"} and
                     browser_enabled_for(webnovel)):
        try:
            status, _, body, _, used_browser = await fetch_webnovel(webnovel)
            if status == 200 and len(body) <= MAX_PAGE_BYTES:
                result = parse_webnovel(body.decode("utf-8", "replace"), webnovel)
                if result.state == "OK":
                    found = {"title": result.title, "chapter": result.latest.chapter,
                             "cover_url": result.cover_url}
                    if used_browser:
                        access = {"state": "REACHABLE_VIA_BROWSER", "status_code": 200,
                                  "final_url": webnovel}
        except (httpx.RequestError, UnsafeSource, ValueError, BrowserFetchError):
            pass
    if royalroad and (access["state"] == "REACHABLE" or
                      access["state"] in {"LIKELY_CLOUDFLARE", "INCONCLUSIVE", "TIMEOUT"} and
                      browser_enabled_for(royalroad)):
        try:
            status, _, body, _, used_browser = await fetch_royalroad(royalroad)
            if status == 200 and len(body) <= ROYALROAD_MAX_PAGE_BYTES:
                result = parse_royalroad(body.decode("utf-8", "replace"), royalroad)
                if result.state == "OK":
                    found = {"title": result.title, "chapter": result.latest.chapter,
                             "cover_url": result.cover_url}
                    if used_browser:
                        access = {"state": "REACHABLE_VIA_BROWSER", "status_code": 200,
                                  "final_url": royalroad}
        except (httpx.RequestError, UnsafeSource, ValueError, BrowserFetchError):
            pass
    if scribblehub and (access["state"] == "REACHABLE" or
                        access["state"] in {"LIKELY_CLOUDFLARE", "INCONCLUSIVE", "TIMEOUT"} and
                        browser_enabled_for(scribblehub)):
        try:
            status, _, body, _, used_browser = await fetch_scribblehub(scribblehub)
            if status == 200 and len(body) <= SCRIBBLEHUB_MAX_PAGE_BYTES:
                result = parse_scribblehub(body.decode("utf-8", "replace"), scribblehub)
                if result.state == "OK":
                    found = {"title": result.title, "chapter": result.latest.chapter,
                             "cover_url": result.cover_url}
                    if used_browser:
                        access = {"state": "REACHABLE_VIA_BROWSER", "status_code": 200,
                                  "final_url": scribblehub}
        except (httpx.RequestError, UnsafeSource, ValueError, BrowserFetchError):
            pass
    parts = urlsplit(payload.url)
    if (not series_url and not comix and not webnovel and not royalroad and not scribblehub and
            parts.path.rstrip("/").rsplit("/", 1)[-1].lower() in {"list", "chapters", "toc", "chapter-list"} and
            access["state"] == "REACHABLE"):
        try:
            toc = await extract_toc(payload.url)
            if toc.state == "OK" and toc.latest:
                found["chapter"] = toc.latest.chapter
        except (httpx.RequestError, UnsafeSource, ValueError):
            pass
    return {"access": access, "title": found.get("title"),
            "current_chapter": None if webnovel or royalroad or scribblehub else detection.current_chapter,
            "latest_chapter": found.get("chapter"),
            "cover_url": found.get("cover_url"),
            "checker": "FREEWEBNOVEL" if series_url else ("SCRIBBLEHUB" if scribblehub else "ROYALROAD" if royalroad else "WEBNOVEL" if webnovel else "COMIX" if comix else
                       ("TOC_SCRAPER" if not detection.url_template else "INCREMENTAL_PROBE")),
            "url_template": None if webnovel or royalroad or scribblehub else freewebnovel_template(series_url) or detection.url_template}
