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

    current, latest = _run_incremental_probe(
        start_url,
        latest_available=398,
        manual_regex=r"episode_no=(\d+)",
    )

    assert int(current) == 393
    assert latest is not None
    assert int(latest) == 398
    assert int(latest) > int(current)


def test_manhwaread_sequential_probe_finds_newer_chapter() -> None:
    start_url = "https://manhwaread.com/manhwa/the-mating-of-elves/chapter-60/"

    current, latest = _run_incremental_probe(start_url, latest_available=63)

    assert int(current) == 60
    assert latest is not None
    assert int(latest) == 63
    assert int(latest) > int(current)
