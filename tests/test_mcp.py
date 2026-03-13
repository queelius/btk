"""Tests for the btk MCP server (get_schema, query, mutate, import, and export tools)."""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from btk.mcp import create_server


@pytest.fixture
def db_path(tmp_path):
    """Create a test SQLite database with btk schema and sample data."""
    db = tmp_path / "test_btk.db"
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE bookmarks (
            id INTEGER PRIMARY KEY,
            unique_id TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            description TEXT,
            bookmark_type TEXT,
            added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_visited TIMESTAMP,
            visit_count INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0,
            archived INTEGER DEFAULT 0,
            pinned INTEGER DEFAULT 0,
            reachable INTEGER DEFAULT 1
        );

        CREATE TABLE tags (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT
        );

        CREATE TABLE bookmark_tags (
            bookmark_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (bookmark_id, tag_id),
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE bookmark_sources (
            id INTEGER PRIMARY KEY,
            bookmark_id INTEGER NOT NULL,
            source_type TEXT,
            source_name TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE
        );

        CREATE TABLE bookmark_visits (
            id INTEGER PRIMARY KEY,
            bookmark_id INTEGER NOT NULL,
            visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_type TEXT,
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE
        );

        CREATE TABLE bookmark_media (
            id INTEGER PRIMARY KEY,
            bookmark_id INTEGER NOT NULL,
            media_type TEXT,
            media_source TEXT,
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE
        );

        -- Sample data (unique_id = sha256(url)[:8])
        INSERT INTO bookmarks (id, unique_id, url, title)
        VALUES (1, '100680ad', 'https://example.com', 'Example Site');

        INSERT INTO bookmarks (id, unique_id, url, title, stars)
        VALUES (2, '25d3e0d8', 'https://python.org', 'Python', 1);

        INSERT INTO tags (id, name) VALUES (1, 'programming');
        INSERT INTO tags (id, name) VALUES (2, 'web');

        INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (2, 1);
        """
    )

    conn.commit()
    conn.close()
    return str(db)


def _call(server, tool_name, arguments=None):
    """Synchronous helper to call a tool on the MCP server via Client."""
    from fastmcp import Client

    async def _run():
        async with Client(server) as client:
            result = await client.call_tool(tool_name, arguments or {})
            return result.content[0].text

    return asyncio.run(_run())


# ---------- get_schema tests ----------


class TestGetSchema:
    def test_returns_ddl_and_row_counts(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "get_schema")
        assert "CREATE TABLE" in text
        assert "bookmarks: 2 rows" in text

    def test_includes_all_tables(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "get_schema")
        for table in [
            "bookmarks",
            "tags",
            "bookmark_tags",
            "bookmark_sources",
            "bookmark_visits",
            "bookmark_media",
        ]:
            assert table in text, f"Missing table: {table}"


# ---------- query tests ----------


class TestQuery:
    def test_select_returns_rows(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "query", {"sql": "SELECT id, title FROM bookmarks ORDER BY id"})
        rows = json.loads(text)
        assert len(rows) == 2
        assert rows[0]["title"] == "Example Site"
        assert rows[1]["title"] == "Python"

    def test_select_with_params(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "query", {"sql": "SELECT title FROM bookmarks WHERE stars = ?", "params": [1]})
        rows = json.loads(text)
        assert len(rows) == 1
        assert rows[0]["title"] == "Python"

    def test_rejects_non_select(self, db_path):
        server = create_server(db_path=db_path)
        for stmt in [
            "INSERT INTO bookmarks (unique_id, url, title) VALUES ('x','x','x')",
            "UPDATE bookmarks SET title = 'hacked'",
            "DELETE FROM bookmarks",
            "DROP TABLE bookmarks",
        ]:
            text = _call(server, "query", {"sql": stmt})
            result = json.loads(text)
            assert "error" in result, f"Should reject: {stmt}"

    def test_rejects_pragma(self, db_path):
        """PRAGMA statements should be rejected (some are write operations)."""
        server = create_server(db_path=db_path)
        for stmt in [
            "PRAGMA writable_schema = ON",
            "PRAGMA journal_mode = DELETE",
            "PRAGMA table_info(bookmarks)",
        ]:
            text = _call(server, "query", {"sql": stmt})
            result = json.loads(text)
            assert "error" in result, f"Should reject: {stmt}"

    def test_join_query(self, db_path):
        server = create_server(db_path=db_path)
        sql = """
            SELECT b.title, t.name AS tag
            FROM bookmarks b
            JOIN bookmark_tags bt ON b.id = bt.bookmark_id
            JOIN tags t ON bt.tag_id = t.id
        """
        text = _call(server, "query", {"sql": sql})
        rows = json.loads(text)
        assert len(rows) == 1
        assert rows[0]["title"] == "Python"
        assert rows[0]["tag"] == "programming"

    def test_empty_result(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "query", {"sql": "SELECT * FROM bookmarks WHERE title = 'nonexistent'"})
        rows = json.loads(text)
        assert rows == []

    def test_sql_error_returns_message(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "query", {"sql": "SELECT * FROM nonexistent_table"})
        result = json.loads(text)
        assert "error" in result


# ---------- mutate: add tests ----------


class TestMutateAdd:
    def test_add_single_bookmark(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "add", "url": "https://rust-lang.org", "title": "Rust"}
        ]})
        result = json.loads(text)
        assert result["total"] == 1
        assert result["succeeded"] == 1
        assert result["results"][0]["status"] == "ok"
        new_id = result["results"][0]["id"]
        assert isinstance(new_id, int)

        # Verify via query
        text = _call(server, "query", {
            "sql": "SELECT title FROM bookmarks WHERE id = ?",
            "params": [new_id],
        })
        rows = json.loads(text)
        assert len(rows) == 1
        assert rows[0]["title"] == "Rust"

    def test_add_with_tags(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "add", "url": "https://docs.python.org", "title": "Python Docs",
             "tags": ["python", "tutorial"]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        new_id = result["results"][0]["id"]

        # Verify tags linked
        text = _call(server, "query", {
            "sql": (
                "SELECT t.name FROM tags t "
                "JOIN bookmark_tags bt ON t.id = bt.tag_id "
                "WHERE bt.bookmark_id = ? ORDER BY t.name"
            ),
            "params": [new_id],
        })
        rows = json.loads(text)
        tag_names = [r["name"] for r in rows]
        assert "python" in tag_names
        assert "tutorial" in tag_names

    def test_add_duplicate_url_skips(self, db_path):
        """https://example.com is already in the fixture."""
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "add", "url": "https://example.com", "title": "Dupe"}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "skipped"
        assert result["results"][0]["existing_id"] == 1
        assert result["skipped"] == 1
        assert result["succeeded"] == 0

    def test_add_multiple_in_batch(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "add", "url": "https://a.com"},
            {"op": "add", "url": "https://b.com"},
            {"op": "add", "url": "https://c.com"},
        ]})
        result = json.loads(text)
        assert result["total"] == 3
        assert result["succeeded"] == 3
        for r in result["results"]:
            assert r["status"] == "ok"


# ---------- mutate: update tests ----------


class TestMutateUpdate:
    def test_update_single_field(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "update", "bookmark_ids": [1], "fields": {"stars": True}}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["affected"] == 1

        # Verify via query
        text = _call(server, "query", {
            "sql": "SELECT stars FROM bookmarks WHERE id = 1"
        })
        rows = json.loads(text)
        assert rows[0]["stars"] == 1

    def test_update_multiple_bookmarks(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "update", "bookmark_ids": [1, 2],
             "fields": {"description": "Updated desc"}}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["affected"] == 2

    def test_update_nonexistent(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "update", "bookmark_ids": [9999],
             "fields": {"title": "Ghost"}}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["affected"] == 0

    def test_update_rejects_unsafe_fields(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "update", "bookmark_ids": [1], "fields": {"id": 999}}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "error"
        assert "Disallowed fields" in result["results"][0]["reason"]


# ---------- mutate: delete tests ----------


class TestMutateDelete:
    def test_delete_bookmark(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "delete", "bookmark_ids": [1]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["affected"] == 1

        # Verify count dropped
        text = _call(server, "query", {
            "sql": "SELECT COUNT(*) AS cnt FROM bookmarks"
        })
        rows = json.loads(text)
        assert rows[0]["cnt"] == 1

    def test_delete_multiple(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "delete", "bookmark_ids": [1, 2]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["affected"] == 2


# ---------- mutate: tag tests ----------


class TestMutateTag:
    def test_add_tags(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "tag", "bookmark_ids": [1], "add": ["tutorial", "web"]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["tags_added"] == 2

        # Verify via query
        text = _call(server, "query", {
            "sql": (
                "SELECT t.name FROM tags t "
                "JOIN bookmark_tags bt ON t.id = bt.tag_id "
                "WHERE bt.bookmark_id = 1 ORDER BY t.name"
            )
        })
        rows = json.loads(text)
        tag_names = [r["name"] for r in rows]
        assert "tutorial" in tag_names
        assert "web" in tag_names

    def test_remove_tags(self, db_path):
        """Bookmark 2 has tag 'programming'; remove it."""
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "tag", "bookmark_ids": [2], "remove": ["programming"]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["tags_removed"] == 1

        # Verify 0 tags left
        text = _call(server, "query", {
            "sql": "SELECT COUNT(*) AS cnt FROM bookmark_tags WHERE bookmark_id = 2"
        })
        rows = json.loads(text)
        assert rows[0]["cnt"] == 0

    def test_tag_multiple_bookmarks(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "tag", "bookmark_ids": [1, 2], "add": ["batch-tagged"]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["tags_added"] == 2

        # Verify both bookmarks have the tag
        text = _call(server, "query", {
            "sql": (
                "SELECT COUNT(*) AS cnt FROM bookmark_tags bt "
                "JOIN tags t ON bt.tag_id = t.id "
                "WHERE t.name = 'batch-tagged'"
            )
        })
        rows = json.loads(text)
        assert rows[0]["cnt"] == 2


# ---------- mutate: merge tests ----------


class TestMutateMerge:
    def test_merge_moves_tags(self, db_path):
        """Add bookmarks 3 and 4; give 4 a tag; merge 4 into 3; verify tag moved."""
        # Insert extra bookmarks and a tag directly
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO bookmarks (id, unique_id, url, title) "
            "VALUES (3, 'merge_aa', 'https://merge-a.com', 'Merge A')"
        )
        cur.execute(
            "INSERT INTO bookmarks (id, unique_id, url, title) "
            "VALUES (4, 'merge_bb', 'https://merge-b.com', 'Merge B')"
        )
        cur.execute("INSERT INTO tags (id, name) VALUES (10, 'merge-tag')")
        cur.execute("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (4, 10)")
        conn.commit()
        conn.close()

        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "merge", "keep_id": 3, "duplicate_ids": [4]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["keep_id"] == 3
        assert result["results"][0]["deleted"] == 1

        # Verify tag moved to keeper
        text = _call(server, "query", {
            "sql": (
                "SELECT t.name FROM tags t "
                "JOIN bookmark_tags bt ON t.id = bt.tag_id "
                "WHERE bt.bookmark_id = 3"
            )
        })
        rows = json.loads(text)
        tag_names = [r["name"] for r in rows]
        assert "merge-tag" in tag_names

        # Verify bookmark 4 is deleted
        text = _call(server, "query", {
            "sql": "SELECT id FROM bookmarks WHERE id = 4"
        })
        rows = json.loads(text)
        assert len(rows) == 0

    def test_merge_keeps_stars(self, db_path):
        """Bookmark 3 has stars=0, bookmark 4 has stars=1; merge 4 into 3."""
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO bookmarks (id, unique_id, url, title, stars) "
            "VALUES (3, 'star_aa', 'https://star-a.com', 'Star A', 0)"
        )
        cur.execute(
            "INSERT INTO bookmarks (id, unique_id, url, title, stars) "
            "VALUES (4, 'star_bb', 'https://star-b.com', 'Star B', 1)"
        )
        conn.commit()
        conn.close()

        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "merge", "keep_id": 3, "duplicate_ids": [4]}
        ]})
        result = json.loads(text)
        assert result["results"][0]["status"] == "ok"

        # Verify keeper has stars=1
        text = _call(server, "query", {
            "sql": "SELECT stars FROM bookmarks WHERE id = 3"
        })
        rows = json.loads(text)
        assert rows[0]["stars"] == 1


# ---------- transaction safety tests ----------


class TestTransactionSafety:
    def test_bad_op_does_not_corrupt(self, db_path):
        """Batch with one good add + one update on nonexistent; verify add persisted."""
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "add", "url": "https://safe.com", "title": "Safe"},
            {"op": "update", "bookmark_ids": [9999], "fields": {"title": "Nope"}},
        ]})
        result = json.loads(text)
        assert result["total"] == 2
        assert result["succeeded"] == 2  # update on nonexistent still succeeds with affected=0
        assert result["skipped"] == 0

        # Verify the add persisted
        text = _call(server, "query", {
            "sql": "SELECT title FROM bookmarks WHERE url = 'https://safe.com'"
        })
        rows = json.loads(text)
        assert len(rows) == 1
        assert rows[0]["title"] == "Safe"

    def test_unknown_op_returns_error(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": [
            {"op": "fly_to_moon"}
        ]})
        result = json.loads(text)
        assert result["total"] == 1
        assert result["succeeded"] == 0
        assert result["results"][0]["status"] == "error"
        assert "Unknown operation" in result["results"][0]["reason"]

    def test_empty_batch(self, db_path):
        server = create_server(db_path=db_path)
        text = _call(server, "mutate", {"operations": []})
        result = json.loads(text)
        assert result["total"] == 0
        assert result["succeeded"] == 0
        assert result["skipped"] == 0
        assert result["results"] == []


# ---------- btk_db_path fixture for import/export tests ----------


@pytest.fixture
def btk_db_path(tmp_path):
    """Create a btk database using the ORM (needed for import/export tests)."""
    from btk.db import Database

    path = str(tmp_path / "btk_test.db")
    db = Database(path=path)
    db.add(url="https://example.com", title="Example", stars=True)
    db.add(url="https://python.org", title="Python", tags=["programming"])
    return path


# ---------- import_bookmarks tests ----------


class TestImport:
    def test_import_html(self, btk_db_path, tmp_path):
        """Import a minimal Netscape HTML bookmark file and verify via query."""
        html_file = tmp_path / "bookmarks.html"
        html_file.write_text(
            '<!DOCTYPE NETSCAPE-Bookmark-file-1>\n'
            '<DL><DT><A HREF="https://rust-lang.org">Rust</A>\n'
            '<DT><A HREF="https://golang.org">Go</A></DL>',
            encoding="utf-8",
        )

        server = create_server(db_path=btk_db_path)
        text = _call(server, "import_bookmarks", {
            "file_path": str(html_file),
        })
        result = json.loads(text)
        assert result["status"] == "ok"
        assert result["imported"] == 2

        # Verify bookmarks exist
        text = _call(server, "query", {
            "sql": "SELECT COUNT(*) AS cnt FROM bookmarks",
        })
        rows = json.loads(text)
        assert rows[0]["cnt"] == 4  # 2 original + 2 imported

    def test_import_json(self, btk_db_path, tmp_path):
        """Import a minimal JSON bookmark file and verify via query."""
        json_file = tmp_path / "bookmarks.json"
        json_file.write_text(json.dumps([
            {"url": "https://docs.rs", "title": "Docs.rs", "tags": ["rust"]},
            {"url": "https://crates.io", "title": "Crates.io"},
        ]), encoding="utf-8")

        server = create_server(db_path=btk_db_path)
        text = _call(server, "import_bookmarks", {
            "file_path": str(json_file),
        })
        result = json.loads(text)
        assert result["status"] == "ok"
        assert result["imported"] == 2

        # Verify
        text = _call(server, "query", {
            "sql": "SELECT title FROM bookmarks WHERE url = 'https://docs.rs'",
        })
        rows = json.loads(text)
        assert len(rows) == 1
        assert rows[0]["title"] == "Docs.rs"

    def test_import_nonexistent_file(self, btk_db_path):
        """Importing a nonexistent file returns an error."""
        server = create_server(db_path=btk_db_path)
        text = _call(server, "import_bookmarks", {
            "file_path": "/no/such/file.json",
        })
        result = json.loads(text)
        assert "error" in result
        assert "not found" in result["error"].lower() or "File not found" in result["error"]


# ---------- export_bookmarks tests ----------


class TestExport:
    def test_export_json(self, btk_db_path, tmp_path):
        """Export all bookmarks to JSON and verify file content."""
        out_file = tmp_path / "export.json"

        server = create_server(db_path=btk_db_path)
        text = _call(server, "export_bookmarks", {
            "file_path": str(out_file),
            "format": "json",
        })
        result = json.loads(text)
        assert result["status"] == "ok"
        assert result["exported"] == 2
        assert result["format"] == "json"

        # Verify file content
        with open(out_file) as f:
            data = json.load(f)
        assert len(data) == 2
        urls = {b["url"] for b in data}
        assert "https://example.com" in urls
        assert "https://python.org" in urls

    def test_export_with_bookmark_ids(self, btk_db_path, tmp_path):
        """Export only specific bookmarks by ID and verify count."""
        out_file = tmp_path / "filtered.json"

        server = create_server(db_path=btk_db_path)

        # First, find the ID of the starred bookmark via query
        text = _call(server, "query", {
            "sql": "SELECT id FROM bookmarks WHERE stars = 1",
        })
        rows = json.loads(text)
        starred_ids = [r["id"] for r in rows]
        assert len(starred_ids) == 1

        # Export only those IDs
        text = _call(server, "export_bookmarks", {
            "file_path": str(out_file),
            "format": "json",
            "bookmark_ids": starred_ids,
        })
        result = json.loads(text)
        assert result["status"] == "ok"
        assert result["exported"] == 1

        # Verify only starred bookmark exported
        with open(out_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["url"] == "https://example.com"
