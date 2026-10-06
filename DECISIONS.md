# Decisions

Record changes here with date, reason, alternatives, and requirement IDs.

## D-001 — Focused media tracker (2026-10-05)
Keep household tasks and other apps separate. A broad home-app data model was considered; the focused reading queue is simpler to maintain. REQ-004, REQ-009.

## D-002 — Personal libraries and admin support (2026-10-05)
Each user owns a library and progress; admin may explicitly access another. Shared catalog and shared progress were considered. REQ-001, REQ-002.

## D-003 — Safe view per session (2026-10-05)
One sensitive flag excludes entries from normal surfaces when safe view is on; new sessions start safe. Account authorization protects users from each other. Default-visible and several privacy flags were considered. REQ-003, REQ-012.

## D-004 — Dedicated checker first (2026-10-05)
Use site adapter before generic methods, allow item override, and fall through only on `UNSUPPORTED`. This prevents speculative probing after unchanged or blocked results. FreeWebNovel is first. REQ-005–REQ-008.

## D-005 — Manual tracking for blocked sites (2026-10-05)
Warn but permit saving. No Cloudflare bypass or required Pi browser automation. Hard rejection and bypass were considered. REQ-004, REQ-006.

## D-006 — Small catalog model (2026-10-05)
Keep one category, add one note and cover, allow safe auto-fetch and upload. No arbitrary attachments or rich catalog fields. REQ-009, REQ-010.

## D-007 — Preserve Pi operations (2026-10-05)
Keep SQLite, separate Compose service, Caddy, LAN/VPN access, and KeiHub's updater and encrypted backup. Extra database and required cloud identity were rejected for maintenance cost. REQ-014.

## D-008 — Explicit complete export (2026-10-05)
Password-confirmed full ZIP includes sensitive records. A safe-view filtered archive would be an incomplete backup. REQ-003, REQ-012.

## D-009 — Compatible dependency updates (2026-10-05)
Refresh the frontend lockfile within declared version ranges and keep Tailwind CSS 3 for this release. The audited update reduced reported advisories from 17 to 5 and passed lint and builds on Windows and the Pi. The remaining five are in the Tailwind 3 build tool chain; removing them currently requires a Tailwind 4 migration and a separate UI review. This build tool chain is not served to tracker users. REQ-014.

## D-010 — Saved filter presets (2026-10-05)
Initial choice: a compact picker instead of a horizontally scrolling category chip strip. Built-in Images includes all current visual categories, including Anime; Words includes Novel and Light Novel; Unread spans all categories. Custom presets belong to one account. The picker and criteria scope were superseded by D-011 after user preview. REQ-009, REQ-011.

## D-011 — Preset and reading controls revised after preview (2026-10-05)
Desktop presets use wrapping chips; phones open a compact preset picker. The Filters control opens a modal that holds the criteria and Save/Update actions together. Save captures categories, unread and active flags, and sort key/direction, while search and safe view remain outside presets. Titles open the ToC or series; chapter numbers link only when a specific URL can be built and use the same default and hover styling as title links. Cover URLs are fetched through the same public-address and redirect guard as other source requests, then normalized into local storage. A dropdown-only preset control and a separate criteria editor were rejected after user review. REQ-009–REQ-011.

## D-012 — Centered wide-screen content (2026-10-06)
Cap the reading queue's main content at 96 rem and center it on wider screens. Keep the header full width. The previous 110 rem limit spread table columns too far apart at 1920 px; a narrower limit still leaves room for the table and wrapping presets. REQ-009.
