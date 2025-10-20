# Bookmark Toolkit (BTK)

A modern, database-first bookmark manager with powerful features for organizing, searching, and analyzing your bookmarks.

## Key Features

### Interactive Shell with Virtual Filesystem

BTK's flagship feature - an interactive shell that lets you browse bookmarks like files in a Unix filesystem:

```bash
$ btk shell

btk:/$ ls
bookmarks/    (100)   All bookmarks
tags/                 Browse by tag hierarchy
starred/      (15)    Starred bookmarks
unread/       (42)    Bookmarks never visited
popular/      (100)   100 most visited bookmarks
recent/               Recently active (time-based)

btk:/$ cd tags/programming/python
btk:/tags/programming/python$ ls
web/  data-science/  testing/
3298  4095  5124  5789

btk:/tags/programming/python$ recent visited
# Shows recently visited Python bookmarks

btk:/tags/programming/python$ cd 4095
btk:/tags/programming/python/4095$ star
★ Starred bookmark #4095
```

**Shell Features:**

- Virtual filesystem with `/bookmarks`, `/tags`, `/starred`, `/archived`, `/recent`, `/domains`
- Unix-like navigation: `cd`, `ls`, `pwd`, `mv`, `cp`
- Context-aware commands that adapt based on your location
- Hierarchical tag browsing (e.g., `/tags/programming/python/web`)
- Tag operations: rename with `mv`, bulk tag with `cp`
- Activity tracking: `recent visited/added/starred`

[Learn the Shell →](guide/shell.md)

### Powerful Command-Line Interface

Organized grouped commands for scripting and automation:

```bash
# Bookmark operations
btk bookmark add https://example.com --tags "python,tutorial"
btk bookmark list --starred --tags python
btk bookmark search "machine learning" --in-content

# Tag management
btk tag tree                    # Hierarchical tag view
btk tag rename old-tag new-tag  # Rename globally
btk tag copy important --starred # Bulk tagging

# Content operations
btk content refresh --all --workers 50
btk content auto-tag --all --apply

# Import/Export
btk import html bookmarks.html
btk export html bookmarks.html --hierarchical

# Database management
btk db info
btk db dedupe --strategy merge
```

[Command Reference →](guide/commands.md)

### Hierarchical Tag System

Organize bookmarks with hierarchical tags using `/` separators:

```bash
programming/python/web/django
programming/python/data-science/pandas
research/machine-learning/nlp
tutorial/video/beginner
```

**Benefits:**

- Navigate tags like directories in the shell
- Filter by tag prefix (e.g., all `programming/python` bookmarks)
- Export as browser-compatible folders
- Rename/reorganize entire tag hierarchies
- Multi-dimensional organization

[Tag Guide →](guide/tags.md)

### Advanced Features

#### Content Caching & Search

- **Automatic caching** - Fetches and stores HTML/markdown content
- **PDF support** - Extracts text from PDF bookmarks
- **Full-text search** - Search within cached content
- **Compression** - zlib compression (70-80% reduction)
- **Offline access** - View cached content without internet

#### Auto-Tagging with NLP

- **TF-IDF analysis** - Analyzes content to suggest relevant tags
- **Confidence scoring** - Shows confidence for each suggested tag
- **Preview mode** - Review suggestions before applying
- **Bulk operations** - Auto-tag entire collection

#### Database Management

- **SQLite backend** - Fast, reliable, and portable
- **ACID transactions** - Data integrity guaranteed
- **Deduplication** - Find and merge duplicate bookmarks
- **Statistics** - Track usage patterns and health metrics
- **Optimization** - Vacuum and optimize database

#### Import & Export

**Import from:**

- Browser HTML exports (Chrome, Firefox, Safari)
- JSON, CSV, Markdown, plain text
- Direct browser import (Chrome, Firefox, Safari)

**Export to:**

- Hierarchical HTML (browser-compatible folders)
- JSON (full metadata preservation)
- CSV (data analysis)
- Markdown (documentation)

#### Graph Analysis

- **Similarity graphs** - Build weighted bookmark relationship networks
- **Multiple metrics** - Domain similarity, tag overlap, direct links
- **Export formats** - GEXF (Gephi), GraphML (yEd), JSON (Cytoscape)
- **Visualization** - Analyze bookmark relationships

[Graph Guide →](guide/graph.md)

## Why BTK?

### Modern Architecture

- **SQLAlchemy ORM** - Clean, maintainable database layer
- **SQLite backend** - Fast queries, ACID compliance, portability
- **Grouped CLI** - Organized command structure
- **Rich terminal output** - Beautiful tables and formatting
- **Comprehensive testing** - 515 tests, >80% core coverage

### Powerful Yet Simple

**Simple enough for daily use:**

```bash
btk shell                    # Interactive exploration
btk bookmark add https://..  # Quick additions
btk bookmark search "term"   # Fast searches
```

**Powerful enough for advanced workflows:**

```bash
# Bulk import and organize
btk import html bookmarks.html
btk content refresh --all --workers 50
btk content auto-tag --all --apply --threshold 0.7

# Complex queries
btk bookmark query "stars = true AND visit_count > 10"

# Graph analysis
btk graph build --min-edge-weight 4.0
btk graph export network.gexf --format gexf
```

### Flexible Organization

- **Multi-tagging** - One bookmark, many tags
- **Hierarchical structure** - Organize tags in trees
- **Smart collections** - Starred, archived, recent
- **Domain-based browsing** - View by website
- **Content-based search** - Find by cached content

### Privacy & Control

- **Local-first** - Your data stays on your machine
- **No cloud dependency** - Works offline
- **Open source** - MIT licensed
- **Portable** - Single SQLite database file
- **No tracking** - Your bookmarks are private

## Quick Start

### Installation

```bash
pip install bookmark-tk
```

### Initialize

```bash
btk init
```

### Choose Your Interface

=== "Interactive Shell"
    Perfect for exploration and interactive organization:

    ```bash
    btk shell

    btk:/$ cd tags/programming/python
    btk:/tags/programming/python$ recent
    btk:/tags/programming/python$ cd 4095
    btk:/tags/programming/python/4095$ star
    ```

=== "Command-Line"
    Perfect for scripting and automation:

    ```bash
    btk bookmark add https://example.com --tags python,tutorial
    btk bookmark list --starred
    btk tag tree
    btk export html bookmarks.html --hierarchical
    ```

[Full Quick Start →](getting-started/quickstart.md)

## Use Cases

### Personal Knowledge Management

Organize technical articles, tutorials, and documentation:

```
programming/
├── python/
│   ├── web/django
│   ├── data-science/pandas
│   └── testing/pytest
├── javascript/
│   ├── react
│   └── node
└── databases/
    ├── postgresql
    └── redis
```

### Research & Academia

Manage papers, datasets, and research resources:

```
research/
├── machine-learning/
│   ├── nlp/transformers
│   ├── computer-vision/cnn
│   └── reinforcement-learning/dqn
├── papers/
│   ├── to-read
│   ├── reading
│   └── completed
└── datasets/
    ├── image
    └── text
```

### Project Management

Track project resources and references:

```
projects/
├── website-redesign/
│   ├── inspiration
│   ├── tools
│   └── resources
├── ml-classifier/
│   ├── papers
│   ├── datasets
│   └── libraries
└── mobile-app/
    ├── react-native
    └── apis
```

### Content Curation

Build curated bookmark collections:

```bash
# Export curated lists
btk export html python-resources.html --filter-tags "python" --hierarchical
btk export markdown weekly-readings.md --filter-tags "to-read"

# Share collections
btk export json collection.json --starred --filter-tags "featured"
```

## Documentation

### Getting Started

- **[Installation](getting-started/installation.md)** - Install BTK
- **[Quick Start](getting-started/quickstart.md)** - Get up and running
- **[Configuration](getting-started/configuration.md)** - Configure BTK

### User Guide

- **[Interactive Shell](guide/shell.md)** - Virtual filesystem interface
- **[Core Commands](guide/commands.md)** - CLI reference
- **[Tags & Organization](guide/tags.md)** - Hierarchical tags
- **[Import & Export](guide/import-export.md)** - Data portability
- **[Search & Query](guide/search.md)** - Find bookmarks
- **[Content Caching](guide/content.md)** - Offline access
- **[Graph Analysis](guide/graph.md)** - Visualize relationships

### Advanced

- **[Plugin System](advanced/plugins.md)** - Extend functionality
- **[Browser Integration](advanced/browser.md)** - Browser sync
- **[Database Management](advanced/database.md)** - Manage data
- **[Performance Tuning](advanced/performance.md)** - Optimize speed

### Reference

- **[CLI Reference](api/cli.md)** - Complete command list
- **[Python API](api/python.md)** - Use BTK in Python
- **[Architecture](development/architecture.md)** - How BTK works
- **[Contributing](development/contributing.md)** - Help develop BTK

## Community & Support

- **GitHub**: [queelius/bookmark-tk](https://github.com/queelius/bookmark-tk)
- **Issues**: [Report bugs or request features](https://github.com/queelius/bookmark-tk/issues)
- **PyPI**: [bookmark-tk](https://pypi.org/project/bookmark-tk/)
- **Documentation**: [https://queelius.github.io/bookmark-tk/](https://queelius.github.io/bookmark-tk/)

## Recent Updates

### v0.7.1 - Smart Collections & Time-Based Navigation (October 2025)

- **Smart Collections** - 5 new auto-updating virtual directories
  - `/unread` - Bookmarks never visited
  - `/popular` - Top 100 most visited bookmarks
  - `/broken` - Unreachable bookmarks
  - `/untagged` - Bookmarks without tags
  - `/pdfs` - PDF document bookmarks
- **Time-Based Recent** - Hierarchical time navigation
  - Browse by period: today, yesterday, this-week, last-week, this-month, last-month
  - Filter by activity: visited, added, starred
  - 6 time periods × 3 activity types = 18 browsable directories
- **Enhanced organization** - Find and organize bookmarks more efficiently
- **Collection counts** - See bookmark counts at a glance in `ls` output

[Shell Guide →](guide/shell.md) | [Full Changelog →](development/changelog.md)

### v0.7.0 - Interactive Shell & Major Refactoring (October 2025)

- **New interactive shell** with virtual filesystem
- **Hierarchical tag navigation** - Browse tags like directories
- **Grouped CLI structure** - Organized commands
- **Context-aware commands** - Commands adapt to location
- **Tag operations** - `mv` for renaming, `cp` for copying
- **Activity tracking** - `recent` command with filters
- **515 tests** - Comprehensive test suite
- **>80% coverage** - Core modules thoroughly tested

[Full Changelog →](development/changelog.md)

## License

MIT License - see [LICENSE](https://github.com/queelius/bookmark-tk/blob/master/LICENSE) for details.

## Author

Developed by [Alex Towell](https://github.com/queelius)

---

**Ready to organize your bookmarks?** [Get Started →](getting-started/quickstart.md)
