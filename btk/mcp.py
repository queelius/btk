"""
MCP (Model Context Protocol) server for btk.

Exposes bookmark database tools over MCP using FastMCP and aiosqlite.
"""

import json
from typing import Optional

import aiosqlite
from fastmcp import FastMCP

_ALLOWED_KEYWORDS = frozenset({"SELECT", "WITH", "EXPLAIN", "PRAGMA"})


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

    return server
