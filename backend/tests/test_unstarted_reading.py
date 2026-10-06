"""REQ-011: a saved series with no reading progress starts at chapter one."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import main
from database import get_db
from models.base import Base
from models.item import TrackedItem
from models.user import User
from services.auth import hash_password


def test_unstarted_series_opens_and_marks_first_chapter(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def session_factory():
        return Session(engine)

    def test_db():
        with session_factory() as db:
            yield db

    monkeypatch.setattr(main, "SessionLocal", session_factory)
    main.app.dependency_overrides[get_db] = test_db
    try:
        series = "https://freewebnovel.com/novel/reborn-as-the-genius-son-of-the-richest-family"
        with session_factory() as db:
            owner = User(username="reader", hashed_password=hash_password("reader-long-password"))
            db.add(owner)
            db.flush()
            item = TrackedItem(original_url=series, series_url=series, user_id=owner.id,
                               url_template=series + "/chapter-{n}", latest_chapter="1416")
            db.add(item)
            db.commit()
            item_id = item.id

        client = TestClient(main.app)
        login = client.post("/auth/login", json={"username": "reader", "password": "reader-long-password"})
        assert login.status_code == 200
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        before = client.get(f"/items/{item_id}").json()
        assert before["current_chapter"] is None
        assert before["has_unread"] is True
        next_chapter = client.get(f"/items/{item_id}/next").json()
        assert next_chapter["next_chapter"] == "1"
        assert next_chapter["next_url"] == series + "/chapter-1"
        assert client.get(f"/items/{item_id}").json()["current_chapter"] is None

        marked = client.post(f"/items/{item_id}/mark-read", json={"chapter": "1"}, headers=headers)
        assert marked.status_code == 200
        assert marked.json()["current_chapter"] == "1"
        assert client.get(f"/items/{item_id}/next").json()["next_chapter"] == "2"
    finally:
        main.app.dependency_overrides.clear()
