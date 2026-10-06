# Chapter Tracker — Backend

FastAPI + SQLAlchemy + SQLite backend for the Smart Bookmark & Chapter Tracker.

## Requirements

- Python 3.11+
- The `env/` virtual environment is already set up with all dependencies.

## Quick start

```powershell
# From repo root:
npm run dev:backend

# Or directly from this directory:
.\env\Scripts\uvicorn main:app --reload
```

The API will be available at **http://localhost:8000**.  
Interactive docs: **http://localhost:8000/docs**

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```env
DATABASE_URL=sqlite:///./tracker.db
DEFAULT_CHECK_INTERVAL_MIN=360
PROBE_REQUEST_TIMEOUT=10.0
PROBE_DELAY_SECONDS=1.0
MAX_PROBE_AHEAD=10
```

## Database migrations (Alembic)

Alembic tracks every schema change as a versioned Python script stored in
`alembic/versions/`. Each script has an `upgrade()` and a `downgrade()` function
so you can move the database forward or backward to any revision.

### How Alembic tracks state

Alembic stores the **current revision ID** in an `alembic_version` table inside
your database. When you run `upgrade head` it applies every unapplied migration
in dependency order. When you run `downgrade`, it calls the `downgrade()` function
of the current revision and rolls back one step (or more if you specify a target).

### Common workflows

**First-time setup — create the database from scratch:**
```powershell
.\env\Scripts\alembic upgrade head
```
This runs all migrations in order. On a fresh database that means creating all
tables defined in `alembic/versions/`.

**Add a new column to `TrackedItem`:**
1. Edit `models/item.py` — add the column, e.g.:
   ```python
   notes: Mapped[str | None] = mapped_column(Text, nullable=True)
   ```
2. Generate the migration script (Alembic diffs the ORM models against the DB):
   ```powershell
   .\env\Scripts\alembic revision --autogenerate -m "add_notes_to_tracked_items"
   ```
3. Review the generated file in `alembic/versions/` — autogenerate is usually
   correct but always check for dropped indices or renamed columns.
4. Apply it:
   ```powershell
   .\env\Scripts\alembic upgrade head
   ```

**Rename a column (manual migration):**
Autogenerate cannot detect renames — it would drop the old column and add a new
one, losing data. Write the migration by hand instead:
```python
def upgrade() -> None:
    op.alter_column("tracked_items", "old_name", new_column_name="new_name")

def downgrade() -> None:
    op.alter_column("tracked_items", "new_name", new_column_name="old_name")
```

**Check which revision the database is at:**
```powershell
.\env\Scripts\alembic current
```

**Show the full migration history:**
```powershell
.\env\Scripts\alembic history --verbose
```

**Roll back the last migration:**
```powershell
.\env\Scripts\alembic downgrade -1
```

**Roll back to a specific revision (use the ID shown by `alembic history`):**
```powershell
.\env\Scripts\alembic downgrade df12640c1aa2
```

**Stamp an existing database without running migrations** (useful if you created
the DB with `create_all` before adopting Alembic):
```powershell
.\env\Scripts\alembic stamp head
```

Run `alembic upgrade head` before starting the server. The app does not create or
alter schema automatically at startup. Do not use `create_all` to upgrade an
existing library. See root `README.md` for the guarded local FlareSolverr
preview (REQ-015).

## API overview

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/items` | Add a tracked item (auto-detects chapter pattern) |
| `GET` | `/items` | List all items (`?active_only=true`) |
| `GET` | `/items/{id}` | Get one item |
| `PATCH` | `/items/{id}` | Update title, regex, interval, current chapter |
| `DELETE` | `/items/{id}` | Delete item + history |
| `GET` | `/items/{id}/next` | URL of the next unread chapter |
| `POST` | `/items/{id}/mark-read` | Advance `current_chapter` |
| `POST` | `/items/{id}/check` | Probe for new chapters (one item) |
| `POST` | `/items/check-all` | Probe all active items |
| `POST` | `/patterns/detect` | Preview pattern detection without saving |
| `POST` | `/users` | Create a user (stub) |
| `GET` | `/users/{id}` | Get a user (stub) |
| `GET` | `/health` | Health check |

## Project structure

```
backend/
  main.py               # FastAPI app factory + lifespan
  config.py             # Pydantic Settings
  database.py           # SQLAlchemy engine + session dependency
  models/               # ORM models (User, TrackedItem, ChapterCheckLog)
  schemas/              # Pydantic request/response schemas
  routers/              # FastAPI routers (items, users, patterns)
  services/
    pattern_detection.py  # URL pattern detection (3-strategy cascade)
    checking/
      orchestrator.py     # check persistence
      selector.py         # strategy selection
      http.py             # guarded direct fetch and diagnostics
      browser.py          # optional allowlisted FlareSolverr transport
      sites/freewebnovel.py  # series-page ToC adapter
      strategies/toc.py  # generic ToC parser
      strategies/probe.py  # incremental URL probing
    scheduler.py          # APScheduler background checks
  alembic/              # Database migrations
```

## Adding a new check strategy

Add a site adapter in its own `services/checking/sites/<site>.py` file and select it in `checking/selector.py`. A generic ToC rule belongs in `checking/strategies/toc.py`; URL probing belongs in `checking/strategies/probe.py`. Return a typed `CheckResult`, with `UNCHANGED` or `BLOCKED` terminal, and add a fixture for the site's own chapter links plus unrelated links. Only site and ToC checkers may opt into `checking/browser.py` after a direct challenge or connection/timeout failure; never call it from incremental probing or diagnostics. Any browser service needs private access and public-only egress before host activation. See REQ-005, REQ-007, and REQ-015.
