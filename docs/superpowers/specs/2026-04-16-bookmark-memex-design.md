# bookmark-memex Design Spec

Clean break from btk/bookmark-tk. New package `bookmark-memex` satisfying the
memex archive contract. Old `bookmark-tk` stays on PyPI frozen.

## Scope

**In scope (v1):**

- Bookmarks + hierarchical tags + marginalia (memex contract)
- Content caching with FTS5 (longevity, searchability)
- Media detector auto-discovery framework
- Browser import (Chrome/Firefox) + file import (HTML/JSON/CSV/Markdown/text)
- Health checking (URL reachability, dead link detection)
- Reading queue (priority, progress, "next" flow)
- MCP server (6 tools, memex contract)
- Arkiv export + HTML-app export (directory default, `--single` for embedded)
- Live web UI for browsing, queue management, visit tracking
- Soft delete (`archived_at`), durable IDs, URI scheme

**Out of scope:**

- Views DSL (dropped)
- Graph analysis (dropped)
- Generic plugin system (dropped; detector auto-discovery covers extensibility)
- Auto-tagging NLP (deferred; LLM can tag via MCP)
- Collections table (tags serve this purpose)
- Satellite tables for visits/media (flattened)
- Backward compatibility with btk

## Architecture: Selective Port

New package structure, new schema, new MCP server, new CLI. Proven modules
ported from btk where they handle real edge cases:

| Ported from btk | Purpose |
|-----------------|---------|
| content_fetcher.py | HTTP fetch with timeouts, retries, encoding detection |
| content_cache.py | zlib compress/decompress, store/retrieve |
| content_extractor.py | HTML to markdown to plain text extraction, PDF text |
| importers/file_importers.py | Netscape HTML, JSON, CSV, Markdown, text parsing |
| html_app export + assets/ | sql.js WASM integration, DB subsetting, ID remapping |
| tag_utils.py | Hierarchical tag operations (parent paths, tree building) |
| fts.py | FTS5 index creation, sync triggers, search helpers |
| utils.py | URL normalization, SHA256 ID generation, favicon download |

Everything else written fresh: schema, models, db.py, MCP server, CLI,
config, serve.py, detector framework, arkiv exporter, URI module, soft delete.

## Schema

Seven tables plus three FTS5 virtual tables.

### bookmarks

Core record table. Health check fields and media metadata live here directly
(no satellite tables). Media is a JSON column populated by detectors.

```sql
CREATE TABLE bookmarks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id         TEXT    UNIQUE NOT NULL,  -- sha256(normalize(url))[:16]
    url               TEXT    UNIQUE NOT NULL,
    title             TEXT    NOT NULL,
    description       TEXT,
    bookmark_type     TEXT    NOT NULL DEFAULT 'bookmark',  -- bookmark, history, tab, reference
    added             TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_visited      TIMESTAMP,
    visit_count       INTEGER NOT NULL DEFAULT 0,
    starred           BOOLEAN NOT NULL DEFAULT 0,
    pinned            BOOLEAN NOT NULL DEFAULT 0,
    reachable         BOOLEAN,               -- null = unchecked
    last_checked      TIMESTAMP,
    status_code       INTEGER,
    favicon_data      BLOB,
    favicon_mime_type TEXT,
    media             JSON,                  -- populated by detectors
    extra_data        JSON,                  -- extensible metadata
    archived_at       TIMESTAMP              -- null = active, set = soft-deleted
);

CREATE INDEX ix_bookmarks_unique_id ON bookmarks(unique_id);
CREATE INDEX ix_bookmarks_url ON bookmarks(url);
CREATE INDEX ix_bookmarks_added_desc ON bookmarks(added DESC);
CREATE INDEX ix_bookmarks_starred ON bookmarks(starred);
CREATE INDEX ix_bookmarks_pinned ON bookmarks(pinned);
CREATE INDEX ix_bookmarks_bookmark_type ON bookmarks(bookmark_type);
CREATE INDEX ix_bookmarks_archived_at ON bookmarks(archived_at);
```

### tags

Hierarchical via `/` separator. No `description` column (btk had it; nobody used it).

```sql
CREATE TABLE tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL,
    color TEXT
);

CREATE INDEX ix_tags_name ON tags(name);
```

### bookmark_tags

Junction table. Many-to-many.

```sql
CREATE TABLE bookmark_tags (
    bookmark_id INTEGER NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (bookmark_id, tag_id)
);

CREATE INDEX ix_bookmark_tags_tag_id ON bookmark_tags(tag_id);
```

### bookmark_sources

Import provenance. One bookmark can have multiple sources (imported from Chrome
AND Firefox AND a bookmarks.html file). Preserves folder hierarchy and raw
source data for lossless round-trip.

```sql
CREATE TABLE bookmark_sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmark_id  INTEGER NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    source_type  TEXT    NOT NULL,  -- chrome, firefox, safari, html_file, json_file, csv_file, manual, mcp
    source_name  TEXT,              -- profile display name, filename
    folder_path  TEXT,              -- original folder hierarchy from source
    imported_at  TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    raw_data     JSON               -- lossless preservation of source fields
);

CREATE INDEX ix_bookmark_sources_bookmark_id ON bookmark_sources(bookmark_id);
CREATE INDEX ix_bookmark_sources_source_type ON bookmark_sources(source_type);
```

### content_cache

Cached page content for offline viewing and FTS. HTML stored zlib-compressed.
`extracted_text` is the FTS-ready plain text derived from markdown/HTML.

```sql
CREATE TABLE content_cache (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmark_id       INTEGER UNIQUE NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    html_content      BLOB,           -- zlib-compressed
    markdown_content  TEXT,
    extracted_text    TEXT,            -- plain text for FTS indexing
    content_hash      TEXT,
    content_length    INTEGER NOT NULL DEFAULT 0,
    compressed_size   INTEGER NOT NULL DEFAULT 0,
    fetched_at        TIMESTAMP NOT NULL,
    content_type      TEXT,
    archived_at       TIMESTAMP
);

CREATE INDEX ix_content_cache_bookmark_id ON content_cache(bookmark_id);
```

### annotations

Marginalia per the memex contract. UUID primary key for durable cross-archive
URIs. `ON DELETE SET NULL` on bookmark_id so annotations survive bookmark
deletion (orphan survival).

```sql
CREATE TABLE annotations (
    id          TEXT PRIMARY KEY,  -- uuid hex, durable
    bookmark_id INTEGER REFERENCES bookmarks(id) ON DELETE SET NULL,
    text        TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    archived_at TIMESTAMP
);

CREATE INDEX ix_annotations_bookmark_id ON annotations(bookmark_id);
```

### events

Audit log for tracking operations.

```sql
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT,
    timestamp   TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    event_data  JSON
);

CREATE INDEX ix_events_type ON events(event_type);
CREATE INDEX ix_events_timestamp ON events(timestamp DESC);
```

### schema_version

Lightweight migration tracking. No Alembic.

```sql
CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    description TEXT
);
```

### FTS5 virtual tables

```sql
CREATE VIRTUAL TABLE bookmarks_fts USING fts5(
    title, description, url,
    content=bookmarks, content_rowid=id
);

CREATE VIRTUAL TABLE content_fts USING fts5(
    extracted_text,
    content=content_cache, content_rowid=id
);

CREATE VIRTUAL TABLE annotations_fts USING fts5(
    text,
    content=annotations
);
```

Triggers keep FTS in sync on INSERT/UPDATE/DELETE against the content tables.

### Reading queue

Not a separate table. Stored in `bookmarks.extra_data` JSON:

```json
{
    "queue_position": 3,
    "queue_added_at": "2026-04-16T10:00:00Z",
    "queue_priority": "high"
}
```

Bookmarks in the queue: `extra_data->>'queue_position' IS NOT NULL`.
Ordered by: `extra_data->>'queue_priority'` (high=0, medium=1, low=2),
then `CAST(extra_data->>'queue_position' AS INTEGER)`.
The web UI and MCP `mutate` ops manage these fields.

### Deduplication on import

URL uniqueness enforced by `unique_id` (sha256 of normalized URL). When a
browser import encounters a URL already in the database:

1. The existing bookmark is kept (no overwrite).
2. A new `bookmark_sources` row is added (preserving the new folder path and source).
3. Tags from the new source are merged (union) with existing tags.
4. If the existing bookmark has no title but the new source does, the title is updated.

This handles the case where the same URL appears in multiple browser folders:
one bookmark record, multiple source rows, union of all folder-derived tags.

## Package Structure

```
bookmark_memex/
    __init__.py
    cli.py
    config.py
    db.py
    models.py
    mcp.py
    serve.py
    uri.py
    fts.py
    soft_delete.py

    importers/
        __init__.py
        base.py
        file_importers.py      # ported from btk
        browser.py

    exporters/
        __init__.py
        formats.py
        arkiv.py
        html_app.py            # ported from btk
        html_app/
            assets/            # app.css, app.js, sql-wasm.js, sql-wasm.wasm

    content/
        __init__.py
        fetcher.py             # ported from btk
        cache.py               # ported from btk
        extractor.py           # ported from btk

    detectors/
        __init__.py            # auto-discovery engine
        youtube.py
        arxiv.py
        github.py

    migrations/
        __init__.py

    web/
        templates/
        static/

tests/
    conftest.py
    test_models.py
    test_db.py
    test_mcp.py
    test_importers.py
    test_exporters.py
    test_detectors.py
    test_serve.py
    test_uri.py
    test_soft_delete.py
    test_content.py
    test_fts.py
    test_arkiv.py
    ...
```

## CLI

Thin admin CLI. Interactive query goes through MCP or web UI.

```
bookmark-memex import <file> [--format html|json|csv|md|text]
bookmark-memex import browser [--browser chrome|firefox] [--profile NAME]
bookmark-memex export <path> [--format json|csv|md|arkiv|html-app|text|m3u] [--single]
bookmark-memex fetch [--all | --stale | ID...]
bookmark-memex detect [--all | ID...]
bookmark-memex check [--all | --stale | ID...]
bookmark-memex db info | schema | vacuum | migrate
bookmark-memex serve [--port 8080]
bookmark-memex mcp [--transport stdio|sse]
bookmark-memex sql "SELECT ..."
```

`--single` on export html-app produces a single HTML file with base64-encoded DB.

Entry point in pyproject.toml:

```toml
[project.scripts]
bookmark-memex = "bookmark_memex.cli:main"
```

## MCP Server

Six tools. Signatures align with the memex archive contract.

### execute_sql(sql, params=None)

Read-only SQL. Connection opened with `?mode=ro`. Only SELECT/WITH/EXPLAIN
allowed. Tool description includes example queries for common operations.

### get_schema()

DDL, row counts, FTS5 docs, example queries. Also exposed as MCP resource
at `bookmark-memex://schema`.

### get_record(kind, id)

Resolve a bookmark-memex URI. Kinds:

- `bookmark`: lookup by unique_id. Returns bookmark with tags, media,
  content cache summary, annotations.
- `annotation`: lookup by uuid. Returns annotation with parent bookmark URI.

Returns `NOT_FOUND` error if the record does not exist. This is the tool
meta-memex calls for cross-archive URI resolution.

### mutate(operations)

Batched write operations in a single transaction. Each operation is a dict
with an `op` field:

- `add`: create bookmark. Required: `url`. Optional: title, description, tags,
  starred, pinned, bookmark_type. Runs detectors on the URL. Generates
  unique_id from normalized URL. Skips duplicates (returns existing ID).
- `update`: update bookmark fields. Identify by `id` or `unique_id`.
- `delete`: soft-delete (sets `archived_at`). Pass `hard: true` for physical removal.
- `tag`: add/remove tags. `{op: "tag", ids: [...], add: [...], remove: [...]}`.
- `annotate`: create, update, or delete annotations.
  `{op: "annotate", bookmark_unique_id: "a1b2c3...", text: "..."}` to create (uses durable ID).
  `{op: "annotate", uuid: "annotation-uuid", text: "..."}` to update (uses annotation's durable UUID).
  `{op: "annotate", uuid: "annotation-uuid", delete: true}` to soft-delete.
- `restore`: undo soft-delete. `{op: "restore", ids: [...]}`.
- `queue`: manage reading queue via `extra_data` JSON fields.
  `{op: "queue", action: "add", ids: [...], priority: "medium"}` to enqueue.
  `{op: "queue", action: "remove", ids: [...]}` to dequeue.
  `{op: "queue", action: "next"}` to mark first item read and return next.
  `{op: "queue", action: "priority", ids: [...], priority: "high"}` to reprioritize.

Individual op failures do not stop the batch. Returns counts and per-op results.

### import_bookmarks(file_path, format=None)

Import from file. Format auto-detected from extension if omitted.

### export_bookmarks(file_path, format="json", bookmark_ids=None)

Export to file. Supports: json, csv, markdown, text, m3u, arkiv, html-app.

## Media Detector Framework

### Contract

A detector is a Python file with a `detect(url, content=None)` function.
Returns a dict of media metadata, or `None` if the URL is not recognized.

```python
def detect(url: str, content: str | None = None) -> dict | None:
    """Return media metadata if recognized, else None."""
```

The returned dict must include `source` (string identifying the platform)
and `type` (media classification). All other fields are detector-specific.

### Discovery

Two directories scanned, user overrides built-in on filename match:

1. `bookmark_memex/detectors/` (built-in)
2. `~/.config/bookmark-memex/detectors/` (user-provided)

Every `.py` file with a `detect` callable is loaded. Discovery runs once at
startup and is cached.

### Integration

- On bookmark add (import, MCP mutate, web UI): `run_detectors(url)` is called.
  Result stored in `bookmarks.media` JSON column.
- CLI `bookmark-memex detect --all` re-runs detectors over existing bookmarks.
- `--fetch` flag enables network-dependent enrichment (e.g., YouTube oEmbed).
- First match wins. Detector order: user directory first, then built-in
  alphabetically.

### Built-in detectors (v1)

- `youtube.py`: YouTube videos, playlists, channels. Extracts video_id,
  playlist_id. Optional oEmbed fetch for title/thumbnail/duration.
- `arxiv.py`: ArXiv papers. Extracts paper ID, constructs PDF/abs URLs.
- `github.py`: GitHub repos, issues, PRs, gists. Extracts owner/repo/type.

## Web UI

Server-rendered HTML via Jinja2. Vanilla JS for interactivity. No build step.

### Routes

```
GET  /                          # dashboard: recent, queue summary, stats
GET  /bookmarks                 # paginated list with search/filter
GET  /bookmarks/<id>            # detail: metadata, content, annotations, media
POST /bookmarks/<id>/open       # increment visit_count, redirect to URL
POST /bookmarks/<id>/star       # toggle
POST /bookmarks/<id>/pin        # toggle
POST /bookmarks/<id>/archive    # soft delete
GET  /tags                      # tag cloud / hierarchy
GET  /tags/<name>               # bookmarks with this tag
GET  /queue                     # reading queue ordered by priority
POST /queue/add/<id>            # add to queue
POST /queue/remove/<id>         # remove from queue
POST /queue/next                # mark current read, advance, redirect
GET  /annotations               # all annotations, searchable
POST /bookmarks/<id>/annotate   # add annotation
GET  /search?q=...              # FTS5 across bookmarks + content + annotations
```

### Visit tracking

Clicking a bookmark title in the UI hits `/bookmarks/<id>/open`. The server
increments `visit_count`, sets `last_visited`, logs an event, and returns a
302 redirect to the bookmark URL. No browser extension needed.

### Queue management

The queue page shows bookmarks where `extra_data->>'queue_position' IS NOT NULL`,
ordered by priority then position. "Next" button marks the current item as
read (removes from queue, increments visit_count) and redirects to the next
item's URL.

### Content viewer

The detail page renders cached `markdown_content` inline. If the original URL
is dead (`reachable = false`), the cached version is the primary view. Annotations
appear alongside the content.

### Media cards

If `media.source` is set, the detail page renders a source-specific card
(YouTube embed, ArXiv abstract, GitHub repo stats). Driven by the `media`
JSON column; templates check `media.source` and render accordingly.

## Arkiv Export

Directory output:

```
<out>/
    records.jsonl
    schema.yaml
    README.md
```

Two record kinds:

```jsonl
{"kind": "bookmark", "uri": "bookmark-memex://bookmark/<uid>", "url": "...", "title": "...", "description": "...", "tags": [...], "media": {...}, "added": "...", "visit_count": 0, "starred": false}
{"kind": "annotation", "uri": "bookmark-memex://annotation/<uuid>", "bookmark_uri": "bookmark-memex://bookmark/<uid>", "text": "...", "created_at": "..."}
```

Only active records emitted (`archived_at IS NULL`). Module-level `SCHEMA`
dict for introspection. Follows book-memex's arkiv exporter pattern.

## HTML-App Export

Self-contained static site with sql.js (WASM) for in-browser queries.

Default: directory with `index.html`, `bookmarks.db`, `assets/`.
`--single` flag: single HTML file with base64-encoded DB.

Read-only. No visit tracking or queue management. This is an artifact for
static hosting (Hugo blog, GitHub Pages).

Ported from btk's existing html-app exporter, which handles sql.js integration,
database subsetting by bookmark IDs, and ID remapping for multi-database merging.

## URI Module

No SQLAlchemy dependency. Usable by external consumers.

```
bookmark-memex://bookmark/<unique_id>
bookmark-memex://annotation/<uuid>
```

Functions: `build_bookmark_uri(unique_id)`, `build_annotation_uri(uuid)`,
`parse_uri(uri) -> ParsedUri`, `InvalidUriError`.

Fragment support for future position addressing:

```
bookmark-memex://bookmark/<uid>#paragraph=12
bookmark-memex://bookmark/<uid>#heading=introduction
```

ORM models expose a `uri` property that delegates to the builders.

## Soft Delete

Port of book-memex's `soft_delete.py` module.

- `filter_active(query, model, include_archived=False)`: default query filter
- `archive(session, instance)`: set `archived_at`, idempotent
- `restore(session, instance)`: clear `archived_at`
- `hard_delete(session, instance)`: physical delete
- `is_archived(instance)`: boolean check

All tables with `archived_at` participate. Default queries exclude archived rows.

## Durable ID Scheme

```python
unique_id = sha256(normalize(url)).hexdigest()[:16]
```

Normalization: lowercase scheme and host, strip trailing slash, sort query
parameters, remove default ports. 16 hex chars = 64 bits of entropy.

Same URL always produces the same ID across re-imports. This is the `<id>`
portion of `bookmark-memex://bookmark/<id>`.

## Configuration

XDG-compliant paths. TOML config.

```
~/.config/bookmark-memex/config.toml       # user config
~/.config/bookmark-memex/detectors/        # user-provided detectors
~/.local/share/bookmark-memex/bookmarks.db # default database
./bookmark-memex.toml                      # local config (overrides user)
```

Config hierarchy (highest wins):
1. CLI arguments
2. `BOOKMARK_MEMEX_*` environment variables
3. Local config (`./bookmark-memex.toml`)
4. User config (`~/.config/bookmark-memex/config.toml`)
5. Defaults

## Dependencies

```toml
[project]
name = "bookmark-memex"
requires-python = ">=3.10"
dependencies = [
    "sqlalchemy>=2.0",
    "beautifulsoup4",
    "requests",
    "rich",
    "pyyaml",
    "jinja2",
]

[project.optional-dependencies]
mcp = ["fastmcp>=2.0", "aiosqlite>=0.20"]
serve = ["flask"]
```

Python 3.10+ (not 3.8 like btk). Enables `match` statements, union types,
and modern SQLAlchemy patterns without compatibility shims.

## What's Not in v1

- Embedding computation (meta-memex's responsibility)
- Cross-archive trails (meta-memex's responsibility)
- NLP auto-tagging (LLM via MCP instead)
- Graph analysis (dropped)
- Views DSL (dropped)
- Generic plugin system (dropped)
- YouTube OAuth import pipeline (detector framework covers metadata; bulk
  playlist import is a future CLI command)
