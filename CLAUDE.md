# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

bookmark-memex is a personal bookmark archive satisfying the memex ecosystem contract. It provides:

- SQLite + FTS5 backend with soft delete (`archived_at` timestamps)
- MCP server with 6 tools (`execute_sql`, `get_schema`, `get_record`, `mutate`, `import_bookmarks`, `export_bookmarks`)
- Thin admin CLI for import, export, and housekeeping (interactive query goes through MCP)
- Import from HTML (Netscape), JSON, CSV, Markdown, text files
- Export to JSON, CSV, Markdown, text, m3u, arkiv JSONL, html-app
- Content caching with zlib compression and FTS5 full-text search
- Media detector auto-discovery framework (YouTube, ArXiv, GitHub built-in)
- Durable IDs: `sha256(normalize(url))[:16]`, stable across re-imports
- URI scheme: `bookmark-memex://bookmark/<unique_id>`, `bookmark-memex://annotation/<uuid>`
- Marginalia (annotations with orphan survival via `ON DELETE SET NULL`)

**Current Version:** 0.1.0
**Package Name:** bookmark-memex (PyPI)
**Python:** >=3.10

This is a clean break from btk/bookmark-tk. The old `btk/` directory in this repo is frozen reference code.

## Build and Development Commands

```bash
make help           # Show all commands
make install-dev    # Install with dev deps (creates .venv/)
make test           # Run all tests
make test-coverage  # Tests with coverage report
make lint           # flake8
make format         # black (line-length 120)
make typecheck      # mypy
make check          # lint + typecheck
make clean          # remove build artifacts

# Run specific bookmark-memex tests (prefix: test_bm_*)
pytest tests/test_bm_db.py -v
pytest tests/test_bm_mcp.py -v
pytest -k "test_bm_" -v          # all bookmark-memex tests
```

## Architecture

### Package layout

```
bookmark_memex/
    __init__.py          # version
    models.py            # SQLAlchemy ORM (7 tables)
    db.py                # Database class: CRUD, tags, annotations, soft delete
    config.py            # TOML config, XDG paths, BOOKMARK_MEMEX_* env vars
    uri.py               # bookmark-memex:// URI builder/parser (no SQLAlchemy dep)
    soft_delete.py       # filter_active, archive, restore, hard_delete helpers
    fts.py               # FTS5 index: bookmarks_fts, content_fts, annotations_fts
    mcp.py               # MCP server (fastmcp + aiosqlite), 6 tools
    cli.py               # argparse CLI: import, export, db, sql, mcp, serve
    content/
        fetcher.py       # HTTP fetch with requests.Session
        extractor.py     # HTML->markdown->text, zlib compression, PDF extraction
    importers/
        file_importers.py  # HTML, JSON, CSV, Markdown, text
    exporters/
        formats.py       # JSON, CSV, text, markdown, m3u
        arkiv.py         # arkiv JSONL + schema.yaml for memex ecosystem
    detectors/
        __init__.py      # auto-discovery engine
        youtube.py       # YouTube videos, playlists, channels
        arxiv.py         # ArXiv papers
        github.py        # repos, issues, PRs, gists
```

### Key design patterns

- **Satellite table for provenance only**: `bookmark_sources` tracks where each bookmark was imported from (Chrome, Firefox, file, MCP). Multiple sources per bookmark.
- **Flat media metadata**: the `media` JSON column on bookmarks (not a separate table) is populated by auto-discovered detectors.
- **Soft delete everywhere**: `archived_at TIMESTAMP NULL` on bookmarks, content_cache, annotations. `filter_active()` helper. Default queries exclude archived rows.
- **Orphan-surviving annotations**: `ON DELETE SET NULL` on `annotations.bookmark_id`. Deleting a bookmark preserves its notes.
- **Durable IDs from URL**: `unique_id = sha256(normalize(url))[:16]`. Same URL always produces the same ID across re-imports.
- **Reading queue via extra_data JSON**: not a separate table. `extra_data->>'queue_position' IS NOT NULL` identifies queued bookmarks.

### MCP server tools

| Tool | Access | Purpose |
|------|--------|---------|
| `execute_sql` | read-only | SQL queries (SELECT/WITH/EXPLAIN only) |
| `get_schema` | read-only | DDL + row counts |
| `get_record` | read-only | Resolve `bookmark-memex://` URI by kind + id |
| `mutate` | write | Batched ops: add, update, delete, tag, annotate, restore |
| `import_bookmarks` | write | Import from file |
| `export_bookmarks` | write | Export to file |

`_create_tools(db_path)` returns sync functions for testing without MCP. `create_server()` wraps them as async MCP tools.

### CLI commands

```
bookmark-memex import <file> [--format ...]
bookmark-memex export <path> [--format ...] [--single]
bookmark-memex db info|schema|vacuum
bookmark-memex sql "SELECT ..."  [-o table|json|csv]
bookmark-memex mcp [--transport stdio|sse]
bookmark-memex serve [--port 8080]      # not yet implemented
bookmark-memex fetch/detect/check       # not yet implemented
```

## Database Schema

7 tables + 3 FTS5 virtual tables:

```
bookmarks          Core record. unique_id (16-char hex), url (unique), title,
                   bookmark_type, added, last_visited, visit_count, starred,
                   pinned, reachable, last_checked, status_code, media (JSON),
                   extra_data (JSON), archived_at

bookmark_sources   Import provenance (1:N). source_type, source_name,
                   folder_path, imported_at, raw_data (JSON)

tags               Hierarchical via / separator. name (unique), color
bookmark_tags      M2M junction

content_cache      1:1 with bookmark. html_content (zlib blob),
                   markdown_content, extracted_text, content_hash,
                   fetched_at, archived_at

annotations        Marginalia. Text PK (uuid hex), bookmark_id (SET NULL),
                   text, created_at, updated_at, archived_at

events             Audit log. event_type, entity_type, entity_id, event_data
schema_version     Migration tracking (no Alembic)

bookmarks_fts      FTS5 on url, title, description, tags
content_fts        FTS5 on extracted_text
annotations_fts    FTS5 on text
```

## Configuration

```
~/.config/bookmark-memex/config.toml       # user config
~/.config/bookmark-memex/detectors/        # user media detectors
~/.local/share/bookmark-memex/bookmarks.db # default database
./bookmark-memex.toml                      # local override
```

Hierarchy (highest wins): CLI `--db` flag, `BOOKMARK_MEMEX_*` env vars, local TOML, user TOML, XDG defaults.

## Media Detectors

Auto-discovered `.py` files with a `detect(url, content=None)` function returning `dict | None`. Built-in: `youtube.py`, `arxiv.py`, `github.py`. User detectors in `~/.config/bookmark-memex/detectors/` override built-in on filename match.

## Memex Ecosystem

This archive is part of the `*-memex` ecosystem. See `../CLAUDE.md` for the workspace contract:
- URI scheme: `bookmark-memex://bookmark/<id>`, `bookmark-memex://annotation/<uuid>`
- Arkiv export: `records.jsonl` + `schema.yaml` with bookmark and annotation kinds
- Cross-archive resolution via `get_record(kind, id)` MCP tool

## Testing

```bash
pytest tests/test_bm_*.py -v              # all bookmark-memex tests (~350)
pytest tests/test_bm_db.py -v             # database layer
pytest tests/test_bm_mcp.py -v            # MCP server tools
pytest tests/test_bm_exporters.py -v      # exporters including arkiv
```

Test fixtures in `tests/conftest.py`: `tmp_db_path` (temp database with cleanup).

## Follow-up Work (Not Yet Implemented)

- Web UI: Flask server with Jinja2 templates, visit tracking, queue management
- HTML-app export: sql.js WASM single-file and directory modes
- Browser import: Chrome/Firefox direct DB import
- Content fetch/detect/check CLI commands
