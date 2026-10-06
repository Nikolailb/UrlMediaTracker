"""Incremental chapter URL probing (REQ-005). Never uses browser fetching."""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit, urlunsplit
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from services.pattern_detection import build_chapter_url
from services.checking.http import PublicHTTPTransport, _challenge
logger = logging.getLogger(__name__)

class ProbeBlocked(Exception):
    """A source presented a browser challenge during a chapter probe."""


class ProbeFailed(Exception):
    """A chapter probe could not establish a trustworthy unchanged result."""


def _normalise_probe_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def _redirect_kept_same_target(requested_url: str, final_url: str) -> bool:
    return _normalise_probe_url(requested_url) == _normalise_probe_url(final_url)


def _redirect_kept_query_identity(requested_url: str, final_url: str) -> bool:
    """Return True when redirect only canonicalizes the chapter URL.

    Accept redirects that preserve scheme, host, query parameters, and path
    depth. Reject redirects that bounce back to a parent series/ToC page,
    which often happens for unreleased chapters.
    """
    req = urlsplit(requested_url)
    fin = urlsplit(final_url)

    if (
        req.scheme.lower() != fin.scheme.lower()
        or req.netloc.lower() != fin.netloc.lower()
    ):
        return False

    req_query = sorted(parse_qsl(req.query, keep_blank_values=True))
    fin_query = sorted(parse_qsl(fin.query, keep_blank_values=True))
    if req_query != fin_query:
        return False

    req_segments = [segment for segment in req.path.split("/") if segment]
    fin_segments = [segment for segment in fin.path.split("/") if segment]
    return len(req_segments) == len(fin_segments)


@dataclass
class CheckerConfig:
    timeout: float = 10.0
    delay_seconds: float = 0.5
    coarse_step: int = 5
    max_coarse_steps: int = 100
    # Hard wall-clock cap on a single find_latest_chapter call (seconds).
    max_probe_duration_seconds: float = 60.0
    # Optional ToC URL carried by the shared checker configuration.
    toc_url: str | None = None
    # Phrases that indicate a soft 404.
    content_error_phrases: tuple[str, ...] = field(
        default_factory=lambda: (
            "chapter not available",
            "chapter missing",
            "chapter content is missing",
            "content is missing or does not exist",
            "chapter does not exist",
            "chapter not found",
            "page not found",
            "content not found",
            "no chapter found",
            "chapter unavailable",
            "moved permanently",
            "404 not found",
        )
    )
    probe_byte_limit: int = 32_768


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------


class BaseCheckStrategy(ABC):
    """
    Interface for chapter-detection strategies.

    Implement ``find_latest_chapter`` to probe a site in whatever way is
    most appropriate. Return the highest chapter identifier found (as a
    string), or ``None`` if nothing new was discovered.
    """

    @abstractmethod
    async def find_latest_chapter(
        self,
        current_latest: str,
        url_template: str,
        config: CheckerConfig,
    ) -> str | None: ...


# ---------------------------------------------------------------------------
# Content-aware probe helper
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception_type(httpx.RequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _probe(
    client: httpx.AsyncClient,
    url: str,
    config: CheckerConfig,
) -> bool:
    """
    Return ``True`` if *url* both responds with a success status code
    **and** appears to contain real chapter content.

    Uses a streaming GET so only the first ``config.probe_byte_limit``
    bytes are downloaded — enough to catch error banners in the page
    header without fetching the full HTML.

    Raises ``httpx.RequestError`` on network failures so callers can
    handle retries/logging uniformly.
    """
    async with client.stream("GET", url) as resp:
        if resp.status_code in {403, 503}:
            challenge_body = bytearray()
            async for chunk in resp.aiter_bytes():
                challenge_body.extend(chunk[:max(0, 32768 - len(challenge_body))])
                if len(challenge_body) >= 32768:
                    break
            if _challenge(resp.status_code, bytes(challenge_body), dict(getattr(resp, "headers", {}))):
                raise ProbeBlocked("Likely browser challenge")
            raise ProbeFailed(f"HTTP {resp.status_code} during probe")
        if resp.status_code >= 400:
            return False
        if resp.status_code >= 300:
            raise ProbeFailed(f"HTTP {resp.status_code} during probe")
        final_url = str(resp.url)
        if resp.history and not _redirect_kept_same_target(url, final_url):
            if not _redirect_kept_query_identity(url, final_url):
                logger.debug(
                    "Probe redirected away from chapter URL: %s -> %s", url, final_url
                )
                return False
            logger.debug(
                "Probe redirected to canonical chapter URL (query preserved): %s -> %s",
                url,
                final_url,
            )
        raw = b""
        async for chunk in resp.aiter_bytes(chunk_size=4_096):
            raw += chunk
            if len(raw) >= config.probe_byte_limit:
                break
    text = raw.decode("utf-8", errors="replace").lower()
    if _challenge(resp.status_code, bytes(raw), dict(getattr(resp, "headers", {}))):
        raise ProbeBlocked("Likely browser challenge")
    return not any(phrase in text for phrase in config.content_error_phrases)


# ---------------------------------------------------------------------------
# Built-in strategy: incremental HTTP probing
# ---------------------------------------------------------------------------


class IncrementalProbeStrategy(BaseCheckStrategy):
    """
    Two-phase content-aware probe to find the latest available chapter.

    Phase 1 — coarse: probe N + STEP, N + 2*STEP, … until the first miss.
    This skips large gaps quickly (e.g. 100 new chapters in ~20 requests
    with the default step of 5).

    Phase 2 — fine: probe every integer in the window between the last
    coarse hit and the coarse miss to find the exact last chapter.

    Each probe is a streaming GET request. Only the first
    ``config.probe_byte_limit`` bytes are read, so large HTML pages are
    not downloaded in full. After receiving a 200, the response body is
    scanned for ``config.content_error_phrases`` to catch sites that
    return HTTP 200 for missing chapters (soft 404s).

    ``config.max_coarse_steps`` is a safety cap so a site that returns
    200 for everything cannot loop forever.
    """

    async def find_latest_chapter(
        self,
        current_latest: str,
        url_template: str,
        config: CheckerConfig,
    ) -> str | None:
        try:
            base_num = int(float(current_latest))
        except (ValueError, TypeError):
            logger.warning(
                "Cannot parse chapter number %r for incremental probe.", current_latest
            )
            return None

        step = max(1, config.coarse_step)
        found_latest: str | None = None

        async with httpx.AsyncClient(
            timeout=config.timeout,
            follow_redirects=True,
            transport=PublicHTTPTransport(),
            trust_env=False,
            headers={"User-Agent": "ChapterTracker/1.0 (chapter availability check)"},
        ) as client:

            # ------------------------------------------------------------------
            # Phase 1: coarse stepping — find the window [coarse_low, coarse_miss)
            # that contains the last available chapter.
            # ------------------------------------------------------------------
            coarse_low = base_num  # last confirmed-good chapter number
            coarse_miss = base_num + step  # first unconfirmed candidate

            for _ in range(config.max_coarse_steps):
                probe_url = build_chapter_url(url_template, str(coarse_miss))
                try:
                    exists = await _probe(client, probe_url, config)
                    if exists:
                        found_latest = str(coarse_miss)
                        coarse_low = coarse_miss
                        coarse_miss += step
                        logger.debug("Coarse hit: chapter %s exists.", coarse_low)
                        await asyncio.sleep(config.delay_seconds)
                    else:
                        logger.debug("Coarse miss: chapter %s.", coarse_miss)
                        break
                except httpx.RequestError as exc:
                    logger.warning("Network error probing %s: %s", probe_url, exc)
                    raise ProbeFailed("Network error during probe") from exc

            # ------------------------------------------------------------------
            # Phase 2: fine stepping within (coarse_low, coarse_miss) — only
            # needed when the coarse step is > 1.
            # ------------------------------------------------------------------
            if step > 1:
                for num in range(coarse_low + 1, coarse_miss):
                    probe_url = build_chapter_url(url_template, str(num))
                    try:
                        exists = await _probe(client, probe_url, config)
                        if exists:
                            found_latest = str(num)
                            logger.debug("Fine hit: chapter %s exists.", num)
                            await asyncio.sleep(config.delay_seconds)
                        else:
                            logger.debug("Fine miss: chapter %s, done.", num)
                            break
                    except httpx.RequestError as exc:
                        logger.warning("Network error probing %s: %s", probe_url, exc)
                        raise ProbeFailed("Network error during probe") from exc

        return found_latest


# ---------------------------------------------------------------------------
# Strategy registry — add new strategies here
# ---------------------------------------------------------------------------
