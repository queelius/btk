"""MCP server for bookmark-memex.

Exposes six tools per the memex archive contract:
  - get_schema          (read-only)
  - execute_sql         (read-only)
  - get_record          (read-only)
  - mutate              (read-write)
  - import_bookmarks    (read-write)
  - export_bookmarks    (read-write)

Architecture
------------
``_create_tools(db_path)`` returns a plain dict of synchronous Python
functions.  These are directly testable without starting an MCP server.

``create_server(db_path)`` wraps each function as an async FastMCP tool,
running sync helpers in the default executor when needed.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from bookmark_memex.config import get_config
from bookmark_memex.db import Database

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_KEYWORDS: frozenset[str] = frozenset({"SELECT", "WITH", "EXPLAIN"})


# ---------------------------------------------------------------------------
# Pure-Python tool implementations (sync, testable without MCP)
# ---------------------------------------------------------------------------


def _create_tools(db_path: str) -> dict[str, Any]:
    """Return a dict of sync tool functions bound to *db_path*.

    Keys match the MCP tool names:
        get_schema, execute_sql, get_record, mutate
    (import_bookmarks and export_bookmarks are registered separately in
    create_server because they are heavier and always use the executor.)
    """

    # ------------------------------------------------------------------
    # get_schema
    # ------------------------------------------------------------------

    def get_schema() -> str:
        """Return DDL + row counts for every table in the database."""
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            tables = conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='table' ORDER BY name"
            ).fetchall()
            parts: list[str] = []
            for row in tables:
                name = row["name"]
                ddl = row["sql"] or ""
                try:
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM [{name}]"
                    ).fetchone()[0]
                except Exception:
                    count = "?"
                parts.append(f"-- {name} ({count} rows)\n{ddl};")
            return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # execute_sql
    # ------------------------------------------------------------------

    def execute_sql(
        sql: str,
        params: Optional[list[Any]] = None,
    ) -> list[dict] | str:
        """Execute a read-only SQL statement.

        Only SELECT, WITH, and EXPLAIN are accepted.  Returns a list of
        row dicts on success, or a JSON-encoded error string on failure.
        """
        first_word = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
        if first_word not in _ALLOWED_KEYWORDS:
            return json.dumps({
                "error": (
                    f"Statement type '{first_word}' is not allowed. "
                    f"Only {sorted(_ALLOWED_KEYWORDS)} are permitted."
                )
            })

        uri = f"file:{db_path}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql, params or [])
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # get_record
    # ------------------------------------------------------------------

    def get_record(kind: str, id: str) -> dict:
        """Return a single record by kind and identifier.

        kind='bookmark'   : look up by unique_id; include marginalia.
        kind='marginalia' : look up by UUID; include parent bookmark_uri
                            if the note has a bookmark_id.
        kind='annotation' : legacy alias for 'marginalia'.

        Raises ValueError if the record is not found or kind is unknown.
        """
        db = Database(db_path)

        if kind == "bookmark":
            bm = db.get_by_unique_id(id)
            if bm is None:
                raise ValueError(
                    f"bookmark with unique_id={id!r} not found"
                )
            notes = db.list_marginalia(id)
            return {
                "unique_id": bm.unique_id,
                "uri": bm.uri,
                "url": bm.url,
                "title": bm.title,
                "description": bm.description,
                "bookmark_type": bm.bookmark_type,
                "starred": bm.starred,
                "pinned": bm.pinned,
                "added": bm.added.isoformat() if bm.added else None,
                "last_visited": bm.last_visited.isoformat() if bm.last_visited else None,
                "visit_count": bm.visit_count,
                "tags": [t.name for t in bm.tags],
                "marginalia": [
                    {
                        "id": n.id,
                        "uri": n.uri,
                        "text": n.text,
                        "created_at": n.created_at.isoformat() if n.created_at else None,
                        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
                    }
                    for n in notes
                ],
            }

        if kind in ("marginalia", "annotation"):
            # Fetch via raw SQL to avoid needing a separate lookup method.
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT m.id, m.text, m.created_at, m.updated_at, "
                    "       m.archived_at, "
                    "       m.bookmark_id, b.unique_id AS bookmark_unique_id "
                    "FROM marginalia m "
                    "LEFT JOIN bookmarks b ON m.bookmark_id = b.id "
                    "WHERE m.id = ?",
                    [id],
                ).fetchone()
            if row is None:
                raise ValueError(f"marginalia with id={id!r} not found")
            result: dict = dict(row)
            result["uri"] = f"bookmark-memex://marginalia/{row['id']}"
            if row["bookmark_unique_id"]:
                result["bookmark_uri"] = (
                    f"bookmark-memex://bookmark/{row['bookmark_unique_id']}"
                )
            return result

        raise ValueError(
            f"Unknown record kind {kind!r}. "
            "Supported: 'bookmark', 'marginalia' (alias 'annotation')."
        )

    # ------------------------------------------------------------------
    # mutate
    # ------------------------------------------------------------------

    def mutate(operations: list[dict]) -> dict:
        """Execute a batch of write operations.

        Each operation dict must have an "op" key. Supported ops:

          Bookmark lifecycle:
            add, update, delete, restore, tag
          Marginalia (notes) lifecycle:
            add_marginalia, update_marginalia,
            delete_marginalia, restore_marginalia

          Legacy alias:
            annotate — equivalent to add_marginalia

        Returns {"total": N, "succeeded": N, "results": [...]}.
        Individual failures do not abort the remaining batch.
        """
        db = Database(db_path)
        results: list[dict] = []
        succeeded = 0

        for op in operations:
            op_type = op.get("op", "")
            try:
                result = _dispatch_op(db, op_type, op)
                results.append({"status": "ok", **result})
                succeeded += 1
            except Exception as exc:
                results.append({"status": "error", "op": op_type, "error": str(exc)})

        return {
            "total": len(operations),
            "succeeded": succeeded,
            "results": results,
        }

    return {
        "get_schema": get_schema,
        "execute_sql": execute_sql,
        "get_record": get_record,
        "mutate": mutate,
    }


# ---------------------------------------------------------------------------
# Operation dispatcher (private helper for mutate)
# ---------------------------------------------------------------------------


def _dispatch_op(db: Database, op_type: str, op: dict) -> dict:
    """Execute a single mutation operation; return a result dict.

    Raises on failure so the caller can record it without stopping the batch.
    """
    if op_type == "add":
        bm = db.add(
            op["url"],
            title=op.get("title"),
            description=op.get("description"),
            tags=op.get("tags"),
            starred=op.get("starred", False),
        )
        return {"unique_id": bm.unique_id, "id": bm.id}

    if op_type == "update":
        bm_id = op["id"]
        fields = {
            k: v
            for k, v in op.items()
            if k not in ("op", "id")
        }
        bm = db.update(bm_id, **fields)
        if bm is None:
            raise ValueError(f"bookmark id={bm_id} not found for update")
        return {"id": bm.id}

    if op_type == "delete":
        db.delete(op["id"], hard=op.get("hard", False))
        return {"id": op["id"]}

    if op_type == "tag":
        for bm_id in op.get("ids", []):
            db.tag(
                bm_id,
                add=op.get("add"),
                remove=op.get("remove"),
            )
        return {"ids": op.get("ids", [])}

    if op_type in ("add_marginalia", "annotate"):
        note = db.add_marginalia(op["bookmark_unique_id"], op["text"])
        return {"id": note.id, "uri": note.uri}

    if op_type == "update_marginalia":
        note = db.update_marginalia(op["id"], op["text"])
        if note is None:
            raise ValueError(
                f"marginalia id={op['id']!r} not found (or archived)"
            )
        return {"id": note.id, "uri": note.uri}

    if op_type == "delete_marginalia":
        if not db.delete_marginalia(op["id"], hard=op.get("hard", False)):
            raise ValueError(f"marginalia id={op['id']!r} not found")
        return {"id": op["id"]}

    if op_type == "restore_marginalia":
        if not db.restore_marginalia(op["id"]):
            raise ValueError(
                f"marginalia id={op['id']!r} not found or already active"
            )
        return {"id": op["id"]}

    if op_type == "restore":
        for bm_id in op.get("ids", []):
            db.restore(bm_id)
        return {"ids": op.get("ids", [])}

    raise ValueError(f"Unknown op type: {op_type!r}")


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------


def create_server(db_path: Optional[str] = None):
    """Build and return a FastMCP server with all six archive-contract tools.

    Resolves *db_path* from the process-wide config when not provided.
    """
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "fastmcp is required for the MCP server. "
            "Install with: pip install 'bookmark-memex[mcp]'"
        ) from exc

    import asyncio

    if db_path is None:
        db_path = get_config().database

    db_path = str(db_path)
    tools = _create_tools(db_path)

    mcp = FastMCP("bookmark-memex")

    # ------------------------------------------------------------------
    # Read-only tools
    # ------------------------------------------------------------------

    @mcp.tool(annotations={"readOnlyHint": True})
    async def get_schema() -> str:
        """Return DDL and row counts for every table in the bookmark database."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, tools["get_schema"])

    @mcp.tool(annotations={"readOnlyHint": True})
    async def execute_sql(
        sql: str,
        params: Optional[list] = None,
    ) -> str:
        """Execute a read-only SQL query (SELECT/WITH/EXPLAIN) and return JSON rows."""
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: tools["execute_sql"](sql, params)
        )
        # Serialise to JSON string for the MCP wire format
        return json.dumps(result, default=str)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def get_record(kind: str, id: str) -> str:
        """Return a single bookmark or marginalia record as JSON.

        kind: 'bookmark' or 'marginalia' (legacy alias: 'annotation')
        id:   unique_id (bookmark) or note UUID
        """
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: tools["get_record"](kind, id)
        )
        return json.dumps(result, default=str)

    # ------------------------------------------------------------------
    # Write tools
    # ------------------------------------------------------------------

    @mcp.tool()
    async def mutate(operations: list) -> str:
        """Execute a batch of write operations.

        Each item in *operations* must have an "op" key.  Supported ops:
        add, update, delete, tag, annotate, restore.

        Returns a JSON summary: {"total": N, "succeeded": N, "results": [...]}.
        """
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: tools["mutate"](operations)
        )
        return json.dumps(result, default=str)

    @mcp.tool()
    async def import_bookmarks(
        file_path: str,
        format: Optional[str] = None,
    ) -> str:
        """Import bookmarks from a file.

        Supports: html (Netscape), json, csv, markdown, text.
        Auto-detects format from the file extension when format is None.

        Returns a JSON summary: {"imported": N}.
        """
        from bookmark_memex.importers import import_file
        from bookmark_memex.db import Database as _Database

        loop = asyncio.get_running_loop()

        def _run() -> dict:
            db = _Database(db_path)
            n = import_file(db, Path(file_path), format=format)
            return {"imported": n}

        result = await loop.run_in_executor(None, _run)
        return json.dumps(result)

    @mcp.tool()
    async def export_bookmarks(
        file_path: str,
        format: str = "json",
        bookmark_ids: Optional[list[int]] = None,
    ) -> str:
        """Export bookmarks to a file.

        Supported formats: json, csv, text, markdown, m3u, arkiv.
        bookmark_ids: optional list of IDs to restrict the export.

        Returns {"exported_to": file_path}.
        """
        from bookmark_memex.exporters import export_file
        from bookmark_memex.db import Database as _Database

        loop = asyncio.get_running_loop()

        def _run() -> dict:
            db = _Database(db_path)
            export_file(db, Path(file_path), format=format, bookmark_ids=bookmark_ids)
            return {"exported_to": file_path}

        result = await loop.run_in_executor(None, _run)
        return json.dumps(result)

    return mcp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover
    """Start the MCP server (stdio transport)."""
    create_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
