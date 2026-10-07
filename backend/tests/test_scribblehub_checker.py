"""REQ-019: Scribble Hub tracks series-scoped ToC order, not chapter titles or IDs."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import main
from database import get_db
from models.base import Base
from models.user import User
from routers import tools as tool_routes
from services.auth import hash_password
from services.checking import selector
from services.checking.orchestrator import CheckerConfig
from services.checking.sites import scribblehub as site

SERIES = "https://www.scribblehub.com/series/2388343/"
CHAPTER = "https://www.scribblehub.com/read/2388343-what-the-magical-girls-from-my-favorite-yuri-are-into-me/chapter/2600496/"
HTML = (Path(__file__).parent / "fixtures" / "scribblehub_series.html").read_text(encoding="utf-8")


def test_scribblehub_scope_and_newest_first_catalog():
    assert site.series_url(SERIES + "what-the-magical-girls-from-my-favorite-yuri-are-into-me/") == SERIES
    assert site.series_url(CHAPTER) == SERIES
    assert site.series_url("https://www.scribblehub.com/series/2388343/old-slug/?utm_source=search") == SERIES
    assert site.series_url("https://www.scribblehub.com.evil.test/series/2388343/") is None
    found = site.parse_scribblehub(HTML, SERIES)
    assert found.state == "OK" and found.confidence == "HIGH"
    assert found.latest.chapter == "126"  # The visible title says Chapter 125.
    assert found.latest.url.endswith("/chapter/2602375/")
    assert found.first_url.endswith("/chapter/2388346/")
    assert len(found.links) == 4


def test_scribblehub_rejects_wrong_series_and_partial_or_changed_toc():
    assert site.parse_scribblehub(HTML, "https://www.scribblehub.com/series/999999/").state == "CONTRADICTORY"
    assert site.parse_scribblehub(HTML.replace('order="126"', 'order="128"'), SERIES).state == "CONTRADICTORY"
    assert site.parse_scribblehub(
        HTML.replace(CHAPTER, "https://www.scribblehub.com/read/9999-other/chapter/2600496/"),
        SERIES).state == "TRUNCATED"
    assert site.parse_scribblehub(HTML.replace('class="toc_w" order="125"', 'class="other" order="125"'), SERIES).state == "TRUNCATED"
    assert site.parse_scribblehub(HTML.replace('class="cnt_toc">126', 'class="cnt_toc">bad'), SERIES).state == "CHANGED_LAYOUT"
    assert site.parse_scribblehub("<html>challenge</html>", SERIES).state == "CHANGED_LAYOUT"


def test_scribblehub_selector_detects_change_and_same_position_replacement(monkeypatch):
    async def fetched(_url):
        return 200, SERIES, HTML.encode(), {}, True
    monkeypatch.setattr(selector, "fetch_scribblehub", fetched)
    item = SimpleNamespace(series_url=SERIES, original_url=SERIES, strategy_override=None,
                           latest_chapter="125", current_chapter="125", latest_chapter_url=None)
    checked = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert checked.outcome == "NEW" and checked.method == "SCRIBBLEHUB"
    assert checked.chapter == "126" and checked.chapter_url.endswith("/chapter/2602375/")
    item.latest_chapter = "126"
    item.latest_chapter_url = "https://www.scribblehub.com/read/2388343-old-title/chapter/2602375/"
    checked = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert checked.outcome == "UNCHANGED"
    item.latest_chapter_url = "https://www.scribblehub.com/read/2388343-old/chapter/9999999/"
    checked = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert checked.outcome == "FAILED" and "same ToC position" in checked.detail


def test_scribblehub_browser_retry_only_after_challenge(monkeypatch):
    calls = []
    async def direct(url, **_kwargs):
        calls.append(("direct", url))
        return 403, url, b"cf-chl", {"cf-ray": "fixture"}
    async def browser(url, *, purpose, max_bytes):
        calls.append((purpose, url))
        assert max_bytes == site.MAX_PAGE_BYTES + 1
        return 200, url, HTML.encode(), {}
    monkeypatch.setattr(site, "safe_get", direct)
    monkeypatch.setattr(site, "browser_get", browser)
    result = asyncio.run(site.fetch_scribblehub(SERIES))
    assert result[0] == 200 and result[-1] is True
    assert calls == [("direct", SERIES), ("SITE_SCRAPER", SERIES)]


def test_scribblehub_browser_unavailable_keeps_direct_challenge(monkeypatch):
    async def direct(url, **_kwargs):
        return 403, url, b"cf-chl", {"cf-ray": "fixture"}
    async def unavailable(*_args, **_kwargs):
        raise site.BrowserFetchError("Host not allowlisted")
    monkeypatch.setattr(site, "safe_get", direct)
    monkeypatch.setattr(site, "browser_get", unavailable)
    status, _, _, _, used_browser = asyncio.run(site.fetch_scribblehub(SERIES))
    assert status == 403 and used_browser is False


def test_scribblehub_chapter_add_keeps_opaque_id_out_of_progress(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def session_factory():
        return Session(engine)
    def test_db():
        with session_factory() as db:
            yield db
    async def no_cover(_url):
        return None
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    monkeypatch.setattr("routers.items.fetch_cover", no_cover)
    main.app.dependency_overrides[get_db] = test_db
    try:
        with session_factory() as db:
            db.add(User(username="scribble-reader", hashed_password=hash_password("reader-long-password")))
            db.commit()
        client = TestClient(main.app)
        login = client.post("/auth/login", json={"username": "scribble-reader", "password": "reader-long-password"})
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        created = client.post("/items", json={"url": CHAPTER}, headers=headers)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item["series_url"] == SERIES and item["toc_url"] == SERIES
        assert item["url_template"] is None
        assert item["current_chapter"] is None and item["latest_chapter"] is None
    finally:
        main.app.dependency_overrides.clear()


def test_scribblehub_preview_reports_browser_method(monkeypatch):
    async def challenge(_url):
        return {"state": "LIKELY_CLOUDFLARE", "status_code": 403, "final_url": SERIES}
    async def fetched(_url):
        return 200, SERIES, HTML.encode(), {}, True
    monkeypatch.setattr(tool_routes, "diagnose_url", challenge)
    monkeypatch.setattr(tool_routes, "browser_enabled_for", lambda _url: True)
    monkeypatch.setattr(tool_routes, "fetch_scribblehub", fetched)
    result = asyncio.run(tool_routes.preview(tool_routes.UrlInput(url=CHAPTER)))
    assert result["access"]["state"] == "REACHABLE_VIA_BROWSER"
    assert result["checker"] == "SCRIBBLEHUB" and result["latest_chapter"] == "126"
    assert result["current_chapter"] is None and result["url_template"] is None
    selected = asyncio.run(tool_routes.toc_preview(tool_routes.TocPreviewInput(url=SERIES)))
    assert selected["state"] == "OK" and selected["method"] == "SCRIBBLEHUB"
