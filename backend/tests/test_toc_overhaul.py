"""REQ-016: actual links, duplicate groups, pagination and Comix metadata."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import httpx

from services.checking import selector
from services.checking.sites.comix import parse_comix, merge_rendered_group
from services.checking.strategies.toc import parse_toc
from services.checking.strategies.probe import CheckerConfig
from routers import tools
from services.checking.results import Extraction
from schemas.item import ItemCreate
from services.pattern_detection import detect_pattern, unsafe_chapter_template

BASE = "https://comix.to/title/39w1n-the-mating-of-elves"
WEBTOONS = "https://www.webtoons.com/en/super-hero/unordinary/list?title_no=679"


def test_webtoons_list_uses_visible_episode_not_internal_id(monkeypatch):
    html = (Path(__file__).parent / "fixtures" / "webtoons_unordinary_list.html").read_text()
    example = "https://www.webtoons.com/en/super-hero/unordinary/episode-391/viewer?title_no=679&episode_no=410"
    found = parse_toc(html, WEBTOONS, examples=[example], chapter_regex=r"episode-(\d+)")
    assert found.state == "OK"
    assert found.latest.chapter == "393"
    assert found.latest.url.endswith("/episode-393/viewer?title_no=679&episode_no=412")
    assert len(found.links) == 3
    assert found.last_page_url.endswith("list?page=2&title_no=679")
    pattern = detect_pattern(example)
    assert pattern.current_chapter == "391"
    assert pattern.url_template is None
    assert pattern.strategy_used == "ambiguous_id"
    manual = detect_pattern(example, r"episode-(\d+)")
    assert manual.chapter_regex == r"episode-(\d+)"
    assert manual.current_chapter == "391"
    assert manual.url_template is None
    assert unsafe_chapter_template(
        "https://www.webtoons.com/en/super-hero/unordinary/episode-{n}/viewer?title_no=679&episode_no=404")

    async def get(url, **_kwargs):
        assert url == WEBTOONS
        return 200, url, html.encode(), {}

    monkeypatch.setattr(selector, "_checker_get", get)
    item = SimpleNamespace(series_url=None, original_url=WEBTOONS, strategy_override="TOC_SCRAPER",
                           check_strategy="TOC_SCRAPER", toc_url=WEBTOONS,
                           url_template="https://www.webtoons.com/en/super-hero/unordinary/episode-{n}/viewer?title_no=679&episode_no=404",
                           latest_chapter="391", current_chapter="390", preferred_group=None,
                           toc_examples_json=json.dumps([example]), toc_row_class=None, toc_latest_page_url=None,
                           chapter_regex=r"episode-(\d+)", pattern_source="MANUAL")
    result = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert (result.outcome, result.chapter, result.chapter_url) == ("NEW", "393", found.latest.url)
    item.strategy_override = "INCREMENTAL_PROBE"
    result = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert result.outcome == "UNSUPPORTED"
    assert "separate path and query" in result.detail


def test_generic_toc_uses_manual_chapter_regex_without_a_url_template():
    url = "https://reader.example/series/story/list?series=42"
    html = '''<a href="/series/story/release-72?series=42">Read newest</a>
    <a href="/series/story/release-71?series=42">Read previous</a>
    <a href="/series/story/release-900?series=99">Other title</a>'''
    assert parse_toc(html, url).state == "EMPTY"
    found = parse_toc(html, url, chapter_regex=r"release-(\d+)")
    assert found.state == "OK"
    assert found.latest.chapter == "72"
    assert len(found.links) == 2
    conflict = '<a href="/series/story/release-72?series=42">Chapter 73</a>'
    assert parse_toc(conflict, url, chapter_regex=r"release-(\d+)").state == "CONTRADICTORY"


def test_toc_preview_passes_manual_regex_to_generic_extractor(monkeypatch):
    url = "https://reader.example/series/story/list?series=42"
    html = '<a href="/series/story/release-72?series=42">Read newest</a>'

    async def valid(_url):
        return None

    async def get(request_url, **_kwargs):
        return 200, request_url, html.encode(), {}

    monkeypatch.setattr(tools, "validate_public_url", valid)
    monkeypatch.setattr(selector, "_checker_get", get)
    result = asyncio.run(tools.toc_preview(tools.TocPreviewInput(
        url=url, strategy_override="TOC_SCRAPER", chapter_regex=r"release-(\d+)")))
    assert (result["state"], result["method"], result["latest_chapter"]) == ("OK", "TOC_SCRAPER", "72")


def test_new_item_check_interval_defaults_to_six_hours():
    assert ItemCreate(url=BASE).check_interval_min == 360


def _comix_html(latest=73):
    slug = "39w1n"
    detail = {"hid": slug, "title": "The Mating of Elves", "latestChapter": latest,
              "latestChapterUrl": f"/title/39w1n-the-mating-of-elves/11434031-chapter-{latest}",
              "firstChapterUrl": "/title/39w1n-the-mating-of-elves/6112546-chapter-1",
              "poster": {"large": "https://static.comix.to/cover.jpg"}}
    queries = {json.dumps(["manga", "detail", slug], separators=(",", ":")): detail,
               json.dumps(["manga", "groups", slug], separators=(",", ":")):
                   [{"id": 12, "name": "Group A"}, {"id": 13, "name": "Group B"}]}
    return '<script type="application/json" id="initial-data">' + json.dumps({"queries": queries}) + "</script>"


def test_comix_series_metadata_and_identity():
    found = parse_comix(_comix_html(), BASE)
    assert found.state == "OK"
    assert found.latest.chapter == "73"
    assert found.latest.url == BASE + "/11434031-chapter-73"
    assert found.first_url == BASE + "/6112546-chapter-1"
    assert found.group_labels["12"] == "Group A"
    assert parse_comix(_comix_html().replace('"hid": "39w1n"', '"hid": "wrong"'), BASE).state == "CONTRADICTORY"
    assert parse_comix(_comix_html().replace("11434031-chapter-73", "11434031-chapter-900"), BASE).state == "CONTRADICTORY"


def test_generic_toc_uses_actual_links_and_deduplicates_groups():
    html = f'''<aside class="related"><a href="{BASE}/8888-chapter-900">Chapter 900</a></aside>
    <ul class="chapters">
      <li data-group="12"><a href="{BASE}/11111-chapter-65">Chapter 65</a></li>
      <li data-group="13"><a href="{BASE}/22222-chapter-65">Chapter 65</a></li>
      <li data-group="12"><a href="{BASE}/33333-chapter-64">Chapter 64</a></li>
    </ul>'''
    found = parse_toc(html, BASE, preferred_group="13")
    assert found.state == "OK"
    assert found.latest.chapter == "65"
    assert found.latest.url == BASE + "/22222-chapter-65"
    assert found.groups == ["12", "13"]
    assert len(found.links) == 3
    assert parse_toc('<div class="related"><a href="/other/chapter-5682">Chapter 5682</a></div>', BASE).state == "EMPTY"


def test_rendered_comix_prefers_group_without_changing_latest():
    found = parse_comix(_comix_html(), BASE)
    html = f'''<ul class="mchap-list"><li class="mchap-item"><div class="mchap-row">
      <a class="mchap-row__primary" href="/title/39w1n-the-mating-of-elves/22222-chapter-73"><span>Ch.73</span></a>
      <div class="mchap-row__secondary"><a class="mchap-row__group" href="/groups/13">Group B</a></div>
    </div></li></ul>'''
    merge_rendered_group(found, html, BASE, "13")
    assert found.latest.chapter == "73"
    assert found.latest.group == "13"
    assert found.latest.url == BASE + "/22222-chapter-73"
    unlisted = parse_comix(_comix_html(), BASE)
    merge_rendered_group(unlisted, html, BASE, "12")
    assert unlisted.latest.chapter == "73"
    assert unlisted.latest.url == BASE + "/11434031-chapter-73"
    assert any("unavailable" in warning for warning in unlisted.warnings)


def test_ascending_pagination_fetches_last_page_and_never_probes(monkeypatch):
    first = '<ul><li><a href="/series/chapter-1">Chapter 1</a></li><li><a href="/series/chapter-2">Chapter 2</a></li></ul><a href="?page=3">Last</a>'
    last = '<ul><li><a href="/series/chapter-64">Chapter 64</a></li><li><a href="/series/chapter-65">Chapter 65</a></li></ul>'
    calls = []

    async def get(url, **_kwargs):
        calls.append(url)
        return 200, url, (last if "page=3" in url else first).encode(), {}

    async def no_probe(*_args, **_kwargs):
        raise AssertionError("No probe after a ToC check")

    monkeypatch.setattr(selector, "_checker_get", get)
    monkeypatch.setattr("services.checking.strategies.probe.IncrementalProbeStrategy.find_latest_chapter", no_probe)
    item = SimpleNamespace(series_url=None, original_url="https://example.com/series",
                           strategy_override=None, check_strategy="TOC_THEN_PROBE",
                           toc_url="https://example.com/series", url_template=None,
                           latest_chapter="64", current_chapter="60", preferred_group=None,
                           toc_examples_json=None, toc_row_class=None)
    result = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert (result.outcome, result.chapter) == ("NEW", "65")
    assert calls == ["https://example.com/series", "https://example.com/series?page=3"]
    assert result.toc_latest_page_url == "https://example.com/series?page=3"


def test_confirmed_latest_page_is_one_fetch_until_rollover(monkeypatch):
    calls = []
    page3 = '<a href="/series/chapter-65">Chapter 65</a><a href="/series/chapter-64">Chapter 64</a>'
    page3_rollover = page3 + '<a href="?page=4">Next</a>'
    page4 = '<a href="/series/chapter-66">Chapter 66</a><a href="/series/chapter-67">Chapter 67</a>'
    rollover = False

    async def get(url, **_kwargs):
        calls.append(url)
        body = page4 if "page=4" in url else page3_rollover if rollover else page3
        return 200, url, body.encode(), {}

    monkeypatch.setattr(selector, "_checker_get", get)
    source = "https://example.com/series"
    confirmed = source + "?page=3"
    found = asyncio.run(selector.extract_toc(source, confirmed_latest_page_url=confirmed))
    assert found.latest.chapter == "65" and found.checked_page_url == confirmed
    assert calls == [confirmed]
    rollover = True
    found = asyncio.run(selector.extract_toc(source, confirmed_latest_page_url=confirmed))
    assert found.latest.chapter == "67" and found.checked_page_url == source + "?page=4"
    assert calls[-2:] == [confirmed, source + "?page=4"]


def test_comix_unchanged_without_template_or_browser(monkeypatch):
    async def get(url, **_kwargs):
        return 200, url, _comix_html().encode(), {}
    monkeypatch.setattr(selector, "_checker_get", get)
    item = SimpleNamespace(series_url=BASE, original_url=BASE, strategy_override=None,
                           latest_chapter="73", current_chapter="60", preferred_group=None)
    result = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert (result.outcome, result.method, result.chapter) == ("UNCHANGED", "COMIX", "73")
    assert result.chapter_url == BASE + "/11434031-chapter-73"


def test_generic_toc_changed_layout_and_conflicting_links():
    url = "https://example.com/series"
    html = '<ul><li class="old-row"><a href="/series/chapter-8">Chapter 8</a></li></ul>'
    assert parse_toc(html, url, row_class="chapter-row").state == "CHANGED_LAYOUT"
    conflict = '<ul><li><a href="/series/chapter-8">Chapter 9</a></li></ul>'
    assert parse_toc(conflict, url).state == "CONTRADICTORY"


def test_toc_preview_reports_connection_failure(monkeypatch):
    async def valid(_url):
        return None

    async def failed(_url, **_kwargs):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(tools, "validate_public_url", valid)
    monkeypatch.setattr(tools, "extract_toc", failed)
    result = asyncio.run(tools.toc_preview(tools.TocPreviewInput(url="https://example.com/series")))
    assert result["state"] == "FAILED"


def test_toc_preview_uses_selected_method_on_comix(monkeypatch):
    async def valid(_url):
        return None

    async def get(url, **_kwargs):
        return 200, url, _comix_html().encode(), {}

    async def generic(_url, **_kwargs):
        return Extraction("EMPTY", "TOC_SCRAPER", warnings=["No trustworthy series chapter links were found."])

    monkeypatch.setattr(tools, "validate_public_url", valid)
    monkeypatch.setattr(tools, "_checker_get", get)
    monkeypatch.setattr(tools, "extract_toc", generic)
    dedicated = asyncio.run(tools.toc_preview(tools.TocPreviewInput(url=BASE)))
    generic_result = asyncio.run(tools.toc_preview(tools.TocPreviewInput(
        url=BASE, strategy_override="TOC_SCRAPER", example_urls=[BASE + "/11434031-chapter-73"])))
    assert (dedicated["state"], dedicated["method"]) == ("OK", "COMIX")
    assert (generic_result["state"], generic_result["method"]) == ("EMPTY", "TOC_SCRAPER")
    assert any("Choose Automatic or Comix" in warning for warning in generic_result["warnings"])


def test_truncated_toc_is_not_unchanged(monkeypatch):
    async def too_large(url, **_kwargs):
        return 200, url, b"a" * 512_001, {}

    monkeypatch.setattr(selector, "_checker_get", too_large)
    found = asyncio.run(selector.extract_toc("https://example.com/series"))
    assert found.state == "TRUNCATED"
    assert selector._from_extraction(found, "12").outcome == "FAILED"
