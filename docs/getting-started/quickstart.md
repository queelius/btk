# Quick Start

Get started with BTK in minutes. This guide covers basic setup and introduces both the CLI and interactive shell interfaces.

## Installation

Install BTK using pip:

```bash
pip install bookmark-tk
```

## Initialize Database

BTK uses a SQLite database to store your bookmarks. Initialize it:

```bash
# Create database in current directory
btk init

# Or specify a custom location
btk --db ~/my-bookmarks.db init
```

This creates a `btk.db` file (or your specified filename) with the necessary schema.

## Choose Your Interface

BTK provides two ways to interact with your bookmarks:

1. **CLI** - Command-line interface for scripting and automation
2. **Shell** - Interactive filesystem-like interface for exploration

### Quick Start: Interactive Shell

The shell is the best way to get started and explore BTK:

```bash
btk shell
```

You'll see:

```
╔════════════════════════════════════════════════════════════════╗
║                     BTK Shell v1.0                              ║
║          Browse your bookmarks like a filesystem                ║
╚════════════════════════════════════════════════════════════════╝

Type 'help' or '?' to list commands.
Type 'help <command>' for command details.
Type 'tutorial' for a quick tour.

btk:/$
```

#### Shell Basics

Navigate bookmarks like a filesystem:

```bash
# See what's available
btk:/$ ls
bookmarks/    (100)   All bookmarks
tags/                 Browse by tag hierarchy
starred/      (15)    Starred bookmarks
unread/       (42)    Bookmarks never visited
popular/      (100)   100 most visited bookmarks
recent/               Recently active (time-based)
broken/       (3)     Unreachable bookmarks
untagged/     (15)    Bookmarks with no tags
pdfs/         (8)     PDF bookmarks

# Browse bookmarks
btk:/$ cd bookmarks
btk:/bookmarks$ ls
# (shows your bookmarks)

# Navigate by tags
btk:/$ cd tags/programming/python
btk:/tags/programming/python$ ls
# (shows Python bookmarks and subtags)

# View bookmark details
btk:/bookmarks$ cd 123
btk:/bookmarks/123$ cat url
https://example.com

# Star a bookmark
btk:/bookmarks/123$ star
★ Starred bookmark #123
```

See the full [Shell Guide](../guide/shell.md) for all shell features.

### Quick Start: CLI

For scripting and quick commands, use the CLI:

```bash
# Add a bookmark
btk bookmark add https://example.com --title "Example" --tags tutorial,web

# List bookmarks
btk bookmark list

# Search bookmarks
btk bookmark search "python"

# Launch shell
btk shell
```

## Import Bookmarks

Import existing bookmarks from various sources:

### From Browser Export

Most browsers can export bookmarks as HTML:

```bash
# Export from browser (usually in Settings > Bookmarks > Export)
# Then import:
btk import html bookmarks.html
```

### From JSON

```bash
btk import json bookmarks.json
```

### From Text File

Import a list of URLs (one per line):

```bash
btk import text urls.txt
```

## Basic Operations

### Add Bookmarks

=== "Shell"
    ```bash
    btk:/$ cd bookmarks
    btk:/bookmarks$ add https://example.com
    Title: Example Site
    Tags: tutorial,web
    ✓ Added bookmark #123
    ```

=== "CLI"
    ```bash
    btk bookmark add https://example.com \
      --title "Example Site" \
      --tags "tutorial,web"
    ```

### Search Bookmarks

=== "Shell"
    ```bash
    btk:/$ find "python"
    Found 23 bookmarks matching 'python'
    ```

=== "CLI"
    ```bash
    btk bookmark search "python"
    ```

### List Bookmarks

=== "Shell"
    ```bash
    btk:/$ cd bookmarks
    btk:/bookmarks$ ls
    ID    Title                Tags         Added
    ──────────────────────────────────────────────
    123   Example Site         tutorial,web 2024-10-19
    124   Python Tutorial      python       2024-10-18
    ```

=== "CLI"
    ```bash
    btk bookmark list

    # With filters
    btk bookmark list --starred --tags python --limit 10
    ```

### Star Important Bookmarks

=== "Shell"
    ```bash
    btk:/bookmarks/123$ star
    ★ Starred bookmark #123

    # View starred bookmarks
    btk:/$ cd starred
    btk:/starred$ ls
    ```

=== "CLI"
    ```bash
    btk bookmark update 123 --stars

    # List starred
    btk bookmark list --starred
    ```

### Organize with Tags

=== "Shell"
    ```bash
    # Add tags to bookmark
    btk:/bookmarks/123$ tag important featured

    # Navigate by tags
    btk:/$ cd tags/important
    btk:/tags/important$ ls

    # Rename tags
    btk:/tags$ mv old-tag new-tag
    ```

=== "CLI"
    ```bash
    # Add tags
    btk tag add important 123 124 125

    # View tag tree
    btk tag tree

    # Rename tags
    btk tag rename old-tag new-tag
    ```

## Working with Hierarchical Tags

BTK supports hierarchical tags using `/` as a separator:

```bash
# Add bookmarks with hierarchical tags
btk bookmark add https://flask.com \
  --tags "programming/python/web/flask"

btk bookmark add https://numpy.org \
  --tags "programming/python/data-science/numpy"
```

This creates a navigable structure:

```
programming/
└── python/
    ├── web/
    │   └── flask
    └── data-science/
        └── numpy
```

### Navigating Hierarchies

=== "Shell"
    ```bash
    btk:/$ cd tags/programming
    btk:/tags/programming$ ls
    python/  javascript/  go/

    btk:/tags/programming$ cd python
    btk:/tags/programming/python$ ls
    web/  data-science/  testing/
    3298  4095  5124  (bookmark IDs)

    btk:/tags/programming/python$ cd web
    btk:/tags/programming/python/web$ ls
    flask/  django/  fastapi/
    1001  1002  1003  (more bookmarks)
    ```

=== "CLI"
    ```bash
    # View tag tree
    btk tag tree

    # Filter by tag prefix
    btk tag filter programming/python

    # List bookmarks with tag
    btk bookmark list --tags "programming/python"
    ```

## Export Bookmarks

Export your bookmarks to various formats:

### Export to HTML

Browser-compatible HTML format:

```bash
# Simple export
btk export html bookmarks.html

# Hierarchical export (creates folders from tags)
btk export html bookmarks.html --hierarchical
```

Import the HTML file into any browser!

### Export to JSON

```bash
# All bookmarks
btk export json bookmarks.json

# Starred only
btk export json starred.json --starred

# Filtered by tags
btk export json python.json --filter-tags "python"
```

### Export to Markdown

```bash
btk export markdown bookmarks.md
```

## Advanced Features

### Content Caching

BTK can cache webpage content for offline access and full-text search:

```bash
# Refresh content for all bookmarks
btk content refresh --all

# Search in cached content
btk bookmark search "machine learning" --in-content

# View cached content
btk content view 123
```

### Auto-Tagging

Let BTK suggest tags based on content:

```bash
# Preview suggested tags
btk content auto-tag --id 123

# Apply suggested tags
btk content auto-tag --id 123 --apply

# Bulk auto-tag
btk content auto-tag --all --apply --threshold 0.7
```

### Database Management

```bash
# View database info
btk db info

# Find duplicates
btk db dedupe --preview

# Optimize database
btk db vacuum
```

## Common Workflows

### Daily Bookmark Management

```bash
# Launch shell
btk shell

# View recent activity
btk:/$ recent

# Browse by tags
btk:/$ cd tags/programming/python
btk:/tags/programming/python$ ls

# Star important bookmarks
btk:/tags/programming/python$ cd 4095
btk:/tags/programming/python/4095$ star
```

### Using Smart Collections (v0.7.1)

Smart collections help you quickly find and organize bookmarks:

```bash
# Find bookmarks you haven't read yet
btk:/$ cd unread
btk:/unread$ ls
1001  1005  1023  1055  (42 bookmarks total)

# Review and tag them
btk:/unread$ cd 1001
btk:/unread/1001$ cat title
Machine Learning Paper: Attention Is All You Need

btk:/unread/1001$ tag research/ml/transformers to-read
btk:/unread/1001$ visit
# After visiting, automatically removed from /unread

# Check your most-visited references
btk:/$ cd popular
btk:/popular$ ls
# Shows top 100 most-visited bookmarks

# Find and fix broken links
btk:/$ cd broken
btk:/broken$ ls
2345  3456  4567  (3 unreachable bookmarks)

btk:/broken$ cat 2345/url
# Update or remove broken bookmarks

# Organize untagged bookmarks
btk:/$ cd untagged
btk:/untagged$ ls
5001  5002  5003  (15 untagged bookmarks)

# Tag them systematically
btk:/untagged/5001$ tag appropriate-tags

# Browse PDF documents
btk:/$ cd pdfs
btk:/pdfs$ ls
# All your PDF bookmarks in one place
```

### Time-Based Activity Review (v0.7.1)

Navigate bookmark activity by time periods:

```bash
# See what you bookmarked today
btk:/$ cd recent/today/added
btk:/recent/today/added$ ls
5001  5002  5003

# Review what you read this week
btk:/$ cd recent/this-week/visited
btk:/recent/this-week/visited$ ls
# Shows all bookmarks visited this week

# Check yesterday's reading
btk:/$ cd recent/yesterday/visited
btk:/recent/yesterday/visited$ ls
4876  4654  4321

# Compare this month vs last month
btk:/$ cd recent/this-month/added
btk:/recent/this-month/added$ ls | wc -l
45 bookmarks added this month

btk:/$ cd ../../../last-month/added
btk:/recent/last-month/added$ ls | wc -l
32 bookmarks added last month
```

### Organizing Bookmarks

```bash
# View tag structure
btk tag tree

# Rename tags for consistency
btk tag rename javascript js

# Reorganize flat tags into hierarchy
btk tag rename backend programming/backend
btk tag rename frontend programming/frontend

# Tag groups of bookmarks
btk tag copy important --starred
```

### Bulk Import and Organization

```bash
# Import bookmarks
btk import html bookmarks.html

# Refresh all content
btk content refresh --all --workers 50

# Auto-tag based on content
btk content auto-tag --all --apply

# Export organized bookmarks
btk export html organized-bookmarks.html --hierarchical
```

## Tips for Getting Started

### 1. Start with the Shell

The interactive shell is perfect for learning and exploration:

```bash
btk shell
btk:/$ help
btk:/$ tutorial
```

### 2. Use Hierarchical Tags

Organize from the start with hierarchical tags:

```bash
programming/python/web
programming/python/data-science
research/machine-learning/nlp
```

### 3. Leverage Content Caching

Cache content for offline access and better search:

```bash
# Cache as you add
btk bookmark add https://example.com  # Auto-caches

# Refresh periodically
btk content refresh --all
```

### 4. Regular Maintenance

Keep your bookmarks organized:

```bash
# Weekly: check recent additions
btk bookmark list --sort added --limit 20

# Monthly: find and merge duplicates
btk db dedupe --preview

# Monthly: optimize database
btk db vacuum
```

### 5. Export Backups

Regular backups ensure you never lose bookmarks:

```bash
# JSON backup (preserves all metadata)
btk export json backup-$(date +%Y%m%d).json

# HTML backup (browser-compatible)
btk export html backup.html --hierarchical
```

## Shell vs CLI: When to Use Each

### Use the Shell When:

- Exploring your bookmark collection
- Organizing tags interactively
- Reviewing recent activity
- Learning BTK features
- Working with bookmarks in context

### Use the CLI When:

- Scripting and automation
- Batch operations
- Integration with other tools
- Quick one-off commands
- Working in shell scripts

Both interfaces are powerful - use whichever fits your workflow!

## Configuration

BTK can be configured via configuration file:

```bash
# Show current config
btk config show

# Set database location
btk config set database.path ~/bookmarks.db

# Set default output format
btk config set output.format json

# Configuration file location
~/.config/btk/config.toml
```

## Next Steps

Now that you know the basics, dive deeper:

- **[Interactive Shell](../guide/shell.md)** - Complete shell guide with all commands
- **[Core Commands](../guide/commands.md)** - Full CLI reference
- **[Tags & Organization](../guide/tags.md)** - Master hierarchical tags
- **[Import & Export](../guide/import-export.md)** - Detailed import/export options
- **[Search & Query](../guide/search.md)** - Advanced search techniques

## Getting Help

- Type `help` in the shell for command help
- Use `btk --help` or `btk <group> --help` for CLI help
- Check the [documentation](https://queelius.github.io/bookmark-tk/)
- Report issues on [GitHub](https://github.com/queelius/bookmark-tk/issues)

Happy bookmarking!
