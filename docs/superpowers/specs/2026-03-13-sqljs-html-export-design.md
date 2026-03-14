# sql.js-Powered HTML-App Export

**Date:** 2026-03-13
**Status:** Proposed

## Problem

The HTML-app export embeds bookmarks as a JSON blob and uses JavaScript array operations (`filter()`, `sort()`) for all filtering, search, and statistics. This limits what users can do — no ad-hoc queries, no cross-database analysis, no SQL-powered aggregations. The ~1,100-line JS engine reimplements query logic that SQLite already handles.

## Decision

Replace the JSON data engine with sql.js (SQLite compiled to WebAssembly). Embed the actual btk SQLite database schema in the export so SQL queries transfer directly between `btk sql` and the HTML viewer. Add a user-facing SQL query box. Support multi-database exports by merging all databases into a single export DB with a `source_db` discriminator column.

## Data Pipeline

1. `export_html_app` receives `Bookmark` ORM objects (unchanged API).
2. Python creates a **temporary in-memory SQLite database** using `sqlite3`, with the btk schema (bookmarks, tags, bookmark_tags).
3. Inserts only the exported bookmarks — no content_cache, bookmark_health, or other heavy tables.
4. Serializes the `.db` bytes.
5. For multi-db: each `--include-db` database's bookmarks are inserted into the same export DB with `source_db` set to the database name.
6. Packaging depends on `--no-embed` flag (see below).

**Why a fresh export DB, not a copy of the user's file:**
- The user's DB has tables irrelevant to the viewer (content_cache can be 790MB).
- We export only the bookmarks that matched the query/view.
- The export DB uses a **compatible subset** of the real schema so SQL queries transfer.

## Export Database Schema

Compatible subset of the real btk schema. Column types and sizes match the ORM models so SQL queries transfer directly between `btk sql` and the HTML viewer.

```sql
CREATE TABLE bookmarks (
    id INTEGER PRIMARY KEY,
    unique_id VARCHAR(8),
    url VARCHAR(2048),
    title VARCHAR(512),
    description TEXT,
    bookmark_type VARCHAR(16) NOT NULL DEFAULT 'bookmark',
    added DATETIME,
    stars INTEGER DEFAULT 0,
    pinned INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0,
    reachable INTEGER,
    visit_count INTEGER DEFAULT 0,
    last_visited DATETIME,
    favicon_data BLOB,
    favicon_mime_type VARCHAR(64),
    extra_data JSON,
    source_db VARCHAR(64) NOT NULL DEFAULT 'default'
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name VARCHAR(256),
    description TEXT,
    color VARCHAR(7)
);

CREATE TABLE bookmark_tags (
    bookmark_id INTEGER REFERENCES bookmarks(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (bookmark_id, tag_id)
);

CREATE TABLE bookmark_media (
    id INTEGER PRIMARY KEY,
    bookmark_id INTEGER REFERENCES bookmarks(id) UNIQUE,
    media_type VARCHAR(32),
    media_source VARCHAR(64),
    media_id VARCHAR(128),
    author_name VARCHAR(256),
    author_url VARCHAR(2048),
    thumbnail_url VARCHAR(2048),
    published_at DATETIME
);
```

**`source_db` column:** Added to `bookmarks` to support multi-database exports. Set to `'default'` for the main database, or the named database key (e.g., `'history'`) for included databases. This replaces the `ATTACH DATABASE` approach which sql.js does not support.

Tables **not** exported: `content_cache`, `bookmark_health`, `bookmark_sources`, `bookmark_visits`, `collections`, `bookmark_collections`, `schema_version`.

## sql.js Bundling

btk vendors sql.js distribution files (`sql-wasm.js` + `sql-wasm.wasm`) as Python package data. No runtime download, no CDN dependency.

**Version pinning:** A specific sql.js release (e.g., 1.10.3) is vendored. Updates are explicit, tracked in `pyproject.toml` package data.

**Sizes:**
- `sql-wasm.wasm`: ~640KB raw, ~853KB base64-encoded
- `sql-wasm.js`: ~90KB

## Packaging Modes

Controlled by `--no-embed` CLI flag on `btk export`. Default is embedded (single file).

### Embedded Mode (default)

Single self-contained HTML file:
- `sql-wasm.js` inlined as a `<script>` block
- `sql-wasm.wasm` base64-encoded as a data URI: `data:application/wasm;base64,...`
- The single `.db` file (containing all databases merged) base64-encoded in a `<script type="application/octet-stream" id="btk-db">` tag
- Works offline, can be emailed, no external dependencies

**Size expectations:** For a ~6,770-bookmark export, the database is roughly 2-5MB raw, becoming 2.7-6.7MB base64. Plus ~853KB for the WASM and ~90KB for the JS loader. Total: 3.5-7.5MB for a large collection.

### Directory Mode (`--no-embed`)

Multi-file output. The `--no-embed` flag triggers directory mode. If the output path ends with `.html`, it is treated as an error (suggest removing the extension). The output directory is created if it does not exist.

```
output/
  index.html
  sql-wasm.js
  sql-wasm.wasm
  export.db
```
- JS loads WASM and database via `fetch()`
- Same code paths, different loaders
- Smaller total size (no base64 overhead)

### Loading Sequence (browser)

1. sql.js initializes, loads WASM (from data URI or fetch)
2. Export database loaded into sql.js (from decoded base64 or fetched file)
3. UI renders from SQL queries

## Multi-Database Support

New CLI flag: `--include-db <name>` (repeatable).

```bash
btk export output.html html-app --include-db history
btk export output.html html-app --include-db history --include-db tabs
```

- Each named database resolved via `config.resolve_database()`
- All databases merged into a **single export DB** with `source_db` column as discriminator
- Main database bookmarks get `source_db = 'default'`
- Included databases get `source_db = '<name>'` (e.g., `'history'`)
- Tags are merged: same tag name across databases maps to one tag row
- Bookmark IDs are remapped during export to avoid collisions across databases

**ID remapping algorithm:** The export DB uses autoincrement IDs. Main database bookmarks are inserted first. For each included database, bookmarks are inserted with new IDs (autoincrement continues from the last main ID). A temporary `old_id -> new_id` mapping is maintained per database to correctly remap `bookmark_tags.bookmark_id` and `bookmark_media.bookmark_id` foreign keys before inserting those rows.

**`extra_data` serialization:** When inserting into the raw `sqlite3` export database, `extra_data` dicts must be explicitly serialized via `json.dumps()` (SQLAlchemy handles this transparently, but raw `sqlite3` does not).

**Why merge instead of ATTACH:** sql.js (WebAssembly SQLite) does not support `ATTACH DATABASE` — there is no filesystem to reference. Merging at export time gives the same query power with a simpler runtime:

```sql
-- Cross-database query: find URLs in bookmarks but not in history
SELECT url FROM bookmarks WHERE source_db = 'default'
  AND url NOT IN (SELECT url FROM bookmarks WHERE source_db = 'history')

-- Filter by source
SELECT * FROM bookmarks WHERE source_db = 'history'
```

The sidebar shows a database filter dropdown when multiple source databases are present.

## JavaScript Architecture

### State Management

`AppState` holds **UI state only** — no bookmark data:
```javascript
const AppState = {
    db: null,                // sql.js database instance
    sourceDbs: [],           // available source_db values
    activeSourceDb: null,    // null = all, or specific source_db name
    searchQuery: '',
    selectedTags: new Set(),
    sortBy: 'added',
    sortDir: 'desc',
    activeCollection: 'all',
    viewMode: 'grid',
    theme: 'light',
    // ... other UI state
};
```

### Query-Driven Rendering

Every render builds a SQL query from UI state and executes it:

- **Smart collections** become SQL:
  ```
  all:      SELECT * FROM bookmarks
  unread:   SELECT * FROM bookmarks WHERE visit_count = 0
  starred:  SELECT * FROM bookmarks WHERE stars = 1
  queue:    SELECT * FROM bookmarks WHERE json_extract(extra_data, '$.reading_queue') = 1
  popular:  SELECT * FROM bookmarks WHERE visit_count > 5 ORDER BY visit_count DESC LIMIT 100
  media:    SELECT b.* FROM bookmarks b JOIN bookmark_media bm ON b.id = bm.bookmark_id
  broken:   SELECT * FROM bookmarks WHERE reachable = 0
  untagged: SELECT * FROM bookmarks WHERE id NOT IN (SELECT bookmark_id FROM bookmark_tags)
  pdfs:     SELECT * FROM bookmarks WHERE url LIKE '%.pdf'
  ```
- **Tag filtering:** `JOIN bookmark_tags bt ON b.id = bt.bookmark_id JOIN tags t ON bt.tag_id = t.id WHERE t.name IN (...)`
- **Sorting:** `ORDER BY <column> <direction>`
- **Search:** `WHERE title LIKE '%query%' OR url LIKE '%query%' OR description LIKE '%query%'` (LIKE for v1; FTS possible later)
- **Pagination:** `LIMIT <page_size> OFFSET <page * page_size>`
- **Tag cloud:** `SELECT t.name, COUNT(*) c FROM tags t JOIN bookmark_tags bt ON t.id = bt.tag_id GROUP BY t.name ORDER BY c DESC`
- **Statistics:** Real SQL aggregations (`COUNT`, `AVG`, `GROUP BY domain`, etc.)

### Query Box

- Text input + Run button, toggleable panel (bottom of sidebar or dedicated tab)
- Executes arbitrary SQL against the database
- Results rendered as an HTML table
- Errors displayed inline
- **Read-only enforcement:** Before executing, validate that the first keyword is in `{SELECT, WITH, EXPLAIN}` (same whitelist as the MCP server's `query` tool). This prevents mutations on the in-memory database. sql.js would happily execute `DELETE FROM bookmarks` in-memory — the keyword check prevents this.

### Favicon Rendering

`favicon_data` is stored as a BLOB in the export database. sql.js returns BLOBs as `Uint8Array`. The JS rendering code converts to a data URI for display:

```javascript
function faviconDataUri(row) {
    if (!row.favicon_data) return null;
    const bytes = row.favicon_data;  // Uint8Array from sql.js
    const mime = row.favicon_mime_type || 'image/png';
    // Chunk-based conversion — spread operator would blow the stack on large favicons
    const binary = Array.from(bytes, b => String.fromCharCode(b)).join('');
    return `data:${mime};base64,${btoa(binary)}`;
}
```

### What Stays the Same

- All HTML/CSS (grid, list, table, gallery layouts)
- Keyboard shortcuts (j/k navigation, /, g/l/t/m view switching, d dark mode)
- Dark mode toggle
- Favicon rendering
- View mode switching

### What Changes

- `_HTML_APP_JS` (~1,118 lines) substantially rewritten
- `SearchIndex` class removed (SQL replaces it)
- `SMART_COLLECTIONS` filter functions become SQL strings
- All `AppState.bookmarks.filter(...).sort(...)` chains become `db.exec(sql)`
- `_serialize_bookmark_for_app()` removed (data goes through SQLite, not JSON)
- `_get_tag_stats()` and `_get_export_stats()` removed (SQL aggregations replace them)

## Views

Existing btk views (from `views.yaml`) are exported as a JSON metadata blob in the HTML, defining smart collections in the sidebar. View **execution** is SQL-based — the view definitions map to WHERE/ORDER/LIMIT clauses.

## File Organization

Extract the HTML-app export from `exporters.py` (currently ~3,000 lines) into its own module:

```
btk/
  exporters.py              # All other formats, thin dispatch to html_app
  html_app/
    __init__.py           # export_html_app() entry point
    builder.py            # Export DB creation, serialization, base64 encoding
    assets/
      app.css           # Extracted from _HTML_APP_CSS
      app.js            # Rewritten JS with SQL engine
      sql-wasm.js       # Vendored sql.js loader
      sql-wasm.wasm     # Vendored sql.js WASM binary
    template.py           # HTML template assembly (embed vs directory)
```

Benefits:
- CSS and JS are real files with syntax highlighting and editor support
- sql.js assets vendored alongside the code that uses them
- `builder.py` handles export DB creation and encoding
- `template.py` handles the two packaging modes
- `exporters.py` drops ~3,000 lines, keeps a thin `"html-app": html_app.export_html_app` entry

### `pyproject.toml` Package Data

The `assets/` directory contains non-Python files (`.css`, `.js`, `.wasm`) that must be included in the distribution:

```toml
[tool.setuptools.package-data]
"btk.html_app.assets" = ["*.css", "*.js", "*.wasm"]
```

## CLI Changes

```bash
# Basic export (embedded mode, single file)
btk export output.html html-app

# Directory mode
btk export output/ html-app --no-embed

# Multi-database
btk export output.html html-app --include-db history

# Combined
btk export output/ html-app --no-embed --include-db history --include-db tabs
```

New flags on the `export` command:
- `--no-embed`: Directory mode instead of single-file (default is embedded)
- `--include-db <name>`: Include a named database (repeatable)

### `export_file()` Plumbing

`export_file()` gains optional kwargs for the new flags:

```python
def export_file(bookmarks, path, format, views=None, db=None,
                embed=True, include_dbs=None):
```

- `include_dbs`: `Optional[Dict[str, List[Bookmark]]]` — maps database names to their bookmark lists. Example: `{"history": [<Bookmark>, ...]}`. `None` means no additional databases.
- `embed`: `bool` — `True` for single-file, `False` for directory mode.

For `html-app`, `export_file()` passes `embed` and `include_dbs` to `html_app.export_html_app()`. The CLI resolves `--include-db` names to database paths via `config.resolve_database()`, opens each database, loads bookmarks, and builds the `include_dbs` dict before calling `export_file()`. Other export formats ignore these kwargs.

## What We're NOT Doing

- No FTS5 in v1 — `LIKE` search is sufficient, FTS can be added later
- No CodeMirror/Monaco editor for the query box — plain text input
- No query history or saved queries in v1
- No CDN loading of sql.js — always vendored
- No write operations in the browser — read-only SQL only
- No export of content_cache or other heavy tables
- No changes to other export formats (json, csv, html, markdown, etc.)
- No backward compatibility with old JSON-based HTML-app exports — `html-app` format produces the new sql.js version only
- No `ATTACH DATABASE` in sql.js — multi-db handled by merging into a single export DB with `source_db` discriminator
- No view DSL compilation to SQL — views are exported as pre-evaluated bookmark ID lists (same as today), displayed as sidebar collections
