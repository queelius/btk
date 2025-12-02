"""
Reading Queue Module for BTK.

Provides functionality for managing a reading queue/list of bookmarks,
tracking reading progress, and prioritizing content for later reading.

The reading queue uses the bookmark's extra_data JSON field to store:
- reading_queue: bool - whether bookmark is in the reading queue
- reading_progress: int (0-100) - reading progress percentage
- queued_at: ISO datetime string - when added to queue
- reading_priority: int (1-5) - priority level (1=highest)
- estimated_read_time: int - estimated reading time in minutes
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from .models import Bookmark


# Average reading speed in words per minute
WORDS_PER_MINUTE = 200


def estimate_reading_time(text: str, words_per_minute: int = WORDS_PER_MINUTE) -> int:
    """
    Estimate reading time for a text.

    Args:
        text: The text content to estimate
        words_per_minute: Reading speed (default: 200 WPM)

    Returns:
        Estimated reading time in minutes (minimum 1)
    """
    if not text:
        return 1

    # Count words (simple split on whitespace)
    word_count = len(text.split())

    # Calculate minutes, minimum 1
    minutes = max(1, round(word_count / words_per_minute))

    return minutes


def estimate_reading_time_for_bookmark(db, bookmark_id: int) -> Optional[int]:
    """
    Estimate reading time for a bookmark based on its cached content.

    Args:
        db: Database instance
        bookmark_id: ID of the bookmark

    Returns:
        Estimated reading time in minutes, or None if no content available
    """
    from .models import ContentCache
    from sqlalchemy import select

    with db.session() as session:
        stmt = select(ContentCache).where(ContentCache.bookmark_id == bookmark_id)
        cache = session.scalars(stmt).first()

        if cache and cache.markdown_content:
            return estimate_reading_time(cache.markdown_content)

    return None


def auto_estimate_queue_times(db, overwrite: bool = False) -> Dict[int, int]:
    """
    Auto-estimate reading times for all queue items.

    Args:
        db: Database instance
        overwrite: If True, overwrite existing estimates

    Returns:
        Dict mapping bookmark_id to estimated minutes
    """
    queue = get_queue(db, include_completed=True)
    estimates = {}

    for item in queue:
        # Skip if already has estimate and not overwriting
        if item.estimated_read_time and not overwrite:
            continue

        estimate = estimate_reading_time_for_bookmark(db, item.bookmark.id)
        if estimate:
            # Update the bookmark
            bookmark = db.get(id=item.bookmark.id)
            if bookmark:
                extra = bookmark.extra_data or {}
                extra['estimated_read_time'] = estimate
                db.update(item.bookmark.id, extra_data=extra)
                estimates[item.bookmark.id] = estimate

    return estimates


@dataclass
class ReadingQueueItem:
    """Represents a bookmark in the reading queue."""
    bookmark: Bookmark
    progress: int
    priority: int
    queued_at: datetime
    estimated_read_time: Optional[int]

    @property
    def is_complete(self) -> bool:
        return self.progress >= 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            'bookmark_id': self.bookmark.id,
            'url': self.bookmark.url,
            'title': self.bookmark.title,
            'progress': self.progress,
            'priority': self.priority,
            'queued_at': self.queued_at.isoformat() if self.queued_at else None,
            'estimated_read_time': self.estimated_read_time,
            'is_complete': self.is_complete
        }


def get_reading_data(bookmark: Bookmark) -> Dict[str, Any]:
    """Extract reading queue data from bookmark's extra_data."""
    extra = bookmark.extra_data or {}
    return {
        'in_queue': extra.get('reading_queue', False),
        'progress': extra.get('reading_progress', 0),
        'priority': extra.get('reading_priority', 3),
        'queued_at': extra.get('queued_at'),
        'estimated_read_time': extra.get('estimated_read_time')
    }


def is_in_queue(bookmark: Bookmark) -> bool:
    """Check if bookmark is in the reading queue."""
    extra = bookmark.extra_data or {}
    return extra.get('reading_queue', False)


def add_to_queue(db, bookmark_id: int, priority: int = 3,
                 estimated_read_time: Optional[int] = None) -> bool:
    """
    Add a bookmark to the reading queue.

    Args:
        db: Database instance
        bookmark_id: ID of the bookmark to add
        priority: Priority level (1-5, 1=highest)
        estimated_read_time: Estimated reading time in minutes

    Returns:
        True if successful, False if bookmark not found
    """
    bookmark = db.get(id=bookmark_id)
    if not bookmark:
        return False

    extra = bookmark.extra_data or {}
    extra['reading_queue'] = True
    extra['reading_progress'] = extra.get('reading_progress', 0)
    extra['reading_priority'] = max(1, min(5, priority))
    extra['queued_at'] = datetime.now(timezone.utc).isoformat()
    if estimated_read_time:
        extra['estimated_read_time'] = estimated_read_time

    return db.update(bookmark_id, extra_data=extra)


def remove_from_queue(db, bookmark_id: int) -> bool:
    """
    Remove a bookmark from the reading queue.

    Args:
        db: Database instance
        bookmark_id: ID of the bookmark to remove

    Returns:
        True if successful, False if bookmark not found
    """
    bookmark = db.get(id=bookmark_id)
    if not bookmark:
        return False

    extra = bookmark.extra_data or {}
    extra['reading_queue'] = False
    # Keep progress and other data for history

    return db.update(bookmark_id, extra_data=extra)


def update_progress(db, bookmark_id: int, progress: int) -> bool:
    """
    Update reading progress for a bookmark.

    Args:
        db: Database instance
        bookmark_id: ID of the bookmark
        progress: Progress percentage (0-100)

    Returns:
        True if successful, False if bookmark not found
    """
    bookmark = db.get(id=bookmark_id)
    if not bookmark:
        return False

    extra = bookmark.extra_data or {}
    extra['reading_progress'] = max(0, min(100, progress))

    # Auto-remove from queue if complete
    if progress >= 100:
        extra['reading_queue'] = False
        extra['completed_at'] = datetime.now(timezone.utc).isoformat()

    return db.update(bookmark_id, extra_data=extra)


def set_priority(db, bookmark_id: int, priority: int) -> bool:
    """
    Set priority for a reading queue item.

    Args:
        db: Database instance
        bookmark_id: ID of the bookmark
        priority: Priority level (1-5, 1=highest)

    Returns:
        True if successful, False if bookmark not found
    """
    bookmark = db.get(id=bookmark_id)
    if not bookmark:
        return False

    extra = bookmark.extra_data or {}
    extra['reading_priority'] = max(1, min(5, priority))

    return db.update(bookmark_id, extra_data=extra)


def get_queue(db, include_completed: bool = False,
              sort_by: str = 'priority') -> List[ReadingQueueItem]:
    """
    Get all bookmarks in the reading queue.

    Args:
        db: Database instance
        include_completed: Include items with 100% progress
        sort_by: Sort field ('priority', 'queued_at', 'progress', 'title')

    Returns:
        List of ReadingQueueItem objects
    """
    all_bookmarks = db.all()
    queue_items = []

    for bookmark in all_bookmarks:
        data = get_reading_data(bookmark)
        if not data['in_queue']:
            continue

        if not include_completed and data['progress'] >= 100:
            continue

        queued_at = None
        if data['queued_at']:
            try:
                queued_at = datetime.fromisoformat(data['queued_at'])
            except (ValueError, TypeError):
                queued_at = datetime.now(timezone.utc)

        item = ReadingQueueItem(
            bookmark=bookmark,
            progress=data['progress'],
            priority=data['priority'],
            queued_at=queued_at or datetime.now(timezone.utc),
            estimated_read_time=data['estimated_read_time']
        )
        queue_items.append(item)

    # Sort
    if sort_by == 'priority':
        queue_items.sort(key=lambda x: (x.priority, x.queued_at or datetime.min.replace(tzinfo=timezone.utc)))
    elif sort_by == 'queued_at':
        queue_items.sort(key=lambda x: x.queued_at or datetime.min.replace(tzinfo=timezone.utc))
    elif sort_by == 'progress':
        queue_items.sort(key=lambda x: x.progress, reverse=True)
    elif sort_by == 'title':
        queue_items.sort(key=lambda x: x.bookmark.title.lower())

    return queue_items


def get_queue_stats(db) -> Dict[str, Any]:
    """
    Get statistics about the reading queue.

    Returns:
        Dictionary with queue statistics
    """
    queue = get_queue(db, include_completed=True)

    total = len(queue)
    in_progress = sum(1 for item in queue if 0 < item.progress < 100)
    not_started = sum(1 for item in queue if item.progress == 0)
    completed = sum(1 for item in queue if item.progress >= 100)

    total_time = sum(item.estimated_read_time or 0 for item in queue if not item.is_complete)
    avg_progress = sum(item.progress for item in queue) / total if total > 0 else 0

    by_priority = {}
    for item in queue:
        p = item.priority
        by_priority[p] = by_priority.get(p, 0) + 1

    return {
        'total': total,
        'in_progress': in_progress,
        'not_started': not_started,
        'completed': completed,
        'avg_progress': round(avg_progress, 1),
        'estimated_remaining_time': total_time,
        'by_priority': by_priority
    }


def get_next_to_read(db) -> Optional[ReadingQueueItem]:
    """
    Get the next recommended item to read.

    Prioritizes by: priority level, then by progress (prefer started items),
    then by queued_at (oldest first).

    Returns:
        ReadingQueueItem or None if queue is empty
    """
    queue = get_queue(db, include_completed=False, sort_by='priority')

    if not queue:
        return None

    # Among highest priority items, prefer ones already started
    highest_priority = queue[0].priority
    candidates = [item for item in queue if item.priority == highest_priority]

    # Prefer items in progress over not started
    in_progress = [item for item in candidates if item.progress > 0]
    if in_progress:
        # Return the one closest to completion
        in_progress.sort(key=lambda x: x.progress, reverse=True)
        return in_progress[0]

    # Otherwise return oldest queued item
    candidates.sort(key=lambda x: x.queued_at or datetime.min.replace(tzinfo=timezone.utc))
    return candidates[0]
