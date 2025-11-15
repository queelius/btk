"""
Tests for Time-Based Recent Navigation feature (v0.7.1)

Time-based recent navigation provides a hierarchical directory structure:
/recent/{period}/{activity}

Periods: today, yesterday, this-week, last-week, this-month, last-month
Activity types: visited, added, starred

Total: 6 periods × 3 activities = 18 subdirectories
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from btk.db import Database
from btk.shell import BookmarkShell, get_time_ranges, filter_by_activity


class TestTimeRangesFunction:
    """Test get_time_ranges() helper function."""

    def test_get_time_ranges_returns_six_periods(self):
        """get_time_ranges should return 6 time periods."""
        ranges = get_time_ranges()
        assert len(ranges) == 6
        expected_periods = {'today', 'yesterday', 'this-week', 'last-week', 'this-month', 'last-month'}
        assert set(ranges.keys()) == expected_periods

    def test_each_time_range_has_start_and_end(self):
        """Each time range should be a tuple of (start, end) datetimes."""
        ranges = get_time_ranges()
        for period, (start, end) in ranges.items():
            assert isinstance(start, datetime), f"Period {period} start is not datetime"
            assert isinstance(end, datetime), f"Period {period} end is not datetime"
            assert start < end, f"Period {period} start >= end"
            assert start.tzinfo is not None, f"Period {period} start has no timezone"
            assert end.tzinfo is not None, f"Period {period} end has no timezone"

    def test_today_range_starts_at_midnight(self):
        """Today range should start at midnight of current day."""
        ranges = get_time_ranges()
        start, end = ranges['today']

        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0
        assert start.microsecond == 0

    def test_yesterday_range_is_24_hours(self):
        """Yesterday range should be exactly 24 hours."""
        ranges = get_time_ranges()
        start, end = ranges['yesterday']

        duration = end - start
        assert duration == timedelta(days=1), f"Yesterday duration is {duration}, not 24 hours"

    def test_this_week_starts_on_monday(self):
        """This week range should start on Monday."""
        ranges = get_time_ranges()
        start, end = ranges['this-week']

        # weekday() returns 0 for Monday, 6 for Sunday
        assert start.weekday() == 0, f"This week starts on {start.strftime('%A')}, not Monday"

    def test_this_month_starts_on_first_day(self):
        """This month range should start on day 1."""
        ranges = get_time_ranges()
        start, end = ranges['this-month']

        assert start.day == 1, f"This month starts on day {start.day}, not day 1"
        assert start.hour == 0 and start.minute == 0 and start.second == 0

    def test_last_month_is_full_month(self):
        """Last month range should be the complete previous month."""
        ranges = get_time_ranges()
        start, end = ranges['last-month']

        # Start should be day 1 of previous month
        assert start.day == 1

        # End should be day 1 of current month (exclusive)
        now = datetime.now(timezone.utc)
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        assert end == current_month_start


class TestFilterByActivityFunction:
    """Test filter_by_activity() helper function."""

    @pytest.fixture
    def test_bookmarks(self):
        """Create test bookmarks with various timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Recent bookmarks (today)
            db.add(
                url="https://example.com/visited-today",
                title="Visited Today",
                last_visited=now - timedelta(hours=2)
            )
            db.add(
                url="https://example.com/added-today",
                title="Added Today",
                added=now - timedelta(hours=3)
            )
            db.add(
                url="https://example.com/starred-today",
                title="Starred Today",
                stars=True,
                added=now - timedelta(hours=1)  # Starred timestamp uses 'added'
            )

            # Old bookmarks (yesterday)
            db.add(
                url="https://example.com/visited-yesterday",
                title="Visited Yesterday",
                last_visited=now - timedelta(days=1, hours=2)
            )
            db.add(
                url="https://example.com/added-yesterday",
                title="Added Yesterday",
                added=now - timedelta(days=1, hours=3)
            )

            yield db, today_start, now

    def test_filter_by_visited_activity(self, test_bookmarks):
        """filter_by_activity should filter by last_visited timestamp."""
        db, start, end = test_bookmarks
        bookmarks = db.list()

        filtered = filter_by_activity(bookmarks, 'visited', start, end)

        assert len(filtered) >= 1, "Should find bookmarks visited today"
        for bookmark in filtered:
            if bookmark.last_visited:
                # SQLite returns naive datetimes, so make them aware for comparison
                visited_time = bookmark.last_visited
                if visited_time.tzinfo is None:
                    visited_time = visited_time.replace(tzinfo=timezone.utc)
                assert start <= visited_time <= end, \
                    f"Bookmark {bookmark.title} visited at {visited_time}, outside range {start} to {end}"

    def test_filter_by_added_activity(self, test_bookmarks):
        """filter_by_activity should filter by added timestamp."""
        db, start, end = test_bookmarks
        bookmarks = db.list()

        filtered = filter_by_activity(bookmarks, 'added', start, end)

        assert len(filtered) >= 1, "Should find bookmarks added today"
        for bookmark in filtered:
            # SQLite returns naive datetimes, so make them aware for comparison
            added_time = bookmark.added
            if added_time.tzinfo is None:
                added_time = added_time.replace(tzinfo=timezone.utc)
            assert start <= added_time <= end, \
                f"Bookmark {bookmark.title} added at {added_time}, outside range {start} to {end}"

    def test_filter_by_starred_activity(self, test_bookmarks):
        """filter_by_activity should filter by starred_at timestamp (uses added as proxy)."""
        db, start, end = test_bookmarks
        bookmarks = db.list()

        filtered = filter_by_activity(bookmarks, 'starred', start, end)

        assert len(filtered) >= 1, "Should find bookmarks starred today"
        for bookmark in filtered:
            assert bookmark.stars is True, f"Bookmark {bookmark.title} should be starred"
            if bookmark.added:
                # SQLite returns naive datetimes, so make them aware for comparison
                added_time = bookmark.added
                if added_time.tzinfo is None:
                    added_time = added_time.replace(tzinfo=timezone.utc)
                assert start <= added_time <= end, \
                    f"Bookmark {bookmark.title} starred at {added_time}, outside range {start} to {end}"

    def test_filter_excludes_bookmarks_outside_range(self, test_bookmarks):
        """Bookmarks outside time range should be excluded."""
        db, start, end = test_bookmarks
        bookmarks = db.list()

        filtered = filter_by_activity(bookmarks, 'visited', start, end)

        # Find bookmarks visited yesterday (should not be included)
        yesterday_bookmarks = [b for b in bookmarks if 'yesterday' in b.title.lower()]
        for bookmark in yesterday_bookmarks:
            assert bookmark not in filtered, \
                f"Bookmark {bookmark.title} from yesterday should not be in today's results"

    def test_filter_handles_none_timestamps(self):
        """filter_by_activity should handle bookmarks with None timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Bookmark never visited (last_visited = None)
            db.add(url="https://example.com/never-visited", title="Never Visited")

            bookmarks = db.list()
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            filtered = filter_by_activity(bookmarks, 'visited', today_start, now)

            # Bookmark with None timestamp should not be included
            assert len(filtered) == 0, "Bookmark with None timestamp should be excluded"

    def test_filter_sorts_by_timestamp_descending(self, test_bookmarks):
        """Filtered results should be sorted by timestamp (most recent first)."""
        db, start, end = test_bookmarks
        bookmarks = db.list()

        filtered = filter_by_activity(bookmarks, 'added', start, end)

        if len(filtered) >= 2:
            # Verify descending order
            for i in range(len(filtered) - 1):
                assert filtered[i].added >= filtered[i + 1].added, \
                    "Results should be sorted by timestamp descending"


class TestRecentDirectoryNavigation:
    """Test navigation of /recent directory structure."""

    @pytest.fixture
    def db(self):
        """Create test database with timestamped bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)

            # Today's activities
            db.add(
                url="https://example.com/today-visited",
                title="Today Visited",
                last_visited=now - timedelta(hours=1),
                visit_count=1
            )
            db.add(
                url="https://example.com/today-added",
                title="Today Added",
                added=now - timedelta(hours=2)
            )
            db.add(
                url="https://example.com/today-starred",
                title="Today Starred",
                stars=True,
            )

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_cd_to_recent_root(self, shell):
        """Should be able to cd /recent."""
        shell.do_cd("/recent")
        assert shell.cwd == "/recent"

    def test_get_context_for_recent_root(self, shell):
        """_get_context should recognize /recent path."""
        shell.cwd = "/recent"
        context = shell._get_context()
        assert context['type'] == 'recent'
        assert 'bookmarks' in context

    def test_ls_recent_root_shows_time_periods(self, shell):
        """ls /recent should show 6 time period subdirectories."""
        shell.cwd = "/recent"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Should show time periods
            assert mock_print.call_count > 0

    def test_cd_to_time_period(self, shell):
        """Should be able to cd /recent/today."""
        shell.do_cd("/recent/today")
        assert shell.cwd == "/recent/today"

    def test_get_context_for_time_period(self, shell):
        """_get_context should recognize /recent/today path."""
        shell.cwd = "/recent/today"
        context = shell._get_context()
        assert context['type'] == 'recent_period'
        assert context['period'] == 'today'

    def test_ls_time_period_shows_activity_types(self, shell):
        """ls /recent/today should show 3 activity subdirectories."""
        shell.cwd = "/recent/today"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Should show visited/, added/, starred/
            assert mock_print.call_count > 0

    def test_cd_to_activity_directory(self, shell):
        """Should be able to cd /recent/today/visited."""
        shell.do_cd("/recent/today/visited")
        assert shell.cwd == "/recent/today/visited"

    def test_get_context_for_activity_directory(self, shell):
        """_get_context should recognize /recent/today/visited path."""
        shell.cwd = "/recent/today/visited"
        context = shell._get_context()
        assert context['type'] == 'recent_activity'
        assert context['period'] == 'today'
        assert context['activity'] == 'visited'
        assert 'bookmarks' in context

    def test_ls_activity_directory_shows_bookmarks(self, shell):
        """ls /recent/today/visited should show bookmarks visited today."""
        shell.cwd = "/recent/today/visited"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Should show bookmarks
            assert mock_print.call_count > 0


class TestAllTimePeriods:
    """Test all 6 time periods work correctly."""

    @pytest.fixture
    def shell(self):
        """Create shell with test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            shell = BookmarkShell(db_path)
            yield shell

    @pytest.mark.parametrize("period", [
        "today",
        "yesterday",
        "this-week",
        "last-week",
        "this-month",
        "last-month"
    ])
    def test_cd_to_each_period(self, shell, period):
        """Should be able to cd into each time period."""
        shell.do_cd(f"/recent/{period}")
        assert shell.cwd == f"/recent/{period}"

    @pytest.mark.parametrize("period", [
        "today",
        "yesterday",
        "this-week",
        "last-week",
        "this-month",
        "last-month"
    ])
    def test_get_context_for_each_period(self, shell, period):
        """_get_context should recognize each time period."""
        shell.cwd = f"/recent/{period}"
        context = shell._get_context()
        assert context['type'] == 'recent_period'
        assert context['period'] == period


class TestAllActivityTypes:
    """Test all 3 activity types work correctly."""

    @pytest.fixture
    def db(self):
        """Create test database with activities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)

            # Create bookmarks for each activity type
            db.add(
                url="https://example.com/visited",
                title="Visited",
                last_visited=now,
                visit_count=1
            )
            db.add(
                url="https://example.com/added",
                title="Added",
                added=now
            )
            db.add(
                url="https://example.com/starred",
                title="Starred",
                stars=True,
            )

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    @pytest.mark.parametrize("activity", ["visited", "added", "starred"])
    def test_cd_to_each_activity(self, shell, activity):
        """Should be able to cd into each activity type."""
        shell.do_cd(f"/recent/today/{activity}")
        assert shell.cwd == f"/recent/today/{activity}"

    @pytest.mark.parametrize("activity", ["visited", "added", "starred"])
    def test_get_context_for_each_activity(self, shell, activity):
        """_get_context should recognize each activity type."""
        shell.cwd = f"/recent/today/{activity}"
        context = shell._get_context()
        assert context['type'] == 'recent_activity'
        assert context['period'] == 'today'
        assert context['activity'] == activity

    @pytest.mark.parametrize("activity", ["visited", "added", "starred"])
    def test_ls_each_activity_type(self, shell, activity):
        """ls should work for each activity type."""
        shell.cwd = f"/recent/today/{activity}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.call_count > 0


class TestCombinationsOfPeriodsAndActivities:
    """Test comprehensive combinations of periods and activities."""

    @pytest.fixture
    def db(self):
        """Create test database with diverse timestamped bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Today
            db.add(url="https://example.com/t1", title="Today 1",
                   last_visited=now, added=now, stars=True)

            # Yesterday
            yesterday = now - timedelta(days=1)
            db.add(url="https://example.com/y1", title="Yesterday 1",
                   last_visited=yesterday, added=yesterday, visit_count=1)

            # This week
            this_week = now - timedelta(days=3)
            db.add(url="https://example.com/tw1", title="This Week 1",
                   last_visited=this_week, added=this_week, visit_count=1)

            # Last week
            last_week = now - timedelta(days=10)
            db.add(url="https://example.com/lw1", title="Last Week 1",
                   last_visited=last_week, added=last_week, visit_count=1)

            # This month
            this_month = now - timedelta(days=15)
            db.add(url="https://example.com/tm1", title="This Month 1",
                   last_visited=this_month, added=this_month, visit_count=1)

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_today_visited_shows_correct_bookmarks(self, shell):
        """"/recent/today/visited should show bookmarks visited today."""
        shell.cwd = "/recent/today/visited"
        context = shell._get_context()
        bookmarks = context['bookmarks']

        # At least the "Today 1" bookmark should be present
        titles = [b.title for b in bookmarks]
        assert "Today 1" in titles

    def test_yesterday_added_shows_correct_bookmarks(self, shell):
        """"/recent/yesterday/added should show bookmarks added yesterday."""
        shell.cwd = "/recent/yesterday/added"
        context = shell._get_context()
        bookmarks = context['bookmarks']

        titles = [b.title for b in bookmarks]
        assert "Yesterday 1" in titles

    def test_periods_are_mutually_exclusive(self, shell):
        """Bookmark from yesterday should not appear in today."""
        shell.cwd = "/recent/today/visited"
        context = shell._get_context()
        today_bookmarks = context['bookmarks']
        today_titles = [b.title for b in today_bookmarks]

        # "Yesterday 1" should NOT be in today's results
        assert "Yesterday 1" not in today_titles

    def test_navigation_through_all_18_subdirectories(self, shell):
        """Test navigation through all 18 period/activity combinations."""
        periods = ["today", "yesterday", "this-week", "last-week", "this-month", "last-month"]
        activities = ["visited", "added", "starred"]

        for period in periods:
            for activity in activities:
                path = f"/recent/{period}/{activity}"
                shell.do_cd(path)
                assert shell.cwd == path, f"Failed to navigate to {path}"


class TestRecentBackwardCompatibility:
    """Test backward compatibility with original /recent behavior."""

    @pytest.fixture
    def db(self):
        """Create test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)

            # Add bookmarks with IDs
            db.add(url="https://example.com/1", title="Bookmark 1",
                   last_visited=now - timedelta(hours=1), visit_count=1)
            db.add(url="https://example.com/2", title="Bookmark 2",
                   last_visited=now - timedelta(hours=2), visit_count=1)

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_recent_with_bookmark_id_still_works(self, shell):
        """"/recent/{id} should still work for bookmark IDs (backward compat)."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/recent/{bookmark_id}"
            context = shell._get_context()
            # Should detect as bookmark, not time period
            assert context['type'] == 'bookmark'
            assert context['bookmark_id'] == bookmark_id

    def test_recent_root_shows_recently_visited(self, shell):
        """"/recent should show recently visited bookmarks by default."""
        shell.cwd = "/recent"
        context = shell._get_context()
        assert context['type'] == 'recent'
        assert 'bookmarks' in context
        # Bookmarks should be sorted by last_visited descending
        bookmarks = context['bookmarks']
        if len(bookmarks) >= 2:
            # Most recently visited first
            assert bookmarks[0].title == "Bookmark 1"


class TestTimeBasedEdgeCases:
    """Test edge cases for time-based navigation."""

    def test_invalid_period_name(self):
        """Invalid period name should not be in time_ranges."""
        ranges = get_time_ranges()
        assert 'invalid-period' not in ranges
        assert 'last-year' not in ranges  # not implemented

    def test_invalid_activity_type(self):
        """Invalid activity type should not filter bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)
            db.add(url="https://example.com/1", title="Test", added=now)

            bookmarks = db.list()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Invalid activity type should return empty list or handle gracefully
            filtered = filter_by_activity(bookmarks, 'invalid-activity', start, now)
            # Behavior: should return empty list or raise error
            # Let's test it returns empty
            assert len(filtered) == 0

    def test_empty_time_range(self):
        """Empty time range should return no bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)
            db.add(url="https://example.com/1", title="Test", added=now)

            bookmarks = db.list()

            # Create empty time range (end == start)
            filtered = filter_by_activity(bookmarks, 'added', now, now)
            assert len(filtered) == 0, "Empty time range should return no bookmarks"

    def test_future_time_range(self):
        """Future time range should return no bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            now = datetime.now(timezone.utc)
            db.add(url="https://example.com/1", title="Test", added=now)

            bookmarks = db.list()

            # Future time range
            future_start = now + timedelta(days=1)
            future_end = now + timedelta(days=2)

            filtered = filter_by_activity(bookmarks, 'added', future_start, future_end)
            assert len(filtered) == 0, "Future time range should return no bookmarks"


class TestPwdInTimeBasedDirectories:
    """Test pwd command in time-based directories."""

    @pytest.fixture
    def shell(self):
        """Create shell with test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            shell = BookmarkShell(db_path)
            yield shell

    def test_pwd_in_recent_root(self, shell):
        """pwd in /recent should show /recent."""
        shell.do_cd("/recent")
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_pwd("")
            mock_print.assert_called_once_with("/recent")

    def test_pwd_in_period_directory(self, shell):
        """pwd in /recent/today should show full path."""
        shell.do_cd("/recent/today")
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_pwd("")
            mock_print.assert_called_once_with("/recent/today")

    def test_pwd_in_activity_directory(self, shell):
        """pwd in /recent/today/visited should show full path."""
        shell.do_cd("/recent/today/visited")
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_pwd("")
            mock_print.assert_called_once_with("/recent/today/visited")
