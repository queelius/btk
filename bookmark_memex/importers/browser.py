"""Browser bookmark importer for bookmark-memex.

Supports Chrome/Chromium-family and Firefox browsers.
Provides two public functions:

    import_browser_bookmarks(db, browser, profile) -> ImportResult
    list_browser_profiles(browser)                  -> list[dict]

The lower-level ChromeImporter and FirefoxImporter classes are also public
so they can be tested directly against fake filesystem fixtures.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple, Optional

from bookmark_memex.db import Database, generate_unique_id
from bookmark_memex.detectors import run_detectors

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class BrowserProfile:
    """Metadata about a single browser profile on disk."""

    name: str
    path: Path
    browser: str
    is_default: bool = False


class ImportResult(NamedTuple):
    """Counts from a single :func:`import_browser_bookmarks` call.

    ``processed`` is the number of raw browser entries with an http(s) URL.
    ``added`` is the number of new bookmark rows created. ``merged`` is the
    number of existing bookmark rows that were touched (new source row,
    extra tags, title backfill). ``processed == added + merged`` when every
    raw entry had a valid URL.
    """

    processed: int
    added: int
    merged: int


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class BrowserImporter:
    """Base class for browser-specific importers."""

    def __init__(self) -> None:
        self.system = platform.system()

    def find_profiles(self) -> list[BrowserProfile]:
        """Return all detectable profiles for this browser."""
        raise NotImplementedError

    def import_bookmarks(self, profile_path: Path) -> list[dict[str, Any]]:
        """Return raw bookmark dicts from *profile_path*."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _copy_database(self, db_path: Path) -> Path:
        """Copy a (possibly locked) SQLite database to a temp file."""
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
        os.close(temp_fd)
        shutil.copy2(db_path, temp_path)
        return Path(temp_path)

    def _chrome_timestamp_to_datetime(self, chrome_timestamp: int) -> Optional[str]:
        """Convert Chrome microseconds-since-1601 to ISO 8601 UTC string."""
        epoch_diff = 11644473600000000  # µs between 1601-01-01 and 1970-01-01
        if chrome_timestamp:
            unix_ts = (chrome_timestamp - epoch_diff) / 1_000_000
            return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
        return None

    def _firefox_timestamp_to_datetime(self, firefox_timestamp: int) -> Optional[str]:
        """Convert Firefox microseconds-since-Unix-epoch to ISO 8601 UTC string."""
        if firefox_timestamp:
            unix_ts = firefox_timestamp / 1_000_000
            return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
        return None


# ---------------------------------------------------------------------------
# Chrome / Chromium-family
# ---------------------------------------------------------------------------


class ChromeImporter(BrowserImporter):
    """Import bookmarks from Chrome, Chromium, Edge, or Brave."""

    def find_profiles(self) -> list[BrowserProfile]:
        """Return all detected Chromium-family profiles on the current OS."""
        profiles: list[BrowserProfile] = []

        if self.system == "Darwin":
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
            appdata = os.environ.get("LOCALAPPDATA", "")
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
            browser_name = self._browser_name(chrome_dir)

            default_dir = chrome_dir / "Default"
            if default_dir.exists():
                profiles.append(
                    BrowserProfile(
                        name="Default",
                        path=default_dir,
                        browser=browser_name,
                        is_default=True,
                    )
                )

            for profile_dir in chrome_dir.glob("Profile *"):
                if profile_dir.is_dir():
                    profiles.append(
                        BrowserProfile(
                            name=profile_dir.name,
                            path=profile_dir,
                            browser=browser_name,
                            is_default=False,
                        )
                    )

        return profiles

    def _browser_name(self, chrome_dir: Path) -> str:
        path_lower = str(chrome_dir).lower()
        if "edge" in path_lower:
            return "Microsoft Edge"
        if "brave" in path_lower:
            return "Brave"
        if "chromium" in path_lower:
            return "Chromium"
        return "Chrome"

    def import_bookmarks(self, profile_path: Path) -> list[dict[str, Any]]:
        """Parse the Chrome JSON Bookmarks file and return bookmark dicts."""
        bookmarks_file = profile_path / "Bookmarks"
        if not bookmarks_file.exists():
            logger.warning("No Bookmarks file at %s", bookmarks_file)
            return []

        try:
            data = json.loads(bookmarks_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to read Chrome Bookmarks: %s", exc)
            return []

        bookmarks: list[dict[str, Any]] = []
        if "roots" in data:
            for root_name, root_data in data["roots"].items():
                if isinstance(root_data, dict) and "children" in root_data:
                    folder_name = root_data.get("name", root_name)
                    self._walk(root_data["children"], bookmarks, folder_name)

        return bookmarks

    def _walk(
        self,
        items: list[dict],
        bookmarks: list[dict[str, Any]],
        parent_folder: str = "",
    ) -> None:
        for item in items:
            if item.get("type") == "url":
                bookmark: dict[str, Any] = {
                    "url": item.get("url", ""),
                    "title": item.get("name", ""),
                    "added": self._chrome_timestamp_to_datetime(
                        int(item.get("date_added", 0))
                    ),
                    "tags": [],
                    "description": "",
                    "source": "chrome",
                    "folder_path": parent_folder or None,
                }
                if parent_folder and parent_folder not in (
                    "Bookmarks bar",
                    "Other bookmarks",
                ):
                    bookmark["tags"].append(f"chrome/{parent_folder}")
                if "date_last_used" in item:
                    bookmark["last_visited"] = self._chrome_timestamp_to_datetime(
                        int(item["date_last_used"])
                    )
                bookmarks.append(bookmark)

            elif item.get("type") == "folder" and "children" in item:
                folder_name = item.get("name", "")
                if parent_folder and parent_folder not in (
                    "Bookmarks bar",
                    "Other bookmarks",
                ):
                    folder_name = f"{parent_folder}/{folder_name}"
                self._walk(item["children"], bookmarks, folder_name)


# ---------------------------------------------------------------------------
# Firefox
# ---------------------------------------------------------------------------


class FirefoxImporter(BrowserImporter):
    """Import bookmarks from Firefox."""

    def find_profiles(self) -> list[BrowserProfile]:
        """Return all detected Firefox profiles on the current OS."""
        profiles: list[BrowserProfile] = []

        if self.system == "Darwin":
            firefox_dir = Path.home() / "Library/Application Support/Firefox/Profiles"
        elif self.system == "Linux":
            firefox_dir = Path.home() / ".mozilla/firefox"
        elif self.system == "Windows":
            appdata = os.environ.get("APPDATA", "")
            firefox_dir = Path(appdata) / "Mozilla/Firefox/Profiles"
        else:
            return profiles

        if not firefox_dir.exists():
            return profiles

        for profile_dir in firefox_dir.glob("*.default*"):
            if profile_dir.is_dir():
                profiles.append(
                    BrowserProfile(
                        name=profile_dir.name,
                        path=profile_dir,
                        browser="Firefox",
                        is_default="default-release" in profile_dir.name,
                    )
                )

        return profiles

    def import_bookmarks(self, profile_path: Path) -> list[dict[str, Any]]:
        """Query places.sqlite and return bookmark dicts."""
        places_db = profile_path / "places.sqlite"
        if not places_db.exists():
            logger.warning("No places.sqlite at %s", places_db)
            return []

        temp_db: Optional[Path] = None
        try:
            temp_db = self._copy_database(places_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    b.title,
                    p.url,
                    b.dateAdded,
                    b.lastModified,
                    GROUP_CONCAT(t.title, '/') AS folders
                FROM moz_bookmarks b
                JOIN moz_places p ON b.fk = p.id
                LEFT JOIN moz_bookmarks t ON b.parent = t.id
                WHERE b.type = 1
                    AND p.url NOT LIKE 'place:%'
                    AND p.url NOT LIKE 'about:%'
                GROUP BY b.id
                ORDER BY b.dateAdded DESC
                """
            )
            rows = cursor.fetchall()
            conn.close()

            bookmarks: list[dict[str, Any]] = []
            _skip = {"bookmarks", "menu", "toolbar"}
            for title, url, date_added, last_modified, folders in rows:
                if not url:
                    continue
                folder_path = (
                    folders
                    if folders and folders not in _skip
                    else None
                )
                tags: list[str] = []
                if folder_path:
                    tags.append(f"firefox/{folder_path}")
                bookmarks.append(
                    {
                        "url": url,
                        "title": title or url,
                        "added": self._firefox_timestamp_to_datetime(date_added),
                        "modified": self._firefox_timestamp_to_datetime(last_modified),
                        "tags": tags,
                        "source": "firefox",
                        "folder_path": folder_path,
                    }
                )
            return bookmarks

        except Exception as exc:
            logger.error("Failed to import Firefox bookmarks: %s", exc)
            return []
        finally:
            if temp_db and temp_db.exists():
                temp_db.unlink()


# ---------------------------------------------------------------------------
# Top-level API
# ---------------------------------------------------------------------------


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def import_browser_bookmarks(
    db: Database,
    browser: str = "chrome",
    profile: Optional[str] = None,
) -> ImportResult:
    """Import bookmarks from a browser into *db*.

    Args:
        db:      Open Database instance.
        browser: ``"chrome"`` or ``"firefox"`` (case-insensitive).
        profile: Profile name to use; uses the default profile when omitted.

    Returns:
        :class:`ImportResult` with ``processed``, ``added``, and ``merged``
        counts. A raw entry is merged rather than added when a bookmark with
        the same normalised URL already exists in the database (either from
        a prior import or earlier in this same call).
    """
    browser_lc = browser.lower()

    if browser_lc in ("chrome", "chromium", "edge", "brave"):
        importer: BrowserImporter = ChromeImporter()
        source_type = "chrome"
    elif browser_lc == "firefox":
        importer = FirefoxImporter()
        source_type = "firefox"
    else:
        raise ValueError(f"Unsupported browser: {browser!r}")

    # Resolve the profile path.
    profiles = importer.find_profiles()
    if not profiles:
        raise ValueError(f"No {browser} profiles found on this system")

    if profile is None:
        chosen = next((p for p in profiles if p.is_default), profiles[0])
    else:
        chosen = next(
            (p for p in profiles if p.name.lower() == profile.lower()), None
        )
        if chosen is None:
            available = ", ".join(p.name for p in profiles)
            raise ValueError(
                f"Profile {profile!r} not found for {browser}. "
                f"Available: {available}"
            )

    raw = importer.import_bookmarks(chosen.path)
    profile_name = f"{chosen.browser}/{chosen.name}"

    processed = 0
    added = 0
    merged = 0
    seen_ids: set[str] = set()

    for entry in raw:
        url = entry.get("url", "")
        if not url or not _is_http(url):
            continue

        processed += 1
        uid = generate_unique_id(url)
        is_new = uid not in seen_ids and db.get_by_unique_id(uid) is None
        seen_ids.add(uid)

        tags = list(entry.get("tags") or [])
        folder_path = entry.get("folder_path")

        bm = db.add(
            url,
            title=entry.get("title") or "",
            tags=tags or None,
            source_type=source_type,
            source_name=profile_name,
            folder_path=folder_path,
        )

        if is_new:
            added += 1
        else:
            merged += 1

        # Run detectors (YouTube, arXiv, GitHub, …) and store media metadata.
        result = run_detectors(url)
        if result is not None:
            db.update(bm.id, media=result)

    return ImportResult(processed=processed, added=added, merged=merged)


def list_browser_profiles(browser: Optional[str] = None) -> list[dict[str, Any]]:
    """Return structured info about every detected browser profile.

    Args:
        browser: Optional filter — ``"chrome"`` or ``"firefox"``.
                 When ``None`` both browsers are queried.

    Returns:
        List of dicts with keys ``browser``, ``name``, ``path``, ``is_default``.
    """
    importers: list[tuple[str, BrowserImporter]] = [
        ("chrome", ChromeImporter()),
        ("firefox", FirefoxImporter()),
    ]

    if browser is not None:
        browser_lc = browser.lower()
        importers = [(k, v) for k, v in importers if k == browser_lc]

    result: list[dict[str, Any]] = []
    for _key, imp in importers:
        for p in imp.find_profiles():
            result.append(
                {
                    "browser": p.browser,
                    "name": p.name,
                    "path": str(p.path),
                    "is_default": p.is_default,
                }
            )
    return result
