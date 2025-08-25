"""
Bookmark scheduler for BTK.

This module provides scheduling capabilities for bookmarks including
reminders, read-later queues, and periodic review scheduling.
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import heapq
import random

from btk.plugins import Plugin, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    """Types of bookmark schedules."""
    READ_LATER = "read_later"
    REMINDER = "reminder"
    PERIODIC_REVIEW = "periodic_review"
    SPACED_REPETITION = "spaced_repetition"
    DAILY_ROTATION = "daily_rotation"


class Priority(Enum):
    """Priority levels for scheduled bookmarks."""
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    SOMEDAY = 5


@dataclass
class ScheduledBookmark:
    """A scheduled bookmark entry."""
    bookmark_id: str  # ID or URL
    schedule_type: ScheduleType
    scheduled_for: datetime
    priority: Priority = Priority.NORMAL
    notes: str = ""
    recurrence: Optional[str] = None  # e.g., "daily", "weekly", "monthly"
    review_count: int = 0
    last_reviewed: Optional[datetime] = None
    snooze_count: int = 0
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if isinstance(self.schedule_type, str):
            self.schedule_type = ScheduleType(self.schedule_type)
        if isinstance(self.priority, int):
            self.priority = Priority(self.priority)
    
    def __lt__(self, other):
        """For priority queue sorting."""
        # Sort by scheduled time, then priority
        if self.scheduled_for != other.scheduled_for:
            return self.scheduled_for < other.scheduled_for
        return self.priority.value < other.priority.value


class BookmarkScheduler(Plugin):
    """
    Bookmark scheduling plugin for BTK.
    
    This plugin provides various scheduling features:
    - Read-later queue with priority management
    - Reminders for time-sensitive bookmarks
    - Periodic review scheduling
    - Spaced repetition for learning materials
    - Daily rotation of bookmarks to surface
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the bookmark scheduler.
        
        Args:
            data_dir: Directory to store schedule data
        """
        self._metadata = PluginMetadata(
            name="bookmark_scheduler",
            version="1.0.0",
            author="BTK Team",
            description="Schedule bookmarks for reading, review, and reminders",
            priority=PluginPriority.NORMAL.value
        )
        
        # Set up data directory
        self.data_dir = data_dir or (Path.home() / '.btk' / 'scheduler')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Schedule file
        self.schedule_file = self.data_dir / 'schedules.json'
        
        # Load existing schedules
        self.schedules: List[ScheduledBookmark] = self._load_schedules()
        
        # Create priority queue for efficient retrieval
        self._rebuild_queue()
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def _load_schedules(self) -> List[ScheduledBookmark]:
        """Load schedules from disk."""
        if not self.schedule_file.exists():
            return []
        
        try:
            with open(self.schedule_file, 'r') as f:
                data = json.load(f)
                
            schedules = []
            for item in data:
                # Convert datetime strings
                item['scheduled_for'] = datetime.fromisoformat(item['scheduled_for'])
                item['created_at'] = datetime.fromisoformat(item['created_at'])
                if item.get('last_reviewed'):
                    item['last_reviewed'] = datetime.fromisoformat(item['last_reviewed'])
                
                schedules.append(ScheduledBookmark(**item))
            
            return schedules
            
        except Exception as e:
            logger.error(f"Failed to load schedules: {e}")
            return []
    
    def _save_schedules(self):
        """Save schedules to disk."""
        try:
            data = []
            for schedule in self.schedules:
                item = asdict(schedule)
                # Convert datetime to strings
                item['scheduled_for'] = item['scheduled_for'].isoformat()
                item['created_at'] = item['created_at'].isoformat()
                if item['last_reviewed']:
                    item['last_reviewed'] = item['last_reviewed'].isoformat()
                # Convert enums to values
                item['schedule_type'] = item['schedule_type'].value
                item['priority'] = item['priority'].value
                data.append(item)
            
            with open(self.schedule_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save schedules: {e}")
    
    def _rebuild_queue(self):
        """Rebuild the priority queue."""
        self.queue = list(self.schedules)
        heapq.heapify(self.queue)
    
    def schedule_bookmark(self, bookmark: Dict[str, Any], 
                         schedule_type: ScheduleType,
                         when: Optional[datetime] = None,
                         priority: Priority = Priority.NORMAL,
                         recurrence: Optional[str] = None,
                         notes: str = "") -> ScheduledBookmark:
        """
        Schedule a bookmark.
        
        Args:
            bookmark: The bookmark to schedule
            schedule_type: Type of schedule
            when: When to schedule (None for type-specific defaults)
            priority: Priority level
            recurrence: Recurrence pattern (daily, weekly, monthly)
            notes: Additional notes
            
        Returns:
            The scheduled bookmark entry
        """
        # Determine bookmark ID
        bookmark_id = bookmark.get('unique_id') or bookmark.get('id') or bookmark.get('url')
        
        # Determine schedule time
        if when is None:
            when = self._get_default_schedule_time(schedule_type, priority)
        
        # Check if already scheduled
        existing = self.get_schedule(bookmark_id)
        if existing:
            # Update existing schedule
            existing.scheduled_for = when
            existing.priority = priority
            existing.schedule_type = schedule_type
            if recurrence:
                existing.recurrence = recurrence
            if notes:
                existing.notes = notes
            scheduled = existing
        else:
            # Create new schedule
            scheduled = ScheduledBookmark(
                bookmark_id=bookmark_id,
                schedule_type=schedule_type,
                scheduled_for=when,
                priority=priority,
                recurrence=recurrence,
                notes=notes
            )
            self.schedules.append(scheduled)
        
        # Rebuild queue and save
        self._rebuild_queue()
        self._save_schedules()
        
        return scheduled
    
    def _get_default_schedule_time(self, schedule_type: ScheduleType, 
                                  priority: Priority) -> datetime:
        """Get default schedule time based on type and priority."""
        now = datetime.now()
        
        if schedule_type == ScheduleType.READ_LATER:
            # Based on priority
            if priority == Priority.URGENT:
                return now + timedelta(hours=1)
            elif priority == Priority.HIGH:
                return now + timedelta(days=1)
            elif priority == Priority.LOW:
                return now + timedelta(weeks=1)
            elif priority == Priority.SOMEDAY:
                return now + timedelta(days=30)
            else:  # NORMAL
                return now + timedelta(days=3)
        
        elif schedule_type == ScheduleType.REMINDER:
            # Default to tomorrow at 9am
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        
        elif schedule_type == ScheduleType.PERIODIC_REVIEW:
            # Default to one week
            return now + timedelta(weeks=1)
        
        elif schedule_type == ScheduleType.SPACED_REPETITION:
            # Start with 1 day for first review
            return now + timedelta(days=1)
        
        else:  # DAILY_ROTATION
            # Tomorrow
            return now + timedelta(days=1)
    
    def get_schedule(self, bookmark_id: str) -> Optional[ScheduledBookmark]:
        """Get schedule for a bookmark."""
        for schedule in self.schedules:
            if schedule.bookmark_id == bookmark_id:
                return schedule
        return None
    
    def get_due_bookmarks(self, as_of: Optional[datetime] = None) -> List[ScheduledBookmark]:
        """
        Get bookmarks that are due.
        
        Args:
            as_of: Check due as of this time (default: now)
            
        Returns:
            List of due scheduled bookmarks
        """
        if as_of is None:
            as_of = datetime.now()
        
        due = []
        for schedule in self.schedules:
            if schedule.scheduled_for <= as_of:
                due.append(schedule)
        
        # Sort by scheduled time and priority
        due.sort()
        return due
    
    def get_upcoming_bookmarks(self, days: int = 7) -> List[ScheduledBookmark]:
        """
        Get upcoming scheduled bookmarks.
        
        Args:
            days: Number of days to look ahead
            
        Returns:
            List of upcoming scheduled bookmarks
        """
        now = datetime.now()
        future = now + timedelta(days=days)
        
        upcoming = []
        for schedule in self.schedules:
            if now <= schedule.scheduled_for <= future:
                upcoming.append(schedule)
        
        upcoming.sort()
        return upcoming
    
    def mark_reviewed(self, bookmark_id: str, 
                     reschedule: bool = True) -> Optional[ScheduledBookmark]:
        """
        Mark a bookmark as reviewed.
        
        Args:
            bookmark_id: Bookmark ID
            reschedule: Whether to reschedule based on recurrence
            
        Returns:
            Updated schedule or None
        """
        schedule = self.get_schedule(bookmark_id)
        if not schedule:
            return None
        
        # Update review info
        schedule.last_reviewed = datetime.now()
        schedule.review_count += 1
        
        if reschedule and schedule.recurrence:
            # Reschedule based on recurrence
            schedule.scheduled_for = self._calculate_next_schedule(schedule)
        elif reschedule and schedule.schedule_type == ScheduleType.SPACED_REPETITION:
            # Spaced repetition algorithm
            schedule.scheduled_for = self._calculate_spaced_repetition(schedule)
        else:
            # Remove from schedules
            self.schedules.remove(schedule)
        
        self._rebuild_queue()
        self._save_schedules()
        
        return schedule if schedule in self.schedules else None
    
    def _calculate_next_schedule(self, schedule: ScheduledBookmark) -> datetime:
        """Calculate next schedule time based on recurrence."""
        base = schedule.scheduled_for
        
        if schedule.recurrence == "daily":
            return base + timedelta(days=1)
        elif schedule.recurrence == "weekly":
            return base + timedelta(weeks=1)
        elif schedule.recurrence == "biweekly":
            return base + timedelta(weeks=2)
        elif schedule.recurrence == "monthly":
            return base + timedelta(days=30)
        elif schedule.recurrence == "quarterly":
            return base + timedelta(days=90)
        elif schedule.recurrence == "yearly":
            return base + timedelta(days=365)
        else:
            # Default to weekly
            return base + timedelta(weeks=1)
    
    def _calculate_spaced_repetition(self, schedule: ScheduledBookmark) -> datetime:
        """
        Calculate next review time using spaced repetition algorithm.
        
        Uses a simplified version of SM-2 algorithm.
        """
        # Intervals: 1 day, 3 days, 7 days, 14 days, 30 days, 90 days
        intervals = [1, 3, 7, 14, 30, 90, 180, 365]
        
        # Get next interval
        review_index = min(schedule.review_count, len(intervals) - 1)
        days = intervals[review_index]
        
        # Add some randomness to prevent clustering
        days += random.randint(-1, 1) if days > 3 else 0
        
        return datetime.now() + timedelta(days=max(1, days))
    
    def snooze_bookmark(self, bookmark_id: str, 
                       duration: Optional[timedelta] = None) -> Optional[ScheduledBookmark]:
        """
        Snooze a scheduled bookmark.
        
        Args:
            bookmark_id: Bookmark ID
            duration: Snooze duration (default: 1 day)
            
        Returns:
            Updated schedule or None
        """
        schedule = self.get_schedule(bookmark_id)
        if not schedule:
            return None
        
        if duration is None:
            # Default snooze based on priority
            if schedule.priority == Priority.URGENT:
                duration = timedelta(hours=2)
            elif schedule.priority == Priority.HIGH:
                duration = timedelta(hours=6)
            else:
                duration = timedelta(days=1)
        
        schedule.scheduled_for = datetime.now() + duration
        schedule.snooze_count += 1
        
        self._rebuild_queue()
        self._save_schedules()
        
        return schedule
    
    def remove_schedule(self, bookmark_id: str) -> bool:
        """
        Remove a bookmark from schedule.
        
        Args:
            bookmark_id: Bookmark ID
            
        Returns:
            True if removed, False if not found
        """
        schedule = self.get_schedule(bookmark_id)
        if schedule:
            self.schedules.remove(schedule)
            self._rebuild_queue()
            self._save_schedules()
            return True
        return False
    
    def get_read_later_queue(self, limit: Optional[int] = None) -> List[ScheduledBookmark]:
        """
        Get the read-later queue.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of read-later bookmarks sorted by priority and time
        """
        read_later = [s for s in self.schedules 
                     if s.schedule_type == ScheduleType.READ_LATER]
        read_later.sort()
        
        if limit:
            return read_later[:limit]
        return read_later
    
    def get_daily_rotation(self, count: int = 5) -> List[ScheduledBookmark]:
        """
        Get daily rotation of bookmarks.
        
        Args:
            count: Number of bookmarks to return
            
        Returns:
            List of bookmarks for daily rotation
        """
        # Get all daily rotation bookmarks
        rotation = [s for s in self.schedules 
                   if s.schedule_type == ScheduleType.DAILY_ROTATION]
        
        # Get due bookmarks
        now = datetime.now()
        due = [s for s in rotation if s.scheduled_for <= now]
        
        # If not enough due, add some upcoming
        if len(due) < count:
            upcoming = [s for s in rotation if s.scheduled_for > now]
            upcoming.sort()
            due.extend(upcoming[:count - len(due)])
        
        # Limit and shuffle for variety
        result = due[:count]
        random.shuffle(result)
        
        return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scheduling statistics."""
        now = datetime.now()
        
        stats = {
            'total_scheduled': len(self.schedules),
            'by_type': {},
            'by_priority': {},
            'overdue': 0,
            'due_today': 0,
            'due_this_week': 0,
            'average_snooze_count': 0,
            'most_reviewed': None,
            'longest_scheduled': None
        }
        
        # Count by type and priority
        for schedule in self.schedules:
            # By type
            type_name = schedule.schedule_type.value
            stats['by_type'][type_name] = stats['by_type'].get(type_name, 0) + 1
            
            # By priority
            priority_name = schedule.priority.name
            stats['by_priority'][priority_name] = stats['by_priority'].get(priority_name, 0) + 1
            
            # Check if overdue
            if schedule.scheduled_for < now:
                stats['overdue'] += 1
            elif schedule.scheduled_for.date() == now.date():
                stats['due_today'] += 1
            elif schedule.scheduled_for <= now + timedelta(days=7):
                stats['due_this_week'] += 1
        
        # Calculate averages
        if self.schedules:
            total_snoozes = sum(s.snooze_count for s in self.schedules)
            stats['average_snooze_count'] = total_snoozes / len(self.schedules)
            
            # Find most reviewed
            most_reviewed = max(self.schedules, key=lambda s: s.review_count)
            stats['most_reviewed'] = {
                'bookmark_id': most_reviewed.bookmark_id,
                'review_count': most_reviewed.review_count
            }
            
            # Find longest scheduled
            longest = max(self.schedules, key=lambda s: (s.scheduled_for - s.created_at).days)
            days_scheduled = (longest.scheduled_for - longest.created_at).days
            stats['longest_scheduled'] = {
                'bookmark_id': longest.bookmark_id,
                'days': days_scheduled
            }
        
        return stats


def register_plugins(registry):
    """Register the bookmark scheduler with the plugin registry."""
    scheduler = BookmarkScheduler()
    registry.register(scheduler)
    logger.info("Registered bookmark scheduler")