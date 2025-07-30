# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bookmark Toolkit (btk) is a Python command-line tool for managing and analyzing bookmarks. It provides features for importing, searching, editing, and exporting bookmarks, as well as querying them using JMESPath and LLM integration.

## Key Commands

### Build and Development

```bash
# Use the Makefile for common tasks
make help           # Show all available commands
make venv          # Create virtual environment
make install-dev    # Install with development dependencies (creates venv automatically)
make test          # Run tests
make test-coverage # Run tests with coverage report
make lint          # Run linting
make format        # Format code with black
make check         # Run all quality checks

# Note: The Makefile automatically manages a virtual environment at .venv/
# All commands will create and use the virtual environment as needed
```

### Testing and Linting

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=btk --cov-report=term-missing

# Run linting
flake8 btk tests

# Format code
black btk tests

# Type checking
mypy btk

# Install pre-commit hooks
pre-commit install

# Run all pre-commit hooks on all files
pre-commit run --all-files
```

## Common BTK Commands

### Import Commands

- `btk import nbf <file>` - Import from Netscape Bookmark Format (HTML)
- `btk import html <file>` - Import from generic HTML (extracts all links)
- `btk import json <file>` - Import from JSON file
- `btk import csv <file>` - Import from CSV file  
- `btk import markdown <file>` - Extract and import links from Markdown files
- `btk import dir <directory>` - Recursively scan and import all supported files from a directory

### Export Commands

- `btk export <lib_dir> html` - Export to Netscape HTML format (browser-compatible)
- `btk export <lib_dir> json` - Export to JSON format
- `btk export <lib_dir> csv` - Export to CSV format
- `btk export <lib_dir> markdown` - Export to Markdown format (organized by tags)
- `btk export <lib_dir> zip` - Export as ZIP archive
- `btk export <lib_dir> hierarchical` - Export bookmarks organized by tag hierarchy
  - `--hierarchical-format` - Output format: markdown, json, or html (default: markdown)
  - `--tag-separator` - Tag separator character (default: /)

### Bookmark Management

- `btk add <lib_dir> <url>` - Add a new bookmark
- `btk remove <lib_dir> <id>` - Remove bookmark by ID
- `btk edit <lib_dir> <id>` - Edit bookmark details
- `btk list <lib_dir>` - List all bookmarks
- `btk search <lib_dir> <query>` - Search bookmarks
- `btk jmespath <lib_dir> <query>` - Query using JMESPath
- `btk dedupe <lib_dir>` - Find and remove duplicate bookmarks
  - `--strategy` - Deduplication strategy: merge, keep_first, keep_last, keep_most_visited
  - `--preview` - Preview changes without applying
  - `--stats` - Show duplicate statistics only

### Tag Management

- `btk tag tree <lib_dir>` - Display tags in hierarchical tree structure
- `btk tag stats <lib_dir>` - Show tag usage statistics
- `btk tag rename <lib_dir> <old_tag> <new_tag>` - Rename a tag and all its children
- `btk tag merge <lib_dir> <tag1> <tag2>... --into <target>` - Merge multiple tags into one
- `btk tag filter <lib_dir> <prefix>` - Filter bookmarks by tag prefix (e.g., "programming/")

### Bulk Operations

- `btk bulk add <lib_dir> --from-file <urls.txt>` - Add multiple bookmarks from a file
  - `--tags` - Comma-separated tags to apply to all bookmarks
  - `--no-fetch-titles` - Don't fetch titles from URLs
- `btk bulk edit <lib_dir>` - Edit multiple bookmarks matching criteria
  - `--filter-tags <prefix>` - Filter by tag prefix
  - `--filter-url <pattern>` - Filter by URL pattern
  - `--filter-starred/--filter-unstarred` - Filter by starred status
  - `--add-tags` - Tags to add
  - `--remove-tags` - Tags to remove
  - `--set-stars true/false` - Set starred status
  - `--set-description` - Set description
  - `--preview` - Preview changes without applying
- `btk bulk remove <lib_dir>` - Remove multiple bookmarks matching criteria
  - `--filter-tags`, `--filter-url` - Same as bulk edit
  - `--filter-visits-min/max` - Filter by visit count range
  - `--filter-no-description` - Filter bookmarks without description
  - `--preview` - Preview removals without applying
  - `--output-removed` - Save removed bookmarks to directory

### Other Commands

- `btk merge union|intersection|difference <lib1> <lib2>...` - Merge bookmark libraries
- `btk visit <lib_dir> <id>` - Visit bookmark in browser
- `btk reachable <lib_dir>` - Check which bookmarks are reachable
- `btk purge <lib_dir> --unreachable` - Remove unreachable bookmarks

## Code Architecture

The project is organized as a Python package with the following structure:

- **btk/cli.py**: Main entry point containing the argparse-based CLI interface. Implements all btk commands.

- **btk/utils.py**: Core utility functions for bookmark management including:
  - Loading/saving bookmark libraries
  - Managing favicons
  - URL validation and normalization
  - Bookmark data structure handling

- **btk/tools.py**: Implementation of bookmark operations including:
  - Import/export functions for all formats
  - Search and filtering
  - Bookmark manipulation (add, remove, edit)
  - Reachability checking

- **btk/merge.py**: Set operations for merging bookmark libraries (union, intersection, difference)

### Data Structure

Bookmarks are stored in JSON format in a library directory with:

- `bookmarks.json`: Main bookmark data file
- `favicons/`: Directory containing downloaded favicon images

Each bookmark entry contains fields like: id, unique_id, title, url, added, stars, tags, visit_count, description, favicon, last_visited, reachable.

## Project Structure

- `btk/` - Main package directory
  - `cli.py` - Command-line interface
  - `tools.py` - Core bookmark operations
  - `utils.py` - Utility functions
  - `merge.py` - Bookmark library merging operations
  - `viz.py` - Visualization tools (to be moved to integrations)
- `tests/` - Test suite with unit and integration tests
- `integrations/` - External integrations
  - `mcp-btk/` - Model Context Protocol server for AI integration
  - `viz-btk/` - Visualization tools (future)

## Important Notes

- The tool uses JMESPath for structured querying of bookmarks. Numbers in JMESPath queries must be wrapped in backticks (e.g., `[?visit_count > \`5\`]`)
- Bookmark libraries are directories containing bookmarks.json and associated assets
- The project follows a modular architecture with integrations kept separate from the core tool
- Test coverage: Core modules (tools.py, utils.py) have 60-70% coverage, CLI has integration tests
