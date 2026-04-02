# Smart Bookmark & Chapter Tracker

A fullstack web application for tracking progress across serialized online content — manga, web novels, and blogs.

## Quick start

```powershell
npm run dev
```

This starts both the backend and frontend concurrently:
- **Backend** → http://localhost:8000 (FastAPI + SQLite)
- **Frontend** → http://localhost:5173 (React + Vite)

### Prerequisites

- Python 3.11+ with the `backend/env/` virtualenv already set up
- Node.js 18+

## Repository structure

```
progress_tracking_service/
  backend/    # FastAPI application — see backend/README.md
  frontend/   # React + TypeScript — see frontend/README.md
  package.json  # Root scripts (dev, dev:backend, dev:frontend)
```

## Available scripts (root)

| Command | Description |
|---------|-------------|
| `npm run dev` | Start backend + frontend together |
| `npm run dev:backend` | Start FastAPI only |
| `npm run dev:frontend` | Start Vite only |

## Core features

- **Smart pattern detection** — paste any chapter URL and the system automatically extracts the template (e.g. `chapter-{n}`), with manual regex override for edge cases
- **Progress tracking** — current vs latest chapter with a visual indicator
- **Automated update checks** — periodic background checks using configurable intervals per item
- **Sortable & filterable list** — search, filter by status or unread, sort by any column
- **Responsive UI** — table layout on desktop, card grid on mobile
- **Dark mode** — system default, user-overridable via header toggle

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend API | Python · FastAPI · Pydantic · SQLAlchemy |
| Database | SQLite (dev) → PostgreSQL-ready |
| Migrations | Alembic |
| Background jobs | APScheduler |
| Frontend | React 19 · TypeScript · Vite |
| Styling | Tailwind CSS v3 · CSS variables |
| Data fetching | TanStack Query v5 |
