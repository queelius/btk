# BTK CLI Refactoring Plan

## Goal
Reorganize CLI into logical command groups with clean separation and CLI-shell parity for stateless commands.

## New Command Structure

```
btk bookmark <command>  # Core CRUD operations
btk tag <command>       # Tag management
btk content <command>   # Content operations
btk import <source>     # Import from sources
btk export <format>     # Export to formats
btk db <command>        # Database management
btk graph <command>     # Graph analysis
btk config <command>    # Configuration
btk shell               # Interactive shell
```

## Command Groups Detail

### 1. `btk bookmark` - Core bookmark CRUD
**Stateless, has CLI-shell parity**

| Command | Description | Shell Equivalent |
|---------|-------------|------------------|
| `add <url>` | Add bookmark | N/A (shell is for browsing) |
| `get <id>` | Get bookmark by ID | `cat all` (when cd'd to bookmark) |
| `list` | List all bookmarks | `ls` (in /bookmarks) |
| `search <query>` | Search bookmarks | `find` |
| `update <id>` | Update bookmark | `tag`, `star`, etc. |
| `delete <id>...` | Delete bookmarks | N/A |
| `query <sql>` | Advanced SQL query | N/A |

**Options:**
```bash
btk bookmark add https://example.com --title "Example" --tags "web,demo" --star
btk bookmark list --limit 10 --sort visit_count --starred
btk bookmark search "python" --tags "programming" --limit 20
btk bookmark get 123 --details
btk bookmark update 123 --title "New" --add-tags "important"
btk bookmark delete 1 2 3
btk bookmark query "stars = true AND visit_count > 10"
```

### 2. `btk tag` - Tag management
**Stateless, has CLI-shell parity**

| Command | Description | Shell Equivalent |
|---------|-------------|------------------|
| `list` | List all tags | `ls` (in /tags) |
| `add <tag> <id>` | Add tag to bookmark(s) | `tag <id> <tags>` or `cp <tag> <id>` |
| `remove <tag> <id>` | Remove tag from bookmark(s) | N/A |
| `rename <old> <new>` | Rename tag globally | `mv <old> <new>` |
| `copy <tag> <target>` | Copy tag to bookmark(s) | `cp <tag> <target>` |
| `stats` | Tag statistics | `stat` (in /tags) |

**Options:**
```bash
btk tag list
btk tag add python 123
btk tag add featured --all  # Add to all bookmarks
btk tag remove deprecated 456
btk tag rename "old-name" "new-name"
btk tag copy important --starred  # Copy to all starred
btk tag stats
```

### 3. `btk content` - Content operations
**Stateless, some shell parity**

| Command | Description | Shell Equivalent |
|---------|-------------|------------------|
| `refresh` | Refresh cached content | N/A |
| `view <id>` | View cached content | `cat` (sort of) |
| `auto-tag` | Auto-generate tags | N/A |

**Options:**
```bash
btk content refresh --id 123
btk content refresh --all
btk content view 123 --html
btk content auto-tag --id 123 --apply
```

### 4. `btk import` - Import bookmarks
**Stateless, no shell equivalent**

| Command | Description |
|---------|-------------|
| `html <file>` | Import from HTML |
| `json <file>` | Import from JSON |
| `csv <file>` | Import from CSV |

**Options:**
```bash
btk import html bookmarks.html
btk import json data.json
btk import csv export.csv
```

### 5. `btk export` - Export bookmarks
**Stateless, no shell equivalent**

| Command | Description |
|---------|-------------|
| `html <file>` | Export to HTML |
| `json <file>` | Export to JSON |
| `csv <file>` | Export to CSV |
| `markdown <file>` | Export to Markdown |

**Options:**
```bash
btk export html bookmarks.html
btk export json data.json --starred
btk export markdown README.md --tags "important"
```

### 6. `btk db` - Database management
**Stateless, no shell equivalent**

| Command | Description |
|---------|-------------|
| `info` | Database information |
| `schema` | Show schema |
| `stats` | Statistics |
| `vacuum` | Optimize database |

**Options:**
```bash
btk db info
btk db schema
btk db stats
btk db vacuum
```

### 7. `btk graph` - Graph analysis
**Stateless, no shell equivalent**

| Command | Description |
|---------|-------------|
| `build` | Build similarity graph |
| `analyze` | Analyze relationships |
| `communities` | Detect communities |

### 8. `btk config` - Configuration
**Stateless, no shell equivalent**

| Command | Description |
|---------|-------------|
| `get <key>` | Get config value |
| `set <key> <value>` | Set config value |
| `list` | List all config |

### 9. `btk shell` - Interactive shell
**Stateful, shell-only**

```bash
btk shell  # Launch interactive shell
```

## Implementation Strategy

### Phase 1: Create new grouped parsers
1. Keep existing commands working
2. Add new grouped commands alongside
3. Test both work in parallel

### Phase 2: Migrate functionality
1. Update command functions to work with both old and new parsers
2. Add deprecation warnings to old commands
3. Update documentation to show new commands

### Phase 3: Remove old structure (optional)
1. Remove old flat commands
2. Clean up code
3. Update all examples

## CLI-Shell Parity Matrix

| Operation | CLI | Shell |
|-----------|-----|-------|
| List bookmarks | `btk bookmark list` | `ls` (in /bookmarks) |
| Search | `btk bookmark search "term"` | `find "term"` |
| Get bookmark | `btk bookmark get 123` | `cd bookmarks/123; ls` |
| Add tag | `btk tag add python 123` | `tag 123 python` or `cp python 123` |
| Rename tag | `btk tag rename old new` | `mv old new` |
| Copy tag | `btk tag copy tag 123` | `cp tag 123` |
| Star bookmark | `btk bookmark update 123 --star` | `star 123` or `star` (in context) |
| Recent activity | `btk bookmark list --sort visited --limit 10` | `recent` |

## Migration Examples

### Old → New

```bash
# Old
btk add https://example.com --tags "web"
btk list --limit 10
btk search "python"
btk update 123 --tags "python,web"
btk tags

# New
btk bookmark add https://example.com --tags "web"
btk bookmark list --limit 10
btk bookmark search "python"
btk bookmark update 123 --tags "python,web"
btk tag list
```

## Benefits

1. **Logical Grouping** - Related commands together
2. **Discoverability** - `btk tag --help` shows all tag operations
3. **Scalability** - Easy to add new commands
4. **CLI-Shell Parity** - Clear mapping for stateless operations
5. **Clean Separation** - Stateful (shell) vs stateless (CLI) commands
6. **Consistency** - Similar operations have similar syntax across groups
