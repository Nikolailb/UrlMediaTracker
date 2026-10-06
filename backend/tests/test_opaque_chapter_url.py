"""REQ-004/REQ-005: a changing-looking chapter ID must not become a probe template."""

from services.pattern_detection import detect_pattern


COMIX_CHAPTER = "https://comix.to/title/39w1n-the-mating-of-elves/8904631-chapter-63"


def test_comix_example_is_not_a_sequential_probe_template():
    detected = detect_pattern(COMIX_CHAPTER)
    assert detected.current_chapter == "63"
    assert detected.url_template is None
    assert detected.strategy_used == "opaque_id"
    assert detected.chapter_regex is not None

    manual = detect_pattern(COMIX_CHAPTER, r"chapter-(\d+)")
    assert manual.current_chapter == "63"
    assert manual.url_template is None
    assert manual.strategy_used == "opaque_id"


def test_stable_chapter_example_still_builds_probe_template():
    detected = detect_pattern("https://example.com/series/chapter-63")
    assert detected.url_template == "https://example.com/series/chapter-{n}"
