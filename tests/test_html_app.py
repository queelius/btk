"""Tests for the sql.js HTML-app export module."""
import base64
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from btk.models import Bookmark, Tag, BookmarkMedia


def _make_bookmark(**kwargs):
    """Create a Bookmark with sensible defaults for testing."""
    defaults = {
        "id": 1,
        "unique_id": "abc12345",
        "url": "https://example.com",
        "title": "Example",
        "description": "A test bookmark",
        "bookmark_type": "bookmark",
        "added": datetime(2025, 1, 15, tzinfo=timezone.utc),
        "stars": False,
        "pinned": False,
        "archived": False,
        "reachable": True,
        "visit_count": 5,
        "last_visited": datetime(2025, 6, 1, tzinfo=timezone.utc),
        "favicon_data": None,
        "favicon_mime_type": None,
        "extra_data": {"reading_queue": True},
    }
    defaults.update(kwargs)
    b = Bookmark(**{k: v for k, v in defaults.items() if k != "tags"})
    b.tags = kwargs.get("tags", [])
    return b


def _make_tag(id, name, color=None):
    return Tag(id=id, name=name, color=color)


def _load_db_bytes(db_bytes):
    """Load serialized DB bytes into an in-memory connection (Python 3.8+ compatible)."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(db_bytes)
        tmp_path = tmp.name
    try:
        conn = sqlite3.connect(tmp_path)
    finally:
        os.unlink(tmp_path)
    return conn


class TestBuildExportDb:
    """Test export database creation."""

    def test_empty_export(self):
        from btk.html_app.builder import build_export_db
        db_bytes = build_export_db([])
        assert isinstance(db_bytes, bytes)
        assert len(db_bytes) > 0

        # Verify schema exists
        conn = _load_db_bytes(db_bytes)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        assert "bookmarks" in tables
        assert "tags" in tables
        assert "bookmark_tags" in tables
        assert "bookmark_media" in tables
        conn.close()

    def test_single_bookmark(self):
        from btk.html_app.builder import build_export_db
        tag = _make_tag(1, "python", "#3776AB")
        b = _make_bookmark(id=1, tags=[tag])
        db_bytes = build_export_db([b])

        conn = _load_db_bytes(db_bytes)
        conn.row_factory = sqlite3.Row

        # Check bookmark
        row = conn.execute("SELECT * FROM bookmarks WHERE id = 1").fetchone()
        assert row["url"] == "https://example.com"
        assert row["title"] == "Example"
        assert row["source_db"] == "default"
        assert row["visit_count"] == 5

        # Check tag
        tag_row = conn.execute("SELECT * FROM tags WHERE name = 'python'").fetchone()
        assert tag_row is not None
        assert tag_row["color"] == "#3776AB"

        # Check association
        bt_row = conn.execute("SELECT * FROM bookmark_tags").fetchone()
        assert bt_row["bookmark_id"] == 1
        assert bt_row["tag_id"] == tag_row["id"]
        conn.close()

    def test_extra_data_serialized_as_json(self):
        from btk.html_app.builder import build_export_db
        b = _make_bookmark(extra_data={"reading_queue": True, "priority": 1})
        db_bytes = build_export_db([b])

        conn = _load_db_bytes(db_bytes)
        row = conn.execute("SELECT extra_data FROM bookmarks WHERE id = 1").fetchone()
        parsed = json.loads(row[0])
        assert parsed["reading_queue"] is True
        assert parsed["priority"] == 1
        conn.close()

    def test_favicon_blob_preserved(self):
        from btk.html_app.builder import build_export_db
        favicon = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        b = _make_bookmark(favicon_data=favicon, favicon_mime_type="image/png")
        db_bytes = build_export_db([b])

        conn = _load_db_bytes(db_bytes)
        row = conn.execute("SELECT favicon_data, favicon_mime_type FROM bookmarks WHERE id = 1").fetchone()
        assert row[0] == favicon
        assert row[1] == "image/png"
        conn.close()

    def test_bookmark_media_exported(self):
        from btk.html_app.builder import build_export_db
        media = BookmarkMedia(
            id=1, bookmark_id=1,
            media_type="video", media_source="youtube",
            media_id="dQw4w9WgXcQ", author_name="Rick Astley"
        )
        b = _make_bookmark(id=1)
        b.media = media
        db_bytes = build_export_db([b])

        conn = _load_db_bytes(db_bytes)
        row = conn.execute("SELECT * FROM bookmark_media WHERE bookmark_id = 1").fetchone()
        assert row is not None
        conn.close()

    def test_source_db_default(self):
        from btk.html_app.builder import build_export_db
        b = _make_bookmark()
        db_bytes = build_export_db([b])
        conn = _load_db_bytes(db_bytes)
        row = conn.execute("SELECT source_db FROM bookmarks").fetchone()
        assert row[0] == "default"
        conn.close()


class TestMultiDbMerge:
    """Test multi-database merge with ID remapping."""

    def test_include_dbs_sets_source_db(self):
        from btk.html_app.builder import build_export_db
        main_b = _make_bookmark(id=1, url="https://main.com", unique_id="main0001")
        hist_b = _make_bookmark(id=1, url="https://hist.com", unique_id="hist0001")

        include_dbs = {"history": [hist_b]}
        db_bytes = build_export_db([main_b], include_dbs=include_dbs)

        conn = _load_db_bytes(db_bytes)
        rows = conn.execute("SELECT url, source_db FROM bookmarks ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0] == ("https://main.com", "default")
        assert rows[1] == ("https://hist.com", "history")
        conn.close()

    def test_id_remapping_avoids_collision(self):
        from btk.html_app.builder import build_export_db
        main_b = _make_bookmark(id=1, url="https://main.com", unique_id="main0001")
        hist_b = _make_bookmark(id=1, url="https://hist.com", unique_id="hist0001")

        include_dbs = {"history": [hist_b]}
        db_bytes = build_export_db([main_b], include_dbs=include_dbs)

        conn = _load_db_bytes(db_bytes)
        ids = [r[0] for r in conn.execute("SELECT id FROM bookmarks ORDER BY id").fetchall()]
        assert len(ids) == 2
        assert ids[0] != ids[1]  # No collision
        conn.close()

    def test_tags_merged_across_databases(self):
        from btk.html_app.builder import build_export_db
        tag_py = _make_tag(1, "python")
        main_b = _make_bookmark(id=1, url="https://main.com", unique_id="main0001", tags=[tag_py])

        tag_py2 = _make_tag(5, "python")  # Same name, different ID
        hist_b = _make_bookmark(id=1, url="https://hist.com", unique_id="hist0001", tags=[tag_py2])

        include_dbs = {"history": [hist_b]}
        db_bytes = build_export_db([main_b], include_dbs=include_dbs)

        conn = _load_db_bytes(db_bytes)
        # Should have only ONE tag row for "python"
        tag_rows = conn.execute("SELECT * FROM tags WHERE name = 'python'").fetchall()
        assert len(tag_rows) == 1
        # Both bookmarks should reference it
        bt_count = conn.execute("SELECT COUNT(*) FROM bookmark_tags").fetchone()[0]
        assert bt_count == 2
        conn.close()

    def test_bookmark_tags_fk_remapped(self):
        from btk.html_app.builder import build_export_db
        tag = _make_tag(1, "ai")
        hist_b = _make_bookmark(id=42, url="https://hist.com", unique_id="hist0042", tags=[tag])

        include_dbs = {"history": [hist_b]}
        db_bytes = build_export_db([], include_dbs=include_dbs)

        conn = _load_db_bytes(db_bytes)
        # The bookmark_tags.bookmark_id should match the remapped bookmark id, not 42
        bt_row = conn.execute("SELECT bookmark_id FROM bookmark_tags").fetchone()
        bm_row = conn.execute("SELECT id FROM bookmarks").fetchone()
        assert bt_row[0] == bm_row[0]
        conn.close()


class TestEncodeExportDb:
    """Test base64 encoding utility."""

    def test_encode_returns_base64_string(self):
        from btk.html_app.builder import build_export_db, encode_export_db
        db_bytes = build_export_db([])
        encoded = encode_export_db(db_bytes)
        assert isinstance(encoded, str)
        # Should be valid base64
        decoded = base64.b64decode(encoded)
        assert decoded == db_bytes


class TestAssembleEmbedded:
    """Test embedded (single-file) HTML assembly."""

    def test_produces_valid_html(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_sql_wasm_js(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert "initSqlJs" in html or "sql-wasm" in html.lower()

    def test_contains_base64_db(self):
        from btk.html_app.builder import build_export_db, encode_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([_make_bookmark()])
        html = assemble_embedded(db_bytes, views={})
        encoded = encode_export_db(db_bytes)
        assert encoded in html

    def test_contains_wasm_data_uri(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert "data:application/wasm;base64," in html

    def test_contains_app_css(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert "<style>" in html
        # Should contain actual CSS content (e.g., the root variables)
        assert "--bg-primary" in html

    def test_views_embedded_as_json(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        views = {"starred": {"description": "Starred bookmarks", "bookmark_ids": [1, 2]}}
        html = assemble_embedded(db_bytes, views=views)
        assert '"starred"' in html
        assert 'id="btk-views"' in html

    def test_contains_query_modal(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert 'id="query-modal"' in html
        assert 'id="query-input"' in html
        assert 'id="query-results"' in html

    def test_contains_db_filter_section(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert 'id="db-filter-section"' in html

    def test_load_mode_embedded(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert '"embedded"' in html

    def test_contains_btk_db_element(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_embedded
        db_bytes = build_export_db([])
        html = assemble_embedded(db_bytes, views={})
        assert 'id="btk-db"' in html


class TestAssembleDirectory:
    """Test directory-mode output."""

    def test_creates_directory_structure(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_directory
        db_bytes = build_export_db([])

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "export"
            assemble_directory(db_bytes, outdir, views={})

            assert (outdir / "index.html").exists()
            assert (outdir / "sql-wasm.js").exists()
            assert (outdir / "sql-wasm.wasm").exists()
            assert (outdir / "export.db").exists()

    def test_db_file_matches_bytes(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_directory
        b = _make_bookmark()
        db_bytes = build_export_db([b])

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "export"
            assemble_directory(db_bytes, outdir, views={})

            with open(outdir / "export.db", "rb") as f:
                assert f.read() == db_bytes

    def test_index_html_uses_fetch(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_directory
        db_bytes = build_export_db([])

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "export"
            assemble_directory(db_bytes, outdir, views={})

            html = (outdir / "index.html").read_text()
            assert "fetch(" in html
            # Should NOT have base64-embedded db or wasm
            assert "data:application/wasm;base64," not in html

    def test_index_html_references_external_sqljs(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_directory
        db_bytes = build_export_db([])

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "export"
            assemble_directory(db_bytes, outdir, views={})

            html = (outdir / "index.html").read_text()
            assert 'src="sql-wasm.js"' in html

    def test_load_mode_directory(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_directory
        db_bytes = build_export_db([])

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "export"
            assemble_directory(db_bytes, outdir, views={})

            html = (outdir / "index.html").read_text()
            assert '"directory"' in html

    def test_no_base64_db_in_directory_mode(self):
        from btk.html_app.builder import build_export_db, encode_export_db
        from btk.html_app.template import assemble_directory
        b = _make_bookmark()
        db_bytes = build_export_db([b])
        encoded = encode_export_db(db_bytes)

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "export"
            assemble_directory(db_bytes, outdir, views={})

            html = (outdir / "index.html").read_text()
            assert encoded not in html
            assert 'id="btk-db"' not in html

    def test_views_embedded_in_directory_mode(self):
        from btk.html_app.builder import build_export_db
        from btk.html_app.template import assemble_directory
        db_bytes = build_export_db([])
        views = {"recent": {"description": "Recent", "bookmark_ids": [3]}}

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "export"
            assemble_directory(db_bytes, outdir, views=views)

            html = (outdir / "index.html").read_text()
            assert '"recent"' in html
