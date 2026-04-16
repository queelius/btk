"""Thin admin CLI for bookmark-memex.

Interactive query goes through the MCP server or the web UI.
This CLI handles imports, exports, database maintenance, raw SQL,
and launching the MCP/web servers.

Entry point: bookmark-memex (see pyproject.toml)
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

from bookmark_memex import __version__


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> ArgumentParser:
    """Return the fully configured argument parser."""
    parser = ArgumentParser(
        prog="bookmark-memex",
        description="Personal bookmark archive — admin CLI",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        default=None,
        help="Path to the SQLite database (overrides config)",
    )
    parser.set_defaults(command=None)

    sub = parser.add_subparsers(dest="command")

    # ── import ───────────────────────────────────────────────────────────────
    p_import = sub.add_parser("import", help="Import bookmarks from a file")
    p_import.add_argument("file", metavar="FILE", help="Path to the import file")
    p_import.add_argument(
        "--format",
        choices=["html", "json", "csv", "markdown", "text"],
        default=None,
        help="File format (auto-detected from extension when omitted)",
    )

    # ── import-browser ───────────────────────────────────────────────────────
    p_ib = sub.add_parser("import-browser", help="Import from browser bookmark store")
    p_ib.add_argument(
        "--browser",
        choices=["chrome", "firefox"],
        default=None,
        help="Browser to import from",
    )
    p_ib.add_argument(
        "--profile",
        metavar="NAME",
        default=None,
        help="Browser profile name",
    )
    p_ib.add_argument(
        "--list",
        dest="list_profiles",
        action="store_true",
        default=False,
        help="List detected browser profiles and exit",
    )

    # ── export ───────────────────────────────────────────────────────────────
    p_export = sub.add_parser("export", help="Export bookmarks to a file")
    p_export.add_argument("path", metavar="PATH", help="Destination file path")
    p_export.add_argument(
        "--format",
        choices=["json", "csv", "markdown", "text", "m3u", "arkiv", "html-app"],
        default=None,
        help="Export format (inferred from extension when omitted)",
    )
    p_export.add_argument(
        "--single",
        action="store_true",
        default=False,
        help="Export to a single self-contained file (html-app only)",
    )

    # ── fetch ────────────────────────────────────────────────────────────────
    p_fetch = sub.add_parser("fetch", help="Fetch/cache web content for bookmarks")
    fetch_group = p_fetch.add_mutually_exclusive_group()
    fetch_group.add_argument("--all", action="store_true", default=False)
    fetch_group.add_argument("--stale", action="store_true", default=False)
    p_fetch.add_argument("ids", nargs="*", type=int, metavar="ID")

    # ── detect ───────────────────────────────────────────────────────────────
    p_detect = sub.add_parser("detect", help="Run media detectors on bookmarks")
    p_detect.add_argument("--all", action="store_true", default=False)
    p_detect.add_argument("--fetch", action="store_true", default=False)
    p_detect.add_argument("ids", nargs="*", type=int, metavar="ID")

    # ── check ────────────────────────────────────────────────────────────────
    p_check = sub.add_parser("check", help="Check bookmark health (reachability)")
    check_group = p_check.add_mutually_exclusive_group()
    check_group.add_argument("--all", action="store_true", default=False)
    check_group.add_argument("--stale", action="store_true", default=False)
    p_check.add_argument("ids", nargs="*", type=int, metavar="ID")

    # ── db ───────────────────────────────────────────────────────────────────
    p_db = sub.add_parser("db", help="Database maintenance commands")
    p_db.add_argument(
        "db_command",
        choices=["info", "schema", "vacuum", "migrate"],
        metavar="COMMAND",
        help="One of: info, schema, vacuum, migrate",
    )

    # ── serve ────────────────────────────────────────────────────────────────
    p_serve = sub.add_parser("serve", help="Start the REST API + web UI server")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.add_argument("--host", default="127.0.0.1")

    # ── mcp ──────────────────────────────────────────────────────────────────
    p_mcp = sub.add_parser("mcp", help="Start the MCP server")
    p_mcp.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )

    # ── sql ──────────────────────────────────────────────────────────────────
    p_sql = sub.add_parser("sql", help="Execute a raw SQL query")
    p_sql.add_argument("query", metavar="QUERY", help="SQL query string")
    p_sql.add_argument(
        "-o",
        dest="output",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )

    return parser


# ---------------------------------------------------------------------------
# Database resolution
# ---------------------------------------------------------------------------


def _resolve_db(args: Namespace) -> str:
    """Return the database path: CLI flag > config default."""
    if args.db:
        return args.db
    from bookmark_memex.config import get_config

    return get_config().database


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_import(args: Namespace) -> None:
    """Import bookmarks from a file and print the imported count."""
    from bookmark_memex.db import Database
    from bookmark_memex.importers import import_file

    db_path = _resolve_db(args)
    db = Database(db_path)
    count = import_file(db, Path(args.file), format=args.format)
    print(f"Imported {count} bookmark(s) from {args.file}")


def cmd_import_browser(args: Namespace) -> None:
    """Import bookmarks from a browser profile."""
    from bookmark_memex.importers.browser import import_browser_bookmarks, list_browser_profiles

    if getattr(args, "list_profiles", False):
        profiles = list_browser_profiles(getattr(args, "browser", None))
        if not profiles:
            print("No browser profiles detected.")
        for p in profiles:
            default_marker = " (default)" if p.get("is_default") else ""
            print(f"  {p['browser']} / {p['name']}{default_marker}: {p['path']}")
        return

    db_path = _resolve_db(args)
    from bookmark_memex.db import Database

    db = Database(db_path)
    browser = getattr(args, "browser", None) or "chrome"
    profile = getattr(args, "profile", None)
    count = import_browser_bookmarks(db, browser=browser, profile=profile)
    print(f"Imported {count} bookmark(s) from {browser}")


def cmd_export(args: Namespace) -> None:
    """Export bookmarks to a file."""
    from bookmark_memex.db import Database
    from bookmark_memex.exporters import export_file

    db_path = _resolve_db(args)
    db = Database(db_path)

    fmt = args.format
    if fmt is None:
        # Infer from extension
        ext = Path(args.path).suffix.lower()
        ext_map = {
            ".json": "json",
            ".csv": "csv",
            ".md": "markdown",
            ".txt": "text",
            ".m3u": "m3u",
        }
        fmt = ext_map.get(ext, "json")

    export_file(db, Path(args.path), format=fmt, single=args.single)
    print(f"Exported to {args.path} (format: {fmt})")


def cmd_db(args: Namespace) -> None:
    """Database maintenance: info, schema, vacuum, migrate."""
    db_path = _resolve_db(args)

    conn = sqlite3.connect(db_path)
    try:
        if args.db_command == "info":
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            for (name,) in tables:
                count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                print(f"  {name}: {count} row(s)")

        elif args.db_command == "schema":
            rows = conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
            ).fetchall()
            for (sql,) in rows:
                print(sql)
                print()

        elif args.db_command == "vacuum":
            conn.execute("VACUUM")
            print("VACUUM complete.")

        elif args.db_command == "migrate":
            print("Command not yet implemented")
            sys.exit(1)

    finally:
        conn.close()


def cmd_sql(args: Namespace) -> None:
    """Execute a raw SQL query and print results in the chosen format."""
    db_path = _resolve_db(args)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute(args.query)
        rows = cursor.fetchall()

        if not rows:
            print("(no rows)")
            return

        columns = list(rows[0].keys())

        if args.output == "json":
            for row in rows:
                print(json.dumps(dict(row)))

        elif args.output == "csv":
            writer = csv.writer(sys.stdout)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(list(row))

        else:  # table (tab-separated)
            print("\t".join(columns))
            for row in rows:
                print("\t".join(str(v) if v is not None else "" for v in row))

        if args.output == "table":
            print(f"({len(rows)} row(s))")

    finally:
        conn.close()


def cmd_mcp(args: Namespace) -> None:
    """Start the MCP server."""
    from bookmark_memex.mcp import create_server

    db_path = _resolve_db(args)
    create_server(db_path).run()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handlers = {
        "import": cmd_import,
        "import-browser": cmd_import_browser,
        "export": cmd_export,
        "db": cmd_db,
        "sql": cmd_sql,
        "mcp": cmd_mcp,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Command '{args.command}' not yet implemented")
        sys.exit(1)
