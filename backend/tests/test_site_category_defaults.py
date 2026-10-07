"""REQ-020: prose-site category defaults remain editable."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import main
from database import get_db
from models.base import Base
from models.user import User
from services.auth import hash_password


def test_known_prose_sites_default_to_novel_only_when_category_is_omitted(monkeypatch):
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
            db.add(User(username="category-reader", hashed_password=hash_password("reader-long-password")))
            db.commit()
        client = TestClient(main.app)
        login = client.post("/auth/login", json={"username": "category-reader", "password": "reader-long-password"})
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        sites = (
            "https://freewebnovel.com/novel/example-book",
            "https://www.webnovel.com/book/35844914500239705",
            "https://www.royalroad.com/fiction/107917/old-title",
            "https://www.scribblehub.com/series/2388343/old-title/",
        )
        for url in sites:
            response = client.post("/items", json={"url": url}, headers=headers)
            assert response.status_code == 201, response.text
            assert response.json()["category"] == "Novel"

        explicit = client.post("/items", json={"url": sites[0], "category": "Light Novel"}, headers=headers)
        assert explicit.status_code == 201 and explicit.json()["category"] == "Light Novel"
        none = client.post("/items", json={"url": sites[1], "category": None}, headers=headers)
        assert none.status_code == 201 and none.json()["category"] is None
        other = client.post("/items", json={"url": "https://comix.to/title/39w1n-example"}, headers=headers)
        assert other.status_code == 201 and other.json()["category"] is None
    finally:
        main.app.dependency_overrides.clear()
