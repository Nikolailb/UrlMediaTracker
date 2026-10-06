"""REQ-004/REQ-005: a ToC-first add can use a separate chapter URL example."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import main
from database import get_db
from models.base import Base
from models.user import User
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
