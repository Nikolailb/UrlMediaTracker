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
DEFAULT_CHECK_INTERVAL_MIN=60
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

> On first startup the app also calls `Base.metadata.create_all` as a fallback
> so the server can boot without running migrations manually. In production,
> running `alembic upgrade head` explicitly before starting the server is
> recommended — it ensures all schema changes are applied in the correct order
> and lets you catch migration errors before traffic starts.

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
    chapter_checker.py    # HTTP probing strategy + ABC for extensibility
    scheduler.py          # APScheduler background checks
  alembic/              # Database migrations
```

## Adding a new check strategy

1. Create a class that inherits `BaseCheckStrategy` in `services/chapter_checker.py`
2. Implement `find_latest_chapter(current_latest, url_template, config) -> str | None`
3. Register it in `STRATEGY_REGISTRY` with a string key
4. Add the key as a value to the `CheckStrategy` enum in `models/item.py` and generate a migration
