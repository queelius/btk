"""Tests for the arkiv exporter's ``include_history`` opt-in.

Covers the privacy contract:
- History is NEVER present without ``include_history=True``.
- Every kind in the bundle is documented in schema.yaml (no dangling
  docs for kinds that didn't actually appear).
- Marginalia attached to history records surface their parent URIs in
  the bundle even when ``include_history=False``.
- Visit referrer chains (``from_visit_uri``) round-trip through the
  bundle.
- CLI ``--include-history`` flag plumbs through to the exporter.
"""
from __future__ import annotations

import json
import uuid
import zipfile
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bookmark_memex.db import Database
from bookmark_memex.exporters.arkiv import export_arkiv
from bookmark_memex.importers.browser import BrowserProfile, ChromeImporter
from bookmark_memex.importers.browser_history import import_history
from bookmark_memex.models import Marginalia


# ---------------------------------------------------------------------------
# Fixture helpers (minimal fake Chrome history so we don't depend on the OS)
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
    """Load a small fake Chrome profile into *db*."""
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
                "transition": 1,
                "from_visit": 0,
            },
            {
                "visit_id": 2,
                "url": "https://result.example.com/a",
                "title": "Result A",
                "visited_at": datetime(2026, 4, 20, 9, 0, 5),
                "transition": 0,
                "from_visit": 1,
            },
        ],
    )
    fake_profile = BrowserProfile(
        name="Default", path=profile, browser="Chrome", is_default=True
    )
    with patch.object(ChromeImporter, "find_profiles", return_value=[fake_profile]):
        import_history(db, browser="chrome")


def _read_bundle_jsonl(bundle_path: Path) -> list[dict]:
    if bundle_path.is_dir():
        text = (bundle_path / "records.jsonl").read_text()
    elif str(bundle_path).endswith(".zip"):
        with zipfile.ZipFile(bundle_path) as zf:
            text = zf.read("records.jsonl").decode("utf-8")
    else:
        raise AssertionError(f"unexpected bundle shape {bundle_path}")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _read_bundle_schema(bundle_path: Path) -> dict:
    if bundle_path.is_dir():
        return yaml.safe_load((bundle_path / "schema.yaml").read_text())
    with zipfile.ZipFile(bundle_path) as zf:
        return yaml.safe_load(zf.read("schema.yaml").decode("utf-8"))


# ---------------------------------------------------------------------------
# Privacy-default: history off unless asked for
# ---------------------------------------------------------------------------


class TestHistoryOptInDefault:
    def test_history_absent_by_default(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        db = Database(tmp_db_path)
        db.add("https://saved.example.com/", title="Saved")
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        result = export_arkiv(db, out)
        records = _read_bundle_jsonl(out)

        kinds = {r["kind"] for r in records}
        assert "bookmark" in kinds
        assert "history-url" not in kinds
        assert "visit" not in kinds

        assert "history-url" not in result["counts"]
        assert "visit" not in result["counts"]

    def test_history_present_when_opted_in(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        db = Database(tmp_db_path)
        db.add("https://saved.example.com/", title="Saved")
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle-with-history"
        result = export_arkiv(db, out, include_history=True)
        records = _read_bundle_jsonl(out)

        kinds = {r["kind"] for r in records}
        assert {"bookmark", "history-url", "visit"}.issubset(kinds)

        assert result["counts"]["history-url"] == 2
        assert result["counts"]["visit"] == 2


# ---------------------------------------------------------------------------
# Record shapes
# ---------------------------------------------------------------------------


class TestRecordShapes:
    def test_history_url_fields(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        db = Database(tmp_db_path)
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        export_arkiv(db, out, include_history=True)
        records = _read_bundle_jsonl(out)

        hu = next(r for r in records if r["kind"] == "history-url")
        assert hu["uri"].startswith("bookmark-memex://history-url/")
        assert hu["url"].startswith("https://")
        assert hu["visit_count"] == 1
        assert hu["first_visited"] is not None
        assert hu["last_visited"] is not None

    def test_visit_fields_and_referrer_chain(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        db = Database(tmp_db_path)
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        export_arkiv(db, out, include_history=True)
        records = _read_bundle_jsonl(out)

        visits = [r for r in records if r["kind"] == "visit"]
        assert len(visits) == 2
        # Sorted by visited_at ASC in the export. The second visit was
        # navigated to from the first.
        assert visits[0]["transition"] == "typed"
        assert visits[0]["from_visit_uri"] is None
        assert visits[1]["transition"] == "link"
        assert visits[1]["from_visit_uri"] == visits[0]["uri"]

    def test_visit_orders_after_history_url_in_stream(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """A marginalia-like consumer can assume parents appear first.

        The exporter orders: bookmarks, history-urls, visits, marginalia.
        This test guards that order so downstream code can stream-parse.
        """
        db = Database(tmp_db_path)
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        export_arkiv(db, out, include_history=True)
        records = _read_bundle_jsonl(out)

        # Every visit's history_url_uri must have already appeared as an
        # earlier history-url record.
        seen_history_urls: set[str] = set()
        for r in records:
            if r["kind"] == "history-url":
                seen_history_urls.add(r["uri"])
            elif r["kind"] == "visit":
                assert r["history_url_uri"] in seen_history_urls


# ---------------------------------------------------------------------------
# Marginalia on history records
# ---------------------------------------------------------------------------


class TestMarginaliaOnHistory:
    def test_marginalia_surfaces_history_url_uri_even_without_include(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """A note attached to a history URL still references its parent
        URI in its marginalia record, even when history itself is not
        exported. This lets a note stay meaningful in a
        bookmarks-only bundle.
        """
        db = Database(tmp_db_path)
        _populate_history(db, tmp_path)

        with db._session() as s:
            hu_row = s.execute(
                __import__(
                    "sqlalchemy",
                    fromlist=["text"],
                ).text(
                    "SELECT id, unique_id FROM history_urls LIMIT 1"
                )
            ).fetchone()
        hu_id, hu_unique_id = hu_row

        mid = uuid.uuid4().hex
        with db._session() as s:
            s.add(Marginalia(id=mid, history_url_id=hu_id, text="observational note"))

        out = tmp_path / "bundle"
        export_arkiv(db, out, include_history=False)
        records = _read_bundle_jsonl(out)

        marg = next(r for r in records if r["kind"] == "marginalia")
        assert marg["text"] == "observational note"
        assert marg["bookmark_uri"] is None
        assert marg["history_url_uri"] == (
            f"bookmark-memex://history-url/{hu_unique_id}"
        )

    def test_marginalia_history_uris_match_between_bundles(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """Whether or not include_history is set, the marginalia's
        history_url_uri must be the same string.
        """
        db = Database(tmp_db_path)
        _populate_history(db, tmp_path)

        with db._session() as s:
            from sqlalchemy import text as _text
            hu_row = s.execute(
                _text("SELECT id FROM history_urls LIMIT 1")
            ).fetchone()
        hu_id = hu_row[0]

        mid = uuid.uuid4().hex
        with db._session() as s:
            s.add(Marginalia(id=mid, history_url_id=hu_id, text="n"))

        out_off = tmp_path / "off"
        out_on = tmp_path / "on"
        export_arkiv(db, out_off, include_history=False)
        export_arkiv(db, out_on, include_history=True)

        marg_off = next(
            r for r in _read_bundle_jsonl(out_off) if r["kind"] == "marginalia"
        )
        marg_on = next(
            r for r in _read_bundle_jsonl(out_on) if r["kind"] == "marginalia"
        )
        assert marg_off["history_url_uri"] == marg_on["history_url_uri"]


# ---------------------------------------------------------------------------
# schema.yaml
# ---------------------------------------------------------------------------


class TestSchemaYaml:
    def test_schema_omits_history_kinds_when_not_exported(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        db = Database(tmp_db_path)
        db.add("https://saved.example.com/", title="Saved")
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        export_arkiv(db, out, include_history=False)
        schema = _read_bundle_schema(out)

        assert "bookmark" in schema["kinds"]
        # Only kinds that are actually present should be documented.
        assert "history-url" not in schema["kinds"]
        assert "visit" not in schema["kinds"]

    def test_schema_includes_history_kinds_when_exported(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        db = Database(tmp_db_path)
        db.add("https://saved.example.com/", title="Saved")
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        export_arkiv(db, out, include_history=True)
        schema = _read_bundle_schema(out)

        assert {"bookmark", "history-url", "visit"}.issubset(schema["kinds"].keys())
        assert schema["counts"]["history-url"] == 2
        assert schema["counts"]["visit"] == 2


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


class TestCLIExportHistoryFlag:
    def test_flag_defaults_off(self, tmp_db_path: str, tmp_path: Path) -> None:
        from bookmark_memex.cli import cmd_export

        db = Database(tmp_db_path)
        db.add("https://saved.example.com/", title="Saved")
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        args = Namespace(
            db=tmp_db_path,
            path=str(out),
            format="arkiv",
            as_dir=False,
            single=False,
            include_history=False,
        )
        cmd_export(args)

        records = _read_bundle_jsonl(out)
        kinds = {r["kind"] for r in records}
        assert "history-url" not in kinds

    def test_flag_on(self, tmp_db_path: str, tmp_path: Path) -> None:
        from bookmark_memex.cli import cmd_export

        db = Database(tmp_db_path)
        db.add("https://saved.example.com/", title="Saved")
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle"
        args = Namespace(
            db=tmp_db_path,
            path=str(out),
            format="arkiv",
            as_dir=False,
            single=False,
            include_history=True,
        )
        cmd_export(args)

        records = _read_bundle_jsonl(out)
        kinds = {r["kind"] for r in records}
        assert "history-url" in kinds
        assert "visit" in kinds

    def test_flag_ignored_by_html_app(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        """--include-history on an html-app export must not break things."""
        from bookmark_memex.cli import cmd_export

        db = Database(tmp_db_path)
        db.add("https://saved.example.com/", title="Saved")

        out = tmp_path / "spa.html"
        args = Namespace(
            db=tmp_db_path,
            path=str(out),
            format="html-app",
            as_dir=False,
            single=True,
            include_history=True,
        )
        # Must not raise: export_file should strip include_history before
        # passing to html-app.
        cmd_export(args)
        assert out.exists()


# ---------------------------------------------------------------------------
# Bundle formats (zip round-trip of a history-bearing bundle)
# ---------------------------------------------------------------------------


class TestBundleFormats:
    def test_zip_bundle_contains_history(
        self, tmp_db_path: str, tmp_path: Path
    ) -> None:
        db = Database(tmp_db_path)
        _populate_history(db, tmp_path)

        out = tmp_path / "bundle.zip"
        export_arkiv(db, out, include_history=True)
        assert out.exists()

        records = _read_bundle_jsonl(out)
        kinds = {r["kind"] for r in records}
        assert {"history-url", "visit"}.issubset(kinds)
