# Roadmap

Milestones are reviewable increments; mark complete only with acceptance evidence. [SPEC.md](SPEC.md) is authoritative.

| Milestone | Deliverable and exit check | Requirements | Status |
|---|---|---|---|
| M0 — Contract | Seven root documents agree with repository and KeiHub operations before feature code. | REQ-001–REQ-014 | Complete: documentation created |
| M1a — Checking outcomes | Typed outcomes, safe fallback, pending jump review, fixture tests. | REQ-005, REQ-008 | Implemented locally; fixture tests pass |
| M1b — Source support | FreeWebNovel, add preview, site diagnostic, URL guard tests. | REQ-004, REQ-006, REQ-007 | Implemented locally; live source and redirect checks remain |
| M2a — Auth | Schema, admin bootstrap, legacy owner migration, sessions, invites, API authorization. | REQ-001, REQ-002 | Implemented locally; live legacy migration remains |
| M2b — Safe view | Flag, session default, server filtering, leak tests. | REQ-003 | Implemented locally; API tests pass |
| M3a — Queue | Category chips, issue feedback, card/table switch. | REQ-009, REQ-013 | Implemented locally; browser test showed filtered table/card switching and safe-view counts |
| M3b — Media/mobile | Notes, covers, open-next/mark-read actions, viewport checks. | REQ-010, REQ-011 | Implemented locally; phone-width browser tests showed no page overflow and mark-read progress through click and Enter key |
| M4a — Portability | Versioned ZIP, legacy JSON compatibility, round-trip tests. | REQ-012 | Implemented locally; ZIP dedup, invalid-archive atomicity, and sensitive cover round-trip tests pass with Pillow |
| M4b — Pi recovery | Cover mount and backup, restore rehearsal, failed-upgrade rollback. | REQ-014 | Live encrypted backup restored and SQLite progress digest matched; isolated rollback restored old image, database, and cover; ARM64 candidate image built and passed migration/admin/health/login/cover smoke checks; live host installation remains |

Do not deploy schema changes before a verified snapshot of live tracker data. Preserve a matching old image/data pair. The 2026-10-05 restore rehearsal used the latest encrypted USB snapshot and matched all five live tracker records and their progress digest; the isolated restore was removed and the USB unmounted. An isolated test on the Pi exercised a deliberate tracker readiness failure and verified paired rollback of image, database, and cover. A separate ARM64 candidate image built successfully and passed disposable-database migration, admin bootstrap, health, login, and cover-storage smoke checks. A live upgrade and backup of newly created covers remain to be verified.
