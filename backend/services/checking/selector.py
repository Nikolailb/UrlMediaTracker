"""Select site, ToC, or URL strategy and return typed outcomes (REQ-005)."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import httpx
from services.checking.http import UnsafeSource, safe_get, _challenge

# Public aliases retained for API and existing imports.
from services.checking.sites.freewebnovel import (
    series_url as freewebnovel_series_url,
    chapter_template as freewebnovel_template,
    parse_freewebnovel,
)
from services.checking.strategies.toc import parse_toc


@dataclass
class CheckResult:
    outcome: str
    method: str
    chapter: str | None = None
    chapter_url: str | None = None
    detail: str | None = None


async def _checker_get(url: str, *, purpose: str):
    """Retry a challenged or unreachable site/ToC through an opted-in browser."""
    from services.checking.browser import browser_get, BrowserFetchError
    try:
        status, final_url, body, headers = await safe_get(url)
    except (httpx.ConnectError, httpx.TimeoutException) as direct_error:
        try:
            return await browser_get(url, purpose=purpose)
        except BrowserFetchError:
            raise direct_error from None
    if _challenge(status, body, headers):
        try:
            return await browser_get(url, purpose=purpose)
        except BrowserFetchError:
            return status, final_url, body, headers
    return status, final_url, body, headers


async def check_source(item, config) -> CheckResult:
    """Select a checker; only unsupported ToC methods can fall through to probing."""
    from services.checking.strategies.probe import IncrementalProbeStrategy, ProbeBlocked, ProbeFailed

    series = freewebnovel_series_url(item.series_url or item.original_url)
    override = item.strategy_override
    if series and override in {None, "FREEWEBNOVEL"}:
        try:
            status, _, body, headers = await _checker_get(series, purpose="SITE_SCRAPER")
            if _challenge(status, body, headers):
                return CheckResult("BLOCKED", "FREEWEBNOVEL", detail="Likely browser challenge")
            if status >= 400:
                return CheckResult("FAILED", "FREEWEBNOVEL", detail=f"HTTP {status}")
            found = parse_freewebnovel(body.decode("utf-8", "replace"), series)
            if not found["chapter"]:
                return CheckResult("FAILED", "FREEWEBNOVEL", detail="No consistent latest-chapter signals on series page")
            try:
                newer = Decimal(found["chapter"]) > Decimal(item.latest_chapter or item.current_chapter or "0")
            except InvalidOperation:
                newer = found["chapter"] != item.latest_chapter
            return CheckResult("NEW" if newer else "UNCHANGED", "FREEWEBNOVEL",
                               found["chapter"], found["chapter_url"])
        except (httpx.RequestError, UnsafeSource, ValueError) as exc:
            return CheckResult("FAILED", "FREEWEBNOVEL", detail=str(exc)[:200])

    method = override or item.check_strategy
    if method in {"TOC_SCRAPER", "TOC_THEN_PROBE"}:
        if not item.toc_url or not item.url_template:
            result = CheckResult("UNSUPPORTED", "TOC_SCRAPER", detail="ToC or chapter template missing")
        else:
            try:
                status, _, body, headers = await _checker_get(item.toc_url, purpose="TOC_SCRAPER")
                if _challenge(status, body, headers):
                    return CheckResult("BLOCKED", "TOC_SCRAPER", detail="Likely browser challenge")
                if status >= 400:
                    return CheckResult("FAILED", "TOC_SCRAPER", detail=f"HTTP {status}")
                found = parse_toc(body.decode("utf-8", "replace"), item.toc_url, item.url_template)
                if not found:
                    result = CheckResult("FAILED", "TOC_SCRAPER", detail="No matching chapter links")
                else:
                    chapter, chapter_url = found
                    try:
                        newer = Decimal(chapter) > Decimal(item.latest_chapter or item.current_chapter or "0")
                    except InvalidOperation:
                        newer = chapter != (item.latest_chapter or item.current_chapter)
                    return CheckResult("NEW" if newer else "UNCHANGED", "TOC_SCRAPER", chapter, chapter_url)
            except (httpx.RequestError, UnsafeSource, ValueError) as exc:
                return CheckResult("FAILED", "TOC_SCRAPER", detail=str(exc)[:200])
        if method == "TOC_SCRAPER" or result.outcome != "UNSUPPORTED":
            return result

    if not item.url_template:
        return CheckResult("UNSUPPORTED", "INCREMENTAL_PROBE", detail="No chapter URL template")
    try:
        int(float(item.latest_chapter or item.current_chapter or "0"))
    except (ValueError, TypeError):
        return CheckResult("UNSUPPORTED", "INCREMENTAL_PROBE", detail="Chapter label cannot be probed numerically")
    try:
        chapter = await IncrementalProbeStrategy().find_latest_chapter(
            item.latest_chapter or item.current_chapter or "0", item.url_template, config)
        return CheckResult("NEW" if chapter else "UNCHANGED", "INCREMENTAL_PROBE", chapter,
                           item.url_template.replace("{n}", chapter) if chapter else None)
    except ProbeBlocked as exc:
        return CheckResult("BLOCKED", "INCREMENTAL_PROBE", detail=str(exc))
    except (httpx.RequestError, ValueError, ProbeFailed, UnsafeSource) as exc:
        return CheckResult("FAILED", "INCREMENTAL_PROBE", detail=str(exc)[:200])
