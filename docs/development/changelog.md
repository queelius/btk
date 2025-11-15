# Changelog

All notable changes to BTK (Bookmark Toolkit) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.2] - 2025-11-15

### Added - Test Coverage

**Comprehensive Test Suite for v0.7.1 Features**

This release significantly improves test coverage for the smart collections and time-based recent navigation features introduced in v0.7.1.

#### Test Suite Improvements

- **82 new tests** added for v0.7.1 features (26 smart collections + 56 time-based navigation)
- **597 total tests** now passing (up from 515)
- **Overall coverage increased to 63.43%** (up from 60.87%)
- **Shell module coverage increased to 61.44%** (up from 50%)

#### Smart Collections Tests (`test_shell_smart_collections.py`)

- 26 comprehensive tests covering all 5 smart collections
- Test coverage for: `/unread`, `/popular`, `/broken`, `/untagged`, `/pdfs`
- Validates filter functions, context detection, navigation, and dynamic updates
- Tests edge cases: empty collections, full collections, collection updates

#### Time-Based Recent Navigation Tests (`test_shell_time_based_recent.py`)

- 56 comprehensive tests covering hierarchical time-based navigation
- Tests all 6 time periods: today, yesterday, this-week, last-week, this-month, last-month
- Tests all 3 activity types: visited, added, starred
- Tests all 18 subdirectory combinations (6 periods × 3 activities)
- Validates time range calculations and timezone handling
- Tests backward compatibility with `/recent/{id}` pattern

#### Test Quality

Following TDD best practices:
- Behavior-focused tests (test what, not how)
- Clear Given-When-Then structure
- Descriptive test names
- Proper test isolation and independence
- Comprehensive edge case coverage
- Fast execution (~30 seconds for full suite)

### Fixed

- Timezone handling in time-based navigation tests
- Context detection test patterns to match shell implementation
- Test data setup for activity filtering tests

### Documentation

- Created `TEST_SUITE_SUCCESS.md` documenting test suite status and quality metrics
- Updated test coverage reports and recommendations

## [0.7.1] - 2025-10-20

### Added - Smart Collections

**Major Feature: Auto-Updating Virtual Directories**

Smart collections provide dynamic, auto-updating virtual directories in the shell that filter bookmarks based on specific criteria. All collections update automatically as bookmarks change, providing instant access to useful subsets without manual organization.

#### Five Built-in Collections

1. **`/unread` - Never Visited Bookmarks**
   - Filter: `visit_count == 0`
   - Shows bookmarks that have never been opened
   - Automatically updates when bookmarks are visited
   - Use cases: Reading backlog, forgotten resources, articles to review
   - Example: `btk:/$ cd unread && ls`

2. **`/popular` - Most Visited Bookmarks**
   - Filter: Top 100 by `visit_count` (sorted descending)
   - Shows your most frequently accessed references
   - Automatically updates based on visit patterns
   - Use cases: Quick access to go-to resources, identify important bookmarks
   - Example: `btk:/$ cd popular && recent visited`

3. **`/broken` - Unreachable Bookmarks**
   - Filter: `reachable == false`
   - Shows bookmarks where URL returns error or timeout
   - Helps maintain collection health
   - Use cases: Find dead links, update URLs, archive old content
   - Example: `btk:/$ cd broken && cat 2345/url`

4. **`/untagged` - Bookmarks Without Tags**
   - Filter: `len(tags) == 0`
   - Shows bookmarks missing tags
   - Helps maintain consistent organization
   - Use cases: Organize imports, systematic tagging, quality control
   - Example: `btk:/$ cd untagged && tag 5001 appropriate-tags`

5. **`/pdfs` - PDF Documents**
   - Filter: `url.endswith('.pdf')`
   - Shows bookmarks pointing to PDF files
   - Quick access to papers, books, documentation
   - Use cases: Research papers, technical docs, academic resources
   - Example: `btk:/$ cd pdfs && find "machine learning"`

#### Collection Features

- **Auto-updating** - Collections recompute on access, always showing current state
- **Collection counts** - `ls` displays bookmark counts: `unread/ (42) Bookmarks never visited`
- **Context-aware** - All shell commands work within collections (recent, stat, find, etc.)
- **Nested navigation** - Navigate from collections to bookmarks and back
- **Combining features** - Collections work seamlessly with tags, search, and other features

#### Technical Implementation

- **SmartCollection class** - Defines collection name, filter function, and description
- **SMART_COLLECTIONS registry** - Easily extensible for future collections
- **Lazy evaluation** - Collections computed on access, not cached
- **Performance** - Suitable for databases up to 10k bookmarks without noticeable delay

### Added - Time-Based Recent Navigation

**Major Feature: Hierarchical Time-Based Directory Structure**

Enhanced the `/recent` directory with hierarchical organization by time periods and activity types. Instead of a flat list, bookmarks are now organized into browsable time-based subdirectories.

#### Structure

```
/recent/
├── today/          # 00:00 today to now
│   ├── visited/    # Bookmarks visited today
│   ├── added/      # Bookmarks added today
│   └── starred/    # Bookmarks starred today
├── yesterday/      # 00:00 yesterday to 00:00 today
├── this-week/      # Start of week (Monday) to now
├── last-week/      # Previous Monday to this Monday
├── this-month/     # 1st of month to now
└── last-month/     # 1st of previous month to 1st of this month
```

#### Time Periods (6 total)

1. **`today`** - Activity from 00:00 today to now
2. **`yesterday`** - Activity from 00:00 yesterday to 00:00 today
3. **`this-week`** - Activity from start of week (Monday) to now
4. **`last-week`** - Activity from previous Monday to start of this week
5. **`this-month`** - Activity from 1st of month to now
6. **`last-month`** - Activity from 1st of previous month to 1st of this month

!!! note "Week Definition"
    Weeks start on Monday for consistent reporting.

#### Activity Types (3 per period)

1. **`visited`** - Bookmarks visited during period (by `last_visited`)
2. **`added`** - Bookmarks added during period (by `added`)
3. **`starred`** - Bookmarks starred during period (approximated by `added`)

!!! warning "Starred Approximation"
    Currently uses `added` timestamp as proxy for when bookmarks were starred. A future update may add dedicated `starred_at` field.

#### Navigation Examples

```bash
# Today's visited bookmarks
btk:/$ cd recent/today/visited
btk:/recent/today/visited$ ls
4892  4765  4501  4305  4201

# This week's additions
btk:/$ cd recent/this-week/added
btk:/recent/this-week/added$ stat

# Yesterday's reading list
btk:/$ cd recent/yesterday/visited
btk:/recent/yesterday/visited$ visit 4876

# Monthly comparison
btk:/$ cd recent/this-month/added
btk:/recent/this-month/added$ ls | wc -l
45 bookmarks

btk:/$ cd ../../../last-month/added
btk:/recent/last-month/added$ ls | wc -l
32 bookmarks
```

#### Use Cases

- **Daily triage** - Review bookmarks added today, tag and organize
- **Weekly review** - See what you read vs. what you added this week
- **Monthly metrics** - Track bookmark additions and reading patterns
- **Time-based cleanup** - Find old unread bookmarks, review past activity
- **Productivity tracking** - Compare activity across time periods

#### Technical Implementation

- **get_time_ranges()** - Calculates datetime ranges for each period
- **filter_by_activity()** - Filters bookmarks by activity type and time range
- **Timezone-aware** - All timestamps use UTC with timezone awareness
- **Enhanced context detection** - `_get_context()` handles time-based paths
- **Display helpers** - `_ls_recent_root()` and `_ls_recent_period()` for formatted output

### Improved

- **Enhanced `ls` output** - Shows counts for all directories at root level
  ```
  btk:/$ ls
  bookmarks/    (100)   All bookmarks
  unread/       (42)    Bookmarks never visited
  popular/      (100)   100 most visited bookmarks
  broken/       (3)     Unreachable bookmarks
  ```

- **Better organization** - Smart collections provide instant access to useful bookmark subsets
- **Improved discoverability** - Time-based navigation makes activity tracking intuitive
- **Context-aware stat** - Statistics commands work in all collection contexts

### Changed

- **Default /recent behavior** - Now shows recently **visited** instead of recently **added**
  - More intuitive for most use cases
  - Previously: sorted by `added` timestamp
  - Now: sorted by `last_visited` timestamp
  - Backward compatible: subdirectories provide both views

- **Virtual filesystem expanded** - Five new top-level directories
  - Old: 6 directories (bookmarks, tags, starred, archived, recent, domains)
  - New: 11 directories (added 5 smart collections)

### Backward Compatibility

- **Full backward compatibility** maintained
  - `/recent/<id>` still works for direct bookmark access
  - All existing shell commands unchanged
  - All 515 existing tests pass
  - No breaking changes to API or CLI

- **Enhanced features** - New functionality added without removing old behavior
  - `/recent` can still show bookmarks at root level (recently visited)
  - Time-based subdirectories are additive, not replacement

### Performance

- **Lazy evaluation** - Collections computed on access
  - No caching overhead
  - Always up-to-date
  - Suitable for <10k bookmarks

- **Optimization opportunities** - For large collections (>100k bookmarks)
  - Could add result caching with TTL
  - Could push filtering to SQL queries
  - Could add database indices for time-based queries

### Documentation

- **Updated shell guide** - Comprehensive documentation of:
  - Smart Collections section with all 5 collections
  - Time-Based Recent Navigation section with examples
  - Practical workflows and use cases
  - Performance notes and tips

- **Updated quickstart** - Added sections:
  - Using Smart Collections workflow
  - Time-Based Activity Review workflow
  - Updated shell examples with new directories

- **Updated homepage** - Highlights v0.7.1 features
  - Smart collections listed in Recent Updates
  - Updated shell example to show new directories

- **Updated commands guide** - Info box about smart collections in shell

### Testing

- **All existing tests pass** - No regressions
  - 515 tests passing
  - ~12 second execution time
  - Shell tests cover new features

- **Integration testing** - Manual verification of:
  - Smart collection navigation
  - Time-based directory browsing
  - Collection count display
  - Context-aware commands in collections

### Design Decisions

1. **No `starred_at` field** - Using `added` as proxy
   - Avoids schema migration complexity
   - Can enhance later if user feedback warrants it
   - Approximation is "good enough" for most use cases

2. **5 core collections** - Focused, high-value set
   - Based on common bookmark management needs
   - Room for expansion based on user feedback
   - Keeps interface uncluttered

3. **Top 100 for popular** - Limited scope prevents overwhelming display
   - Configurable in future if needed
   - Most users care about top items

4. **Show counts in ls** - Better UX, minimal performance impact
   - Helps users understand collection sizes at a glance
   - Computes count during collection filtering (already happening)

5. **6 time periods** - Covers most common use cases
   - Daily: today, yesterday
   - Weekly: this-week, last-week
   - Monthly: this-month, last-month
   - Can expand if needed (last-7-days, last-30-days, etc.)

### Future Enhancements

#### Short Term
- Unit tests specifically for smart collections and time-based navigation
- Performance benchmarking with large datasets (10k, 100k bookmarks)

#### Medium Term
- **User-defined collections** via config file
  ```toml
  [collections.reading-list]
  filter = "unread AND (tag:books OR tag:articles)"
  sort = "added DESC"
  ```

- **More time periods** - last-7-days, last-30-days, all-time
- **Collection parameters** - `popular/50` for top 50 instead of 100
- **Caching** for large databases

#### Long Term
- **Collection operators** - Intersection, union, difference
  ```bash
  btk:/$ cd starred+unread  # Starred AND unread
  btk:/$ cd python-archived  # Python but NOT archived
  ```

- **starred_at timestamp** - Dedicated field for accurate starred tracking
- **SQL-based filtering** - Push collection logic to database for performance
- **Collection export** - Export collections as separate files

### Known Limitations

1. **Starred timestamp approximation**
   - No dedicated `starred_at` field
   - Uses `added` timestamp instead
   - May not reflect actual time bookmark was starred

2. **No caching**
   - Collections recomputed on each access
   - May be slow for very large databases (>100k)
   - Consider SQL-based filtering for production use with large datasets

3. **PDF detection limitation**
   - Only detects URLs ending with `.pdf`
   - PDFs served dynamically (e.g., `?format=pdf`) not detected
   - Could enhance with content-type checking in future

### Migration Notes

No migration required. This release is fully backward compatible with v0.7.0.

- All existing workflows continue to work
- New features are additive, not breaking
- Database schema unchanged
- Configuration unchanged

### Contributors

This release implements the smart collections and time-based recent features as designed in:
- `docs/development/SMART_COLLECTIONS_DESIGN.md`
- `docs/development/SMART_COLLECTIONS_IMPLEMENTATION.md`

## [0.7.0] - 2025-10-19

### Added - Interactive Shell

**Major Feature: Interactive Shell with Virtual Filesystem**

- **Virtual filesystem interface** for browsing bookmarks
  - Root directories: `/bookmarks`, `/tags`, `/starred`, `/archived`, `/recent`, `/domains`
  - Navigate bookmarks like files in a Unix filesystem
  - Path-based navigation with support for `.` and `..`
  - Context-aware commands that adapt based on current location

- **Navigation commands**
  - `ls` - List bookmarks, tags, or directories (context-aware)
  - `cd <path>` - Change directory with full path support
  - `pwd` - Print current working directory
  - `which <id>` - Find all locations where a bookmark exists

- **Hierarchical tag browsing**
  - Navigate tag hierarchies like directories (e.g., `/tags/programming/python/web`)
  - Tags with `/` separator create browsable directory structures
  - Subtags displayed as subdirectories in `ls` output
  - Bookmark IDs displayed alongside subtags in tag directories

- **Tag operations in shell**
  - `mv <old-tag> <new-tag>` - Rename tags across all bookmarks
  - `cp <tag> <target>` - Copy tags to bookmarks
    - `cp tag .` - Copy to current bookmark
    - `cp tag <id>` - Copy to specific bookmark
    - `cp tag *` - Copy to all bookmarks in current context
  - Confirmation prompts for bulk operations

- **Activity tracking**
  - `recent [visited|added|starred]` - View recent activity
  - Context-aware filtering (shows only bookmarks in current context)
  - `--limit N` option to control number of results

- **Viewing commands**
  - `cat <field>` or `cat <id>/<field>` - Display bookmark fields
  - `file [<id>]` - Show bookmark metadata summary
  - `stat` - Show statistics for current context

- **Bookmark operations**
  - `star [<id>]` - Toggle star status
  - `tag <tags...>` - Add tags to current or specified bookmark
  - `untag <tags...>` - Remove tags from bookmark
  - `visit [<id>]` - Open bookmark in browser
  - `edit <field>` - Edit bookmark fields
  - `rm [<id>]` - Remove bookmark (with confirmation)

- **Search commands**
  - `find <query>` - Search bookmarks (context-aware)
  - `grep <pattern> <field>` - Search in specific fields

- **Utility commands**
  - `help [command]` - Show command help
  - `history` - View command history
  - `clear` - Clear screen
  - `tutorial` - Interactive tutorial
  - `!<command>` - Execute system commands

### Added - Grouped CLI Structure

**Major Refactor: Organized Command Groups**

The CLI has been reorganized from flat commands to logical groups:

1. **`btk bookmark`** - Core bookmark operations
   - `add` - Add new bookmark
   - `list` - List bookmarks with filtering
   - `search` - Search bookmarks
   - `get` - Get bookmark details
   - `update` - Update bookmark metadata
   - `delete` - Delete bookmarks
   - `query` - Advanced SQL-like queries

2. **`btk tag`** - Tag management
   - `list` - List all tags
   - `tree` - Show hierarchical tag tree
   - `stats` - Tag usage statistics
   - `add` - Add tags to bookmarks
   - `remove` - Remove tags from bookmarks
   - `rename` - Rename tags globally
   - `copy` - Copy tags to bookmarks
   - `filter` - Filter bookmarks by tag prefix

3. **`btk content`** - Content operations
   - `refresh` - Fetch/refresh cached content
   - `view` - View cached content
   - `auto-tag` - AI-powered tag suggestions

4. **`btk import`** - Import bookmarks
   - `html` - Import HTML (Netscape format)
   - `json` - Import JSON
   - `csv` - Import CSV
   - `text` - Import plain text URLs
   - `chrome` - Import from Chrome
   - `firefox` - Import from Firefox
   - `safari` - Import from Safari

5. **`btk export`** - Export bookmarks
   - `html` - Export to HTML (with --hierarchical option)
   - `json` - Export to JSON
   - `csv` - Export to CSV
   - `markdown` - Export to Markdown

6. **`btk db`** - Database management
   - `info` - Show database statistics
   - `schema` - Display database schema
   - `stats` - Detailed statistics
   - `vacuum` - Optimize database
   - `dedupe` - Handle duplicate bookmarks

7. **`btk graph`** - Graph analysis
   - `build` - Build similarity graph
   - `neighbors` - Find similar bookmarks
   - `export` - Export graph data
   - `stats` - Graph statistics

8. **`btk config`** - Configuration
   - `show` - Display current configuration
   - `set` - Set configuration values
   - `init` - Initialize configuration file

9. **`btk shell`** - Launch interactive shell

### Added - Tag Management Commands

- **`btk tag add <tag> <ids...>`** - Add tag to multiple bookmarks
  - `--all` - Add to all bookmarks
  - `--starred` - Add to starred bookmarks
  - `--filter-tags` - Add to bookmarks with specific tags

- **`btk tag remove <tag> <ids...>`** - Remove tag from bookmarks
  - `--all` - Remove from all bookmarks
  - `--filter-tags` - Remove from filtered bookmarks

- **`btk tag rename <old> <new>`** - Rename tag globally
  - Shows affected bookmark count
  - Requires confirmation
  - Cleans up orphaned tags

- **`btk tag copy <tag>`** - Copy tag to bookmarks
  - `--to-ids` - Copy to specific IDs
  - `--starred` - Copy to starred bookmarks
  - `--filter-tags` - Copy to filtered bookmarks

### Added - CLI-Shell Parity

Commands that work similarly in both CLI and shell:

| Operation | CLI | Shell |
|-----------|-----|-------|
| List bookmarks | `btk bookmark list` | `ls` (in /bookmarks) |
| Search | `btk bookmark search "term"` | `find "term"` |
| Get bookmark | `btk bookmark get 123` | `cd bookmarks/123; ls` |
| Add tag | `btk tag add python 123` | `tag 123 python` |
| Rename tag | `btk tag rename old new` | `mv old new` |
| Copy tag | `btk tag copy tag 123` | `cp tag 123` |
| Star bookmark | `btk bookmark update 123 --stars` | `star 123` |
| Recent activity | `btk bookmark list --sort visited` | `recent` |

### Improved

- **Context-aware operations** - Commands now adapt based on shell location
- **Better help system** - Improved help text for all commands
- **Confirmation prompts** - Added safety for destructive operations
- **Error handling** - Better error messages and validation
- **Path normalization** - Robust path handling in shell
- **Tag hierarchy support** - Full support for `/` separated tag hierarchies

### Changed

- **CLI command structure** - Migrated from flat to grouped commands
  - Old: `btk add`, `btk list`, `btk tags`
  - New: `btk bookmark add`, `btk bookmark list`, `btk tag list`
- **Shell navigation** - Changed from bookmark-centric to filesystem-centric
  - Old: Started directly in bookmark list
  - New: Start at `/` root with multiple top-level directories
- **Tag operations** - Moved from bookmark commands to dedicated tag group
- **Database location** - Now specified via `--db` flag or config, not directory

### Testing

- **515 total tests** - Comprehensive test coverage
  - 69 new shell tests (53% coverage)
  - 41 new CLI tests (23% coverage)
  - All core modules >80% coverage
- **Test categories**
  - Unit tests for core functions
  - Integration tests for shell commands
  - Integration tests for CLI commands
  - End-to-end workflow tests

### Performance

- No significant performance changes
- Shell maintains interactive responsiveness
- CLI commands remain fast for typical operations

### Documentation

- **New shell guide** - Complete documentation of shell interface
- **Updated command guide** - Reorganized for new CLI structure
- **Updated tags guide** - Enhanced with hierarchical tag navigation
- **Updated quick start** - Includes both CLI and shell workflows
- **Updated homepage** - Highlights shell as flagship feature

## [0.6.0] - 2024-XX-XX

### Added

- **Graph analysis features**
  - Build bookmark similarity graphs
  - Export to GEXF, GraphML, JSON formats
  - Visualize relationships in external tools (Gephi, yEd, Cytoscape)
  - Multiple similarity metrics (domain, tags, links)
  - Configurable edge weights and thresholds

- **Plugin system**
  - Extensible plugin architecture
  - Plugin lifecycle hooks
  - Plugin priority system
  - Example plugins included

### Improved

- **Content caching**
  - Better compression ratios
  - Improved PDF text extraction
  - More reliable content fetching
  - Error handling for unreachable URLs

- **Auto-tagging**
  - Enhanced TF-IDF analysis
  - Confidence scoring
  - Preview mode before applying
  - Bulk operations support

### Fixed

- Various bug fixes and stability improvements
- Database migration improvements
- Import/export edge cases

## [0.5.0] - 2024-XX-XX

### Added

- **Database migration to SQLAlchemy**
  - SQLite backend with SQLAlchemy ORM
  - ACID transaction support
  - Better query performance
  - Schema migrations

- **Content caching system**
  - Automatic HTML caching
  - Markdown conversion
  - zlib compression
  - PDF text extraction

- **Browser import**
  - Direct import from Chrome
  - Direct import from Firefox
  - Direct import from Safari
  - Profile selection support

### Changed

- Migrated from JSON file storage to SQLite database
- Improved command-line argument parsing
- Better error messages and validation

### Removed

- Legacy JSON-based storage system
- Directory-based bookmark libraries

## [0.4.0] - 2024-XX-XX

### Added

- **Auto-tagging with NLP**
  - TF-IDF based tag suggestions
  - Confidence scoring
  - Bulk auto-tagging

- **Hierarchical HTML export**
  - Browser-compatible folder structure
  - Tags create nested folders
  - Import into any browser

### Improved

- Search performance
- Import/export reliability
- Tag management

## [0.3.0] - 2024-XX-XX

### Added

- **Multi-format import/export**
  - HTML (Netscape Bookmark Format)
  - JSON
  - CSV
  - Markdown
  - Plain text

- **Advanced search**
  - Full-text search
  - Tag filtering
  - JMESPath queries

### Improved

- Better duplicate detection
- Enhanced tag support

## [0.2.0] - 2024-XX-XX

### Added

- Basic bookmark management
  - Add, edit, delete bookmarks
  - Tag support
  - Star bookmarks

- **Deduplication**
  - Find duplicate URLs
  - Multiple merge strategies

### Improved

- Command-line interface
- Error handling

## [0.1.0] - 2024-XX-XX

### Added

- Initial release
- Basic bookmark storage in JSON
- Simple import/export
- Tag support
- Search functionality

---

## Migration Guides

### Migrating to v0.7.0

#### CLI Command Changes

The command structure has changed. Update your scripts:

**Before (v0.6.0):**
```bash
btk add https://example.com
btk list
btk tags
btk search "python"
```

**After (v0.7.0):**
```bash
btk bookmark add https://example.com
btk bookmark list
btk tag list
btk bookmark search "python"
```

#### Shell Changes

The shell now starts at `/` instead of directly in the bookmark list:

**Before (v0.6.0):**
```bash
btk:/$ ls          # Listed all bookmarks
btk:/$ cd 123      # Entered bookmark
```

**After (v0.7.0):**
```bash
btk:/$ ls            # Shows virtual directories
btk:/$ cd bookmarks  # Enter bookmarks directory
btk:/bookmarks$ ls   # List bookmarks
btk:/bookmarks$ cd 123
```

Or use absolute paths:
```bash
btk:/$ cd /bookmarks/123
```

### Migrating to v0.6.0

If upgrading from v0.5.0 or earlier, your database schema will be automatically migrated on first run. Always backup your database before upgrading:

```bash
# Backup
cp btk.db btk.db.backup

# Upgrade
pip install --upgrade bookmark-tk

# Run to trigger migration
btk db info
```

### Migrating from JSON (v0.4.0 and earlier)

If you have bookmarks in the old JSON format, import them:

```bash
# Old format (directory with bookmarks.json)
btk import json /path/to/old/bookmarks.json

# The new database-based system will be used going forward
```

---

## Compatibility Notes

### v0.7.0

- **Python**: Requires Python 3.8+
- **Database**: SQLite 3.31.0+
- **Breaking changes**: CLI command structure changed (grouped commands)
- **Migration**: Scripts using old CLI commands need updates

### v0.6.0

- **Python**: Requires Python 3.8+
- **Database**: SQLite 3.31.0+
- **Breaking changes**: None (backward compatible with v0.5.0 databases)

### v0.5.0

- **Python**: Requires Python 3.8+
- **Database**: SQLite 3.31.0+
- **Breaking changes**: Database format changed from JSON to SQLite
- **Migration**: Use import command to migrate from JSON

---

## Roadmap

### Planned for v0.8.0

- **Enhanced shell features**
  - Tab completion for paths and commands
  - Command aliases
  - Shell scripting support
  - History search (Ctrl+R)

- **Smart collections**
  - Auto-updating collections (e.g., `/recent/last-week`)
  - Time-based directories (`/recent/today`, `/recent/this-week`)
  - Custom collection rules

- **Search improvements**
  - Full-text search with ranking
  - Advanced query builder
  - Saved searches

### Planned for v0.9.0

- **Collaboration features**
  - Export/import bookmark collections
  - Shared tag taxonomies
  - Collection templates

- **Browser extensions**
  - Chrome extension
  - Firefox extension
  - Real-time sync

### Planned for v1.0.0

- **MCP integration**
  - Model Context Protocol support
  - AI-powered queries
  - Semantic search

- **Static site generator**
  - Generate browsable websites from bookmarks
  - Customizable themes
  - Deploy to GitHub Pages

- **Advanced features**
  - Bookmark annotations
  - Reading list management
  - Link rot detection
  - Wayback Machine integration

---

## Contributing

See [Contributing Guide](contributing.md) for how to contribute to BTK.

## Support

- Report bugs: [GitHub Issues](https://github.com/queelius/bookmark-tk/issues)
- Feature requests: [GitHub Discussions](https://github.com/queelius/bookmark-tk/discussions)
- Documentation: [https://queelius.github.io/bookmark-tk/](https://queelius.github.io/bookmark-tk/)
