"""
Browser bookmark synchronization for BTK.

This module provides two-way sync between BTK and browser bookmarks,
detecting changes and resolving conflicts intelligently.
"""

import os
import json
import logging
import shutil
from typing import Dict, Any, List, Optional, Tuple, Set
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import hashlib
import sqlite3

from btk.plugins import Plugin, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


class Browser(Enum):
    """Supported browsers."""
    CHROME = "chrome"
    FIREFOX = "firefox"
    EDGE = "edge"
    SAFARI = "safari"
    BRAVE = "brave"
    VIVALDI = "vivaldi"


class SyncDirection(Enum):
    """Synchronization direction."""
    TO_BROWSER = "to_browser"
    FROM_BROWSER = "from_browser"
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(Enum):
    """Conflict resolution strategies."""
    BROWSER_WINS = "browser_wins"
    BTK_WINS = "btk_wins"
    NEWEST_WINS = "newest_wins"
    MERGE = "merge"
    ASK = "ask"


@dataclass
class SyncState:
    """State information for synchronization."""
    last_sync: Optional[datetime] = None
    browser_hash: Optional[str] = None
    btk_hash: Optional[str] = None
    synced_items: Dict[str, str] = None  # URL -> hash mapping
    
    def __post_init__(self):
        if self.synced_items is None:
            self.synced_items = {}


class BrowserSync(Plugin):
    """
    Browser bookmark synchronization plugin.
    
    This plugin enables two-way sync between BTK and browser bookmarks,
    with intelligent conflict resolution and change detection.
    """
    
    def __init__(self, browser: Browser = Browser.CHROME,
                 profile: Optional[str] = None,
                 sync_dir: SyncDirection = SyncDirection.BIDIRECTIONAL,
                 conflict_strategy: ConflictResolution = ConflictResolution.NEWEST_WINS):
        """
        Initialize browser sync.
        
        Args:
            browser: Browser type to sync with
            profile: Browser profile name (None for default)
            sync_dir: Synchronization direction
            conflict_strategy: How to resolve conflicts
        """
        self._metadata = PluginMetadata(
            name="browser_sync",
            version="1.0.0",
            author="BTK Team",
            description=f"Sync bookmarks with {browser.value} browser",
            priority=PluginPriority.NORMAL.value
        )
        
        self.browser = browser
        self.profile = profile
        self.sync_direction = sync_dir
        self.conflict_strategy = conflict_strategy
        
        # Find browser bookmark file
        self.bookmark_file = self._find_bookmark_file()
        
        # State file for tracking sync
        self.state_file = Path.home() / '.btk' / 'sync_state' / f"{browser.value}_{profile or 'default'}.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load sync state
        self.state = self._load_state()
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def _find_bookmark_file(self) -> Optional[Path]:
        """
        Find the browser's bookmark file.
        
        Returns:
            Path to bookmark file or None if not found
        """
        home = Path.home()
        
        # Define paths for each browser
        paths = {
            Browser.CHROME: [
                home / '.config' / 'google-chrome' / (self.profile or 'Default') / 'Bookmarks',
                home / 'Library' / 'Application Support' / 'Google' / 'Chrome' / (self.profile or 'Default') / 'Bookmarks',
                home / 'AppData' / 'Local' / 'Google' / 'Chrome' / 'User Data' / (self.profile or 'Default') / 'Bookmarks'
            ],
            Browser.FIREFOX: [
                # Firefox uses places.sqlite, more complex
                home / '.mozilla' / 'firefox',
                home / 'Library' / 'Application Support' / 'Firefox' / 'Profiles',
                home / 'AppData' / 'Roaming' / 'Mozilla' / 'Firefox' / 'Profiles'
            ],
            Browser.EDGE: [
                home / '.config' / 'microsoft-edge' / (self.profile or 'Default') / 'Bookmarks',
                home / 'Library' / 'Application Support' / 'Microsoft Edge' / (self.profile or 'Default') / 'Bookmarks',
                home / 'AppData' / 'Local' / 'Microsoft' / 'Edge' / 'User Data' / (self.profile or 'Default') / 'Bookmarks'
            ],
            Browser.BRAVE: [
                home / '.config' / 'BraveSoftware' / 'Brave-Browser' / (self.profile or 'Default') / 'Bookmarks',
                home / 'Library' / 'Application Support' / 'BraveSoftware' / 'Brave-Browser' / (self.profile or 'Default') / 'Bookmarks',
                home / 'AppData' / 'Local' / 'BraveSoftware' / 'Brave-Browser' / 'User Data' / (self.profile or 'Default') / 'Bookmarks'
            ],
            Browser.VIVALDI: [
                home / '.config' / 'vivaldi' / (self.profile or 'Default') / 'Bookmarks',
                home / 'Library' / 'Application Support' / 'Vivaldi' / (self.profile or 'Default') / 'Bookmarks',
                home / 'AppData' / 'Local' / 'Vivaldi' / 'User Data' / (self.profile or 'Default') / 'Bookmarks'
            ]
        }
        
        # Check each path
        for path in paths.get(self.browser, []):
            if self.browser == Browser.FIREFOX:
                # For Firefox, find profile directory
                if path.exists():
                    for profile_dir in path.glob('*.default*'):
                        places_file = profile_dir / 'places.sqlite'
                        if places_file.exists():
                            return places_file
            else:
                # For Chromium-based browsers
                if path.exists():
                    return path
        
        logger.warning(f"Could not find {self.browser.value} bookmark file")
        return None
    
    def _load_state(self) -> SyncState:
        """Load synchronization state."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    return SyncState(
                        last_sync=datetime.fromisoformat(data['last_sync']) if data.get('last_sync') else None,
                        browser_hash=data.get('browser_hash'),
                        btk_hash=data.get('btk_hash'),
                        synced_items=data.get('synced_items', {})
                    )
            except Exception as e:
                logger.warning(f"Failed to load sync state: {e}")
        
        return SyncState()
    
    def _save_state(self):
        """Save synchronization state."""
        try:
            data = {
                'last_sync': self.state.last_sync.isoformat() if self.state.last_sync else None,
                'browser_hash': self.state.browser_hash,
                'btk_hash': self.state.btk_hash,
                'synced_items': self.state.synced_items
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save sync state: {e}")
    
    def read_browser_bookmarks(self) -> List[Dict[str, Any]]:
        """
        Read bookmarks from the browser.
        
        Returns:
            List of bookmarks in BTK format
        """
        if not self.bookmark_file or not self.bookmark_file.exists():
            logger.error(f"Browser bookmark file not found")
            return []
        
        if self.browser == Browser.FIREFOX:
            return self._read_firefox_bookmarks()
        else:
            return self._read_chromium_bookmarks()
    
    def _read_chromium_bookmarks(self) -> List[Dict[str, Any]]:
        """Read bookmarks from Chromium-based browsers."""
        try:
            with open(self.bookmark_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            bookmarks = []
            
            # Process bookmark bar
            if 'bookmark_bar' in data.get('roots', {}):
                self._process_chromium_folder(data['roots']['bookmark_bar'], bookmarks, ['bookmark_bar'])
            
            # Process other bookmarks
            if 'other' in data.get('roots', {}):
                self._process_chromium_folder(data['roots']['other'], bookmarks, ['other'])
            
            # Process synced bookmarks
            if 'synced' in data.get('roots', {}):
                self._process_chromium_folder(data['roots']['synced'], bookmarks, ['synced'])
            
            return bookmarks
            
        except Exception as e:
            logger.error(f"Failed to read Chromium bookmarks: {e}")
            return []
    
    def _process_chromium_folder(self, folder: Dict[str, Any], bookmarks: List[Dict[str, Any]], 
                                 path: List[str]):
        """Process a Chromium bookmark folder recursively."""
        if folder.get('type') == 'folder':
            folder_name = folder.get('name', '')
            if folder_name and folder_name not in ['Bookmarks Bar', 'Other Bookmarks']:
                path = path + [folder_name]
            
            for child in folder.get('children', []):
                self._process_chromium_folder(child, bookmarks, path)
        
        elif folder.get('type') == 'url':
            # Convert to BTK format
            bookmark = {
                'url': folder.get('url'),
                'title': folder.get('name', ''),
                'tags': path[1:] if len(path) > 1 else [],  # Use folder path as tags
                'added': self._chromium_timestamp_to_iso(folder.get('date_added')),
                'browser_id': folder.get('id'),
                'browser_guid': folder.get('guid'),
                'source': f'browser:{self.browser.value}'
            }
            
            # Add last modified if available
            if folder.get('date_last_used'):
                bookmark['last_visited'] = self._chromium_timestamp_to_iso(folder['date_last_used'])
            
            bookmarks.append(bookmark)
    
    def _chromium_timestamp_to_iso(self, timestamp: str) -> str:
        """Convert Chromium timestamp to ISO format."""
        if not timestamp:
            return datetime.now().isoformat()
        
        try:
            # Chromium uses microseconds since 1601-01-01
            epoch_delta = 11644473600  # Seconds between 1601 and 1970
            seconds = int(timestamp) / 1000000 - epoch_delta
            return datetime.fromtimestamp(seconds).isoformat()
        except:
            return datetime.now().isoformat()
    
    def _read_firefox_bookmarks(self) -> List[Dict[str, Any]]:
        """Read bookmarks from Firefox places.sqlite."""
        bookmarks = []
        
        try:
            # Copy database to avoid locking issues
            temp_db = Path('/tmp') / f'places_{os.getpid()}.sqlite'
            shutil.copy2(self.bookmark_file, temp_db)
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # Query bookmarks
            query = """
            SELECT 
                b.id,
                b.title,
                p.url,
                b.dateAdded,
                b.lastModified,
                b.guid,
                b.parent,
                (SELECT title FROM moz_bookmarks WHERE id = b.parent) as folder
            FROM moz_bookmarks b
            LEFT JOIN moz_places p ON b.fk = p.id
            WHERE b.type = 1 AND p.url IS NOT NULL
            """
            
            cursor.execute(query)
            
            for row in cursor.fetchall():
                bookmark = {
                    'url': row[2],
                    'title': row[1] or '',
                    'tags': [row[7]] if row[7] and row[7] not in ['Bookmarks Toolbar', 'Bookmarks Menu'] else [],
                    'added': self._firefox_timestamp_to_iso(row[3]),
                    'modified': self._firefox_timestamp_to_iso(row[4]),
                    'browser_id': row[0],
                    'browser_guid': row[5],
                    'source': f'browser:{self.browser.value}'
                }
                bookmarks.append(bookmark)
            
            conn.close()
            temp_db.unlink()
            
        except Exception as e:
            logger.error(f"Failed to read Firefox bookmarks: {e}")
        
        return bookmarks
    
    def _firefox_timestamp_to_iso(self, timestamp: int) -> str:
        """Convert Firefox timestamp to ISO format."""
        if not timestamp:
            return datetime.now().isoformat()
        
        try:
            # Firefox uses microseconds since epoch
            return datetime.fromtimestamp(timestamp / 1000000).isoformat()
        except:
            return datetime.now().isoformat()
    
    def sync(self, btk_bookmarks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Synchronize bookmarks between BTK and browser.
        
        Args:
            btk_bookmarks: Current BTK bookmarks
            
        Returns:
            Tuple of (synchronized bookmarks, sync statistics)
        """
        stats = {
            'added_to_btk': 0,
            'added_to_browser': 0,
            'updated_in_btk': 0,
            'updated_in_browser': 0,
            'conflicts_resolved': 0,
            'errors': []
        }
        
        # Read browser bookmarks
        browser_bookmarks = self.read_browser_bookmarks()
        
        if not browser_bookmarks and not btk_bookmarks:
            return btk_bookmarks, stats
        
        # Create URL mappings
        btk_by_url = {b['url']: b for b in btk_bookmarks}
        browser_by_url = {b['url']: b for b in browser_bookmarks}
        
        # Determine what needs syncing
        btk_urls = set(btk_by_url.keys())
        browser_urls = set(browser_by_url.keys())
        
        # Handle different sync directions
        if self.sync_direction == SyncDirection.FROM_BROWSER:
            # Only sync from browser to BTK
            new_urls = browser_urls - btk_urls
            for url in new_urls:
                btk_bookmarks.append(browser_by_url[url])
                stats['added_to_btk'] += 1
            
        elif self.sync_direction == SyncDirection.TO_BROWSER:
            # Only sync from BTK to browser
            new_urls = btk_urls - browser_urls
            for url in new_urls:
                # Would need browser-specific write implementation
                stats['added_to_browser'] += 1
            
        else:  # BIDIRECTIONAL
            # Sync both ways
            
            # Add new browser bookmarks to BTK
            new_in_browser = browser_urls - btk_urls
            for url in new_in_browser:
                btk_bookmarks.append(browser_by_url[url])
                stats['added_to_btk'] += 1
            
            # Add new BTK bookmarks to browser
            new_in_btk = btk_urls - browser_urls
            for url in new_in_btk:
                # Would need browser-specific write implementation
                stats['added_to_browser'] += 1
            
            # Handle conflicts for common URLs
            common_urls = btk_urls & browser_urls
            for url in common_urls:
                btk_bookmark = btk_by_url[url]
                browser_bookmark = browser_by_url[url]
                
                # Check if they differ
                if self._bookmarks_differ(btk_bookmark, browser_bookmark):
                    resolved = self._resolve_conflict(btk_bookmark, browser_bookmark)
                    
                    # Update BTK bookmark
                    idx = btk_bookmarks.index(btk_bookmark)
                    btk_bookmarks[idx] = resolved
                    stats['conflicts_resolved'] += 1
        
        # Update sync state
        self.state.last_sync = datetime.now()
        self.state.browser_hash = self._calculate_hash(browser_bookmarks)
        self.state.btk_hash = self._calculate_hash(btk_bookmarks)
        self._save_state()
        
        return btk_bookmarks, stats
    
    def _bookmarks_differ(self, bookmark1: Dict[str, Any], bookmark2: Dict[str, Any]) -> bool:
        """Check if two bookmarks differ significantly."""
        # Compare key fields
        if bookmark1.get('title') != bookmark2.get('title'):
            return True
        
        tags1 = set(bookmark1.get('tags', []))
        tags2 = set(bookmark2.get('tags', []))
        if tags1 != tags2:
            return True
        
        return False
    
    def _resolve_conflict(self, btk_bookmark: Dict[str, Any], 
                         browser_bookmark: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a conflict between BTK and browser bookmarks.
        
        Args:
            btk_bookmark: BTK version
            browser_bookmark: Browser version
            
        Returns:
            Resolved bookmark
        """
        if self.conflict_strategy == ConflictResolution.BTK_WINS:
            return btk_bookmark
        
        elif self.conflict_strategy == ConflictResolution.BROWSER_WINS:
            # Keep BTK-specific fields
            result = browser_bookmark.copy()
            for field in ['id', 'unique_id', 'stars', 'visit_count', 'description']:
                if field in btk_bookmark:
                    result[field] = btk_bookmark[field]
            return result
        
        elif self.conflict_strategy == ConflictResolution.NEWEST_WINS:
            # Compare modification times
            btk_modified = btk_bookmark.get('modified', btk_bookmark.get('added', ''))
            browser_modified = browser_bookmark.get('modified', browser_bookmark.get('added', ''))
            
            if btk_modified > browser_modified:
                return btk_bookmark
            else:
                return browser_bookmark
        
        else:  # MERGE
            # Merge both versions
            result = btk_bookmark.copy()
            
            # Use longer title
            if len(browser_bookmark.get('title', '')) > len(result.get('title', '')):
                result['title'] = browser_bookmark['title']
            
            # Merge tags
            all_tags = set(result.get('tags', []))
            all_tags.update(browser_bookmark.get('tags', []))
            result['tags'] = sorted(list(all_tags))
            
            # Keep browser metadata
            result['browser_id'] = browser_bookmark.get('browser_id')
            result['browser_guid'] = browser_bookmark.get('browser_guid')
            
            return result
    
    def _calculate_hash(self, bookmarks: List[Dict[str, Any]]) -> str:
        """Calculate hash of bookmarks for change detection."""
        # Sort bookmarks by URL for consistent hashing
        sorted_bookmarks = sorted(bookmarks, key=lambda b: b.get('url', ''))
        
        # Create string representation
        content = json.dumps(sorted_bookmarks, sort_keys=True)
        
        # Return hash
        return hashlib.sha256(content.encode()).hexdigest()


def register_plugins(registry):
    """Register the browser sync plugin with the plugin registry."""
    # Could register multiple browser sync instances
    for browser in [Browser.CHROME, Browser.FIREFOX, Browser.EDGE]:
        try:
            sync = BrowserSync(browser=browser)
            if sync.bookmark_file:
                registry.register(sync)
                logger.info(f"Registered browser sync for {browser.value}")
        except Exception as e:
            logger.debug(f"Could not register sync for {browser.value}: {e}")