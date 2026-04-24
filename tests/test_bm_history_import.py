"""Tests for bookmark_memex.importers.browser_history and related DB layer.

Covers:
- URL normalisation and tracking-param stripping
- history_url upsert + trigger-maintained aggregates
- history_visit INSERT OR IGNORE dedup
- Chrome timestamp/transition decoding
- Firefox timestamp/visit_type decoding
- Full Chrome import against fake History SQLite fixtures
- Full Firefox import against fake places.sqlite fixtures
- Rolling-update idempotence
- Referrer-chain resolution (from_visit)
- CLI integration (--list, --since, import)
- Marginalia on history records survives record archive (orphan survival)
"""
from __future__ import annotations

import sqlite3
from argparse import Namespace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from bookmark_memex.db import (
    Database,
    generate_history_unique_id,
    normalize_url,
    normalize_url_for_history,
)
from bookmark_memex.importers.browser import BrowserProfile, ChromeImporter, FirefoxImporter
from bookmark_memex.importers.browser_history import (
    HistoryImportResult,
    _datetime_to_chrome_us,
    _datetime_to_firefox_us,
    _decode_chrome_transition,
    _decode_firefox_visit_type,
    import_history,
)


# ---------------------------------------------------------------------------
# URL normalisation
# ---------------------------------------------------------------------------


class TestNormalizeUrlForHistory:
    def test_strips_utm_params(self) -> None:
        u = "https://example.com/page?utm_source=x&utm_medium=y&keep=1"
        assert normalize_url_for_history(u) == "https://example.com/page?keep=1"

    def test_strips_all_common_trackers(self) -> None:
        u = (
            "https://example.com/?gclid=a&fbclid=b&msclkid=c&_hsenc=d"
            "&mc_eid=e&ref_src=f&igshid=g&keep=1"
        )
        assert normalize_url_for_history(u) == "https://example.com/?keep=1"

    def test_case_insensitive_tracker_match(self) -> None:
        u = "https://example.com/?UTM_SOURCE=x&keep=1"
        assert normalize_url_for_history(u) == "https://example.com/?keep=1"

    def test_drops_fragment(self) -> None:
        assert (
            normalize_url_for_history("https://example.com/page#section-3")
            == "https://example.com/page"
        )

    def test_preserves_non_tracker_params(self) -> None:
        u = "https://example.com/search?q=test&page=2"
        assert normalize_url_for_history(u) == "https://example.com/search?page=2&q=test"

    def test_unique_id_same_with_or_without_trackers(self) -> None:
        a = generate_history_unique_id("https://example.com/p")
        b = generate_history_unique_id("https://example.com/p?utm_source=x")
        assert a == b

    def test_unique_id_differs_from_bookmark_unique_id(self) -> None:
        """Bookmarks preserve URL exactly; history strips trackers.

        A URL with tracking params gets one unique_id under bookmark
        rules, another under history rules.
        """
        import hashlib

        url = "https://example.com/?utm_source=x"
        bm_uid = hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16]
        hist_uid = generate_history_unique_id(url)
        assert bm_uid != hist_uid


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


class TestTimestamps:
    def test_chrome_roundtrip(self) -> None:
        dt = datetime(2026, 4, 20, 12, 0, 0)
        us = _datetime_to_chrome_us(dt)
        assert us > 0
        # Chrome epoch is 1601, so a 2026 timestamp in Chrome microseconds
        # is much larger than the same timestamp in Firefox/unix microseconds.
        assert us > _datetime_to_firefox_us(dt)

    def test_firefox_roundtrip(self) -> None:
        dt = datetime(2026, 4, 20, 12, 0, 0)
        us = _datetime_to_firefox_us(dt)
        assert us > 0


# ---------------------------------------------------------------------------
# Transition decoding
# ---------------------------------------------------------------------------


class TestTransitionDecoding:
    def test_chrome_link(self) -> None:
        assert _decode_chrome_transition(0) == "link"

    def test_chrome_typed(self) -> None:
        assert _decode_chrome_transition(1) == "typed"

    def test_chrome_reload(self) -> None:
        assert _decode_chrome_transition(8) == "reload"

    def test_chrome_with_qualifiers_stripped(self) -> None:
        """Chrome packs qualifiers above the low 8 bits.

        Transition 0x01800000 | 1 means 'typed' with forward-back
        qualifiers; the core value is still 1 (typed).
        """
        raw = 0x01800001
        assert _decode_chrome_transition(raw) == "typed"

    def test_chrome_unknown_value_falls_back(self) -> None:
        assert _decode_chrome_transition(0xFF) == "other"

    def test_firefox_link(self) -> None:
        assert _decode_firefox_visit_type(1) == "link"

    def test_firefox_redirect(self) -> None:
        assert _decode_firefox_visit_type(5) == "redirect"
        assert _decode_firefox_visit_type(6) == "redirect"

    def test_firefox_unknown_value_falls_back(self) -> None:
        assert _decode_firefox_visit_type(99) == "other"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


class TestDatabaseHistoryMethods:
    def test_upsert_inserts_when_absent(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        row, created = db.upsert_history_url(
            "https://example.com/x", title="Example"
        )
        assert created is True
        assert row.url == "https://example.com/x"
        assert row.title == "Example"
        assert row.visit_count == 0

    def test_upsert_returns_existing_on_second_call(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        first, created1 = db.upsert_history_url("https://example.com/y")
        second, created2 = db.upsert_history_url(
            "https://example.com/y", title="Late title"
        )
        assert created1 is True
        assert created2 is False
        assert first.id == second.id
        assert second.title == "Late title"

    def test_upsert_does_not_clobber_title(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        db.upsert_history_url("https://example.com/z", title="Original")
        row, _ = db.upsert_history_url("https://example.com/z", title="Later")
        assert row.title == "Original"  # only backfilled when empty

    def test_upsert_typed_count_accumulates(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        db.upsert_history_url("https://example.com/t", typed_count_delta=2)
        row, _ = db.upsert_history_url(
            "https://example.com/t", typed_count_delta=3
        )
        assert row.typed_count == 5

    def test_upsert_dedups_by_history_unique_id(self, tmp_db_path: str) -> None:
        """Two URLs differing only by utm_source dedup to one row."""
        db = Database(tmp_db_path)
        a, _ = db.upsert_history_url("https://example.com/dedup?utm_source=x")
        b, _ = db.upsert_history_url("https://example.com/dedup?utm_source=y")
        assert a.id == b.id

    def test_visit_insert_updates_aggregates(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        url_row, _ = db.upsert_history_url("https://example.com/v")

        t0 = datetime(2026, 4, 20, 9, 0, 0)
        t1 = datetime(2026, 4, 20, 12, 0, 0)
        t2 = datetime(2026, 4, 20, 10, 0, 0)

        for t in (t0, t1, t2):
            v, inserted = db.add_history_visit(
                url_id=url_row.id,
                visited_at=t,
                source_type="chrome",
                source_name="Chrome/Default",
            )
            assert inserted is True

        refreshed = db.get_history_url(url_row.id)
        assert refreshed.visit_count == 3
        assert refreshed.first_visited == t0
        assert refreshed.last_visited == t1

    def test_visit_dedup_on_tuple(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        url_row, _ = db.upsert_history_url("https://example.com/d")
        t = datetime(2026, 4, 20, 9, 0, 0)

        v1, ins1 = db.add_history_visit(
            url_id=url_row.id,
            visited_at=t,
            source_type="chrome",
            source_name="Chrome/Default",
        )
        v2, ins2 = db.add_history_visit(
            url_id=url_row.id,
            visited_at=t,
            source_type="chrome",
            source_name="Chrome/Default",
        )
        assert ins1 is True
        assert ins2 is False
        assert v2.id == v1.id

    def test_visit_not_dedup_across_sources(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        url_row, _ = db.upsert_history_url("https://example.com/cross")
        t = datetime(2026, 4, 20, 9, 0, 0)

        _, ins1 = db.add_history_visit(
            url_id=url_row.id,
            visited_at=t,
            source_type="chrome",
            source_name="Chrome/Default",
        )
        _, ins2 = db.add_history_visit(
            url_id=url_row.id,
            visited_at=t,
            source_type="firefox",
            source_name="Firefox/default-release",
        )
        assert ins1 is True
        assert ins2 is True

    def test_hard_delete_visit_updates_aggregates(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        url_row, _ = db.upsert_history_url("https://example.com/del")
        t0 = datetime(2026, 4, 20, 9, 0, 0)
        t1 = datetime(2026, 4, 20, 10, 0, 0)

        v0, _ = db.add_history_visit(
            url_id=url_row.id, visited_at=t0,
            source_type="chrome", source_name="Chrome/Default",
        )
        db.add_history_visit(
            url_id=url_row.id, visited_at=t1,
            source_type="chrome", source_name="Chrome/Default",
        )

        # Hard-delete the earlier visit and confirm aggregates move.
        with db._session() as s:
            visit = s.get(type(v0), v0.id)
            s.delete(visit)
        refreshed = db.get_history_url(url_row.id)
        assert refreshed.visit_count == 1
        assert refreshed.first_visited == t1
        assert refreshed.last_visited == t1


# ---------------------------------------------------------------------------
# Fake-DB fixtures
# ---------------------------------------------------------------------------


def _make_fake_chrome_history(dest: Path, visits: list[dict]) -> None:
    """Write a minimal Chrome History SQLite at *dest*.

    *visits* is a list of dicts with keys:
        url, title, visited_at (datetime), transition (int),
        from_visit (int, 0 = none), typed_count (int, default 0)
    """
    conn = sqlite3.connect(str(dest))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE urls (
            id INTEGER PRIMARY KEY,
            url LONGVARCHAR,
            title LONGVARCHAR,
            visit_count INTEGER DEFAULT 0,
            typed_count INTEGER DEFAULT 0
        );
        CREATE TABLE visits (
            id INTEGER PRIMARY KEY,
            url INTEGER,
            visit_time INTEGER,
            from_visit INTEGER,
            transition INTEGER,
            visit_duration INTEGER
        );
        """
    )

    url_cache: dict[str, int] = {}
    for v in visits:
        if v["url"] not in url_cache:
            cur.execute(
                "INSERT INTO urls (url, title, typed_count) VALUES (?, ?, ?)",
                (v["url"], v.get("title", ""), v.get("typed_count", 0)),
            )
            url_cache[v["url"]] = cur.lastrowid
        url_id = url_cache[v["url"]]

        cur.execute(
            "INSERT INTO visits (id, url, visit_time, from_visit, transition, visit_duration) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                v.get("visit_id", 0) or None,
                url_id,
                _datetime_to_chrome_us(v["visited_at"]),
                v.get("from_visit", 0),
                v.get("transition", 0),
                v.get("duration_us", 0),
            ),
        )
    conn.commit()
    conn.close()


def _make_fake_firefox_places(dest: Path, visits: list[dict]) -> None:
    """Write a minimal Firefox places.sqlite at *dest*.

    Keys in *visits* dicts:
        url, title, visited_at (datetime), visit_type (int),
        from_visit (int), typed (int, 0 or 1)
    """
    conn = sqlite3.connect(str(dest))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE moz_places (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            typed INTEGER DEFAULT 0
        );
        CREATE TABLE moz_historyvisits (
            id INTEGER PRIMARY KEY,
            place_id INTEGER,
            from_visit INTEGER,
            visit_date INTEGER,
            visit_type INTEGER
        );
        """
    )
    place_cache: dict[str, int] = {}
    for v in visits:
        if v["url"] not in place_cache:
            cur.execute(
                "INSERT INTO moz_places (url, title, typed) VALUES (?, ?, ?)",
                (v["url"], v.get("title", ""), v.get("typed", 0)),
            )
            place_cache[v["url"]] = cur.lastrowid
        place_id = place_cache[v["url"]]
        cur.execute(
            "INSERT INTO moz_historyvisits (id, place_id, from_visit, visit_date, visit_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                v.get("visit_id", 0) or None,
                place_id,
                v.get("from_visit", 0),
                _datetime_to_firefox_us(v["visited_at"]),
                v.get("visit_type", 1),
            ),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Chrome end-to-end
# ---------------------------------------------------------------------------


class TestChromeEndToEnd:
    def test_basic_import(self, tmp_db_path: str, tmp_path: Path) -> None:
        profile = tmp_path / "Default"
        profile.mkdir()
        _make_fake_chrome_history(
            profile / "History",
            [
                {
                    "visit_id": 1,
                    "url": "https://a.example.com/",
                    "title": "A",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "transition": 0,  # link
                },
                {
                    "visit_id": 2,
                    "url": "https://b.example.com/",
                    "title": "B",
                    "visited_at": datetime(2026, 4, 20, 10, 0, 0),
                    "transition": 1,  # typed
                },
                {
                    "visit_id": 3,
                    "url": "https://a.example.com/",
                    "title": "A",
                    "visited_at": datetime(2026, 4, 20, 11, 0, 0),
                    "transition": 8,  # reload
                },
            ],
        )
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            result = import_history(db, browser="chrome")

        assert isinstance(result, HistoryImportResult)
        assert result.urls_seen == 2
        assert result.urls_added == 2
        assert result.urls_updated == 0
        assert result.visits_seen == 3
        assert result.visits_added == 3
        assert result.visits_skipped == 0

        # Transitions correctly decoded into history_visits
        import sqlite3 as sq
        conn = sq.connect(tmp_db_path)
        cur = conn.cursor()
        transitions = [r[0] for r in cur.execute(
            "SELECT transition FROM history_visits ORDER BY visited_at"
        ).fetchall()]
        assert transitions == ["link", "typed", "reload"]
        conn.close()

    def test_rolling_update_is_idempotent(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        profile = tmp_path / "Default"
        profile.mkdir()
        visits = [
            {
                "visit_id": 1,
                "url": "https://x.example.com/",
                "title": "X",
                "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                "transition": 0,
            },
            {
                "visit_id": 2,
                "url": "https://x.example.com/",
                "visited_at": datetime(2026, 4, 20, 10, 0, 0),
                "transition": 0,
            },
        ]
        _make_fake_chrome_history(profile / "History", visits)

        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            r1 = import_history(db, browser="chrome")
            r2 = import_history(db, browser="chrome")

        assert r1.visits_added == 2
        assert r1.visits_skipped == 0
        assert r2.visits_added == 0
        assert r2.visits_skipped == 2
        assert r2.urls_added == 0
        assert r2.urls_updated == 1  # same URL, existed already, counted once

    def test_referrer_chain_resolved(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """visit 2's from_visit = 1 should resolve to our primary key."""
        profile = tmp_path / "Default"
        profile.mkdir()
        _make_fake_chrome_history(
            profile / "History",
            [
                {
                    "visit_id": 10,
                    "url": "https://search.example.com/q=memex",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "transition": 1,  # typed
                    "from_visit": 0,
                },
                {
                    "visit_id": 11,
                    "url": "https://result.example.com/a",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 5),
                    "transition": 0,  # link
                    "from_visit": 10,
                },
            ],
        )
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            import_history(db, browser="chrome")

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, from_visit_id FROM history_visits ORDER BY visited_at"
        ).fetchall()
        conn.close()
        assert len(rows) == 2
        # Second visit's from_visit_id should match the first visit's id.
        assert rows[1][1] == rows[0][0]

    def test_tracking_params_collapse_to_one_url(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        profile = tmp_path / "Default"
        profile.mkdir()
        _make_fake_chrome_history(
            profile / "History",
            [
                {
                    "visit_id": 1,
                    "url": "https://site.example.com/page?utm_source=a",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "transition": 0,
                },
                {
                    "visit_id": 2,
                    "url": "https://site.example.com/page?utm_source=b",
                    "visited_at": datetime(2026, 4, 20, 10, 0, 0),
                    "transition": 0,
                },
            ],
        )
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            result = import_history(db, browser="chrome")
        assert result.urls_added == 1
        assert result.visits_added == 2

    def test_since_filter(self, tmp_db_path: str, tmp_path: Path) -> None:
        profile = tmp_path / "Default"
        profile.mkdir()
        _make_fake_chrome_history(
            profile / "History",
            [
                {
                    "visit_id": 1,
                    "url": "https://old.example.com/",
                    "visited_at": datetime(2026, 4, 1, 9, 0, 0),
                    "transition": 0,
                },
                {
                    "visit_id": 2,
                    "url": "https://new.example.com/",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "transition": 0,
                },
            ],
        )
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )
        since = datetime(2026, 4, 10, 0, 0, 0)
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            result = import_history(db, browser="chrome", since=since)
        assert result.visits_added == 1
        assert result.urls_added == 1

    def test_unsupported_browser_raises(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        with pytest.raises(ValueError, match="Unsupported"):
            import_history(db, browser="safari")

    def test_no_profiles_raises(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        with patch.object(ChromeImporter, "find_profiles", return_value=[]):
            with pytest.raises(ValueError, match="No chrome profiles"):
                import_history(db, browser="chrome")

    def test_unknown_profile_raises(self, tmp_db_path: str, tmp_path: Path) -> None:
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=tmp_path, browser="Chrome", is_default=True
        )
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            with pytest.raises(ValueError, match="not found"):
                import_history(db, browser="chrome", profile="NoSuchProfile")

    def test_missing_history_db_returns_empty_counts(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """Profile directory exists but has no History file (Chrome not yet used)."""
        profile = tmp_path / "Default"
        profile.mkdir()
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            result = import_history(db, browser="chrome")
        assert result == HistoryImportResult(0, 0, 0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Firefox end-to-end
# ---------------------------------------------------------------------------


class TestFirefoxEndToEnd:
    def test_basic_import(self, tmp_db_path: str, tmp_path: Path) -> None:
        profile = tmp_path / "abc.default-release"
        profile.mkdir()
        _make_fake_firefox_places(
            profile / "places.sqlite",
            [
                {
                    "visit_id": 1,
                    "url": "https://ff.example.com/",
                    "title": "FF",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "visit_type": 1,  # link
                },
                {
                    "visit_id": 2,
                    "url": "https://ff.example.com/b",
                    "visited_at": datetime(2026, 4, 20, 10, 0, 0),
                    "visit_type": 2,  # typed
                    "typed": 1,
                },
            ],
        )
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="abc.default-release",
            path=profile,
            browser="Firefox",
            is_default=True,
        )
        with patch.object(
            FirefoxImporter, "find_profiles", return_value=[fake_profile]
        ):
            result = import_history(db, browser="firefox")
        assert result.urls_added == 2
        assert result.visits_added == 2

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.cursor()
        transitions = {
            r[0] for r in cur.execute("SELECT transition FROM history_visits")
        }
        assert transitions == {"link", "typed"}
        conn.close()


# ---------------------------------------------------------------------------
# Marginalia orphan survival (extended to history records)
# ---------------------------------------------------------------------------


class TestHistoryMarginalia:
    def test_marginalia_can_reference_history_url(self, tmp_db_path: str) -> None:
        """Attach marginalia directly to a history_urls row."""
        from bookmark_memex.models import Marginalia
        import uuid

        db = Database(tmp_db_path)
        row, _ = db.upsert_history_url("https://m.example.com/")

        mid = uuid.uuid4().hex
        with db._session() as s:
            s.add(Marginalia(
                id=mid,
                history_url_id=row.id,
                text="test note on history URL",
            ))

        with db._session() as s:
            m = s.get(Marginalia, mid)
            assert m is not None
            assert m.history_url_id == row.id
            assert m.bookmark_id is None
            assert m.history_visit_id is None

    def test_marginalia_survives_history_url_deletion(
        self, tmp_db_path: str
    ) -> None:
        """ON DELETE SET NULL: deleting the history_url leaves the note with NULL FK."""
        from bookmark_memex.models import Marginalia, HistoryUrl
        import uuid

        db = Database(tmp_db_path)
        row, _ = db.upsert_history_url("https://orphan.example.com/")

        mid = uuid.uuid4().hex
        with db._session() as s:
            s.add(Marginalia(
                id=mid,
                history_url_id=row.id,
                text="orphan survivor",
            ))

        with db._session() as s:
            u = s.get(HistoryUrl, row.id)
            s.delete(u)

        with db._session() as s:
            m = s.get(Marginalia, mid)
            assert m is not None
            assert m.history_url_id is None
            assert m.text == "orphan survivor"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIImportHistory:
    def test_list_flag_prints_profiles(
        self, tmp_db_path: str, capsys
    ) -> None:
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
            from bookmark_memex.cli import cmd_import_history

            args = Namespace(
                db=tmp_db_path,
                browser=None,
                profile=None,
                since=None,
                list_profiles=True,
            )
            cmd_import_history(args)

        out = capsys.readouterr().out
        assert "Chrome" in out
        assert "Default" in out

    def test_import_command_prints_counts(
        self, tmp_db_path: str, tmp_path: Path, capsys
    ) -> None:
        profile = tmp_path / "Default"
        profile.mkdir()
        _make_fake_chrome_history(
            profile / "History",
            [
                {
                    "visit_id": 1,
                    "url": "https://cli.example.com/",
                    "title": "CLI",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "transition": 0,
                }
            ],
        )

        fake = [
            BrowserProfile(
                name="Default", path=profile, browser="Chrome", is_default=True
            )
        ]
        with patch.object(ChromeImporter, "find_profiles", return_value=fake):
            from bookmark_memex.cli import cmd_import_history

            args = Namespace(
                db=tmp_db_path,
                browser="chrome",
                profile=None,
                since=None,
                list_profiles=False,
            )
            cmd_import_history(args)

        out = capsys.readouterr().out
        assert "chrome" in out.lower()
        assert "urls seen 1" in out
        assert "visits seen 1" in out
        assert "added 1" in out

    def test_since_flag_parsed(
        self, tmp_db_path: str, tmp_path: Path, capsys
    ) -> None:
        profile = tmp_path / "Default"
        profile.mkdir()
        _make_fake_chrome_history(
            profile / "History",
            [
                {
                    "visit_id": 1,
                    "url": "https://old.example.com/",
                    "visited_at": datetime(2026, 4, 1, 9, 0, 0),
                    "transition": 0,
                },
                {
                    "visit_id": 2,
                    "url": "https://new.example.com/",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "transition": 0,
                },
            ],
        )
        fake = [
            BrowserProfile(
                name="Default", path=profile, browser="Chrome", is_default=True
            )
        ]
        with patch.object(ChromeImporter, "find_profiles", return_value=fake):
            from bookmark_memex.cli import cmd_import_history

            args = Namespace(
                db=tmp_db_path,
                browser="chrome",
                profile=None,
                since="2026-04-10",
                list_profiles=False,
            )
            cmd_import_history(args)

        out = capsys.readouterr().out
        assert "visits seen 1" in out
        assert "added 1" in out

    def test_since_flag_invalid_value(
        self, tmp_db_path: str
    ) -> None:
        from bookmark_memex.cli import cmd_import_history

        args = Namespace(
            db=tmp_db_path,
            browser="chrome",
            profile=None,
            since="not-a-date",
            list_profiles=False,
        )
        with pytest.raises(SystemExit):
            cmd_import_history(args)


# ---------------------------------------------------------------------------
# Cross-table query sanity
# ---------------------------------------------------------------------------


class TestMcpGetRecord:
    def test_get_record_history_url(self, tmp_db_path: str) -> None:
        from bookmark_memex.mcp import _create_tools

        db = Database(tmp_db_path)
        row, _ = db.upsert_history_url(
            "https://mcp.example.com/page", title="MCP"
        )
        db.add_history_visit(
            url_id=row.id,
            visited_at=datetime(2026, 4, 20, 9, 0, 0),
            source_type="chrome",
            source_name="Chrome/Default",
            transition="link",
        )

        tools = _create_tools(tmp_db_path)
        result = tools["get_record"]("history-url", row.unique_id)

        assert result["url"] == "https://mcp.example.com/page"
        assert result["visit_count"] == 1
        assert len(result["recent_visits"]) == 1
        assert result["recent_visits"][0]["transition"] == "link"
        assert result["uri"].startswith("bookmark-memex://history-url/")

    def test_get_record_visit(self, tmp_db_path: str) -> None:
        from bookmark_memex.mcp import _create_tools

        db = Database(tmp_db_path)
        row, _ = db.upsert_history_url("https://v.example.com/")
        visit, _ = db.add_history_visit(
            url_id=row.id,
            visited_at=datetime(2026, 4, 20, 9, 0, 0),
            source_type="chrome",
            source_name="Chrome/Default",
            transition="typed",
        )

        tools = _create_tools(tmp_db_path)
        result = tools["get_record"]("visit", visit.unique_id)

        assert result["transition"] == "typed"
        assert result["url"] == "https://v.example.com/"
        assert result["source_type"] == "chrome"
        assert result["history_url_uri"].startswith(
            "bookmark-memex://history-url/"
        )

    def test_get_record_history_url_not_found(self, tmp_db_path: str) -> None:
        from bookmark_memex.mcp import _create_tools

        tools = _create_tools(tmp_db_path)
        with pytest.raises(ValueError, match="not found"):
            tools["get_record"]("history-url", "0000000000000000")

    def test_get_record_marginalia_on_history_url_resolves(
        self, tmp_db_path: str
    ) -> None:
        """A note on a history URL surfaces its parent URI in get_record."""
        from bookmark_memex.mcp import _create_tools
        from bookmark_memex.models import Marginalia
        import uuid

        db = Database(tmp_db_path)
        row, _ = db.upsert_history_url("https://marg.example.com/")
        mid = uuid.uuid4().hex
        with db._session() as s:
            s.add(Marginalia(
                id=mid,
                history_url_id=row.id,
                text="note on history",
            ))

        tools = _create_tools(tmp_db_path)
        result = tools["get_record"]("marginalia", mid)

        assert result["text"] == "note on history"
        assert result["history_url_uri"].startswith(
            "bookmark-memex://history-url/"
        )
        assert "bookmark_uri" not in result  # no bookmark attached


class TestHistoryBookmarkCrossQuery:
    def test_join_on_unique_id_without_trackers(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """The spec's example query: bookmarks joined with history_urls.

        When the bookmark URL is free of tracking params the unique_id
        matches exactly between the two tables, so a JOIN works.
        """
        profile = tmp_path / "Default"
        profile.mkdir()
        _make_fake_chrome_history(
            profile / "History",
            [
                {
                    "visit_id": 1,
                    "url": "https://shared.example.com/page",
                    "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                    "transition": 0,
                }
            ],
        )
        db = Database(tmp_db_path)
        fake_profile = BrowserProfile(
            name="Default", path=profile, browser="Chrome", is_default=True
        )
        with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
            import_history(db, browser="chrome")

        db.add("https://shared.example.com/page", title="Shared")

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT b.title, h.visit_count "
            "FROM bookmarks b "
            "JOIN history_urls h ON h.unique_id = b.unique_id"
        ).fetchall()
        conn.close()
        assert rows == [("Shared", 1)]
