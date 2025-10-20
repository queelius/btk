# BTK Shell & CLI Refactoring Summary

## Completed: October 19, 2025

## Overview
Major refactoring of both the BTK interactive shell and CLI to provide a clean, organized, and powerful bookmark management experience.

---

## Shell Refactoring ✅

### Virtual Filesystem Structure
Implemented a complete virtual filesystem for navigating bookmarks:

```
btk:/
├── bookmarks/          # All bookmarks by ID
│   └── <id>/          # Individual bookmark (can view fields)
├── tags/              # Hierarchical tag browsing
│   ├── <tag>/         # Tag directory
│   └── <tag>/<id>/    # Bookmark within tag context
├── starred/           # Starred bookmarks
│   └── <id>/          # Starred bookmark
├── archived/          # Archived bookmarks
│   └── <id>/          # Archived bookmark
├── recent/            # Recently added bookmarks
│   └── <id>/          # Recent bookmark
└── domains/           # Browse by domain
    ├── <domain>/      # Domain directory
    └── <domain>/<id>/ # Bookmark from domain
```

### Hierarchical Tags
Tags now support `/` separator for hierarchy:
- `programming/python/data-science`
- `video/tutorial/beginner`
- `work/projects/active`

Navigate like directories:
```bash
btk:/$ cd tags/programming/python
btk:/tags/programming/python$ ls
# Shows subtags and bookmarks
```

### Enhanced Navigation Commands

#### Core Navigation
- `ls` - Context-aware listing (shows different content based on location)
- `cd <path>` - Full Unix-like path navigation with `.` and `..`
- `pwd` - Shows current path

#### New Commands
- **`recent`** - Context-aware activity viewer
  - `recent` - Recently visited bookmarks (default)
  - `recent added` - Recently added
  - `recent starred` - Recently starred
  - Works in context: when in `/tags/programming`, shows only programming bookmarks

- **`mv`** - Rename/reorganize tags
  - `mv old_tag new_tag` - Rename tag across all bookmarks
  - Automatic cleanup of orphaned tags
  - Confirmation prompt for safety

- **`cp`** - Copy tags to bookmarks
  - `cp <tag> .` - Add tag to current bookmark
  - `cp <tag> <id>` - Add tag to specific bookmark
  - `cp <tag> *` - Add tag to all bookmarks in current context

### Updated Existing Commands
All commands now work with the new context system:
- `cat` - Display bookmark fields (with path syntax: `cat 123/url`)
- `file` - Show bookmark metadata
- `stat` - Show statistics (context-aware)
- `star` - Toggle star (works from any bookmark context)
- `tag` - Add tags (supports direct ID access)

### Path-Based Features
- Absolute paths: `/bookmarks/123`, `/tags/programming`
- Relative paths: `../..`, `bookmarks/123`
- Special paths: `.` (current), `..` (parent)
- Bookmark ID detection in virtual directories: `/tags/video/3298` correctly identifies as bookmark 3298

---

## CLI Refactoring ✅

### New Grouped Structure

Reorganized from flat command list to logical groups:

```bash
btk <group> <command> [options]
```

#### Command Groups

**1. `btk bookmark`** - Core CRUD operations
```bash
btk bookmark add <url> --title "Title" --tags "tag1,tag2"
btk bookmark list --limit 10 --starred
btk bookmark search "query" --tags "python"
btk bookmark get 123 --details
btk bookmark update 123 --add-tags "important"
btk bookmark delete 1 2 3
btk bookmark query "stars = true AND visit_count > 10"
```

**2. `btk tag`** - Tag management
```bash
btk tag list
btk tag add python 123 456
btk tag remove deprecated 789
btk tag rename "old-name" "new-name"
btk tag copy important --starred
btk tag stats
```

**3. `btk content`** - Content operations
```bash
btk content refresh --id 123
btk content refresh --all --force
btk content view 123 --html
btk content auto-tag --id 123 --apply
```

**4. `btk import`** - Import bookmarks
```bash
btk import html bookmarks.html
btk import json data.json
btk import csv export.csv
```

**5. `btk export`** - Export bookmarks
```bash
btk export html bookmarks.html
btk export json data.json --starred
btk export markdown README.md --tags "important"
btk export csv export.csv --include-archived
```

**6. `btk db`** - Database management
```bash
btk db info
btk db schema
btk db stats
```

**7. `btk graph`** - Graph analysis
```bash
btk graph build --tag-weight 2.0
btk graph neighbors 123 --limit 10
btk graph export viz.html --format d3
btk graph stats
```

**8. `btk config`** - Configuration
```bash
btk config show
btk config set key value
btk config init
```

**9. `btk shell`** - Interactive shell
```bash
btk shell  # Launch interactive shell
```

### CLI-Shell Parity

| Operation | CLI | Shell |
|-----------|-----|-------|
| List bookmarks | `btk bookmark list` | `ls` (in /bookmarks) |
| Search | `btk bookmark search "term"` | `find "term"` |
| Get bookmark | `btk bookmark get 123` | `cd bookmarks/123; ls` |
| Add tag | `btk tag add python 123` | `tag 123 python` or `cp python 123` |
| Rename tag | `btk tag rename old new` | `mv old new` |
| Copy tag | `btk tag copy tag 123` | `cp tag 123` |
| Star bookmark | `btk bookmark update 123 --star` | `star 123` or `star` (in context) |
| Recent activity | `btk bookmark list --sort visited` | `recent` |

---

## Implementation Details

### Files Modified
- `/home/spinoza/github/beta/btk/btk/shell.py` - Complete refactoring (~300+ lines changed)
- `/home/spinoza/github/beta/btk/btk/cli.py` - Complete parser restructuring (~200 lines changed)

### Key Technical Changes

#### Shell (`shell.py`)
1. Removed `current_bookmark` state tracking
2. Added path-based `cwd` (current working directory)
3. Implemented `_parse_path()` for path normalization
4. Implemented `_get_context()` and `_get_context_for_path()` for context detection
5. Added helper methods for filtering:
   - `_get_bookmarks_by_tag_prefix()` - Hierarchical tag support
   - `_get_bookmarks_by_domain()` - Domain filtering
   - `_get_all_tags()` and `_get_all_domains()` - Enumeration
6. Completely rewrote navigation commands: `do_ls()`, `do_cd()`, `do_pwd()`
7. Added new commands: `do_recent()`, `do_mv()`, `do_cp()`
8. Updated all existing commands to use context system

#### CLI (`cli.py`)
1. Created grouped subparser structure
2. Added tag management functions:
   - `cmd_tag_add()` - Add tags to bookmarks
   - `cmd_tag_remove()` - Remove tags from bookmarks
   - `cmd_tag_rename()` - Rename tags globally
3. Reorganized all existing commands into logical groups
4. Updated help text and examples

### Testing Results
All features tested and working:
- ✅ Virtual directory navigation
- ✅ Hierarchical tag browsing (e.g., `/tags/programming/python/data-science`)
- ✅ Bookmark context detection in tag paths (e.g., `/tags/video/3298`)
- ✅ Context-aware `recent` command
- ✅ Tag renaming with `mv`
- ✅ Tag copying with `cp`
- ✅ Grouped CLI structure (`btk bookmark`, `btk tag`, etc.)
- ✅ CLI tag management commands
- ✅ Backward navigation with `..`
- ✅ Path-like `cat` syntax (`cat 123/url`)

---

## Benefits

### For Users

**Shell:**
1. **Intuitive Navigation** - Browse bookmarks like files in a filesystem
2. **Powerful Filtering** - Navigate by tags, domains, starred status, etc.
3. **Context-Aware Commands** - Commands adapt based on location
4. **Hierarchical Tags** - Organize tags in meaningful hierarchies
5. **Familiar Interface** - Unix-like commands (ls, cd, pwd, mv, cp)

**CLI:**
1. **Logical Grouping** - Related commands together (all tag operations under `btk tag`)
2. **Discoverability** - `btk tag --help` shows all tag operations
3. **Consistency** - Similar syntax across command groups
4. **Composability** - Works well in Unix pipelines
5. **Clear Separation** - Stateful (shell) vs stateless (CLI) commands

### For Development

1. **Scalability** - Easy to add new commands to appropriate groups
2. **Maintainability** - Clear organization of code
3. **CLI-Shell Parity** - Easy to map stateless operations between interfaces
4. **Testability** - Well-defined command boundaries
5. **Extensibility** - Plugin-like structure for new command groups

---

## Examples

### Shell Navigation Examples
```bash
btk:/$ ls
# Shows virtual directories

btk:/$ cd tags/programming
btk:/tags/programming$ ls
# Shows programming bookmarks and subtags

btk:/tags/programming$ cd python/data-science
btk:/tags/programming/python/data-science$ ls
# Shows data science bookmarks

btk:/tags/programming/python/data-science$ recent
# Shows recently visited data science bookmarks

btk:/tags/programming/python/data-science$ cd 5
btk:/tags/programming/python/data-science/5$ star
# Stars NumPy bookmark

btk:/tags/programming/python/data-science/5$ cp important .
# Adds 'important' tag to current bookmark
```

### CLI Usage Examples
```bash
# Add bookmark with tags
btk bookmark add https://example.com --title "Example" --tags "web,demo"

# List starred programming bookmarks
btk bookmark list --starred --tags "programming" --limit 20

# Rename a tag across all bookmarks
btk tag rename "javascript" "js"

# Copy tag to all starred bookmarks
btk tag add featured $(btk bookmark list --starred --output json | jq -r '.[].id')

# Export starred bookmarks as markdown
btk export markdown important.md --starred

# Build and analyze bookmark graph
btk graph build --tag-weight 3.0
btk graph neighbors 123 --limit 5
```

---

## Migration Guide

### Shell Users
The shell now starts at `/` (root) instead of directly in bookmarks.

**Old workflow:**
```bash
btk:/$ ls      # Listed all bookmarks
btk:/$ cd 123  # Entered bookmark 123
```

**New workflow:**
```bash
btk:/$ ls            # Shows virtual directories
btk:/$ cd bookmarks
btk:/bookmarks$ ls   # Lists all bookmarks
btk:/bookmarks$ cd 123
btk:/bookmarks/123$ ls  # Shows bookmark fields
```

**Or use absolute paths:**
```bash
btk:/$ cd bookmarks/123
btk:/bookmarks/123$ ls
```

### CLI Users
Commands are now grouped.

**Old:**
```bash
btk add https://example.com
btk list
btk search "python"
btk tags
```

**New:**
```bash
btk bookmark add https://example.com
btk bookmark list
btk bookmark search "python"
btk tag list
```

---

## Future Enhancements

Potential additions based on this foundation:

1. **Shell:**
   - `rm` command for removing bookmarks
   - `find` command improvements with regex support
   - `grep` for searching within bookmark content
   - Tab completion for paths and commands
   - Bookmark aliases (symlinks in filesystem metaphor)

2. **CLI:**
   - Bulk operations with filters
   - Batch import/export operations
   - Advanced query language
   - Webhook/API integration commands

3. **Both:**
   - Plugin system for custom commands
   - Bookmark collections/workspaces
   - Sharing and collaboration features
   - Integration with external services

---

## Documentation Files

- `CLI_REFACTOR_PLAN.md` - Detailed refactoring plan with command mapping
- `REFACTOR_SUMMARY.md` - This document
- `shell_refactor_snippet.py` - Reference implementation of navigation methods

---

## Conclusion

This refactoring represents a significant improvement to BTK's usability and organization:

- **Shell**: Now provides a powerful, intuitive, filesystem-like interface for browsing bookmarks
- **CLI**: Organized into logical groups with clear CLI-shell parity for stateless operations
- **Both**: Follow Unix philosophy and compose well with other tools

The foundation is now in place for future enhancements while maintaining backward compatibility where possible and providing clear migration paths where not.
