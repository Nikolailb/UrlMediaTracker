"""Select site, ToC, or URL strategy and return typed outcomes (REQ-005)."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import httpx
from urllib.parse import parse_qs, urlsplit
from services.checking.http import UnsafeSource, safe_get, _challenge

# Public aliases retained for API and existing imports.
from services.checking.sites.freewebnovel import (
    series_url as freewebnovel_series_url,
    chapter_template as freewebnovel_template,
    parse_freewebnovel,
)
from services.checking.strategies.toc import parse_toc, _rank, query_identity_conflicts
from services.checking.strategies.toc import parse_toc_examples
from services.checking.sites.comix import series_url as comix_series_url, parse_comix, merge_rendered_group
from services.checking.browser import browser_enabled_for, browser_get, BrowserFetchError
from services.checking.results import Extraction


@dataclass
class CheckResult:
    outcome: str
    method: str
    chapter: str | None = None
    chapter_url: str | None = None
    detail: str | None = None
    first_url: str | None = None
    confidence: str | None = None
    groups: list[str] | None = None
    toc_latest_page_url: str | None = None


async def _checker_get(url: str, *, purpose: str, max_bytes: int = 512_001):
    """Retry a challenged or unreachable site/ToC through an opted-in browser."""
    from services.checking.browser import browser_get, BrowserFetchError
    try:
        status, final_url, body, headers = await safe_get(url, max_bytes=max_bytes)
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


def _compare(found: str, previous: str | None) -> bool:
    try:
        return Decimal(found) > Decimal(previous or "0")
    except InvalidOperation:
        return found != previous


def _from_extraction(found: Extraction, previous: str | None) -> CheckResult:
    if found.state != "OK" or not found.latest:
        return CheckResult("FAILED", found.method,
                           detail=f"{found.state}: " + ("; ".join(found.warnings) or "No trustworthy chapter result."))
    try:
        if previous is not None and Decimal(found.latest.chapter) < Decimal(previous):
            return CheckResult("FAILED", found.method, detail="Source reported an older latest chapter.")
    except InvalidOperation:
        pass
    return CheckResult("NEW" if _compare(found.latest.chapter, previous) else "UNCHANGED",
                       found.method, found.latest.chapter, found.latest.url,
                       "; ".join(found.warnings) or None, found.first_url,
                       found.confidence, found.groups, found.checked_page_url)


async def extract_toc(url: str, *, examples: list[str] | None = None,
                      row_class: str | None = None, preferred_group: str | None = None,
                      confirmed_latest_page_url: str | None = None,
                      chapter_regex: str | None = None) -> Extraction:
    """Fetch and parse at most the first and explicit last HTML page."""
    if confirmed_latest_page_url:
        source = urlsplit(url)
        confirmed = urlsplit(confirmed_latest_page_url)
        if (confirmed.scheme != source.scheme or confirmed.hostname != source.hostname or
                confirmed.path.rstrip("/") != source.path.rstrip("/") or
                query_identity_conflicts(source.query, confirmed.query) or
                (confirmed_latest_page_url != url and not parse_qs(confirmed.query).get("page"))):
            return Extraction("CONTRADICTORY", "TOC_SCRAPER", warnings=["Saved ToC page does not match the source."])
    status, final_url, body, headers = await _checker_get(confirmed_latest_page_url or url, purpose="TOC_SCRAPER")
    if _challenge(status, body, headers):
        return Extraction("BLOCKED", "TOC_SCRAPER", warnings=["Likely browser challenge."])
    if status >= 400:
        return Extraction("HTTP_ERROR", "TOC_SCRAPER", warnings=[f"HTTP {status}."])
    if len(body) >= 512_001:
        return Extraction("TRUNCATED", "TOC_SCRAPER", warnings=["ToC exceeded the 512 KiB limit."])
    first = parse_toc(body.decode("utf-8", "replace"), final_url, examples=examples,
                      row_class=row_class, preferred_group=preferred_group,
                      chapter_regex=chapter_regex)
    if first.state != "OK":
        return first
    first.checked_page_url = final_url
    if not first.last_page_url:
        return first
    if confirmed_latest_page_url:
        if confirmed_latest_page_url == url:
            return first
        try:
            current_page = int(parse_qs(urlsplit(final_url).query).get("page", ["1"])[0])
            next_page = int(parse_qs(urlsplit(first.last_page_url).query).get("page", ["1"])[0])
        except ValueError:
            return Extraction("CONTRADICTORY", "TOC_SCRAPER", warnings=["Invalid pagination link."])
        if next_page <= current_page:
            return first
    else:
        if len(first.links) < 2:
            return first
        numbers = [_rank(link.chapter) for link in first.links]
        if numbers[0] >= numbers[-1]:
            return first
    status, final_url, body, headers = await _checker_get(first.last_page_url, purpose="TOC_SCRAPER")
    if _challenge(status, body, headers):
        return Extraction("BLOCKED", "TOC_SCRAPER", warnings=["Last ToC page is blocked."])
    if status >= 400 or len(body) >= 512_001:
        return Extraction("TRUNCATED" if len(body) >= 512_001 else "HTTP_ERROR", "TOC_SCRAPER",
                          warnings=["Last ToC page could not be read."])
    last = parse_toc(body.decode("utf-8", "replace"), final_url, examples=examples,
                     row_class=row_class, preferred_group=preferred_group,
                     chapter_regex=chapter_regex)
    if last.state != "OK" or not last.latest or not first.latest:
        return Extraction("CHANGED_LAYOUT", "TOC_SCRAPER", warnings=["Last ToC page did not contain matching chapters."])
    if _rank(last.latest.chapter) < _rank(first.latest.chapter):
        return Extraction("CONTRADICTORY", "TOC_SCRAPER", warnings=["Pagination order is inconsistent."])
    last.checked_page_url = final_url
    return last


async def check_source(item, config) -> CheckResult:
    """Select a checker; only unsupported ToC methods can fall through to probing."""
    from services.checking.strategies.probe import IncrementalProbeStrategy, ProbeBlocked, ProbeFailed

    series = freewebnovel_series_url(item.series_url or item.original_url)
    comix = comix_series_url(item.series_url or item.original_url)
    override = item.strategy_override
    if override == "COMIX" and not comix:
        return CheckResult("UNSUPPORTED", "COMIX", detail="Comix checker requires a Comix series URL")
    if override == "FREEWEBNOVEL" and not series:
        return CheckResult("UNSUPPORTED", "FREEWEBNOVEL", detail="FreeWebNovel checker requires a FreeWebNovel series URL")
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

    if comix and override in {None, "COMIX"}:
        try:
            status, _, body, headers = await _checker_get(comix, purpose="SITE_SCRAPER")
            if _challenge(status, body, headers):
                return CheckResult("BLOCKED", "COMIX", detail="Likely browser challenge")
            if status >= 400 or len(body) >= 512_001:
                return CheckResult("FAILED", "COMIX", detail=f"HTTP {status} or truncated page")
            found = parse_comix(body.decode("utf-8", "replace"), comix)
            preferred_group = getattr(item, "preferred_group", None)
            if found.state == "OK" and preferred_group and browser_enabled_for(comix):
                try:
                    _, _, rendered, _ = await browser_get(comix, purpose="SITE_SCRAPER", wait_seconds=2)
                    merge_rendered_group(found, rendered.decode("utf-8", "replace"),
                                         comix, preferred_group)
                except BrowserFetchError:
                    found.warnings.append("Preferred group could not be checked; using the series link.")
            elif found.state == "OK" and preferred_group:
                found.warnings.append("Browser group lookup is not enabled; using the series link.")
            return _from_extraction(found, item.latest_chapter or item.current_chapter)
        except (httpx.RequestError, UnsafeSource, ValueError) as exc:
            return CheckResult("FAILED", "COMIX", detail=str(exc)[:200])

    method = override or item.check_strategy
    if method in {"TOC_SCRAPER", "TOC_THEN_PROBE"}:
        if not item.toc_url:
            result = CheckResult("UNSUPPORTED", "TOC_SCRAPER", detail="ToC URL missing")
        else:
            try:
                found = await extract_toc(item.toc_url, examples=parse_toc_examples(getattr(item, "toc_examples_json", None)),
                                          row_class=getattr(item, "toc_row_class", None),
                                          preferred_group=getattr(item, "preferred_group", None),
                                          confirmed_latest_page_url=getattr(item, "toc_latest_page_url", None),
                                          chapter_regex=(getattr(item, "chapter_regex", None)
                                                         if getattr(item, "pattern_source", None) == "MANUAL" else None))
                if found.state == "BLOCKED":
                    return CheckResult("BLOCKED", "TOC_SCRAPER", detail="; ".join(found.warnings))
                return _from_extraction(found, item.latest_chapter or item.current_chapter)
            except (httpx.RequestError, UnsafeSource, ValueError) as exc:
                return CheckResult("FAILED", "TOC_SCRAPER", detail=str(exc)[:200])
        if method == "TOC_SCRAPER" or result.outcome != "UNSUPPORTED":
            return result

    from services.pattern_detection import unsafe_chapter_template
    if unsafe_chapter_template(item.url_template):
        return CheckResult("UNSUPPORTED", "INCREMENTAL_PROBE",
                           detail="The URL has separate path and query chapter values; use ToC links instead of URL probing")
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
