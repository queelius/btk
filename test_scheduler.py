#!/usr/bin/env python3
"""
Test the bookmark scheduler plugin.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from integrations.bookmark_scheduler import BookmarkScheduler
from integrations.bookmark_scheduler.scheduler import ScheduleType, Priority

def test_scheduler():
    """Test the bookmark scheduler."""
    print("=== Testing Bookmark Scheduler ===\n")
    
    scheduler = BookmarkScheduler()
    
    # Test bookmarks
    bookmarks = [
        {'id': 1, 'url': 'https://example.com/article1', 'title': 'Important Article'},
        {'id': 2, 'url': 'https://example.com/tutorial', 'title': 'Python Tutorial'},
        {'id': 3, 'url': 'https://example.com/reference', 'title': 'API Reference'},
        {'id': 4, 'url': 'https://example.com/video', 'title': 'Video Course'},
        {'id': 5, 'url': 'https://example.com/blog', 'title': 'Blog Post'},
    ]
    
    # Schedule some bookmarks
    print("Scheduling bookmarks...")
    
    # Read later with different priorities
    s1 = scheduler.schedule_bookmark(
        bookmarks[0], 
        ScheduleType.READ_LATER,
        priority=Priority.URGENT,
        notes="Read this ASAP for the meeting"
    )
    print(f"  Scheduled '{bookmarks[0]['title']}' as URGENT read-later")
    
    s2 = scheduler.schedule_bookmark(
        bookmarks[1],
        ScheduleType.SPACED_REPETITION,
        notes="Learning Python advanced concepts"
    )
    print(f"  Scheduled '{bookmarks[1]['title']}' for spaced repetition")
    
    # Schedule a reminder
    tomorrow_9am = datetime.now().replace(hour=9, minute=0) + timedelta(days=1)
    s3 = scheduler.schedule_bookmark(
        bookmarks[2],
        ScheduleType.REMINDER,
        when=tomorrow_9am,
        notes="Check API changes"
    )
    print(f"  Scheduled '{bookmarks[2]['title']}' reminder for tomorrow 9am")
    
    # Periodic review
    s4 = scheduler.schedule_bookmark(
        bookmarks[3],
        ScheduleType.PERIODIC_REVIEW,
        recurrence="weekly",
        notes="Review progress on video course"
    )
    print(f"  Scheduled '{bookmarks[3]['title']}' for weekly review")
    
    # Daily rotation
    s5 = scheduler.schedule_bookmark(
        bookmarks[4],
        ScheduleType.DAILY_ROTATION,
        priority=Priority.LOW
    )
    print(f"  Scheduled '{bookmarks[4]['title']}' for daily rotation")
    
    print("\n" + "="*50 + "\n")
    
    # Get due bookmarks
    print("Due bookmarks:")
    due = scheduler.get_due_bookmarks()
    if due:
        for schedule in due:
            print(f"  - {schedule.bookmark_id}: {schedule.schedule_type.value} "
                  f"(Priority: {schedule.priority.name})")
    else:
        print("  No bookmarks due yet")
    
    print("\nUpcoming bookmarks (next 7 days):")
    upcoming = scheduler.get_upcoming_bookmarks(days=7)
    for schedule in upcoming[:5]:  # Show first 5
        days_until = (schedule.scheduled_for - datetime.now()).days
        print(f"  - {schedule.bookmark_id}: in {days_until} days "
              f"({schedule.schedule_type.value})")
    
    print("\n" + "="*50 + "\n")
    
    # Test read-later queue
    print("Read-Later Queue:")
    queue = scheduler.get_read_later_queue(limit=5)
    for i, schedule in enumerate(queue, 1):
        print(f"  {i}. {schedule.bookmark_id} - Priority: {schedule.priority.name}")
        if schedule.notes:
            print(f"     Notes: {schedule.notes}")
    
    print("\n" + "="*50 + "\n")
    
    # Test marking as reviewed
    print("Testing review functionality...")
    if upcoming:
        bookmark_id = upcoming[0].bookmark_id
        print(f"  Marking '{bookmark_id}' as reviewed...")
        updated = scheduler.mark_reviewed(bookmark_id)
        if updated:
            print(f"  Rescheduled for: {updated.scheduled_for.strftime('%Y-%m-%d %H:%M')}")
            print(f"  Review count: {updated.review_count}")
    
    # Test snoozing
    print("\nTesting snooze functionality...")
    if queue:
        bookmark_id = queue[0].bookmark_id
        print(f"  Snoozing '{bookmark_id}'...")
        snoozed = scheduler.snooze_bookmark(bookmark_id, timedelta(hours=4))
        if snoozed:
            print(f"  Snoozed until: {snoozed.scheduled_for.strftime('%Y-%m-%d %H:%M')}")
            print(f"  Snooze count: {snoozed.snooze_count}")
    
    print("\n" + "="*50 + "\n")
    
    # Get statistics
    print("Scheduler Statistics:")
    stats = scheduler.get_statistics()
    print(f"  Total scheduled: {stats['total_scheduled']}")
    print(f"  Overdue: {stats['overdue']}")
    print(f"  Due today: {stats['due_today']}")
    print(f"  Due this week: {stats['due_this_week']}")
    
    print("\n  By type:")
    for type_name, count in stats['by_type'].items():
        print(f"    {type_name}: {count}")
    
    print("\n  By priority:")
    for priority_name, count in stats['by_priority'].items():
        print(f"    {priority_name}: {count}")
    
    if stats['most_reviewed']:
        print(f"\n  Most reviewed: {stats['most_reviewed']['bookmark_id']} "
              f"({stats['most_reviewed']['review_count']} times)")
    
    print("\n✅ Scheduler test completed!")


if __name__ == "__main__":
    test_scheduler()