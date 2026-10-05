"""Bounded source diagnostics and typed site/generic chapter checks."""
import asyncio
import ipaddress
import re
import socket
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import httpcore
from httpcore._backends.auto import AutoBackend

from services.pattern_detection import detect_pattern


class UnsafeSource(ValueError):
    pass


async def _public_addresses(host: str, port: int) -> list[str]:
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeSource("Host could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(record[4][0]).is_global for record in addresses):
        raise UnsafeSource("Local, private, or reserved network targets are not allowed.")
    return [record[4][0] for record in addresses]


async def validate_public_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeSource("Invalid source URL.") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise UnsafeSource("Only public HTTP(S) URLs without credentials are allowed.")
    if port and port not in {80, 443}:
        raise UnsafeSource("Only standard web ports are allowed.")
    await _public_addresses(parts.hostname, port or (443 if parts.scheme == "https" else 80))
    return url


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve and pin a validated public IP at the actual TCP connection."""
    def __init__(self):
        self._backend = AutoBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        addresses = await _public_addresses(host, port)
        return await self._backend.connect_tcp(addresses[0], port, timeout=timeout,
                                               local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, *args, **kwargs):
        raise UnsafeSource("Unix sockets are not allowed.")

    async def sleep(self, seconds):
        await self._backend.sleep(seconds)


class PublicHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(), network_backend=PublicNetworkBackend(),
            max_connections=5, max_keepalive_connections=0)


async def safe_get(url: str, *, max_bytes: int = 256_000) -> tuple[int, str, bytes, dict[str, str]]:
    """Fetch a public page with explicit redirect checks and bounded body."""
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False,
                                transport=PublicHTTPTransport(),
                                headers={"User-Agent": "UrlMediaTracker/2.0"}) as client:
        current = url
        for _ in range(5):
            await validate_public_url(current)
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        return response.status_code, current, b"", dict(response.headers)
                    current = urljoin(current, location)
                    continue
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    remaining = max_bytes - len(body)
                    if remaining <= 0:
                        break
                    body.extend(chunk[:remaining])
                return response.status_code, str(response.url), bytes(body), dict(response.headers)
    raise UnsafeSource("Too many redirects.")


def _challenge(status_code: int, body: bytes, headers: dict[str, str]) -> bool:
    lower = body[:32_768].lower()
    return (b"cf-chl" in lower or b"challenge-platform" in lower or
            b"checking your browser" in lower or
            (status_code in {403, 503} and "cf-ray" in headers))


async def diagnose_url(url: str) -> dict:
    try:
        status_code, final_url, body, headers = await safe_get(url, max_bytes=65_536)
        if _challenge(status_code, body, headers):
            state = "LIKELY_CLOUDFLARE"
        elif 200 <= status_code < 300:
            state = "REACHABLE"
        elif status_code >= 400:
            state = "HTTP_ERROR"
        else:
            state = "INCONCLUSIVE"
        return {"state": state, "status_code": status_code, "final_url": final_url}
    except (httpx.TimeoutException, asyncio.TimeoutError):
        return {"state": "TIMEOUT", "status_code": None, "final_url": None}
    except UnsafeSource as exc:
        return {"state": "REJECTED", "status_code": None, "final_url": None,
                "detail": str(exc)[:200]}
    except httpx.RequestError as exc:
        return {"state": "INCONCLUSIVE", "status_code": None, "final_url": None,
                "detail": str(exc)[:200]}


def freewebnovel_series_url(url: str) -> str | None:
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in {"freewebnovel.com", "www.freewebnovel.com"}:
        return None
    match = re.fullmatch(r"/novel/([^/]+)(?:/chapter-[0-9]+)?/?", parts.path, re.I)
    if not match:
        return None
    return urlunsplit(("https", "freewebnovel.com", f"/novel/{match.group(1)}", "", ""))


def freewebnovel_template(series_url: str | None) -> str | None:
    return f"{series_url}/chapter-{{n}}" if series_url else None


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._link_text: list[str] = []
        self.title = ""
        self._in_h1 = False
        self.cover: str | None = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "a":
            self._href = data.get("href")
            self._link_text = []
        if tag == "h1":
            self._in_h1 = True
        if tag == "meta" and data.get("property") == "og:image":
            self.cover = data.get("content")

    def handle_data(self, data):
        if self._href:
            self._link_text.append(data)
        if self._in_h1:
            self.title += data.strip()

    def handle_endtag(self, tag):
        if tag == "a":
            if self._href:
                self.links.append((self._href, "".join(self._link_text).strip()))
            self._href = None
        if tag == "h1":
            self._in_h1 = False


def parse_freewebnovel(html: str, series_url: str) -> dict:
    parser = _PageParser()
    parser.feed(html)
    prefix = series_url.rstrip("/") + "/chapter-"
    candidates: list[tuple[int, str]] = []
    for href, label in parser.links:
        absolute = urljoin(series_url, href).split("?", 1)[0].split("#", 1)[0]
        match = re.fullmatch(re.escape(prefix) + r"([0-9]+)/?", absolute, re.I)
        if match:
            number = int(match.group(1))
            # The label must actually describe a chapter, not a related story.
            label_match = re.search(r"\bchapter\s+(\d+)\b", label, re.I)
            if label_match and int(label_match.group(1)) == number:
                candidates.append((number, absolute))
    latest = max(candidates, default=None)
    return {"title": parser.title or None, "cover_url": urljoin(series_url, parser.cover) if parser.cover else None,
            "chapter": str(latest[0]) if latest else None,
            "chapter_url": latest[1] if latest else None}


@dataclass
class CheckResult:
    outcome: str
    method: str
    chapter: str | None = None
    chapter_url: str | None = None
    detail: str | None = None


async def check_source(item, config) -> CheckResult:
    """Select a checker; only unsupported methods may fall through."""
    from services.chapter_checker import IncrementalProbeStrategy, ProbeBlocked, ProbeFailed

    series_url = freewebnovel_series_url(item.series_url or item.original_url)
    override = item.strategy_override
    if series_url and override in {None, "FREEWEBNOVEL"}:
        try:
            status, _, body, headers = await safe_get(series_url)
            if _challenge(status, body, headers):
                return CheckResult("BLOCKED", "FREEWEBNOVEL", detail="Likely browser challenge")
            if status >= 400:
                return CheckResult("FAILED", "FREEWEBNOVEL", detail=f"HTTP {status}")
            found = parse_freewebnovel(body.decode("utf-8", "replace"), series_url)
            if not found["chapter"]:
                return CheckResult("FAILED", "FREEWEBNOVEL", detail="No series chapter links found")
            try:
                newer = float(found["chapter"]) > float(item.latest_chapter or item.current_chapter or 0)
            except ValueError:
                newer = found["chapter"] != item.latest_chapter
            return CheckResult("NEW" if newer else "UNCHANGED", "FREEWEBNOVEL",
                               found["chapter"], found["chapter_url"])
        except (httpx.RequestError, UnsafeSource) as exc:
            return CheckResult("FAILED", "FREEWEBNOVEL", detail=str(exc)[:200])

    method = override or item.check_strategy
    if method in {"TOC_SCRAPER", "TOC_THEN_PROBE"}:
        if not item.toc_url or not item.url_template:
            result = CheckResult("UNSUPPORTED", "TOC_SCRAPER", detail="ToC or chapter template missing")
        else:
            try:
                status, _, body, headers = await safe_get(item.toc_url)
                if _challenge(status, body, headers):
                    return CheckResult("BLOCKED", "TOC_SCRAPER")
                if status >= 400:
                    return CheckResult("FAILED", "TOC_SCRAPER", detail=f"HTTP {status}")
                prefix, suffix = item.url_template.split("{n}", 1)
                pattern = re.compile(re.escape(prefix) + r"(\d+(?:\.\d+)?[a-z]?)" + re.escape(suffix), re.I)
                links = re.findall(r'href=["\']([^"\']+)', body.decode("utf-8", "replace"), re.I)
                chapters = [(m.group(1), urljoin(item.toc_url, href)) for href in links
                            if (m := pattern.fullmatch(urljoin(item.toc_url, href)))]
                if not chapters:
                    result = CheckResult("FAILED", "TOC_SCRAPER", detail="No matching chapter links")
                else:
                    chapter, chapter_url = max(chapters, key=lambda pair: (
                        Decimal(re.match(r"\d+(?:\.\d+)?", pair[0]).group()), pair[0].lower()))
                    try:
                        newer = Decimal(chapter) > Decimal(item.latest_chapter or item.current_chapter or "0")
                    except InvalidOperation:
                        newer = chapter != (item.latest_chapter or item.current_chapter)
                    return CheckResult("NEW" if newer else "UNCHANGED", "TOC_SCRAPER",
                                       chapter, chapter_url)
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
