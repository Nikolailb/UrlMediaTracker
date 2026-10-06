# Product specification

Status: implementation contract. Mark an acceptance criterion complete only after verification. IDs are permanent.

## Accounts and visibility

### REQ-001 — Personal libraries
Each account owns its entries, progress, notes, and covers. Ordinary users can read and change only their own library. An admin can explicitly select another account for support or export. Pre-upgrade entries and progress are assigned to the initial admin without changing IDs or chapter values.

Acceptance: direct API reads and writes, checks, bulk actions, and exports across accounts are denied; migration preserves count and sample progress.

### REQ-002 — Local authentication
The admin creates one-use invites expiring in 24 hours; recipients choose passwords. No public registration or email is required. Use HTTP-only session cookies and CSRF protection for mutations. A local host command can recover the admin account.

Acceptance: expired/reused invites fail; unauthenticated item and user APIs fail; only admin can invite or manage users; logout revokes the session.

### REQ-003 — Sensitive entries and safe view
An item has one `is_sensitive` flag. Safe view starts on every new session and can be deliberately changed for that session. While on, sensitive entries are absent from ordinary list, card, search, count, activity, preview, file, and direct item APIs, including admin views. Full account export is a separate password-confirmed action that explicitly includes sensitive entries.

Acceptance: title, URL, note, cover, and counts cannot leak through normal APIs while safe view is on; authorized reveal works; a new session starts safe.

## Source checking

### REQ-004 — Add from series or chapter URL
Preview inferred title, current chapter, cover candidate, accessibility, and checker before saving. Let the user edit the inference. An inaccessible source can be saved for manual tracking.

Acceptance: both URL forms create entries; inaccessible source warns without blocking; private-network fetch targets are rejected, including redirected targets.

### REQ-005 — Checker selection and outcomes
Prefer a matching site-specific checker, then a compatible generic ToC or URL checker. Permit item-level override and display the method. Return distinct new, unchanged, unsupported, blocked, and failed outcomes. Unchanged or blocked never triggers a generic probe.

Acceptance: fixture tests cover each outcome and override; unchanged ToC and unrelated links never advance the chapter.

### REQ-006 — Site-access diagnostic
Provide a test in the add flow and a separate URL tool. Distinguish likely Cloudflare challenge, ordinary HTTP error, timeout, reachable, and inconclusive. Bound requests by timeout, response size, redirects, and public-address checks. Do not claim guaranteed future access.

Acceptance: challenge and error fixtures differ; rejected private URLs produce no outbound request; manual tracking remains possible.

### REQ-007 — FreeWebNovel checker
Recognize series and chapter links and extract the requested series's chapter number and usable chapter URL, excluding recommendations and global post IDs.

Acceptance: a saved fixture for the supplied Harem System series reports Chapter 644, not 5682, and a corresponding series chapter URL.

### REQ-008 — Suspicious increases
An automatic numeric increase greater than both 50 chapters and 25% of the prior latest becomes a pending result for owner review. Incomparable chapter labels also require review. The owner can accept or correct it.

Acceptance: 644-to-5682 is held, one-chapter increase applies, and pending/review actions appear in the app and history.

## Daily use and portability

### REQ-009 — Queue, views, filters
Keep the table and add a selectable cover-card view on desktop/tablet. Show wrapping preset chips on desktop and a compact preset modal on phones. Provide built-in Images (Manhwa, Manhua, Manga, Webtoon, Pornhwa, Comic, Anime), Words (Novel, Light Novel), and Unread presets. An account can create, rename, change, and delete its own additional presets. The Filters modal edits and saves the full current state: an OR list of categories, unread-only, include-inactive, sort key, and sort direction. An empty category list means all categories. Search and safe view stay independent. Built-ins remain available and cannot be changed. The reading queue remains home; no separate analytics dashboard.

Acceptance: selecting each preset applies all saved filter and sort criteria in both views; Save and Update appear in the Filters modal and capture its current state without requiring the criteria to be re-entered. The account can reload, update, rename, and delete a preset; another account cannot access it through the API. Desktop chips wrap at the container edge and phone presets fit a modal at 360 px without horizontal page overflow. On a 1920 px viewport, the queue content is centered within a 96 rem maximum width; smaller viewports still use available width. Safe view still excludes sensitive entries regardless of preset.

### REQ-010 — Notes and covers
Support an optional short note and one locally stored cover. Try safe metadata fetch; allow upload, direct public image URL fetch, replacement, and removal. No other file attachments. Missing covers use a placeholder.

Acceptance: validate type, size, and decoded image for both upload and URL fetch; reject private-network targets and recheck redirects; cover API enforces authorization and safe view; backups and exports include covers.

### REQ-011 — Mobile reading
Make open-next and mark-read prominent touch actions on phones and visible in the table. Link item titles to the ToC or series URL. Link progress chapter numbers to their specific chapter URL when a reliable template is known. Search, filters, view choice, and editing remain usable without horizontal overflow.

Acceptance: core actions work at 360 px width with touch and keyboard access; title and known chapter links open the intended destination. Chapter numbers are plain foreground text until hovered, when they match title links' blue and underline styling. Unavailable chapter links have clear feedback.

### REQ-012 — Portable account archive
An explicit password-confirmed full export produces a versioned ZIP containing entries, progress, notes, sensitive entries, covers, and custom filter presets. Import targets the selected authorized account and deduplicates normalized URLs and preset names within it. Support legacy JSON import where safe. Operational backup is separate.

Acceptance: ZIP round-trip reproduces representative data and custom presets; malformed archives cause no partial import; full export never silently omits sensitive entries.

### REQ-013 — In-app feedback
Show unread, failed-check, and pending-review states in the queue. No push, email, or cloud notification service.

Acceptance: each state is distinct and pending results have an action.

### REQ-014 — Pi operations
Keep SQLite, the separate tracker service, Caddy, LAN/VPN access, and KeiHub's CI-gated update and encrypted restic backup. Persist database and covers together. Require verified backup before migration and paired image/data rollback on failure.

Acceptance: restore rehearsal recovers entries/covers; existing record count and sample rows survive migration; isolated failed-readiness test restores the paired version; no added database or mandatory cloud service.
