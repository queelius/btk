"""Tests for bookmark_memex.db.Database."""

from __future__ import annotations

import pytest

from bookmark_memex.db import Database, normalize_url, generate_unique_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_db_path):
    return Database(tmp_db_path)


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------


def test_normalize_url_strips_trailing_slash():
    assert normalize_url("https://example.com/path/") == "https://example.com/path"


def test_normalize_url_keeps_root_slash():
    assert normalize_url("https://example.com") == "https://example.com/"


def test_normalize_url_lowercases_scheme_host():
    assert normalize_url("HTTPS://Example.COM/") == "https://example.com/"


def test_normalize_url_removes_http_default_port():
    assert normalize_url("http://example.com:80/") == "http://example.com/"


def test_normalize_url_removes_https_default_port():
    assert normalize_url("https://example.com:443/") == "https://example.com/"


def test_normalize_url_sorts_query_params():
    result = normalize_url("https://example.com/?b=2&a=1")
    assert result == "https://example.com/?a=1&b=2"


def test_generate_unique_id_length():
    uid = generate_unique_id("https://example.com")
    assert len(uid) == 16


def test_generate_unique_id_deterministic():
    uid1 = generate_unique_id("https://example.com")
    uid2 = generate_unique_id("https://example.com")
    assert uid1 == uid2


def test_generate_unique_id_normalizes():
    """Trailing slash vs no slash should produce same id."""
    uid1 = generate_unique_id("https://example.com/")
    uid2 = generate_unique_id("https://example.com")
    assert uid1 == uid2


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_add_bookmark_returns_bookmark_with_id(db):
    bm = db.add("https://example.com", title="Example")
    assert bm.id is not None
    assert bm.id > 0


def test_add_bookmark_unique_id_length_16(db):
    bm = db.add("https://example.com", title="Example")
    assert len(bm.unique_id) == 16


def test_add_with_tags_stores_tag_names(db):
    bm = db.add("https://example.com", title="Example", tags=["python", "web"])
    names = {t.name for t in bm.tags}
    assert names == {"python", "web"}


def test_add_starred(db):
    bm = db.add("https://example.com", title="Example", starred=True)
    assert bm.starred is True


def test_add_pinned(db):
    bm = db.add("https://example.com", title="Example", pinned=True)
    assert bm.pinned is True


def test_add_duplicate_url_returns_existing(db):
    bm1 = db.add("https://example.com", title="First")
    bm2 = db.add("https://example.com", title="Second")
    assert bm1.id == bm2.id
    assert bm1.unique_id == bm2.unique_id


def test_add_normalizes_url_trailing_slash(db):
    """https://example.com/ and https://example.com should map to same row."""
    bm1 = db.add("https://example.com/", title="With Slash")
    bm2 = db.add("https://example.com", title="Without Slash")
    assert bm1.id == bm2.id


def test_add_records_source_type(db):
    bm = db.add(
        "https://example.com",
        title="Example",
        source_type="chrome_html",
        source_name="Chrome Export",
    )
    assert len(bm.sources) == 1
    assert bm.sources[0].source_type == "chrome_html"


def test_add_no_source_type_no_sources(db):
    bm = db.add("https://example.com", title="Example")
    # source record only created when source_type is given
    assert len(bm.sources) == 0


def test_add_duplicate_merges_tags(db):
    db.add("https://example.com", title="Example", tags=["python"])
    bm2 = db.add("https://example.com", title="Example", tags=["web"])
    names = {t.name for t in bm2.tags}
    assert "python" in names
    assert "web" in names


def test_add_title_empty_updated_on_duplicate(db):
    """When the first add has no title and the second does, title gets filled in."""
    bm1 = db.add("https://example.com")  # no title → empty string
    bm2 = db.add("https://example.com", title="Now Has Title")
    assert bm2.title == "Now Has Title"


# ---------------------------------------------------------------------------
# get / get_by_unique_id
# ---------------------------------------------------------------------------


def test_get_by_id(db):
    bm = db.add("https://example.com", title="Example")
    fetched = db.get(bm.id)
    assert fetched is not None
    assert fetched.id == bm.id


def test_get_by_unique_id(db):
    bm = db.add("https://example.com", title="Example")
    fetched = db.get_by_unique_id(bm.unique_id)
    assert fetched is not None
    assert fetched.unique_id == bm.unique_id


def test_get_nonexistent_returns_none(db):
    result = db.get(999999)
    assert result is None


def test_get_by_unique_id_nonexistent_returns_none(db):
    result = db.get_by_unique_id("0000000000000000")
    assert result is None


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_title(db):
    bm = db.add("https://example.com", title="Old Title")
    updated = db.update(bm.id, title="New Title")
    assert updated is not None
    assert updated.title == "New Title"


def test_update_starred(db):
    bm = db.add("https://example.com", title="Example")
    updated = db.update(bm.id, starred=True)
    assert updated.starred is True


def test_update_nonexistent_returns_none(db):
    result = db.update(999999, title="Nope")
    assert result is None


# ---------------------------------------------------------------------------
# visit
# ---------------------------------------------------------------------------


def test_visit_increments_count(db):
    bm = db.add("https://example.com", title="Example")
    assert bm.visit_count == 0
    db.visit(bm.id)
    fetched = db.get(bm.id)
    assert fetched.visit_count == 1


def test_visit_sets_last_visited(db):
    bm = db.add("https://example.com", title="Example")
    assert bm.last_visited is None
    db.visit(bm.id)
    fetched = db.get(bm.id)
    assert fetched.last_visited is not None


def test_visit_increments_multiple_times(db):
    bm = db.add("https://example.com", title="Example")
    db.visit(bm.id)
    db.visit(bm.id)
    db.visit(bm.id)
    fetched = db.get(bm.id)
    assert fetched.visit_count == 3


# ---------------------------------------------------------------------------
# delete / restore
# ---------------------------------------------------------------------------


def test_soft_delete_hides_from_get(db):
    bm = db.add("https://example.com", title="Example")
    db.delete(bm.id)
    assert db.get(bm.id) is None


def test_soft_delete_visible_with_include_archived(db):
    bm = db.add("https://example.com", title="Example")
    db.delete(bm.id)
    found = db.get(bm.id, include_archived=True)
    assert found is not None
    assert found.archived_at is not None


def test_hard_delete_gone_even_with_include_archived(db):
    bm = db.add("https://example.com", title="Example")
    db.delete(bm.id, hard=True)
    assert db.get(bm.id, include_archived=True) is None


def test_restore_brings_back_soft_deleted(db):
    bm = db.add("https://example.com", title="Example")
    db.delete(bm.id)
    db.restore(bm.id)
    found = db.get(bm.id)
    assert found is not None
    assert found.archived_at is None


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_returns_active_bookmarks(db):
    db.add("https://a.com", title="A")
    db.add("https://b.com", title="B")
    bms = db.list()
    assert len(bms) == 2


def test_list_excludes_archived_by_default(db):
    bm = db.add("https://example.com", title="Example")
    db.add("https://other.com", title="Other")
    db.delete(bm.id)
    bms = db.list()
    assert len(bms) == 1
    assert bms[0].url != "https://example.com"


def test_list_includes_archived_when_flag_set(db):
    bm = db.add("https://example.com", title="Example")
    db.add("https://other.com", title="Other")
    db.delete(bm.id)
    bms = db.list(include_archived=True)
    assert len(bms) == 2


def test_list_limit(db):
    for i in range(5):
        db.add(f"https://example{i}.com", title=f"Example {i}")
    bms = db.list(limit=3)
    assert len(bms) == 3


# ---------------------------------------------------------------------------
# tag / list_tags
# ---------------------------------------------------------------------------


def test_add_tags_to_bookmark(db):
    bm = db.add("https://example.com", title="Example")
    db.tag(bm.id, add=["python", "web"])
    fresh = db.get(bm.id)
    names = {t.name for t in fresh.tags}
    assert names == {"python", "web"}


def test_remove_tags_from_bookmark(db):
    bm = db.add("https://example.com", title="Example", tags=["python", "web"])
    db.tag(bm.id, remove=["web"])
    fresh = db.get(bm.id)
    names = {t.name for t in fresh.tags}
    assert "web" not in names
    assert "python" in names


def test_tag_reuse(db):
    """Adding the same tag to two bookmarks should use one Tag row."""
    db.add("https://a.com", title="A", tags=["python"])
    db.add("https://b.com", title="B", tags=["python"])
    tags = db.list_tags()
    python_tags = [t for t in tags if t.name == "python"]
    assert len(python_tags) == 1


def test_list_tags_returns_tags(db):
    db.add("https://a.com", title="A", tags=["python", "web"])
    tags = db.list_tags()
    names = {t.name for t in tags}
    assert "python" in names
    assert "web" in names


# ---------------------------------------------------------------------------
# annotate / get_annotations
# ---------------------------------------------------------------------------


def test_add_annotation_creates_annotation(db):
    bm = db.add("https://example.com", title="Example")
    ann = db.annotate(bm.unique_id, "This is a great resource")
    assert ann.id is not None
    assert ann.text == "This is a great resource"
    assert ann.bookmark_id == bm.id


def test_annotation_id_is_nonempty_string(db):
    bm = db.add("https://example.com", title="Example")
    ann = db.annotate(bm.unique_id, "Note")
    assert isinstance(ann.id, str)
    assert len(ann.id) > 0


def test_list_annotations_returns_all(db):
    bm = db.add("https://example.com", title="Example")
    db.annotate(bm.unique_id, "First note")
    db.annotate(bm.unique_id, "Second note")
    anns = db.get_annotations(bm.unique_id)
    texts = {a.text for a in anns}
    assert "First note" in texts
    assert "Second note" in texts


def test_list_annotations_empty(db):
    bm = db.add("https://example.com", title="Example")
    anns = db.get_annotations(bm.unique_id)
    assert anns == []


def test_list_annotations_only_returns_for_target_bookmark(db):
    bm1 = db.add("https://a.com", title="A")
    bm2 = db.add("https://b.com", title="B")
    db.annotate(bm1.unique_id, "Note for A")
    db.annotate(bm2.unique_id, "Note for B")
    anns = db.get_annotations(bm1.unique_id)
    assert len(anns) == 1
    assert anns[0].text == "Note for A"


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


def test_log_event_does_not_raise(db):
    """log_event should complete without error."""
    db.log_event("add", "bookmark", entity_id="abc123", data={"url": "https://example.com"})


def test_log_event_with_minimal_args(db):
    db.log_event("import", "bookmark")
