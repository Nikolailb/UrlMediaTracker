"""REQ-018: Royal Road position comes from the scoped fiction catalog."""
import asyncio
import re
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
from services.checking.sites.royalroad import parse_royalroad, series_url
from services.checking.sites import royalroad as royalroad_site

FICTION = "https://www.royalroad.com/fiction/107917"
HTML = (Path(__file__).parent / "fixtures" / "royalroad_fiction.html").read_text(encoding="utf-8")


def test_royalroad_stable_fiction_id_and_catalog_order():
    assert series_url(FICTION + "/sky-pride-old-title") == FICTION
    assert series_url(FICTION + "/sky-pride-old-title/chapter/2113501/chapter-1--first") == FICTION
    assert series_url("https://www.royalroad.com/fiction/65629/the-game-at-carousel?utm_source=search&utm_medium=fiction-search") == "https://www.royalroad.com/fiction/65629"
    assert series_url("https://www.royalroad.com.evil.test/fiction/107917") is None
    found = parse_royalroad(HTML, FICTION)
    assert found.state == "OK"
    assert found.title == "Sky Pride [Title changes often]"
    assert found.latest.chapter == "3"  # title is Art Contest; volume numbering restarted
    assert found.latest.url == FICTION + "/sky-pride-old-title/chapter/4079802/art-contest"
    assert found.first_url == FICTION + "/sky-pride-old-title/chapter/2113501/chapter-1--first"


def test_royalroad_rejects_other_fiction_and_incomplete_catalog():
    assert parse_royalroad(HTML, "https://www.royalroad.com/fiction/999999").state == "CONTRADICTORY"
    assert parse_royalroad(HTML.replace('"order":2', '"order":5'), FICTION).state == "CONTRADICTORY"
    assert parse_royalroad(HTML.replace('"id":4079802', '"id":4079803'), FICTION).state == "TRUNCATED"
    duplicate = HTML.replace('"id":4079802', '"id":2113560').replace('/chapter/4079802/art-contest', '/chapter/2113560/art-contest')
    assert parse_royalroad(duplicate, FICTION).state == "CONTRADICTORY"
    assert parse_royalroad(HTML.replace('data-chapters="3"', 'data-chapters="4"'), FICTION).state == "TRUNCATED"
    assert parse_royalroad(HTML.replace('"order":2,"visible":1', '"order":2,"visible":0'), FICTION).state == "TRUNCATED"
    assert parse_royalroad(HTML.replace('"order":2,"visible":1,"hiddenCount":null',
                                        '"order":2,"visible":1,"hiddenCount":1'), FICTION).state == "TRUNCATED"
    assert parse_royalroad("<html>challenge</html>", FICTION).state == "CHANGED_LAYOUT"


def test_royalroad_check_uses_browser_catalog_without_probe(monkeypatch):
    calls = []
    async def fetched(url):
        calls.append(url)
        return 200, url, HTML.encode(), {}, True
    monkeypatch.setattr(selector, "fetch_royalroad", fetched)
    item = SimpleNamespace(series_url=FICTION, original_url=FICTION, strategy_override=None,
                           latest_chapter="2", current_chapter="2", latest_chapter_url=None)
    checked = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert checked.method == "ROYALROAD" and checked.outcome == "NEW"
    assert checked.chapter == "3" and checked.chapter_url.endswith("/chapter/4079802/art-contest")
    assert calls == [FICTION]


def test_royalroad_same_position_with_new_chapter_id_is_an_issue(monkeypatch):
    async def fetched(url):
        return 200, url, HTML.encode(), {}, True
    monkeypatch.setattr(selector, "fetch_royalroad", fetched)
    item = SimpleNamespace(series_url=FICTION, original_url=FICTION, strategy_override=None,
                           latest_chapter="3", current_chapter="2",
                           latest_chapter_url=FICTION + "/sky-pride-old-title/chapter/9999999/other")
    checked = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert checked.outcome == "FAILED" and "no longer in the catalog" in checked.detail


def test_royalroad_stubbing_keeps_monotonic_tracker_position(monkeypatch):
    stubbed = re.sub(r'\{"id":2113501[^\n]+\n', '', HTML)
    stubbed = (stubbed.replace('"order":1', '"order":0')
              .replace('"order":2', '"order":1')
              .replace('data-chapters="3"', 'data-chapters="2"'))
    async def fetched(_url):
        return 200, FICTION, stubbed.encode(), {}, True

    monkeypatch.setattr(selector, "fetch_royalroad", fetched)
    item = SimpleNamespace(series_url=FICTION, original_url=FICTION, strategy_override=None,
                           latest_chapter="3", current_chapter="2",
                           latest_chapter_url=FICTION + "/sky-pride-old-title/chapter/4079802/art-contest")
    checked = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert checked.outcome == "UNCHANGED" and checked.chapter == "3"

    with_new = stubbed.replace(']; window.volumes',
        ',{"id":4079803,"order":2,"visible":1,"url":"/fiction/107917/sky-pride-old-title/chapter/4079803/new-post"}]; window.volumes')
    with_new = with_new.replace('data-chapters="2"', 'data-chapters="3"')
    async def fetched_new(_url):
        return 200, FICTION, with_new.encode(), {}, True

    monkeypatch.setattr(selector, "fetch_royalroad", fetched_new)
    checked = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert checked.outcome == "NEW" and checked.chapter == "4"


def test_royalroad_browser_retry_only_after_challenge(monkeypatch):
    calls = []
    async def challenged(url, **_kwargs):
        calls.append(("direct", url))
        return 403, url, b"cf-chl", {"cf-ray": "fixture"}

    async def browser(url, *, purpose, max_bytes):
        calls.append((purpose, url))
        assert max_bytes == royalroad_site.MAX_PAGE_BYTES + 1
        return 200, url, HTML.encode(), {}

    monkeypatch.setattr(royalroad_site, "safe_get", challenged)
    monkeypatch.setattr(royalroad_site, "browser_get", browser)
    result = asyncio.run(royalroad_site.fetch_royalroad(FICTION))
    assert result[0] == 200 and result[-1] is True
    assert calls == [("direct", FICTION), ("SITE_SCRAPER", FICTION)]


def test_royalroad_chapter_url_add_does_not_save_opaque_id_as_progress(monkeypatch):
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
            db.add(User(username="royal-reader", hashed_password=hash_password("reader-long-password")))
            db.commit()
        client = TestClient(main.app)
        login = client.post("/auth/login", json={"username": "royal-reader", "password": "reader-long-password"})
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        created = client.post("/items", json={
            "url": FICTION + "/sky-pride-old-title/chapter/2113501/chapter-1--first",
        }, headers=headers)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item["series_url"] == FICTION and item["toc_url"] == FICTION
        assert item["url_template"] is None
        assert item["current_chapter"] is None and item["latest_chapter"] is None
    finally:
        main.app.dependency_overrides.clear()


def test_royalroad_add_preview_reports_browser_result_without_id_progress(monkeypatch):
    async def challenge(_url):
        return {"state": "LIKELY_CLOUDFLARE", "status_code": 403, "final_url": FICTION}

    async def fetched(url):
        return 200, url, HTML.encode(), {}, True

    monkeypatch.setattr(tool_routes, "diagnose_url", challenge)
    monkeypatch.setattr(tool_routes, "browser_enabled_for", lambda _url: True)
    monkeypatch.setattr(tool_routes, "fetch_royalroad", fetched)
    result = asyncio.run(tool_routes.preview(tool_routes.UrlInput(
        url=FICTION + "/sky-pride-old-title/chapter/2113501/chapter-1--first")))
    assert result["access"]["state"] == "REACHABLE_VIA_BROWSER"
    assert result["checker"] == "ROYALROAD" and result["latest_chapter"] == "3"
    assert result["current_chapter"] is None and result["url_template"] is None
