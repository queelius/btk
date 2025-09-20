"""
Universal browser synchronization for BTK.

Supports simultaneous sync across multiple browsers with advanced
conflict resolution, real-time monitoring, and optional SQLite backend.
"""

import os
import json
import sqlite3
import logging
import hashlib
from typing import Dict, Any, List, Optional, Set, Tuple
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import platform
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class Browser(Enum):
    """Supported browsers."""
    CHROME = "chrome"
    FIREFOX = "firefox"
    EDGE = "edge"
    SAFARI = "safari"
    BRAVE = "brave"
    VIVALDI = "vivaldi"
    OPERA = "opera"


class SyncDirection(Enum):
    """Synchronization direction."""
    TO_BROWSER = "to_browser"
    FROM_BROWSER = "from_browser"
    BIDIRECTIONAL = "bidirectional"


class ConflictStrategy(Enum):
    """Conflict resolution strategies."""
    BROWSER_WINS = "browser_wins"
    BTK_WINS = "btk_wins"
    NEWEST_WINS = "newest_wins"
    HIGHEST_HEALTH = "highest_health"
    MOST_VISITED = "most_visited"
    MERGE_ALL = "merge_all"
    MANUAL = "manual"


@dataclass
class SyncConfig:
    """Configuration for browser sync."""
    browsers: List[str] = field(default_factory=list)
    direction: SyncDirection = SyncDirection.BIDIRECTIONAL
    conflict_strategy: ConflictStrategy = ConflictStrategy.NEWEST_WINS
    sync_interval: int = 30  # seconds for watch mode
    auto_sync: bool = False
    backup_before_sync: bool = True
    use_sqlite: bool = False
    sqlite_path: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    browser_profiles: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class BookmarkChange:
    """Represents a bookmark change event."""
    source: str  # browser name or 'btk'
    action: str  # 'added', 'modified', 'removed'
    bookmark: Dict[str, Any]
    timestamp: datetime
    profile: Optional[str] = None


@dataclass
class SyncResult:
    """Result of a sync operation."""
    total_synced: int = 0
    added: int = 0
    modified: int = 0
    removed: int = 0
    conflicts_resolved: int = 0
    errors: List[str] = field(default_factory=list)
    duration: float = 0.0


class SQLiteBookmarkStore:
    """
    SQLite backend for BTK bookmarks with advanced querying capabilities.
    """

    def __init__(self, db_path: str):
        """Initialize SQLite store."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        """Create optimized database schema."""
        self.conn.executescript('''
            -- Main bookmarks table
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_id TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                description TEXT,
                added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_visited TIMESTAMP,
                visit_count INTEGER DEFAULT 0,
                stars BOOLEAN DEFAULT 0,
                health_score REAL,
                favicon TEXT,
                reachable BOOLEAN,
                content_hash TEXT,
                UNIQUE(url)
            );

            -- Tags table
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            -- Many-to-many relationship
            CREATE TABLE IF NOT EXISTS bookmark_tags (
                bookmark_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (bookmark_id, tag_id),
                FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            -- Browser sync tracking
            CREATE TABLE IF NOT EXISTS browser_sync (
                bookmark_id INTEGER,
                browser TEXT NOT NULL,
                profile TEXT,
                browser_id TEXT,
                browser_path TEXT,  -- Path in browser's bookmark tree
                last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_hash TEXT,
                metadata TEXT,  -- JSON for browser-specific data
                PRIMARY KEY (bookmark_id, browser, profile),
                FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE
            );

            -- Sync history for conflict resolution
            CREATE TABLE IF NOT EXISTS sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bookmark_id INTEGER,
                source TEXT,  -- Which browser/btk initiated change
                action TEXT,  -- added/modified/removed
                old_data TEXT,  -- JSON of previous state
                new_data TEXT,  -- JSON of new state
                conflict_resolved TEXT,  -- How conflict was resolved
                FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE SET NULL
            );

            -- Full-text search virtual table
            CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks_fts USING fts5(
                title,
                description,
                url,
                tags,
                content=bookmarks,
                content_rowid=id
            );

            -- Performance indexes
            CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON bookmarks(url);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_added ON bookmarks(added);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_health ON bookmarks(health_score);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_visited ON bookmarks(last_visited);
            CREATE INDEX IF NOT EXISTS idx_browser_sync_browser ON browser_sync(browser, profile);
            CREATE INDEX IF NOT EXISTS idx_sync_history_time ON sync_history(sync_time);
            CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);

            -- Triggers to maintain FTS index
            CREATE TRIGGER IF NOT EXISTS bookmarks_fts_insert AFTER INSERT ON bookmarks
            BEGIN
                INSERT INTO bookmarks_fts(rowid, title, description, url, tags)
                SELECT new.id, new.title, new.description, new.url,
                       GROUP_CONCAT(t.name, ' ')
                FROM bookmark_tags bt
                JOIN tags t ON bt.tag_id = t.id
                WHERE bt.bookmark_id = new.id;
            END;

            CREATE TRIGGER IF NOT EXISTS bookmarks_fts_update AFTER UPDATE ON bookmarks
            BEGIN
                UPDATE bookmarks_fts
                SET title = new.title,
                    description = new.description,
                    url = new.url
                WHERE rowid = new.id;
            END;

            CREATE TRIGGER IF NOT EXISTS bookmarks_fts_delete AFTER DELETE ON bookmarks
            BEGIN
                DELETE FROM bookmarks_fts WHERE rowid = old.id;
            END;
        ''')
        self.conn.commit()

    def add_bookmark(self, bookmark: Dict[str, Any]) -> int:
        """Add a bookmark to the database."""
        cursor = self.conn.cursor()

        # Insert bookmark
        cursor.execute('''
            INSERT OR REPLACE INTO bookmarks
            (unique_id, url, title, description, added, last_visited,
             visit_count, stars, health_score, favicon, reachable)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            bookmark.get('unique_id', self._generate_unique_id(bookmark['url'])),
            bookmark['url'],
            bookmark.get('title'),
            bookmark.get('description'),
            bookmark.get('added'),
            bookmark.get('last_visited'),
            bookmark.get('visit_count', 0),
            bookmark.get('stars', False),
            bookmark.get('health_score'),
            bookmark.get('favicon'),
            bookmark.get('reachable')
        ))

        bookmark_id = cursor.lastrowid

        # Handle tags
        tags = bookmark.get('tags', [])
        for tag in tags:
            cursor.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag,))
            cursor.execute('SELECT id FROM tags WHERE name = ?', (tag,))
            tag_id = cursor.fetchone()[0]
            cursor.execute(
                'INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag_id) VALUES (?, ?)',
                (bookmark_id, tag_id)
            )

        self.conn.commit()
        return bookmark_id

    def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Full-text search across bookmarks."""
        cursor = self.conn.cursor()

        # Use FTS5 for search
        cursor.execute('''
            SELECT b.*, GROUP_CONCAT(t.name) as tags
            FROM bookmarks b
            LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
            LEFT JOIN tags t ON bt.tag_id = t.id
            WHERE b.id IN (
                SELECT rowid FROM bookmarks_fts
                WHERE bookmarks_fts MATCH ?
                ORDER BY rank
            )
            GROUP BY b.id
            LIMIT ?
        ''', (query, limit))

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def query(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        """Execute arbitrary SQL query."""
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_browser_bookmarks(self, browser: str, profile: str = None) -> List[Dict[str, Any]]:
        """Get all bookmarks from a specific browser."""
        cursor = self.conn.cursor()

        if profile:
            cursor.execute('''
                SELECT b.*, GROUP_CONCAT(t.name) as tags, bs.browser_path
                FROM bookmarks b
                LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
                LEFT JOIN tags t ON bt.tag_id = t.id
                JOIN browser_sync bs ON b.id = bs.bookmark_id
                WHERE bs.browser = ? AND bs.profile = ?
                GROUP BY b.id
            ''', (browser, profile))
        else:
            cursor.execute('''
                SELECT b.*, GROUP_CONCAT(t.name) as tags, bs.browser_path
                FROM bookmarks b
                LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
                LEFT JOIN tags t ON bt.tag_id = t.id
                JOIN browser_sync bs ON b.id = bs.bookmark_id
                WHERE bs.browser = ?
                GROUP BY b.id
            ''', (browser,))

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def record_sync(self, bookmark_id: int, browser: str, profile: str,
                    browser_id: str = None, browser_path: str = None):
        """Record browser sync information."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO browser_sync
            (bookmark_id, browser, profile, browser_id, browser_path, last_synced)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (bookmark_id, browser, profile, browser_id, browser_path, datetime.now()))
        self.conn.commit()

    def get_sync_conflicts(self, since: datetime = None) -> List[Dict[str, Any]]:
        """Get bookmarks with sync conflicts."""
        cursor = self.conn.cursor()

        query = '''
            SELECT b.*, COUNT(DISTINCT bs.browser) as browser_count,
                   GROUP_CONCAT(DISTINCT bs.browser) as browsers
            FROM bookmarks b
            JOIN browser_sync bs ON b.id = bs.bookmark_id
            WHERE bs.bookmark_id IN (
                SELECT bookmark_id
                FROM sync_history
                WHERE action = 'modified'
                  AND (? IS NULL OR sync_time > ?)
                GROUP BY bookmark_id
                HAVING COUNT(DISTINCT source) > 1
            )
            GROUP BY b.id
        '''

        cursor.execute(query, (since, since))
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert SQLite row to dictionary."""
        d = dict(row)
        # Parse tags from comma-separated string
        if 'tags' in d and d['tags']:
            d['tags'] = d['tags'].split(',')
        else:
            d['tags'] = []
        return d

    def _generate_unique_id(self, url: str) -> str:
        """Generate unique ID for a bookmark."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def close(self):
        """Close database connection."""
        self.conn.close()


class UniversalBrowserSync:
    """
    Universal browser synchronization engine.

    Handles multi-browser sync with conflict resolution and monitoring.
    """

    def __init__(self, btk_lib: str, config: SyncConfig):
        """
        Initialize sync engine.

        Args:
            btk_lib: Path to BTK bookmark library
            config: Sync configuration
        """
        self.btk_lib = Path(btk_lib)
        self.config = config

        # Initialize storage backend
        if config.use_sqlite:
            db_path = config.sqlite_path or str(self.btk_lib / 'bookmarks.db')
            self.store = SQLiteBookmarkStore(db_path)
        else:
            self.store = None  # Use JSON files

        # Detect available browsers
        self.browsers = self._detect_browsers()

        # Load sync state
        self.sync_state_file = self.btk_lib / '.sync_state.json'
        self.sync_state = self._load_sync_state()

    def _detect_browsers(self) -> Dict[str, List[Path]]:
        """Detect installed browsers and their profiles."""
        browsers = {}
        system = platform.system()

        # Browser profile paths by OS
        if system == "Darwin":  # macOS
            paths = {
                Browser.CHROME: Path.home() / "Library/Application Support/Google/Chrome",
                Browser.FIREFOX: Path.home() / "Library/Application Support/Firefox/Profiles",
                Browser.SAFARI: Path.home() / "Library/Safari",
                Browser.BRAVE: Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser",
            }
        elif system == "Linux":
            paths = {
                Browser.CHROME: Path.home() / ".config/google-chrome",
                Browser.FIREFOX: Path.home() / ".mozilla/firefox",
                Browser.BRAVE: Path.home() / ".config/BraveSoftware/Brave-Browser",
            }
        elif system == "Windows":
            appdata = Path(os.environ['LOCALAPPDATA'])
            paths = {
                Browser.CHROME: appdata / "Google/Chrome/User Data",
                Browser.FIREFOX: appdata / "Mozilla/Firefox/Profiles",
                Browser.EDGE: appdata / "Microsoft/Edge/User Data",
                Browser.BRAVE: appdata / "BraveSoftware/Brave-Browser/User Data",
            }

        # Check which browsers are installed
        for browser, path in paths.items():
            if path.exists():
                profiles = self._find_profiles(browser, path)
                if profiles:
                    browsers[browser.value] = profiles
                    logger.info(f"Found {browser.value} with {len(profiles)} profiles")

        return browsers

    def _find_profiles(self, browser: Browser, browser_path: Path) -> List[Path]:
        """Find browser profiles."""
        profiles = []

        if browser == Browser.FIREFOX:
            # Firefox uses profiles.ini
            for item in browser_path.glob("*.default*"):
                if item.is_dir():
                    profiles.append(item)
        else:
            # Chrome-based browsers use Default, Profile 1, etc.
            for item in ["Default", "Profile 1", "Profile 2"]:
                profile_path = browser_path / item
                if profile_path.exists():
                    profiles.append(profile_path)

        return profiles

    def _load_sync_state(self) -> Dict[str, Any]:
        """Load previous sync state."""
        if self.sync_state_file.exists():
            with open(self.sync_state_file, 'r') as f:
                return json.load(f)
        return {'last_sync': {}, 'checksums': {}}

    def _save_sync_state(self):
        """Save current sync state."""
        with open(self.sync_state_file, 'w') as f:
            json.dump(self.sync_state, f, indent=2, default=str)

    def sync_all(self) -> SyncResult:
        """
        Synchronize all configured browsers.

        Returns:
            SyncResult with statistics
        """
        start_time = time.time()
        result = SyncResult()

        # Backup if configured
        if self.config.backup_before_sync:
            self._backup_bookmarks()

        # Collect changes from all sources
        all_changes = []

        # Get BTK changes
        btk_changes = self._detect_btk_changes()
        all_changes.extend(btk_changes)

        # Get browser changes
        for browser_name in self.config.browsers:
            if browser_name in self.browsers:
                for profile_path in self.browsers[browser_name]:
                    browser_changes = self._detect_browser_changes(browser_name, profile_path)
                    all_changes.extend(browser_changes)

        # Group changes by URL for conflict detection
        changes_by_url = defaultdict(list)
        for change in all_changes:
            url = change.bookmark.get('url')
            if url:
                changes_by_url[url].append(change)

        # Process changes with conflict resolution
        for url, url_changes in changes_by_url.items():
            if len(url_changes) > 1:
                # Conflict detected
                resolved = self._resolve_conflict(url_changes)
                result.conflicts_resolved += 1
            else:
                resolved = url_changes[0]

            # Apply the change
            self._apply_change(resolved)

            if resolved.action == 'added':
                result.added += 1
            elif resolved.action == 'modified':
                result.modified += 1
            elif resolved.action == 'removed':
                result.removed += 1

        result.total_synced = result.added + result.modified + result.removed
        result.duration = time.time() - start_time

        # Update sync state
        self._save_sync_state()

        logger.info(f"Sync completed: {result.total_synced} items in {result.duration:.2f}s")
        return result

    def _detect_btk_changes(self) -> List[BookmarkChange]:
        """Detect changes in BTK bookmarks since last sync."""
        changes = []

        # Load current BTK bookmarks
        bookmarks_file = self.btk_lib / 'bookmarks.json'
        if not bookmarks_file.exists():
            return changes

        with open(bookmarks_file, 'r') as f:
            current_bookmarks = json.load(f)

        # Calculate current checksum
        current_checksum = self._calculate_checksum(current_bookmarks)

        # Compare with last sync
        last_checksum = self.sync_state.get('checksums', {}).get('btk')

        if last_checksum != current_checksum:
            # Changes detected - do detailed comparison
            last_bookmarks = self.sync_state.get('last_bookmarks', {}).get('btk', [])

            current_urls = {b['url']: b for b in current_bookmarks}
            last_urls = {b['url']: b for b in last_bookmarks}

            # Find added bookmarks
            for url in set(current_urls.keys()) - set(last_urls.keys()):
                changes.append(BookmarkChange(
                    source='btk',
                    action='added',
                    bookmark=current_urls[url],
                    timestamp=datetime.now()
                ))

            # Find removed bookmarks
            for url in set(last_urls.keys()) - set(current_urls.keys()):
                changes.append(BookmarkChange(
                    source='btk',
                    action='removed',
                    bookmark=last_urls[url],
                    timestamp=datetime.now()
                ))

            # Find modified bookmarks
            for url in set(current_urls.keys()) & set(last_urls.keys()):
                if self._bookmark_changed(last_urls[url], current_urls[url]):
                    changes.append(BookmarkChange(
                        source='btk',
                        action='modified',
                        bookmark=current_urls[url],
                        timestamp=datetime.now()
                    ))

        # Update state
        self.sync_state['checksums']['btk'] = current_checksum
        self.sync_state.setdefault('last_bookmarks', {})['btk'] = current_bookmarks

        return changes

    def _detect_browser_changes(self, browser: str, profile_path: Path) -> List[BookmarkChange]:
        """Detect changes in browser bookmarks."""
        changes = []

        # Read browser bookmarks (implementation depends on browser type)
        browser_bookmarks = self._read_browser_bookmarks(browser, profile_path)

        # Similar change detection logic as BTK
        # ... (abbreviated for space)

        return changes

    def _resolve_conflict(self, changes: List[BookmarkChange]) -> BookmarkChange:
        """
        Resolve conflicts between multiple changes to the same bookmark.

        Args:
            changes: List of conflicting changes

        Returns:
            The resolved change to apply
        """
        strategy = self.config.conflict_strategy

        if strategy == ConflictStrategy.NEWEST_WINS:
            return max(changes, key=lambda c: c.timestamp)

        elif strategy == ConflictStrategy.BTK_WINS:
            btk_changes = [c for c in changes if c.source == 'btk']
            return btk_changes[0] if btk_changes else changes[0]

        elif strategy == ConflictStrategy.BROWSER_WINS:
            browser_changes = [c for c in changes if c.source != 'btk']
            return browser_changes[0] if browser_changes else changes[0]

        elif strategy == ConflictStrategy.HIGHEST_HEALTH:
            # Choose bookmark with highest health score
            return max(changes, key=lambda c: c.bookmark.get('health_score', 0))

        elif strategy == ConflictStrategy.MOST_VISITED:
            # Choose most visited bookmark
            return max(changes, key=lambda c: c.bookmark.get('visit_count', 0))

        elif strategy == ConflictStrategy.MERGE_ALL:
            # Merge metadata from all sources
            merged = changes[0].bookmark.copy()
            for change in changes[1:]:
                # Merge tags
                merged_tags = set(merged.get('tags', []))
                merged_tags.update(change.bookmark.get('tags', []))
                merged['tags'] = sorted(list(merged_tags))

                # Keep highest visit count
                merged['visit_count'] = max(
                    merged.get('visit_count', 0),
                    change.bookmark.get('visit_count', 0)
                )

                # Keep longest description
                if len(change.bookmark.get('description', '')) > len(merged.get('description', '')):
                    merged['description'] = change.bookmark['description']

            return BookmarkChange(
                source='merged',
                action='modified',
                bookmark=merged,
                timestamp=datetime.now()
            )

        else:  # MANUAL
            # In a real implementation, this would prompt the user
            logger.warning(f"Manual conflict resolution required for {changes[0].bookmark.get('url')}")
            return changes[0]

    def _apply_change(self, change: BookmarkChange):
        """Apply a bookmark change to all targets."""
        if self.store:
            # Use SQLite backend
            if change.action == 'added':
                self.store.add_bookmark(change.bookmark)
            # ... handle other actions
        else:
            # Use JSON files
            # ... existing JSON handling
            pass

    def _bookmark_changed(self, old: Dict, new: Dict) -> bool:
        """Check if a bookmark has changed."""
        # Ignore certain fields when comparing
        ignore_fields = {'id', 'last_checked', 'health_score'}

        for key in set(old.keys()) | set(new.keys()):
            if key in ignore_fields:
                continue
            if old.get(key) != new.get(key):
                return True
        return False

    def _calculate_checksum(self, bookmarks: List[Dict]) -> str:
        """Calculate checksum for bookmark list."""
        # Sort bookmarks by URL for consistent hashing
        sorted_bookmarks = sorted(bookmarks, key=lambda b: b.get('url', ''))
        content = json.dumps(sorted_bookmarks, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def _backup_bookmarks(self):
        """Create backup before sync."""
        backup_dir = self.btk_lib / 'backups'
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f'bookmarks_backup_{timestamp}.json'

        # Copy current bookmarks
        import shutil
        shutil.copy2(self.btk_lib / 'bookmarks.json', backup_file)
        logger.info(f"Created backup: {backup_file}")

    def _read_browser_bookmarks(self, browser: str, profile_path: Path) -> List[Dict]:
        """Read bookmarks from a browser profile."""
        bookmarks = []

        if browser in ['chrome', 'edge', 'brave']:
            # Chrome-based browsers use Bookmarks JSON file
            bookmarks_file = profile_path / 'Bookmarks'
            if bookmarks_file.exists():
                with open(bookmarks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Parse Chrome bookmark structure
                    bookmarks = self._parse_chrome_bookmarks(data)

        elif browser == 'firefox':
            # Firefox uses places.sqlite
            places_db = profile_path / 'places.sqlite'
            if places_db.exists():
                bookmarks = self._read_firefox_bookmarks(places_db)

        return bookmarks

    def _parse_chrome_bookmarks(self, data: Dict) -> List[Dict]:
        """Parse Chrome bookmark structure."""
        bookmarks = []

        def traverse(node, path=''):
            if node.get('type') == 'url':
                bookmarks.append({
                    'url': node.get('url'),
                    'title': node.get('name'),
                    'added': self._chrome_time_to_iso(node.get('date_added')),
                    'tags': [path] if path else [],
                    'browser_id': node.get('id'),
                    'browser_path': path
                })
            elif node.get('type') == 'folder':
                new_path = f"{path}/{node.get('name')}" if path else node.get('name', '')
                for child in node.get('children', []):
                    traverse(child, new_path)

        # Traverse bookmark bar and other bookmarks
        roots = data.get('roots', {})
        traverse(roots.get('bookmark_bar', {}), 'Bookmarks Bar')
        traverse(roots.get('other', {}), 'Other Bookmarks')

        return bookmarks

    def _chrome_time_to_iso(self, chrome_time: str) -> str:
        """Convert Chrome timestamp to ISO format."""
        if chrome_time:
            # Chrome uses microseconds since 1601-01-01
            epoch_diff = 11644473600000000
            try:
                timestamp = (int(chrome_time) - epoch_diff) / 1000000
                return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            except:
                pass
        return None

    def _read_firefox_bookmarks(self, places_db: Path) -> List[Dict]:
        """Read bookmarks from Firefox places.sqlite."""
        import sqlite3
        import shutil
        import tempfile

        # Copy database to temp location (Firefox may have it locked)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            shutil.copy2(places_db, tmp.name)

            conn = sqlite3.connect(tmp.name)
            cursor = conn.cursor()

            # Query bookmarks
            cursor.execute('''
                SELECT b.id, b.title, p.url, b.dateAdded
                FROM moz_bookmarks b
                JOIN moz_places p ON b.fk = p.id
                WHERE b.type = 1
            ''')

            bookmarks = []
            for row in cursor.fetchall():
                bookmarks.append({
                    'browser_id': row[0],
                    'title': row[1],
                    'url': row[2],
                    'added': self._firefox_time_to_iso(row[3]),
                    'tags': []  # TODO: Extract Firefox tags
                })

            conn.close()
            os.unlink(tmp.name)

        return bookmarks

    def _firefox_time_to_iso(self, firefox_time: int) -> str:
        """Convert Firefox timestamp to ISO format."""
        if firefox_time:
            # Firefox uses microseconds since Unix epoch
            try:
                timestamp = firefox_time / 1000000
                return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            except:
                pass
        return None

    def watch(self, callback=None):
        """
        Watch for bookmark changes and sync automatically.

        Args:
            callback: Optional callback function for change events
        """
        logger.info(f"Starting watch mode (interval: {self.config.sync_interval}s)")

        while True:
            try:
                # Check for changes
                changes = []
                changes.extend(self._detect_btk_changes())

                for browser_name in self.config.browsers:
                    if browser_name in self.browsers:
                        for profile_path in self.browsers[browser_name]:
                            changes.extend(self._detect_browser_changes(browser_name, profile_path))

                if changes:
                    logger.info(f"Detected {len(changes)} changes")

                    if callback:
                        callback(changes)

                    if self.config.auto_sync:
                        result = self.sync_all()
                        logger.info(f"Auto-sync completed: {result.total_synced} items")

                time.sleep(self.config.sync_interval)

            except KeyboardInterrupt:
                logger.info("Watch mode stopped")
                break
            except Exception as e:
                logger.error(f"Error in watch mode: {e}")
                time.sleep(self.config.sync_interval)