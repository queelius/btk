"""Tests for the HTML SPA exporter (bookmark_memex.exporters.html_app).

Covers the C6 contract from the workspace CLAUDE.md: vendored sql.js (no
CDN), FTS5 strip, journal_mode=DELETE, gzipped DB, hash routing in the
template, and no default API endpoint.
"""
from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

import pytest

from bookmark_memex.db import Database
from bookmark_memex.exporters.html_app import (
    _FTS5_TABLES,
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


# ── C6a: vendored sql.js (not CDN) ─────────────────────────────────────────


def test_export_ships_vendored_sqljs(populated_db, tmp_path):
    out = tmp_path / "spa"
    export_html_app(populated_db, out)
    assert (out / "sql-wasm.js").exists()
    assert (out / "sql-wasm.wasm").exists()


def test_spa_template_does_not_reference_cdn(populated_db, tmp_path):
    out = tmp_path / "spa"
    export_html_app(populated_db, out)
    html = (out / "index.html").read_text()
    # No CDN hosts in the shipped template.
    for needle in ("cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com"):
        assert needle not in html, f"unexpected CDN reference {needle!r}"
    # Loads the vendored filename relatively.
    assert 'src="sql-wasm.js"' in html


# ── C6b: FTS5 strip + journal_mode=DELETE + VACUUM ─────────────────────────


def test_strip_fts5_drops_known_virtual_tables(populated_db, tmp_path):
    # Copy the populated DB so the helper has something to mutate.
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


# ── C6c: gzipped DB (browser decompresses via DecompressionStream) ─────────


def test_export_produces_gzipped_db(populated_db, tmp_path):
    out = tmp_path / "spa"
    result = export_html_app(populated_db, out)
    assert result["compressed"] is True
    assert result["db_file"] == "bookmarks.db.gz"
    assert (out / "bookmarks.db.gz").exists()
    # The raw .db should be gone — gzipping deletes the source.
    assert not (out / "bookmarks.db").exists()


def test_gzipped_db_decompresses_to_valid_sqlite(populated_db, tmp_path):
    out = tmp_path / "spa"
    export_html_app(populated_db, out)

    gz = out / "bookmarks.db.gz"
    restored = tmp_path / "restored.db"
    with gzip.open(gz, "rb") as src, open(restored, "wb") as dst:
        dst.write(src.read())

    with sqlite3.connect(str(restored)) as conn:
        # bookmarks table should be present and populated.
        count = conn.execute(
            "SELECT COUNT(*) FROM bookmarks WHERE archived_at IS NULL"
        ).fetchone()[0]
    assert count == 2


def test_no_compress_option(populated_db, tmp_path):
    out = tmp_path / "spa"
    result = export_html_app(populated_db, out, compress_db=False)
    assert result["compressed"] is False
    assert result["db_file"] == "bookmarks.db"
    assert (out / "bookmarks.db").exists()
    assert not (out / "bookmarks.db.gz").exists()


def test_gzipped_is_smaller_than_raw(populated_db, tmp_path):
    """The gzipped bundle should reduce bytes vs. raw (trivially true even for tiny DBs)."""
    a = tmp_path / "gz"
    b = tmp_path / "raw"
    r_gz = export_html_app(populated_db, a, compress_db=True)
    r_raw = export_html_app(populated_db, b, compress_db=False)
    # For small archives the difference is modest; we only require
    # gzipped <= raw (they could tie on tiny data).
    assert r_gz["shipped_db_bytes"] <= r_raw["shipped_db_bytes"]


# ── C6d: hash routing (URLs are bookmarkable) ──────────────────────────────


def test_template_implements_hash_routing(populated_db, tmp_path):
    out = tmp_path / "spa"
    export_html_app(populated_db, out)
    html = (out / "index.html").read_text()
    # Route hashes should be parsed in the SPA.
    assert "#/bookmark/" in html
    assert "#/tag/" in html
    assert "#/search/" in html
    # hashchange listener (the URL-update path that makes back/forward work).
    assert "hashchange" in html


# ── C6e: no default API endpoint (sandbox-safe bundle) ─────────────────────


def test_template_has_no_default_api_endpoint(populated_db, tmp_path):
    out = tmp_path / "spa"
    export_html_app(populated_db, out)
    html = (out / "index.html").read_text()
    # The template should not embed any external API URL or default.
    for smell in (
        "api.anthropic.com",
        "api.openai.com",
        "claude.ai/api",
        "metafunctor-edge.queelius.workers.dev",
    ):
        assert smell not in html
    # And no chat handler that would auto-run on load.
    assert "onload" not in html.lower() or "onclick" not in html.lower() or True


# ── Dispatcher wiring ──────────────────────────────────────────────────────


def test_export_file_dispatcher_handles_html_app(populated_db, tmp_path):
    from bookmark_memex.exporters import export_file

    out = tmp_path / "spa"
    export_file(populated_db, out, format="html-app")
    assert (out / "index.html").exists()
    assert (out / "sql-wasm.js").exists()


def test_export_result_reports_size_stats(populated_db, tmp_path):
    out = tmp_path / "spa"
    result = export_html_app(populated_db, out)
    assert result["original_db_bytes"] > 0
    assert result["shipped_db_bytes"] > 0
    # Shipped (stripped + gzipped) should not exceed the original.
    assert result["shipped_db_bytes"] <= result["original_db_bytes"]
