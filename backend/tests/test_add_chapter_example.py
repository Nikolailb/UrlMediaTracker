"""REQ-004/REQ-005: a ToC-first add can use a separate chapter URL example."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import main
from database import get_db
from models.base import Base
from models.user import User
from models.item import TrackedItem, PatternSource
from services.auth import hash_password


def test_toc_first_add_uses_chapter_example_without_inferred_progress(monkeypatch):
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
            db.add(User(username="reader", hashed_password=hash_password("reader-long-password")))
            db.commit()

        client = TestClient(main.app)
        login = client.post("/auth/login", json={"username": "reader", "password": "reader-long-password"})
        assert login.status_code == 200
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        toc = "https://hentai20.io/i-became-a-pornhwa-npc/"
        chapter = "https://hentai20.io/i-became-a-pornhwa-npc-chapter-55/"
        created = client.post("/items", json={
            "url": toc, "chapter_url": chapter, "strategy_override": "TOC_SCRAPER",
        }, headers=headers)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item["original_url"] == toc
        assert item["toc_url"] == toc
        assert item["url_template"] == "https://hentai20.io/i-became-a-pornhwa-npc-chapter-{n}/"
        assert item["strategy_override"] == "TOC_SCRAPER"
        assert item["current_chapter"] is None
        assert item["latest_chapter"] is None

        edited = client.patch(f"/items/{item['id']}", json={
            "chapter_url": "https://hentai20.io/i-became-a-pornhwa-npc-chapter-60/",
            "toc_url": toc,
        }, headers=headers)
        assert edited.status_code == 200, edited.text
        assert edited.json()["url_template"] == "https://hentai20.io/i-became-a-pornhwa-npc-chapter-{n}/"
        assert edited.json()["toc_url"] == toc
        assert edited.json()["current_chapter"] is None
        assert edited.json()["latest_chapter"] is None

        invalid_edit = client.patch(f"/items/{item['id']}", json={"chapter_url": "file:///etc/passwd"}, headers=headers)
        assert invalid_edit.status_code == 422

        custom_toc = "https://hentai20.io/i-became-a-pornhwa-npc/chapters/"
        other = client.post("/items", json={
            "url": toc, "chapter_url": chapter, "toc_url": custom_toc,
            "strategy_override": "INCREMENTAL_PROBE", "current_chapter": "12",
        }, headers=headers)
        assert other.status_code == 201, other.text
        assert other.json()["toc_url"] == custom_toc
        assert other.json()["strategy_override"] == "INCREMENTAL_PROBE"
        assert other.json()["current_chapter"] == "12"
        assert other.json()["latest_chapter"] is None

        invalid = client.post("/items", json={
            "url": toc, "chapter_url": "file:///etc/passwd",
        }, headers=headers)
        assert invalid.status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_create_and_mark_sensitive_while_safe_view_is_on(monkeypatch):
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
            db.add(User(username="reader", hashed_password=hash_password("reader-long-password")))
            db.commit()
        client = TestClient(main.app)
        login = client.post("/auth/login", json={"username": "reader", "password": "reader-long-password"})
        assert login.json()["safe_view_enabled"] is True
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}

        hidden = client.post("/items", json={"url": "https://example.com/private/list", "is_sensitive": True}, headers=headers)
        assert hidden.status_code == 201, hidden.text
        hidden_id = hidden.json()["id"]
        assert client.get("/items").json() == []
        assert client.get(f"/items/{hidden_id}").status_code == 404

        visible = client.post("/items", json={"url": "https://example.com/public/list"}, headers=headers)
        assert visible.status_code == 201
        visible_id = visible.json()["id"]
        changed = client.patch(f"/items/{visible_id}", json={"is_sensitive": True}, headers=headers)
        assert changed.status_code == 200
        assert client.get("/items").json() == []
        assert client.get(f"/items/{visible_id}").status_code == 404

        with session_factory() as db:
            reader = db.query(User).filter_by(username="reader").one()
            webtoon = TrackedItem(
                original_url="https://www.webtoons.com/en/super-hero/unordinary/list?title_no=679",
                toc_url="https://www.webtoons.com/en/super-hero/unordinary/list?title_no=679",
                url_template="https://www.webtoons.com/en/super-hero/unordinary/episode-{n}/viewer?title_no=679&episode_no=404",
                chapter_regex=r"episode-(\d+)", pattern_source=PatternSource.MANUAL,
                latest_chapter="393", current_chapter="391", user_id=reader.id,
            )
            db.add(webtoon)
            db.commit()
            webtoon_id = webtoon.id
        next_page = client.get(f"/items/{webtoon_id}/next")
        assert next_page.status_code == 200
        assert next_page.json()["destination"] == "TOC"
        assert next_page.json()["next_url"].endswith("/list?title_no=679")
        edited = client.patch(f"/items/{webtoon_id}", json={"manual_regex": r"episode-(\d+)",
                                                       "strategy_override": "TOC_SCRAPER"}, headers=headers)
        assert edited.status_code == 200, edited.text
        assert edited.json()["chapter_regex"] == r"episode-(\d+)"
        assert edited.json()["url_template"] is None
    finally:
        main.app.dependency_overrides.clear()
