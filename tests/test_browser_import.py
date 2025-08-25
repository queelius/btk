"""Tests for browser bookmark and history import."""

import pytest
import tempfile
import sqlite3
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import shutil

from btk.browser_import import (
    BrowserProfile, ChromeImporter, FirefoxImporter, SafariImporter,
    BrowserImportManager, find_browser_profiles, import_from_browser
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def chrome_profile(temp_dir):
    """Create a mock Chrome profile."""
    profile_path = Path(temp_dir) / "chrome_profile"
    profile_path.mkdir(parents=True)
    
    # Create bookmarks file
    bookmarks_data = {
        "roots": {
            "bookmark_bar": {
                "children": [
                    {
                        "type": "url",
                        "name": "Example",
                        "url": "https://example.com",
                        "date_added": "13350000000000000"
                    },
                    {
                        "type": "folder",
                        "name": "Work",
                        "children": [
                            {
                                "type": "url",
                                "name": "GitHub",
                                "url": "https://github.com",
                                "date_added": "13350000000000000"
                            }
                        ]
                    }
                ]
            }
        }
    }
    
    with open(profile_path / "Bookmarks", "w") as f:
        json.dump(bookmarks_data, f)
    
    # Create history database
    history_db = profile_path / "History"
    conn = sqlite3.connect(history_db)
    cursor = conn.cursor()
    
    # Create urls table
    cursor.execute("""
        CREATE TABLE urls (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            visit_count INTEGER,
            last_visit_time INTEGER
        )
    """)
    
    # Insert sample data
    cursor.execute("""
        INSERT INTO urls (url, title, visit_count, last_visit_time)
        VALUES (?, ?, ?, ?)
    """, ("https://python.org", "Python", 10, 13350000000000000))
    
    conn.commit()
    conn.close()
    
    return profile_path


@pytest.fixture
def firefox_profile(temp_dir):
    """Create a mock Firefox profile."""
    profile_path = Path(temp_dir) / "firefox_profile"
    profile_path.mkdir(parents=True)
    
    # Create places.sqlite database
    places_db = profile_path / "places.sqlite"
    conn = sqlite3.connect(places_db)
    cursor = conn.cursor()
    
    # Create moz_places table
    cursor.execute("""
        CREATE TABLE moz_places (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            visit_count INTEGER,
            last_visit_date INTEGER,
            hidden INTEGER DEFAULT 0
        )
    """)
    
    # Create moz_bookmarks table
    cursor.execute("""
        CREATE TABLE moz_bookmarks (
            id INTEGER PRIMARY KEY,
            type INTEGER,
            fk INTEGER,
            parent INTEGER,
            title TEXT,
            dateAdded INTEGER,
            lastModified INTEGER
        )
    """)
    
    # Insert sample data
    cursor.execute("""
        INSERT INTO moz_places (id, url, title, visit_count, last_visit_date)
        VALUES (1, 'https://mozilla.org', 'Mozilla', 5, 1700000000000000)
    """)
    
    cursor.execute("""
        INSERT INTO moz_bookmarks (type, fk, parent, title, dateAdded, lastModified)
        VALUES (1, 1, 0, 'Mozilla', 1700000000000000, 1700000000000000)
    """)
    
    conn.commit()
    conn.close()
    
    return profile_path


class TestChromeImporter:
    """Test Chrome importer functionality."""
    
    def test_import_bookmarks(self, chrome_profile):
        """Test importing bookmarks from Chrome."""
        importer = ChromeImporter()
        bookmarks = importer.import_bookmarks(chrome_profile)
        
        assert len(bookmarks) == 2
        
        # Check first bookmark
        assert bookmarks[0]['url'] == 'https://example.com'
        assert bookmarks[0]['title'] == 'Example'
        assert bookmarks[0]['source'] == 'chrome'
        
        # Check nested bookmark
        assert bookmarks[1]['url'] == 'https://github.com'
        assert bookmarks[1]['title'] == 'GitHub'
        # Tag should include the parent folder path
        assert any('Work' in tag for tag in bookmarks[1]['tags'])
    
    def test_import_history(self, chrome_profile):
        """Test importing history from Chrome."""
        importer = ChromeImporter()
        history = importer.import_history(chrome_profile)
        
        assert len(history) == 1
        assert history[0]['url'] == 'https://python.org'
        assert history[0]['title'] == 'Python'
        assert history[0]['visit_count'] == 10
        assert history[0]['source'] == 'chrome_history'
        assert 'chrome/history' in history[0]['tags']
    
    def test_chrome_timestamp_conversion(self):
        """Test Chrome timestamp conversion."""
        importer = ChromeImporter()
        
        # Chrome timestamp for Jan 1, 2024 00:00:00 UTC
        chrome_timestamp = 13350000000000000
        iso_date = importer._chrome_timestamp_to_datetime(chrome_timestamp)
        
        assert iso_date is not None
        assert '2024' in iso_date
    
    @patch('platform.system')
    def test_find_profiles_macos(self, mock_system, temp_dir):
        """Test finding Chrome profiles on macOS."""
        mock_system.return_value = 'Darwin'
        
        # Create mock Chrome directory structure
        chrome_dir = Path(temp_dir) / "Library/Application Support/Google/Chrome"
        default_profile = chrome_dir / "Default"
        profile1 = chrome_dir / "Profile 1"
        
        default_profile.mkdir(parents=True)
        profile1.mkdir(parents=True)
        
        with patch.object(Path, 'home', return_value=Path(temp_dir)):
            importer = ChromeImporter()
            profiles = importer.find_profiles()
        
        assert len(profiles) == 2
        assert any(p.name == "Default" and p.is_default for p in profiles)
        assert any(p.name == "Profile 1" for p in profiles)


class TestFirefoxImporter:
    """Test Firefox importer functionality."""
    
    def test_import_bookmarks(self, firefox_profile):
        """Test importing bookmarks from Firefox."""
        importer = FirefoxImporter()
        bookmarks = importer.import_bookmarks(firefox_profile)
        
        assert len(bookmarks) == 1
        assert bookmarks[0]['url'] == 'https://mozilla.org'
        assert bookmarks[0]['title'] == 'Mozilla'
        assert bookmarks[0]['source'] == 'firefox'
    
    def test_import_history(self, firefox_profile):
        """Test importing history from Firefox."""
        importer = FirefoxImporter()
        history = importer.import_history(firefox_profile)
        
        assert len(history) == 1
        assert history[0]['url'] == 'https://mozilla.org'
        assert history[0]['title'] == 'Mozilla'
        assert history[0]['visit_count'] == 5
        assert history[0]['source'] == 'firefox_history'
    
    def test_firefox_timestamp_conversion(self):
        """Test Firefox timestamp conversion."""
        importer = FirefoxImporter()
        
        # Firefox timestamp (microseconds since Unix epoch)
        firefox_timestamp = 1700000000000000
        iso_date = importer._firefox_timestamp_to_datetime(firefox_timestamp)
        
        assert iso_date is not None
        assert '2023' in iso_date  # November 2023
    
    @patch('platform.system')
    def test_find_profiles_linux(self, mock_system, temp_dir):
        """Test finding Firefox profiles on Linux."""
        mock_system.return_value = 'Linux'
        
        # Create mock Firefox directory structure
        firefox_dir = Path(temp_dir) / ".mozilla/firefox"
        default_profile = firefox_dir / "abc123.default-release"
        default_profile.mkdir(parents=True)
        
        with patch.object(Path, 'home', return_value=Path(temp_dir)):
            importer = FirefoxImporter()
            profiles = importer.find_profiles()
        
        assert len(profiles) == 1
        assert profiles[0].name == "abc123.default-release"
        assert profiles[0].is_default


class TestSafariImporter:
    """Test Safari importer functionality."""
    
    def test_safari_timestamp_conversion(self):
        """Test Safari timestamp conversion."""
        importer = SafariImporter()
        
        # Safari timestamp (seconds since 2001)
        safari_timestamp = 700000000.0  # Approximately March 2023
        iso_date = importer._safari_timestamp_to_datetime(safari_timestamp)
        
        assert iso_date is not None
        assert '2023' in iso_date
    
    @patch('platform.system')
    def test_find_profiles_macos(self, mock_system, temp_dir):
        """Test finding Safari profile on macOS."""
        mock_system.return_value = 'Darwin'
        
        # Create mock Safari directory
        safari_dir = Path(temp_dir) / "Library/Safari"
        safari_dir.mkdir(parents=True)
        
        with patch.object(Path, 'home', return_value=Path(temp_dir)):
            importer = SafariImporter()
            profiles = importer.find_profiles()
        
        assert len(profiles) == 1
        assert profiles[0].browser == "Safari"
        assert profiles[0].is_default
    
    @patch('platform.system')
    def test_no_profiles_on_non_macos(self, mock_system):
        """Test that Safari profiles are not found on non-macOS."""
        mock_system.return_value = 'Linux'
        
        importer = SafariImporter()
        profiles = importer.find_profiles()
        
        assert len(profiles) == 0


class TestBrowserImportManager:
    """Test BrowserImportManager functionality."""
    
    def test_import_browser_bookmarks(self, chrome_profile):
        """Test importing bookmarks through the manager."""
        manager = BrowserImportManager()
        bookmarks = manager.import_browser_bookmarks('chrome', chrome_profile)
        
        assert len(bookmarks) == 2
        assert bookmarks[0]['url'] == 'https://example.com'
    
    def test_import_browser_history(self, chrome_profile):
        """Test importing history through the manager."""
        manager = BrowserImportManager()
        history = manager.import_browser_history('chrome', chrome_profile, limit=10)
        
        assert len(history) == 1
        assert history[0]['url'] == 'https://python.org'
    
    def test_import_unknown_browser(self):
        """Test importing from unknown browser raises error."""
        manager = BrowserImportManager()
        
        with pytest.raises(ValueError, match="Unknown browser"):
            manager.import_browser_bookmarks('netscape', Path('/tmp'))
    
    @patch.object(ChromeImporter, 'find_profiles')
    @patch.object(FirefoxImporter, 'find_profiles')
    @patch.object(SafariImporter, 'find_profiles')
    def test_find_all_profiles(self, mock_safari, mock_firefox, mock_chrome):
        """Test finding all browser profiles."""
        mock_chrome.return_value = [
            BrowserProfile("Default", Path("/chrome"), "Chrome", True)
        ]
        mock_firefox.return_value = [
            BrowserProfile("default", Path("/firefox"), "Firefox", True)
        ]
        mock_safari.return_value = []
        
        manager = BrowserImportManager()
        profiles = manager.find_all_profiles()
        
        assert 'chrome' in profiles
        assert 'firefox' in profiles
        assert 'safari' not in profiles  # Empty list filtered out
        assert len(profiles['chrome']) == 1
        assert len(profiles['firefox']) == 1
    
    @patch.object(BrowserImportManager, 'find_all_profiles')
    @patch.object(BrowserImportManager, 'import_browser_bookmarks')
    @patch.object(BrowserImportManager, 'import_browser_history')
    def test_auto_import(self, mock_history, mock_bookmarks, mock_find):
        """Test auto-import from all browsers."""
        mock_find.return_value = {
            'chrome': [BrowserProfile("Default", Path("/chrome"), "Chrome", True)]
        }
        mock_bookmarks.return_value = [
            {'url': 'https://example.com', 'title': 'Example'}
        ]
        mock_history.return_value = [
            {'url': 'https://python.org', 'title': 'Python'}
        ]
        
        manager = BrowserImportManager()
        results = manager.auto_import(include_history=True, history_limit=100)
        
        assert 'Chrome_Default' in results
        assert len(results['Chrome_Default']) == 2  # 1 bookmark + 1 history


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @patch.object(BrowserImportManager, 'find_all_profiles')
    def test_find_browser_profiles(self, mock_find):
        """Test find_browser_profiles convenience function."""
        mock_find.return_value = {'chrome': []}
        
        profiles = find_browser_profiles()
        
        assert 'chrome' in profiles
        mock_find.assert_called_once()
    
    @patch.object(BrowserImportManager, 'find_all_profiles')
    @patch.object(BrowserImportManager, 'import_browser_bookmarks')
    def test_import_from_browser_with_default(self, mock_import, mock_find):
        """Test importing from browser with default profile."""
        mock_find.return_value = {
            'chrome': [
                BrowserProfile("Default", Path("/chrome"), "Chrome", True),
                BrowserProfile("Profile 1", Path("/chrome1"), "Chrome", False)
            ]
        }
        mock_import.return_value = []
        
        bookmarks = import_from_browser('chrome')
        
        # Should use default profile
        mock_import.assert_called_with('chrome', Path("/chrome"))
    
    @patch.object(BrowserImportManager, 'find_all_profiles')
    def test_import_from_browser_no_profile(self, mock_find):
        """Test importing from browser with no profiles raises error."""
        mock_find.return_value = {}
        
        with pytest.raises(ValueError, match="No chrome profile found"):
            import_from_browser('chrome')