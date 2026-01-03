# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bookmark Toolkit (btk) is a Python command-line tool for managing and analyzing bookmarks using a SQLite database. It provides:

- Multi-format import/export (HTML, JSON, CSV, Markdown, HTML-app)
- Interactive shell with virtual filesystem navigation
- Hierarchical tag system
- Content caching with full-text search
- Auto-tagging via NLP/TF-IDF
- Plugin system for extensibility
- View DSL for composable bookmark queries
- REST API server with web UI

**Current Version:** 0.8.0
**Package Name:** bookmark-tk (PyPI)
**Python:** >=3.8

## Build and Development Commands

```bash
# Use the Makefile for all development tasks
make help           # Show all available commands
make venv           # Create virtual environment at .venv/
make install-dev    # Install with dev dependencies (auto-creates venv)
make test           # Run all tests
make test-coverage  # Run tests with coverage report
make lint           # Run flake8 linting
make format         # Format code with black
make typecheck      # Run mypy type checking
make check          # Run all quality checks (lint + format-check + typecheck)
make build          # Build distribution packages
make clean          # Clean build artifacts

# Useful shortcuts
make quick-test     # Fast test run (-x --tb=short)
make ci             # Full CI pipeline (install-dev, check, test-coverage)
make test-file FILE=tests/test_shell.py    # Run specific test file
make test-match MATCH=test_import          # Run tests matching pattern
```

## Testing

```bash
# Run all tests (~1000+ tests)
pytest

# Run with coverage
pytest --cov=btk --cov-report=term-missing

# Test specific modules
pytest tests/test_shell.py -v
pytest tests/test_views.py -v
pytest tests/test_exporters.py -v
```

## Code Architecture

```
btk/
├── __init__.py          # Version: __version__ = "0.7.5"
├── cli.py               # Grouped argparse CLI (btk <group> <command>)
├── shell.py             # Interactive shell with VFS interface
├── db.py                # SQLAlchemy database operations
├── models.py            # ORM models (Bookmark, Tag, ContentCache, etc.)
├── importers.py         # Import from HTML, JSON, CSV, Markdown, text
├── exporters.py         # Export to various formats (incl. html-app)
├── graph.py             # Bookmark relationship graphs
├── tag_utils.py         # Hierarchical tag operations
├── content_fetcher.py   # Web content fetching
├── content_cache.py     # Content cache management (zlib compression)
├── content_extractor.py # HTML/Markdown/PDF extraction
├── auto_tag.py          # NLP-based auto-tagging
├── dedup.py             # Deduplication strategies
├── plugins.py           # Plugin system architecture
├── archiver.py          # Web archive integration
├── browser_import.py    # Chrome/Firefox bookmark import
├── config.py            # Configuration management
├── serve.py             # REST API server with web UI
├── fts.py               # Full-text search index
├── views/               # View DSL module
│   ├── core.py          # View base class, ViewResult, ViewContext
│   ├── predicates.py    # Predicate classes (Tags, Field, Domain, etc.)
│   ├── primitives.py    # Primitive views (Select, Order, Limit, etc.)
│   ├── composites.py    # Composite views (Union, Intersect, Pipeline)
│   ├── parser.py        # YAML parser for view definitions
│   └── registry.py      # ViewRegistry with built-in views
└── utils.py             # Utility functions
```

### Key Components

- **shell.py**: Virtual filesystem interface with POSIX-like commands (cd, ls, pwd, cat)
  - Smart collections: `/unread`, `/popular`, `/broken`, `/untagged`, `/pdfs`
  - Time-based navigation: `/recent/{today,week,month,year}/{added,visited,starred}`
  - Tag hierarchy browsing: `/tags/programming/python`

- **views/**: Composable View DSL following SICP principles
  - Views as functions: Database → ViewResult
  - Algebraic operators: union (|), intersect (&), difference (-), pipeline (>>)
  - YAML-based view definitions in `btk-views.yaml`

- **exporters.py**: Export formats including interactive HTML-app with embedded views

- **serve.py**: REST API server at `btk serve` with web UI for browsing bookmarks

## Database Schema (SQLite)

```
bookmarks: id, unique_id, url, title, description, added, stars, visit_count,
           last_visited, reachable, media_type, author_name, thumbnail_url
tags: id, name, description, color
bookmark_tags: bookmark_id, tag_id (many-to-many)
content_cache: id, bookmark_id, html_content, markdown_content, content_hash, fetched_at
bookmark_health: id, bookmark_id, status_code, checked_at, response_time
collections: id, name, query, description
```

## Common CLI Commands

```bash
# Start interactive shell (recommended)
btk shell

# Bookmark operations
btk bookmark add https://example.com --title "Example" --tags web,tutorial
btk bookmark list
btk bookmark search "python"
btk bookmark get 42 --details

# Tag management
btk tag list
btk tag tree                    # Hierarchical view

# Import/Export
btk import html bookmarks.html
btk export output.html html-app  # Interactive HTML app with views

# Raw SQL queries
btk sql -e "SELECT COUNT(*) FROM bookmarks"
btk sql -e "SELECT t.name, COUNT(*) FROM tags t JOIN bookmark_tags bt ON t.id = bt.tag_id GROUP BY t.name ORDER BY 2 DESC LIMIT 10"
btk sql -e "SELECT * FROM bookmarks WHERE url LIKE '%github.com%'" -o json

# View management
btk view list                   # List all views (built-in + custom)
btk view eval arxiv --limit 10  # Evaluate a view
btk view export starred output.html --format html-app

# Database operations
btk db info
btk db vacuum
btk serve                       # Start REST API + web UI
```

## View DSL

Views are composable bookmark queries defined in YAML. Place in `btk-views.yaml`:

```yaml
# Simple view
arxiv:
  description: "ArXiv papers"
  select:
    domain: arxiv.org
  order: added desc

# Composite view with multiple conditions
ai_python:
  description: "AI resources in Python"
  select:
    all:
      - tags:
          any: [ai, ai/machine-learning]
      - tags:
          any: [python, programming/python]
  order: stars desc, added desc

# View composition
recent_ai:
  extends: ai_python
  select:
    added:
      within: "30 days"
  limit: 50
```

Built-in views: `all`, `recent`, `starred`, `pinned`, `archived`, `unread`, `popular`, `broken`, `untagged`

## Shell Virtual Filesystem

```
/                      # Root - shows top-level directories
├── bookmarks/         # All bookmarks by ID
│   └── <id>/          # Individual bookmark (cat for details)
├── tags/              # Hierarchical tag navigation
│   └── programming/
│       └── python/    # Bookmarks with this tag
├── starred/           # Starred bookmarks
├── archived/          # Archived bookmarks
├── domains/           # Bookmarks by domain
├── recent/            # Time-based navigation
│   ├── today/         # added/, visited/, starred/
│   ├── week/
│   ├── month/
│   └── year/
├── unread/            # Smart: never visited
├── popular/           # Smart: visit_count > 5
├── broken/            # Smart: unreachable URLs
├── untagged/          # Smart: no tags
└── pdfs/              # Smart: PDF URLs
```

## Dev Database Insights

The dev database (`dev/btk.db`, ~790 MB) contains ~6,770 bookmarks with:

**Top Tags:**
- `imported/chrome` (2,574) - Chrome imports
- `programming` (2,175) - General programming
- `programming/php` (1,636), `programming/python` (405), `programming/cpp` (314)
- `reference/wikipedia` (1,521) - Wikipedia articles
- `ai` (448), `ai/machine-learning` (328), `ai/neural-networks` (156)
- `framework/nextjs` (901), `framework/express` (275)
- `content/video` (751), `video/youtube` (739)

**Top Domains:**
- wikipedia.org (1,856), youtube.com (918), arxiv.org (330), github.com (278)
- huggingface.co (79), openai.com (60), boost.org (85)

**Content Types:**
- Videos: 776 (media_type=video)
- PDFs: 502 (.pdf URLs)
- Academic: 651 (.edu, arxiv, research sites)
- With cached content: 3,917

## Important Notes

- **Database-first**: Uses SQLite via SQLAlchemy, not JSON files
- **Virtual environment**: Makefile auto-manages `.venv/` directory
- **Hierarchical tags**: Use `/` separator (e.g., `programming/python/web`)
- **Views file**: Place `btk-views.yaml` in working dir or `~/.config/btk/views.yaml`
- **Testing**: Always run `make test` after changes

## Release Process

```bash
# 1. Bump version in: pyproject.toml, btk/__init__.py, btk/shell.py
# 2. Update docs/development/changelog.md
# 3. Run tests
make test-coverage

# 4. Git commit and tag
git add -A && git commit -m "Release vX.Y.Z: ..."
git tag vX.Y.Z
git push origin master --tags

# 5. Build and publish to PyPI
make build
twine upload dist/*

# 6. Deploy docs (if using mkdocs)
mkdocs gh-deploy
```

## Project Structure

```
btk/                    # Main package
tests/                  # Test suite (~1000+ tests)
dev/                    # Development database and views
integrations/
└── mcp-btk/            # Model Context Protocol server (Node.js)
docs/                   # MkDocs documentation
```
