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
# Start the interactive shell (recommended for exploration)
btk shell

# Or use direct CLI commands
btk bookmark add https://example.com --title "Example" --tags tutorial,web
btk bookmark list
btk bookmark search "python"

# Import and export
btk import html bookmarks.html
btk export bookmarks.html html --hierarchical

# Tag management
btk tag add my-tag 42          # Add tag to bookmark #42
btk tag list                   # List all tags
btk tag tree                   # Show tag hierarchy
```

## Interactive Shell

BTK includes a powerful interactive shell with a virtual filesystem interface:

```sh
$ btk shell

btk:/$ ls
bookmarks  tags  starred  archived  recent  domains

btk:/$ cd tags
btk:/tags$ ls
programming/  research/  tutorial/  web/

btk:/tags$ cd programming/python
btk:/tags/programming/python$ ls
3298  4095  5124  5789  (bookmark IDs with this tag)

btk:/tags/programming/python$ cat 4095/title
Advanced Python Techniques

btk:/tags/programming/python$ star 4095
★ Starred bookmark #4095

btk:/tags/programming/python$ recent
# Shows recently visited bookmarks in this context

btk:/tags/programming/python$ cd /bookmarks/4095
btk:/bookmarks/4095$ pwd
/bookmarks/4095

btk:/bookmarks/4095$ tag data-science machine-learning
✓ Added tags to bookmark #4095
```

### Shell Features

- **Virtual filesystem** - Navigate bookmarks like files and directories
- **Hierarchical tags** - Tags like `programming/python/django` create navigable folders
- **Context-aware commands** - Commands adapt based on your current location
- **Unix-like interface** - Familiar `cd`, `ls`, `pwd`, `mv`, `cp` commands
- **Tab completion** - (planned) Auto-complete for commands and paths
- **Tag operations** - Rename tags with `mv old-tag new-tag`
- **Bulk operations** - Copy tags to multiple bookmarks with `cp`

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

## CLI Commands

BTK organizes commands into logical groups. Use `btk <group> <command>` syntax:

### Bookmark Operations

```sh
# Add bookmarks
btk bookmark add https://example.com --title "Example" --tags tutorial,reference
btk bookmark add https://paper.pdf --tags research,ml  # Auto-extracts PDF text

# List and search
btk bookmark list                       # List all bookmarks
btk bookmark list --limit 10            # List first 10
btk bookmark search "machine learning"  # Search bookmarks
btk bookmark search "python" --in-content  # Search cached content

# Get bookmark details
btk bookmark get 42                     # Simple view
btk bookmark get 42 --details           # Full details
btk bookmark get 42 --format json       # JSON output

# Update bookmarks
btk bookmark update 42 --title "New Title" --tags python,tutorial --stars
btk bookmark update 42 --add-tags advanced --remove-tags beginner

# Delete bookmarks
btk bookmark delete 42
btk bookmark delete --filter-tags old/  # Delete by tag prefix

# Query with JMESPath
btk bookmark query "[?stars == \`true\`].title"  # Starred bookmarks
btk bookmark query "[?visit_count > \`5\`]"      # Frequently visited
```

### Tag Management

```sh
# List tags
btk tag list                            # All tags
btk tag tree                            # Hierarchical tree view
btk tag stats                           # Usage statistics

# Tag operations
btk tag add my-tag 42 43 44             # Add tag to bookmarks
btk tag remove old-tag 42               # Remove tag from bookmark
btk tag rename old-tag new-tag          # Rename tag everywhere
btk tag copy source-tag 42              # Copy tag to bookmark
btk tag filter programming/python       # Filter by tag prefix
```

### Import & Export

```sh
# Import from various formats
btk import html bookmarks.html          # Netscape HTML format
btk import json bookmarks.json          # JSON format
btk import csv bookmarks.csv            # CSV format
btk import markdown notes.md            # Extract links from markdown
btk import text urls.txt                # Plain text URLs

# Import browser bookmarks
btk import chrome                       # Import from Chrome
btk import firefox --profile default    # Import from Firefox profile

# Export to various formats
btk export output.html html --hierarchical  # HTML with folder structure
btk export output.json json                 # JSON format
btk export output.csv csv                   # CSV format
btk export output.md markdown               # Markdown with sections
```

### Content Operations

```sh
# Refresh cached content
btk content refresh --id 42             # Refresh specific bookmark
btk content refresh --all               # Refresh all bookmarks
btk content refresh --all --workers 50  # Use 50 parallel workers

# View cached content
btk content view 42                     # View markdown in terminal
btk content view 42 --html              # Open HTML in browser

# Auto-tag using content
btk content auto-tag --id 42            # Preview suggested tags
btk content auto-tag --id 42 --apply    # Apply suggested tags
btk content auto-tag --all --workers 100  # Tag all bookmarks
```

### Database Operations

```sh
# Database info
btk db info                             # Show statistics
btk db stats                            # Detailed stats
btk db vacuum                           # Optimize database

# Deduplication
btk db dedupe --strategy merge          # Merge duplicate metadata
btk db dedupe --strategy keep_first     # Keep oldest bookmark
btk db dedupe --preview                 # Preview changes
```

### Configuration

```sh
btk config show                         # Show current config
btk config set database.path ~/bookmarks.db
btk config set output.format json
```

### Shell

```sh
btk shell                               # Start interactive shell
btk shell --db ~/bookmarks.db           # Use specific database
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
- **Models**: Bookmark, Tag, ContentCache, BookmarkHealth, Collection
- **CLI**: Grouped argparse structure with Rich for beautiful terminal output
- **Shell**: Interactive REPL with virtual filesystem and context-aware commands
- **Testing**: pytest with 515 tests, >80% coverage on core modules
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
├── cli.py              # Grouped command-line interface
├── shell.py            # Interactive shell with virtual filesystem
├── db.py               # Database operations
├── models.py           # SQLAlchemy models
├── graph.py            # Bookmark relationship graphs
├── importers.py        # Import from various formats
├── exporters.py        # Export to various formats
├── content_fetcher.py  # Web content fetching
├── content_cache.py    # Content cache management
├── content_extractor.py # Content extraction & parsing
├── auto_tag.py         # Auto-tagging with NLP/TF-IDF
├── plugins.py          # Plugin system
├── tag_utils.py        # Tag operations & hierarchies
├── dedup.py            # Deduplication strategies
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

- **Overall: 515 tests, all passing** ✅
- Core modules: >80% coverage
  - graph.py: 97.28%
  - models.py: 96.62%
  - tag_utils.py: 95.67%
  - content_extractor.py: 93.63%
  - exporters.py: 92.45%
  - plugins.py: 90.07%
  - dedup.py: 88.24%
  - utils.py: 88.57%
  - db.py: 86.91%
- Interface modules:
  - shell.py: 53.12% (69 tests)
  - cli.py: 23.11% (41 tests)
  - Expected lower coverage for interactive/CLI code

## Roadmap

### Recently Completed ✅

- **Smart Collections & Time-Based Recent** (v0.7.1)
  - 5 auto-updating smart collections (`/unread`, `/popular`, `/broken`, `/untagged`, `/pdfs`)
  - Time-based navigation with 6 periods × 3 activity types
  - Enhanced `/recent` with hierarchical structure
  - Collection counts in `ls` output
- **Interactive Shell with Virtual Filesystem** (v0.7.0)
  - Unix-like navigation (`cd`, `ls`, `pwd`)
  - Hierarchical tag browsing
  - Context-aware commands
  - Tag operations (`mv`, `cp`)
- **Grouped CLI Structure** - Organized commands by functionality
- **Comprehensive Test Suite** - 515 tests with >50% shell coverage
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

- **Enhanced Domain Organization** - Improved domain-based browsing and filtering
- **Bookmark Notes/Annotations** - Rich text notes and annotations on bookmarks
- **User-Defined Collections** - Custom smart collections via configuration
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
