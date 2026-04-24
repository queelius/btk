"""Tests for bookmark_memex.fts.FTSIndex."""

from __future__ import annotations

import pytest

from bookmark_memex.db import Database
from bookmark_memex.fts import FTSIndex, SearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_db_path):
    return Database(tmp_db_path)


@pytest.fixture
def fts(db):
    idx = FTSIndex(db.path)
    idx.create_indexes()
    return idx


# ---------------------------------------------------------------------------
# SearchResult dataclass
# ---------------------------------------------------------------------------


def test_search_result_fields():
    r = SearchResult(
        bookmark_id=1,
        url="https://example.com",
        title="Example",
        description="A site",
        rank=2.5,
        snippet="...example...",
    )
    assert r.bookmark_id == 1
    assert r.url == "https://example.com"
    assert r.title == "Example"
    assert r.description == "A site"
    assert r.rank == 2.5
    assert r.snippet == "...example..."


def test_search_result_snippet_defaults_to_none():
    r = SearchResult(
        bookmark_id=2,
        url="https://test.com",
        title="Test",
        description="",
        rank=0.0,
    )
    assert r.snippet is None


# ---------------------------------------------------------------------------
# create_indexes / get_stats
# ---------------------------------------------------------------------------


def test_create_indexes_makes_bookmarks_fts_exist(fts):
    stats = fts.get_stats()
    assert stats["bookmarks_fts"]["exists"] is True


def test_create_indexes_makes_marginalia_fts_exist(fts):
    stats = fts.get_stats()
    assert stats["marginalia_fts"]["exists"] is True


def test_create_indexes_makes_content_fts_exist(fts):
    stats = fts.get_stats()
    assert stats["content_fts"]["exists"] is True


def test_create_indexes_idempotent(db):
    """Calling create_indexes twice should not raise."""
    idx = FTSIndex(db.path)
    idx.create_indexes()
    idx.create_indexes()  # second call should be a no-op


def test_get_stats_document_counts_start_at_zero(fts):
    stats = fts.get_stats()
    assert stats["bookmarks_fts"]["documents"] == 0
    assert stats["marginalia_fts"]["documents"] == 0
    assert stats["content_fts"]["documents"] == 0


# ---------------------------------------------------------------------------
# rebuild_bookmarks_index
# ---------------------------------------------------------------------------


def test_rebuild_bookmarks_index_returns_correct_count(db, fts):
    db.add("https://a.com", title="Alpha")
    db.add("https://b.com", title="Beta")
    db.add("https://c.com", title="Gamma")
    count = fts.rebuild_bookmarks_index()
    assert count == 3


def test_rebuild_bookmarks_index_excludes_archived(db, fts):
    bm1 = db.add("https://active.com", title="Active")
    bm2 = db.add("https://archived.com", title="Archived Bookmark")
    db.delete(bm2.id)  # soft delete
    count = fts.rebuild_bookmarks_index()
    assert count == 1


def test_rebuild_bookmarks_index_progress_callback(db, fts):
    db.add("https://a.com", title="A")
    db.add("https://b.com", title="B")
    calls = []
    fts.rebuild_bookmarks_index(progress_callback=lambda cur, tot: calls.append((cur, tot)))
    assert len(calls) == 2
    assert calls[-1] == (2, 2)


def test_rebuild_bookmarks_index_updates_stats(db, fts):
    db.add("https://x.com", title="X")
    fts.rebuild_bookmarks_index()
    stats = fts.get_stats()
    assert stats["bookmarks_fts"]["documents"] == 1


# ---------------------------------------------------------------------------
# rebuild_marginalia_index
# ---------------------------------------------------------------------------


def test_rebuild_marginalia_index_returns_correct_count(db, fts):
    bm = db.add("https://example.com", title="Example")
    db.add_marginalia(bm.unique_id, "First note")
    db.add_marginalia(bm.unique_id, "Second note")
    count = fts.rebuild_marginalia_index()
    assert count == 2


def test_rebuild_marginalia_index_zero_when_empty(db, fts):
    count = fts.rebuild_marginalia_index()
    assert count == 0


def test_rebuild_annotations_alias_still_works(db, fts):
    """Legacy name must continue to function for backward compatibility."""
    bm = db.add("https://example.com", title="Example")
    db.annotate(bm.unique_id, "Legacy-name call")
    count = fts.rebuild_annotations_index()
    assert count == 1


# ---------------------------------------------------------------------------
# rebuild_content_index
# ---------------------------------------------------------------------------


def test_rebuild_content_index_zero_when_empty(db, fts):
    count = fts.rebuild_content_index()
    assert count == 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_empty_query_returns_empty(fts):
    assert fts.search("") == []
    assert fts.search("   ") == []


def test_search_by_title_finds_bookmark(db, fts):
    db.add("https://python.org", title="Python Programming Language", description="")
    db.add("https://rust-lang.org", title="Rust Systems Language", description="")
    fts.rebuild_bookmarks_index()

    results = fts.search("Python")
    ids = [r.bookmark_id for r in results]
    # should find the Python bookmark
    assert any(True for r in results if "Python" in r.title)


def test_search_no_results(db, fts):
    db.add("https://example.com", title="Just an Example", description="")
    fts.rebuild_bookmarks_index()

    results = fts.search("xyznonexistentword")
    assert results == []


def test_search_returns_search_result_objects(db, fts):
    db.add("https://docs.python.org", title="Python Docs", description="Official docs")
    fts.rebuild_bookmarks_index()

    results = fts.search("Python")
    assert len(results) >= 1
    r = results[0]
    assert isinstance(r, SearchResult)
    assert isinstance(r.bookmark_id, int)
    assert isinstance(r.rank, float)


def test_search_rank_is_nonnegative(db, fts):
    db.add("https://example.com", title="Example Site", description="Just an example")
    fts.rebuild_bookmarks_index()
    results = fts.search("example")
    for r in results:
        assert r.rank >= 0


def test_search_respects_limit(db, fts):
    for i in range(10):
        db.add(f"https://example{i}.com", title=f"Example Site {i}", description="example")
    fts.rebuild_bookmarks_index()
    results = fts.search("example", limit=3)
    assert len(results) <= 3


def test_search_with_tags(db, fts):
    db.add("https://arxiv.org/123", title="A Machine Learning Paper", tags=["ai", "research"])
    fts.rebuild_bookmarks_index()
    results = fts.search("machine learning")
    assert len(results) >= 1
