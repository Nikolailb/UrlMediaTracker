"""Opt-in browser-backed HTML fetch for approved series/ToC checkers (REQ-005, REQ-015).

Never call this from incremental URL probing or the general site diagnostic.
"""
import asyncio
import json
from urllib.parse import urlsplit

import httpx

from config import settings
from services.checking.http import UnsafeSource, validate_public_url


class BrowserFetchError(Exception):
    pass


_browser_slots = asyncio.Semaphore(1)


def browser_enabled_for(url: str) -> bool:
    """Whether this host was explicitly opted in for site/ToC browser checks."""
    allowed = {host.strip().lower() for host in settings.FLARESOLVERR_ALLOWED_HOSTS.split(",") if host.strip()}
    return bool(settings.FLARESOLVERR_URL and (urlsplit(url).hostname or "").lower() in allowed)


async def browser_get(url: str, *, purpose: str, max_bytes: int = 512_000) -> tuple[int, str, bytes, dict[str, str]]:
    """Fetch one explicitly approved series/ToC URL through FlareSolverr.

    The browser service must also be isolated from private network egress at deployment:
    Chrome can follow intermediate redirects and load subresources before we inspect its result.
    """
    if purpose not in {"SITE_SCRAPER", "TOC_SCRAPER"}:
        raise BrowserFetchError("Browser fetch is limited to site and ToC scrapers.")
    host = (urlsplit(url).hostname or "").lower()
    if not browser_enabled_for(url):
        raise BrowserFetchError("Browser fetch is not enabled for this host.")
    try:
        await validate_public_url(url)
    except UnsafeSource as exc:
        raise BrowserFetchError("Browser target is not public.") from exc
    endpoint = settings.FLARESOLVERR_URL.rstrip("/") + "/v1"
    async with _browser_slots:
        try:
            async with httpx.AsyncClient(timeout=40, trust_env=False) as client:
                async with client.stream("POST", endpoint, json={
                        "cmd": "request.get", "url": url, "maxTimeout": 35_000,
                        "disableMedia": True,
                }) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > max_bytes * 3:
                            raise BrowserFetchError("Browser response exceeded size limit.")
                    result = json.loads(raw)
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise BrowserFetchError("Browser service request failed.") from exc
    if not isinstance(result, dict):
        raise BrowserFetchError("Browser service returned an invalid response.")
    if result.get("status") != "ok" or not isinstance(result.get("solution"), dict):
        raise BrowserFetchError(str(result.get("message") or "Browser service failed.")[:200])
    solution = result["solution"]
    final_url = solution.get("url")
    if not isinstance(final_url, str) or (urlsplit(final_url).hostname or "").lower() != host:
        raise BrowserFetchError("Browser navigation left the approved host.")
    try:
        await validate_public_url(final_url)
    except UnsafeSource as exc:
        raise BrowserFetchError("Browser result is not public.") from exc
    body = solution.get("response")
    if not isinstance(body, str) or len(body.encode("utf-8")) > max_bytes:
        raise BrowserFetchError("Browser response is missing or too large.")
    status = solution.get("status")
    if not isinstance(status, int):
        raise BrowserFetchError("Browser response lacks an HTTP status.")
    return status, final_url, body.encode("utf-8"), solution.get("headers") or {}
