"""
Tests for date-based bookmark navigation features.

Tests cover:
- Shell /by-date virtual directory navigation
- CLI --by-date grouping option
- REST API /bookmarks/by-date endpoint
"""
import pytest
import tempfile
import os
import json
from datetime import datetime, timezone, timedelta
from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from btk.db import Database
from btk.models import Bookmark, Tag
from btk.shell import BookmarkShell


class TestShellByDateNavigation:
    """Test shell /by-date virtual directory navigation."""

    @pytest.fixture
    def shell_with_dated_bookmarks(self):
        """Create a shell with bookmarks on different dates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            shell = BookmarkShell(db_path)

            # Add bookmarks with different dates
            dates = [
                datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 20, 14, 30, 0, tzinfo=timezone.utc),
                datetime(2024, 2, 5, 9, 0, 0, tzinfo=timezone.utc),
                datetime(2024, 3, 10, 16, 45, 0, tzinfo=timezone.utc),
                datetime(2023, 12, 25, 12, 0, 0, tzinfo=timezone.utc),
            ]

            for i, date in enumerate(dates):
                b = shell.db.add(
                    url=f"https://example{i}.com",
                    title=f"Bookmark {i}",
                    tags=[f"tag{i}"]
                )
                # Update the added date directly
                from btk.models import Bookmark as BM
                with shell.db.session() as session:
                    bookmark = session.get(BM, b.id)
                    bookmark.added = date
                    if i % 2 == 0:  # Some have last_visited
                        bookmark.last_visited = date + timedelta(days=1)
                    session.commit()

            yield shell

    def test_by_date_root_context(self, shell_with_dated_bookmarks):
        """Test /by-date shows field options."""
        shell = shell_with_dated_bookmarks
        ctx = shell._get_context_for_path("/by-date")
        assert ctx['type'] == 'by_date_root'

    def test_by_date_added_shows_years(self, shell_with_dated_bookmarks):
        """Test /by-date/added shows years."""
        shell = shell_with_dated_bookmarks
        ctx = shell._get_context_for_path("/by-date/added")
        assert ctx['type'] == 'by_date_years'
        assert ctx['field'] == 'added'
        assert 2024 in ctx['years']
        assert 2023 in ctx['years']

    def test_by_date_visited_shows_years(self, shell_with_dated_bookmarks):
        """Test /by-date/visited shows years."""
        shell = shell_with_dated_bookmarks
        ctx = shell._get_context_for_path("/by-date/visited")
        assert ctx['type'] == 'by_date_years'
        assert ctx['field'] == 'visited'

    def test_by_date_year_shows_months(self, shell_with_dated_bookmarks):
        """Test /by-date/added/2024 shows months."""
        shell = shell_with_dated_bookmarks
        ctx = shell._get_context_for_path("/by-date/added/2024")
        assert ctx['type'] == 'by_date_months'
        assert ctx['year'] == 2024
        assert 1 in ctx['months']  # January
        assert 2 in ctx['months']  # February
        assert 3 in ctx['months']  # March

    def test_by_date_month_shows_days(self, shell_with_dated_bookmarks):
        """Test /by-date/added/2024/01 shows days."""
        shell = shell_with_dated_bookmarks
        ctx = shell._get_context_for_path("/by-date/added/2024/01")
        assert ctx['type'] == 'by_date_days'
        assert ctx['year'] == 2024
        assert ctx['month'] == 1
        assert 15 in ctx['days']
        assert 20 in ctx['days']

    def test_by_date_day_shows_bookmarks(self, shell_with_dated_bookmarks):
        """Test /by-date/added/2024/01/15 shows bookmarks."""
        shell = shell_with_dated_bookmarks
        ctx = shell._get_context_for_path("/by-date/added/2024/01/15")
        assert ctx['type'] == 'by_date_bookmarks'
        assert ctx['year'] == 2024
        assert ctx['month'] == 1
        assert ctx['day'] == 15
        assert len(ctx['bookmarks']) == 1

    def test_by_date_invalid_field_returns_unknown(self, shell_with_dated_bookmarks):
        """Test /by-date/invalid returns unknown."""
        shell = shell_with_dated_bookmarks
        ctx = shell._get_context_for_path("/by-date/invalid")
        assert ctx['type'] == 'unknown'

    def test_cd_to_by_date(self, shell_with_dated_bookmarks):
        """Test cd navigation to by-date paths."""
        shell = shell_with_dated_bookmarks

        shell.do_cd("by-date")
        assert shell.cwd == "/by-date"

        shell.do_cd("added")
        assert shell.cwd == "/by-date/added"

        shell.do_cd("2024")
        assert shell.cwd == "/by-date/added/2024"

    def test_ls_by_date_root(self, shell_with_dated_bookmarks):
        """Test ls at /by-date shows field options."""
        shell = shell_with_dated_bookmarks
        shell.cwd = "/by-date"

        output = StringIO()
        with redirect_stdout(output):
            shell.do_ls("")

        result = output.getvalue()
        assert "added" in result.lower()
        assert "visited" in result.lower()

    def test_ls_by_date_years(self, shell_with_dated_bookmarks):
        """Test ls at /by-date/added shows years."""
        shell = shell_with_dated_bookmarks
        shell.cwd = "/by-date/added"

        output = StringIO()
        with redirect_stdout(output):
            shell.do_ls("")

        result = output.getvalue()
        assert "2024" in result
        assert "2023" in result

    def test_ls_by_date_months(self, shell_with_dated_bookmarks):
        """Test ls at /by-date/added/2024 shows months."""
        shell = shell_with_dated_bookmarks
        shell.cwd = "/by-date/added/2024"

        output = StringIO()
        with redirect_stdout(output):
            shell.do_ls("")

        result = output.getvalue()
        assert "Jan" in result or "01" in result

    def test_by_date_in_root_listing(self, shell_with_dated_bookmarks):
        """Test by-date appears in root directory listing."""
        shell = shell_with_dated_bookmarks
        shell.cwd = "/"

        output = StringIO()
        with redirect_stdout(output):
            shell.do_ls("")

        result = output.getvalue()
        assert "by-date" in result.lower()


class TestCLIByDateOption:
    """Test CLI --by-date grouping option."""

    @pytest.fixture
    def db_with_dated_bookmarks(self):
        """Create a database with bookmarks on different dates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            dates = [
                datetime(2024, 1, 15, tzinfo=timezone.utc),
                datetime(2024, 1, 20, tzinfo=timezone.utc),
                datetime(2024, 2, 5, tzinfo=timezone.utc),
                datetime(2024, 3, 10, tzinfo=timezone.utc),
            ]

            for i, date in enumerate(dates):
                b = db.add(
                    url=f"https://example{i}.com",
                    title=f"Bookmark {i}",
                )
                from btk.models import Bookmark as BM
                with db.session() as session:
                    bookmark = session.get(BM, b.id)
                    bookmark.added = date
                    session.commit()

            yield db, db_path

    def test_output_bookmarks_by_date_year(self, db_with_dated_bookmarks):
        """Test grouping by year."""
        from btk.cli import output_bookmarks_by_date
        db, _ = db_with_dated_bookmarks
        bookmarks = db.list()

        output = StringIO()
        with redirect_stdout(output):
            output_bookmarks_by_date(bookmarks, 'added', 'year', 'table')

        result = output.getvalue()
        assert "2024" in result

    def test_output_bookmarks_by_date_month(self, db_with_dated_bookmarks):
        """Test grouping by month."""
        from btk.cli import output_bookmarks_by_date
        db, _ = db_with_dated_bookmarks
        bookmarks = db.list()

        output = StringIO()
        with redirect_stdout(output):
            output_bookmarks_by_date(bookmarks, 'added', 'month', 'table')

        result = output.getvalue()
        assert "Jan" in result or "Feb" in result or "Mar" in result

    def test_output_bookmarks_by_date_day(self, db_with_dated_bookmarks):
        """Test grouping by day."""
        from btk.cli import output_bookmarks_by_date
        db, _ = db_with_dated_bookmarks
        bookmarks = db.list()

        output = StringIO()
        with redirect_stdout(output):
            output_bookmarks_by_date(bookmarks, 'added', 'day', 'table')

        result = output.getvalue()
        # Should show specific dates
        assert "2024" in result

    def test_output_bookmarks_by_date_json(self, db_with_dated_bookmarks):
        """Test JSON output format."""
        from btk.cli import output_bookmarks_by_date
        db, _ = db_with_dated_bookmarks
        bookmarks = db.list()

        output = StringIO()
        with redirect_stdout(output):
            output_bookmarks_by_date(bookmarks, 'added', 'month', 'json')

        result = output.getvalue()
        data = json.loads(result)
        assert data['field'] == 'added'
        assert data['granularity'] == 'month'
        assert 'groups' in data

    def test_cmd_list_with_by_date(self, db_with_dated_bookmarks):
        """Test cmd_list with --by-date argument."""
        from btk.cli import cmd_list
        from argparse import Namespace

        _, db_path = db_with_dated_bookmarks

        args = Namespace(
            db=db_path,
            limit=None,
            offset=0,
            sort='added',
            include_archived=False,
            by_date='added',
            date_granularity='month',
            output='table'
        )

        output = StringIO()
        with redirect_stdout(output):
            cmd_list(args)

        result = output.getvalue()
        assert "Date Added" in result or "month" in result.lower()


class TestServeByDateEndpoint:
    """Test REST API /bookmarks/by-date endpoint."""

    @pytest.fixture
    def handler_with_bookmarks(self):
        """Create a mock handler with dated bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            dates = [
                datetime(2024, 1, 15, tzinfo=timezone.utc),
                datetime(2024, 1, 20, tzinfo=timezone.utc),
                datetime(2024, 2, 5, tzinfo=timezone.utc),
            ]

            for i, date in enumerate(dates):
                b = db.add(
                    url=f"https://example{i}.com",
                    title=f"Bookmark {i}",
                )
                from btk.models import Bookmark as BM
                with db.session() as session:
                    bookmark = session.get(BM, b.id)
                    bookmark.added = date
                    session.commit()

            yield db

    def test_handle_bookmarks_by_date_default(self, handler_with_bookmarks):
        """Test by-date endpoint with default parameters."""
        from btk.serve import BTKAPIHandler
        from pathlib import Path

        db = handler_with_bookmarks

        # Create a mock handler
        class MockHandler(BTKAPIHandler):
            def __init__(self, db):
                self.db = db
                self.frontend_dir = Path(".")
                self.response_data = None
                self.response_status = None

            def send_json(self, data, status=200):
                self.response_data = data
                self.response_status = status

        handler = MockHandler(db)
        handler.handle_bookmarks_by_date({'field': ['added'], 'granularity': ['month']})

        assert handler.response_status == 200
        assert handler.response_data['field'] == 'added'
        assert handler.response_data['granularity'] == 'month'
        assert 'groups' in handler.response_data
        assert handler.response_data['total'] == 3

    def test_handle_bookmarks_by_date_year_granularity(self, handler_with_bookmarks):
        """Test by-date endpoint with year granularity."""
        from btk.serve import BTKAPIHandler
        from pathlib import Path

        db = handler_with_bookmarks

        class MockHandler(BTKAPIHandler):
            def __init__(self, db):
                self.db = db
                self.frontend_dir = Path(".")
                self.response_data = None
                self.response_status = None

            def send_json(self, data, status=200):
                self.response_data = data
                self.response_status = status

        handler = MockHandler(db)
        handler.handle_bookmarks_by_date({'field': ['added'], 'granularity': ['year']})

        assert handler.response_data['granularity'] == 'year'
        # All bookmarks are in 2024
        assert len(handler.response_data['groups']) == 1
        assert handler.response_data['groups'][0]['key'] == '2024'

    def test_handle_bookmarks_by_date_with_year_filter(self, handler_with_bookmarks):
        """Test by-date endpoint with year filter."""
        from btk.serve import BTKAPIHandler
        from pathlib import Path

        db = handler_with_bookmarks

        class MockHandler(BTKAPIHandler):
            def __init__(self, db):
                self.db = db
                self.frontend_dir = Path(".")
                self.response_data = None
                self.response_status = None

            def send_json(self, data, status=200):
                self.response_data = data
                self.response_status = status

        handler = MockHandler(db)
        handler.handle_bookmarks_by_date({
            'field': ['added'],
            'granularity': ['month'],
            'year': ['2024']
        })

        assert handler.response_data['filters']['year'] == 2024
        assert handler.response_data['total'] == 3

    def test_handle_bookmarks_by_date_invalid_field(self, handler_with_bookmarks):
        """Test by-date endpoint with invalid field."""
        from btk.serve import BTKAPIHandler
        from pathlib import Path

        db = handler_with_bookmarks

        class MockHandler(BTKAPIHandler):
            def __init__(self, db):
                self.db = db
                self.frontend_dir = Path(".")
                self.response_data = None
                self.response_status = None

            def send_json(self, data, status=200):
                self.response_data = data
                self.response_status = status

            def send_error_json(self, message, status=400):
                self.response_data = {'error': message}
                self.response_status = status

        handler = MockHandler(db)
        handler.handle_bookmarks_by_date({'field': ['invalid'], 'granularity': ['month']})

        assert handler.response_status == 400
        assert 'error' in handler.response_data


class TestDateGroupingHelpers:
    """Test helper functions for date grouping."""

    @pytest.fixture
    def shell_with_bookmarks(self):
        """Create shell with test bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            shell = BookmarkShell(db_path)

            dates = [
                datetime(2024, 1, 15, tzinfo=timezone.utc),
                datetime(2024, 1, 20, tzinfo=timezone.utc),
                datetime(2024, 2, 5, tzinfo=timezone.utc),
            ]

            for i, date in enumerate(dates):
                b = shell.db.add(
                    url=f"https://example{i}.com",
                    title=f"Bookmark {i}",
                )
                from btk.models import Bookmark as BM
                with shell.db.session() as session:
                    bookmark = session.get(BM, b.id)
                    bookmark.added = date
                    session.commit()

            yield shell

    def test_get_date_groups_by_year(self, shell_with_bookmarks):
        """Test _get_date_groups with year granularity."""
        shell = shell_with_bookmarks
        bookmarks = shell.db.list()

        groups = shell._get_date_groups(bookmarks, 'added', 'year')

        assert 2024 in groups
        assert groups[2024] == 3

    def test_get_date_groups_by_month(self, shell_with_bookmarks):
        """Test _get_date_groups with month granularity."""
        shell = shell_with_bookmarks
        bookmarks = shell.db.list()

        groups = shell._get_date_groups(bookmarks, 'added', 'month', year=2024)

        assert 1 in groups  # January
        assert 2 in groups  # February
        assert groups[1] == 2  # 2 bookmarks in January
        assert groups[2] == 1  # 1 bookmark in February

    def test_get_date_groups_by_day(self, shell_with_bookmarks):
        """Test _get_date_groups with day granularity."""
        shell = shell_with_bookmarks
        bookmarks = shell.db.list()

        groups = shell._get_date_groups(bookmarks, 'added', 'day', year=2024, month=1)

        assert 15 in groups
        assert 20 in groups
        assert groups[15] == 1
        assert groups[20] == 1

    def test_get_bookmarks_by_date(self, shell_with_bookmarks):
        """Test _get_bookmarks_by_date returns correct bookmarks."""
        shell = shell_with_bookmarks
        bookmarks = shell.db.list()

        result = shell._get_bookmarks_by_date(bookmarks, 'added', 2024, 1, 15)

        assert len(result) == 1
        assert result[0].title == "Bookmark 0"

    def test_get_date_groups_with_no_matching_bookmarks(self, shell_with_bookmarks):
        """Test _get_date_groups returns empty when no matches."""
        shell = shell_with_bookmarks
        bookmarks = shell.db.list()

        groups = shell._get_date_groups(bookmarks, 'added', 'month', year=2020)

        assert len(groups) == 0

    def test_get_date_groups_skips_none_dates(self, shell_with_bookmarks):
        """Test _get_date_groups handles bookmarks without dates."""
        shell = shell_with_bookmarks

        # Add bookmark without last_visited
        shell.db.add(url="https://novisit.com", title="No Visit")

        bookmarks = shell.db.list()
        groups = shell._get_date_groups(bookmarks, 'last_visited', 'year')

        # Should not fail, just skip bookmarks without last_visited
        assert isinstance(groups, dict)
