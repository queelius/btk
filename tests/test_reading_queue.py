"""Tests for the reading queue module."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from btk.reading_queue import (
    ReadingQueueItem,
    get_reading_data,
    is_in_queue,
    add_to_queue,
    remove_from_queue,
    update_progress,
    set_priority,
    get_queue,
    get_queue_stats,
    get_next_to_read
)


class MockBookmark:
    """Mock bookmark for testing."""
    def __init__(self, id, title="Test", url="https://example.com", extra_data=None):
        self.id = id
        self.title = title
        self.url = url
        self.extra_data = extra_data or {}


class TestReadingQueueItem:
    """Tests for ReadingQueueItem dataclass."""

    def test_basic_item(self):
        """Test creating a basic queue item."""
        bookmark = MockBookmark(1, "Test Article")
        item = ReadingQueueItem(
            bookmark=bookmark,
            progress=50,
            priority=2,
            queued_at=datetime.now(timezone.utc),
            estimated_read_time=15
        )
        assert item.bookmark.id == 1
        assert item.progress == 50
        assert item.priority == 2
        assert item.estimated_read_time == 15
        assert item.is_complete is False

    def test_is_complete(self):
        """Test is_complete property."""
        bookmark = MockBookmark(1)

        item_incomplete = ReadingQueueItem(
            bookmark=bookmark,
            progress=99,
            priority=3,
            queued_at=datetime.now(timezone.utc),
            estimated_read_time=None
        )
        assert item_incomplete.is_complete is False

        item_complete = ReadingQueueItem(
            bookmark=bookmark,
            progress=100,
            priority=3,
            queued_at=datetime.now(timezone.utc),
            estimated_read_time=None
        )
        assert item_complete.is_complete is True

    def test_to_dict(self):
        """Test conversion to dictionary."""
        bookmark = MockBookmark(42, "Test Title", "https://test.com")
        now = datetime.now(timezone.utc)
        item = ReadingQueueItem(
            bookmark=bookmark,
            progress=75,
            priority=1,
            queued_at=now,
            estimated_read_time=30
        )
        d = item.to_dict()
        assert d['bookmark_id'] == 42
        assert d['title'] == "Test Title"
        assert d['url'] == "https://test.com"
        assert d['progress'] == 75
        assert d['priority'] == 1
        assert d['estimated_read_time'] == 30
        assert d['is_complete'] is False


class TestGetReadingData:
    """Tests for get_reading_data function."""

    def test_empty_extra_data(self):
        """Test with no extra data."""
        bookmark = MockBookmark(1, extra_data=None)
        data = get_reading_data(bookmark)
        assert data['in_queue'] is False
        assert data['progress'] == 0
        assert data['priority'] == 3
        assert data['queued_at'] is None

    def test_with_queue_data(self):
        """Test with reading queue data."""
        bookmark = MockBookmark(1, extra_data={
            'reading_queue': True,
            'reading_progress': 50,
            'reading_priority': 1,
            'queued_at': '2024-01-15T10:00:00+00:00'
        })
        data = get_reading_data(bookmark)
        assert data['in_queue'] is True
        assert data['progress'] == 50
        assert data['priority'] == 1
        assert data['queued_at'] == '2024-01-15T10:00:00+00:00'


class TestIsInQueue:
    """Tests for is_in_queue function."""

    def test_not_in_queue(self):
        """Test bookmark not in queue."""
        bookmark = MockBookmark(1, extra_data={})
        assert is_in_queue(bookmark) is False

    def test_in_queue(self):
        """Test bookmark in queue."""
        bookmark = MockBookmark(1, extra_data={'reading_queue': True})
        assert is_in_queue(bookmark) is True

    def test_explicitly_not_in_queue(self):
        """Test bookmark explicitly not in queue."""
        bookmark = MockBookmark(1, extra_data={'reading_queue': False})
        assert is_in_queue(bookmark) is False


class TestAddToQueue:
    """Tests for add_to_queue function."""

    def test_add_to_queue(self):
        """Test adding bookmark to queue."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1)
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        result = add_to_queue(mock_db, 1, priority=2)

        assert result is True
        mock_db.update.assert_called_once()
        call_args = mock_db.update.call_args
        assert call_args[0][0] == 1
        extra = call_args[1]['extra_data']
        assert extra['reading_queue'] is True
        assert extra['reading_priority'] == 2

    def test_add_nonexistent_bookmark(self):
        """Test adding nonexistent bookmark."""
        mock_db = MagicMock()
        mock_db.get.return_value = None

        result = add_to_queue(mock_db, 999)

        assert result is False
        mock_db.update.assert_not_called()

    def test_add_with_estimated_time(self):
        """Test adding with estimated read time."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1)
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        result = add_to_queue(mock_db, 1, estimated_read_time=20)

        assert result is True
        call_args = mock_db.update.call_args
        extra = call_args[1]['extra_data']
        assert extra['estimated_read_time'] == 20


class TestRemoveFromQueue:
    """Tests for remove_from_queue function."""

    def test_remove_from_queue(self):
        """Test removing bookmark from queue."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1, extra_data={'reading_queue': True})
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        result = remove_from_queue(mock_db, 1)

        assert result is True
        call_args = mock_db.update.call_args
        extra = call_args[1]['extra_data']
        assert extra['reading_queue'] is False

    def test_remove_nonexistent(self):
        """Test removing nonexistent bookmark."""
        mock_db = MagicMock()
        mock_db.get.return_value = None

        result = remove_from_queue(mock_db, 999)

        assert result is False


class TestUpdateProgress:
    """Tests for update_progress function."""

    def test_update_progress(self):
        """Test updating reading progress."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1, extra_data={'reading_queue': True})
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        result = update_progress(mock_db, 1, 75)

        assert result is True
        call_args = mock_db.update.call_args
        extra = call_args[1]['extra_data']
        assert extra['reading_progress'] == 75

    def test_progress_clamps(self):
        """Test progress is clamped to 0-100."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1, extra_data={})
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        # Test clamping to 0
        update_progress(mock_db, 1, -10)
        call_args = mock_db.update.call_args
        assert call_args[1]['extra_data']['reading_progress'] == 0

        # Test clamping to 100
        update_progress(mock_db, 1, 150)
        call_args = mock_db.update.call_args
        assert call_args[1]['extra_data']['reading_progress'] == 100

    def test_complete_removes_from_queue(self):
        """Test 100% progress removes from queue."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1, extra_data={'reading_queue': True})
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        update_progress(mock_db, 1, 100)

        call_args = mock_db.update.call_args
        extra = call_args[1]['extra_data']
        assert extra['reading_progress'] == 100
        assert extra['reading_queue'] is False
        assert 'completed_at' in extra


class TestSetPriority:
    """Tests for set_priority function."""

    def test_set_priority(self):
        """Test setting priority."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1, extra_data={})
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        result = set_priority(mock_db, 1, 1)

        assert result is True
        call_args = mock_db.update.call_args
        extra = call_args[1]['extra_data']
        assert extra['reading_priority'] == 1

    def test_priority_clamps(self):
        """Test priority is clamped to 1-5."""
        mock_db = MagicMock()
        mock_bookmark = MockBookmark(1, extra_data={})
        mock_db.get.return_value = mock_bookmark
        mock_db.update.return_value = True

        set_priority(mock_db, 1, 0)
        call_args = mock_db.update.call_args
        assert call_args[1]['extra_data']['reading_priority'] == 1

        set_priority(mock_db, 1, 10)
        call_args = mock_db.update.call_args
        assert call_args[1]['extra_data']['reading_priority'] == 5


class TestGetQueue:
    """Tests for get_queue function."""

    def test_empty_queue(self):
        """Test getting empty queue."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={}),
            MockBookmark(2, extra_data={'reading_queue': False})
        ]

        queue = get_queue(mock_db)
        assert len(queue) == 0

    def test_get_queue_items(self):
        """Test getting queue items."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, "First", extra_data={'reading_queue': True, 'reading_priority': 1, 'reading_progress': 0}),
            MockBookmark(2, "Second", extra_data={'reading_queue': True, 'reading_priority': 2, 'reading_progress': 50}),
            MockBookmark(3, "Not in queue", extra_data={}),
        ]

        queue = get_queue(mock_db)
        assert len(queue) == 2
        assert queue[0].bookmark.id == 1  # Priority 1 comes first
        assert queue[1].bookmark.id == 2

    def test_exclude_completed(self):
        """Test excluding completed items."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={'reading_queue': True, 'reading_progress': 50}),
            MockBookmark(2, extra_data={'reading_queue': True, 'reading_progress': 100}),
        ]

        queue = get_queue(mock_db, include_completed=False)
        assert len(queue) == 1
        assert queue[0].bookmark.id == 1

    def test_include_completed(self):
        """Test including completed items."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={'reading_queue': True, 'reading_progress': 50}),
            MockBookmark(2, extra_data={'reading_queue': True, 'reading_progress': 100}),
        ]

        queue = get_queue(mock_db, include_completed=True)
        assert len(queue) == 2

    def test_sort_by_progress(self):
        """Test sorting by progress."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={'reading_queue': True, 'reading_progress': 25}),
            MockBookmark(2, extra_data={'reading_queue': True, 'reading_progress': 75}),
            MockBookmark(3, extra_data={'reading_queue': True, 'reading_progress': 50}),
        ]

        queue = get_queue(mock_db, sort_by='progress')
        assert queue[0].bookmark.id == 2  # 75% first
        assert queue[1].bookmark.id == 3  # 50% second
        assert queue[2].bookmark.id == 1  # 25% third


class TestGetQueueStats:
    """Tests for get_queue_stats function."""

    def test_empty_queue_stats(self):
        """Test stats for empty queue."""
        mock_db = MagicMock()
        mock_db.all.return_value = []

        stats = get_queue_stats(mock_db)
        assert stats['total'] == 0
        assert stats['in_progress'] == 0
        assert stats['not_started'] == 0
        assert stats['completed'] == 0
        assert stats['avg_progress'] == 0

    def test_queue_stats(self):
        """Test calculating queue stats."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={'reading_queue': True, 'reading_progress': 0, 'reading_priority': 1}),
            MockBookmark(2, extra_data={'reading_queue': True, 'reading_progress': 50, 'reading_priority': 2}),
            MockBookmark(3, extra_data={'reading_queue': True, 'reading_progress': 100, 'reading_priority': 2}),
            MockBookmark(4, extra_data={'reading_queue': True, 'reading_progress': 75, 'reading_priority': 3}),
        ]

        stats = get_queue_stats(mock_db)
        assert stats['total'] == 4
        assert stats['not_started'] == 1
        assert stats['in_progress'] == 2  # 50% and 75%
        assert stats['completed'] == 1
        assert stats['avg_progress'] == 56.2  # (0+50+100+75)/4, rounded to 1 decimal
        assert stats['by_priority'][1] == 1
        assert stats['by_priority'][2] == 2
        assert stats['by_priority'][3] == 1


class TestGetNextToRead:
    """Tests for get_next_to_read function."""

    def test_empty_queue(self):
        """Test empty queue returns None."""
        mock_db = MagicMock()
        mock_db.all.return_value = []

        result = get_next_to_read(mock_db)
        assert result is None

    def test_prefers_highest_priority(self):
        """Test returns highest priority item."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={'reading_queue': True, 'reading_priority': 3, 'reading_progress': 0}),
            MockBookmark(2, extra_data={'reading_queue': True, 'reading_priority': 1, 'reading_progress': 0}),
            MockBookmark(3, extra_data={'reading_queue': True, 'reading_priority': 2, 'reading_progress': 0}),
        ]

        result = get_next_to_read(mock_db)
        assert result.bookmark.id == 2  # Priority 1

    def test_prefers_in_progress_over_not_started(self):
        """Test prefers items already in progress."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={'reading_queue': True, 'reading_priority': 1, 'reading_progress': 0}),
            MockBookmark(2, extra_data={'reading_queue': True, 'reading_priority': 1, 'reading_progress': 50}),
        ]

        result = get_next_to_read(mock_db)
        assert result.bookmark.id == 2  # Already started

    def test_excludes_completed(self):
        """Test excludes completed items."""
        mock_db = MagicMock()
        mock_db.all.return_value = [
            MockBookmark(1, extra_data={'reading_queue': True, 'reading_priority': 1, 'reading_progress': 100}),
            MockBookmark(2, extra_data={'reading_queue': True, 'reading_priority': 2, 'reading_progress': 0}),
        ]

        result = get_next_to_read(mock_db)
        assert result.bookmark.id == 2


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_queue_help(self):
        """Test queue command is registered."""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'btk.cli', 'queue', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert 'list' in result.stdout
        assert 'add' in result.stdout
        assert 'remove' in result.stdout
        assert 'progress' in result.stdout
        assert 'priority' in result.stdout
        assert 'next' in result.stdout
        assert 'stats' in result.stdout
