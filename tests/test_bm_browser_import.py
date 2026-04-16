"""Tests for bookmark_memex browser importer (Chrome and Firefox)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bookmark_memex.db import Database
from bookmark_memex.importers.browser import (
    BrowserProfile,
    ChromeImporter,
    FirefoxImporter,
    import_browser_bookmarks,
    list_browser_profiles,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chrome_bookmarks(children: list[dict]) -> dict:
    """Wrap *children* in the minimal Chrome Bookmarks JSON envelope."""
    return {
        "roots": {
            "bookmark_bar": {
                "name": "Bookmarks bar",
                "type": "folder",
                "children": children,
            },
            "other": {
                "name": "Other bookmarks",
                "type": "folder",
                "children": [],
            },
        }
    }


def _url_node(name: str, url: str, date_added: str = "13345000000000000") -> dict:
    return {"type": "url", "name": name, "url": url, "date_added": date_added}


def _folder_node(name: str, children: list[dict]) -> dict:
    return {"type": "folder", "name": name, "children": children}


# ---------------------------------------------------------------------------
# ChromeImporter — unit tests (no real Chrome required)
# ---------------------------------------------------------------------------


class TestChromeImporterBookmarks:
    def test_flat_bookmarks_returned(self, tmp_path: Path) -> None:
        """Two top-level URL nodes are returned as two dicts."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks(
            [
                _url_node("Example", "https://example.com"),
                _url_node("Python", "https://python.org"),
            ]
        )
        (profile / "Bookmarks").write_text(json.dumps(data))

        importer = ChromeImporter()
        results = importer.import_bookmarks(profile)

        assert len(results) == 2
        urls = {r["url"] for r in results}
        assert "https://example.com" in urls
        assert "https://python.org" in urls

    def test_nested_folder_tag(self, tmp_path: Path) -> None:
        """URLs inside a named folder get a chrome/<folder> tag."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks(
            [
                _folder_node(
                    "Dev",
                    [_url_node("GitHub", "https://github.com")],
                )
            ]
        )
        (profile / "Bookmarks").write_text(json.dumps(data))

        importer = ChromeImporter()
        results = importer.import_bookmarks(profile)

        assert len(results) == 1
        gh = results[0]
        assert gh["url"] == "https://github.com"
        assert any("Dev" in t for t in gh["tags"])

    def test_deeply_nested_folder_path(self, tmp_path: Path) -> None:
        """Deeply nested folders produce a compound folder_path."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks(
            [
                _folder_node(
                    "Outer",
                    [
                        _folder_node(
                            "Inner",
                            [_url_node("Site", "https://site.example.com")],
                        )
                    ],
                )
            ]
        )
        (profile / "Bookmarks").write_text(json.dumps(data))

        importer = ChromeImporter()
        results = importer.import_bookmarks(profile)

        assert len(results) == 1
        assert "Outer" in results[0]["folder_path"]
        assert "Inner" in results[0]["folder_path"]

    def test_missing_bookmarks_file_returns_empty(self, tmp_path: Path) -> None:
        """A profile directory without a Bookmarks file returns []."""
        profile = tmp_path / "Default"
        profile.mkdir()

        importer = ChromeImporter()
        results = importer.import_bookmarks(profile)

        assert results == []

    def test_top_level_url_no_folder_tag(self, tmp_path: Path) -> None:
        """URLs directly under Bookmarks bar get no chrome/ tag."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks([_url_node("Root", "https://root.example.com")])
        (profile / "Bookmarks").write_text(json.dumps(data))

        importer = ChromeImporter()
        results = importer.import_bookmarks(profile)

        assert len(results) == 1
        # No chrome/ tag for direct children of Bookmarks bar
        assert results[0]["tags"] == []

    def test_chrome_timestamp_conversion(self) -> None:
        """Chrome epoch timestamp converts to a reasonable ISO date string."""
        importer = ChromeImporter()
        # A known Chrome timestamp: 13345000000000000 µs
        dt_str = importer._chrome_timestamp_to_datetime(13345000000000000)
        assert dt_str is not None
        assert "2023" in dt_str or "2024" in dt_str or "2022" in dt_str  # rough sanity

    def test_zero_timestamp_returns_none(self) -> None:
        """Chrome timestamp of 0 returns None."""
        importer = ChromeImporter()
        assert importer._chrome_timestamp_to_datetime(0) is None


# ---------------------------------------------------------------------------
# ChromeImporter — integration with Database
# ---------------------------------------------------------------------------


class TestChromeImporterDatabase:
    def test_import_to_database(self, tmp_db_path: str, tmp_path: Path) -> None:
        """Fake Chrome bookmarks land in a real Database."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks(
            [_url_node("Test", "https://test.example.com")]
        )
        (profile / "Bookmarks").write_text(json.dumps(data))

        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default",
            path=profile,
            browser="Chrome",
            is_default=True,
        )

        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            count = import_browser_bookmarks(db, browser="chrome")

        assert count == 1
        bookmarks = db.list()
        assert len(bookmarks) == 1
        assert "test.example.com" in bookmarks[0].url

    def test_duplicate_url_not_double_counted(self, tmp_db_path: str, tmp_path: Path) -> None:
        """Importing the same URL twice does not add a second row."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks(
            [
                _url_node("Dup A", "https://dup.example.com"),
                _url_node("Dup B", "https://dup.example.com"),
            ]
        )
        (profile / "Bookmarks").write_text(json.dumps(data))

        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )

        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            count = import_browser_bookmarks(db, browser="chrome")

        # Importer counts each raw entry; DB deduplicates on unique_id
        assert len(db.list()) == 1

    def test_source_type_stored(self, tmp_db_path: str, tmp_path: Path) -> None:
        """Imported bookmark carries source_type='chrome'."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks([_url_node("X", "https://src.example.com")])
        (profile / "Bookmarks").write_text(json.dumps(data))

        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )

        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            import_browser_bookmarks(db, browser="chrome")

        bm = db.list()[0]
        assert any(s.source_type == "chrome" for s in bm.sources)

    def test_folder_tag_stored_in_db(self, tmp_db_path: str, tmp_path: Path) -> None:
        """Folder-derived tags are persisted on the bookmark."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks(
            [
                _folder_node(
                    "Research",
                    [_url_node("ArXiv", "https://arxiv.org")],
                )
            ]
        )
        (profile / "Bookmarks").write_text(json.dumps(data))

        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )

        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            import_browser_bookmarks(db, browser="chrome")

        bm = db.list()[0]
        tag_names = {t.name for t in bm.tags}
        assert any("Research" in t for t in tag_names)

    def test_no_profiles_raises(self, tmp_db_path: str) -> None:
        """ValueError is raised when no browser profiles are found."""
        db = Database(tmp_db_path)
        with patch.object(ChromeImporter, "find_profiles", return_value=[]):
            with pytest.raises(ValueError, match="No chrome profiles"):
                import_browser_bookmarks(db, browser="chrome")

    def test_unknown_profile_name_raises(self, tmp_db_path: str, tmp_path: Path) -> None:
        """Requesting a non-existent profile name raises ValueError."""
        fake_profile = BrowserProfile(
            name="Default",
            path=tmp_path / "Default",
            browser="Chrome",
            is_default=True,
        )
        db = Database(tmp_db_path)
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            with pytest.raises(ValueError, match="not found"):
                import_browser_bookmarks(db, browser="chrome", profile="NonExistent")

    def test_unsupported_browser_raises(self, tmp_db_path: str) -> None:
        """Unsupported browser string raises ValueError immediately."""
        db = Database(tmp_db_path)
        with pytest.raises(ValueError, match="Unsupported browser"):
            import_browser_bookmarks(db, browser="safari")


# ---------------------------------------------------------------------------
# FirefoxImporter — unit tests (fake SQLite places.sqlite)
# ---------------------------------------------------------------------------


def _make_places_db(tmp_path: Path) -> Path:
    """Create a minimal places.sqlite in *tmp_path* and return its path."""
    db_path = tmp_path / "places.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE moz_places (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            visit_count INTEGER DEFAULT 0,
            last_visit_date INTEGER,
            hidden INTEGER DEFAULT 0
        );
        CREATE TABLE moz_bookmarks (
            id INTEGER PRIMARY KEY,
            type INTEGER,
            fk INTEGER,
            parent INTEGER,
            title TEXT,
            dateAdded INTEGER,
            lastModified INTEGER
        );
        """
    )
    conn.commit()
    conn.close()
    return db_path


class TestFirefoxImporterBookmarks:
    def test_empty_places_returns_empty(self, tmp_path: Path) -> None:
        """An empty places.sqlite returns []."""
        profile = tmp_path / "abc.default-release"
        profile.mkdir()
        _make_places_db(profile)

        importer = FirefoxImporter()
        results = importer.import_bookmarks(profile)
        assert results == []

    def test_missing_places_returns_empty(self, tmp_path: Path) -> None:
        """A profile without places.sqlite returns []."""
        profile = tmp_path / "abc.default-release"
        profile.mkdir()

        importer = FirefoxImporter()
        results = importer.import_bookmarks(profile)
        assert results == []

    def test_firefox_timestamp_conversion(self) -> None:
        """Firefox µs epoch converts to a non-None ISO string."""
        importer = FirefoxImporter()
        # 1_700_000_000_000_000 µs ~ 2023-11-14
        dt = importer._firefox_timestamp_to_datetime(1_700_000_000_000_000)
        assert dt is not None
        assert "2023" in dt

    def test_zero_timestamp_returns_none(self) -> None:
        importer = FirefoxImporter()
        assert importer._firefox_timestamp_to_datetime(0) is None


# ---------------------------------------------------------------------------
# list_browser_profiles
# ---------------------------------------------------------------------------


class TestListBrowserProfiles:
    def test_returns_list(self) -> None:
        """list_browser_profiles returns a list (possibly empty on CI)."""
        result = list_browser_profiles()
        assert isinstance(result, list)

    def test_filter_by_browser(self) -> None:
        """Filtering by browser returns only that browser's entries."""
        chrome_profiles = [
            BrowserProfile(
                name="Default", path=Path("/fake"), browser="Chrome", is_default=True
            )
        ]
        firefox_profiles = [
            BrowserProfile(
                name="abc.default-release",
                path=Path("/fake2"),
                browser="Firefox",
                is_default=True,
            )
        ]

        with (
            patch.object(ChromeImporter, "find_profiles", return_value=chrome_profiles),
            patch.object(FirefoxImporter, "find_profiles", return_value=firefox_profiles),
        ):
            result = list_browser_profiles("chrome")

        assert len(result) == 1
        assert result[0]["browser"] == "Chrome"

    def test_all_browsers_when_no_filter(self) -> None:
        """Without a filter, profiles from all browsers are returned."""
        chrome_profiles = [
            BrowserProfile(
                name="Default", path=Path("/fake"), browser="Chrome", is_default=True
            )
        ]
        firefox_profiles = [
            BrowserProfile(
                name="abc.default-release",
                path=Path("/fake2"),
                browser="Firefox",
                is_default=True,
            )
        ]

        with (
            patch.object(ChromeImporter, "find_profiles", return_value=chrome_profiles),
            patch.object(FirefoxImporter, "find_profiles", return_value=firefox_profiles),
        ):
            result = list_browser_profiles()

        assert len(result) == 2
        browsers = {r["browser"] for r in result}
        assert "Chrome" in browsers
        assert "Firefox" in browsers

    def test_dict_keys_present(self) -> None:
        """Each profile dict has the expected keys."""
        fake = [
            BrowserProfile(
                name="Default", path=Path("/fake"), browser="Chrome", is_default=True
            )
        ]
        with patch.object(ChromeImporter, "find_profiles", return_value=fake):
            with patch.object(FirefoxImporter, "find_profiles", return_value=[]):
                result = list_browser_profiles()

        assert len(result) == 1
        p = result[0]
        assert set(p.keys()) >= {"browser", "name", "path", "is_default"}


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIImportBrowser:
    def test_list_flag_prints_profiles(self, tmp_db_path: str, capsys) -> None:
        """--list flag prints profile info without importing."""
        fake = [
            BrowserProfile(
                name="Default",
                path=Path("/fake/Default"),
                browser="Chrome",
                is_default=True,
            )
        ]
        with (
            patch.object(ChromeImporter, "find_profiles", return_value=fake),
            patch.object(FirefoxImporter, "find_profiles", return_value=[]),
        ):
            from bookmark_memex.cli import cmd_import_browser
            from argparse import Namespace

            args = Namespace(
                db=tmp_db_path,
                browser=None,
                profile=None,
                list_profiles=True,
            )
            cmd_import_browser(args)

        out = capsys.readouterr().out
        assert "Chrome" in out
        assert "Default" in out

    def test_import_command_returns_count(
        self, tmp_db_path: str, tmp_path: Path, capsys
    ) -> None:
        """import-browser prints imported count."""
        profile = tmp_path / "Default"
        profile.mkdir()
        data = _make_chrome_bookmarks([_url_node("X", "https://cli-test.example.com")])
        (profile / "Bookmarks").write_text(json.dumps(data))

        fake = [
            BrowserProfile(
                name="Default", path=profile, browser="Chrome", is_default=True
            )
        ]
        with patch.object(ChromeImporter, "find_profiles", return_value=fake):
            from bookmark_memex.cli import cmd_import_browser
            from argparse import Namespace

            args = Namespace(
                db=tmp_db_path,
                browser="chrome",
                profile=None,
                list_profiles=False,
            )
            cmd_import_browser(args)

        out = capsys.readouterr().out
        assert "1" in out
        assert "chrome" in out.lower()
