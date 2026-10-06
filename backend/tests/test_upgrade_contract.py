import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.base import Base
from models.item import TrackedItem
from models.user import LoginSession, User
from routers.items import _visible_query
from services.auth import Identity
from services.checking import selector as site_checker, http as source_http
from services.checking.selector import CheckResult, freewebnovel_series_url, parse_freewebnovel
import pytest
import io
import json
import zipfile
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from services.checking.orchestrator import CheckerConfig, check_item
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from database import get_db
import main
from services.auth import hash_password


EXAMPLE = "https://freewebnovel.com/novel/harem-system-in-a-fantasy-world"
HTML = '''<meta property="og:title" content="Harem System In A fantasy World">
<meta property="og:novel:lastest_chapter_name" content="Chapter 644: New">
<meta property="og:novel:lastest_chapter_url" content="https://freewebnovel.com/novel/harem-system-in-a-fantasy-world/chapter-644">
<div id="indexListPage" data-total-chapters="644"><div class="m-newest1">
<a href="/novel/harem-system-in-a-fantasy-world/chapter-644">Chapter 644: New</a>
<a href="/novel/harem-system-in-a-fantasy-world/chapter-643">Chapter 643</a></div>
<div class="col-slide"><a href="/novel/another-story/chapter-5682">Chapter 5682</a></div></div>'''


def test_freewebnovel_is_scoped_to_requested_series():
    assert freewebnovel_series_url(EXAMPLE + "/chapter-235") == EXAMPLE
    parsed = parse_freewebnovel(HTML, EXAMPLE)
    assert parsed["chapter"] == "644"
    assert parsed["chapter_url"] == EXAMPLE + "/chapter-644"


def test_private_source_is_rejected_before_fetch():
    with pytest.raises(site_checker.UnsafeSource):
        asyncio.run(site_checker.safe_get("http://127.0.0.1/admin"))


def test_site_checker_unchanged_does_not_probe(monkeypatch):
    async def fake_get(_url, **_kwargs):
        return 200, EXAMPLE, HTML.encode(), {}
    monkeypatch.setattr(site_checker, "safe_get", fake_get)
    item = SimpleNamespace(series_url=EXAMPLE, original_url=EXAMPLE,
                           strategy_override=None, latest_chapter="644", current_chapter="640")
    result = asyncio.run(site_checker.check_source(item, CheckerConfig()))
    assert result.outcome == "UNCHANGED"
    assert result.method == "FREEWEBNOVEL"


def test_unrelated_toc_links_do_not_fall_through_to_probe(monkeypatch):
    async def fake_get(_url, **_kwargs):
        return 200, "https://example.com/series", b'<a href="https://example.com/other/chapter-5682">Chapter 5682</a>', {}
    async def unexpected_probe(*args, **kwargs):
        raise AssertionError("Generic probe should not run")
    monkeypatch.setattr(site_checker, "safe_get", fake_get)
    monkeypatch.setattr("services.checking.strategies.probe.IncrementalProbeStrategy.find_latest_chapter", unexpected_probe)
    item = SimpleNamespace(series_url=None, original_url="https://example.com/series",
                           strategy_override=None, check_strategy="TOC_THEN_PROBE",
                           toc_url="https://example.com/series",
                           url_template="https://example.com/series/chapter-{n}",
                           latest_chapter="644", current_chapter="640")
    result = asyncio.run(site_checker.check_source(item, CheckerConfig()))
    assert result.outcome == "FAILED"


def test_probe_challenge_is_blocked_instead_of_unchanged(monkeypatch):
    from services.checking.strategies import probe as probe_checker

    class Response:
        status_code = 403
        headers = {"cf-ray": "fixture"}
        url = "https://example.com/series/chapter-645"
        history = []

        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def aiter_bytes(self, **_kwargs):
            yield b"checking your browser cf-chl"

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        def stream(self, *_args): return Response()

    monkeypatch.setattr(probe_checker.httpx, "AsyncClient", lambda **_kwargs: Client())
    item = SimpleNamespace(series_url=None, original_url="https://example.com/series/chapter-640",
                           strategy_override="INCREMENTAL_PROBE", check_strategy="INCREMENTAL_PROBE",
                           toc_url=None, url_template="https://example.com/series/chapter-{n}",
                           latest_chapter="640", current_chapter="640")
    result = asyncio.run(site_checker.check_source(item, CheckerConfig()))
    assert result.outcome == "BLOCKED"


def test_site_diagnostic_distinguishes_challenge_and_http_error(monkeypatch):
    async def challenge(_url, **_kwargs):
        return 403, "https://example.com/", b"cf-chl checking your browser", {"cf-ray": "fixture"}
    monkeypatch.setattr(source_http, "safe_get", challenge)
    assert asyncio.run(source_http.diagnose_url("https://example.com"))["state"] == "LIKELY_CLOUDFLARE"

    async def ordinary_error(_url, **_kwargs):
        return 404, "https://example.com/", b"missing", {}
    monkeypatch.setattr(source_http, "safe_get", ordinary_error)
    assert asyncio.run(source_http.diagnose_url("https://example.com"))["state"] == "HTTP_ERROR"


def test_sensitive_and_other_user_items_are_filtered():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="reader", is_admin=False)
        other = User(username="other", is_admin=False)
        db.add_all([owner, other])
        db.flush()
        db.add_all([
            TrackedItem(original_url="https://example.com/a", user_id=owner.id, is_sensitive=False),
            TrackedItem(original_url="https://example.com/b", user_id=owner.id, is_sensitive=True),
            TrackedItem(original_url="https://example.com/c", user_id=other.id, is_sensitive=False),
        ])
        db.commit()
        identity = Identity(owner, LoginSession(safe_view_enabled=True), owner.id)
        assert [item.original_url for item in _visible_query(db, identity).all()] == ["https://example.com/a"]
        identity.session.safe_view_enabled = False
        assert len(_visible_query(db, identity).all()) == 2


def test_suspicious_increase_is_held(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="reader")
        db.add(owner)
        db.flush()
        item = TrackedItem(original_url=EXAMPLE, series_url=EXAMPLE, user_id=owner.id,
                           latest_chapter="644", current_chapter="640")
        db.add(item)
        db.commit()
        async def fake_check(_item, _config):
            return CheckResult("NEW", "FREEWEBNOVEL", "5682", EXAMPLE + "/chapter-5682")
        monkeypatch.setattr(site_checker, "check_source", fake_check)
        log = asyncio.run(check_item(item, db, CheckerConfig()))
        assert log.outcome == "PENDING"
        assert item.latest_chapter == "644"
        assert item.pending_latest_chapter == "5682"


def test_incomparable_label_is_held_for_review(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="reader")
        db.add(owner); db.flush()
        item = TrackedItem(original_url="https://example.com/series", user_id=owner.id,
                           latest_chapter="183b", current_chapter="183a")
        db.add(item); db.commit()
        async def fake_check(_item, _config):
            return CheckResult("NEW", "TOC_SCRAPER", "184a", "https://example.com/series/chapter-184a")
        monkeypatch.setattr(site_checker, "check_source", fake_check)
        log = asyncio.run(check_item(item, db, CheckerConfig()))
        assert log.outcome == "PENDING"
        assert item.latest_chapter == "183b"
        assert item.pending_latest_chapter == "184a"


def test_api_account_isolation_and_safe_view(monkeypatch):
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
            alice = User(username="alice", hashed_password=hash_password("alice-long-password"))
            bob = User(username="bob", hashed_password=hash_password("bob-long-password"))
            db.add_all([alice, bob]); db.flush()
            own = TrackedItem(original_url="https://example.com/own", user_id=alice.id,
                              toc_url="https://example.com/own", current_chapter="12", latest_chapter="15",
                              first_chapter_url="https://example.com/own/chapter-1",
                              latest_chapter_url="https://example.com/own/chapter-15")
            sensitive = TrackedItem(original_url="https://example.com/sensitive", user_id=alice.id, is_sensitive=True)
            foreign = TrackedItem(original_url="https://example.com/foreign", user_id=bob.id)
            db.add_all([own, sensitive, foreign]); db.commit()
            own_id, foreign_id, sensitive_id = own.id, foreign.id, sensitive.id
        client = TestClient(main.app)
        assert client.get("/items").status_code == 401
        assert client.post("/tools/toc-preview", json={"url": "https://example.com/own"}).status_code in {401, 403}
        login = client.post("/auth/login", json={"username": "alice", "password": "alice-long-password"})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        assert len(client.get("/items").json()) == 1
        assert client.get(f"/items/{foreign_id}").status_code == 404
        assert client.get(f"/items/{sensitive_id}").status_code == 404
        assert client.patch(f"/items/{foreign_id}", json={"title": "stolen"}, headers={"X-CSRF-Token": csrf}).status_code == 404
        assert client.patch(f"/items/{own_id}", json={"is_sensitive": True}, headers={"X-CSRF-Token": csrf}).status_code == 409
        assert client.get(f"/items/{sensitive_id}/history").status_code == 404
        assert client.get(f"/items/{sensitive_id}/cover").status_code == 404
        assert client.get(f"/items/{sensitive_id}/next").status_code == 404
        fallback = client.get(f"/items/{own_id}/next").json()
        assert (fallback["destination"], fallback["next_chapter"], fallback["next_url"]) == (
            "TOC", "13", "https://example.com/own")
        assert client.patch(f"/items/{own_id}", json={"current_chapter": "14"},
                            headers={"X-CSRF-Token": csrf}).status_code == 200
        direct = client.get(f"/items/{own_id}/next").json()
        assert (direct["destination"], direct["next_url"]) == (
            "CHAPTER", "https://example.com/own/chapter-15")
        archive_response = client.post("/archive/export", json={"password": "alice-long-password"}, headers={"X-CSRF-Token": csrf})
        assert archive_response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
            exported = json.loads(archive.read("items.json"))
        assert len(exported) == 2  # Explicit full export includes hidden entries.
        imported = client.post("/archive/import", files={"file": ("account.zip", archive_response.content, "application/zip")}, headers={"X-CSRF-Token": csrf})
        assert imported.status_code == 201
        assert imported.json() == {"created": 0, "skipped": 2}
        bad_buffer = io.BytesIO()
        with zipfile.ZipFile(bad_buffer, "w") as bad_zip:
            bad_zip.writestr("manifest.json", json.dumps({"format": "urlmediatracker-account", "version": 1, "includes_sensitive": True}))
            bad_zip.writestr("items.json", json.dumps([
                {"original_url": "https://example.com/new"},
                {"original_url": "https://example.com/invalid", "cover": "covers/missing.jpg"},
            ]))
        invalid = client.post("/archive/import", files={"file": ("bad.zip", bad_buffer.getvalue(), "application/zip")}, headers={"X-CSRF-Token": csrf})
        assert invalid.status_code == 422
        assert len(client.get("/items").json()) == 1
        assert client.post("/auth/safe-view?enabled=false", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert len(client.get("/items").json()) == 2
        assert client.get(f"/items/{sensitive_id}").status_code == 200
        assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert client.get("/items").status_code == 401
        again = client.post("/auth/login", json={"username": "alice", "password": "alice-long-password"})
        assert again.json()["safe_view_enabled"] is True
        assert len(client.get("/items").json()) == 1
    finally:
        main.app.dependency_overrides.clear()


def test_admin_invite_and_explicit_library_selection(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def session_factory(): return Session(engine)
    def test_db():
        with session_factory() as db: yield db
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    main.app.dependency_overrides[get_db] = test_db
    try:
        with session_factory() as db:
            admin = User(username="admin", is_admin=True, hashed_password=hash_password("admin-long-password"))
            reader = User(username="reader", hashed_password=hash_password("reader-long-password"))
            db.add_all([admin, reader]); db.flush()
            db.add(TrackedItem(original_url="https://example.com/reader", user_id=reader.id))
            db.commit()
            reader_id = reader.id
        admin_client = TestClient(main.app)
        login = admin_client.post("/auth/login", json={"username": "admin", "password": "admin-long-password"})
        csrf = login.json()["csrf_token"]
        assert admin_client.get("/items").json() == []
        assert len(admin_client.get("/items", headers={"X-Library-User": reader_id}).json()) == 1
        invite = admin_client.post("/auth/invites", headers={"X-CSRF-Token": csrf})
        assert invite.status_code == 200
        token = invite.json()["token"]
        new_client = TestClient(main.app)
        accepted = new_client.post("/auth/accept-invite", json={"token": token, "username": "new-reader", "password": "new-reader-password"})
        assert accepted.status_code == 200
        again = TestClient(main.app).post("/auth/accept-invite", json={"token": token, "username": "other-reader", "password": "other-reader-password"})
        assert again.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


def test_legacy_migration_and_bootstrap_preserve_progress(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "legacy.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    alembic = [sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"), "upgrade"]
    subprocess.run([*alembic, "d7e8f9a0b1c2"], cwd=backend, env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        db.execute("""INSERT INTO tracked_items
            (id, original_url, pattern_source, check_strategy, current_chapter, latest_chapter,
             check_interval_min, is_active, consecutive_failures, created_at, updated_at)
            VALUES (?, ?, 'AUTO', 'INCREMENTAL_PROBE', '640', '644', 60, 1, 0,
                    '2026-01-01', '2026-01-01')""", ("legacy-id", EXAMPLE))
    subprocess.run([*alembic, "head"], cwd=backend, env=env, check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "admin_bootstrap", "--password-stdin"],
                   input="a-long-test-password\n", text=True, cwd=backend, env=env,
                   check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        row = db.execute("SELECT id, current_chapter, latest_chapter, user_id FROM tracked_items").fetchone()
        admin = db.execute("SELECT id FROM users WHERE is_admin = 1").fetchone()
    assert row == ("legacy-id", "640", "644", admin[0])


def test_cover_is_decoded_and_stored_locally(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image
    from services.covers import cover_path, save_cover
    from config import settings

    monkeypatch.setattr(settings, "COVER_DIR", str(tmp_path))
    image = Image.new("RGB", (4, 4), (100, 20, 20))
    source = io.BytesIO()
    image.save(source, format="PNG")
    name = save_cover(source.getvalue())
    assert cover_path(name).is_file()
    with Image.open(cover_path(name)) as saved:
        assert saved.format == "JPEG"
        assert saved.size == (4, 4)
    with pytest.raises(ValueError):
        save_cover(b"not an image")


def test_cover_url_fetch_is_guarded_and_authorized(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image
    from config import settings
    from routers import items as item_routes

    monkeypatch.setattr(settings, "COVER_DIR", str(tmp_path / "covers"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def session_factory(): return Session(engine)
    def test_db():
        with session_factory() as db: yield db
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    main.app.dependency_overrides[get_db] = test_db
    try:
        with session_factory() as db:
            owner = User(username="cover-owner", hashed_password=hash_password("cover-owner-password"))
            other = User(username="cover-other", hashed_password=hash_password("cover-other-password"))
            db.add_all([owner, other]); db.flush()
            item = TrackedItem(original_url="https://example.com/series", user_id=owner.id)
            db.add(item); db.commit()
            item_id = item.id
        client = TestClient(main.app)
        csrf = client.post("/auth/login", json={"username": "cover-owner", "password": "cover-owner-password"}).json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        denied = client.post(f"/items/{item_id}/cover-url", json={"url": "http://127.0.0.1/cover.png"}, headers=headers)
        assert denied.status_code == 422
        assert client.get(f"/items/{item_id}").json()["cover_filename"] is None

        image = Image.new("RGB", (4, 4), (50, 100, 150))
        raw = io.BytesIO(); image.save(raw, format="PNG")
        async def fake_get(url, **kwargs):
            assert url == "https://images.example.com/cover.png"
            assert kwargs["max_bytes"] > len(raw.getvalue())
            return 200, url, raw.getvalue(), {"content-type": "image/png"}
        monkeypatch.setattr(item_routes, "safe_get", fake_get)
        added = client.post(f"/items/{item_id}/cover-url", json={"url": "https://images.example.com/cover.png"}, headers=headers)
        assert added.status_code == 200, added.text
        assert client.get(f"/items/{item_id}/cover").content.startswith(b"\xff\xd8")

        other_client = TestClient(main.app)
        other_csrf = other_client.post("/auth/login", json={"username": "cover-other", "password": "cover-other-password"}).json()["csrf_token"]
        assert other_client.post(f"/items/{item_id}/cover-url", json={"url": "https://images.example.com/cover.png"}, headers={"X-CSRF-Token": other_csrf}).status_code == 404
    finally:
        main.app.dependency_overrides.clear()


def test_archive_round_trip_includes_sensitive_cover(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image
    from config import settings

    monkeypatch.setattr(settings, "COVER_DIR", str(tmp_path / "covers"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def session_factory(): return Session(engine)
    def test_db():
        with session_factory() as db: yield db
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    main.app.dependency_overrides[get_db] = test_db
    try:
        with session_factory() as db:
            alice = User(username="alice-cover", hashed_password=hash_password("alice-cover-password"))
            bob = User(username="bob-cover", hashed_password=hash_password("bob-cover-password"))
            db.add_all([alice, bob]); db.flush()
            item = TrackedItem(original_url="https://example.com/cover-series", user_id=alice.id,
                               is_sensitive=True, current_chapter="12", latest_chapter="15", note="private note",
                               latest_chapter_url="https://example.com/cover-series/chapter-15",
                               first_chapter_url="https://example.com/cover-series/chapter-1",
                               preferred_group="team-a",
                               toc_examples_json='["https://example.com/cover-series/chapter-15"]',
                               toc_row_class="chapter-row")
            db.add(item); db.commit()
            item_id = item.id
        alice_client = TestClient(main.app)
        alice_login = alice_client.post("/auth/login", json={"username": "alice-cover", "password": "alice-cover-password"}).json()
        alice_csrf = {"X-CSRF-Token": alice_login["csrf_token"]}
        alice_client.post("/auth/safe-view?enabled=false", headers=alice_csrf)
        image = Image.new("RGB", (4, 4), (20, 100, 20))
        raw = io.BytesIO(); image.save(raw, format="PNG")
        assert alice_client.post(f"/items/{item_id}/cover", files={"file": ("cover.png", raw.getvalue(), "image/png")}, headers=alice_csrf).status_code == 200
        archive = alice_client.post("/archive/export", json={"password": "alice-cover-password"}, headers=alice_csrf)
        assert archive.status_code == 200
        bob_client = TestClient(main.app)
        bob_login = bob_client.post("/auth/login", json={"username": "bob-cover", "password": "bob-cover-password"}).json()
        bob_csrf = {"X-CSRF-Token": bob_login["csrf_token"]}
        imported = bob_client.post("/archive/import", files={"file": ("account.zip", archive.content, "application/zip")}, headers=bob_csrf)
        assert imported.json() == {"created": 1, "skipped": 0}
        assert bob_client.get("/items").json() == []
        bob_client.post("/auth/safe-view?enabled=false", headers=bob_csrf)
        restored = bob_client.get("/items").json()[0]
        assert (restored["current_chapter"], restored["latest_chapter"], restored["note"], restored["is_sensitive"]) == ("12", "15", "private note", True)
        assert restored["latest_chapter_url"] == "https://example.com/cover-series/chapter-15"
        assert restored["first_chapter_url"] == "https://example.com/cover-series/chapter-1"
        assert restored["preferred_group"] == "team-a"
        assert restored["toc_example_urls"] == ["https://example.com/cover-series/chapter-15"]
        assert restored["toc_row_class"] == "chapter-row"
        assert bob_client.get(f"/items/{restored['id']}/cover").content.startswith(b"\xff\xd8")
    finally:
        main.app.dependency_overrides.clear()
