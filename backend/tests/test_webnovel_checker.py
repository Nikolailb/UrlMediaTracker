"""REQ-017: WebNovel uses scoped catalog IDs, never numeric URL probing."""
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
from services.auth import hash_password
from routers import tools as tool_routes

from services.checking import selector
from services.checking.orchestrator import CheckerConfig
from services.checking.sites.webnovel import parse_webnovel, series_url

BOOK = "https://www.webnovel.com/book/35844914500239705"
HTML = (Path(__file__).parent / "fixtures" / "webnovel_book.html").read_text(encoding="utf-8")


def test_webnovel_catalog_uses_index_and_opaque_id():
    assert series_url(BOOK + "/96231485677293542") == BOOK
    assert series_url(BOOK + "/catalog") == BOOK
    assert series_url("https://www.webnovel.com/book/other_35844914500239705") == BOOK
    assert series_url("https://www.webnovel.com.evil.test/book/35844914500239705") is None
    result = parse_webnovel(HTML, BOOK)
    assert result.state == "OK"
    assert result.latest.chapter == "2"  # total count includes an auxiliary entry
    assert result.latest.url == BOOK + "/96232671088268884"
    assert result.first_url == BOOK + "/96231485677293542"
    assert result.title == "My Hero Academia: Chaos' Whims"


def test_webnovel_mismatched_book_or_latest_fails_closed():
    assert parse_webnovel(HTML, "https://www.webnovel.com/book/11111111111111111").state == "CONTRADICTORY"
    changed = HTML.replace('"chapterIndex":2,"chapterName":"One\'s',
                           '"chapterIndex":5,"chapterName":"One\'s', 1)
    assert parse_webnovel(changed, BOOK).state == "CONTRADICTORY"
    assert parse_webnovel("<html><div>Challenge</div></html>", BOOK).state == "CHANGED_LAYOUT"


def test_webnovel_check_uses_browser_result_without_probe(monkeypatch):
    calls = []
    async def fetched(url):
        calls.append(url)
        return 200, url, HTML.encode(), {}, True
    monkeypatch.setattr(selector, "fetch_webnovel", fetched)
    item = SimpleNamespace(series_url=BOOK, original_url=BOOK, strategy_override=None,
                           latest_chapter="1", current_chapter="1")
    result = asyncio.run(selector.check_source(item, CheckerConfig()))
    assert result.method == "WEBNOVEL" and result.outcome == "NEW"
    assert result.chapter == "2" and result.chapter_url == BOOK + "/96232671088268884"
    assert result.first_url == BOOK + "/96231485677293542"
    assert calls == [BOOK]


def test_webnovel_chapter_url_add_never_stores_opaque_id_as_progress(monkeypatch):
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
            db.add(User(username="webnovel-reader", hashed_password=hash_password("reader-long-password")))
            db.commit()
        client = TestClient(main.app)
        login = client.post("/auth/login", json={"username": "webnovel-reader", "password": "reader-long-password"})
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        created = client.post("/items", json={"url": BOOK + "/96231485677293542"}, headers=headers)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item["series_url"] == BOOK and item["toc_url"] == BOOK
        assert item["url_template"] is None
        assert item["current_chapter"] is None and item["latest_chapter"] is None
    finally:
        main.app.dependency_overrides.clear()


def test_webnovel_add_preview_hides_opaque_ids(monkeypatch):
    async def challenge(_url):
        return {"state": "LIKELY_CLOUDFLARE", "status_code": 403, "final_url": BOOK}

    async def fetched(url):
        return 200, url, HTML.encode(), {}, True

    monkeypatch.setattr(tool_routes, "diagnose_url", challenge)
    monkeypatch.setattr(tool_routes, "browser_enabled_for", lambda _url: True)
    monkeypatch.setattr(tool_routes, "fetch_webnovel", fetched)
    result = asyncio.run(tool_routes.preview(tool_routes.UrlInput(url=BOOK + "/96231485677293542")))
    assert result["access"]["state"] == "REACHABLE_VIA_BROWSER"
    assert result["checker"] == "WEBNOVEL" and result["latest_chapter"] == "2"
    assert result["current_chapter"] is None and result["url_template"] is None
