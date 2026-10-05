# Architecture

## Components

Browser (React build) → KeiHub Caddy same-origin route → FastAPI → SQLite. APScheduler checks active items with bounded outbound requests. Checker selection chooses a dedicated site adapter first, then a compatible generic ToC or URL method. A typed result enters the application service; suspicious-jump policy decides whether to update the accepted latest chapter or store a pending candidate. Validated covers are files in the tracker data directory and are served only by authorized API routes.

Local authentication uses password hashes, one-use invites, and revocable sessions in SQLite. The browser has an HTTP-only cookie; every item query derives account and session safe-view state server-side. An admin must explicitly select another account. CSRF tokens protect mutations. `user_id` query parameters are not an authorization mechanism.

Saved filter presets belong to the selected library account and are managed through authorized API routes. Three built-ins are supplied by the server; custom preset definitions are small SQLite rows. The browser applies their category/unread/active criteria to the authorized item list in either view. Safe view is enforced by the API before filtering, so no preset can expose hidden entries.

## Checking boundary

Checkers receive canonical series/source URL, optional chapter template and ToC, accepted latest value, and bounded request settings. They return `NEW`, `UNCHANGED`, `UNSUPPORTED`, `BLOCKED`, or `FAILED`, with candidate chapter/link and diagnostic where relevant. `UNCHANGED` is terminal. Only `UNSUPPORTED` may fall through to a compatible method. FreeWebNovel is the first dedicated adapter.

All user-supplied fetch URLs require HTTP(S), public DNS results, connection to a validated address, redirect-by-redirect revalidation, and time, byte, and redirect limits. The guard covers diagnostics, metadata, ToC, probes, and covers. Never fetch loopback, RFC1918, link-local, or other reserved addresses. Report likely challenges without attempting to bypass them.

## Storage and operations

SQLite remains the only database. Alembic owns additive schema migrations; startup `create_all` is not a migration. Index items by owner, sensitivity, and check dates. The portable account archive is versioned, includes custom presets, and excludes credentials, sessions, invites, and host secrets. Encrypted restic snapshots include consistent SQLite data, cover files, configuration, and matching deployment revision.

The Pi remains KeiHub-managed: separate tracker Compose project, Caddy HTTPS on LAN/VPN, CI-gated candidate build, verified pre-upgrade backup, migration, readiness test, and paired rollback. The documented DB is `/srv/keihub/data/tracker/main.db`; inspect the live mount before edits. Add persistent covers beneath the tracker data root and verify backup inclusion. Do not introduce Redis, PostgreSQL, object storage, browser automation, or required cloud identity.
