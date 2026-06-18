# bookmark-memex

A personal bookmark archive: a database-first bookmark manager with full-text
search, content caching, and an MCP server for LLM agents. Part of the
`*-memex` personal-data ecosystem (see `../CLAUDE.md`).

This is a clean break from the older `btk` / `bookmark-tk` project; the package,
CLI, and repo are all named `bookmark-memex`.

## Features

- SQLite + FTS5 backend with soft delete (`archived_at`)
- Durable content-derived IDs: `unique_id = sha256(normalize(url))[:16]`,
  stable across re-imports
- Cross-archive URIs: `bookmark-memex://bookmark/<unique_id>`,
  `bookmark-memex://marginalia/<uuid>`
- Import from HTML (Netscape), JSON, CSV, Markdown, and plain text
- Export to JSON, CSV, Markdown, text, m3u, and arkiv JSONL
- Content caching (zlib-compressed HTML/markdown) with FTS5 search
- Media auto-detection (YouTube, ArXiv, GitHub built-in; user detectors
  override)
- Marginalia (free-form notes) with orphan survival via `ON DELETE SET NULL`
- MCP server exposing `execute_sql`, `get_schema`, `get_record`, `mutate`,
  `import_bookmarks`, and `export_bookmarks`

## Installation

```sh
pip install bookmark-memex
# development
make install-dev   # creates .venv/ with dev deps
```

Python >= 3.10.

## CLI

```sh
bookmark-memex import <file> [--format html|json|csv|markdown|text]
bookmark-memex export <path> [--format json|csv|markdown|text|m3u|arkiv] [--single]
bookmark-memex db info | schema | vacuum
bookmark-memex sql "SELECT title, url FROM bookmarks LIMIT 10" [-o table|json|csv]
bookmark-memex mcp [--transport stdio|sse]
```

Configuration is resolved (highest wins): CLI `--db` flag, `BOOKMARK_MEMEX_*`
env vars, local `./bookmark-memex.toml`, user
`~/.config/bookmark-memex/config.toml`, XDG defaults
(`~/.local/share/bookmark-memex/bookmarks.db`).

## MCP server

`bookmark-memex mcp` starts a stdio MCP server. Query happens through MCP, not
the CLI: `execute_sql` (read-only: SELECT/WITH/EXPLAIN), `get_schema`, and
`get_record(kind, id)` for URI resolution; `mutate` runs a batch of write ops
(`add`, `update`, `delete`, `tag`, `restore`, plus the marginalia ops). Bookmark
ops accept the durable `unique_id` (preferred) or the integer `id`.

```json
{"mcpServers": {"bookmark-memex": {"command": "bookmark-memex", "args": ["mcp"]}}}
```

## Schema

Core tables: `bookmarks` (durable `unique_id`, `url`, title, type, `added`,
`visit_count`, `starred`, `pinned`, reachability, `media`/`extra_data` JSON,
`archived_at`), `bookmark_sources` (import provenance), `tags` (hierarchical)
plus `bookmark_tags`, `content_cache`, `marginalia`, `history_urls` plus
`history_visits`, `events`, `schema_version`. Plus FTS5 virtual tables
`bookmarks_fts`, `content_fts`, `marginalia_fts`.

## Testing

```sh
pytest -k "test_bm_" -v        # all bookmark-memex tests
make check                     # lint + typecheck
```

See `CLAUDE.md` for architecture, design patterns, and the full ecosystem
contract.
