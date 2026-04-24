"""Pre-create migrations on Database.__init__.

We currently have exactly one migration:

    _apply_rename_annotations_to_marginalia: renames the legacy
    ``annotations`` table to ``marginalia`` and drops the legacy
    ``annotations_fts`` shadow table (it gets rebuilt under the new
    name on the next FTS bootstrap).

The migration must be:
- Safe on fresh DBs (no legacy tables): no-op.
- Safe on pre-rename DBs: data preserved, new name in place.
- Idempotent: repeated opens do not corrupt state.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bookmark_memex.db import Database


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        return {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def test_migration_is_noop_on_fresh_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    Database(str(db_path))
    tables = _table_names(db_path)
    assert "marginalia" in tables
    assert "annotations" not in tables


def test_migration_renames_legacy_annotations_table(tmp_path):
    """A DB whose canonical table is called ``annotations`` is migrated."""
    db_path = tmp_path / "legacy.db"

    # Bootstrap the canonical schema, insert a note, then rename the
    # marginalia table back to annotations to simulate a pre-rename DB.
    db = Database(str(db_path))
    bm = db.add("https://example.com/a", title="Alpha")
    note = db.add_marginalia(bm.unique_id, "original note")
    note_id = note.id
    del db

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("ALTER TABLE marginalia RENAME TO annotations")
        conn.commit()

    # Now reopen — migration should rename it back.
    db2 = Database(str(db_path))
    tables = _table_names(db_path)
    assert "marginalia" in tables
    assert "annotations" not in tables

    # And the row must still be there, keyed by its original UUID.
    notes = db2.list_marginalia(bm.unique_id)
    assert len(notes) == 1
    assert notes[0].id == note_id
    assert notes[0].text == "original note"
    assert notes[0].uri.startswith("bookmark-memex://marginalia/")


def test_migration_drops_legacy_annotations_fts_shadow(tmp_path):
    """Legacy annotations_fts is dropped; the fresh index bootstraps on demand."""
    db_path = tmp_path / "legacy_fts.db"

    # Bootstrap then simulate legacy names.
    db = Database(str(db_path))
    bm = db.add("https://example.com/a", title="Alpha")
    db.add_marginalia(bm.unique_id, "with fts")
    del db

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("ALTER TABLE marginalia RENAME TO annotations")
        # Synthesise a legacy FTS5 table as well.
        conn.execute(
            "CREATE VIRTUAL TABLE annotations_fts USING fts5("
            " annotation_id UNINDEXED, text"
            ")"
        )
        conn.commit()

    Database(str(db_path))
    tables = _table_names(db_path)
    assert "annotations_fts" not in tables


def test_migration_is_idempotent(tmp_path):
    """Re-opening an already-migrated DB must not corrupt state."""
    db_path = tmp_path / "idem.db"
    db = Database(str(db_path))
    bm = db.add("https://example.com/a", title="Alpha")
    db.add_marginalia(bm.unique_id, "first")
    del db

    # Open again several times; count of notes stays at 1.
    for _ in range(3):
        db = Database(str(db_path))
        notes = db.list_marginalia(bm.unique_id)
        assert len(notes) == 1
        assert notes[0].text == "first"
        del db
