# Working instructions for UrlMediaTracker agents

Read `README.md`, `SPEC.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `ROADMAP.md`, and `DECISIONS.md` before changing behavior. For Pi changes, also read `D:\Projects\Web\KeiHub\OPERATIONS.md` and inspect live paths rather than assuming the document is current.

Use stable `REQ-###` IDs in code changes, tests, and roadmap updates. Never recycle IDs. Update documentation when behavior changes. Keep roadmap status honest: planned is not deployed.

Work in small verified increments. Prioritize one-maintainer simplicity, SQLite, household-scale performance, portable data, and safe restore. Run targeted backend tests and frontend build/lint. Enforce account authorization and safe-view filtering at API and file-serving boundaries. Validate outbound URL fetches against private-network targets and redirects.

Keep checker code in `backend/services/checking/`: one module per dedicated adapter in `sites/`, generic methods in `strategies/`, and shared transport/selection/orchestration at the package root. Browser-backed fetching is opt-in for site or ToC checks only; never call it from URL probing or general site diagnostics. Require public-only browser-container egress before enabling an allowed host (REQ-015).

Before production schema or deployment changes, confirm live database path and count, take and verify a consistent backup, preserve a matching old image/data pair, and rehearse rollback. Do not alter the live Pi merely because local tests pass. Keep secrets, exports, database files, covers, and backups out of Git. Preserve user data with additive migrations; never use `create_all` in place of Alembic.
