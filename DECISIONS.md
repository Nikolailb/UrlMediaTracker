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

## D-013 — Explicit browser transport for selected ToC checkers (2026-10-06)
Keep direct requests as the default. Permit an optional FlareSolverr retry after a challenge or direct connection/timeout failure only for an explicitly allowlisted site's adapter or generic ToC checker. Never use it for incremental URL probing or the general site diagnostic; probing makes many requests and can increase blocking. FreeWebNovel uses a custom series-page ToC parser based on the latest metadata, latest list, and total count. Split it, generic ToC parsing, and URL probing into separate files. An always-on browser proxy and a universal Cloudflare bypass were considered, but add Pi cost and cannot guarantee access. The browser service must have public-only egress because it can follow redirects and load subresources before application-side validation. REQ-005, REQ-007, REQ-015. This supersedes D-005's earlier decision against any browser-backed option; manual tracking remains available.

## D-014 — Checker package layout (2026-10-06)
Place all chapter checking under `services/checking/`, with site adapters in `sites/`, generic methods in `strategies/`, and shared selection, orchestration, and transports at the package root. This keeps adding a tenth site adapter from crowding general services and keeps cover handling separate. A flat collection of checker files was considered and rejected for maintainability. REQ-005, REQ-015.

## D-015 — Guarded local browser preview (2026-10-06)
For local development, put FlareSolverr on an internal Docker network and route its browser through a small proxy that rejects private DNS results and pins connections to the validated public address. Publish only a loopback API gateway to the dev backend. A plain FlareSolverr container with unrestricted egress was considered for ease of setup but cannot enforce the public-only boundary required by REQ-015. This arrangement was verified locally; Pi deployment remains a separate decision after resource and operations checks. REQ-015.

## D-019 — Pi browser allowlist begins with FreeWebNovel (2026-10-06)
Run a separate, pinned ARM64 FlareSolverr stack on the Pi with the same internal-network and public-only proxy design as development. Bind its API to `127.0.0.1:8191` and allowlist only `freewebnovel.com` in the tracker. Direct fetching remains first; the site adapter uses the browser only after a challenge or connection/timeout failure. A live Pi series check returned chapter 546 and a matching chapter URL. Docker reported that this Pi does not enforce container memory limits, so keep browser checks serialized and watch RAM/swap. A sampled generic ToC source was directly reachable (HTTP 200) and parsed its latest chapter, so it does not warrant browser access now. Other sampled entries use incremental URL probing, which stays browser-free. A global browser fallback and expanding the allowlist without source-specific evidence were considered and rejected. REQ-005, REQ-007, REQ-015.

## D-016 — URL then editable source review (2026-10-06)
Keep two short add steps: paste a URL, then review the source and personal fields. The source check can take time, so a separate review step makes the detected method and values clear. Copy detected details only when the user chooses **Use detected details**; keep latest chapter separate from personal reading position. Put regex and generic ToC fields in advanced options because a dedicated site checker does not require a chapter URL pattern. Remove the duplicate URL line beneath linked titles in table and card views. A one-screen form and automatic overwrite of inferred values were considered; the two-step review makes source results easier to verify without making advanced settings part of the default path. REQ-004, REQ-011.

## D-017 — Chapter 1 for unstarted items (2026-10-06)
Treat empty progress as not started when a numeric latest chapter and reliable chapter URL template exist. Show a chapter 1 start link, let Open next target chapter 1, and let Mark read save chapter 1. The display alone never changes the stored progress. Requiring the user to enter chapter 0 before reading was considered but adds avoidable setup for series URLs. REQ-011, REQ-013.

## D-018 — Separate ToC source and chapter example (2026-10-06)
Allow a ToC or series URL in the first add step and a chapter URL example in advanced review options. Derive the chapter template from the example, default the ToC to the first URL, and never interpret the example's chapter number as reading progress or latest. Provide the same explicit strategy override available when editing. Requiring a chapter URL as the first input would make the source URL awkward for ToC-first sites. The original choice not to store the example was superseded by D-025 for generic ToC scoping. REQ-004, REQ-005.

## D-020 — Edit chapter examples and withhold unsafe probe templates (2026-10-06)
Put a chapter URL example beside the ToC URL in Edit item → Detection. Derive and preview a replacement pattern, preserving reading progress and latest chapter. The supplied Comix URL contains a separate long numeric ID before `chapter-63`; a single example cannot show whether that ID changes, so generating `8904631-chapter-{n}` would claim unsupported knowledge. Flag this shape and withhold the generic template, even when a manual regex extracts `63`. The current generic ToC matcher also needs a stable template; automatic checking for this URL shape requires a site adapter or a new extractor of actual ToC chapter links. Keeping the old ID in a probe template and silently trying the next number were considered and rejected. REQ-004, REQ-005.

## D-021 — Actual ToC links and Comix metadata (2026-10-06)

Extract actual series chapter links for generic ToCs; keep sequential probing separate. Comix's public HTML embeds a latest number and URL but no chapter anchors, and its chapter API requires a browser-provided token. Use its series-scoped metadata first, then optionally the guarded browser for group-specific links after host verification. Track the highest chapter across groups once; a preferred group changes only the reading link. When an exact next URL is unknown, open the ToC. A generic URL-template requirement, repeated chapter probing, and a mandatory browser for every check were rejected. REQ-005, REQ-011, REQ-015, REQ-016.

## D-022 — Enable the guarded Comix group lookup on the Pi (2026-10-06)

Allowlist `comix.to` only after a bounded browser request returned HTTP 200 with 20 chapter and group rows, the deployed adapter read a matching group link, and the Pi retained about 3 GiB available RAM with no swap use. Keep direct series metadata as the normal check path; invoke the browser only when a preferred group is set. The host Compose change has a saved copy under `/srv/keihub/rollback/`, and a verified encrypted backup followed activation. A global browser option and browser lookup for every Comix check were rejected because they add latency and Pi load. REQ-015, REQ-016.

## D-023 — Preview the selected checker and recheck saved changes (2026-10-06)

Make the ToC test run the currently selected checker. The earlier panel always used Comix metadata even when an item was explicitly saved with generic ToC, showing a misleading OK while scheduled checks returned EMPTY. Keep explicit overrides meaningful, warn when generic ToC is selected for Comix, and offer a direct switch to its dedicated checker. A chapter example remains optional and cannot invent links absent from ToC HTML. Changing checker settings removes the prior method's issue and starts one new check with visible feedback; unchanged settings preserve their issue. Default new items to a six-hour interval without changing existing records. Silently changing the saved override or treating a successful preview as proof of the selected method were rejected. REQ-004, REQ-005, REQ-013, REQ-016.

## D-024 — Allow hidden creation and distinguish Webtoons episode labels (2026-10-06)

Let an owner create or mark an entry sensitive with safe view on; it disappears from normal reads after saving. Keep the generic ToC scanner host-neutral: scope common list pages by path and shared query values, use a manual chapter URL regex when supplied, and retain the real matched link. A path chapter number and query chapter ID can differ, so do not generate or use a one-placeholder probe template from such a URL, including for older saved patterns. The Webtoons Episode 393 / `episode_no=412` case is a regression fixture, not a special scanner branch. A pending result clears a prior check error, and acceptance advances the latest baseline without permanently trusting that source. Requiring reveal before creation and ignoring the saved ToC regex were rejected. REQ-003, REQ-005, REQ-008, REQ-011, REQ-016.

## D-025 — Example guided links outside the ToC path (2026-10-06)

Some series ToCs live under `/manga/series-slug/` while their chapter pages live at `/series-slug-chapter-N/`. The ToC path must not be used to infer the outside-path chapter pattern. Derive it from the supplied chapter URL example by varying only the detected chapter number; include that example in preview and persist it as a ToC hint. Older items can reconstruct the pattern from their example-derived URL template. Keep the visible-label cross-check, recommendation exclusion, and no-probe-on-issue rule. A Hentai20-only adapter, a broad same-host chapter search, and inference from the `/manga/` slug were considered; explicit examples give the owner control over which link shape belongs to the series. REQ-004, REQ-005, REQ-016.

## D-026 — WebNovel embedded catalog (2026-10-07)

Use a dedicated WebNovel adapter to read the book-scoped catalog embedded in the About page, even though chapter rows are shown under a separate tab. A direct request receives a Cloudflare challenge in local tests; the guarded FlareSolverr service returned the catalog for the sample book and a second short book. Use the catalog's `chapterIndex` and opaque `chapterId`, cross-check identity and latest entry, and cap the response at 5 MB. The saved sample has 89 entries including an auxiliary row, a latest index of 88, and a title containing 85, so neither total count nor title is a safe chapter number. A long book exceeded a smaller 2.5 MB test cap but parsed at 2.65 MB under the final 5 MB cap, yielding chapter 2128; larger pages remain an explicit issue. Sequential probing and reliance on an undocumented third-party API were rejected. Enable `www.webnovel.com` in local development for review; Pi allowlisting requires a separate release review. REQ-015, REQ-017.

## D-027 — Royal Road fiction ID and catalog order (2026-10-07)

Use the numeric fiction ID as the stable source key and retain the current slug only in verified chapter links. Royal Road's direct fiction page returned a Cloudflare 403 locally; guarded FlareSolverr returned a page with only 20 rendered rows but a complete embedded `window.chapters` array. The saved modern page also embeds that array. Number releases initially by the array's zero-based `order` plus one; volume titles restart and the sample's final post is an art contest, so title numbers cannot define progress. The Game at Carousel `/fiction/65629` has only early chapters followed by a jump to Book Five in its current catalog, showing that stubbing removes entries and shifts later indices. Preserve the accepted number using the previous latest chapter ID as the anchor, then count entries after it. If that ID disappears, require review. The public RSS feed is reachable directly but contains ten latest links without their full-series positions, so it is not the primary checker. Validate contiguous order and scoped IDs/URLs; fail visibly for incomplete catalogs. Generic URL probing, relying on title slugs, and treating the first rendered page as the latest were rejected. Local allowlisting precedes any separate Pi decision. REQ-015, REQ-018.

## D-028 — Scribble Hub first-page order (2026-10-07)

Use the numeric series ID as the source key and the first ToC page's explicit row order as the release position. The supplied page declares 126 entries and its newest row is order 126, while the title says Chapter 125; title numbers and opaque chapter IDs are unsuitable for progress. The site's page selector uses JavaScript pagination, but its default first page already contains the latest rows. One guarded browser request after the observed direct Cloudflare 403 returned the same series-scoped links and count. Validate count, selected page size, descending order, and series link identity; treat a changed latest chapter ID at the same count as a check issue, while allowing a title slug change around the same ID. Fetching every older AJAX page, sequential probing, and inferring an ID from the title were rejected. This host is allowlisted locally for review only. REQ-015, REQ-019.

## D-029 — Editable Novel default (2026-10-07)

Suggest the existing `Novel` category for new FreeWebNovel, WebNovel, Royal Road, and Scribble Hub entries using their URL recognizers. A user may choose any category or no category. API omission receives the default; explicit `null` means none. Keep existing records and imports unchanged. Automatically reclassifying old entries or inferring categories from scraped titles was rejected because those would overwrite personal organization. REQ-020.

## D-030 — One mark across tracker and hub (2026-10-08)

Use a generated open-book and blue bookmark mark as the common tracker identity. Derive the favicon and manifest PNGs from the transparent source so they remain visually consistent. Keep a separate subdued dark card background for optional KeiHub upload. Store these as static files and leave hub assignment to the owner; the tracker does not need access to KeiHub's database or upload API. REQ-021.

## D-031 — Separate publishing and reading completion (2026-10-08)

Store one lifecycle status with Ongoing, Paused, Completed, and Finished. Completed represents a manual publishing decision and keeps unread work in the queue; Finished represents an explicit reading decision after catching up. Keep chapter progress and latest known chapter in their own fields. Only Ongoing gets scheduled or Check All polling. Manual checks remain possible for Completed and Finished; a newly discovered chapter reopens Finished as Completed. Saved filters select statuses directly, while the old include-inactive flag remains a compatibility field. We rejected automatic completion from scraper metadata because source signals vary, and automatic finishing at the latest chapter because catching up does not mean the owner is done. REQ-022.

## D-032 — Comix extraction in Add preview (2026-10-08)

The Add review step invokes the guarded Comix checker after a direct Cloudflare challenge when the Comix host is explicitly browser-allowlisted. A separate direct-only access test can still report a challenge; the preview reports browser reachability only after valid Comix series metadata is extracted. This aligns Add with Test selected checker without enabling browser fetching for URL probing or general diagnostics. REQ-004, REQ-006, REQ-015, REQ-016.

## D-033 — Reviewed Pi release and browser hosts (2026-10-08)

Publish commit `1a63471` through KeiHub's exact-commit CI gate after the user reviewed the local status and Comix changes. The live Compose environment was inspected and already allowlisted FreeWebNovel, Comix, WebNovel, Royal Road, and Scribble Hub. Keep its loopback-only API, internal browser network, public-only proxy, and serialized checks. An encrypted USB backup and isolated eight-item database-and-covers migration/rollback rehearsal preceded the live additive migration. The Pi passed post-release integrity and HTTPS checks, and its Comix preview returned chapter 121 through the browser. Other newly released adapters were covered by fixtures and prior local live checks; their Pi source checks were not repeated in this release. REQ-015–REQ-022.
