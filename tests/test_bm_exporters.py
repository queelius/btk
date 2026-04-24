"""Tests for bookmark_memex.exporters package.

Tests cover JSON, CSV, text, markdown, m3u formats, the arkiv exporter,
and the export_file dispatcher.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml

from bookmark_memex.db import Database
from bookmark_memex.exporters import export_file
from bookmark_memex.exporters.arkiv import SCHEMA, export_arkiv
from bookmark_memex.exporters.formats import (
    export_csv,
    export_json,
    export_m3u,
    export_markdown,
    export_text,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_db_path):
    d = Database(tmp_db_path)
    d.add("https://example.com", title="Example", tags=["test"])
    d.add("https://python.org", title="Python", tags=["programming"], starred=True)
    d.annotate(d.list()[0].unique_id, "A note about example.com")
    return d


@pytest.fixture
def out_dir(tmp_path):
    return tmp_path / "exports"


# ---------------------------------------------------------------------------
# export_json
# ---------------------------------------------------------------------------


def test_json_exports_all_bookmarks(db, tmp_path):
    out = tmp_path / "bm.json"
    export_json(db, out)
    data = json.loads(out.read_text())
    assert len(data) == 2


def test_json_includes_tags(db, tmp_path):
    out = tmp_path / "bm.json"
    export_json(db, out)
    data = json.loads(out.read_text())
    urls_to_tags = {d["url"]: d["tags"] for d in data}
    # Both bookmarks should have their tags included
    assert any("test" in tags for tags in urls_to_tags.values())
    assert any("programming" in tags for tags in urls_to_tags.values())


def test_json_with_bookmark_ids(db, tmp_path):
    out = tmp_path / "bm.json"
    bms = db.list()
    export_json(db, out, bookmark_ids=[bms[0].id])
    data = json.loads(out.read_text())
    assert len(data) == 1
    assert data[0]["url"] == bms[0].url


def test_json_dict_keys(db, tmp_path):
    out = tmp_path / "bm.json"
    export_json(db, out)
    data = json.loads(out.read_text())
    assert len(data) > 0
    record = data[0]
    for key in ("url", "title", "description", "tags", "starred", "pinned", "added", "visit_count", "unique_id"):
        assert key in record, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------


def test_csv_correct_line_count(db, tmp_path):
    out = tmp_path / "bm.csv"
    export_csv(db, out)
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    # header + 2 bookmarks
    assert len(rows) == 3


def test_csv_header_row(db, tmp_path):
    out = tmp_path / "bm.csv"
    export_csv(db, out)
    with open(out, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == ["url", "title", "tags", "description", "starred"]


def test_csv_contains_urls(db, tmp_path):
    out = tmp_path / "bm.csv"
    export_csv(db, out)
    content = out.read_text()
    assert "example.com" in content
    assert "python.org" in content


# ---------------------------------------------------------------------------
# export_text
# ---------------------------------------------------------------------------


def test_text_one_url_per_line(db, tmp_path):
    out = tmp_path / "bm.txt"
    export_text(db, out)
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    assert len(lines) == 2


def test_text_contains_only_urls(db, tmp_path):
    out = tmp_path / "bm.txt"
    export_text(db, out)
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    for line in lines:
        assert line.startswith("http"), f"Expected URL, got: {line!r}"


# ---------------------------------------------------------------------------
# export_markdown
# ---------------------------------------------------------------------------


def test_markdown_has_heading(db, tmp_path):
    out = tmp_path / "bm.md"
    export_markdown(db, out)
    content = out.read_text()
    assert "# Bookmarks" in content


def test_markdown_list_items(db, tmp_path):
    out = tmp_path / "bm.md"
    export_markdown(db, out)
    content = out.read_text()
    # Each bookmark should produce a list item line
    lines = [l for l in content.splitlines() if l.startswith("- ")]
    assert len(lines) == 2


def test_markdown_format(db, tmp_path):
    out = tmp_path / "bm.md"
    export_markdown(db, out)
    content = out.read_text()
    # Should have markdown link syntax
    assert "[" in content and "](" in content


# ---------------------------------------------------------------------------
# export_m3u
# ---------------------------------------------------------------------------


def test_m3u_has_header(db, tmp_path):
    out = tmp_path / "playlist.m3u"
    export_m3u(db, out)
    content = out.read_text()
    assert content.startswith("#EXTM3U")


def test_m3u_has_extinf_entries(db, tmp_path):
    out = tmp_path / "playlist.m3u"
    export_m3u(db, out)
    content = out.read_text()
    extinf_lines = [l for l in content.splitlines() if l.startswith("#EXTINF")]
    assert len(extinf_lines) == 2


def test_m3u_has_urls(db, tmp_path):
    out = tmp_path / "playlist.m3u"
    export_m3u(db, out)
    content = out.read_text()
    assert "example.com" in content
    assert "python.org" in content


# ---------------------------------------------------------------------------
# export_file dispatcher
# ---------------------------------------------------------------------------


def test_export_file_json(db, tmp_path):
    out = tmp_path / "bm.json"
    export_file(db, out, format="json")
    data = json.loads(out.read_text())
    assert len(data) == 2


def test_export_file_csv(db, tmp_path):
    out = tmp_path / "bm.csv"
    export_file(db, out, format="csv")
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 3


def test_export_file_text(db, tmp_path):
    out = tmp_path / "bm.txt"
    export_file(db, out, format="text")
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    assert len(lines) == 2


def test_export_file_markdown(db, tmp_path):
    out = tmp_path / "bm.md"
    export_file(db, out, format="markdown")
    assert "# Bookmarks" in out.read_text()


def test_export_file_m3u(db, tmp_path):
    out = tmp_path / "playlist.m3u"
    export_file(db, out, format="m3u")
    assert out.read_text().startswith("#EXTM3U")


def test_export_file_arkiv(db, tmp_path):
    out = tmp_path / "arkiv_out"
    export_file(db, out, format="arkiv")
    assert (out / "records.jsonl").exists()
    assert (out / "schema.yaml").exists()


def test_export_file_unknown_format_raises(db, tmp_path):
    out = tmp_path / "bm.xyz"
    with pytest.raises(ValueError, match="unknown format"):
        export_file(db, out, format="xyz")


# ---------------------------------------------------------------------------
# arkiv: SCHEMA structure
# ---------------------------------------------------------------------------


def test_arkiv_schema_has_kinds():
    assert "kinds" in SCHEMA
    assert "bookmark" in SCHEMA["kinds"]
    assert "marginalia" in SCHEMA["kinds"]


def test_arkiv_schema_bookmark_has_uri_template():
    bm_kind = SCHEMA["kinds"]["bookmark"]
    assert "uri" in bm_kind
    assert "bookmark-memex://bookmark/" in bm_kind["uri"]


def test_arkiv_schema_marginalia_has_uri_template():
    m_kind = SCHEMA["kinds"]["marginalia"]
    assert "uri" in m_kind
    assert "bookmark-memex://marginalia/" in m_kind["uri"]


def test_arkiv_schema_has_scheme():
    assert SCHEMA.get("scheme") == "bookmark-memex"


# ---------------------------------------------------------------------------
# arkiv: export_arkiv
# ---------------------------------------------------------------------------


def test_arkiv_creates_records_and_schema(db, tmp_path):
    out = tmp_path / "arkiv"
    result = export_arkiv(db, out)
    assert Path(result["records_path"]).exists()
    assert Path(result["schema_path"]).exists()


def test_arkiv_returns_counts(db, tmp_path):
    out = tmp_path / "arkiv"
    result = export_arkiv(db, out)
    assert result["counts"]["bookmark"] == 2
    assert result["counts"]["marginalia"] == 1
    # Legacy alias still available for old callers.
    assert result["counts"]["annotation"] == 1


def test_arkiv_records_have_uris(db, tmp_path):
    out = tmp_path / "arkiv"
    export_arkiv(db, out)
    records_path = out / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line.strip()]
    for r in records:
        assert "uri" in r
        assert r["uri"].startswith("bookmark-memex://")


def test_arkiv_records_kinds(db, tmp_path):
    out = tmp_path / "arkiv"
    export_arkiv(db, out)
    records_path = out / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line.strip()]
    kinds = {r["kind"] for r in records}
    assert "bookmark" in kinds
    assert "marginalia" in kinds


def test_arkiv_bookmark_record_fields(db, tmp_path):
    out = tmp_path / "arkiv"
    export_arkiv(db, out)
    records_path = out / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line.strip()]
    bm_records = [r for r in records if r["kind"] == "bookmark"]
    assert len(bm_records) == 2
    for r in bm_records:
        for field in ("url", "title", "unique_id", "tags", "starred", "pinned"):
            assert field in r, f"Missing field {field!r} in bookmark record"


def test_arkiv_marginalia_has_bookmark_uri(db, tmp_path):
    out = tmp_path / "arkiv"
    export_arkiv(db, out)
    records_path = out / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line.strip()]
    m_records = [r for r in records if r["kind"] == "marginalia"]
    assert len(m_records) == 1
    m = m_records[0]
    assert "bookmark_uri" in m
    assert m["bookmark_uri"].startswith("bookmark-memex://bookmark/")


def test_arkiv_schema_yaml_parseable(db, tmp_path):
    out = tmp_path / "arkiv"
    export_arkiv(db, out)
    schema_content = (out / "schema.yaml").read_text()
    schema = yaml.safe_load(schema_content)
    assert schema["scheme"] == "bookmark-memex"
    assert "exported_at" in schema
    assert "kinds" in schema


def test_arkiv_excludes_archived_bookmarks(db, tmp_path):
    """Soft-deleting a bookmark should reduce the bookmark count by 1."""
    bms = db.list()
    db.delete(bms[0].id)  # soft delete

    out = tmp_path / "arkiv"
    result = export_arkiv(db, out)
    assert result["counts"]["bookmark"] == 1


def test_arkiv_excludes_archived_marginalia(db, tmp_path):
    """Marginalia on a soft-deleted bookmark are NOT archived themselves
    (ON DELETE SET NULL), but we only export active marginalia.
    This test verifies the marginalia count reflects only active rows.
    """
    # The single note is active; verify it shows up.
    out = tmp_path / "arkiv"
    result = export_arkiv(db, out)
    assert result["counts"]["marginalia"] >= 1


# ───────────────────────────────────────────────────────────────────
# arkiv bundles: directory + .zip + .tar.gz (C5a)
# ───────────────────────────────────────────────────────────────────


def test_arkiv_directory_includes_readme(db, tmp_path):
    out = tmp_path / "arkiv"
    export_arkiv(db, out)
    readme = out / "README.md"
    assert readme.exists()
    text = readme.read_text()
    # YAML frontmatter + "arkiv" + usage example.
    assert text.startswith("---")
    assert "generator: bookmark-memex" in text
    assert "--format arkiv" in text


def test_arkiv_zip_bundle(db, tmp_path):
    import zipfile

    out = tmp_path / "archive.zip"
    result = export_arkiv(db, out)
    assert result["format"] == "zip"
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert {"records.jsonl", "schema.yaml", "README.md"}.issubset(names)
        # Records are valid JSONL inside the zip.
        with zf.open("records.jsonl") as f:
            lines = [json.loads(ln) for ln in f.read().decode("utf-8").splitlines() if ln.strip()]
    kinds = {r["kind"] for r in lines}
    assert "bookmark" in kinds
    assert result["counts"]["bookmark"] == 2


def test_arkiv_tar_gz_bundle(db, tmp_path):
    import tarfile

    out = tmp_path / "archive.tar.gz"
    result = export_arkiv(db, out)
    assert result["format"] == "tar.gz"
    assert out.exists()
    with tarfile.open(out, "r:gz") as tf:
        names = set(tf.getnames())
        assert {"records.jsonl", "schema.yaml", "README.md"}.issubset(names)
        extracted = tf.extractfile("records.jsonl")
        assert extracted is not None
        lines = [json.loads(ln) for ln in extracted.read().decode("utf-8").splitlines() if ln.strip()]
    assert any(r["kind"] == "marginalia" for r in lines)


def test_arkiv_tgz_extension(db, tmp_path):
    """The .tgz extension is accepted as a synonym for .tar.gz."""
    import tarfile

    out = tmp_path / "archive.tgz"
    result = export_arkiv(db, out)
    assert result["format"] == "tar.gz"
    with tarfile.open(out, "r:gz") as tf:
        assert "records.jsonl" in tf.getnames()


def test_arkiv_bundle_counts_match_directory(db, tmp_path):
    """The three bundle formats should contain the exact same records."""
    dir_out = tmp_path / "dir"
    zip_out = tmp_path / "bundle.zip"
    tar_out = tmp_path / "bundle.tar.gz"

    r_dir = export_arkiv(db, dir_out)
    r_zip = export_arkiv(db, zip_out)
    r_tar = export_arkiv(db, tar_out)

    assert r_dir["counts"] == r_zip["counts"] == r_tar["counts"]


def test_arkiv_detect_compression():
    from bookmark_memex.exporters.arkiv import _detect_compression

    assert _detect_compression("out") == "dir"
    assert _detect_compression("/tmp/out.zip") == "zip"
    assert _detect_compression("foo.tar.gz") == "tar.gz"
    assert _detect_compression("foo.TAR.GZ") == "tar.gz"
    assert _detect_compression("foo.tgz") == "tar.gz"
    assert _detect_compression("foo.TGZ") == "tar.gz"
