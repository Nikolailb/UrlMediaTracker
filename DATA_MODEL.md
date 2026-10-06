# Data model

SQLite is authoritative. Use additive Alembic migrations and preserve current IDs, URLs, progress, and logs. Inventory existing `user_id` values before assigning legacy unowned items to the initial admin.

| Entity | Fields and constraints |
|---|---|
| `User` | UUID, unique username, optional unique email, password hash, admin/active flags, timestamps. No credentials in exports or logs. |
| `Invite` | UUID, creator, hashed random token, 24-hour expiry, used timestamp, optional intended username. One use. |
| `Session` | Hashed random token, user, expiry, revoked timestamp, CSRF secret, safe-view flag default true. Revoke on logout/reset. |
| `TrackedItem` | Existing UUID, URL, template, regex, category, progress, interval, active and timestamps, owner FK. Add canonical series URL, checker override, `is_sensitive`, short note, opaque cover filename, pending chapter/link, dismissed candidate, last outcome. Owner required after migration; duplicate URLs are checked per owner on import. |
| `ChapterCheckLog` | Existing item FK, time, before/after, success/error. Add typed outcome and pending candidate for auditing. |
| `FilterPreset` | UUID, owner FK, unique case-insensitive name per owner, JSON category list using existing category values, unread-only flag, include-inactive flag, sort key and direction, creation/update timestamps. Built-ins are virtual and cannot be modified. Delete custom presets with their owner. |

Chapter labels remain strings to preserve decimals and suffixes. Strict decimal comparison governs jump policy; incomparable labels need review. `latest_chapter` is accepted, `pending_latest_chapter` awaits action. Canonical series URL identifies the series independently of the submitted chapter URL. URL normalization strips fragments and routine tracking parameters without merging distinct series.

The optional chapter URL example in the add request is transient: the derived `url_template` and `chapter_regex` are stored on `TrackedItem`, while the example chapter number is not saved as progress or latest. The submitted first URL remains `original_url` and becomes `toc_url` by default when an example is supplied. An explicit ToC URL takes priority. REQ-004.

REQ-016 adds nullable `latest_chapter_url` and `first_chapter_url` for verified direct links; `preferred_group` for choosing among duplicate chapter links; `toc_examples_json` for up to two chapter URL hints; `toc_row_class` derived from an optional copied row snippet; and `toc_latest_page_url` for a confirmed latest page in an ascending ToC. The snippet itself is not stored. The highest chapter across all groups is still one `latest_chapter` value. A pending suspicious result keeps its candidate URL in the existing `pending_chapter_url`, and acceptance promotes that URL to `latest_chapter_url`. All six new columns are added through Alembic and are optional for legacy rows. Account ZIP import/export includes them. The stored direct link is used only for the matching chapter; unknown intermediate links fall back to the ToC.

Changing detection fields resets `last_outcome`, `last_error`, `consecutive_failures`, and `last_checked_at` because the previous status belongs to a different method. It also clears pending results from the old method; accepted latest and reading progress are preserved. `check_config_changed` is a response-only flag for the edit action and is not stored. New items use 360 minutes when no interval is supplied; existing rows keep their own interval.

The accepted `latest_chapter` remains the baseline after a pending result is resolved. No permanent site-trust flag is stored; each later jump is evaluated against that baseline. Independent viewer IDs remain part of verified URLs only and are not stored as chapter numbers. A manual regex is already stored in `chapter_regex` and can guide ToC extraction without a `url_template`. These corrections require no schema migration.

Covers have generated filenames outside the public static tree. Authorize file reads against owner/admin and safe view. Delete old files only after a successful database commit. The versioned ZIP holds JSON entries, custom presets, and referenced covers, never users or secrets. Version 1 archives may omit `presets.json` for compatibility with earlier exports. Validate archive paths, count, total size, JSON, images, and duplicates before import. Full operational restore uses a consistent SQLite snapshot, complete cover directory, and matching application revision.
