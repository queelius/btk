# Quick Start

## Initialize Database

```bash
# Create default database in current directory
btk init

# Or specify a custom location
btk --db ~/my-bookmarks.db init
```

## Import Bookmarks

```bash
# From browser HTML export
btk import bookmarks.html

# From JSON
btk import bookmarks.json

# From URLs in text file
btk import urls.txt
```

## Basic Operations

### Add a Bookmark

```bash
btk add https://example.com --title "Example Site" --tags tutorial,web
```

### Search Bookmarks

```bash
# Search titles and URLs
btk search "python"

# Search in cached content
btk search "machine learning" --in-content
```

### List Bookmarks

```bash
# List all
btk list

# Filter by tags
btk list --tags python

# Show starred only
btk list --starred
```

### Export Bookmarks

```bash
# Export to HTML
btk export output.html html

# Export with folder hierarchy
btk export output.html html --hierarchical

# Export to JSON
btk export output.json json
```

## Next Steps

- [Core Commands](../guide/commands.md) - Complete command reference
- [Tags & Organization](../guide/tags.md) - Learn about hierarchical tags
- [Graph Analysis](../guide/graph.md) - Visualize relationships
