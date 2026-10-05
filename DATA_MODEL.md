# Data model

SQLite is authoritative. Use additive Alembic migrations and preserve current IDs, URLs, progress, and logs. Inventory existing `user_id` values before assigning legacy unowned items to the initial admin.

| Entity | Fields and constraints |
|---|---|
| `User` | UUID, unique username, optional unique email, password hash, admin/active flags, timestamps. No credentials in exports or logs. |
| `Invite` | UUID, creator, hashed random token, 24-hour expiry, used timestamp, optional intended username. One use. |
| `Session` | Hashed random token, user, expiry, revoked timestamp, CSRF secret, safe-view flag default true. Revoke on logout/reset. |
| `TrackedItem` | Existing UUID, URL, template, regex, category, progress, interval, active and timestamps, owner FK. Add canonical series URL, checker override, `is_sensitive`, short note, opaque cover filename, pending chapter/link, dismissed candidate, last outcome. Owner required after migration; duplicate URLs are checked per owner on import. |
| `ChapterCheckLog` | Existing item FK, time, before/after, success/error. Add typed outcome and pending candidate for auditing. |

Chapter labels remain strings to preserve decimals and suffixes. Strict decimal comparison governs jump policy; incomparable labels need review. `latest_chapter` is accepted, `pending_latest_chapter` awaits action. Canonical series URL identifies the series independently of the submitted chapter URL. URL normalization strips fragments and routine tracking parameters without merging distinct series.

Covers have generated filenames outside the public static tree. Authorize file reads against owner/admin and safe view. Delete old files only after a successful database commit. The versioned ZIP holds JSON entries and referenced covers, never users or secrets. Validate archive paths, count, total size, JSON, images, and duplicates before import. Full operational restore uses a consistent SQLite snapshot, complete cover directory, and matching application revision.
