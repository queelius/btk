"""
MCP (Model Context Protocol) server for btk.

Exposes bookmark database tools over MCP using FastMCP and aiosqlite.
"""

import json
from typing import Optional

import aiosqlite
from fastmcp import FastMCP

_ALLOWED_KEYWORDS = frozenset({"SELECT", "WITH", "EXPLAIN", "PRAGMA"})

_UPDATE_WHITELIST = frozenset({
    "title", "description", "stars", "archived", "pinned",
    "bookmark_type", "reachable", "visit_count", "last_visited",
})


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    """Resolve the database path from explicit argument, config, or fallback."""
    if db_path:
        return db_path

    try:
        from btk.config import get_config

        config = get_config()
        return config.database
    except Exception:
        pass

    return "btk.db"


async def _op_add(conn: aiosqlite.Connection, op: dict) -> dict:
    """Add a new bookmark."""
    from hashlib import sha256
    from datetime import datetime, timezone

    url = op.get("url")
    if not url:
        return {"status": "error", "reason": "Missing required field: url"}

    unique_id = sha256(url.encode()).hexdigest()[:8]

    # Check for duplicate
    cursor = await conn.execute(
        "SELECT id FROM bookmarks WHERE unique_id = ?", (unique_id,)
    )
    existing = await cursor.fetchone()
    if existing:
        return {"status": "skipped", "reason": "Duplicate URL", "existing_id": existing[0]}

    title = op.get("title", url)
    description = op.get("description")
    bookmark_type = op.get("bookmark_type", "bookmark")
    stars = 1 if op.get("stars") else 0
    added = op.get("added") or datetime.now(timezone.utc).isoformat()

    await conn.execute(
        "INSERT INTO bookmarks (unique_id, url, title, description, bookmark_type, added, stars)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (unique_id, url, title, description, bookmark_type, added, stars),
    )
    cursor = await conn.execute("SELECT last_insert_rowid()")
    (bookmark_id,) = await cursor.fetchone()

    # Handle tags
    tags = op.get("tags", [])
    for tag_name in tags:
        cursor = await conn.execute(
            "SELECT id FROM tags WHERE name = ?", (tag_name,)
        )
        row = await cursor.fetchone()
        if row:
            tag_id = row[0]
        else:
            await conn.execute(
                "INSERT INTO tags (name) VALUES (?)", (tag_name,)
            )
            cursor = await conn.execute("SELECT last_insert_rowid()")
            (tag_id,) = await cursor.fetchone()
        await conn.execute(
            "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag_id) VALUES (?, ?)",
            (bookmark_id, tag_id),
        )

    return {"status": "ok", "id": bookmark_id}


async def _op_update(conn: aiosqlite.Connection, op: dict) -> dict:
    """Update fields on one or more bookmarks."""
    bookmark_ids = op.get("bookmark_ids", [])
    fields = op.get("fields", {})

    if not bookmark_ids:
        return {"status": "error", "reason": "Missing required field: bookmark_ids"}
    if not fields:
        return {"status": "error", "reason": "Missing required field: fields"}

    disallowed = set(fields.keys()) - _UPDATE_WHITELIST
    if disallowed:
        return {"status": "error", "reason": f"Disallowed fields: {', '.join(sorted(disallowed))}"}

    # Normalize bools to int for SQLite
    normalized = {}
    for k, v in fields.items():
        if isinstance(v, bool):
            normalized[k] = int(v)
        else:
            normalized[k] = v

    set_clause = ", ".join(f"{k} = ?" for k in normalized)
    values = list(normalized.values())
    placeholders = ", ".join("?" for _ in bookmark_ids)
    values.extend(bookmark_ids)

    cursor = await conn.execute(
        f"UPDATE bookmarks SET {set_clause} WHERE id IN ({placeholders})",
        values,
    )

    return {"status": "ok", "affected": cursor.rowcount}


async def _op_delete(conn: aiosqlite.Connection, op: dict) -> dict:
    """Delete bookmarks by ID."""
    bookmark_ids = op.get("bookmark_ids", [])
    if not bookmark_ids:
        return {"status": "error", "reason": "Missing required field: bookmark_ids"}

    placeholders = ", ".join("?" for _ in bookmark_ids)

    # Clean up satellite tables that reference the bookmarks
    for table in ("bookmark_tags", "bookmark_sources", "bookmark_visits", "bookmark_media"):
        await conn.execute(
            f"DELETE FROM {table} WHERE bookmark_id IN ({placeholders})",
            bookmark_ids,
        )

    cursor = await conn.execute(
        f"DELETE FROM bookmarks WHERE id IN ({placeholders})",
        bookmark_ids,
    )

    return {"status": "ok", "affected": cursor.rowcount}


async def _op_tag(conn: aiosqlite.Connection, op: dict) -> dict:
    """Add or remove tags from bookmarks."""
    bookmark_ids = op.get("bookmark_ids", [])
    add_tags = op.get("add", [])
    remove_tags = op.get("remove", [])

    if not bookmark_ids:
        return {"status": "error", "reason": "Missing required field: bookmark_ids"}
    if not add_tags and not remove_tags:
        return {"status": "error", "reason": "Must specify at least one of 'add' or 'remove'"}

    tags_added = 0
    tags_removed = 0

    # Add tags
    for tag_name in add_tags:
        cursor = await conn.execute(
            "SELECT id FROM tags WHERE name = ?", (tag_name,)
        )
        row = await cursor.fetchone()
        if row:
            tag_id = row[0]
        else:
            await conn.execute(
                "INSERT INTO tags (name) VALUES (?)", (tag_name,)
            )
            cursor = await conn.execute("SELECT last_insert_rowid()")
            (tag_id,) = await cursor.fetchone()

        for bid in bookmark_ids:
            cursor = await conn.execute(
                "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag_id) VALUES (?, ?)",
                (bid, tag_id),
            )
            tags_added += cursor.rowcount

    # Remove tags
    for tag_name in remove_tags:
        cursor = await conn.execute(
            "SELECT id FROM tags WHERE name = ?", (tag_name,)
        )
        row = await cursor.fetchone()
        if not row:
            continue
        tag_id = row[0]

        placeholders = ", ".join("?" for _ in bookmark_ids)
        cursor = await conn.execute(
            f"DELETE FROM bookmark_tags WHERE tag_id = ? AND bookmark_id IN ({placeholders})",
            [tag_id] + list(bookmark_ids),
        )
        tags_removed += cursor.rowcount

    return {"status": "ok", "tags_added": tags_added, "tags_removed": tags_removed}


async def _op_merge(conn: aiosqlite.Connection, op: dict) -> dict:
    """Merge duplicate bookmarks into a keeper."""
    keep_id = op.get("keep_id")
    duplicate_ids = op.get("duplicate_ids", [])

    if keep_id is None:
        return {"status": "error", "reason": "Missing required field: keep_id"}
    if not duplicate_ids:
        return {"status": "error", "reason": "Missing required field: duplicate_ids"}

    # Verify keeper exists
    cursor = await conn.execute(
        "SELECT id FROM bookmarks WHERE id = ?", (keep_id,)
    )
    if not await cursor.fetchone():
        return {"status": "error", "reason": f"Keeper bookmark {keep_id} not found"}

    placeholders = ", ".join("?" for _ in duplicate_ids)

    # Move tags
    await conn.execute(
        f"INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag_id) "
        f"SELECT ?, tag_id FROM bookmark_tags WHERE bookmark_id IN ({placeholders})",
        [keep_id] + list(duplicate_ids),
    )

    # Move sources
    await conn.execute(
        f"UPDATE bookmark_sources SET bookmark_id = ? WHERE bookmark_id IN ({placeholders})",
        [keep_id] + list(duplicate_ids),
    )

    # Move visits
    await conn.execute(
        f"UPDATE OR IGNORE bookmark_visits SET bookmark_id = ? WHERE bookmark_id IN ({placeholders})",
        [keep_id] + list(duplicate_ids),
    )

    # Promote stars/pinned
    cursor = await conn.execute(
        f"SELECT MAX(stars), MAX(pinned) FROM bookmarks WHERE id IN ({placeholders})",
        duplicate_ids,
    )
    row = await cursor.fetchone()
    if row:
        max_stars, max_pinned = row
        if max_stars:
            await conn.execute(
                "UPDATE bookmarks SET stars = 1 WHERE id = ?", (keep_id,)
            )
        if max_pinned:
            await conn.execute(
                "UPDATE bookmarks SET pinned = 1 WHERE id = ?", (keep_id,)
            )

    # Clean up satellite tables for duplicates before deleting
    await conn.execute(
        f"DELETE FROM bookmark_tags WHERE bookmark_id IN ({placeholders})",
        duplicate_ids,
    )
    await conn.execute(
        f"DELETE FROM bookmark_media WHERE bookmark_id IN ({placeholders})",
        duplicate_ids,
    )

    # Delete duplicates
    cursor = await conn.execute(
        f"DELETE FROM bookmarks WHERE id IN ({placeholders})",
        duplicate_ids,
    )
    deleted = cursor.rowcount

    return {"status": "ok", "keep_id": keep_id, "deleted": deleted}


_OP_DISPATCH = {
    "add": _op_add,
    "update": _op_update,
    "delete": _op_delete,
    "tag": _op_tag,
    "merge": _op_merge,
}


def create_server(db_path: Optional[str] = None) -> FastMCP:
    """Create and return a FastMCP server instance with btk tools.

    Args:
        db_path: Path to the SQLite database.  Falls back to btk config
                 or "btk.db" if not provided.

    Returns:
        Configured FastMCP server.
    """
    resolved_path = _resolve_db_path(db_path)
    server = FastMCP("btk")

    @server.tool()
    async def get_schema() -> str:
        """Return CREATE TABLE DDL and row counts for every table in the database."""
        async with aiosqlite.connect(resolved_path) as db:
            cursor = await db.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            tables = await cursor.fetchall()

            parts: list[str] = []
            for name, ddl in tables:
                count_cursor = await db.execute(f"SELECT COUNT(*) FROM [{name}]")
                (count,) = await count_cursor.fetchone()
                parts.append(f"-- {name}: {count} rows\n{ddl};")

            return "\n\n".join(parts)

    @server.tool()
    async def query(sql: str, params: Optional[list] = None) -> str:
        """Execute a read-only SQL query and return results as JSON.

        Only SELECT, WITH, EXPLAIN, and PRAGMA statements are allowed.

        Args:
            sql: The SQL query to execute.
            params: Optional list of bind parameters.
        """
        # Validate: first keyword must be in the whitelist
        stripped = sql.strip()
        first_keyword = stripped.split()[0].upper() if stripped else ""
        if first_keyword not in _ALLOWED_KEYWORDS:
            return json.dumps({"error": f"Disallowed SQL keyword: {first_keyword}"})

        try:
            async with aiosqlite.connect(resolved_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(sql, params or [])
                rows = await cursor.fetchall()
                result = [dict(row) for row in rows]
                return json.dumps(result, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @server.tool()
    async def mutate(operations: list[dict]) -> str:
        """Execute batched write operations on the bookmark database.

        Each operation is a dict with an "op" key indicating the operation type
        (add, update, delete, tag, merge) plus operation-specific fields.

        Operations are executed in order within a single transaction.
        Individual operation errors do not stop the batch.

        Args:
            operations: List of operation dicts, each with an "op" key.

        Returns:
            JSON with total, succeeded counts and per-operation results.
        """
        results = []
        succeeded = 0

        async with aiosqlite.connect(resolved_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")

            for op in operations:
                op_type = op.get("op", "")
                handler = _OP_DISPATCH.get(op_type)

                if handler is None:
                    results.append({
                        "status": "error",
                        "reason": f"Unknown operation: {op_type}",
                    })
                    continue

                try:
                    result = await handler(db, op)
                    results.append(result)
                    if result.get("status") in ("ok", "skipped"):
                        succeeded += 1
                except Exception as exc:
                    results.append({"status": "error", "reason": str(exc)})

            await db.commit()

        return json.dumps({
            "total": len(operations),
            "succeeded": succeeded,
            "results": results,
        })

    return server
