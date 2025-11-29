# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bookmark Toolkit (btk) is a Python command-line tool for managing and analyzing bookmarks using a SQLite database. It provides:

- Multi-format import/export (HTML, JSON, CSV, Markdown)
- Interactive shell with virtual filesystem navigation
- Hierarchical tag system
- Content caching with full-text search
- Auto-tagging via NLP/TF-IDF
- Plugin system for extensibility

**Current Version:** 0.7.2
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
# Run all tests (597 tests as of v0.7.2)
pytest

# Run with coverage
pytest --cov=btk --cov-report=term-missing

# Test specific modules
pytest tests/test_shell.py -v
pytest tests/test_db.py -v

# Test coverage highlights:
# - graph.py: 97%
# - models.py: 97%
# - tag_utils.py: 96%
# - shell.py: 61%
# - Overall: 63%
```

## Code Architecture

```
btk/
├── __init__.py          # Version: __version__ = "0.7.2"
├── cli.py               # Grouped argparse CLI (btk <group> <command>)
├── shell.py             # Interactive shell with VFS interface
├── db.py                # SQLAlchemy database operations
├── models.py            # ORM models (Bookmark, Tag, ContentCache, etc.)
├── importers.py         # Import from HTML, JSON, CSV, Markdown, text
├── exporters.py         # Export to various formats
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
├── utils.py             # Utility functions
├── constants.py         # Application constants
└── progress.py          # Progress bar utilities
```

### Key Components

- **shell.py**: Virtual filesystem interface with POSIX-like commands (cd, ls, pwd, cat). Supports:
  - Smart collections: `/unread`, `/popular`, `/broken`, `/untagged`, `/pdfs`
  - Time-based navigation: `/recent/{today,week,month,year}/{added,visited,starred}`
  - Tag hierarchy browsing: `/tags/programming/python`

- **db.py**: Database layer using SQLAlchemy ORM with SQLite backend

- **models.py**: Data models including Bookmark, Tag, ContentCache, BookmarkHealth, Collection

- **cli.py**: Grouped command structure: `btk bookmark add`, `btk tag list`, `btk import html`, etc.

## Database Schema (SQLite)

```
bookmarks: id, unique_id, url, title, description, added, stars, visit_count, last_visited, reachable
tags: id, name, description, color
bookmark_tags: bookmark_id, tag_id (many-to-many)
content_cache: id, bookmark_id, html_content, markdown_content, content_hash, fetched_at, status_code
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
btk tag add python 42 43

# Import/Export
btk import html bookmarks.html
btk export output.html html --hierarchical

# Database operations
btk db info
btk db vacuum
btk db dedupe --strategy merge --preview
```

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

## Important Notes

- **Database-first**: Uses SQLite via SQLAlchemy, not JSON files
- **Virtual environment**: Makefile auto-manages `.venv/` directory
- **JMESPath**: Numbers must be backtick-wrapped: `[?visit_count > \`5\`]`
- **Hierarchical tags**: Use `/` separator (e.g., `programming/python/web`)
- **Testing**: Always run `make test` after changes; aim for high coverage

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
tests/                  # Test suite (20 test files, 597 tests)
integrations/
└── mcp-btk/            # Model Context Protocol server (Node.js)
docs/                   # MkDocs documentation
```
