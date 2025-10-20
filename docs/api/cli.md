# CLI Reference

Complete command-line interface reference for BTK (Bookmark Toolkit).

## Command Structure

BTK uses a grouped command structure:

```bash
btk [global-options] <group> <command> [options] [arguments]
```

## Global Options

Options that apply to all commands:

- `--db PATH` - Database file path (default: `btk.db` in current directory)
- `--version` - Show version and exit
- `--help` - Show help message and exit

**Examples:**

```bash
# Use specific database
btk --db ~/bookmarks.db bookmark list

# Show version
btk --version

# Show help
btk --help
```

## Command Groups

### `btk bookmark` - Bookmark Operations

Core CRUD operations for managing bookmarks.

#### `btk bookmark add`

Add a new bookmark.

**Syntax:**
```bash
btk bookmark add <url> [options]
```

**Arguments:**

- `url` - URL of the bookmark (required)

**Options:**

- `--title TEXT` - Bookmark title (auto-fetched if not provided)
- `--description TEXT` - Bookmark description
- `--tags TEXT` - Comma-separated tags
- `--stars` - Mark as starred
- `--no-fetch` - Don't fetch title/content automatically

**Examples:**

```bash
btk bookmark add https://example.com
btk bookmark add https://example.com --title "Example Site"
btk bookmark add https://example.com --tags "python,tutorial" --stars
btk bookmark add https://example.com --no-fetch
```

#### `btk bookmark list`

List bookmarks with filtering and sorting.

**Syntax:**
```bash
btk bookmark list [options]
```

**Options:**

- `--limit N` - Limit results to N bookmarks
- `--offset N` - Skip first N bookmarks
- `--tags TEXT` - Filter by tags (comma-separated)
- `--starred` - Show only starred bookmarks
- `--archived` - Show archived bookmarks
- `--domain TEXT` - Filter by domain
- `--sort FIELD` - Sort by field (added, title, visits, etc.)
- `--format FORMAT` - Output format (table, json, csv)

**Sort Fields:**

- `added` - Date added (default)
- `title` - Alphabetical by title
- `visits` - Visit count
- `visited` - Last visited date
- `stars` - Starred status

**Examples:**

```bash
btk bookmark list
btk bookmark list --limit 20
btk bookmark list --starred --tags python
btk bookmark list --sort visits --limit 10
btk bookmark list --format json > bookmarks.json
```

#### `btk bookmark search`

Search bookmarks using full-text search.

**Syntax:**
```bash
btk bookmark search <query> [options]
```

**Arguments:**

- `query` - Search query (required)

**Options:**

- `--tags TEXT` - Filter by tags
- `--starred` - Search only starred bookmarks
- `--in-content` - Search in cached content (not just title/URL)
- `--limit N` - Limit results

**Examples:**

```bash
btk bookmark search "python tutorial"
btk bookmark search "machine learning" --in-content
btk bookmark search "tutorial" --tags python
btk bookmark search "important" --starred
```

#### `btk bookmark get`

Get detailed information about a specific bookmark.

**Syntax:**
```bash
btk bookmark get <id> [options]
```

**Arguments:**

- `id` - Bookmark ID (required)

**Options:**

- `--details` - Show full details including content cache
- `--format FORMAT` - Output format (table, json, yaml)

**Examples:**

```bash
btk bookmark get 123
btk bookmark get 123 --details
btk bookmark get 123 --format json
```

#### `btk bookmark update`

Update bookmark metadata.

**Syntax:**
```bash
btk bookmark update <id> [options]
```

**Arguments:**

- `id` - Bookmark ID (required)

**Options:**

- `--title TEXT` - Update title
- `--description TEXT` - Update description
- `--stars` - Set starred status to true
- `--no-stars` - Set starred status to false
- `--add-tags TEXT` - Add tags (comma-separated)
- `--remove-tags TEXT` - Remove tags (comma-separated)
- `--set-tags TEXT` - Replace all tags

**Examples:**

```bash
btk bookmark update 123 --title "New Title"
btk bookmark update 123 --stars
btk bookmark update 123 --add-tags "important,featured"
btk bookmark update 123 --remove-tags "draft"
btk bookmark update 123 --set-tags "python,tutorial"
```

#### `btk bookmark delete`

Delete bookmarks from the collection.

**Syntax:**
```bash
btk bookmark delete <id> [<id> ...] [options]
```

**Arguments:**

- `id` - One or more bookmark IDs

**Options:**

- `--filter-tags TEXT` - Delete bookmarks with these tags
- `--filter-domain TEXT` - Delete bookmarks from domain
- `--dry-run` - Preview what would be deleted without deleting

**Examples:**

```bash
btk bookmark delete 123
btk bookmark delete 123 456 789
btk bookmark delete --filter-tags "old,deprecated"
btk bookmark delete --filter-domain "old-site.com"
btk bookmark delete --filter-tags "draft" --dry-run
```

#### `btk bookmark query`

Advanced querying using SQL-like syntax.

**Syntax:**
```bash
btk bookmark query <sql-query>
```

**Arguments:**

- `sql-query` - SQL WHERE clause (required)

**Examples:**

```bash
btk bookmark query "stars = true AND visit_count > 10"
btk bookmark query "added > '2024-10-01'"
btk bookmark query "tags LIKE '%python%'"
btk bookmark query "stars = true AND (tags LIKE '%python%' OR tags LIKE '%tutorial%')"
```

---

### `btk tag` - Tag Management

Commands for managing tags and tag hierarchies.

#### `btk tag list`

List all tags.

**Syntax:**
```bash
btk tag list [options]
```

**Options:**

- `--format FORMAT` - Output format (table, json, csv)

**Examples:**

```bash
btk tag list
btk tag list --format json
```

#### `btk tag tree`

Show hierarchical tag tree.

**Syntax:**
```bash
btk tag tree
```

**Examples:**

```bash
btk tag tree
```

#### `btk tag stats`

Show tag usage statistics.

**Syntax:**
```bash
btk tag stats
```

**Examples:**

```bash
btk tag stats
```

#### `btk tag add`

Add tags to bookmarks.

**Syntax:**
```bash
btk tag add <tag> <id> [<id> ...] [options]
```

**Arguments:**

- `tag` - Tag name (required)
- `id` - One or more bookmark IDs

**Options:**

- `--all` - Add tag to all bookmarks
- `--starred` - Add tag to all starred bookmarks
- `--filter-tags TEXT` - Add to bookmarks with these tags

**Examples:**

```bash
btk tag add important 123 456 789
btk tag add reviewed --starred
btk tag add needs-review --filter-tags "draft,wip"
btk tag add programming/python/advanced 123
```

#### `btk tag remove`

Remove tags from bookmarks.

**Syntax:**
```bash
btk tag remove <tag> <id> [<id> ...] [options]
```

**Arguments:**

- `tag` - Tag name (required)
- `id` - One or more bookmark IDs

**Options:**

- `--all` - Remove tag from all bookmarks
- `--filter-tags TEXT` - Remove from bookmarks with these tags

**Examples:**

```bash
btk tag remove draft 123 456
btk tag remove old --all
btk tag remove wip --filter-tags "completed"
```

#### `btk tag rename`

Rename a tag across all bookmarks.

**Syntax:**
```bash
btk tag rename <old-tag> <new-tag>
```

**Arguments:**

- `old-tag` - Current tag name (required)
- `new-tag` - New tag name (required)

**Examples:**

```bash
btk tag rename javascript js
btk tag rename programming/python/web programming/python/web-dev
btk tag rename backend programming/backend
```

#### `btk tag copy`

Copy a tag to additional bookmarks.

**Syntax:**
```bash
btk tag copy <tag> [options]
```

**Arguments:**

- `tag` - Tag name to copy (required)

**Options:**

- `--to-ids ID [ID ...]` - Copy to specific bookmark IDs
- `--starred` - Copy to all starred bookmarks
- `--filter-tags TEXT` - Copy to bookmarks with these tags

**Examples:**

```bash
btk tag copy featured --to-ids 123 456 789
btk tag copy high-priority --starred
btk tag copy reviewed --filter-tags "programming/python"
```

#### `btk tag filter`

Filter bookmarks by tag prefix.

**Syntax:**
```bash
btk tag filter <prefix>
```

**Arguments:**

- `prefix` - Tag prefix (required)

**Examples:**

```bash
btk tag filter programming/python
btk tag filter tutorial
```

---

### `btk content` - Content Operations

Manage cached webpage content.

#### `btk content refresh`

Fetch or refresh cached content for bookmarks.

**Syntax:**
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
btk content refresh --id 123
btk content refresh --all
btk content refresh --all --workers 50
btk content refresh --starred --force
btk content refresh --filter-tags "programming/python"
```

#### `btk content view`

View cached content for a bookmark.

**Syntax:**
```bash
btk content view <id> [options]
```

**Arguments:**

- `id` - Bookmark ID (required)

**Options:**

- `--html` - Open HTML in browser
- `--markdown` - Display markdown in terminal (default)
- `--raw` - Show raw HTML

**Examples:**

```bash
btk content view 123
btk content view 123 --html
btk content view 123 --raw
```

#### `btk content auto-tag`

Generate tags automatically based on cached content.

**Syntax:**
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
btk content auto-tag --id 123
btk content auto-tag --all
btk content auto-tag --id 123 --apply
btk content auto-tag --all --apply --threshold 0.7 --workers 20
```

---

### `btk import` - Import Operations

Import bookmarks from various formats.

#### `btk import html`

Import bookmarks from HTML (Netscape Bookmark Format).

**Syntax:**
```bash
btk import html <file> [options]
```

**Arguments:**

- `file` - HTML file path (required)

**Options:**

- `--add-tags TEXT` - Add tags to all imported bookmarks
- `--skip-duplicates` - Skip bookmarks that already exist

**Examples:**

```bash
btk import html bookmarks.html
btk import html bookmarks.html --add-tags "imported,firefox"
btk import html bookmarks.html --skip-duplicates
```

#### `btk import json`

Import from JSON format.

**Syntax:**
```bash
btk import json <file> [options]
```

**Arguments:**

- `file` - JSON file path (required)

**Options:**

- `--add-tags TEXT` - Add tags to all imported bookmarks
- `--skip-duplicates` - Skip bookmarks that already exist

**Examples:**

```bash
btk import json bookmarks.json
btk import json bookmarks.json --add-tags "imported"
```

#### `btk import csv`

Import from CSV file.

**Syntax:**
```bash
btk import csv <file> [options]
```

**Arguments:**

- `file` - CSV file path (required)

**Options:**

- `--add-tags TEXT` - Add tags to all imported bookmarks
- `--skip-duplicates` - Skip bookmarks that already exist

**CSV Format:**
```csv
url,title,tags,description
https://example.com,Example,"tutorial,web",Description here
```

**Examples:**

```bash
btk import csv bookmarks.csv
btk import csv bookmarks.csv --add-tags "imported,2024"
```

#### `btk import text`

Import plain text file with URLs (one per line).

**Syntax:**
```bash
btk import text <file> [options]
```

**Arguments:**

- `file` - Text file path (required)

**Options:**

- `--add-tags TEXT` - Tags for all imported bookmarks
- `--fetch-titles` / `--no-fetch-titles` - Fetch titles from URLs (default: true)

**Examples:**

```bash
btk import text urls.txt
btk import text urls.txt --no-fetch-titles
btk import text urls.txt --add-tags "reading-list,2024"
```

#### `btk import chrome`

Import directly from Chrome browser.

**Syntax:**
```bash
btk import chrome [options]
```

**Options:**

- `--profile TEXT` - Browser profile name
- `--add-tags TEXT` - Tags for imported bookmarks

**Examples:**

```bash
btk import chrome
btk import chrome --profile "Profile 1"
btk import chrome --add-tags "chrome,browser"
```

#### `btk import firefox`

Import directly from Firefox browser.

**Syntax:**
```bash
btk import firefox [options]
```

**Options:**

- `--profile TEXT` - Browser profile name
- `--add-tags TEXT` - Tags for imported bookmarks

**Examples:**

```bash
btk import firefox
btk import firefox --profile work
btk import firefox --add-tags "firefox,browser"
```

#### `btk import safari`

Import directly from Safari browser.

**Syntax:**
```bash
btk import safari [options]
```

**Options:**

- `--add-tags TEXT` - Tags for imported bookmarks

**Examples:**

```bash
btk import safari
btk import safari --add-tags "safari,browser"
```

---

### `btk export` - Export Operations

Export bookmarks to various formats.

#### `btk export html`

Export to browser-compatible HTML.

**Syntax:**
```bash
btk export html <output-file> [options]
```

**Arguments:**

- `output-file` - Output file path (required)

**Options:**

- `--hierarchical` - Create folder hierarchy from tags
- `--starred` - Export only starred bookmarks
- `--filter-tags TEXT` - Export bookmarks with tags
- `--include-archived` - Include archived bookmarks

**Examples:**

```bash
btk export html bookmarks.html
btk export html bookmarks.html --hierarchical
btk export html starred.html --starred
btk export html python.html --filter-tags "programming/python"
```

#### `btk export json`

Export to JSON format.

**Syntax:**
```bash
btk export json <output-file> [options]
```

**Arguments:**

- `output-file` - Output file path (required)

**Options:**

- `--starred` - Export only starred bookmarks
- `--filter-tags TEXT` - Export bookmarks with tags
- `--include-archived` - Include archived bookmarks

**Examples:**

```bash
btk export json bookmarks.json
btk export json starred.json --starred
btk export json python.json --filter-tags "python"
```

#### `btk export csv`

Export to CSV format.

**Syntax:**
```bash
btk export csv <output-file> [options]
```

**Arguments:**

- `output-file` - Output file path (required)

**Options:**

- `--starred` - Export only starred bookmarks
- `--filter-tags TEXT` - Export bookmarks with tags
- `--include-archived` - Include archived bookmarks

**Examples:**

```bash
btk export csv bookmarks.csv
btk export csv python.csv --filter-tags "python"
```

#### `btk export markdown`

Export to Markdown format.

**Syntax:**
```bash
btk export markdown <output-file> [options]
```

**Arguments:**

- `output-file` - Output file path (required)

**Options:**

- `--starred` - Export only starred bookmarks
- `--filter-tags TEXT` - Export bookmarks with tags
- `--include-archived` - Include archived bookmarks

**Examples:**

```bash
btk export markdown bookmarks.md
btk export markdown starred.md --starred
```

---

### `btk db` - Database Management

Database maintenance and information commands.

#### `btk db info`

Show database statistics and information.

**Syntax:**
```bash
btk db info
```

**Examples:**

```bash
btk db info
```

#### `btk db schema`

Display database schema.

**Syntax:**
```bash
btk db schema
```

**Examples:**

```bash
btk db schema
```

#### `btk db stats`

Show detailed database statistics.

**Syntax:**
```bash
btk db stats [options]
```

**Options:**

- `--tags` - Tag statistics
- `--domains` - Domain statistics
- `--activity` - Activity statistics

**Examples:**

```bash
btk db stats
btk db stats --tags
btk db stats --domains
btk db stats --activity
```

#### `btk db vacuum`

Optimize database file.

**Syntax:**
```bash
btk db vacuum
```

**Examples:**

```bash
btk db vacuum
```

#### `btk db dedupe`

Find and handle duplicate bookmarks.

**Syntax:**
```bash
btk db dedupe [options]
```

**Options:**

- `--strategy TEXT` - Deduplication strategy:
  - `merge` - Merge duplicate metadata
  - `keep_first` - Keep oldest bookmark
  - `keep_last` - Keep newest bookmark
  - `keep_most_visited` - Keep most visited bookmark
- `--preview` - Preview changes without applying
- `--stats` - Show duplicate statistics only

**Examples:**

```bash
btk db dedupe --preview
btk db dedupe --stats
btk db dedupe --strategy merge
btk db dedupe --strategy keep_first
```

---

### `btk graph` - Graph Analysis

Build and analyze bookmark relationship graphs.

#### `btk graph build`

Build bookmark similarity graph.

**Syntax:**
```bash
btk graph build [options]
```

**Options:**

- `--tag-weight FLOAT` - Weight for tag similarity (default: 1.0)
- `--domain-weight FLOAT` - Weight for domain similarity (default: 1.0)
- `--link-weight FLOAT` - Weight for direct links (default: 2.0)
- `--min-edge-weight FLOAT` - Minimum edge weight to include

**Examples:**

```bash
btk graph build
btk graph build --tag-weight 2.0 --domain-weight 1.0
btk graph build --min-edge-weight 4.0
```

#### `btk graph neighbors`

Find similar bookmarks (neighbors in graph).

**Syntax:**
```bash
btk graph neighbors <id> [options]
```

**Arguments:**

- `id` - Bookmark ID (required)

**Options:**

- `--limit N` - Limit number of results (default: 10)
- `--min-weight FLOAT` - Minimum edge weight

**Examples:**

```bash
btk graph neighbors 123
btk graph neighbors 123 --limit 20
btk graph neighbors 123 --min-weight 3.0
```

#### `btk graph export`

Export graph data for visualization.

**Syntax:**
```bash
btk graph export <output-file> [options]
```

**Arguments:**

- `output-file` - Output file path (required)

**Options:**

- `--format FORMAT` - Export format:
  - `gexf` - GEXF format (Gephi)
  - `graphml` - GraphML format (yEd)
  - `json` - JSON format (Cytoscape)
  - `d3` - D3.js HTML visualization
- `--min-weight FLOAT` - Minimum edge weight to include

**Examples:**

```bash
btk graph export graph.gexf --format gexf
btk graph export graph.graphml --format graphml
btk graph export graph.json --format json
btk graph export viz.html --format d3
btk graph export graph.gexf --min-weight 4.0
```

#### `btk graph stats`

Show graph statistics.

**Syntax:**
```bash
btk graph stats
```

**Examples:**

```bash
btk graph stats
```

---

### `btk config` - Configuration

Manage BTK configuration.

#### `btk config show`

Display current configuration.

**Syntax:**
```bash
btk config show
```

**Examples:**

```bash
btk config show
```

#### `btk config set`

Set configuration value.

**Syntax:**
```bash
btk config set <key> <value>
```

**Arguments:**

- `key` - Configuration key (required)
- `value` - Configuration value (required)

**Configuration Keys:**

- `database.path` - Default database path
- `output.format` - Default output format (table, json, csv)
- `output.colors` - Enable colors (true, false)
- `import.fetch_titles` - Fetch titles when importing (true, false)
- `import.skip_duplicates` - Skip duplicates when importing (true, false)
- `content.workers` - Number of parallel workers for content operations
- `content.cache_expiry_days` - Days before content cache expires

**Examples:**

```bash
btk config set database.path ~/bookmarks.db
btk config set output.format json
btk config set output.colors true
btk config set content.workers 50
```

#### `btk config init`

Initialize default configuration file.

**Syntax:**
```bash
btk config init
```

**Examples:**

```bash
btk config init
```

**Configuration File Location:**

- Linux/macOS: `~/.config/btk/config.toml`
- Windows: `%APPDATA%\btk\config.toml`

---

### `btk shell` - Interactive Shell

Launch the interactive shell.

**Syntax:**
```bash
btk shell [options]
```

**Options:**

- `--db PATH` - Database path

**Examples:**

```bash
btk shell
btk shell --db ~/bookmarks.db
```

See the [Shell Guide](../guide/shell.md) for complete shell documentation.

---

## Exit Codes

BTK returns standard exit codes:

- `0` - Success
- `1` - General error
- `2` - Invalid arguments
- `3` - Database error
- `4` - Network error
- `5` - File I/O error

---

## Environment Variables

BTK respects the following environment variables:

- `BTK_DB` - Default database path (overridden by `--db` flag)
- `BTK_CONFIG` - Configuration file path
- `NO_COLOR` - Disable colored output if set

**Examples:**

```bash
# Set default database
export BTK_DB=~/bookmarks.db
btk bookmark list

# Disable colors
NO_COLOR=1 btk bookmark list
```

---

## Configuration File

BTK uses TOML format for configuration:

```toml
[database]
path = "/home/user/bookmarks.db"

[output]
format = "table"
colors = true

[import]
fetch_titles = true
skip_duplicates = false

[content]
workers = 10
cache_expiry_days = 30

[graph]
tag_weight = 1.0
domain_weight = 1.0
link_weight = 2.0
```

---

## See Also

- [Shell Guide](../guide/shell.md) - Interactive shell reference
- [Commands Guide](../guide/commands.md) - Command examples and workflows
- [Tags Guide](../guide/tags.md) - Tag management strategies
- [Quick Start](../getting-started/quickstart.md) - Getting started guide
