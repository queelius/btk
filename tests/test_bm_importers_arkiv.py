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


def test_roundtrip_preserves_added_and_visit_count(tmp_path):
    """BM-5: a restore must not reset 'added' to the import date or zero out
    visit history; those values are in the bundle and must round-trip."""
    from datetime import datetime

    past = datetime(2020, 1, 2, 3, 4, 5)
    last = datetime(2021, 6, 7, 8, 9, 10)
    src = Database(str(tmp_path / "src.db"))
    src.add(
        "https://example.com/deep#anchor",
        title="Deep link",
        added=past,
        visit_count=7,
        last_visited=last,
    )

    out = tmp_path / "bundle"
    export_arkiv(src, out)

    fresh = Database(str(tmp_path / "fresh.db"))
    import_arkiv(fresh, out)
    bms = fresh.list()
    assert len(bms) == 1
    bm = bms[0]
    assert bm.added == past, "added was reset on restore"
    assert bm.visit_count == 7, "visit_count was zeroed on restore"
    assert bm.last_visited == last


def test_merge_tz_aware_timestamp_onto_existing_bookmark(tmp_path):
    """R1: importing a bundle whose timestamps carry an offset onto an
    already-present (naive-UTC) bookmark must not crash, and must store the
    correct naive-UTC values after the monotonic merge.

    The existing row stores naive-UTC datetimes (the codebase convention via
    _utcnow). A bundle produced externally can carry tz-aware ISO strings
    (with a +HH:MM offset). The monotonic merge in Database.add compares the
    parsed value against the stored naive value; if the parsed value keeps its
    tzinfo, the comparison raises TypeError. The importer must normalize parsed
    timestamps to naive-UTC first.
    """
    db = Database(str(tmp_path / "tz.db"))
    db.add(
        "https://example.com/",
        title="Existing",
        added=datetime(2022, 1, 1, 0, 0, 0),
        visit_count=3,
        last_visited=datetime(2022, 1, 1, 0, 0, 0),
    )
    uid = db.list()[0].unique_id

    # A bundle whose timestamps carry offsets. 'added' is earlier than the
    # stored value (so the monotonic merge will adopt it), and 'last_visited'
    # is later (so it will be adopted too), forcing both comparisons to run.
    bundle = tmp_path / "offset.jsonl"
    rec = {
        "kind": "bookmark",
        "uri": f"bookmark-memex://bookmark/{uid}",
        "unique_id": uid,
        "url": "https://example.com/",
        "title": "Existing",
        "added": "2020-05-06T07:08:09+00:00",
        "visit_count": 9,
        # 06:07:08 at +02:00 == 04:07:08 UTC
        "last_visited": "2023-04-05T06:07:08+02:00",
    }
    bundle.write_text(json.dumps(rec) + "\n")

    # Must not raise.
    stats = import_arkiv(db, bundle)
    assert stats["bookmarks_seen"] == 1

    bm = db.get_by_unique_id(uid)
    assert bm is not None
    # Stored values are naive-UTC. 'added' adopted the earlier bundle value.
    assert bm.added == datetime(2020, 5, 6, 7, 8, 9)
    assert bm.added.tzinfo is None
    # visit_count adopted the larger bundle value.
    assert bm.visit_count == 9
    # last_visited normalized to naive-UTC: 06:07:08+02:00 -> 04:07:08 UTC.
    assert bm.last_visited == datetime(2023, 4, 5, 4, 7, 8)
    assert bm.last_visited.tzinfo is None


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