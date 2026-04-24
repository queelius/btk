"""Tests for the HTML SPA exporter (bookmark_memex.exporters.html_app).

Covers the C6 contract for both output modes:

- single-file (default): sql.js + wasm + gzipped DB inlined as base64
- directory (opt-in): sibling files + bookmarks.db.gz

Both modes: vendored sql.js (no CDN), FTS5 shadow tables stripped,
journal_mode=DELETE on the shipped DB, hash routing in the template,
no default API endpoint.
"""
from __future__ import annotations

import base64
import gzip
import re
import sqlite3
from pathlib import Path

import pytest

from bookmark_memex.db import Database
from bookmark_memex.exporters.html_app import (
    _FTS5_TABLES,
    _prepare_db_bytes,
    _strip_fts5_and_vacuum,
    export_html_app,
)


@pytest.fixture
def populated_db(tmp_db_path):
    db = Database(tmp_db_path)
    py = db.add(
        "https://docs.python.org/3/",
        title="Python Documentation",
        tags=["programming/python", "documentation"],
        starred=True,
    )
    db.add(
        "https://github.com",
        title="GitHub",
        tags=["development", "git"],
        pinned=True,
    )
    db.annotate(py.unique_id, "One of the best reference docs.")
    return db


# ════════════════════════════════════════════════════════════════════
# Shared contract: FTS5 strip + journal_mode (runs before either mode)
# ════════════════════════════════════════════════════════════════════


def test_strip_fts5_drops_known_virtual_tables(populated_db, tmp_path):
    src = Path(populated_db.path)
    copy = tmp_path / "copy.db"
    copy.write_bytes(src.read_bytes())

    _strip_fts5_and_vacuum(copy)

    with sqlite3.connect(str(copy)) as conn:
        names = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for fts in _FTS5_TABLES:
        assert fts not in names, f"FTS5 table {fts!r} should have been dropped"


def test_strip_fts5_sets_journal_mode_delete(populated_db, tmp_path):
    src = Path(populated_db.path)
    copy = tmp_path / "copy.db"
    copy.write_bytes(src.read_bytes())

    _strip_fts5_and_vacuum(copy)

    with sqlite3.connect(str(copy)) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "delete"


def test_prepare_db_bytes_produces_valid_sqlite(populated_db, tmp_path):
    """The private helper returns stripped DB bytes without touching the source."""
    src_before = Path(populated_db.path).read_bytes()

    data = _prepare_db_bytes(Path(populated_db.path))

    # Source must not have been mutated.
    src_after = Path(populated_db.path).read_bytes()
    assert src_before == src_after

    # The returned bytes open as a SQLite database.
    restored = tmp_path / "restored.db"
    restored.write_bytes(data)
    with sqlite3.connect(str(restored)) as conn:
        names = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        # Core tables present, FTS5 shadows gone.
        assert "bookmarks" in names
        for fts in _FTS5_TABLES:
            assert fts not in names


# ════════════════════════════════════════════════════════════════════
# Single-file mode (default)
# ════════════════════════════════════════════════════════════════════


def test_single_file_is_default_mode(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    result = export_html_app(populated_db, out)
    assert result["mode"] == "single-file"
    assert out.exists()
    # Only the .html is produced; no sibling files.
    assert list(out.parent.iterdir()) == [out]


def test_single_file_auto_appends_html_extension(populated_db, tmp_path):
    out = tmp_path / "archive"
    result = export_html_app(populated_db, out)
    assert Path(result["path"]).suffix == ".html"
    assert Path(result["path"]).exists()


def test_single_file_inlines_sqljs(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    export_html_app(populated_db, out)
    html = out.read_text(encoding="utf-8")
    # External src attr gone; function body present instead.
    assert '<script src="sql-wasm.js"></script>' not in html
    assert "initSqlJs" in html  # sql.js API exported globally


def test_single_file_inlines_wasm_as_base64(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    export_html_app(populated_db, out)
    html = out.read_text(encoding="utf-8")
    m = re.search(
        r'<script id="bm-wasm-b64" type="application/base64">\s*([A-Za-z0-9+/=\s]+?)\s*</script>',
        html,
    )
    assert m, "wasm base64 script element not found"
    b64_payload = m.group(1).strip()
    # Non-trivial payload (wasm is ~650 KB base64 → ~870 KB).
    assert len(b64_payload) > 100_000
    # Decodes to a wasm magic-number header.
    blob = base64.b64decode(b64_payload)
    assert blob[:4] == b"\x00asm"


def test_single_file_inlines_gzipped_db_as_base64(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    export_html_app(populated_db, out)
    html = out.read_text(encoding="utf-8")
    m = re.search(
        r'<script id="bm-db-b64" type="application/base64">\s*([A-Za-z0-9+/=\s]+?)\s*</script>',
        html,
    )
    assert m, "db base64 script element not found"
    gz_bytes = base64.b64decode(m.group(1).strip())
    # gzip magic header
    assert gz_bytes[:2] == b"\x1f\x8b"
    # Decompressed payload opens as SQLite.
    raw = gzip.decompress(gz_bytes)
    sqlite_path = tmp_path / "inline.db"
    sqlite_path.write_bytes(raw)
    with sqlite3.connect(str(sqlite_path)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM bookmarks WHERE archived_at IS NULL"
        ).fetchone()[0]
    assert count == 2


def test_single_file_no_cdn_references(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    export_html_app(populated_db, out)
    html = out.read_text(encoding="utf-8")
    for needle in ("cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com"):
        assert needle not in html, f"unexpected CDN reference {needle!r}"


def test_single_file_has_no_default_api_endpoint(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    export_html_app(populated_db, out)
    html = out.read_text(encoding="utf-8")
    for smell in (
        "api.anthropic.com",
        "api.openai.com",
        "claude.ai/api",
        "metafunctor-edge.queelius.workers.dev",
    ):
        assert smell not in html


def test_single_file_hash_routing_present(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    export_html_app(populated_db, out)
    html = out.read_text(encoding="utf-8")
    assert "#/bookmark/" in html
    assert "#/tag/" in html
    assert "#/search/" in html
    assert "hashchange" in html


def test_single_file_reports_size_stats(populated_db, tmp_path):
    out = tmp_path / "archive.html"
    result = export_html_app(populated_db, out)
    assert result["original_db_bytes"] > 0
    assert result["embedded_db_bytes"] > 0
    # Embedded (stripped + gzipped) ≤ original.
    assert result["embedded_db_bytes"] <= result["original_db_bytes"]
    # html_bytes is at least as large as the embedded DB (base64 expansion
    # means more, but monotonic).
    assert result["html_bytes"] >= result["embedded_db_bytes"]


# ════════════════════════════════════════════════════════════════════
# Directory mode (opt-in via single_file=False)
# ════════════════════════════════════════════════════════════════════


def test_directory_mode_ships_vendored_sqljs_siblings(populated_db, tmp_path):
    out = tmp_path / "spa"
    result = export_html_app(populated_db, out, single_file=False)
    assert result["mode"] == "dir"
    assert (out / "sql-wasm.js").exists()
    assert (out / "sql-wasm.wasm").exists()


def test_directory_mode_template_keeps_src_reference(populated_db, tmp_path):
    out = tmp_path / "spa"
    export_html_app(populated_db, out, single_file=False)
    html = (out / "index.html").read_text(encoding="utf-8")
    # In directory mode the runtime loader fetches siblings, so the
    # <script src=...> reference must remain.
    assert '<script src="sql-wasm.js"></script>' in html


def test_directory_mode_produces_gzipped_db_by_default(populated_db, tmp_path):
    out = tmp_path / "spa"
    result = export_html_app(populated_db, out, single_file=False)
    assert result["compressed"] is True
    assert result["db_file"] == "bookmarks.db.gz"
    assert (out / "bookmarks.db.gz").exists()
    assert not (out / "bookmarks.db").exists()


def test_directory_mode_gzipped_decompresses_to_valid_sqlite(populated_db, tmp_path):
    out = tmp_path / "spa"
    export_html_app(populated_db, out, single_file=False)
    gz = out / "bookmarks.db.gz"
    restored = tmp_path / "restored.db"
    with gzip.open(gz, "rb") as src, open(restored, "wb") as dst:
        dst.write(src.read())
    with sqlite3.connect(str(restored)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM bookmarks WHERE archived_at IS NULL"
        ).fetchone()[0]
    assert count == 2


def test_directory_mode_no_compress_option(populated_db, tmp_path):
    out = tmp_path / "spa"
    result = export_html_app(populated_db, out, single_file=False, compress_db=False)
    assert result["compressed"] is False
    assert result["db_file"] == "bookmarks.db"
    assert (out / "bookmarks.db").exists()
    assert not (out / "bookmarks.db.gz").exists()


# ════════════════════════════════════════════════════════════════════
# Dispatcher wiring
# ════════════════════════════════════════════════════════════════════


def test_export_file_dispatcher_defaults_to_single_file(populated_db, tmp_path):
    from bookmark_memex.exporters import export_file

    out = tmp_path / "archive.html"
    export_file(populated_db, out, format="html-app")
    assert out.exists()
    # No sibling files in single-file mode.
    siblings = [p for p in out.parent.iterdir() if p != out]
    assert not siblings


def test_export_file_dispatcher_directory_mode(populated_db, tmp_path):
    from bookmark_memex.exporters import export_file

    out = tmp_path / "spa"
    export_file(populated_db, out, format="html-app", single_file=False)
    assert (out / "index.html").exists()
    assert (out / "sql-wasm.js").exists()
    assert (out / "sql-wasm.wasm").exists()


def test_export_file_dispatcher_ignores_single_file_for_other_formats(populated_db, tmp_path):
    """single_file kwarg from the CLI must not reach other exporters."""
    from bookmark_memex.exporters import export_file

    out = tmp_path / "out.json"
    # Would raise TypeError if JSON exporter received single_file=...
    export_file(populated_db, out, format="json", single_file=True)
    assert out.exists()
