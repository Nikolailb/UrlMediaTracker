"""REQ-022: lifecycle, polling, portability, and migration."""
import asyncio
import io
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

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
from services.checking.selector import CheckResult
from services.item_status import caught_up


def test_finish_requires_comparable_known_progress():
    assert caught_up("3", "3")
    assert not caught_up("Volume 3", "Volume 3")
    assert not caught_up("NaN", "3")


def test_scheduler_only_checks_ongoing(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def session_factory():
        return Session(engine)

    with session_factory() as db:
        for value in ("ONGOING", "PAUSED", "COMPLETED", "FINISHED"):
            db.add(TrackedItem(original_url=f"https://example.com/{value}", status=value,
                               is_active=value == "ONGOING", check_interval_min=360))
        db.commit()

    checked = []

    async def fake_check(item, _db, **_kwargs):
        checked.append(item.status)

    monkeypatch.setattr("database.SessionLocal", session_factory)
    monkeypatch.setattr("services.checking.orchestrator.check_item", fake_check)
    from services.scheduler import run_due_checks
    asyncio.run(run_due_checks())
    assert checked == ["ONGOING"]


def test_status_migration_preserves_legacy_pause_and_presets(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "status.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    alembic = [sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"), "upgrade"]
    subprocess.run([*alembic, "20261006_0004"], cwd=backend, env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        for value in (0, 1):
            db.execute("""INSERT INTO tracked_items
                (id, original_url, pattern_source, check_strategy, check_interval_min,
                 is_active, consecutive_failures, created_at, updated_at)
                VALUES (?, ?, 'AUTO', 'INCREMENTAL_PROBE', 360, ?, 0, '2026-01-01', '2026-01-01')""",
                (f"item-{value}", f"https://example.com/{value}", value))
            db.execute("""INSERT INTO filter_presets
                (id, user_id, name, name_key, categories_json, unread_only,
                 include_inactive, sort_key, sort_dir, created_at, updated_at)
                VALUES (?, 'legacy-owner', ?, ?, '[]', 0, ?, 'title', 'asc', '2026-01-01', '2026-01-01')""",
                (f"preset-{value}", f"Preset {value}", f"preset {value}", value))
    subprocess.run([*alembic, "head"], cwd=backend, env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT id, status FROM tracked_items ORDER BY id").fetchall() == [
            ("item-0", "PAUSED"), ("item-1", "ONGOING")]
        presets = db.execute("SELECT id, statuses_json FROM filter_presets ORDER BY id").fetchall()
        assert json.loads(presets[0][1]) == ["ONGOING", "COMPLETED"]
        assert set(json.loads(presets[1][1])) == {"ONGOING", "PAUSED", "COMPLETED", "FINISHED"}


def test_status_transitions_checks_and_archive(monkeypatch):
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
            reader = User(username="status-reader", hashed_password=hash_password("reader-long-password"))
            other = User(username="status-other", hashed_password=hash_password("other-long-password"))
            db.add_all([reader, other])
            db.flush()
            completed = TrackedItem(user_id=reader.id, original_url="https://example.com/completed",
                                    status="COMPLETED", is_active=False, current_chapter="2", latest_chapter="3")
            ongoing = TrackedItem(user_id=reader.id, original_url="https://example.com/ongoing",
                                  status="ONGOING", is_active=True, current_chapter="1", latest_chapter="3")
            paused = TrackedItem(user_id=reader.id, original_url="https://example.com/paused",
                                 status="PAUSED", is_active=False, current_chapter="1", latest_chapter="3")
            private = TrackedItem(user_id=other.id, original_url="https://example.com/private",
                                  status="COMPLETED", is_active=False, current_chapter="3", latest_chapter="3")
            db.add_all([completed, ongoing, paused, private])
            db.commit()
            completed_id, ongoing_id, paused_id, private_id = completed.id, ongoing.id, paused.id, private.id

        client = TestClient(main.app)
        csrf = client.post("/auth/login", json={"username": "status-reader", "password": "reader-long-password"}).json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        assert client.patch(f"/items/{private_id}", json={"status": "FINISHED"}, headers=headers).status_code == 404
        assert client.patch(f"/items/{ongoing_id}", json={"status": "FINISHED"}, headers=headers).status_code == 409
        assert client.patch(f"/items/{completed_id}", json={"status": "FINISHED"}, headers=headers).status_code == 409
        assert client.post(f"/items/{completed_id}/mark-read", json={"chapter": "3"}, headers=headers).status_code == 200
        finished = client.patch(f"/items/{completed_id}", json={"status": "FINISHED"}, headers=headers)
        assert finished.status_code == 200 and finished.json()["status"] == "FINISHED"
        async def unchanged(*_args, **_kwargs):
            return CheckResult("UNCHANGED", "TEST", chapter="3")
        monkeypatch.setattr("services.checking.selector.check_source", unchanged)
        assert client.post("/items/check-all", headers=headers).json()["checked"] == 1
        assert client.get("/items?active_only=true").json()[0]["id"] == ongoing_id
        assert client.post(f"/items/{paused_id}/check", headers=headers).json()["outcome"] == "UNSUPPORTED"

        async def new_chapter(*_args, **_kwargs):
            return CheckResult("NEW", "TEST", chapter="4", chapter_url="https://example.com/completed/4")
        monkeypatch.setattr("services.checking.selector.check_source", new_chapter)
        checked = client.post(f"/items/{completed_id}/check", headers=headers)
        assert checked.status_code == 200 and checked.json()["outcome"] == "NEW"
        updated = client.get(f"/items/{completed_id}").json()
        assert updated["status"] == "COMPLETED" and updated["latest_chapter"] == "4" and not updated["is_active"]
        assert client.post(f"/items/{completed_id}/mark-read", json={"chapter": "4"}, headers=headers).status_code == 200
        assert client.patch(f"/items/{completed_id}", json={"status": "FINISHED"}, headers=headers).status_code == 200
        assert client.post(f"/items/{completed_id}/mark-read", json={"chapter": "2"}, headers=headers).json()["status"] == "COMPLETED"

        exported = client.post("/archive/export", json={"password": "reader-long-password"}, headers=headers)
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert json.loads(archive.read("manifest.json"))["version"] == 2
            records = json.loads(archive.read("items.json"))
            assert {record["status"] for record in records} == {"ONGOING", "PAUSED", "COMPLETED"}
        assert client.post("/archive/import", files={"file": ("account.zip", exported.content)}, headers=headers).status_code == 201
        csrf_other = client.post("/auth/login", json={"username": "status-other", "password": "other-long-password"}).json()["csrf_token"]
        imported = client.post("/archive/import", files={"file": ("account.zip", exported.content)}, headers={"X-CSRF-Token": csrf_other})
        assert imported.status_code == 201 and imported.json()["created"] == 3
        statuses = {item["status"] for item in client.get("/items").json()}
        assert statuses == {"ONGOING", "PAUSED", "COMPLETED"}
    finally:
        main.app.dependency_overrides.clear()
