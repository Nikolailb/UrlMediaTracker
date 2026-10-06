"""REQ-007 and REQ-015 regression samples from user-supplied series pages."""
import asyncio
import json
from types import SimpleNamespace

import pytest
import httpx

from services.checking import selector as site_checker, browser as browser_fetch, http as source_http
from services.checking.sites.freewebnovel import parse_freewebnovel
from services.checking.orchestrator import CheckerConfig
from services import covers


@pytest.mark.parametrize("slug,title,latest,cover", [
    ("as-a-mafia-boss-i-refuse-to-be-an-extra", "As A Mafia Boss, I Refuse To Be An Extra", 546,
     "/files/article/image/12/12656/12656s.jpg"),
    ("my-taboo-harem", "My Taboo Harem!", 1314,
     "/files/article/image/12/12126/12126s.jpg"),
])
def test_page_metadata_latest_section_and_paginated_list(slug, title, latest, cover):
    base = f"https://freewebnovel.com/novel/{slug}"
    # The actual pages contain these same signals. The first 40 ToC entries
    # and unrelated sidebar numbers must never determine the latest chapter.
    html = f'''<head><meta property="og:title" content="{title}">
    <meta property="og:image" content="https://freewebnovel.com{cover}">
    <meta property="og:novel:lastest_chapter_name" content="Chapter {latest}: Latest">
    <meta property="og:novel:lastest_chapter_url" content="{base}/chapter-{latest}"></head>
    <div id="indexListPage" data-total-chapters="{latest}">
      <div class="m-newest1"><ul class="ul-list5">
        <li><a href="/novel/{slug}/chapter-{latest}">Chapter {latest}: Latest</a></li>
        <li><a href="/novel/{slug}/chapter-{latest-1}">Chapter {latest-1}: Previous</a></li>
      </ul></div>
      <div id="idData"><a href="/novel/{slug}/chapter-40">Chapter 40</a></div>
      <div class="col-slide"><a href="/novel/other-story/chapter-5682">Chapter 5682</a></div>
    </div>'''
    found = parse_freewebnovel(html, base)
    assert found == {"title": title, "cover_url": "https://freewebnovel.com" + cover,
                     "chapter": str(latest), "chapter_url": f"{base}/chapter-{latest}"}


def test_conflicting_page_signals_are_not_accepted():
    base = "https://freewebnovel.com/novel/my-taboo-harem"
    html = f'''<meta property="og:novel:lastest_chapter_name" content="Chapter 5682">
    <meta property="og:novel:lastest_chapter_url" content="{base}/chapter-5682">
    <div id="indexListPage" data-total-chapters="1314"><div class="m-newest1">
      <a href="/novel/my-taboo-harem/chapter-1314">Chapter 1314</a></div></div>'''
    assert parse_freewebnovel(html, base)["chapter"] is None


def test_challenge_uses_opt_in_browser_only_for_site_scraper(monkeypatch):
    base = "https://freewebnovel.com/novel/my-taboo-harem"
    called = []

    async def challenge(_url, **_kwargs):
        return 403, base, b"cf-chl checking your browser", {"cf-ray": "fixture"}

    async def browser(url, *, purpose):
        called.append((url, purpose))
        return 200, url, f'''<meta property="og:novel:lastest_chapter_name" content="Chapter 1314">
          <meta property="og:novel:lastest_chapter_url" content="{base}/chapter-1314">'''.encode(), {}

    monkeypatch.setattr(site_checker, "safe_get", challenge)
    monkeypatch.setattr("services.checking.browser.browser_get", browser)
    item = SimpleNamespace(series_url=base, original_url=base, strategy_override=None,
                           latest_chapter="1313", current_chapter="1313")
    result = asyncio.run(site_checker.check_source(item, CheckerConfig()))
    assert (result.outcome, result.chapter) == ("NEW", "1314")
    assert called == [(base, "SITE_SCRAPER")]
    monkeypatch.setattr(source_http, "safe_get", challenge)
    assert asyncio.run(source_http.diagnose_url(base))["state"] == "LIKELY_CLOUDFLARE"
    assert called == [(base, "SITE_SCRAPER")]


def test_browser_fetch_is_off_by_default_and_rejects_probing(monkeypatch):
    monkeypatch.setattr(browser_fetch.settings, "FLARESOLVERR_URL", None)
    monkeypatch.setattr(browser_fetch.settings, "FLARESOLVERR_ALLOWED_HOSTS", "")
    url = "https://freewebnovel.com/novel/my-taboo-harem"
    with pytest.raises(browser_fetch.BrowserFetchError, match="not enabled"):
        asyncio.run(browser_fetch.browser_get(url, purpose="SITE_SCRAPER"))
    with pytest.raises(browser_fetch.BrowserFetchError, match="limited"):
        asyncio.run(browser_fetch.browser_get(url, purpose="INCREMENTAL_PROBE"))


def test_browser_fetch_rejects_unlisted_host(monkeypatch):
    monkeypatch.setattr(browser_fetch.settings, "FLARESOLVERR_URL", "http://127.0.0.1:8191")
    monkeypatch.setattr(browser_fetch.settings, "FLARESOLVERR_ALLOWED_HOSTS", "freewebnovel.com")
    with pytest.raises(browser_fetch.BrowserFetchError, match="not enabled"):
        asyncio.run(browser_fetch.browser_get("https://example.com/toc", purpose="TOC_SCRAPER"))


def test_challenge_without_browser_stays_blocked(monkeypatch):
    base = "https://freewebnovel.com/novel/my-taboo-harem"
    async def challenge(_url, **_kwargs):
        return 403, base, b"cf-chl", {"cf-ray": "fixture"}
    async def unavailable(*_args, **_kwargs):
        raise browser_fetch.BrowserFetchError("not enabled")
    monkeypatch.setattr(site_checker, "safe_get", challenge)
    monkeypatch.setattr(browser_fetch, "browser_get", unavailable)
    item = SimpleNamespace(series_url=base, original_url=base, strategy_override=None)
    assert asyncio.run(site_checker.check_source(item, CheckerConfig())).outcome == "BLOCKED"


def test_opted_in_site_uses_browser_after_direct_connection_failure(monkeypatch):
    base = "https://freewebnovel.com/novel/my-taboo-harem"
    calls = []
    async def connection_failed(_url, **_kwargs):
        raise httpx.ConnectError("All connection attempts failed")
    async def browser(url, *, purpose):
        calls.append((url, purpose))
        html = f'''<meta property="og:novel:lastest_chapter_name" content="Chapter 1314">
        <meta property="og:novel:lastest_chapter_url" content="{base}/chapter-1314">'''
        return 200, url, html.encode(), {}
    monkeypatch.setattr(site_checker, "safe_get", connection_failed)
    monkeypatch.setattr(browser_fetch, "browser_get", browser)
    item = SimpleNamespace(series_url=base, original_url=base, strategy_override=None,
                           latest_chapter="1313", current_chapter="1313")
    result = asyncio.run(site_checker.check_source(item, CheckerConfig()))
    assert (result.outcome, result.chapter) == ("NEW", "1314")
    assert calls == [(base, "SITE_SCRAPER")]

    async def browser_off(*_args, **_kwargs):
        raise browser_fetch.BrowserFetchError("not enabled")
    monkeypatch.setattr(browser_fetch, "browser_get", browser_off)
    assert asyncio.run(site_checker.check_source(item, CheckerConfig())).outcome == "FAILED"


def test_generic_toc_may_use_approved_browser(monkeypatch):
    url = "https://example.com/series"
    calls = []
    async def challenge(_url, **_kwargs):
        return 403, url, b"cf-chl", {"cf-ray": "fixture"}
    async def browser(target, *, purpose):
        calls.append((target, purpose))
        return 200, target, b'<a href="/series/chapter-4">Chapter 4</a>', {}
    monkeypatch.setattr(site_checker, "safe_get", challenge)
    monkeypatch.setattr(browser_fetch, "browser_get", browser)
    item = SimpleNamespace(series_url=None, original_url=url, strategy_override="TOC_SCRAPER",
                           check_strategy="TOC_SCRAPER", toc_url=url,
                           url_template=url + "/chapter-{n}", latest_chapter="3", current_chapter="3")
    assert asyncio.run(site_checker.check_source(item, CheckerConfig())).chapter == "4"
    assert calls == [(url, "TOC_SCRAPER")]


def test_browser_fetch_validates_result_host(monkeypatch):
    monkeypatch.setattr(browser_fetch.settings, "FLARESOLVERR_URL", "http://127.0.0.1:8191")
    monkeypatch.setattr(browser_fetch.settings, "FLARESOLVERR_ALLOWED_HOSTS", "freewebnovel.com")
    async def public(url): return url
    monkeypatch.setattr(browser_fetch, "validate_public_url", public)
    target = "https://freewebnovel.com/novel/my-taboo-harem"
    result_url = [target]

    class Response:
        def raise_for_status(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def aiter_bytes(self):
            yield json.dumps({"status": "ok", "solution": {"url": result_url[0],
                "status": 200, "response": "<html>series</html>", "headers": {}}}).encode()

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        def stream(self, method, endpoint, *, json):
            assert method == "POST" and endpoint == "http://127.0.0.1:8191/v1"
            assert json["url"] == target and json["cmd"] == "request.get"
            return Response()

    monkeypatch.setattr(browser_fetch.httpx, "AsyncClient", lambda **_kwargs: Client())
    assert asyncio.run(browser_fetch.browser_get(target, purpose="SITE_SCRAPER"))[2] == b"<html>series</html>"
    result_url[0] = "http://127.0.0.1/admin"
    with pytest.raises(browser_fetch.BrowserFetchError, match="approved host"):
        asyncio.run(browser_fetch.browser_get(target, purpose="SITE_SCRAPER"))


def test_cover_metadata_is_parsed_outside_checker_selector(monkeypatch):
    series = "https://freewebnovel.com/novel/my-taboo-harem"
    image = "https://freewebnovel.com/files/article/image/12/12126/12126s.jpg"
    requests = []

    async def fake_get(url, **_kwargs):
        requests.append(url)
        if url == series:
            return 200, series, f'<meta property="og:image" content="{image}">'.encode(), {}
        return 200, image, b"image-bytes", {"content-type": "image/jpeg"}

    monkeypatch.setattr(source_http, "safe_get", fake_get)
    monkeypatch.setattr(covers, "save_cover", lambda raw: "saved.jpg" if raw == b"image-bytes" else None)
    assert asyncio.run(covers.fetch_cover(series)) == "saved.jpg"
    assert requests == [series, image]
