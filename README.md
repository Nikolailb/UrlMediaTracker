# UrlMediaTracker

A self-hosted reading queue for serialized novels, comics, manga, and webtoons. Add a series or chapter URL, check for new chapters, resume reading, and keep personal progress. It targets a household and modest hardware such as a Raspberry Pi.

## Project contract

[SPEC.md](SPEC.md) contains testable requirements, [ARCHITECTURE.md](ARCHITECTURE.md) the components and deployment, [DATA_MODEL.md](DATA_MODEL.md) the storage model, [ROADMAP.md](ROADMAP.md) reviewable milestones, [DECISIONS.md](DECISIONS.md) product tradeoffs, and [AGENTS.md](AGENTS.md) future coding rules. Requirement IDs are stable. Roadmap features are not deployed features until marked complete.

## Current repository and setup

- `backend/`: FastAPI, SQLAlchemy, Alembic, APScheduler, SQLite.
- `frontend/`: React, TypeScript, Vite, Tailwind CSS, TanStack Query.
- `backend/tests/`: backend behavior tests.

Use Python 3.12 and Node.js 24. Create `backend/env`, install `backend/requirements.txt` and `pytest`, then run `alembic upgrade head` from `backend`. Run `python -m admin_bootstrap` from `backend` to set the first admin password; existing entries are assigned to that account. Run `npm ci` at the root and in `frontend`. `npm run dev` starts Uvicorn at `http://localhost:8000` and Vite at `http://localhost:5173`; API docs are at `/docs`. Copy `backend/.env.example` to `backend/.env` as needed. Run backend tests from `backend` with `python -m pytest tests`; run `npm --prefix frontend run build` and `npm --prefix frontend run lint`.

Sign in to your own reading queue. An admin can create expiring invite links and select a member's library. Safe view starts on for each sign-in; reveal sensitive entries deliberately before editing them. Add a series or chapter URL to inspect the checking method and site access before saving. Switch between table and cover cards. Choose Images, Words, or Unread in the filter picker, or save your own combination of categories, unread, and active status. Use the next chapter and mark-read actions. ZIP export requires password confirmation and includes sensitive entries and covers; import deduplicates within the selected account. Legacy JSON import/export remains available.

## Raspberry Pi

KeiHub manages the separate tracker Compose project, Caddy route, CI-gated updater, and encrypted restic backup. The database is `/srv/keihub/data/tracker/main.db` and covers are in `/srv/keihub/data/tracker/covers`; they must be backed up and restored together. Install the matching KeiHub tracker Compose, production requirements, and updater changes before publishing this schema upgrade. Consult `D:\Projects\Web\KeiHub\OPERATIONS.md` for deployment and restore. Preserve existing records and a verified backup before migration. The service is intended for LAN and router-VPN access without mandatory cloud services.
