"""Tests for bookmark_memex.mcp._create_tools.

Tests exercise the pure-Python sync functions returned by _create_tools
directly, without starting an MCP server.
"""
from __future__ import annotations

import pytest

from bookmark_memex.db import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_data(tmp_db_path):
    """Return (db, db_path) with two bookmarks and one annotation."""
    db = Database(tmp_db_path)
    db.add("https://example.com", title="Example Site", tags=["test"])
    db.add("https://python.org", title="Python", tags=["programming"], starred=True)
    # Annotate the first bookmark
    first = db.list()[1]  # list() is desc order, so index 1 = first added
    db.annotate(first.unique_id, "A test note")
    return db, tmp_db_path


@pytest.fixture
def tools(db_with_data):
    """Return the tools dict for the test database."""
    from bookmark_memex.mcp import _create_tools
    _, db_path = db_with_data
    return _create_tools(db_path)


# ---------------------------------------------------------------------------
# get_schema
# ---------------------------------------------------------------------------


def test_get_schema_returns_string(tools):
    schema = tools["get_schema"]()
    assert isinstance(schema, str)


def test_get_schema_contains_bookmarks_table(tools):
    schema = tools["get_schema"]()
    assert "bookmarks" in schema


def test_get_schema_contains_create_table(tools):
    schema = tools["get_schema"]()
    assert "CREATE TABLE" in schema


# ---------------------------------------------------------------------------
# execute_sql
# ---------------------------------------------------------------------------


def test_execute_sql_select_returns_list(tools):
    result = tools["execute_sql"]("SELECT * FROM bookmarks")
    assert isinstance(result, list)


def test_execute_sql_select_correct_count(tools, db_with_data):
    db, _ = db_with_data
    all_bms = db.list()
    result = tools["execute_sql"]("SELECT * FROM bookmarks WHERE archived_at IS NULL")
    assert len(result) == len(all_bms)


def test_execute_sql_returns_dicts(tools):
    result = tools["execute_sql"]("SELECT * FROM bookmarks LIMIT 1")
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert "url" in result[0]


def test_execute_sql_rejects_delete(tools):
    result = tools["execute_sql"]("DELETE FROM bookmarks")
    assert isinstance(result, str)
    assert "error" in result.lower() or "not allowed" in result.lower() or "SELECT" in result


def test_execute_sql_rejects_drop(tools):
    result = tools["execute_sql"]("DROP TABLE bookmarks")
    assert isinstance(result, str)


def test_execute_sql_rejects_insert(tools):
    result = tools["execute_sql"]("INSERT INTO bookmarks (url) VALUES ('x')")
    assert isinstance(result, str)


def test_execute_sql_with_keyword(tools):
    result = tools["execute_sql"]("SELECT count(*) as n FROM bookmarks")
    assert isinstance(result, list)
    assert result[0]["n"] >= 2


def test_execute_sql_with_params(tools):
    result = tools["execute_sql"](
        "SELECT * FROM bookmarks WHERE title = ?",
        params=["Python"],
    )
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["title"] == "Python"


def test_execute_sql_invalid_sql_returns_error_string(tools):
    result = tools["execute_sql"]("SELECT * FROM nonexistent_table_xyz")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_record
# ---------------------------------------------------------------------------


def test_get_record_bookmark_returns_dict(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]
    result = tools["get_record"]("bookmark", bm.unique_id)
    assert isinstance(result, dict)
    assert "url" in result
    assert result["url"] == bm.url


def test_get_record_bookmark_includes_annotations(tools, db_with_data):
    db, _ = db_with_data
    # The annotation was added to the first-added bookmark (example.com)
    bm = db.list()[1]  # desc order, so [1] = example.com
    result = tools["get_record"]("bookmark", bm.unique_id)
    assert "annotations" in result
    assert isinstance(result["annotations"], list)
    assert len(result["annotations"]) >= 1
    assert any("A test note" in a.get("text", "") for a in result["annotations"])


def test_get_record_bookmark_not_found_raises(tools):
    with pytest.raises(ValueError):
        tools["get_record"]("bookmark", "nonexistent_id_000")


def test_get_record_unknown_kind_raises(tools):
    with pytest.raises(ValueError):
        tools["get_record"]("photo", "some-id")


def test_get_record_annotation_returns_dict(tools, db_with_data):
    db, _ = db_with_data
    first_bm = db.list()[1]  # example.com (first added, last in desc list)
    anns = db.get_annotations(first_bm.unique_id)
    assert len(anns) == 1
    ann = anns[0]
    result = tools["get_record"]("annotation", ann.id)
    assert isinstance(result, dict)
    assert result["text"] == "A test note"


def test_get_record_annotation_not_found_raises(tools):
    with pytest.raises(ValueError):
        tools["get_record"]("annotation", "00000000000000000000000000000000")


# ---------------------------------------------------------------------------
# mutate – add
# ---------------------------------------------------------------------------


def test_mutate_add_succeeds(tools):
    result = tools["mutate"]([{"op": "add", "url": "https://new-site.example.com", "title": "New"}])
    assert result["total"] == 1
    assert result["succeeded"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "ok"


def test_mutate_add_returns_unique_id(tools):
    result = tools["mutate"]([{"op": "add", "url": "https://unique-site.example.com"}])
    assert "unique_id" in result["results"][0]
    assert result["results"][0]["unique_id"] is not None


def test_mutate_add_multiple(tools):
    ops = [
        {"op": "add", "url": "https://site-a.example.com", "title": "A"},
        {"op": "add", "url": "https://site-b.example.com", "title": "B"},
    ]
    result = tools["mutate"](ops)
    assert result["total"] == 2
    assert result["succeeded"] == 2


# ---------------------------------------------------------------------------
# mutate – delete (soft)
# ---------------------------------------------------------------------------


def test_mutate_soft_delete_hides_from_get(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]
    uid = bm.unique_id

    result = tools["mutate"]([{"op": "delete", "id": bm.id}])
    assert result["succeeded"] == 1

    # After soft delete, get_record should raise
    with pytest.raises(ValueError):
        tools["get_record"]("bookmark", uid)


def test_mutate_soft_delete_record_still_exists_with_include_archived(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]

    tools["mutate"]([{"op": "delete", "id": bm.id}])

    # Still retrievable if we look in the database directly
    found = db.get(bm.id, include_archived=True)
    assert found is not None
    assert found.archived_at is not None


def test_mutate_hard_delete_removes_record(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]

    tools["mutate"]([{"op": "delete", "id": bm.id, "hard": True}])

    found = db.get(bm.id, include_archived=True)
    assert found is None


# ---------------------------------------------------------------------------
# mutate – update
# ---------------------------------------------------------------------------


def test_mutate_update_title(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]

    result = tools["mutate"]([{"op": "update", "id": bm.id, "title": "Updated Title"}])
    assert result["succeeded"] == 1

    updated = db.get(bm.id)
    assert updated.title == "Updated Title"


# ---------------------------------------------------------------------------
# mutate – tag
# ---------------------------------------------------------------------------


def test_mutate_tag_add(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]

    result = tools["mutate"]([{"op": "tag", "ids": [bm.id], "add": ["newtag"]}])
    assert result["succeeded"] == 1

    updated = db.get(bm.id)
    tag_names = [t.name for t in updated.tags]
    assert "newtag" in tag_names


def test_mutate_tag_remove(tools, db_with_data):
    db, _ = db_with_data
    # python.org has tag "programming"
    bm = db.list()[0]  # most recently added = python.org
    assert any(t.name == "programming" for t in bm.tags)

    result = tools["mutate"]([{"op": "tag", "ids": [bm.id], "remove": ["programming"]}])
    assert result["succeeded"] == 1

    updated = db.get(bm.id)
    tag_names = [t.name for t in updated.tags]
    assert "programming" not in tag_names


# ---------------------------------------------------------------------------
# mutate – annotate
# ---------------------------------------------------------------------------


def test_mutate_annotate_creates_annotation(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]

    result = tools["mutate"]([
        {"op": "annotate", "bookmark_unique_id": bm.unique_id, "text": "MCP note"}
    ])
    assert result["succeeded"] == 1

    anns = db.get_annotations(bm.unique_id)
    assert any(a.text == "MCP note" for a in anns)


# ---------------------------------------------------------------------------
# mutate – restore
# ---------------------------------------------------------------------------


def test_mutate_restore_after_soft_delete(tools, db_with_data):
    db, _ = db_with_data
    bm = db.list()[0]

    # Soft delete first
    tools["mutate"]([{"op": "delete", "id": bm.id}])
    assert db.get(bm.id) is None

    # Restore
    result = tools["mutate"]([{"op": "restore", "ids": [bm.id]}])
    assert result["succeeded"] == 1
    assert db.get(bm.id) is not None


# ---------------------------------------------------------------------------
# mutate – error resilience
# ---------------------------------------------------------------------------


def test_mutate_unknown_op_does_not_crash_batch(tools):
    ops = [
        {"op": "add", "url": "https://resilience.example.com"},
        {"op": "nonexistent_op"},
    ]
    result = tools["mutate"](ops)
    assert result["total"] == 2
    assert result["succeeded"] == 1
    assert result["results"][1]["status"] == "error"


def test_mutate_empty_batch(tools):
    result = tools["mutate"]([])
    assert result["total"] == 0
    assert result["succeeded"] == 0


# ---------------------------------------------------------------------------
# create_server (smoke test)
# ---------------------------------------------------------------------------


def test_create_server_returns_fastmcp(tmp_db_path):
    from bookmark_memex.mcp import create_server
    import fastmcp
    server = create_server(tmp_db_path)
    assert isinstance(server, fastmcp.FastMCP)


def test_create_server_has_required_tools(tmp_db_path):
    import asyncio
    from bookmark_memex.mcp import create_server
    server = create_server(tmp_db_path)
    tools_map = asyncio.run(server.get_tools())
    tool_names = set(tools_map.keys())
    required = {"get_schema", "execute_sql", "get_record", "mutate", "import_bookmarks", "export_bookmarks"}
    assert required.issubset(tool_names)
