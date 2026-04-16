"""Tests for bookmark_memex.cli module.

Parser tests exercise build_parser() without running any commands.
Command tests verify cmd_import and cmd_sql against a real (temp) database.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bookmark_memex.cli import build_parser


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParser:
    def test_import_file(self):
        args = build_parser().parse_args(["import", "bookmarks.html"])
        assert args.command == "import"
        assert args.file == "bookmarks.html"

    def test_import_format_default_none(self):
        args = build_parser().parse_args(["import", "bookmarks.html"])
        assert args.format is None

    def test_import_format_explicit(self):
        args = build_parser().parse_args(["import", "bookmarks.html", "--format", "html"])
        assert args.format == "html"

    def test_export_json(self):
        args = build_parser().parse_args(["export", "out.json", "--format", "json"])
        assert args.command == "export"
        assert args.path == "out.json"
        assert args.format == "json"

    def test_export_default_format_none(self):
        args = build_parser().parse_args(["export", "out.json"])
        assert args.format is None

    def test_export_single_flag(self):
        args = build_parser().parse_args(["export", "out.html", "--format", "html-app", "--single"])
        assert args.single is True

    def test_export_single_flag_default_false(self):
        args = build_parser().parse_args(["export", "out.html"])
        assert args.single is False

    def test_db_info(self):
        args = build_parser().parse_args(["db", "info"])
        assert args.command == "db"
        assert args.db_command == "info"

    def test_db_schema(self):
        args = build_parser().parse_args(["db", "schema"])
        assert args.db_command == "schema"

    def test_db_vacuum(self):
        args = build_parser().parse_args(["db", "vacuum"])
        assert args.db_command == "vacuum"

    def test_sql(self):
        args = build_parser().parse_args(["sql", "SELECT 1"])
        assert args.command == "sql"
        assert args.query == "SELECT 1"

    def test_sql_output_default_table(self):
        args = build_parser().parse_args(["sql", "SELECT 1"])
        assert args.output == "table"

    def test_sql_output_json(self):
        args = build_parser().parse_args(["sql", "SELECT 1", "-o", "json"])
        assert args.output == "json"

    def test_sql_output_csv(self):
        args = build_parser().parse_args(["sql", "SELECT 1", "-o", "csv"])
        assert args.output == "csv"

    def test_serve(self):
        args = build_parser().parse_args(["serve", "--port", "9090"])
        assert args.command == "serve"
        assert args.port == 9090

    def test_serve_default_port(self):
        args = build_parser().parse_args(["serve"])
        assert args.port == 8080

    def test_serve_default_host(self):
        args = build_parser().parse_args(["serve"])
        assert args.host == "127.0.0.1"

    def test_serve_host_option(self):
        args = build_parser().parse_args(["serve", "--host", "0.0.0.0"])
        assert args.host == "0.0.0.0"

    def test_mcp(self):
        args = build_parser().parse_args(["mcp"])
        assert args.command == "mcp"

    def test_mcp_default_transport_stdio(self):
        args = build_parser().parse_args(["mcp"])
        assert args.transport == "stdio"

    def test_mcp_transport_sse(self):
        args = build_parser().parse_args(["mcp", "--transport", "sse"])
        assert args.transport == "sse"

    def test_version_flag(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--version"])

    def test_db_flag(self):
        args = build_parser().parse_args(["--db", "/tmp/test.db", "db", "info"])
        assert args.db == "/tmp/test.db"

    def test_db_flag_default_none(self):
        args = build_parser().parse_args(["db", "info"])
        assert args.db is None

    def test_fetch_all(self):
        args = build_parser().parse_args(["fetch", "--all"])
        assert args.command == "fetch"
        assert getattr(args, "all", None) is True

    def test_detect_all_flag(self):
        args = build_parser().parse_args(["detect", "--all"])
        assert getattr(args, "all", None) is True

    def test_detect_fetch_flag(self):
        args = build_parser().parse_args(["detect", "--fetch"])
        assert getattr(args, "fetch", None) is True

    def test_check_all_flag(self):
        args = build_parser().parse_args(["check", "--all"])
        assert getattr(args, "all", None) is True

    def test_import_browser_defaults(self):
        args = build_parser().parse_args(["import-browser"])
        assert args.command == "import-browser"
        assert args.browser is None
        assert args.profile is None

    def test_import_browser_chrome(self):
        args = build_parser().parse_args(["import-browser", "--browser", "chrome"])
        assert args.browser == "chrome"

    def test_no_command_returns_none(self):
        args = build_parser().parse_args([])
        assert args.command is None


# ---------------------------------------------------------------------------
# Command tests (cmd_import, cmd_sql, cmd_db)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_data(tmp_db_path):
    """Populate a temp db with two bookmarks and return its path."""
    from bookmark_memex.db import Database

    db = Database(tmp_db_path)
    db.add("https://example.com", title="Example", tags=["test"])
    db.add("https://python.org", title="Python", tags=["programming"])
    return tmp_db_path


def test_cmd_import_html(tmp_db_path, tmp_path):
    """cmd_import reads an HTML file and prints the imported count."""
    html = """\
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><A HREF="https://example.com/" ADD_DATE="1677247196">Example</A>
    <DT><A HREF="https://python.org/" ADD_DATE="1677247196" TAGS="python,dev">Python</A>
</DL><p>
"""
    html_file = tmp_path / "bookmarks.html"
    html_file.write_text(html)

    from bookmark_memex.cli import cmd_import

    args = SimpleNamespace(db=tmp_db_path, file=str(html_file), format=None)
    buf = StringIO()
    with patch("sys.stdout", buf):
        cmd_import(args)

    output = buf.getvalue()
    assert "2" in output


def test_cmd_import_prints_count(tmp_db_path, tmp_path):
    """cmd_import prints a count that matches bookmarks in the file."""
    html = """\
<DL><p>
    <DT><A HREF="https://a.com/">A</A>
    <DT><A HREF="https://b.com/">B</A>
    <DT><A HREF="https://c.com/">C</A>
</DL><p>
"""
    f = tmp_path / "b.html"
    f.write_text(html)

    from bookmark_memex.cli import cmd_import

    args = SimpleNamespace(db=tmp_db_path, file=str(f), format=None)
    buf = StringIO()
    with patch("sys.stdout", buf):
        cmd_import(args)

    output = buf.getvalue()
    assert "3" in output


def test_cmd_sql_select(db_with_data):
    """cmd_sql on SELECT COUNT(*) prints a row count."""
    from bookmark_memex.cli import cmd_sql

    args = SimpleNamespace(db=db_with_data, query="SELECT COUNT(*) FROM bookmarks", output="table")
    buf = StringIO()
    with patch("sys.stdout", buf):
        cmd_sql(args)

    output = buf.getvalue()
    assert "2" in output


def test_cmd_sql_json_output(db_with_data):
    """cmd_sql with -o json emits valid JSON rows."""
    from bookmark_memex.cli import cmd_sql

    args = SimpleNamespace(db=db_with_data, query="SELECT url FROM bookmarks ORDER BY url", output="json")
    buf = StringIO()
    with patch("sys.stdout", buf):
        cmd_sql(args)

    output = buf.getvalue()
    rows = [json.loads(line) for line in output.strip().splitlines() if line.strip()]
    assert len(rows) == 2
    assert any("example.com" in r.get("url", "") for r in rows)


def test_cmd_sql_csv_output(db_with_data):
    """cmd_sql with -o csv emits CSV with header."""
    import csv as csv_mod
    from bookmark_memex.cli import cmd_sql

    args = SimpleNamespace(db=db_with_data, query="SELECT url, title FROM bookmarks ORDER BY url", output="csv")
    buf = StringIO()
    with patch("sys.stdout", buf):
        cmd_sql(args)

    output = buf.getvalue()
    reader = csv_mod.reader(output.strip().splitlines())
    rows = list(reader)
    # first row is the header
    assert rows[0] == ["url", "title"]
    assert len(rows) == 3  # header + 2 data rows


def test_cmd_db_info(db_with_data, capsys):
    """cmd_db info prints table names and row counts."""
    from bookmark_memex.cli import cmd_db

    args = SimpleNamespace(db=db_with_data, db_command="info")
    cmd_db(args)
    captured = capsys.readouterr()
    assert "bookmarks" in captured.out


def test_cmd_db_schema(db_with_data, capsys):
    """cmd_db schema prints CREATE TABLE statements."""
    from bookmark_memex.cli import cmd_db

    args = SimpleNamespace(db=db_with_data, db_command="schema")
    cmd_db(args)
    captured = capsys.readouterr()
    assert "CREATE TABLE" in captured.out


def test_cmd_db_vacuum(db_with_data):
    """cmd_db vacuum runs without error."""
    from bookmark_memex.cli import cmd_db

    args = SimpleNamespace(db=db_with_data, db_command="vacuum")
    cmd_db(args)  # should not raise


def test_main_no_command_exits_zero(monkeypatch):
    """main() with no args prints help and exits 0."""
    from bookmark_memex import cli as cli_mod

    monkeypatch.setattr(sys, "argv", ["bookmark-memex"])
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main()
    assert exc_info.value.code == 0


def test_main_unknown_command_exits_nonzero(monkeypatch):
    """main() with unimplemented command exits non-zero."""
    from bookmark_memex import cli as cli_mod

    monkeypatch.setattr(sys, "argv", ["bookmark-memex", "fetch", "--all"])
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main()
    # fetch is not yet implemented, should exit 1
    assert exc_info.value.code != 0


def test_main_dispatches_db_info(db_with_data, monkeypatch, capsys):
    """main() with 'db info' runs and prints table info."""
    from bookmark_memex import cli as cli_mod

    monkeypatch.setattr(sys, "argv", ["bookmark-memex", "--db", db_with_data, "db", "info"])
    cli_mod.main()
    captured = capsys.readouterr()
    assert "bookmarks" in captured.out
