# History capture design

**Date:** 2026-04-20
**Status:** Design, implementation pending
**Author:** Alex Towell (with Claude)

## Motivation

bookmark-memex stores *curated* bookmarks, the URLs the user has explicitly
elected to keep. This spec adds a second, distinct layer: the full browser
**history**, as observational data.

The two serve different questions:

| Layer | Semantics | Example questions |
|-------|-----------|-------------------|
| Bookmarks | Curation, intent | "Things I've saved for later" |
| History | Observation, behaviour | "What was I reading Tuesday at 3pm?" "Which domains am I drifting away from?" "Which URLs have I visited 100+ times but never bookmarked?" |

History is **much larger, more sensitive, and more temporal** than bookmarks.
The design here reflects all three properties.

## Design principles

1. **Distinct storage.** History never writes to `bookmarks`. Queries on
   `bookmarks` never implicitly include history. Cross-queries are explicit
   joins.
2. **Two-layer model**, mirroring Chrome and Firefox: per-URL aggregate
   (`history_urls`) plus per-event visits (`history_visits`). Chrome and
   Firefox both already split the data this way; flattening would discard
   the temporal signal that motivates capture in the first place.
3. **Rolling updates by default.** Importing history from the same browser
   profile twice is idempotent. No "since when" bookmarks to keep on the
   client side; dedup is enforced at the schema layer.
4. **Capture outlives the browser.** Chrome expires history after 90 days
   by default. Captured visits survive independently in the memex archive.
5. **Privacy-first defaults.** Exports (arkiv, HTML SPA) exclude history
   unless an explicit opt-in flag is passed. Tracking params are stripped
   at ingest.
6. **Observational, not curatorial.** No content caching for history URLs.
   No folder tags. No stars, pins, or queues. Visits are events, not
   artefacts.

## Schema

Two new tables plus one FTS5 virtual table. No changes to existing tables.

### `history_urls`

One row per unique URL ever observed in history, per the usual memex
`unique_id` dedup.

```sql
CREATE TABLE history_urls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id       TEXT    UNIQUE NOT NULL,   -- sha256(normalize(url))[:16]
    url             TEXT    UNIQUE NOT NULL,   -- canonical form from normalize_url()
    title           TEXT,                      -- latest observed title
    first_visited   TIMESTAMP,                 -- min(visited_at) across all visits
    last_visited    TIMESTAMP,                 -- max(visited_at) across all visits
    visit_count     INTEGER NOT NULL DEFAULT 0,
    typed_count     INTEGER NOT NULL DEFAULT 0,  -- Chrome only; visits that were typed
    media           JSON,                      -- populated by run_detectors() on first sight
    extra_data      JSON,
    archived_at     TIMESTAMP                  -- soft delete
);

CREATE INDEX idx_history_urls_last_visited ON history_urls(last_visited DESC);
CREATE INDEX idx_history_urls_visit_count  ON history_urls(visit_count DESC);
```

Notes:
- `visit_count` and `last_visited` are **derived** from `history_visits`.
  We recompute them in a trigger on insert / update / delete into visits,
  so both tables stay consistent without the caller having to remember.
- `media` runs once per URL, not once per visit (detectors are URL-shaped).
- `typed_count` is Chrome-specific (Firefox has `typed` as a boolean on
  `moz_places`, not a count). For Firefox imports the column is populated
  from the `typed` flag as either 0 or ≥1, best-effort.

### `history_visits`

One row per observed visit event. Expect tens of thousands per year of
moderate browsing.

```sql
CREATE TABLE history_visits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id       TEXT    UNIQUE NOT NULL,  -- uuid4 hex; stable across reimports via UNIQUE(url_id, visited_at, source_type, source_name)
    url_id          INTEGER NOT NULL REFERENCES history_urls(id) ON DELETE CASCADE,
    visited_at      TIMESTAMP NOT NULL,
    duration_ms     INTEGER,                   -- Chrome only; Firefox stores nothing equivalent
    transition      TEXT,                      -- normalised: 'link' | 'typed' | 'bookmark' | 'reload' | 'redirect' | 'generated' | 'subframe' | 'form_submit' | 'download' | 'other'
    from_visit_id   INTEGER REFERENCES history_visits(id) ON DELETE SET NULL,  -- referrer chain
    source_type     TEXT    NOT NULL,          -- 'chrome' | 'firefox'
    source_name     TEXT    NOT NULL,          -- 'Chrome/Default' | 'Firefox/default-release'
    imported_at     TIMESTAMP NOT NULL,
    archived_at     TIMESTAMP,

    UNIQUE(url_id, visited_at, source_type, source_name)
);

CREATE INDEX idx_history_visits_visited_at        ON history_visits(visited_at DESC);
CREATE INDEX idx_history_visits_url_id_visited_at ON history_visits(url_id, visited_at DESC);
CREATE INDEX idx_history_visits_source            ON history_visits(source_type, source_name);
```

Notes:
- `UNIQUE(url_id, visited_at, source_type, source_name)` is the dedup
  contract for rolling imports. Re-importing the same Chrome profile is
  a no-op for visits we've already seen.
- `from_visit_id` preserves the referrer chain Chrome tracks natively.
  Firefox tracks referrers per-visit too. When a referrer visit isn't in
  our DB (it may have been pruned by the browser before we captured it),
  `from_visit_id` stays `NULL`.
- `ON DELETE CASCADE` on `url_id` is deliberate: deleting a
  `history_urls` row (e.g. GDPR-style purge of a specific site) deletes
  its visits. Marginalia on the URL survives per the ecosystem's
  `ON DELETE SET NULL` rule (see below).
- `transition` is normalised to a small string enum across Chrome's
  bit-packed `visits.transition` field and Firefox's `moz_historyvisits.visit_type`
  numeric enum. Both map to our 9-value enum above. Source-specific raw
  values can go in `extra_data` on the URL if ever needed.

### `history_urls_fts`

```sql
CREATE VIRTUAL TABLE history_urls_fts USING fts5(
    title, url,
    content='history_urls',
    content_rowid='id'
);
```

Keeps titles searchable alongside URL text. No FTS on visits (visits are
event rows, not content).

### Marginalia

The existing `marginalia` table gets two optional FK columns added, or
marginalia extend to history records via the existing `bookmark_id` being
renamed to `record_id` with a `record_kind` discriminator. Prefer the
latter for consistency with the workspace's URI scheme, but flag this as
a migration decision; the safest minimal change is to leave the existing
`bookmark_id` column alone and add:

```sql
ALTER TABLE marginalia ADD COLUMN history_url_id INTEGER
    REFERENCES history_urls(id) ON DELETE SET NULL;
ALTER TABLE marginalia ADD COLUMN history_visit_id INTEGER
    REFERENCES history_visits(id) ON DELETE SET NULL;
CHECK ((bookmark_id IS NOT NULL) + (history_url_id IS NOT NULL) + (history_visit_id IS NOT NULL) <= 1);
```

(SQLite doesn't enforce `CHECK` across ALTER, so the constraint is
advisory; db.py enforces it on insert.) This is additive and preserves
the orphan-survival semantics: deleting any record kind leaves the note
intact with a NULL pointer.

An even cleaner long-term refactor (a unified `urls` table that both
bookmarks and history_urls reference) is called out as out-of-scope
below.

## URI scheme

```
bookmark-memex://history-url/<unique_id>       -- aggregate URL record
bookmark-memex://visit/<unique_id>             -- individual visit event
bookmark-memex://marginalia/<uuid>             -- unchanged; now attachable to any of the three kinds
```

Rationale per the root `~/github/memex/CLAUDE.md` rule: positions within a
record use fragments, but **visits have their own lifecycle** (timestamps,
referrer chains, marginalia, export boundaries), so they warrant a
separate URI kind rather than being fragments on `history-url/`.

## Import flow

Two new subcommands. They re-use `_copy_database`,
`_chrome_timestamp_to_datetime`, and `_firefox_timestamp_to_datetime` from
the existing `browser.py`.

```
bookmark-memex import-history --browser chrome [--profile Default] [--since ISO-DATE] [--strip-tracking/--no-strip-tracking]
bookmark-memex import-history --browser firefox [...]
bookmark-memex import-history --list                 # reuse list_browser_profiles()
```

### Chrome

Source: `<profile>/History` (SQLite, locked when Chrome runs; copy first).

```sql
SELECT v.id, v.visit_time, v.from_visit, v.transition, v.visit_duration,
       u.url, u.title, u.typed_count
FROM   visits v
JOIN   urls u ON u.id = v.url
WHERE  (? IS NULL OR v.visit_time > ?)   -- --since filter in Chrome-time microseconds
ORDER  BY v.visit_time ASC;
```

Per row:
1. Normalise URL via `normalize_url()`.
2. Optionally strip tracking params (see below).
3. Compute `unique_id = sha256(normalize(url))[:16]`.
4. Upsert `history_urls` (insert if absent; leave aggregates to the
   post-insert trigger).
5. Decode Chrome's transition bitfield to the 9-value enum.
6. `INSERT OR IGNORE` into `history_visits` with the dedup tuple.
7. Resolve `from_visit_id` in a second pass (once all visits in this
   batch are inserted, we can map Chrome's internal `from_visit` IDs
   to our `history_visits.id`).

### Firefox

Source: `<profile>/places.sqlite` (the same DB the bookmarks importer
already reads).

```sql
SELECT h.id, h.visit_date, h.from_visit, h.visit_type,
       p.url, p.title, p.typed
FROM   moz_historyvisits h
JOIN   moz_places p ON p.id = h.place_id
WHERE  (? IS NULL OR h.visit_date > ?)
ORDER  BY h.visit_date ASC;
```

Same mapping steps as Chrome, except:
- Timestamps: Firefox uses Unix-epoch microseconds (not 1601-epoch).
- Transition: Firefox's 9-value enum maps 1:1 to our normalised enum.
- `duration_ms` stays `NULL`.

### Return shape

Follows the `ImportResult` pattern already established for bookmarks:

```python
class HistoryImportResult(NamedTuple):
    urls_seen:       int   # raw URL rows processed
    urls_added:      int   # new history_urls created
    urls_updated:    int   # existing history_urls whose aggregates moved
    visits_seen:     int   # raw visit rows processed
    visits_added:    int   # new history_visits inserted
    visits_skipped:  int   # dedup hits (INSERT OR IGNORE)
```

CLI prints all six.

## Rolling updates

The dedup contract is `UNIQUE(url_id, visited_at, source_type, source_name)`.
A weekly cron of `bookmark-memex import-history --browser chrome` is
idempotent and cheap:

- New visits since the last import land via `INSERT OR IGNORE`.
- Visits we already have silently skip.
- Visits pruned from the browser's DB (Chrome's 90-day expiry) stay in
  our DB forever (until the user explicitly archives / purges).

There is **no "last imported at" timestamp persisted client-side**. The
`--since` flag is offered as an optimisation (it lets the source-side
query skip most rows cheaply) but isn't required for correctness.

## Retention and privacy

### Tracking parameter stripping

`normalize_url()` currently lowercases, removes default ports, sorts query
params, and strips trailing slashes. It does **not** strip tracking params.

For history, this matters more than for bookmarks: every distinct
`?utm_campaign=foo&utm_source=bar` version of the same page becomes its
own `history_urls` row, fragmenting the dedup.

Proposed additional normalisation (opt-out via `--no-strip-tracking`):

- Drop `utm_*` params (`utm_source`, `utm_medium`, `utm_campaign`,
  `utm_term`, `utm_content`, `utm_id`, `utm_name`)
- Drop common trackers: `gclid`, `fbclid`, `msclkid`, `mc_eid`, `mc_cid`,
  `_hsenc`, `_hsmi`, `ref`, `ref_src`, `igshid`
- Drop YouTube `t=` when it's 0 (spurious timestamp)

This lives in a new `normalize_url_for_history()` helper rather than
modifying `normalize_url()`. Bookmarks should stay honest about the
exact URL the user saved; history should aggressively canonicalise.

### Export defaults

- `bookmark-memex export --format arkiv ...`: excludes history by
  default. `--include-history` adds `history_url` and `visit` records
  to the arkiv bundle.
- HTML SPA export: same default.
- `bookmark-memex sql`: query any table; SQL is the "power user"
  surface and doesn't need a guard.
- `bookmark-memex export --format json`: bookmarks only, unless
  `--include-history`.

### Retention knobs

Out of scope for v1. The soft-delete `archived_at` column gives us the
mechanism; policy knobs like `--retain-days N` or "summarise and purge"
are worth adding once we have a month of real data to inform defaults.

## Query examples this enables

```sql
-- URLs visited 50+ times but never bookmarked (promotion candidates)
SELECT h.url, h.title, h.visit_count
FROM   history_urls h
LEFT   JOIN bookmarks b ON b.unique_id = h.unique_id
WHERE  h.visit_count >= 50
  AND  b.id IS NULL
  AND  h.archived_at IS NULL
ORDER  BY h.visit_count DESC;

-- Bookmarks I saved more than a year ago but never revisited (stale)
SELECT b.url, b.title, b.added
FROM   bookmarks b
LEFT   JOIN history_urls h ON h.unique_id = b.unique_id
WHERE  b.added < datetime('now', '-365 days')
  AND  (h.last_visited IS NULL OR h.last_visited < b.added)
  AND  b.archived_at IS NULL;

-- "What was I reading on 2026-04-12?"
SELECT u.url, u.title, v.visited_at, v.transition
FROM   history_visits v
JOIN   history_urls u ON u.id = v.url_id
WHERE  v.visited_at BETWEEN '2026-04-12 00:00:00' AND '2026-04-12 23:59:59'
  AND  v.archived_at IS NULL
ORDER  BY v.visited_at;

-- Visit velocity to a domain, weekly buckets
SELECT strftime('%Y-W%W', v.visited_at) AS week,
       COUNT(*)                         AS visits
FROM   history_visits v
JOIN   history_urls u ON u.id = v.url_id
WHERE  u.url LIKE 'https://news.ycombinator.com/%'
GROUP  BY week
ORDER  BY week;

-- Referrer chains that led to bookmarked URLs
SELECT pu.url AS source_url, bu.url AS bookmark_url, v.visited_at
FROM   history_visits   v
JOIN   history_urls     bu ON bu.id = v.url_id
JOIN   bookmarks        b  ON b.unique_id = bu.unique_id
JOIN   history_visits   pv ON pv.id = v.from_visit_id
JOIN   history_urls     pu ON pu.id = pv.url_id
WHERE  v.archived_at IS NULL
ORDER  BY v.visited_at DESC;
```

## Out of scope (candidate v2 work)

1. **Shared `urls` table.** Principled refactor: one `urls` table with
   bookmarks and history_urls both referencing it. Makes cross-queries
   cheaper (no join on `unique_id`) and makes content caching apply
   uniformly. Cost: schema migration touches every part of the codebase.
   Defer until cross-queries are frequent enough to justify the churn.
2. **Content caching for history URLs.** Would balloon the DB size by 10x to 100x on a
   full history import. Genuinely observational data shouldn't carry
   per-row content blobs. Revisit if a specific question needs it.
3. **Retention policies.** `--retain-days`, "summarise and purge", per-
   domain rules. Add once real data informs the design.
4. **Live capture via browser extension.** The browser history DB is
   authoritative enough. A WebExtension listener would add complexity
   (packaging, permissions, install flow) without a clear quality win.
5. **Safari / Edge / Brave history.** Edge and Brave already work if
   `--browser chrome` auto-detects their profile paths (they share the
   Chrome `History` schema). Safari uses a different SQLite schema
   (`History.db` with `history_items` + `history_visits`) and would need
   a third importer class; defer until asked.

## Implementation plan

Target for part (c) after this doc lands:

1. **Schema + migrations**: new tables, FTS, triggers for derived
   aggregates. Migration is additive; no existing-data changes. Extend
   the `ON DELETE SET NULL` marginalia FK set.
2. **`ChromeHistoryImporter` + `FirefoxHistoryImporter`** classes in
   `bookmark_memex/importers/browser_history.py`, subclassing a shared
   base that handles the profile-copy dance already in `browser.py`.
3. **`import_history()` top-level function** returning
   `HistoryImportResult`.
4. **`normalize_url_for_history()`** with the tracking-param strip list.
5. **`import-history` CLI subcommand**: `--browser`, `--profile`,
   `--since`, `--strip-tracking/--no-strip-tracking`, `--list`.
6. **MCP `get_record` extension** for the two new URI kinds.
7. **`arkiv` exporter opt-in**: `--include-history` adds `history_url`
   and `visit` kinds.
8. **Tests** (target parity with the 24 browser-import tests):
   - Chrome history parsing (flat, transition decoding, from_visit chain)
   - Firefox history parsing (timestamp epoch, visit_type mapping)
   - Rolling-update idempotence (`import → import → counts match`)
   - Tracking param stripping (default on)
   - URL dedup across browsers
   - CLI integration

Each step is an independent PR if desired. The minimum useful slice is
1 + 2 + 3 + 5: schema, Chrome importer, CLI. Tests land with (2).

## Open questions

- **Should the existing `bookmarks.visit_count` and `last_visited` be
  derived from `history_visits`?** Currently they're populated by a
  `visit()` CLI that no one calls. If they were views over history, the
  "bookmark but never visited" query becomes cheap. Counter-argument:
  bookmarks were visited before they were bookmarked, and history
  capture is retroactive only back to whatever the browser still has.
  Probably leave as-is; revisit with the shared-`urls` refactor.
- **Should marginalia on a `visit` survive visit archival?** Per the
  ecosystem rule it should. The `ON DELETE SET NULL` applies to
  marginalia on archived/deleted visits too. Flag for code review when
  implementing.
- **Export one bundle or two?** Arkiv-bundle-with-history could be huge.
  Consider `bookmark-memex export --format arkiv --what history` to
  emit history-only bundles for separate sharing / storage.
