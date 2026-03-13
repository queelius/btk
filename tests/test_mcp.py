"""Tests for the btk MCP server (get_schema and query tools)."""

import asyncio
import json
import sqlite3

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
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        );

        CREATE TABLE bookmark_sources (
            id INTEGER PRIMARY KEY,
            bookmark_id INTEGER NOT NULL,
            source_type TEXT,
            source_name TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id)
        );

        CREATE TABLE bookmark_visits (
            id INTEGER PRIMARY KEY,
            bookmark_id INTEGER NOT NULL,
            visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_type TEXT,
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id)
        );

        CREATE TABLE bookmark_media (
            id INTEGER PRIMARY KEY,
            bookmark_id INTEGER NOT NULL,
            media_type TEXT,
            media_source TEXT,
            FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id)
        );

        -- Sample data
        INSERT INTO bookmarks (id, unique_id, url, title)
        VALUES (1, 'abc12345', 'https://example.com', 'Example Site');

        INSERT INTO bookmarks (id, unique_id, url, title, stars)
        VALUES (2, 'def67890', 'https://python.org', 'Python', 1);

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
