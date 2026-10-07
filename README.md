# UrlMediaTracker

A self-hosted reading queue for serialized novels, comics, manga, and webtoons. Add a series or chapter URL, check for new chapters, resume reading, and keep personal progress. It targets a household and modest hardware such as a Raspberry Pi.

## Project contract

[SPEC.md](SPEC.md) contains testable requirements, [ARCHITECTURE.md](ARCHITECTURE.md) the components and deployment, [DATA_MODEL.md](DATA_MODEL.md) the storage model, [ROADMAP.md](ROADMAP.md) reviewable milestones, [DECISIONS.md](DECISIONS.md) product tradeoffs, and [AGENTS.md](AGENTS.md) future coding rules. Requirement IDs are stable. Roadmap features are not deployed features until marked complete.

## Current repository and setup

- `backend/`: FastAPI, SQLAlchemy, Alembic, APScheduler, SQLite.
- `frontend/`: React, TypeScript, Vite, Tailwind CSS, TanStack Query.
- `backend/tests/`: backend behavior tests.

Use Python 3.12 and Node.js 24. Create `backend/env`, install `backend/requirements.txt` and `pytest`, then run `alembic upgrade head` from `backend`. Run `python -m admin_bootstrap` from `backend` to set the first admin password; existing entries are assigned to that account. Run `npm ci` at the root and in `frontend`. `npm run dev` starts Uvicorn at `http://localhost:8000` and Vite at `http://localhost:5173`; API docs are at `/docs`. Copy `backend/.env.example` to `backend/.env` as needed. Run backend tests from `backend` with `python -m pytest tests`; run `npm --prefix frontend run build` and `npm --prefix frontend run lint`.

Sign in to your own reading queue. An admin can create expiring invite links and select a member's library. Safe view starts on for each sign-in; you can create or mark an entry sensitive while it is on, then reveal sensitive entries when you need to view or edit them. Add a series or chapter URL, review the checking method and site access, and use detected details to fill editable fields if they look right. A chapter URL example, regex, generic ToC URL, and strategy override are under advanced checking options; an example chapter number is not treated as reading progress. Switch between table and cover cards. Select Images, Words, or Unread from wrapping desktop chips or the phone preset modal; open Filters to adjust the queue and save its full filter and sort state as a personal preset. Edit covers by upload or public image URL. Titles open the ToC or series; available chapter links and the next chapter action open reading pages. ZIP export requires password confirmation and includes sensitive entries and covers; import deduplicates within the selected account. Legacy JSON import/export remains available.

New entries from FreeWebNovel, WebNovel, Royal Road, and Scribble Hub suggest the `Novel` category after preview. Change it or select **No category** before saving if preferred. Existing entries keep their categories.

Edit item → Detection also accepts a chapter URL example next to the ToC URL. For predictable links such as `/chapter-63`, it updates the saved pattern without moving reading progress. A link such as `/8904631-chapter-63` has a separate numeric ID; the tracker does not assume that ID stays the same for chapter 64. Use **Test selected checker** to inspect actual links on the series page, add up to two example links or a chapter-row snippet when needed, and choose a preferred group for reading links. If the next exact link is unavailable, Open next opens the ToC without advancing progress.

**Test selected checker** follows the chosen strategy. Comix's generic ToC scan cannot see its JavaScript chapter list; choose Automatic or **Comix site checker** for its metadata reader. Chapter examples are optional and do not replace missing ToC links. Saving a changed checker clears the previous check issue and runs a new check with visible feedback. New items default to a 360-minute check interval; existing intervals stay as saved.

The generic ToC scanner works without site-specific branches: it scopes ordinary chapter links to their series path. For a chapter link outside that path, provide a chapter URL example; the scanner matches the full example URL shape while varying only the chapter number. The advanced chapter example is used in the ToC preview and saved for scheduled checks. For unOrdinary, your `episode-(\d+)` override extracts the visible Episode 393, while `episode_no=412` is a separate ID; URL probing is withheld and the ToC provides the exact link. Accepting a pending chapter updates the baseline, allowing ordinary later increments automatically, while another large jump still needs review.

Chapter checking lives under `backend/services/checking/`, with one adapter module per site in `sites/` and generic methods in `strategies/`. It tries a matching site adapter first, then a generic ToC or URL method. FreeWebNovel's adapter reads the requested series page's latest chapter signals rather than the paginated first page of chapter links. Comix reads series-scoped page metadata for its latest and first links; a preferred group's link uses an optional rendered-page lookup. WebNovel's dedicated adapter reads book-scoped embedded catalog data and exact opaque chapter links. Royal Road's dedicated adapter uses the numeric fiction ID and the complete ordered chapter catalog; changing title slugs and volume chapter labels do not affect its reading position. Scribble Hub's dedicated adapter reads the newest first ToC page and uses its explicit row order instead of title numbers. WebNovel, Royal Road, and Scribble Hub are available for local review and are not yet deployed on the Pi. Generic ToC checking extracts actual series chapter links and uses bounded pagination when required. A Cloudflare challenge is reported as blocked by default. Optional FlareSolverr use requires both `FLARESOLVERR_URL` and a comma-separated `FLARESOLVERR_ALLOWED_HOSTS` value. Only site and ToC checkers may use it; the site test and incremental URL probe never do. Keep the FlareSolverr endpoint private and its browser container restricted to public-only network egress. The KeiHub Pi enables it for `freewebnovel.com` and `comix.to` only, using the guarded deployment in [ops/pi-browser](ops/pi-browser/README.md). Comix metadata remains available when its optional group lookup fails.

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

For local WebNovel review, add `www.webnovel.com` to the dev backend's comma-separated allowlist, then restart that backend. The add preview and **Test selected checker** can read a WebNovel book URL such as `https://www.webnovel.com/book/35844914500239705`. **Test site** still reports the direct Cloudflare challenge. Large catalogs above 5 MB are reported as check issues; chapter content may still require WebNovel login or payment. This local allowlist does not change the Pi.

For local Royal Road review, add `www.royalroad.com` to the dev backend's comma-separated allowlist, then restart that backend. Add a fiction URL such as `https://www.royalroad.com/fiction/107917`; the preview and **Test selected checker** should report `ROYALROAD` and a verified latest link. The checker counts every ordered catalog post, including bonus or announcement posts, so its position can differ from a title's chapter number. When older chapters are removed for a stub, it uses the previously accepted latest chapter ID to keep the tracker number stable; if that ID is gone, it reports a check issue for review. **Test site** uses a direct request and can still report a Cloudflare challenge. A new fiction ID would require updating the tracked source manually. This local allowlist does not change the Pi.

For local Scribble Hub review, add `www.scribblehub.com` to the dev backend's comma-separated allowlist, then restart that backend. Add a series URL such as `https://www.scribblehub.com/series/2388343/`; the preview and **Test selected checker** should report `SCRIBBLEHUB`, a release position, and a verified latest link. The sample's position is 126 although its newest title says Chapter 125. Older ToC pages load through JavaScript, but the default first page already contains the latest releases. **Test site** uses a direct request and can still report a Cloudflare challenge. This local allowlist does not change the Pi.

## Raspberry Pi

KeiHub manages the separate tracker Compose project, Caddy route, CI-gated updater, and encrypted restic backup. The database is `/srv/keihub/data/tracker/main.db` and covers are in `/srv/keihub/data/tracker/covers`; they must be backed up and restored together. The optional browser stack is documented in [ops/pi-browser](ops/pi-browser/README.md); on the Pi it is allowlisted for FreeWebNovel and Comix. Consult `D:\Projects\Web\KeiHub\OPERATIONS.md` for deployment and restore. Preserve existing records and a verified backup before migration. The service is intended for LAN and router-VPN access without mandatory cloud services.
