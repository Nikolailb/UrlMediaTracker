import asyncio
import re

from services import chapter_checker
from services.chapter_checker import CheckerConfig, IncrementalProbeStrategy
from services.pattern_detection import detect_pattern


async def _no_sleep(_: float) -> None:
    return None


def _extract_chapter_number(url: str) -> int | None:
    query_match = re.search(r"[?&]episode_no=(\d+)", url)
    if query_match:
        return int(query_match.group(1))

    path_match = re.search(r"chapter-(\d+)", url)
    if path_match:
        return int(path_match.group(1))

    return None


def _fake_probe_factory(latest_available: int):
    async def _fake_probe(_client, url: str, _config: CheckerConfig) -> bool:
        n = _extract_chapter_number(url)
        if n is None:
            return False
        return n <= latest_available

    return _fake_probe


class _FakeHistoryResponse:
    def __init__(self, url: str, status_code: int = 301) -> None:
        self.url = url
        self.status_code = status_code


class _FakeStreamResponse:
    def __init__(
        self,
        status_code: int,
        url: str,
        text: str = "",
        history: list[_FakeHistoryResponse] | None = None,
    ) -> None:
        self.status_code = status_code
        self.url = url
        self.history = history or []
        self._body = text.encode("utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def aiter_bytes(self, chunk_size: int = 4096):
        if self._body:
            yield self._body[:chunk_size]


class _FakeAsyncClient:
    def __init__(self, response_factory) -> None:
        self._response_factory = response_factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def stream(self, method: str, url: str):
        assert method == "GET"
        return self._response_factory(url)


def _run_incremental_probe(
    url: str, latest_available: int, manual_regex: str | None = None
) -> tuple[str, str | None]:
    detection = detect_pattern(url, manual_regex)
    assert detection.url_template is not None
    assert detection.current_chapter is not None

    strategy = IncrementalProbeStrategy()
    config = CheckerConfig(
        timeout=1.0,
        delay_seconds=0.0,
        coarse_step=5,
        max_coarse_steps=20,
        max_probe_duration_seconds=5.0,
    )

    original_probe = chapter_checker._probe
    original_sleep = chapter_checker.asyncio.sleep
    chapter_checker._probe = _fake_probe_factory(latest_available)
    chapter_checker.asyncio.sleep = _no_sleep
    try:
        latest = asyncio.run(
            strategy.find_latest_chapter(
                current_latest=detection.current_chapter,
                url_template=detection.url_template,
                config=config,
            )
        )
    finally:
        chapter_checker._probe = original_probe
        chapter_checker.asyncio.sleep = original_sleep

    return detection.current_chapter, latest


def _run_incremental_probe_with_fake_client(
    url: str, response_factory, manual_regex: str | None = None
) -> tuple[str, str | None]:
    detection = detect_pattern(url, manual_regex)
    assert detection.url_template is not None
    assert detection.current_chapter is not None

    strategy = IncrementalProbeStrategy()
    config = CheckerConfig(
        timeout=1.0,
        delay_seconds=0.0,
        coarse_step=5,
        max_coarse_steps=20,
        max_probe_duration_seconds=5.0,
    )

    original_client = chapter_checker.httpx.AsyncClient
    original_sleep = chapter_checker.asyncio.sleep
    chapter_checker.httpx.AsyncClient = lambda *args, **kwargs: _FakeAsyncClient(
        response_factory
    )
    chapter_checker.asyncio.sleep = _no_sleep
    try:
        latest = asyncio.run(
            strategy.find_latest_chapter(
                current_latest=detection.current_chapter,
                url_template=detection.url_template,
                config=config,
            )
        )
    finally:
        chapter_checker.httpx.AsyncClient = original_client
        chapter_checker.asyncio.sleep = original_sleep

    return detection.current_chapter, latest


def _webtoons_response_factory(latest_available: int):
    def _factory(url: str) -> _FakeStreamResponse:
        chapter_number = _extract_chapter_number(url)
        if chapter_number is None or chapter_number > latest_available:
            return _FakeStreamResponse(status_code=404, url=url)

        final_url = (
            "https://www.webtoons.com/en/super-hero/unordinary/"
            f"episode-{chapter_number}/viewer?title_no=679&episode_no={chapter_number}"
        )
        history = (
            [] if final_url == url else [_FakeHistoryResponse(url, status_code=302)]
        )
        return _FakeStreamResponse(
            status_code=200,
            url=final_url,
            text="<html>episode page</html>",
            history=history,
        )

    return _factory


def _manhwaread_response_factory(latest_available: int):
    def _factory(url: str) -> _FakeStreamResponse:
        chapter_number = _extract_chapter_number(url)
        if chapter_number is None:
            return _FakeStreamResponse(status_code=404, url=url)

        if chapter_number <= latest_available:
            return _FakeStreamResponse(
                status_code=200,
                url=url,
                text="<html>chapter page</html>",
            )

        return _FakeStreamResponse(
            status_code=200,
            url="https://manhwaread.com/manhwa/the-mating-of-elves/",
            text="<html>series table of contents</html>",
            history=[_FakeHistoryResponse(url, status_code=301)],
        )

    return _factory


def test_freewebnovel_sequential_probe_finds_newer_chapter() -> None:
    start_url = (
        "https://freewebnovel.com/novel/harem-system-in-a-fantasy-world/chapter-235"
    )

    current, latest = _run_incremental_probe(start_url, latest_available=240)

    assert int(current) == 235
    assert latest is not None
    assert int(latest) == 240
    assert int(latest) > int(current)


def test_webtoons_sequential_probe_with_custom_regex_episode_no() -> None:
    start_url = (
        "https://www.webtoons.com/en/super-hero/unordinary/"
        "episode-374/viewer?title_no=679&episode_no=393"
    )

    current, latest = _run_incremental_probe_with_fake_client(
        start_url,
        response_factory=_webtoons_response_factory(latest_available=398),
        manual_regex=r"episode_no=(\d+)",
    )

    assert int(current) == 393
    assert latest is not None
    assert int(latest) == 398
    assert int(latest) > int(current)


def test_manhwaread_sequential_probe_finds_newer_chapter() -> None:
    start_url = "https://manhwaread.com/manhwa/the-mating-of-elves/chapter-60/"

    current, latest = _run_incremental_probe_with_fake_client(
        start_url,
        response_factory=_manhwaread_response_factory(latest_available=63),
    )

    assert int(current) == 60
    assert latest is not None
    assert int(latest) == 63
    assert int(latest) > int(current)
