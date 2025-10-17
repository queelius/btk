# Bookmark Toolkit (btk)

A modern, database-first bookmark manager with powerful features for organizing, searching, and analyzing your bookmarks.

## Features

- 🗄️ **SQLite-based storage** - Fast, reliable, and portable
- 📥 **Multi-format import** - HTML (Netscape), JSON, CSV, Markdown, plain text
- 📤 **Multi-format export** - HTML (hierarchical folders), JSON, CSV, Markdown
- 🔍 **Advanced search** - Full-text search including cached content
- 🏷️ **Hierarchical tags** - Organize with nested tags (e.g., `programming/python`)
- 🤖 **Auto-tagging** - NLP-powered automatic tag generation
- 📄 **Content caching** - Stores compressed HTML and markdown for offline access
- 📑 **PDF support** - Extracts and indexes text from PDF bookmarks
- 🔌 **Plugin system** - Extensible architecture for custom features
- 🌐 **Browser integration** - Import bookmarks and history from Chrome, Firefox, Safari
- 📊 **Statistics & analytics** - Track usage, duplicates, health scores
- ⚡ **Parallel processing** - Fast bulk operations with multi-threading

## Installation

```sh
pip install bookmark-tk
```

## Quick Start

```sh
# Initialize default database
btk init

# Import bookmarks from HTML
btk import html bookmarks.html

# Search bookmarks
btk search "python"

# Add a bookmark
btk add https://example.com --title "Example Site" --tags tutorial,web

# List all bookmarks
btk list

# Export to various formats
btk export bookmarks.html html --hierarchical
btk export bookmarks.json json
btk export bookmarks.csv csv
```

## Database Management

BTK uses a single SQLite database file (default: `btk.db`) instead of directory-based storage:

```sh
# Use default database (btk.db in current directory)
btk list

# Specify a different database
btk --db ~/bookmarks.db list

# Set default database in config
btk config set database.path ~/bookmarks.db

# Database operations
btk db info              # Show database statistics
btk db vacuum            # Optimize database
btk db export backup.db  # Export to new database
```

## Core Commands

### Import & Export

```sh
# Import from various formats
btk import html bookmarks.html          # Netscape HTML format
btk import json bookmarks.json          # JSON format
btk import csv bookmarks.csv            # CSV format
btk import markdown notes.md            # Extract links from markdown
btk import text urls.txt                # Plain text URLs

# Auto-detect format
btk import bookmarks.html               # Automatically detects format

# Import browser bookmarks
btk import chrome                       # Import from Chrome
btk import firefox --profile default    # Import from specific Firefox profile

# Export to various formats
btk export output.html html             # HTML with hierarchical folders
btk export output.json json             # JSON format
btk export output.csv csv               # CSV format
btk export output.md markdown           # Markdown with tag sections
```

### Search & Query

```sh
# Basic search (title, URL, description)
btk search "machine learning"

# Search in cached content
btk search "neural networks" --in-content

# Advanced queries with JMESPath
btk query "[?stars == \`true\`].title"                    # Starred bookmarks
btk query "[?visit_count > \`5\`].{title: title, url: url}" # Frequently visited

# Filter by tags
btk tags filter programming/python      # Bookmarks with tag prefix

# List tags with statistics
btk tags list
btk tags tree                           # Show tag hierarchy
btk tags stats                          # Tag usage statistics
```

### Bookmark Management

```sh
# Add bookmarks
btk add https://example.com --title "Example" --tags tutorial,reference
btk add https://paper.pdf --tags research,ml  # Automatically extracts PDF text

# Get bookmark details
btk get 42                              # Simple view
btk get 42 --details                    # Full details with metadata
btk get 42 --format json                # JSON output

# Update bookmarks
btk update 42 --title "New Title" --tags python,tutorial --stars true
btk update 42 --add-tags advanced --remove-tags beginner

# Delete bookmarks
btk delete 42
btk delete --tag-prefix old/            # Delete by tag prefix
```

### Content & Caching

```sh
# Refresh cached content
btk refresh --id 42                     # Refresh specific bookmark
btk refresh --all                       # Refresh all bookmarks
btk refresh --all --workers 50          # Use 50 parallel workers

# View cached content
btk view 42                             # View markdown in terminal
btk view 42 --html                      # Open HTML in browser

# Auto-tag using cached content
btk auto-tag --id 42                    # Preview tags for bookmark
btk auto-tag --id 42 --apply            # Apply suggested tags
btk auto-tag --all --workers 100 --apply # Tag all bookmarks in parallel
```

### Organization

```sh
# Tag operations
btk tags rename "old-tag" "new-tag"
btk tags merge tag1 tag2 tag3 --into merged-tag

# Deduplication
btk dedupe --strategy merge             # Merge duplicate metadata
btk dedupe --strategy keep_first        # Keep oldest bookmark
btk dedupe --strategy keep_most_visited # Keep most visited

# Statistics
btk stats                               # Database statistics
btk stats --tags                        # Tag statistics
```

## Configuration

BTK supports configuration files for persistent settings:

```sh
# Show configuration
btk config show

# Set configuration values
btk config set database.path ~/bookmarks.db
btk config set output.format json
btk config set import.fetch_titles true

# Configuration file location: ~/.config/btk/config.toml
```

## Advanced Features

### PDF Support

BTK automatically extracts text from PDF bookmarks for search and auto-tagging:

```sh
btk add https://arxiv.org/pdf/2301.00001.pdf --tags research,ml
btk search "neural network" --in-content  # Searches PDF text
btk view 42                                # View extracted PDF text
```

### Hierarchical Tags & Export

Organize bookmarks with hierarchical tags and export to browser-compatible HTML:

```sh
# Add bookmarks with hierarchical tags
btk add https://docs.python.org --tags programming/python/docs
btk add https://flask.palletsprojects.com --tags programming/python/web

# Export with folder structure
btk export bookmarks.html html --hierarchical

# Result: Nested folders in browser
# 📁 programming
#   📁 python
#     📁 docs
#       🔖 Python Documentation
#     📁 web
#       🔖 Flask Documentation
```

### Content Caching

BTK caches webpage content for offline access and full-text search:

- Fetches HTML and converts to markdown
- Compresses with zlib (70-80% compression ratio)
- Extracts text from PDFs
- Enables content-based search and auto-tagging

```sh
# Content is cached automatically when adding bookmarks
btk add https://example.com

# Manually refresh content
btk refresh --all --workers 50

# Search within cached content
btk search "specific phrase" --in-content
```

### Plugin System

BTK has an extensible plugin architecture:

```python
from btk.plugins import Plugin, PluginMetadata, PluginPriority

class MyPlugin(Plugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="Custom functionality",
            priority=PluginPriority.NORMAL
        )

    def on_bookmark_added(self, bookmark):
        # Custom logic when bookmark is added
        pass
```

## Architecture

### Modern Stack

- **Database**: SQLAlchemy ORM with SQLite backend
- **Models**: Bookmark, Tag, ContentCache, BookmarkHealth
- **CLI**: argparse with Rich for beautiful terminal output
- **Testing**: pytest with 59% code coverage (317 tests)
- **Content**: HTML/Markdown conversion, zlib compression, PDF extraction

### Database Schema

```
bookmarks
├── id (primary key)
├── unique_id (hash)
├── url
├── title
├── description
├── added (timestamp)
├── stars (boolean)
├── visit_count
├── last_visited
└── reachable (boolean)

tags
├── id
├── name (unique)
├── description
└── color

bookmark_tags (many-to-many)
├── bookmark_id
└── tag_id

content_cache
├── id
├── bookmark_id (foreign key)
├── html_content (compressed)
├── markdown_content
├── content_hash
├── fetched_at
└── status_code
```

### Code Organization

```
btk/
├── cli.py              # Command-line interface
├── db.py               # Database operations
├── models.py           # SQLAlchemy models
├── importers.py        # Import from various formats
├── exporters.py        # Export to various formats
├── content_fetcher.py  # Web content fetching & caching
├── content_cache.py    # Content cache management
├── plugins.py          # Plugin system
├── tag_utils.py        # Tag operations
├── dedup.py            # Deduplication
├── archiver.py         # Web archive integration
└── browser_import.py   # Browser bookmark import
```

## Development

### Running Tests

```sh
# Run all tests
pytest

# Run with coverage
pytest --cov=btk --cov-report=term-missing

# Run specific test file
pytest tests/test_db.py -v
```

### Test Coverage

- Overall: 59.40% (317 tests, all passing)
- Core modules: >80% coverage
  - db.py: 90.77%
  - exporters.py: 92.45%
  - importers.py: 82.35%
  - utils.py: 88.57%
  - tag_utils.py: 95.67%
  - dedup.py: 88.24%
  - plugins.py: 90.07%

## Roadmap

### Recently Completed ✅

- SQLAlchemy-based database architecture
- Content caching with compression
- PDF text extraction
- Auto-tagging with NLP
- Hierarchical tag export
- Parallel processing for bulk operations
- Browser bookmark import
- Plugin system

### In Progress 🚧

- Enhanced search capabilities
- Reading list management
- Link rot detection with Wayback Machine

### Planned Features 🎯

- Browser extensions (Chrome, Firefox)
- MCP integration for AI-powered queries
- Static site generator for bookmark collections
- Similarity detection and recommendations
- Full-text search with ranking
- Bookmark relationship graphs
- Social features (shared collections)

## Migration from Legacy JSON Format

If you're upgrading from an older JSON-based version of BTK:

1. The new version uses SQLite databases instead of JSON files
2. Use `btk import json old-bookmarks.json` to migrate your data
3. Legacy commands and directory-based storage are no longer supported
4. All functionality is now database-first with improved performance

## Contributing

Contributions are welcome! Areas for contribution:

- Adding new importers/exporters
- Creating plugins for custom functionality
- Improving test coverage
- Documentation improvements
- Performance optimizations

See the plugin system for the easiest way to extend BTK without modifying core code.

## License

MIT License - see LICENSE file for details.

## Author

Developed by [Alex Towell](https://github.com/queelius)

## Links

- GitHub: https://github.com/queelius/bookmark-tk
- Issues: https://github.com/queelius/bookmark-tk/issues
- PyPI: https://pypi.org/project/bookmark-tk/
