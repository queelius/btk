"""Tests for the arkiv importer (bookmark_memex.importers.arkiv).

Covers bundle format auto-detection (directory / .zip / .tar.gz / .jsonl /
.jsonl.gz), UUID-stable annotation round-trip, bookmark merge on re-import,
and orphan-annotation survival.
"""
from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bookmark_memex.db import Database
from bookmark_memex.exporters.arkiv import export_arkiv
from bookmark_memex.importers.arkiv import (
    detect,
    import_arkiv,
    _parse_bookmark_unique_id_from_uri,
)


# ───────────────────────────────────────────────────────────────────
# Fixtures: a DB with bookmarks + annotations to round-trip
# ───────────────────────────────────────────────────────────────────


@pytest.fixture
def src_db(tmp_db_path):
    db = Database(tmp_db_path)
    py = db.add(
        "https://docs.python.org/3/",
        title="Python Documentation",
        description="Official Python docs",
        tags=["programming/python", "documentation"],
        starred=True,
    )
    db.add(
        "https://github.com",
        title="GitHub",
        description="Code hosting",
        tags=["development", "git"],
        pinned=True,
    )
    # Pin the python bookmark's unique_id so tests can find it regardless
    # of db.list() ordering (which is added-DESC, so github is first).
    db._python_uid = py.unique_id
    db.annotate(py.unique_id, "One of the best reference docs.")
    return db


@pytest.fixture
def fresh_db(tmp_path):
    return Database(str(tmp_path / "fresh.db"))


# ───────────────────────────────────────────────────────────────────
# _parse_bookmark_unique_id_from_uri
# ───────────────────────────────────────────────────────────────────


def test_parse_unique_id_from_uri_normal():
    assert _parse_bookmark_unique_id_from_uri("bookmark-memex://bookmark/abcdef0123456789") == "abcdef0123456789"


def test_parse_unique_id_from_uri_with_fragment():
    assert (
        _parse_bookmark_unique_id_from_uri("bookmark-memex://bookmark/abcdef0123456789#section=x")
        == "abcdef0123456789"
    )


def test_parse_unique_id_from_uri_wrong_scheme_returns_none():
    assert _parse_bookmark_unique_id_from_uri("file:///tmp/foo") is None


def test_parse_unique_id_from_uri_none_returns_none():
    assert _parse_bookmark_unique_id_from_uri(None) is None


# ───────────────────────────────────────────────────────────────────
# detect(): every bundle shape
# ───────────────────────────────────────────────────────────────────


def test_detect_directory(src_db, tmp_path):
    out = tmp_path / "bundle"
    export_arkiv(src_db, out)
    assert detect(out) is True


def test_detect_zip(src_db, tmp_path):
    out = tmp_path / "bundle.zip"
    export_arkiv(src_db, out)
    assert detect(out) is True


def test_detect_tar_gz(src_db, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    export_arkiv(src_db, out)
    assert detect(out) is True


def test_detect_tgz(src_db, tmp_path):
    out = tmp_path / "bundle.tgz"
    export_arkiv(src_db, out)
    assert detect(out) is True


def test_detect_bare_jsonl(src_db, tmp_path):
    # Synthesize a bare .jsonl file from the directory export.
    dir_out = tmp_path / "d"
    export_arkiv(src_db, dir_out)
    records_path = dir_out / "records.jsonl"
    bare = tmp_path / "records.jsonl"
    bare.write_bytes(records_path.read_bytes())
    assert detect(bare) is True


def test_detect_bare_jsonl_gz(src_db, tmp_path):
    dir_out = tmp_path / "d"
    export_arkiv(src_db, dir_out)
    src = (dir_out / "records.jsonl").read_bytes()
    bare_gz = tmp_path / "records.jsonl.gz"
    with gzip.open(bare_gz, "wb") as f:
        f.write(src)
    assert detect(bare_gz) is True


def test_detect_rejects_non_arkiv_jsonl(tmp_path):
    foreign = tmp_path / "foreign.jsonl"
    foreign.write_text('{"kind":"not-us","uri":"foo://bar/1"}\n')
    assert detect(foreign) is False


def test_detect_rejects_missing_path(tmp_path):
    assert detect(tmp_path / "does-not-exist") is False


def test_detect_rejects_empty_directory(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect(empty) is False


def test_detect_rejects_non_jsonl_file(tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    assert detect(txt) is False


# ───────────────────────────────────────────────────────────────────
# import_arkiv(): round-trip
# ───────────────────────────────────────────────────────────────────


def test_import_directory_bundle_reconstructs_bookmarks(src_db, fresh_db, tmp_path):
    out = tmp_path / "bundle"
    export_arkiv(src_db, out)

    stats = import_arkiv(fresh_db, out)

    assert stats["bookmarks_added"] == 2
    assert stats["bookmarks_seen"] == 2
    assert stats["annotations_added"] == 1
    assert stats["annotations_skipped_existing"] == 0

    urls = {b.url for b in fresh_db.list()}
    assert any("docs.python.org" in u for u in urls)
    assert any("github.com" in u for u in urls)


def test_import_zip_bundle(src_db, fresh_db, tmp_path):
    out = tmp_path / "bundle.zip"
    export_arkiv(src_db, out)
    stats = import_arkiv(fresh_db, out)
    assert stats["bookmarks_added"] == 2


def test_import_tar_gz_bundle(src_db, fresh_db, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    export_arkiv(src_db, out)
    stats = import_arkiv(fresh_db, out)
    assert stats["bookmarks_added"] == 2


def test_import_bare_jsonl_gz(src_db, fresh_db, tmp_path):
    """The SPA round-trip format: bare .jsonl.gz emitted by the browser bundle."""
    dir_out = tmp_path / "d"
    export_arkiv(src_db, dir_out)
    src = (dir_out / "records.jsonl").read_bytes()
    bare_gz = tmp_path / "records.jsonl.gz"
    with gzip.open(bare_gz, "wb") as f:
        f.write(src)

    stats = import_arkiv(fresh_db, bare_gz)
    assert stats["bookmarks_added"] == 2
    assert stats["annotations_added"] == 1


def test_import_preserves_annotation_uuid(src_db, fresh_db, tmp_path):
    """Annotations round-trip with their original UUID (stable identity)."""
    src_anns = src_db.get_annotations(src_db._python_uid)
    assert len(src_anns) == 1
    src_uuid = src_anns[0].id

    out = tmp_path / "bundle"
    export_arkiv(src_db, out)
    import_arkiv(fresh_db, out)

    dst_bm = fresh_db.get_by_unique_id(src_db._python_uid)
    assert dst_bm is not None
    dst_anns = fresh_db.get_annotations(dst_bm.unique_id)
    assert len(dst_anns) == 1
    assert dst_anns[0].id == src_uuid


def test_re_import_is_idempotent(src_db, fresh_db, tmp_path):
    """Re-importing the same bundle should not duplicate anything."""
    out = tmp_path / "bundle"
    export_arkiv(src_db, out)

    import_arkiv(fresh_db, out)
    second = import_arkiv(fresh_db, out)

    # Bookmarks already present; add() returns the existing row so
    # "added" count should be 0 on the second pass.
    assert second["bookmarks_added"] == 0
    assert second["annotations_added"] == 0
    assert second["annotations_skipped_existing"] == 1

    # DB state: still exactly 2 bookmarks and 1 annotation.
    assert len(fresh_db.list()) == 2
    py = fresh_db.get_by_unique_id(src_db._python_uid)
    assert py is not None
    assert len(fresh_db.get_annotations(py.unique_id)) == 1


def test_merge_flag_accepted_and_noop(src_db, fresh_db, tmp_path):
    """--merge is accepted; currently behaves the same as default (no-op)."""
    out = tmp_path / "bundle"
    export_arkiv(src_db, out)

    a = import_arkiv(fresh_db, out, merge=False)
    b_db = Database(str(tmp_path / "fresh2.db"))
    b = import_arkiv(b_db, out, merge=True)

    assert a["bookmarks_added"] == b["bookmarks_added"]
    assert a["annotations_added"] == b["annotations_added"]


def test_import_preserves_tags(src_db, fresh_db, tmp_path):
    out = tmp_path / "bundle"
    export_arkiv(src_db, out)
    import_arkiv(fresh_db, out)

    dst = fresh_db.get_by_unique_id(src_db._python_uid)
    assert dst is not None
    tag_names = {t.name for t in dst.tags}
    assert {"programming/python", "documentation"}.issubset(tag_names)


def test_import_preserves_starred_and_pinned(src_db, fresh_db, tmp_path):
    out = tmp_path / "bundle"
    export_arkiv(src_db, out)
    import_arkiv(fresh_db, out)

    all_bms = fresh_db.list()
    py = next(b for b in all_bms if "python" in b.url)
    gh = next(b for b in all_bms if "github" in b.url)
    assert py.starred is True
    assert gh.pinned is True


def test_orphan_annotation_is_preserved(src_db, fresh_db, tmp_path):
    """An annotation whose parent bookmark has been soft-deleted round-trips as an orphan."""
    # Soft-delete the parent bookmark before export.
    py = src_db.get_by_unique_id(src_db._python_uid)
    assert py is not None
    src_db.delete(py.id)

    # Now the annotation is no longer emitted by the exporter because
    # export filters on active annotations only. But orphan annotations
    # (bookmark_id is NULL with ON DELETE SET NULL) would still be
    # emitted — so this test instead verifies: we can round-trip an
    # already-orphan annotation from a synthetic bundle.
    bundle = tmp_path / "orphan.jsonl"
    orphan = {
        "kind": "annotation",
        "uri": "bookmark-memex://annotation/deadbeef",
        "uuid": "deadbeef",
        "bookmark_uri": None,
        "text": "Orphaned note, parent long gone.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # A bare .jsonl is valid as long as records look like ours.
    bundle.write_text(json.dumps(orphan) + "\n")
    # detect() is strict: this only has annotation kind which satisfies our heuristic.
    assert detect(bundle) is True

    stats = import_arkiv(fresh_db, bundle)
    assert stats["annotations_added"] == 1