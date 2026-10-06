# UrlMediaTracker

A self-hosted reading queue for serialized novels, comics, manga, and webtoons. Add a series or chapter URL, check for new chapters, resume reading, and keep personal progress. It targets a household and modest hardware such as a Raspberry Pi.

## Project contract

[SPEC.md](SPEC.md) contains testable requirements, [ARCHITECTURE.md](ARCHITECTURE.md) the components and deployment, [DATA_MODEL.md](DATA_MODEL.md) the storage model, [ROADMAP.md](ROADMAP.md) reviewable milestones, [DECISIONS.md](DECISIONS.md) product tradeoffs, and [AGENTS.md](AGENTS.md) future coding rules. Requirement IDs are stable. Roadmap features are not deployed features until marked complete.

## Current repository and setup

- `backend/`: FastAPI, SQLAlchemy, Alembic, APScheduler, SQLite.
- `frontend/`: React, TypeScript, Vite, Tailwind CSS, TanStack Query.
- `backend/tests/`: backend behavior tests.

Use Python 3.12 and Node.js 24. Create `backend/env`, install `backend/requirements.txt` and `pytest`, then run `alembic upgrade head` from `backend`. Run `python -m admin_bootstrap` from `backend` to set the first admin password; existing entries are assigned to that account. Run `npm ci` at the root and in `frontend`. `npm run dev` starts Uvicorn at `http://localhost:8000` and Vite at `http://localhost:5173`; API docs are at `/docs`. Copy `backend/.env.example` to `backend/.env` as needed. Run backend tests from `backend` with `python -m pytest tests`; run `npm --prefix frontend run build` and `npm --prefix frontend run lint`.

Sign in to your own reading queue. An admin can create expiring invite links and select a member's library. Safe view starts on for each sign-in; reveal sensitive entries deliberately before editing them. Add a series or chapter URL, review the checking method and site access, and use detected details to fill editable fields if they look right. A chapter URL example, regex, generic ToC URL, and strategy override are under advanced checking options; an example chapter number is not treated as reading progress. Switch between table and cover cards. Select Images, Words, or Unread from wrapping desktop chips or the phone preset modal; open Filters to adjust the queue and save its full filter and sort state as a personal preset. Edit covers by upload or public image URL. Titles open the ToC or series; available chapter links and the next chapter action open reading pages. ZIP export requires password confirmation and includes sensitive entries and covers; import deduplicates within the selected account. Legacy JSON import/export remains available.

Edit item → Detection also accepts a chapter URL example next to the ToC URL. For predictable links such as `/chapter-63`, it updates the saved pattern without moving reading progress. A link such as `/8904631-chapter-63` has a separate numeric ID; the tracker does not assume that ID stays the same for chapter 64. Use **Test ToC extraction** to inspect actual links on the series page, add up to two example links or a chapter-row snippet when needed, and choose a preferred group for reading links. If the next exact link is unavailable, Open next opens the ToC without advancing progress.

Chapter checking lives under `backend/services/checking/`, with one adapter module per site in `sites/` and generic methods in `strategies/`. It tries a matching site adapter first, then a generic ToC or URL method. FreeWebNovel's adapter reads the requested series page's latest chapter signals rather than the paginated first page of chapter links. Comix reads series-scoped page metadata for its latest and first links; a preferred group's link uses an optional rendered-page lookup. Generic ToC checking extracts actual series chapter links and uses bounded pagination when required. A Cloudflare challenge is reported as blocked by default. Optional FlareSolverr use requires both `FLARESOLVERR_URL` and a comma-separated `FLARESOLVERR_ALLOWED_HOSTS` value. Only site and ToC checkers may use it; the site test and incremental URL probe never do. Keep the FlareSolverr endpoint private and its browser container restricted to public-only network egress. The KeiHub Pi enables it for `freewebnovel.com` and `comix.to` only, using the guarded deployment in [ops/pi-browser](ops/pi-browser/README.md). Comix metadata remains available when its optional group lookup fails.

### Local FreeWebNovel preview (REQ-015)

With Docker Desktop running, start the optional browser service from the repository root:

```powershell
docker compose -f compose.flaresolverr.dev.yml up -d
```

The Compose file binds its API to `127.0.0.1:8191` only. FlareSolverr has no direct external network route; its HTTP proxy accepts only public DNS destinations and pins connections to a validated address. Set these variables **for the dev backend process only**, then restart that backend:

```powershell
$env:FLARESOLVERR_URL = 'http://127.0.0.1:8191'
$env:FLARESOLVERR_ALLOWED_HOSTS = 'freewebnovel.com'
```

When running the dev preview, use **Add** with a FreeWebNovel series URL. The preview should show `REACHABLE VIA BROWSER`, method `FREEWEBNOVEL`, and a detected latest chapter. An existing item can use **Check for updates**; a large increase is held as **Review** until accepted. **Test site** intentionally makes a direct request and may still report a Cloudflare HTTP 403. Docker Desktop must remain running for local browser checks. Stop this local option with `docker compose -f compose.flaresolverr.dev.yml down`. The Pi runs a separate pinned browser stack.

## Raspberry Pi

KeiHub manages the separate tracker Compose project, Caddy route, CI-gated updater, and encrypted restic backup. The database is `/srv/keihub/data/tracker/main.db` and covers are in `/srv/keihub/data/tracker/covers`; they must be backed up and restored together. The optional browser stack is documented in [ops/pi-browser](ops/pi-browser/README.md); on the Pi it is allowlisted only for FreeWebNovel. Consult `D:\Projects\Web\KeiHub\OPERATIONS.md` for deployment and restore. Preserve existing records and a verified backup before migration. The service is intended for LAN and router-VPN access without mandatory cloud services.
