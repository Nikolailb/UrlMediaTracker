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
An item has one `is_sensitive` flag. Safe view starts on every new session and can be deliberately changed for that session. A user may create an entry as sensitive or mark a visible entry sensitive while safe view is on; it disappears from normal reads immediately after saving. While on, sensitive entries are absent from ordinary list, card, search, count, activity, preview, file, and direct item APIs, including admin views. Full account export is a separate password-confirmed action that explicitly includes sensitive entries.

Acceptance: create and mark-sensitive mutations succeed while safe view is on, but subsequent list, item, cover, and activity reads do not expose the entry until reveal. A new session starts safe.

## Source checking

### REQ-004 — Add from series or chapter URL
Preview inferred title, chapter, cover candidate, accessibility, and checker before saving. The first add step accepts only a series or chapter URL; the review step offers an explicit action to copy detected title, URL chapter, latest chapter, and cover into editable fields. The user's reading position stays separate from the source's latest chapter. Advanced add options and the edit Detection tab accept an optional chapter URL example alongside an optional separate ToC URL, chapter regex, and strategy override. When a chapter example has a reusable numeric pattern, build or replace the URL template from it; on add, use the first URL as the ToC unless a different ToC is supplied. The chapter number in that example never changes reading progress or the accepted latest chapter. A recognized site-specific series URL needs no URL pattern and must not show a missing-pattern warning. An inaccessible source can be saved for manual tracking.

Acceptance: both URL forms create entries; a ToC-first entry with a chapter-55 example stores the first URL as ToC and a chapter template from the example, with empty progress/latest unless explicitly entered; editing a ToC-first item with a chapter example replaces its checking pattern while preserving ToC and progress; invalid example URLs are rejected. A URL with a separate opaque numeric ID before `chapter-63` is flagged as non-sequential rather than creating a false probe template, including with a manual regex. The UI explains that such links need a site-specific checker for automatic updates. Detection does not silently overwrite edited fields; saved latest chapter matches the review field; the first step asks for no regex; a FreeWebNovel series URL displays no missing-pattern warning; inaccessible source warns without blocking; private-network fetch targets are rejected, including redirected targets.

The default check interval for newly created items is 360 minutes; existing saved intervals are preserved. The chapter URL example is optional for ToC and site-specific checkers. A manual chapter URL regex guides generic ToC link extraction even when it cannot produce a safe sequential URL template. If an example cannot produce such a template, saving must say so without implying the regex is unusable for ToC scanning.

### REQ-005 — Checker selection and outcomes
Prefer a matching site-specific checker, then a compatible generic ToC or URL checker. Permit item-level override during addition and editing, and display the method. Return distinct new, unchanged, unsupported, blocked, and failed outcomes. Unchanged or blocked never triggers a generic probe.

Acceptance: fixture tests cover each outcome and override; unchanged ToC and unrelated links never advance the chapter.

The ToC test action must use the method currently selected in Add or Edit, including an explicit generic ToC override on a known site. When checker settings change, clear the previous method's displayed issue and run one check with the new method when the item is active. Report its success, pending result, or actual failure to the user. An unchanged checker configuration does not erase a genuine current issue.

### REQ-006 — Site-access diagnostic
Provide a test in the add flow and a separate URL tool. Distinguish likely Cloudflare challenge, ordinary HTTP error, timeout, reachable, and inconclusive. Bound requests by timeout, response size, redirects, and public-address checks. Do not claim guaranteed future access.

Acceptance: challenge and error fixtures differ; rejected private URLs produce no outbound request; manual tracking remains possible.

### REQ-007 — FreeWebNovel checker
Recognize series and chapter links and extract the requested series's chapter number and usable chapter URL, excluding recommendations and global post IDs.

Acceptance: a saved fixture for the supplied Harem System series reports Chapter 644, not 5682, and a corresponding series chapter URL. Series-page fixtures for As A Mafia Boss (546) and My Taboo Harem (1314) read the page-scoped latest metadata and latest-chapters section, not the paginated first 40 or sidebar. Conflicting page signals fail the check rather than advancing progress.

### REQ-008 — Suspicious increases
An automatic numeric increase greater than both 50 chapters and 25% of the prior latest becomes a pending result for owner review. Incomparable chapter labels also require review. The owner can accept or correct it.

Acceptance: 644-to-5682 is held, one-chapter increase applies, and pending/review actions appear in the app and history.

Accepting a pending chapter changes the latest-chapter baseline. It does not permanently trust a checker or site: later increases below the numeric threshold apply automatically, while another suspicious jump requires review. A valid pending result or accepted correction clears an older check error.

## Daily use and portability

### REQ-009 — Queue, views, filters
Keep the table and add a selectable cover-card view on desktop/tablet. Show wrapping preset chips on desktop and a compact preset modal on phones. Provide built-in Images (Manhwa, Manhua, Manga, Webtoon, Pornhwa, Comic, Anime), Words (Novel, Light Novel), and Unread presets. An account can create, rename, change, and delete its own additional presets. The Filters modal edits and saves the full current state: an OR list of categories, unread-only, include-inactive, sort key, and sort direction. An empty category list means all categories. Search and safe view stay independent. Built-ins remain available and cannot be changed. The reading queue remains home; no separate analytics dashboard.

Acceptance: selecting each preset applies all saved filter and sort criteria in both views; Save and Update appear in the Filters modal and capture its current state without requiring the criteria to be re-entered. The account can reload, update, rename, and delete a preset; another account cannot access it through the API. Desktop chips wrap at the container edge and phone presets fit a modal at 360 px without horizontal page overflow. On a 1920 px viewport, the queue content is centered within a 96 rem maximum width; smaller viewports still use available width. Safe view still excludes sensitive entries regardless of preset.

### REQ-010 — Notes and covers
Support an optional short note and one locally stored cover. Try safe metadata fetch; allow upload, direct public image URL fetch, replacement, and removal. No other file attachments. Missing covers use a placeholder.

Acceptance: validate type, size, and decoded image for both upload and URL fetch; reject private-network targets and recheck redirects; cover API enforces authorization and safe view; backups and exports include covers.

### REQ-011 — Mobile reading
Make open-next and mark-read prominent touch actions on phones and visible in the table. Link item titles to the ToC or series URL without a duplicate URL line below the title in either queue view. Link progress chapter numbers to their specific chapter URL when a reliable template is known. When latest is at least chapter 1 and progress is empty or zero, display a chapter 1 start link in the progress position; Open next targets chapter 1 and Mark read records chapter 1. Displaying the start link does not itself save progress. Search, filters, view choice, and editing remain usable without horizontal overflow.

Acceptance: core actions work at 360 px width with touch and keyboard access; title and known chapter links open the intended destination. A new FreeWebNovel item with latest 1416 and no progress shows linked `1 / 1416`, reports unread, opens chapter 1, and records progress only after Mark read. Chapter numbers are plain foreground text until hovered, when they match title links' blue and underline styling. Unavailable chapter links have clear feedback.

### REQ-012 — Portable account archive
An explicit password-confirmed full export produces a versioned ZIP containing entries, progress, notes, sensitive entries, covers, and custom filter presets. Import targets the selected authorized account and deduplicates normalized URLs and preset names within it. Support legacy JSON import where safe. Operational backup is separate.

Acceptance: ZIP round-trip reproduces representative data and custom presets; malformed archives cause no partial import; full export never silently omits sensitive entries.

### REQ-013 — In-app feedback
Show unread, failed-check, and pending-review states in the queue. No push, email, or cloud notification service.

Acceptance: each state is distinct and pending results have an action.

### REQ-014 — Pi operations
Keep SQLite, the separate tracker service, Caddy, LAN/VPN access, and KeiHub's CI-gated update and encrypted restic backup. Persist database and covers together. Require verified backup before migration and paired image/data rollback on failure.

Acceptance: restore rehearsal recovers entries/covers; existing record count and sample rows survive migration; isolated failed-readiness test restores the paired version; no added database or mandatory cloud service.

### REQ-015 — Opt-in browser fetching and checker modules
Keep checking code under `services/checking/`: one module per site adapter in `sites/`, generic methods in `strategies/`, and separate selection, orchestration, public HTTP, and browser transport modules. An optional FlareSolverr transport may be called only by a site-specific or ToC checker, only after a direct browser challenge, connection failure, or timeout, and only for an explicitly configured host. An explicitly allowlisted site adapter may also request one bounded rendered-page lookup after a direct successful response when essential chapter rows are loaded by JavaScript; its direct metadata result remains usable if rendering fails. The URL probe and general site-access diagnostic never call it. If the browser service is absent or fails, preserve the direct outcome. Do not enable this transport on a host until its browser container has public-only network egress and is inaccessible from the internet or LAN users.

Acceptance: both configuration values are empty by default; tests show blocked or unreachable sources keep their direct outcome by default, site/ToC can opt in, and probe/diagnostic paths do not invoke the browser service. On an opted-in host, the browser API binds to loopback, its container has no direct external route, private proxy destinations are rejected, and a live approved series check returns a chapter link from that series. A Pi deployment records available RAM, browser request behavior, backup, and rollback instructions. Additional hosts require separate evidence and explicit allowlisting.

### REQ-016 — Reliable ToC extraction and reading links

Generic ToC checks extract chapter labels and actual series-scoped links without requiring a URL template. Collapse duplicate chapter numbers across groups; an optional preferred group chooses the reading link, while the highest chapter across all groups determines update status. Validate pagination order using a bounded first/last-page check when pagination is explicit, then read only the confirmed latest page routinely. The Comix adapter reads series-scoped initial page data and may use the explicitly allowlisted browser transport for rendered group links. A preview shows method, confidence, latest, samples, groups, and warnings; two example links and an optional chapter-row HTML snippet can guide an uncertain generic extraction. Never probe after an ambiguous, blocked, empty, contradictory, or truncated ToC result. Store verified latest links. Open next uses an exact link when known and otherwise opens the ToC without changing progress.

Acceptance: saved fixtures cover ordinary and paginated ToCs, unrelated links, duplicate groups, Comix metadata/rendering, changed layouts, truncation, and failures; duplicates do not create updates, opaque IDs are never synthesized, group preference does not change the latest count, and no uncertain result becomes unchanged. Preview and item APIs enforce login, ownership, and safe view. Migration preserves existing items; ZIP round-trip preserves new fields. The mobile and desktop reading actions use a known direct URL or clearly identified ToC fallback.

For Comix, a generic ToC override reports that the direct HTML has no chapter anchors and offers a one-click switch to the dedicated Comix checker. Optional example links do not cause the generic checker to claim an OK result when its source page contains no matching links.

The generic ToC scanner must not contain host-specific branches. It may recognize common terminal list paths, scope links by series path, reject conflicting shared query values, and use an optional one-group chapter URL regex to extract chapter numbers. An invalid or contradictory regex result is an issue, never unchanged. A chapter URL with separate path and query chapter identifiers must not become a one-placeholder probe template; older saved templates with that ambiguity must not be probed or used by Open next. A descending first page can establish the latest chapter without fetching older pages. The Webtoons regression fixture with visible Episode 393 and `episode_no=412` must report chapter 393 and its exact link, excluding another title's links. A site-neutral fixture whose links require `release-(\d+)` must be EMPTY without the override and succeed with it.

A ToC may link to same-host chapter pages outside its own directory. The ToC path alone must not authorize those links. Derive the full chapter URL shape from a user-provided chapter URL example (or an existing example-derived template), varying only the chapter number. The advanced chapter example also becomes a saved ToC hint and is included in extraction preview. Acceptance: the Hentai20 `/manga/.../` fixture is EMPTY without a chapter example, but an example at `/i-became-a-pornhwa-npc-chapter-75/` finds chapter 80 and its exact URL; a different series' example cannot admit those links. An optional matching regex and row class preserve the result. Existing items with only the derived template still check correctly. A reachable source with no matching links remains an issue, not unchanged. REQ-016.

### REQ-017 — WebNovel book checker

Recognize WebNovel book, catalog, and chapter URLs and read the requested book's embedded chapter catalog with a dedicated `WEBNOVEL` checker. Use the catalog's positive `chapterIndex` as the chapter number and its opaque `chapterId` for exact first and latest links. Exclude auxiliary entries and unrelated books; do not infer a chapter number from a title, total count, or chapter ID. A direct request is first; an explicitly allowlisted FlareSolverr request may retry a challenge or connection/timeout failure. Generic URL probing never handles opaque WebNovel IDs. A missing, oversized, inconsistent, or blocked catalog is a check issue rather than unchanged. The add and extraction previews show the dedicated method and detected details. The local dev backend may allowlist WebNovel for review; Pi activation remains a separate release decision.

Acceptance: saved fixtures verify chapter 1/2 links, the latest index despite a different title number and an auxiliary entry, series identity, and unrelated-link exclusion. A challenged direct request with browser access yields a verified latest link; without browser access it reports blocked. A catalog above the bounded size limit reports an explicit issue. First and latest links drive reading actions; an unknown intermediate link opens the catalog. Local live review confirms the browser service and outbound access before release.

### REQ-018 — Royal Road fiction checker

Recognize Royal Road fiction and chapter URLs by numeric fiction ID and use `https://www.royalroad.com/fiction/{id}` as the canonical source and ToC. Read the fiction-scoped `window.chapters` catalog, including when the visible table shows only one page. On the first check, number releases by the catalog's zero-based `order` plus one, including bonus or announcement posts; chapter titles may restart within volumes and URL slugs may change. Use each entry's actual chapter ID and URL for verified first/latest links. On later checks, locate the previously accepted latest chapter ID in the current catalog. If older chapters were stubbed, preserve the tracker's existing latest number; add only catalog entries after that ID. If the previous latest ID has disappeared, report a reviewable check issue and leave progress unchanged. A direct request is first, with one guarded FlareSolverr retry only for an explicitly allowlisted challenged or unreachable host. Never generate or probe chapter URLs from opaque IDs. Missing, hidden, incomplete, contradictory, oversized, or blocked catalogs are check issues.

Acceptance: the compact Sky Pride fixture yields three ordered releases, its first chapter link, and the art-contest post as latest despite a title without a chapter number; a live check found 415 catalog entries at verification time. The short fiction-ID URL and title-slug/chapter URLs map to the same series; a different fiction ID or unrelated recommendation is excluded. Fixture tests cover order gaps, ID/URL mismatch, count mismatch, challenge retry, stubbing that removes older entries, a missing latest ID, and no opaque-ID progress inference. Local live checks parse the supplied Sky Pride and stubbed Game at Carousel fictions through guarded FlareSolverr. The local dev preview reports the selected method and exact latest link. Pi activation is a separate release decision.

### REQ-019 — Scribble Hub series checker

Recognize Scribble Hub series and chapter URLs by numeric series ID and use `https://www.scribblehub.com/series/{id}/` as the canonical source. Its first ToC page lists the latest releases in descending order and loads older pages through site JavaScript; routine checks read only that first page. Use the row's explicit `order` and series-scoped real chapter URL, never the chapter title or opaque URL ID, as the release position and reading link. Cross-check the first row against the declared ToC count, the selected page size, consecutive row positions, and series identity. Use the page's Read link for an unstarted entry when it belongs to that series. A changed latest chapter ID at an unchanged count, a falling count, a partial or contradictory page, a challenge, or an oversized page is an issue rather than silently unchanged; a title slug change around the same chapter ID is allowed. Direct fetching precedes one guarded FlareSolverr retry for an explicitly allowlisted host. Never probe opaque chapter IDs or require a chapter URL regex. Unknown intermediate links open the ToC.

Acceptance: the saved sample has 126 ordered releases even though the latest title says Chapter 125; it yields the exact chapter-2602375 latest link and chapter-2388346 first link. An unrelated series link is excluded. Fixture tests cover wrong series, missing or shortened ToC, inconsistent order, challenge retry, same-count link replacement, and adding a chapter URL without treating its opaque ID as progress. The local add and extraction previews show `SCRIBBLEHUB` and verified details through guarded FlareSolverr. Pi activation is a separate release decision.

### REQ-020 — Prose-site category suggestion

New entries from FreeWebNovel, WebNovel, Royal Road, and Scribble Hub default to the existing `Novel` category. The add form shows the suggestion after source preview, before saving. The user can choose another category or explicitly choose no category. The API applies the same default when a create request omits `category`, but respects an explicit category or `null`. Existing entries are not reclassified, and other sites have no new default.

Acceptance: each of the four recognized site URL shapes creates a `Novel` item when category is omitted; explicit `Light Novel` and explicit `null` are preserved; an unrelated site remains uncategorized. The add form preserves a category the user has deliberately selected when the URL is previewed again.

### REQ-021 — Tracker identity assets

Use one recognizable book-and-bookmark mark for the application header, browser favicon, and installable web manifest. Provide a transparent icon and a separate dark card background in the repository for manual upload to KeiHub. Artwork must require no remote image service at runtime.

Acceptance: the favicon contains 16, 32, 48, and 64 pixel sizes; the web manifest includes 192 and 512 pixel PNGs; the hub icon has a transparent alpha channel and fits within 512 × 512 pixels; the card background fits within 1600 × 1000 pixels; frontend build and lint pass. Hub upload remains a separate manual action.
