"""Round-trip tests for history records through the arkiv importer.

Exports a DB with history, reimports into a fresh DB, asserts the
structure is preserved: URL counts, visit counts with trigger-rebuilt
aggregates, referrer chains, marginalia parenting, and idempotent
re-imports.

These tests close the loop opened by test_bm_arkiv_history.py (export
side) and exercise:
    bookmark_memex.db.merge_history_url
    bookmark_memex.db.merge_history_visit
    bookmark_memex.db.merge_marginalia (extended)
    bookmark_memex.importers.arkiv.import_arkiv (extended)
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from bookmark_memex.db import Database
from bookmark_memex.exporters.arkiv import export_arkiv
from bookmark_memex.importers.arkiv import import_arkiv
from bookmark_memex.importers.browser import BrowserProfile, ChromeImporter
from bookmark_memex.importers.browser_history import import_history
from bookmark_memex.models import HistoryUrl, HistoryVisit, Marginalia


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_fake_chrome_history(dest: Path, visits: list[dict]) -> None:
    import sqlite3 as _sq
    from bookmark_memex.importers.browser_history import _datetime_to_chrome_us

    conn = _sq.connect(str(dest))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE urls (
            id INTEGER PRIMARY KEY, url LONGVARCHAR, title LONGVARCHAR,
            visit_count INTEGER DEFAULT 0, typed_count INTEGER DEFAULT 0
        );
        CREATE TABLE visits (
            id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER,
            from_visit INTEGER, transition INTEGER, visit_duration INTEGER
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
        cur.execute(
            "INSERT INTO visits (id, url, visit_time, from_visit, transition, visit_duration) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                v.get("visit_id"),
                url_cache[v["url"]],
                _datetime_to_chrome_us(v["visited_at"]),
                v.get("from_visit", 0),
                v.get("transition", 0),
                v.get("duration_us", 0),
            ),
        )
    conn.commit()
    conn.close()


def _populate_history(db: Database, tmp_path: Path) -> None:
    profile = tmp_path / "Default"
    profile.mkdir()
    _make_fake_chrome_history(
        profile / "History",
        [
            {
                "visit_id": 1,
                "url": "https://search.example.com/q=memex",
                "title": "Search",
                "visited_at": datetime(2026, 4, 20, 9, 0, 0),
                "transition": 1,  # typed
            },
            {
                "visit_id": 2,
                "url": "https://result.example.com/a",
                "title": "Result A",
                "visited_at": datetime(2026, 4, 20, 9, 0, 5),
                "transition": 0,  # link
                "from_visit": 1,
            },
            {
                "visit_id": 3,
                "url": "https://result.example.com/a",
                "visited_at": datetime(2026, 4, 20, 10, 0, 0),
                "transition": 8,  # reload
            },
        ],
    )
    fake = BrowserProfile(
        name="Default", path=profile, browser="Chrome", is_default=True
    )
    with patch.object(ChromeImporter, "find_profiles", return_value=[fake]):
        import_history(db, browser="chrome")


# ---------------------------------------------------------------------------
# DB method: merge_history_url
# ---------------------------------------------------------------------------


class TestMergeHistoryUrl:
    def test_inserts_when_absent(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        id_, inserted = db.merge_history_url(
            unique_id="abc1234567890def",
            url="https://m.example.com/",
            title="M",
            typed_count=3,
        )
        assert inserted is True
        row = db.get_history_url(id_)
        assert row.unique_id == "abc1234567890def"
        assert row.title == "M"
        assert row.typed_count == 3

    def test_idempotent(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        uid = "0000000000000001"
        id1, ins1 = db.merge_history_url(unique_id=uid, url="https://a.example.com/")
        id2, ins2 = db.merge_history_url(unique_id=uid, url="https://a.example.com/")
        assert id1 == id2
        assert ins1 is True and ins2 is False

    def test_backfills_empty_title(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        uid = "0000000000000002"
        db.merge_history_url(unique_id=uid, url="https://b.example.com/")
        id_, _ = db.merge_history_url(
            unique_id=uid, url="https://b.example.com/", title="Found"
        )
        assert db.get_history_url(id_).title == "Found"

    def test_preserves_populated_title(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        uid = "0000000000000003"
        db.merge_history_url(unique_id=uid, url="https://c.example.com/", title="Kept")
        id_, _ = db.merge_history_url(
            unique_id=uid, url="https://c.example.com/", title="Not used"
        )
        assert db.get_history_url(id_).title == "Kept"

    def test_bumps_typed_count_monotonically(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        uid = "0000000000000004"
        db.merge_history_url(
            unique_id=uid, url="https://t.example.com/", typed_count=2
        )
        id_, _ = db.merge_history_url(
            unique_id=uid, url="https://t.example.com/", typed_count=5
        )
        assert db.get_history_url(id_).typed_count == 5
        # Lower count should not downshift.
        id_, _ = db.merge_history_url(
            unique_id=uid, url="https://t.example.com/", typed_count=1
        )
        assert db.get_history_url(id_).typed_count == 5


# ---------------------------------------------------------------------------
# DB method: merge_history_visit
# ---------------------------------------------------------------------------


class TestMergeHistoryVisit:
    def _url(self, db: Database, uid: str = "0000000000000100") -> int:
        id_, _ = db.merge_history_url(unique_id=uid, url="https://v.example.com/")
        return id_

    def test_insert_then_idempotent(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        url_uid = "0000000000000100"
        self._url(db, url_uid)

        v_uuid = uuid.uuid4().hex
        t = datetime(2026, 4, 20, 9, 0, 0)
        id1, ins1 = db.merge_history_visit(
            unique_id=v_uuid, url_unique_id=url_uid, visited_at=t,
            source_type="chrome", source_name="Chrome/Default",
        )
        id2, ins2 = db.merge_history_visit(
            unique_id=v_uuid, url_unique_id=url_uid, visited_at=t,
            source_type="chrome", source_name="Chrome/Default",
        )
        assert ins1 is True
        assert ins2 is False
        assert id1 == id2

    def test_unknown_url_drops(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        vid, ins = db.merge_history_visit(
            unique_id=uuid.uuid4().hex,
            url_unique_id="nonexistent00000",
            visited_at=datetime(2026, 4, 20, 9, 0, 0),
            source_type="chrome",
            source_name="Chrome/Default",
        )
        assert vid is None
        assert ins is False

    def test_tuple_dedup_across_uuids(self, tmp_db_path: str) -> None:
        """Two different UUIDs, same (url, time, source) tuple.

        The second insert should resolve to the first row via the
        secondary UNIQUE constraint and return (existing_id, False).
        """
        db = Database(tmp_db_path)
        url_uid = "0000000000000101"
        self._url(db, url_uid)

        t = datetime(2026, 4, 20, 9, 0, 0)
        id1, _ = db.merge_history_visit(
            unique_id="aaa1", url_unique_id=url_uid, visited_at=t,
            source_type="chrome", source_name="Chrome/Default",
        )
        id2, ins2 = db.merge_history_visit(
            unique_id="bbb2", url_unique_id=url_uid, visited_at=t,
            source_type="chrome", source_name="Chrome/Default",
        )
        assert id2 == id1
        assert ins2 is False

    def test_resolves_from_visit(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        url_uid = "0000000000000102"
        self._url(db, url_uid)

        first_uuid = uuid.uuid4().hex
        first_id, _ = db.merge_history_visit(
            unique_id=first_uuid, url_unique_id=url_uid,
            visited_at=datetime(2026, 4, 20, 9, 0, 0),
            source_type="chrome", source_name="Chrome/Default",
        )

        second_uuid = uuid.uuid4().hex
        second_id, _ = db.merge_history_visit(
            unique_id=second_uuid, url_unique_id=url_uid,
            visited_at=datetime(2026, 4, 20, 9, 0, 5),
            source_type="chrome", source_name="Chrome/Default",
            from_visit_unique_id=first_uuid,
        )

        row = db.get_history_visit(second_id)
        assert row.from_visit_id == first_id


# ---------------------------------------------------------------------------
# merge_marginalia extended for history FKs
# ---------------------------------------------------------------------------


class TestMergeMarginaliaHistory:
    def test_history_url_parent(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        hu_id, _ = db.merge_history_url(
            unique_id="0000000000000300", url="https://n.example.com/"
        )
        mid = uuid.uuid4().hex
        inserted = db.merge_marginalia(
            uuid=mid,
            text="history note",
            history_url_unique_id="0000000000000300",
        )
        assert inserted is True
        with db._session() as s:
            m = s.get(Marginalia, mid)
            assert m.history_url_id == hu_id
            assert m.bookmark_id is None
            assert m.history_visit_id is None

    def test_unknown_parent_becomes_orphan(self, tmp_db_path: str) -> None:
        db = Database(tmp_db_path)
        mid = uuid.uuid4().hex
        inserted = db.merge_marginalia(
            uuid=mid,
            text="stranded",
            history_url_unique_id="nonexistent_00000000",
        )
        assert inserted is True
        with db._session() as s:
            m = s.get(Marginalia, mid)
            # Parent lookup failed; note survives with NULL FKs.
            assert m.history_url_id is None
            assert m.text == "stranded"


# ---------------------------------------------------------------------------
# End-to-end round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_history_roundtrips(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        src = Database(tmp_db_path)
        _populate_history(src, tmp_path)

        bundle = tmp_path / "bundle"
        export_arkiv(src, bundle, include_history=True)

        dst_path = str(tmp_path / "dst.db")
        dst = Database(dst_path)
        stats = import_arkiv(dst, bundle)

        assert stats["history_urls_seen"] == 2
        assert stats["history_urls_added"] == 2
        assert stats["visits_seen"] == 3
        assert stats["visits_added"] == 3
        assert stats["visits_dropped_unknown_parent"] == 0

        # Trigger-maintained aggregates rebuild from inserted visits.
        conn = sqlite3.connect(dst_path)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT url, visit_count FROM history_urls ORDER BY url"
        ).fetchall()
        assert rows == [
            ("https://result.example.com/a", 2),
            ("https://search.example.com/q=memex", 1),
        ]

    def test_referrer_chain_roundtrips(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        src = Database(tmp_db_path)
        _populate_history(src, tmp_path)

        bundle = tmp_path / "bundle"
        export_arkiv(src, bundle, include_history=True)

        dst_path = str(tmp_path / "dst.db")
        dst = Database(dst_path)
        import_arkiv(dst, bundle)

        conn = sqlite3.connect(dst_path)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT v.visited_at, v.from_visit_id "
            "FROM history_visits v ORDER BY v.visited_at"
        ).fetchall()
        conn.close()
        # Three visits: typed @9:00, link @9:05 (from #1), reload @10:00.
        assert len(rows) == 3
        assert rows[0][1] is None                     # typed, no referrer
        assert rows[1][1] is not None                 # link resolves to prior
        assert rows[2][1] is None                     # reload has no from_visit

    def test_idempotent_reimport(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        src = Database(tmp_db_path)
        _populate_history(src, tmp_path)

        bundle = tmp_path / "bundle"
        export_arkiv(src, bundle, include_history=True)

        dst_path = str(tmp_path / "dst.db")
        dst = Database(dst_path)
        s1 = import_arkiv(dst, bundle)
        s2 = import_arkiv(dst, bundle)

        assert s1["history_urls_added"] == 2
        assert s2["history_urls_added"] == 0
        assert s2["history_urls_skipped_existing"] == 2
        assert s1["visits_added"] == 3
        assert s2["visits_added"] == 0
        assert s2["visits_skipped_existing"] == 3

    def test_marginalia_on_history_url_roundtrips(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        src = Database(tmp_db_path)
        _populate_history(src, tmp_path)

        with src._session() as s:
            hu = s.execute(
                __import__("sqlalchemy", fromlist=["text"]).text(
                    "SELECT id, unique_id FROM history_urls LIMIT 1"
                )
            ).fetchone()
        hu_id, hu_uid = hu

        mid = uuid.uuid4().hex
        with src._session() as s:
            s.add(Marginalia(id=mid, history_url_id=hu_id, text="round-trip note"))

        bundle = tmp_path / "bundle"
        export_arkiv(src, bundle, include_history=True)

        dst_path = str(tmp_path / "dst.db")
        dst = Database(dst_path)
        stats = import_arkiv(dst, bundle)

        assert stats["marginalia_added"] == 1

        with dst._session() as s:
            m = s.get(Marginalia, mid)
            assert m is not None
            assert m.text == "round-trip note"
            # history_url_id must resolve in the destination DB to a row
            # with the exact same unique_id as on the source.
            hu_dst = s.get(HistoryUrl, m.history_url_id)
            assert hu_dst is not None
            assert hu_dst.unique_id == hu_uid
            assert m.bookmark_id is None

    def test_marginalia_on_visit_roundtrips(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        src = Database(tmp_db_path)
        _populate_history(src, tmp_path)

        with src._session() as s:
            v = s.execute(
                __import__("sqlalchemy", fromlist=["text"]).text(
                    "SELECT id, unique_id FROM history_visits LIMIT 1"
                )
            ).fetchone()
        v_id, v_uid = v

        mid = uuid.uuid4().hex
        with src._session() as s:
            s.add(Marginalia(id=mid, history_visit_id=v_id, text="visit-level note"))

        bundle = tmp_path / "bundle"
        export_arkiv(src, bundle, include_history=True)

        dst_path = str(tmp_path / "dst.db")
        dst = Database(dst_path)
        import_arkiv(dst, bundle)

        with dst._session() as s:
            m = s.get(Marginalia, mid)
            assert m is not None
            hv_dst = s.get(HistoryVisit, m.history_visit_id)
            assert hv_dst.unique_id == v_uid
            assert m.bookmark_id is None
            assert m.history_url_id is None

    def test_bookmarks_only_bundle_drops_history(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """A bundle exported WITHOUT --include-history imports cleanly."""
        src = Database(tmp_db_path)
        src.add("https://saved.example.com/", title="Saved")
        _populate_history(src, tmp_path)

        bundle = tmp_path / "bundle"
        export_arkiv(src, bundle, include_history=False)

        dst_path = str(tmp_path / "dst.db")
        dst = Database(dst_path)
        stats = import_arkiv(dst, bundle)
        assert stats["bookmarks_added"] == 1
        assert stats["history_urls_seen"] == 0
        assert stats["visits_seen"] == 0

    def test_visit_with_missing_parent_url_dropped(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """A malformed visit whose parent URL is not in the bundle is counted."""
        src = Database(tmp_db_path)
        _populate_history(src, tmp_path)

        bundle = tmp_path / "bundle"
        export_arkiv(src, bundle, include_history=True)

        # Corrupt the bundle: rewrite every visit's history_url_uri to
        # point at a nonexistent history-url.
        import json as _json
        jsonl = bundle / "records.jsonl"
        lines = jsonl.read_text().splitlines()
        rewritten = []
        for line in lines:
            if not line.strip():
                continue
            rec = _json.loads(line)
            if rec.get("kind") == "visit":
                rec["history_url_uri"] = "bookmark-memex://history-url/0000000000000000"
            rewritten.append(_json.dumps(rec))
        jsonl.write_text("\n".join(rewritten) + "\n")

        dst_path = str(tmp_path / "dst.db")
        dst = Database(dst_path)
        stats = import_arkiv(dst, bundle)

        assert stats["visits_seen"] == 3
        assert stats["visits_added"] == 0
        assert stats["visits_dropped_unknown_parent"] == 3
