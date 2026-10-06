"""REQ-009: preset defaults, ownership, CRUD, and archive portability."""
import io
import json
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import get_db
from models.base import Base
from models.user import User
from services.auth import hash_password
import main


def test_presets_are_scoped_to_selected_library_and_portable(monkeypatch):
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
        with session_factory() as db:
            admin = User(username="admin", is_admin=True, hashed_password=hash_password("admin-long-password"))
            reader = User(username="reader", hashed_password=hash_password("reader-long-password"))
            db.add_all([admin, reader])
            db.commit()
            admin_id = admin.id
            reader_id = reader.id

        admin_client = TestClient(main.app)
        assert admin_client.get("/filter-presets").status_code == 401
        login = admin_client.post("/auth/login", json={"username": "admin", "password": "admin-long-password"})
        csrf = login.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "X-Library-User": reader_id}
        defaults = admin_client.get("/filter-presets", headers=headers).json()
        assert [row["name"] for row in defaults] == ["Images", "Words", "Unread"]
        assert defaults[0]["categories"] == ["Manhwa", "Manhua", "Manga", "Webtoon", "Pornhwa", "Comic", "Anime"]
        assert defaults[1]["categories"] == ["Novel", "Light Novel"]
        assert defaults[2]["unread_only"] is True

        payload = {"name": "Weekend", "categories": ["Manga", "Webtoon"], "unread_only": True, "include_inactive": False, "sort_key": "title", "sort_dir": "asc"}
        response = admin_client.post("/filter-presets", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        preset_id = response.json()["id"]
        assert len(admin_client.get("/filter-presets").json()) == 3
        assert len(admin_client.get("/filter-presets", headers=headers).json()) == 4
        assert admin_client.put(f"/filter-presets/{preset_id}", json={**payload, "name": "WEEKEND"}, headers=headers).status_code == 200
        assert admin_client.post("/filter-presets", json={**payload, "name": "weekend"}, headers=headers).status_code == 409
        assert admin_client.post("/filter-presets", json={**payload, "categories": ["Unknown"]}, headers=headers).status_code == 422
        assert admin_client.post("/filter-presets", json={**payload, "sort_key": "unknown"}, headers=headers).status_code == 422
        assert admin_client.delete("/filter-presets/images", headers=headers).status_code == 404

        reader_client = TestClient(main.app)
        reader_login = reader_client.post("/auth/login", json={"username": "reader", "password": "reader-long-password"})
        reader_csrf = reader_login.json()["csrf_token"]
        assert reader_client.get("/filter-presets").json()[-1]["name"] == "WEEKEND"
        assert reader_client.put(f"/filter-presets/{preset_id}", json=payload, headers={"X-CSRF-Token": reader_csrf, "X-Library-User": admin_id}).status_code == 403

        exported = admin_client.post("/archive/export", json={"password": "admin-long-password"}, headers=headers)
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            saved = json.loads(archive.read("presets.json"))
        assert saved == [{"name": "WEEKEND", "categories": ["Manga", "Webtoon"], "unread_only": True, "include_inactive": False, "sort_key": "title", "sort_dir": "asc"}]
        imported = admin_client.post("/archive/import", files={"file": ("account.zip", exported.content, "application/zip")}, headers=headers)
        assert imported.status_code == 201
        assert len(admin_client.get("/filter-presets", headers=headers).json()) == 4
        imported_to_admin = admin_client.post(
            "/archive/import",
            files={"file": ("account.zip", exported.content, "application/zip")},
            headers={"X-CSRF-Token": csrf},
        )
        assert imported_to_admin.status_code == 201
        assert admin_client.get("/filter-presets").json()[-1]["name"] == "WEEKEND"
        assert admin_client.delete(f"/filter-presets/{preset_id}", headers=headers).status_code == 204
        assert len(admin_client.get("/filter-presets", headers=headers).json()) == 3
    finally:
        main.app.dependency_overrides.clear()
