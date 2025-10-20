# Core Commands

BTK organizes commands into logical groups, making it easy to discover and use related functionality. This guide covers the most commonly used CLI commands.

!!! tip "Two Interfaces"
    BTK provides both a **CLI** (command-line interface) for scripting and automation, and an **interactive shell** for exploration. See the [Shell Guide](shell.md) for the interactive interface.

!!! info "Smart Collections in Shell (v0.7.1)"
    The interactive shell now includes **smart collections** - auto-updating virtual directories that help you organize bookmarks:

    - `/unread` - Bookmarks never visited
    - `/popular` - Top 100 most visited bookmarks
    - `/broken` - Unreachable bookmarks
    - `/untagged` - Bookmarks without tags
    - `/pdfs` - PDF document bookmarks

    Additionally, the `/recent` directory now provides **time-based navigation** with hierarchical browsing by time period (today, yesterday, this-week, etc.) and activity type (visited, added, starred).

    See the [Shell Guide](shell.md#smart-collections-v071) for full details.

## Command Structure

BTK uses a grouped command structure:

```bash
btk <group> <command> [options]
```

**Command Groups:**

- `bookmark` - Core CRUD operations on bookmarks
- `tag` - Tag management and organization
- `content` - Content fetching and caching
- `import` - Import from various formats
- `export` - Export to various formats
- `db` - Database management
- `graph` - Graph analysis
- `config` - Configuration management
- `shell` - Launch interactive shell

## Bookmark Operations

The `bookmark` group contains all core operations for managing individual bookmarks.

### Add Bookmarks

Add a new bookmark to your collection:

```bash
btk bookmark add <url> [options]
```

**Options:**

- `--title TEXT` - Bookmark title (auto-fetched if not provided)
- `--tags TEXT` - Comma-separated tags
- `--description TEXT` - Bookmark description
- `--stars` - Mark as starred
- `--no-fetch` - Don't fetch title/content automatically

**Examples:**

```bash
# Simple add with auto-fetched title
btk bookmark add https://example.com

# Add with metadata
btk bookmark add https://example.com \
  --title "Example Site" \
  --tags "tutorial,web,beginner" \
  --description "A great example site" \
  --stars

# Add without fetching content
btk bookmark add https://example.com --no-fetch

# Add PDF with automatic text extraction
btk bookmark add https://arxiv.org/pdf/2301.00001.pdf \
  --tags "research,ml,papers"
```

### List Bookmarks

List bookmarks with filtering and sorting:

```bash
btk bookmark list [options]
```

**Options:**

- `--limit N` - Limit results to N bookmarks
- `--offset N` - Skip first N bookmarks
- `--tags TEXT` - Filter by tags (comma-separated)
- `--starred` - Show only starred bookmarks
- `--domain TEXT` - Filter by domain
- `--sort FIELD` - Sort by field (added, title, visits, etc.)
- `--format FORMAT` - Output format (table, json, csv)

**Examples:**

=== "Basic Listing"
    ```bash
    # List all bookmarks
    btk bookmark list

    # List first 20 bookmarks
    btk bookmark list --limit 20

    # List with offset (pagination)
    btk bookmark list --limit 20 --offset 40
    ```

=== "Filtering"
    ```bash
    # Show only starred bookmarks
    btk bookmark list --starred

    # Filter by tags
    btk bookmark list --tags python,tutorial

    # Filter by domain
    btk bookmark list --domain github.com

    # Combine filters
    btk bookmark list --starred --tags python --limit 10
    ```

=== "Sorting"
    ```bash
    # Most recently added
    btk bookmark list --sort added --limit 10

    # Most visited
    btk bookmark list --sort visits --limit 10

    # Alphabetical by title
    btk bookmark list --sort title
    ```

=== "Output Formats"
    ```bash
    # Table format (default)
    btk bookmark list --format table

    # JSON output
    btk bookmark list --format json > bookmarks.json

    # CSV output
    btk bookmark list --format csv > bookmarks.csv
    ```

### Search Bookmarks

Search for bookmarks using full-text search:

```bash
btk bookmark search <query> [options]
```

**Options:**

- `--tags TEXT` - Filter by tags
- `--starred` - Search only starred bookmarks
- `--in-content` - Search in cached content (not just title/URL)
- `--limit N` - Limit results

**Examples:**

```bash
# Search titles and URLs
btk bookmark search "python tutorial"

# Search within cached content
btk bookmark search "machine learning" --in-content

# Search with tag filter
btk bookmark search "tutorial" --tags python,web

# Search starred bookmarks
btk bookmark search "important" --starred --limit 10
```

### Get Bookmark Details

Retrieve detailed information about a specific bookmark:

```bash
btk bookmark get <id> [options]
```

**Options:**

- `--details` - Show full details including content cache info
- `--format FORMAT` - Output format (table, json, yaml)

**Examples:**

```bash
# Basic info
btk bookmark get 123

# Full details
btk bookmark get 123 --details

# JSON output
btk bookmark get 123 --format json
```

**Output:**

```
Bookmark #123
─────────────────────────────────────────
Title:        Advanced Python Techniques
URL:          https://realpython.com/advanced-python-techniques/
Description:  Comprehensive guide to advanced Python features
Added:        2024-03-15 14:30:00
Stars:        ★ Starred
Visits:       15 times
Last Visited: 2024-10-19 14:30:00
Tags:         python, advanced, techniques
Domain:       realpython.com
Content:      Cached (45.2 KB, fetched 2024-10-19)
Status:       ✓ Reachable
```

### Update Bookmarks

Update bookmark metadata:

```bash
btk bookmark update <id> [options]
```

**Options:**

- `--title TEXT` - Update title
- `--description TEXT` - Update description
- `--stars` / `--no-stars` - Set starred status
- `--add-tags TEXT` - Add tags (comma-separated)
- `--remove-tags TEXT` - Remove tags (comma-separated)
- `--set-tags TEXT` - Replace all tags

**Examples:**

```bash
# Update title
btk bookmark update 123 --title "New Title"

# Star bookmark
btk bookmark update 123 --stars

# Add tags
btk bookmark update 123 --add-tags "important,featured"

# Remove tags
btk bookmark update 123 --remove-tags "draft,wip"

# Replace all tags
btk bookmark update 123 --set-tags "python,tutorial,beginner"

# Multiple updates at once
btk bookmark update 123 \
  --title "Updated Title" \
  --stars \
  --add-tags "reviewed"
```

### Delete Bookmarks

Remove bookmarks from your collection:

```bash
btk bookmark delete <id> [<id> ...] [options]
```

**Options:**

- `--filter-tags TEXT` - Delete bookmarks with these tags
- `--filter-domain TEXT` - Delete bookmarks from domain
- `--dry-run` - Preview what would be deleted

**Examples:**

```bash
# Delete single bookmark
btk bookmark delete 123

# Delete multiple bookmarks
btk bookmark delete 123 456 789

# Delete all bookmarks with tag
btk bookmark delete --filter-tags "old,deprecated"

# Preview deletion
btk bookmark delete --filter-tags "old" --dry-run
```

!!! danger "Permanent Deletion"
    Deleted bookmarks cannot be recovered. Use `--dry-run` to preview deletions.

### Query Bookmarks

Advanced querying using SQL-like syntax:

```bash
btk bookmark query <sql-query>
```

**Examples:**

```bash
# Starred bookmarks with many visits
btk bookmark query "stars = true AND visit_count > 10"

# Recent bookmarks
btk bookmark query "added > '2024-10-01'"

# Complex query
btk bookmark query "stars = true AND (tags LIKE '%python%' OR tags LIKE '%tutorial%')"
```

## Tag Management

The `tag` group provides commands for managing tags and tag hierarchies.

### List Tags

Display all tags:

```bash
btk tag list [options]
```

**Options:**

- `--tree` - Show hierarchical tree view
- `--stats` - Show usage statistics
- `--format FORMAT` - Output format

**Examples:**

=== "Simple List"
    ```bash
    btk tag list

    programming
    programming/python
    programming/python/web
    programming/python/data-science
    research
    tutorial
    ```

=== "Tree View"
    ```bash
    btk tag tree

    📁 Root
    ├── 📁 programming (127 bookmarks)
    │   ├── 📁 python (89 bookmarks)
    │   │   ├── 📁 web (34 bookmarks)
    │   │   ├── 📁 data-science (28 bookmarks)
    │   │   └── 📁 testing (19 bookmarks)
    │   ├── 📁 javascript (45 bookmarks)
    │   └── 📁 go (23 bookmarks)
    ├── 📁 research (67 bookmarks)
    └── 📁 tutorial (156 bookmarks)
    ```

=== "Statistics"
    ```bash
    btk tag stats

    Tag Statistics
    ─────────────────────────────────────────
    Total Tags: 47
    Total Usage: 1,234 (avg 26.3 per tag)

    Most Used Tags:
    1. tutorial (156 bookmarks)
    2. programming (127 bookmarks)
    3. python (89 bookmarks)
    4. research (67 bookmarks)
    5. web (56 bookmarks)

    Least Used Tags:
    1. draft (1 bookmark)
    2. archive (2 bookmarks)
    3. temp (3 bookmarks)
    ```

### Add Tags

Add tags to bookmarks:

```bash
btk tag add <tag> <id> [<id> ...] [options]
```

**Options:**

- `--all` - Add tag to all bookmarks
- `--starred` - Add tag to all starred bookmarks
- `--filter-tags TEXT` - Add to bookmarks with these tags

**Examples:**

```bash
# Add tag to specific bookmarks
btk tag add important 123 456 789

# Add tag to all starred bookmarks
btk tag add reviewed --starred

# Add tag to bookmarks with existing tags
btk tag add needs-review --filter-tags "draft,wip"

# Add hierarchical tag
btk tag add programming/python/advanced 123
```

### Remove Tags

Remove tags from bookmarks:

```bash
btk tag remove <tag> <id> [<id> ...] [options]
```

**Options:**

- `--all` - Remove tag from all bookmarks
- `--filter-tags TEXT` - Remove from bookmarks with these tags

**Examples:**

```bash
# Remove tag from specific bookmarks
btk tag remove draft 123 456

# Remove tag from all bookmarks
btk tag remove old --all

# Remove from filtered bookmarks
btk tag remove wip --filter-tags "completed"
```

### Rename Tags

Rename a tag across all bookmarks:

```bash
btk tag rename <old-tag> <new-tag>
```

**Examples:**

```bash
# Simple rename
btk tag rename javascript js

# Rename with hierarchy
btk tag rename programming/python/web programming/python/web-dev

# Reorganize hierarchy
btk tag rename backend programming/backend
```

!!! warning "Global Operation"
    This renames the tag in ALL bookmarks. The operation will show how many bookmarks will be affected and ask for confirmation.

### Copy Tags

Copy a tag to additional bookmarks:

```bash
btk tag copy <tag> [options]
```

**Options:**

- `--to-ids ID [ID ...]` - Copy to specific bookmark IDs
- `--starred` - Copy to all starred bookmarks
- `--filter-tags TEXT` - Copy to bookmarks with these tags

**Examples:**

```bash
# Copy to specific bookmarks
btk tag copy featured --to-ids 123 456 789

# Copy to starred bookmarks
btk tag copy high-priority --starred

# Copy to bookmarks with tags
btk tag copy reviewed --filter-tags "programming/python"
```

### Filter by Tags

List bookmarks with specific tag prefix:

```bash
btk tag filter <prefix>
```

**Examples:**

```bash
# All Python bookmarks
btk tag filter programming/python

# All tutorial bookmarks
btk tag filter tutorial

# Combine with other commands
btk tag filter programming/python | btk export output.html html
```

## Content Operations

The `content` group manages cached webpage content.

### Refresh Content

Fetch or refresh cached content for bookmarks:

```bash
btk content refresh [options]
```

**Options:**

- `--id ID` - Refresh specific bookmark
- `--all` - Refresh all bookmarks
- `--force` - Force refresh even if cached
- `--workers N` - Number of parallel workers (default: 10)
- `--starred` - Refresh only starred bookmarks
- `--filter-tags TEXT` - Refresh bookmarks with tags

**Examples:**

```bash
# Refresh specific bookmark
btk content refresh --id 123

# Refresh all bookmarks
btk content refresh --all

# Refresh with more workers (faster)
btk content refresh --all --workers 50

# Force refresh starred bookmarks
btk content refresh --starred --force

# Refresh bookmarks with tag
btk content refresh --filter-tags "programming/python"
```

**Output:**

```
Refreshing content for 234 bookmarks...
[████████████████████████████████] 234/234 (100%)

Summary:
  ✓ Success:    198 bookmarks
  ⚠ Errors:      23 bookmarks (unreachable)
  ⊘ Skipped:     13 bookmarks (already cached)

Time: 45.3 seconds
Avg Speed: 5.2 bookmarks/second
```

### View Content

View cached content for a bookmark:

```bash
btk content view <id> [options]
```

**Options:**

- `--html` - Open HTML in browser
- `--markdown` - Display markdown in terminal (default)
- `--raw` - Show raw HTML

**Examples:**

```bash
# View as markdown in terminal
btk content view 123

# Open HTML in browser
btk content view 123 --html

# Show raw HTML
btk content view 123 --raw
```

### Auto-Tag Content

Generate tags automatically based on cached content:

```bash
btk content auto-tag [options]
```

**Options:**

- `--id ID` - Auto-tag specific bookmark
- `--all` - Auto-tag all bookmarks
- `--apply` - Apply suggested tags (otherwise just preview)
- `--threshold FLOAT` - Confidence threshold (0.0-1.0, default: 0.5)
- `--workers N` - Number of parallel workers
- `--max-tags N` - Maximum tags to suggest (default: 5)

**Examples:**

```bash
# Preview tags for specific bookmark
btk content auto-tag --id 123

# Preview tags for all bookmarks
btk content auto-tag --all

# Apply tags with confirmation
btk content auto-tag --id 123 --apply

# Bulk auto-tag with high confidence threshold
btk content auto-tag --all --apply --threshold 0.7 --workers 20
```

**Output:**

```
Analyzing bookmark #123...

Current tags: python, tutorial
Suggested tags (confidence):
  1. web-development (0.87)
  2. flask (0.76)
  3. backend (0.64)
  4. api (0.58)

Apply these tags? [y/N]: y
✓ Added 4 tags to bookmark #123
```

## Import Operations

The `import` group handles importing bookmarks from various formats.

### Import HTML

Import bookmarks from HTML (Netscape Bookmark Format):

```bash
btk import html <file> [options]
```

**Options:**

- `--add-tags TEXT` - Add tags to all imported bookmarks
- `--skip-duplicates` - Skip bookmarks that already exist

**Examples:**

```bash
# Import from browser export
btk import html bookmarks.html

# Import with additional tags
btk import html bookmarks.html --add-tags "imported,firefox"

# Skip duplicates
btk import html bookmarks.html --skip-duplicates
```

### Import JSON

Import from JSON format:

```bash
btk import json <file> [options]
```

**Examples:**

```bash
# Import JSON
btk import json bookmarks.json

# Import with tags
btk import json bookmarks.json --add-tags "imported"
```

### Import CSV

Import from CSV file:

```bash
btk import csv <file> [options]
```

**CSV Format:**

```csv
url,title,tags,description
https://example.com,Example Site,"tutorial,web",A great example
https://example.org,Example Org,"reference",Reference documentation
```

**Examples:**

```bash
# Import CSV
btk import csv bookmarks.csv

# Import with additional tags
btk import csv bookmarks.csv --add-tags "imported,2024"
```

### Import Text

Import plain text file with URLs (one per line):

```bash
btk import text <file> [options]
```

**Options:**

- `--add-tags TEXT` - Tags for all imported bookmarks
- `--fetch-titles` - Fetch titles from URLs (default: true)

**Examples:**

```bash
# Import URLs
btk import text urls.txt

# Import without fetching titles
btk import text urls.txt --no-fetch-titles

# Import with tags
btk import text urls.txt --add-tags "reading-list,2024"
```

### Import from Browser

Import directly from browser bookmark databases:

```bash
# Chrome/Chromium
btk import chrome [options]

# Firefox
btk import firefox [options]

# Safari
btk import safari [options]
```

**Options:**

- `--profile TEXT` - Browser profile name
- `--add-tags TEXT` - Tags for imported bookmarks

**Examples:**

```bash
# Import from default Chrome profile
btk import chrome

# Import from specific Firefox profile
btk import firefox --profile work

# Import with tags
btk import chrome --add-tags "chrome,browser"
```

## Export Operations

The `export` group handles exporting bookmarks to various formats.

### Export HTML

Export to browser-compatible HTML:

```bash
btk export html <output-file> [options]
```

**Options:**

- `--hierarchical` - Create folder hierarchy from tags
- `--starred` - Export only starred bookmarks
- `--filter-tags TEXT` - Export bookmarks with tags
- `--include-archived` - Include archived bookmarks

**Examples:**

=== "Basic Export"
    ```bash
    # Simple HTML export
    btk export html bookmarks.html
    ```

=== "Hierarchical Export"
    ```bash
    # Export with folder structure from tags
    btk export html bookmarks.html --hierarchical

    # Result in browser:
    # 📁 Programming
    #   📁 Python
    #     📁 Web
    #       🔖 Flask Documentation
    #       🔖 Django Tutorial
    #     📁 Data Science
    #       🔖 NumPy Guide
    ```

=== "Filtered Export"
    ```bash
    # Export starred bookmarks
    btk export html starred.html --starred

    # Export by tags
    btk export html python.html --filter-tags "programming/python"

    # Combine filters
    btk export html important.html --starred --filter-tags "work"
    ```

### Export JSON

Export to JSON format:

```bash
btk export json <output-file> [options]
```

**Examples:**

```bash
# Export all bookmarks
btk export json bookmarks.json

# Export starred bookmarks
btk export json starred.json --starred

# Export with filter
btk export json python.json --filter-tags "python"
```

**JSON Format:**

```json
[
  {
    "id": 123,
    "url": "https://example.com",
    "title": "Example Site",
    "description": "A great example",
    "tags": ["tutorial", "web"],
    "stars": true,
    "added": "2024-03-15T14:30:00Z",
    "visit_count": 15,
    "last_visited": "2024-10-19T14:30:00Z"
  }
]
```

### Export CSV

Export to CSV format:

```bash
btk export csv <output-file> [options]
```

**Examples:**

```bash
# Export to CSV
btk export csv bookmarks.csv

# Export with filter
btk export csv python.csv --filter-tags "python"
```

### Export Markdown

Export to Markdown format:

```bash
btk export markdown <output-file> [options]
```

**Examples:**

```bash
# Export to Markdown
btk export markdown bookmarks.md

# Export starred bookmarks
btk export markdown starred.md --starred
```

**Markdown Format:**

```markdown
# Bookmarks

## Programming

### Python

- [Advanced Python Techniques](https://realpython.com/advanced-python-techniques/)
  - Tags: python, advanced, techniques
  - ⭐ Starred
  - Added: 2024-03-15

- [NumPy Documentation](https://numpy.org/doc/)
  - Tags: python, data-science, numpy
  - Added: 2024-02-01
```

## Database Operations

The `db` group provides database management commands.

### Database Info

Show database statistics:

```bash
btk db info
```

**Output:**

```
Database Information
─────────────────────────────────────────
Path:             /home/user/btk.db
Size:             45.2 MB
Bookmarks:        1,234
Tags:             47
Starred:          123 (10.0%)
Cached Content:   987 (80.0%)
Total Visits:     12,345

Health Metrics:
  Reachable:      1,156 (93.7%)
  Unreachable:    78 (6.3%)
  Duplicates:     5 possible
```

### Database Schema

Display database schema:

```bash
btk db schema
```

### Database Statistics

Show detailed statistics:

```bash
btk db stats [options]
```

**Options:**

- `--tags` - Tag statistics
- `--domains` - Domain statistics
- `--activity` - Activity statistics

**Examples:**

```bash
# General statistics
btk db stats

# Tag statistics
btk db stats --tags

# Domain statistics
btk db stats --domains
```

### Vacuum Database

Optimize database file:

```bash
btk db vacuum
```

This reclaims unused space and optimizes the database file.

### Deduplicate Bookmarks

Find and handle duplicate bookmarks:

```bash
btk db dedupe [options]
```

**Options:**

- `--strategy TEXT` - merge, keep_first, keep_last, keep_most_visited
- `--preview` - Preview changes without applying
- `--stats` - Show duplicate statistics only

**Examples:**

```bash
# Preview duplicates
btk db dedupe --preview

# Show statistics
btk db dedupe --stats

# Merge duplicates (combine metadata)
btk db dedupe --strategy merge

# Keep first bookmark
btk db dedupe --strategy keep_first
```

## Configuration

The `config` group manages BTK configuration.

### Show Configuration

Display current configuration:

```bash
btk config show
```

**Output:**

```toml
[database]
path = "/home/user/btk.db"

[output]
format = "table"
colors = true

[import]
fetch_titles = true
skip_duplicates = false

[content]
workers = 10
cache_expiry_days = 30
```

### Set Configuration

Set configuration values:

```bash
btk config set <key> <value>
```

**Examples:**

```bash
# Set database path
btk config set database.path ~/bookmarks.db

# Set output format
btk config set output.format json

# Set number of workers
btk config set content.workers 50
```

### Initialize Configuration

Create default configuration file:

```bash
btk config init
```

## Shell

Launch the interactive shell:

```bash
btk shell [options]
```

**Options:**

- `--db PATH` - Database path

**Examples:**

```bash
# Launch shell
btk shell

# Launch with specific database
btk shell --db ~/bookmarks.db
```

See the [Shell Guide](shell.md) for detailed shell documentation.

## Common Workflows

### Daily Bookmark Management

```bash
# Add new bookmarks
btk bookmark add https://newsite.com --tags "python,tutorial"

# Review recent additions
btk bookmark list --sort added --limit 10

# Search for something
btk bookmark search "machine learning"

# Star important bookmarks
btk bookmark update 123 --stars
```

### Bulk Operations

```bash
# Import bookmarks
btk import html bookmarks.html

# Refresh all content
btk content refresh --all --workers 50

# Auto-tag based on content
btk content auto-tag --all --apply --threshold 0.7

# Export to different formats
btk export html bookmarks.html --hierarchical
btk export json backup.json
```

### Tag Organization

```bash
# View tag hierarchy
btk tag tree

# Rename tags
btk tag rename javascript js

# Consolidate tags
btk tag copy important --starred

# Filter by tags
btk tag filter programming/python
```

### Database Maintenance

```bash
# Check database health
btk db info

# Find duplicates
btk db dedupe --preview

# Optimize database
btk db vacuum

# Export backup
btk export json backup-$(date +%Y%m%d).json
```

## Tips and Best Practices

### Use Tag Hierarchies

Organize tags with `/` separators for better structure:

```bash
btk bookmark add https://flask.docs.com \
  --tags "programming/python/web/flask"
```

### Leverage Filters

Combine filters for precise operations:

```bash
btk bookmark list --starred --tags python --sort visits
```

### Automate with Scripts

BTK commands work great in shell scripts:

```bash
#!/bin/bash
# Backup starred bookmarks weekly
btk export json "backups/starred-$(date +%Y%m%d).json" --starred
```

### Regular Maintenance

Set up periodic maintenance tasks:

```bash
# Weekly: refresh content
btk content refresh --all --workers 50

# Monthly: deduplicate
btk db dedupe --strategy merge

# Monthly: optimize
btk db vacuum
```

## Next Steps

- **[Interactive Shell](shell.md)** - Learn the interactive shell interface
- **[Tags & Organization](tags.md)** - Deep dive into tag hierarchies
- **[Import & Export](import-export.md)** - Detailed import/export guide
- **[CLI Reference](../api/cli.md)** - Complete command reference

## See Also

- **[Configuration](../getting-started/configuration.md)** - Configure BTK behavior
- **[Python API](../api/python.md)** - Use BTK in Python code
- **[Architecture](../development/architecture.md)** - How BTK works
