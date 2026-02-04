"""
Browser bookmark and history import for BTK.

This module provides functionality to import bookmarks and browsing history
from popular web browsers including Chrome, Firefox, and Safari.
"""

import os
import json
import sqlite3
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass
import platform

from . import utils

logger = logging.getLogger(__name__)


@dataclass
class BrowserProfile:
    """Information about a browser profile."""
    name: str
    path: Path
    browser: str
    is_default: bool = False


class BrowserImporter:
    """Base class for browser importers."""
    
    def __init__(self):
        self.system = platform.system()
        
    def find_profiles(self) -> List[BrowserProfile]:
        """Find all browser profiles on the system."""
        raise NotImplementedError
    
    def import_bookmarks(self, profile_path: Path) -> List[Dict[str, Any]]:
        """Import bookmarks from a browser profile."""
        raise NotImplementedError
    
    def import_history(self, profile_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Import browsing history from a browser profile."""
        raise NotImplementedError
    
    def _copy_database(self, db_path: Path) -> Path:
        """
        Create a temporary copy of a database file.
        This is necessary because browsers may lock their databases.
        """
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        
        # Create temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.db')
        os.close(temp_fd)
        
        # Copy database
        shutil.copy2(db_path, temp_path)
        return Path(temp_path)
    
    def _chrome_timestamp_to_datetime(self, chrome_timestamp: int) -> str:
        """
        Convert Chrome timestamp (microseconds since 1601) to ISO datetime.
        """
        # Chrome epoch starts at 1601-01-01 00:00:00
        # Unix epoch starts at 1970-01-01 00:00:00
        # Difference in microseconds
        epoch_diff = 11644473600000000
        
        if chrome_timestamp:
            unix_timestamp = (chrome_timestamp - epoch_diff) / 1000000
            dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
            return dt.isoformat()
        return None
    
    def _firefox_timestamp_to_datetime(self, firefox_timestamp: int) -> str:
        """
        Convert Firefox timestamp (microseconds since Unix epoch) to ISO datetime.
        """
        if firefox_timestamp:
            unix_timestamp = firefox_timestamp / 1000000
            dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
            return dt.isoformat()
        return None
    
    def _safari_timestamp_to_datetime(self, safari_timestamp: float) -> str:
        """
        Convert Safari timestamp (seconds since 2001) to ISO datetime.
        """
        # Safari epoch starts at 2001-01-01 00:00:00
        # Unix epoch starts at 1970-01-01 00:00:00
        # Difference in seconds
        epoch_diff = 978307200
        
        if safari_timestamp:
            unix_timestamp = safari_timestamp + epoch_diff
            dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
            return dt.isoformat()
        return None


class ChromeImporter(BrowserImporter):
    """Import bookmarks and history from Chrome/Chromium browsers."""
    
    def find_profiles(self) -> List[BrowserProfile]:
        """Find all Chrome profiles on the system."""
        profiles = []
        
        # Determine Chrome config directory based on OS
        if self.system == "Darwin":  # macOS
            chrome_dirs = [
                Path.home() / "Library/Application Support/Google/Chrome",
                Path.home() / "Library/Application Support/Chromium",
                Path.home() / "Library/Application Support/Microsoft Edge",
                Path.home() / "Library/Application Support/Brave-Browser",
            ]
        elif self.system == "Linux":
            chrome_dirs = [
                Path.home() / ".config/google-chrome",
                Path.home() / ".config/chromium",
                Path.home() / ".config/microsoft-edge",
                Path.home() / ".config/BraveSoftware/Brave-Browser",
            ]
        elif self.system == "Windows":
            appdata = os.environ.get('LOCALAPPDATA', '')
            chrome_dirs = [
                Path(appdata) / "Google/Chrome/User Data",
                Path(appdata) / "Chromium/User Data",
                Path(appdata) / "Microsoft/Edge/User Data",
                Path(appdata) / "BraveSoftware/Brave-Browser/User Data",
            ]
        else:
            return profiles
        
        for chrome_dir in chrome_dirs:
            if not chrome_dir.exists():
                continue
            
            browser_name = self._get_browser_name(chrome_dir)
            
            # Check for Default profile
            default_profile = chrome_dir / "Default"
            if default_profile.exists():
                profiles.append(BrowserProfile(
                    name="Default",
                    path=default_profile,
                    browser=browser_name,
                    is_default=True
                ))
            
            # Check for numbered profiles (Profile 1, Profile 2, etc.)
            for profile_dir in chrome_dir.glob("Profile *"):
                if profile_dir.is_dir():
                    profiles.append(BrowserProfile(
                        name=profile_dir.name,
                        path=profile_dir,
                        browser=browser_name,
                        is_default=False
                    ))
        
        return profiles
    
    def _get_browser_name(self, chrome_dir: Path) -> str:
        """Determine browser name from directory path."""
        path_str = str(chrome_dir).lower()
        if "edge" in path_str:
            return "Microsoft Edge"
        elif "brave" in path_str:
            return "Brave"
        elif "chromium" in path_str:
            return "Chromium"
        else:
            return "Chrome"
    
    def import_bookmarks(self, profile_path: Path) -> List[Dict[str, Any]]:
        """Import bookmarks from Chrome profile."""
        bookmarks_file = profile_path / "Bookmarks"
        
        if not bookmarks_file.exists():
            logger.warning(f"No bookmarks file found at {bookmarks_file}")
            return []
        
        try:
            with open(bookmarks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read Chrome bookmarks: {e}")
            return []
        
        bookmarks = []
        
        # Process bookmark bar
        if 'roots' in data:
            for root_name, root_data in data['roots'].items():
                if isinstance(root_data, dict) and 'children' in root_data:
                    folder_name = root_data.get('name', root_name)
                    self._process_chrome_bookmark_folder(
                        root_data['children'], 
                        bookmarks, 
                        parent_folder=folder_name
                    )
        
        return bookmarks
    
    def _process_chrome_bookmark_folder(self, items: List[Dict], 
                                       bookmarks: List[Dict], 
                                       parent_folder: str = ""):
        """Recursively process Chrome bookmark folders."""
        for item in items:
            if item.get('type') == 'url':
                # It's a bookmark
                bookmark = {
                    'url': item.get('url', ''),
                    'title': item.get('name', ''),
                    'added': self._chrome_timestamp_to_datetime(
                        int(item.get('date_added', 0))
                    ),
                    'tags': [],
                    'description': '',
                    'source': 'chrome'
                }
                
                # Add folder as tag if present
                if parent_folder and parent_folder not in ['Bookmarks bar', 'Other bookmarks']:
                    bookmark['tags'].append(f"chrome/{parent_folder}")
                
                # Add Chrome-specific metadata
                if 'date_last_used' in item:
                    bookmark['last_visited'] = self._chrome_timestamp_to_datetime(
                        int(item['date_last_used'])
                    )
                
                bookmarks.append(bookmark)
                
            elif item.get('type') == 'folder' and 'children' in item:
                # It's a folder, recurse
                folder_name = item.get('name', '')
                if parent_folder and parent_folder not in ['Bookmarks bar', 'Other bookmarks']:
                    folder_name = f"{parent_folder}/{folder_name}"
                    
                self._process_chrome_bookmark_folder(
                    item['children'], 
                    bookmarks, 
                    parent_folder=folder_name
                )
    
    def import_history(self, profile_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Import browsing history from Chrome profile."""
        history_db = profile_path / "History"
        
        if not history_db.exists():
            logger.warning(f"No history database found at {history_db}")
            return []
        
        # Copy database to avoid lock issues
        temp_db = None
        try:
            temp_db = self._copy_database(history_db)
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # Query history
            query = """
                SELECT 
                    url,
                    title,
                    visit_count,
                    last_visit_time
                FROM urls
                ORDER BY last_visit_time DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            history = []
            for row in rows:
                url, title, visit_count, last_visit = row
                
                # Skip empty URLs
                if not url:
                    continue
                
                bookmark = {
                    'url': url,
                    'title': title or url,
                    'visit_count': visit_count,
                    'last_visited': self._chrome_timestamp_to_datetime(last_visit),
                    'tags': ['chrome/history'],
                    'source': 'chrome_history'
                }
                
                history.append(bookmark)
            
            conn.close()
            return history
            
        except Exception as e:
            logger.error(f"Failed to import Chrome history: {e}")
            return []
        finally:
            # Clean up temp file
            if temp_db and temp_db.exists():
                temp_db.unlink()


class FirefoxImporter(BrowserImporter):
    """Import bookmarks and history from Firefox."""
    
    def find_profiles(self) -> List[BrowserProfile]:
        """Find all Firefox profiles on the system."""
        profiles = []
        
        # Determine Firefox profile directory based on OS
        if self.system == "Darwin":  # macOS
            firefox_dir = Path.home() / "Library/Application Support/Firefox/Profiles"
        elif self.system == "Linux":
            firefox_dir = Path.home() / ".mozilla/firefox"
        elif self.system == "Windows":
            appdata = os.environ.get('APPDATA', '')
            firefox_dir = Path(appdata) / "Mozilla/Firefox/Profiles"
        else:
            return profiles
        
        if not firefox_dir.exists():
            return profiles
        
        # Find all profile directories
        for profile_dir in firefox_dir.glob("*.default*"):
            if profile_dir.is_dir():
                profiles.append(BrowserProfile(
                    name=profile_dir.name,
                    path=profile_dir,
                    browser="Firefox",
                    is_default="default-release" in profile_dir.name
                ))
        
        return profiles
    
    def import_bookmarks(self, profile_path: Path) -> List[Dict[str, Any]]:
        """Import bookmarks from Firefox profile."""
        places_db = profile_path / "places.sqlite"
        
        if not places_db.exists():
            logger.warning(f"No places database found at {places_db}")
            return []
        
        # Copy database to avoid lock issues
        temp_db = None
        try:
            temp_db = self._copy_database(places_db)
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # Query bookmarks
            query = """
                SELECT 
                    b.title,
                    p.url,
                    b.dateAdded,
                    b.lastModified,
                    GROUP_CONCAT(t.title, '/') as folders
                FROM moz_bookmarks b
                JOIN moz_places p ON b.fk = p.id
                LEFT JOIN moz_bookmarks t ON b.parent = t.id
                WHERE b.type = 1
                    AND p.url NOT LIKE 'place:%'
                    AND p.url NOT LIKE 'about:%'
                GROUP BY b.id
                ORDER BY b.dateAdded DESC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            bookmarks = []
            for row in rows:
                title, url, date_added, last_modified, folders = row
                
                # Skip empty URLs
                if not url:
                    continue
                
                bookmark = {
                    'url': url,
                    'title': title or url,
                    'added': self._firefox_timestamp_to_datetime(date_added),
                    'modified': self._firefox_timestamp_to_datetime(last_modified),
                    'tags': [],
                    'source': 'firefox'
                }
                
                # Add folder as tag if present
                if folders and folders not in ['bookmarks', 'menu', 'toolbar']:
                    bookmark['tags'].append(f"firefox/{folders}")
                
                bookmarks.append(bookmark)
            
            conn.close()
            return bookmarks
            
        except Exception as e:
            logger.error(f"Failed to import Firefox bookmarks: {e}")
            return []
        finally:
            # Clean up temp file
            if temp_db and temp_db.exists():
                temp_db.unlink()
    
    def import_history(self, profile_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Import browsing history from Firefox profile."""
        places_db = profile_path / "places.sqlite"
        
        if not places_db.exists():
            logger.warning(f"No places database found at {places_db}")
            return []
        
        # Copy database to avoid lock issues
        temp_db = None
        try:
            temp_db = self._copy_database(places_db)
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # Query history
            query = """
                SELECT 
                    url,
                    title,
                    visit_count,
                    last_visit_date
                FROM moz_places
                WHERE hidden = 0
                    AND url NOT LIKE 'place:%'
                    AND url NOT LIKE 'about:%'
                ORDER BY last_visit_date DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            history = []
            for row in rows:
                url, title, visit_count, last_visit = row
                
                # Skip empty URLs
                if not url:
                    continue
                
                bookmark = {
                    'url': url,
                    'title': title or url,
                    'visit_count': visit_count,
                    'last_visited': self._firefox_timestamp_to_datetime(last_visit),
                    'tags': ['firefox/history'],
                    'source': 'firefox_history'
                }
                
                history.append(bookmark)
            
            conn.close()
            return history
            
        except Exception as e:
            logger.error(f"Failed to import Firefox history: {e}")
            return []
        finally:
            # Clean up temp file
            if temp_db and temp_db.exists():
                temp_db.unlink()


class SafariImporter(BrowserImporter):
    """Import bookmarks and history from Safari (macOS only)."""
    
    def find_profiles(self) -> List[BrowserProfile]:
        """Find Safari profile (only one profile in Safari)."""
        if self.system != "Darwin":
            return []
        
        safari_dir = Path.home() / "Library/Safari"
        
        if safari_dir.exists():
            return [BrowserProfile(
                name="Default",
                path=safari_dir,
                browser="Safari",
                is_default=True
            )]
        
        return []
    
    def import_bookmarks(self, profile_path: Path) -> List[Dict[str, Any]]:
        """Import bookmarks from Safari."""
        bookmarks_plist = profile_path / "Bookmarks.plist"
        
        if not bookmarks_plist.exists():
            logger.warning(f"No bookmarks file found at {bookmarks_plist}")
            return []
        
        try:
            # Use plutil to convert plist to JSON
            import subprocess
            result = subprocess.run(
                ['plutil', '-convert', 'json', '-o', '-', str(bookmarks_plist)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to convert Safari bookmarks: {result.stderr}")
                return []
            
            data = json.loads(result.stdout)
            bookmarks = []
            
            # Process bookmark items
            if 'Children' in data:
                self._process_safari_bookmark_items(data['Children'], bookmarks)
            
            return bookmarks
            
        except Exception as e:
            logger.error(f"Failed to import Safari bookmarks: {e}")
            return []
    
    def _process_safari_bookmark_items(self, items: List[Dict], 
                                      bookmarks: List[Dict], 
                                      parent_folder: str = ""):
        """Recursively process Safari bookmark items."""
        for item in items:
            item_type = item.get('WebBookmarkType')
            
            if item_type == 'WebBookmarkTypeLeaf':
                # It's a bookmark
                url_dict = item.get('URLString')
                if url_dict:
                    bookmark = {
                        'url': url_dict,
                        'title': item.get('URIDictionary', {}).get('title', url_dict),
                        'tags': [],
                        'source': 'safari'
                    }
                    
                    # Add folder as tag if present
                    if parent_folder:
                        bookmark['tags'].append(f"safari/{parent_folder}")
                    
                    bookmarks.append(bookmark)
                    
            elif item_type == 'WebBookmarkTypeList' and 'Children' in item:
                # It's a folder, recurse
                folder_name = item.get('Title', '')
                if parent_folder:
                    folder_name = f"{parent_folder}/{folder_name}"
                    
                self._process_safari_bookmark_items(
                    item['Children'], 
                    bookmarks, 
                    parent_folder=folder_name
                )
    
    def import_history(self, profile_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Import browsing history from Safari."""
        history_db = profile_path / "History.db"
        
        if not history_db.exists():
            logger.warning(f"No history database found at {history_db}")
            return []
        
        # Copy database to avoid lock issues
        temp_db = None
        try:
            temp_db = self._copy_database(history_db)
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # Query history
            query = """
                SELECT 
                    hi.url,
                    hi.title,
                    hi.visit_count,
                    hv.visit_time
                FROM history_items hi
                JOIN history_visits hv ON hi.id = hv.history_item
                GROUP BY hi.id
                ORDER BY hv.visit_time DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            history = []
            for row in rows:
                url, title, visit_count, visit_time = row
                
                # Skip empty URLs
                if not url:
                    continue
                
                bookmark = {
                    'url': url,
                    'title': title or url,
                    'visit_count': visit_count,
                    'last_visited': self._safari_timestamp_to_datetime(visit_time),
                    'tags': ['safari/history'],
                    'source': 'safari_history'
                }
                
                history.append(bookmark)
            
            conn.close()
            return history
            
        except Exception as e:
            logger.error(f"Failed to import Safari history: {e}")
            return []
        finally:
            # Clean up temp file
            if temp_db and temp_db.exists():
                temp_db.unlink()


class BrowserImportManager:
    """Manages browser import operations."""
    
    def __init__(self):
        self.chrome_importer = ChromeImporter()
        self.firefox_importer = FirefoxImporter()
        self.safari_importer = SafariImporter()
    
    def find_all_profiles(self) -> Dict[str, List[BrowserProfile]]:
        """Find all browser profiles on the system."""
        profiles = {
            'chrome': self.chrome_importer.find_profiles(),
            'firefox': self.firefox_importer.find_profiles(),
            'safari': self.safari_importer.find_profiles()
        }
        
        # Filter out empty lists
        return {k: v for k, v in profiles.items() if v}
    
    def import_browser_bookmarks(self, browser: str, profile_path: Path) -> List[Dict[str, Any]]:
        """
        Import bookmarks from a specific browser profile.
        
        Args:
            browser: Browser type ('chrome', 'firefox', 'safari')
            profile_path: Path to browser profile
            
        Returns:
            List of bookmark dictionaries
        """
        if browser.lower() in ['chrome', 'chromium', 'edge', 'brave']:
            return self.chrome_importer.import_bookmarks(profile_path)
        elif browser.lower() == 'firefox':
            return self.firefox_importer.import_bookmarks(profile_path)
        elif browser.lower() == 'safari':
            return self.safari_importer.import_bookmarks(profile_path)
        else:
            raise ValueError(f"Unknown browser: {browser}")
    
    def import_browser_history(self, browser: str, profile_path: Path, 
                             limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Import browsing history from a specific browser profile.
        
        Args:
            browser: Browser type ('chrome', 'firefox', 'safari')
            profile_path: Path to browser profile
            limit: Maximum number of history items to import
            
        Returns:
            List of bookmark dictionaries
        """
        if browser.lower() in ['chrome', 'chromium', 'edge', 'brave']:
            return self.chrome_importer.import_history(profile_path, limit)
        elif browser.lower() == 'firefox':
            return self.firefox_importer.import_history(profile_path, limit)
        elif browser.lower() == 'safari':
            return self.safari_importer.import_history(profile_path, limit)
        else:
            raise ValueError(f"Unknown browser: {browser}")
    
    def auto_import(self, include_history: bool = False, 
                   history_limit: int = 1000) -> Dict[str, List[Dict[str, Any]]]:
        """
        Automatically import bookmarks (and optionally history) from all detected browsers.
        
        Args:
            include_history: Whether to import browsing history
            history_limit: Maximum history items per browser
            
        Returns:
            Dictionary mapping browser names to bookmark lists
        """
        results = {}
        all_profiles = self.find_all_profiles()
        
        for browser_type, profiles in all_profiles.items():
            for profile in profiles:
                key = f"{profile.browser}_{profile.name}"
                
                # Import bookmarks
                bookmarks = self.import_browser_bookmarks(
                    profile.browser.lower().split()[0],  # Get first word (e.g., "Microsoft Edge" -> "microsoft")
                    profile.path
                )
                
                # Import history if requested
                if include_history:
                    history = self.import_browser_history(
                        profile.browser.lower().split()[0],
                        profile.path,
                        history_limit
                    )
                    bookmarks.extend(history)
                
                if bookmarks:
                    results[key] = bookmarks
                    logger.info(f"Imported {len(bookmarks)} items from {key}")
        
        return results


# High-level API functions
def find_browser_profiles() -> Dict[str, List[BrowserProfile]]:
    """Find all browser profiles on the system."""
    manager = BrowserImportManager()
    return manager.find_all_profiles()


def import_browser_bookmarks_to_library(lib_dir: str, browser: str = 'all',
                                       profile_path: Optional[str] = None,
                                       include_history: bool = False,
                                       history_limit: int = 1000) -> Dict[str, Any]:
    """
    Import browser bookmarks directly into a BTK library.
    
    This is the main API function that handles the complete import process,
    including deduplication and saving to the library.
    
    Args:
        lib_dir: Directory of the BTK library
        browser: Browser name or 'all' for all browsers
        profile_path: Optional path to specific browser profile
        include_history: Whether to include browsing history
        history_limit: Maximum history items to import
        
    Returns:
        Dictionary with import statistics
    """
    # Ensure library directory exists
    utils.ensure_dir(lib_dir)
    utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
    
    # Load existing bookmarks
    existing_bookmarks = utils.load_bookmarks(lib_dir)
    existing_urls = {b.get('url') for b in existing_bookmarks}
    
    manager = BrowserImportManager()
    stats = {
        'total_imported': 0,
        'duplicates_skipped': 0,
        'browsers': {}
    }
    
    if browser == 'all':
        # Auto-import from all detected browsers
        results = manager.auto_import(include_history, history_limit)
        
        for browser_profile, imported in results.items():
            # Process imported bookmarks
            new_bookmarks = []
            next_id = utils.get_next_id(existing_bookmarks)
            
            for bookmark in imported:
                # Add unique_id if missing
                if 'unique_id' not in bookmark:
                    bookmark['unique_id'] = utils.generate_unique_id(
                        bookmark.get('url'), bookmark.get('title')
                    )
                
                # Check for duplicates
                if bookmark.get('url') not in existing_urls:
                    # Add ID if missing
                    if 'id' not in bookmark:
                        bookmark['id'] = next_id
                        next_id += 1
                    
                    new_bookmarks.append(bookmark)
                    existing_urls.add(bookmark.get('url'))
                else:
                    stats['duplicates_skipped'] += 1
            
            # Add to existing bookmarks
            existing_bookmarks.extend(new_bookmarks)
            
            # Update stats
            stats['browsers'][browser_profile] = {
                'found': len(imported),
                'imported': len(new_bookmarks)
            }
            stats['total_imported'] += len(new_bookmarks)
    
    else:
        # Import from specific browser
        if profile_path is None:
            # Find default profile
            profiles = manager.find_all_profiles().get(browser.lower(), [])
            default_profile = next((p for p in profiles if p.is_default), None)
            if default_profile:
                profile_path = default_profile.path
            elif profiles:
                profile_path = profiles[0].path
            else:
                raise ValueError(f"No {browser} profile found")
        else:
            # Check if it's a profile name or a full path
            profile_path_obj = Path(profile_path)
            
            # If it's not an absolute path or doesn't exist, try to find it as a profile name
            if not profile_path_obj.is_absolute() or not profile_path_obj.exists():
                # Try to find a profile with this name
                profiles = manager.find_all_profiles().get(browser.lower(), [])
                
                # Look for exact profile name match (case-insensitive)
                matching_profile = next(
                    (p for p in profiles if p.name.lower() == profile_path.lower()),
                    None
                )
                
                if matching_profile:
                    profile_path = matching_profile.path
                else:
                    # If no match found and path doesn't exist, show helpful error
                    available_profiles = [p.name for p in profiles] if profiles else []
                    if available_profiles:
                        raise ValueError(
                            f"Profile '{profile_path}' not found for {browser}. "
                            f"Available profiles: {', '.join(available_profiles)}"
                        )
                    else:
                        raise ValueError(f"No {browser} profiles found on this system")
            else:
                profile_path = profile_path_obj
        
        # Import bookmarks
        imported = manager.import_browser_bookmarks(browser, profile_path)
        
        # Import history if requested
        if include_history:
            history = manager.import_browser_history(browser, profile_path, history_limit)
            imported.extend(history)
        
        # Process imported bookmarks
        new_bookmarks = []
        next_id = utils.get_next_id(existing_bookmarks)
        
        for bookmark in imported:
            # Add unique_id if missing
            if 'unique_id' not in bookmark:
                bookmark['unique_id'] = utils.generate_unique_id(
                    bookmark.get('url'), bookmark.get('title')
                )
            
            # Check for duplicates
            if bookmark.get('url') not in existing_urls:
                # Add ID if missing
                if 'id' not in bookmark:
                    bookmark['id'] = next_id
                    next_id += 1
                
                new_bookmarks.append(bookmark)
                existing_urls.add(bookmark.get('url'))
            else:
                stats['duplicates_skipped'] += 1
        
        # Add to existing bookmarks
        existing_bookmarks.extend(new_bookmarks)
        
        # Update stats
        stats['browsers'][browser] = {
            'found': len(imported),
            'imported': len(new_bookmarks)
        }
        stats['total_imported'] = len(new_bookmarks)
    
    # Save bookmarks if any were imported
    if stats['total_imported'] > 0:
        utils.save_bookmarks(existing_bookmarks, None, lib_dir)
    
    return stats


def list_browser_profiles() -> List[Dict[str, Any]]:
    """
    Get a list of all detected browser profiles in a structured format.
    
    Returns:
        List of profile information dictionaries
    """
    manager = BrowserImportManager()
    all_profiles = manager.find_all_profiles()
    
    profile_list = []
    for browser_type, profiles in all_profiles.items():
        for profile in profiles:
            profile_list.append({
                'browser': profile.browser,
                'profile_name': profile.name,
                'path': str(profile.path),
                'is_default': profile.is_default
            })
    
    return profile_list


# Lower-level convenience functions (for direct use if needed)
def import_from_browser(browser: str, profile_path: Optional[str] = None,
                       include_history: bool = False,
                       history_limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Import bookmarks and optionally history from a browser.
    
    This is a lower-level function that returns raw bookmark data
    without saving to a library.
    
    Args:
        browser: Browser name ('chrome', 'firefox', 'safari')
        profile_path: Optional path to specific profile
        include_history: Whether to include browsing history
        history_limit: Maximum history items to import
        
    Returns:
        List of imported bookmarks
    """
    manager = BrowserImportManager()
    
    # If no profile path specified, try to find default profile
    if profile_path is None:
        profiles = manager.find_all_profiles().get(browser.lower(), [])
        default_profile = next((p for p in profiles if p.is_default), None)
        if default_profile:
            profile_path = default_profile.path
        elif profiles:
            profile_path = profiles[0].path
        else:
            raise ValueError(f"No {browser} profile found")
    else:
        profile_path = Path(profile_path)
    
    # Import bookmarks
    bookmarks = manager.import_browser_bookmarks(browser, profile_path)
    
    # Import history if requested
    if include_history:
        history = manager.import_browser_history(browser, profile_path, history_limit)
        bookmarks.extend(history)
    
    return bookmarks


def auto_import_all_browsers(include_history: bool = False,
                            history_limit: int = 1000) -> Dict[str, List[Dict[str, Any]]]:
    """
    Automatically import from all detected browsers.
    
    This is a lower-level function that returns raw bookmark data
    without saving to a library.
    
    Args:
        include_history: Whether to include browsing history
        history_limit: Maximum history items per browser
        
    Returns:
        Dictionary mapping browser profile names to bookmark lists
    """
    manager = BrowserImportManager()
    return manager.auto_import(include_history, history_limit)