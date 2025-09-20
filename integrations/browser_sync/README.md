# BTK Browser Sync Integration

Advanced browser bookmark synchronization across multiple browsers with conflict resolution and real-time monitoring.

## Features

### Multi-Browser Support
- **Simultaneous sync** across Chrome, Firefox, Edge, Safari, Brave, Vivaldi
- **Profile management** - sync specific browser profiles
- **Cross-browser deduplication** - smart detection of same bookmarks across browsers
- **Unified tag system** - map browser folders to BTK tags

### Advanced Sync Capabilities
- **Real-time monitoring** - detect browser bookmark changes instantly
- **Bidirectional sync** - changes flow both ways
- **Conflict resolution** - multiple strategies (newest wins, merge, manual)
- **Incremental sync** - only sync changes since last run
- **Backup & rollback** - restore previous states

### Smart Features
- **Health score integration** - sync bookmark quality metrics to browsers
- **Duplicate detection** - use BTK's smart dedup across browsers
- **Bookmark enrichment** - add BTK metadata to browser bookmarks
- **Sync rules** - filter what gets synced (by tag, domain, age)

## Architecture

### SQLite Backend (Optional)
For advanced querying and better performance with large collections:

```python
# Optional SQLite storage backend
class SQLiteBookmarkStore:
    """
    SQLite backend for BTK bookmarks with full-text search,
    advanced filtering, and transactional updates.
    """

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self._create_schema()

    def _create_schema(self):
        """Create optimized schema with indexes."""
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY,
                unique_id TEXT UNIQUE,
                url TEXT NOT NULL,
                title TEXT,
                description TEXT,
                added TIMESTAMP,
                last_visited TIMESTAMP,
                visit_count INTEGER DEFAULT 0,
                stars BOOLEAN DEFAULT 0,
                health_score REAL,
                UNIQUE(url)
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE
            );

            CREATE TABLE IF NOT EXISTS bookmark_tags (
                bookmark_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (bookmark_id, tag_id),
                FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id)
            );

            CREATE TABLE IF NOT EXISTS browser_sync (
                bookmark_id INTEGER,
                browser TEXT,
                profile TEXT,
                browser_id TEXT,
                last_synced TIMESTAMP,
                sync_hash TEXT,
                PRIMARY KEY (bookmark_id, browser, profile),
                FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id)
            );

            -- Full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks_fts USING fts5(
                title, description, url, content=bookmarks
            );

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON bookmarks(url);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_added ON bookmarks(added);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_health ON bookmarks(health_score);
            CREATE INDEX IF NOT EXISTS idx_browser_sync ON browser_sync(browser, profile);
        ''')
```

### Sync Engine

```python
class UniversalBrowserSync:
    """
    Synchronize bookmarks across multiple browsers simultaneously.
    """

    def __init__(self, btk_lib: str, config: SyncConfig):
        self.btk_lib = btk_lib
        self.config = config
        self.browsers = self._detect_browsers()
        self.sync_state = self._load_sync_state()

    def sync_all(self):
        """Sync all configured browsers."""
        changes = []

        # Collect changes from all browsers
        for browser in self.browsers:
            browser_changes = self._detect_browser_changes(browser)
            changes.extend(browser_changes)

        # Detect BTK changes
        btk_changes = self._detect_btk_changes()

        # Resolve conflicts across all sources
        resolved = self._resolve_conflicts(changes, btk_changes)

        # Apply changes to all targets
        self._apply_changes(resolved)

        # Update sync state
        self._save_sync_state()
```

## Installation

```bash
cd integrations/browser_sync
pip install -r requirements.txt
```

## Usage

### Basic Sync
```bash
# Sync with all detected browsers
btk-browser-sync sync

# Sync specific browsers
btk-browser-sync sync --browsers chrome firefox

# One-way sync
btk-browser-sync sync --direction to-browser
```

### Advanced Configuration
```yaml
# .btk-sync.yaml
sync:
  browsers:
    - chrome:
        profiles: ["Default", "Work"]
        sync_folders: ["Bookmarks Bar", "Other Bookmarks"]
    - firefox:
        profiles: ["default-release"]
        sync_folders: ["toolbar", "menu"]

  rules:
    - include_tags: ["work", "research"]
    - exclude_domains: ["facebook.com", "twitter.com"]
    - min_health_score: 0.4

  conflict_resolution:
    strategy: "newest_wins"
    backup_before_sync: true

  monitoring:
    watch_interval: 30  # seconds
    auto_sync: true
```

### Real-time Monitoring
```bash
# Watch for changes and auto-sync
btk-browser-sync watch

# Stream sync events
btk-browser-sync watch --stream | jq '.event'
```

### Cross-Browser Operations
```bash
# Find bookmarks present in Chrome but not Firefox
btk-browser-sync diff --browsers chrome firefox

# Merge all browser bookmarks into BTK
btk-browser-sync merge --from all-browsers --to btk

# Export unified bookmarks to all browsers
btk-browser-sync export --to all-browsers
```

## API

```python
from btk_browser_sync import UniversalBrowserSync, SyncConfig

# Configure sync
config = SyncConfig(
    browsers=['chrome', 'firefox', 'edge'],
    direction='bidirectional',
    conflict_resolution='merge',
    filters={
        'min_health_score': 0.5,
        'exclude_tags': ['temp', 'archive']
    }
)

# Initialize sync engine
sync = UniversalBrowserSync('~/bookmarks', config)

# Sync all browsers
result = sync.sync_all()
print(f"Synced {result.total_synced} bookmarks")
print(f"Conflicts resolved: {result.conflicts_resolved}")

# Watch for changes
for event in sync.watch():
    print(f"Change detected: {event.type} in {event.browser}")
    if event.auto_sync:
        sync.sync_browser(event.browser)
```

## Database Query Examples

If using SQLite backend:

```python
# Advanced queries
store = SQLiteBookmarkStore('bookmarks.db')

# Full-text search
results = store.search("machine learning python")

# Complex filtering
bookmarks = store.query("""
    SELECT b.*, GROUP_CONCAT(t.name) as tags
    FROM bookmarks b
    LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
    LEFT JOIN tags t ON bt.tag_id = t.id
    WHERE b.health_score > 0.6
      AND b.added > date('now', '-30 days')
      AND t.name IN ('programming', 'ai', 'research')
    GROUP BY b.id
    ORDER BY b.health_score DESC, b.visit_count DESC
""")

# Browser-specific queries
chrome_only = store.query("""
    SELECT b.* FROM bookmarks b
    JOIN browser_sync bs ON b.id = bs.bookmark_id
    WHERE bs.browser = 'chrome'
      AND bs.bookmark_id NOT IN (
        SELECT bookmark_id FROM browser_sync
        WHERE browser = 'firefox'
      )
""")
```

## Advantages of SQLite Option

1. **Performance**
   - Indexed searches are orders of magnitude faster
   - Efficient handling of 100k+ bookmarks
   - Concurrent access support

2. **Advanced Queries**
   - Full-text search
   - Complex JOINs across tags, browsers
   - Aggregations and analytics

3. **Transactional Safety**
   - ACID compliance
   - Rollback on sync failures
   - Concurrent browser access

4. **Backward Compatible**
   - Can still export to JSON
   - Maintains BTK's simple file format
   - Optional - only for power users

## Migration Path

```bash
# Migrate existing JSON to SQLite
btk-browser-sync migrate --from json --to sqlite

# Use SQLite for sync, export to JSON for compatibility
btk-browser-sync sync --backend sqlite --export-json
```

## Future Enhancements

- **Browser Extension**: Real-time sync without polling
- **Cloud Sync**: Sync across devices via encrypted cloud storage
- **AI Integration**: Smart bookmark organization based on content
- **Analytics Dashboard**: Web UI for bookmark analytics
- **Mobile Sync**: Android/iOS bookmark sync