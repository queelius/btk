# Bookmark Scheduler Integration

Schedule bookmarks for reading, review, and reminders with spaced repetition. Perfect for managing read-later queues and learning materials.

## Features

- **Read-Later Queue**: Priority-based reading queue
- **Reminders**: Schedule bookmarks for specific times
- **Periodic Review**: Regular review scheduling
- **Spaced Repetition**: SM-2 algorithm for learning materials
- **Daily Rotation**: Surface random bookmarks daily
- **Snooze Functionality**: Postpone bookmarks
- **Statistics**: Track scheduling patterns

## Installation

No dependencies - uses Python standard library only.

## Usage

```python
from integrations.bookmark_scheduler.scheduler import BookmarkScheduler, ScheduleType, Priority

scheduler = BookmarkScheduler()

# Schedule for read-later
bookmark = {'url': 'https://example.com/article', 'title': 'Article'}
schedule = scheduler.schedule_bookmark(
    bookmark=bookmark,
    schedule_type=ScheduleType.READ_LATER,
    priority=Priority.HIGH
)

# Get due bookmarks
due = scheduler.get_due_bookmarks()
for item in due:
    print(f"{item.bookmark_id}: {item.notes}")

# Mark as reviewed
scheduler.mark_reviewed(bookmark_id, reschedule=True)
```

## Schedule Types

### READ_LATER
Priority-based reading queue with automatic scheduling based on priority.

```python
# Urgent: 1 hour
scheduler.schedule_bookmark(bookmark, ScheduleType.READ_LATER, Priority.URGENT)

# High: 1 day
scheduler.schedule_bookmark(bookmark, ScheduleType.READ_LATER, Priority.HIGH)

# Normal: 3 days
scheduler.schedule_bookmark(bookmark, ScheduleType.READ_LATER, Priority.NORMAL)

# Low: 1 week
scheduler.schedule_bookmark(bookmark, ScheduleType.READ_LATER, Priority.LOW)

# Someday: 30 days
scheduler.schedule_bookmark(bookmark, ScheduleType.READ_LATER, Priority.SOMEDAY)
```

### REMINDER
One-time reminders for time-sensitive bookmarks.

```python
from datetime import datetime, timedelta

# Schedule reminder for tomorrow at 9 AM
tomorrow_9am = datetime.now() + timedelta(days=1)
tomorrow_9am = tomorrow_9am.replace(hour=9, minute=0)

scheduler.schedule_bookmark(
    bookmark,
    ScheduleType.REMINDER,
    when=tomorrow_9am,
    notes="Read before meeting"
)
```

### PERIODIC_REVIEW
Recurring reviews (daily, weekly, monthly).

```python
scheduler.schedule_bookmark(
    bookmark,
    ScheduleType.PERIODIC_REVIEW,
    recurrence="weekly",  # daily, weekly, biweekly, monthly, quarterly, yearly
    notes="Review documentation updates"
)
```

### SPACED_REPETITION
Learning materials with spaced repetition algorithm (SM-2).

```python
scheduler.schedule_bookmark(
    bookmark,
    ScheduleType.SPACED_REPETITION
)

# Review intervals: 1d, 3d, 7d, 14d, 30d, 90d, 180d, 365d
# Automatically increases interval after each review
```

### DAILY_ROTATION
Surface random bookmarks for daily discovery.

```python
scheduler.schedule_bookmark(
    bookmark,
    ScheduleType.DAILY_ROTATION
)

# Get 5 bookmarks for today
daily = scheduler.get_daily_rotation(count=5)
```

## Priority Levels

```python
Priority.URGENT   # 1 - Must read ASAP
Priority.HIGH     # 2 - Important
Priority.NORMAL   # 3 - Standard priority
Priority.LOW      # 4 - Read when free
Priority.SOMEDAY  # 5 - Maybe someday
```

## Examples

### Read-Later Queue

```python
# Add to queue
for bookmark in new_articles:
    scheduler.schedule_bookmark(
        bookmark,
        ScheduleType.READ_LATER,
        priority=Priority.NORMAL
    )

# Get today's reading list
queue = scheduler.get_read_later_queue(limit=10)
for item in queue:
    print(f"[{item.priority.name}] {item.bookmark_id}")

# Mark as read
for item in queue[:5]:
    scheduler.mark_reviewed(item.bookmark_id, reschedule=False)
```

### Learning Materials

```python
# Schedule for spaced repetition
for bookmark in learning_resources:
    scheduler.schedule_bookmark(
        bookmark,
        ScheduleType.SPACED_REPETITION,
        notes="Python tutorial"
    )

# Review due items
due = scheduler.get_due_bookmarks()
for item in due:
    if item.schedule_type == ScheduleType.SPACED_REPETITION:
        # Show item to user for review
        print(f"Review: {item.bookmark_id}")

        # Mark reviewed (automatically schedules next review)
        scheduler.mark_reviewed(item.bookmark_id, reschedule=True)
```

### Daily Bookmark Discovery

```python
# Get 5 random bookmarks for today
daily = scheduler.get_daily_rotation(count=5)

print("Today's bookmarks:")
for item in daily:
    print(f"- {item.bookmark_id}: {item.notes}")

# Mark as viewed
for item in daily:
    scheduler.mark_reviewed(item.bookmark_id, reschedule=True)
```

### Snooze Functionality

```python
# Snooze for default duration (based on priority)
scheduler.snooze_bookmark(bookmark_id)

# Custom snooze duration
from datetime import timedelta
scheduler.snooze_bookmark(bookmark_id, duration=timedelta(hours=4))

# Snooze increments count (track habitual snoozing)
schedule = scheduler.get_schedule(bookmark_id)
print(f"Snoozed {schedule.snooze_count} times")
```

## Scheduled Bookmark Structure

```python
@dataclass
class ScheduledBookmark:
    bookmark_id: str              # URL or unique ID
    schedule_type: ScheduleType   # Type of schedule
    scheduled_for: datetime       # When it's due
    priority: Priority           # Priority level
    notes: str                    # Optional notes
    recurrence: str               # Recurrence pattern
    review_count: int             # Times reviewed
    last_reviewed: datetime       # Last review time
    snooze_count: int             # Times snoozed
    created_at: datetime          # Created timestamp
```

## Statistics

```python
stats = scheduler.get_statistics()

print(f"""
Scheduling Statistics:
  Total scheduled: {stats['total_scheduled']}
  Overdue: {stats['overdue']}
  Due today: {stats['due_today']}
  Due this week: {stats['due_this_week']}

By Type:
{stats['by_type']}

By Priority:
{stats['by_priority']}

Most reviewed: {stats['most_reviewed']}
Average snoozes: {stats['average_snooze_count']:.2f}
""")
```

## Querying Schedules

```python
# Get specific schedule
schedule = scheduler.get_schedule(bookmark_id)

# Get all due bookmarks
due = scheduler.get_due_bookmarks()

# Get upcoming (next 7 days)
upcoming = scheduler.get_upcoming_bookmarks(days=7)

# Get read-later queue
queue = scheduler.get_read_later_queue(limit=20)

# Get daily rotation
daily = scheduler.get_daily_rotation(count=5)
```

## Data Storage

Schedules are stored in `~/.btk/scheduler/schedules.json`:

```json
[
  {
    "bookmark_id": "https://example.com",
    "schedule_type": "read_later",
    "scheduled_for": "2024-01-15T10:30:00",
    "priority": 3,
    "notes": "Interesting article",
    "recurrence": null,
    "review_count": 0,
    "last_reviewed": null,
    "snooze_count": 0,
    "created_at": "2024-01-14T15:20:00"
  }
]
```

## Spaced Repetition Algorithm

Uses simplified SM-2 algorithm:

```python
# Review intervals
intervals = [1, 3, 7, 14, 30, 90, 180, 365]  # days

# After each review, interval increases
review_count=0: 1 day
review_count=1: 3 days
review_count=2: 7 days
review_count=3: 14 days
review_count=4: 30 days
review_count=5: 90 days
review_count=6: 180 days
review_count=7+: 365 days
```

## Recurrence Patterns

- `daily`: Every day
- `weekly`: Every week
- `biweekly`: Every 2 weeks
- `monthly`: Every 30 days
- `quarterly`: Every 90 days
- `yearly`: Every 365 days

## Troubleshooting

### Schedules Not Persisting

```python
# Check data directory
print(scheduler.data_dir)
print(scheduler.schedule_file)

# Ensure directory is writable
scheduler.data_dir.mkdir(parents=True, exist_ok=True)
```

### Incorrect Due Dates

```python
from datetime import datetime

# Check current time
now = datetime.now()

# Manually set schedule time
schedule.scheduled_for = datetime(2024, 1, 15, 10, 30)
scheduler._save_schedules()
```

## Best Practices

1. **Start simple**: Begin with READ_LATER queue
2. **Use priorities**: Properly prioritize bookmarks
3. **Regular reviews**: Check due bookmarks daily
4. **Snooze wisely**: Don't habitually snooze everything
5. **Track patterns**: Use statistics to optimize workflow

## Integration with BTK

```python
import btk.utils as utils

# Load bookmarks
bookmarks = utils.load_bookmarks('/path/to/library')

# Schedule unread articles
for bookmark in bookmarks:
    if 'article' in bookmark.get('tags', []):
        scheduler.schedule_bookmark(
            bookmark,
            ScheduleType.READ_LATER,
            priority=Priority.NORMAL
        )

# Get due reading list
due = scheduler.get_due_bookmarks()

# Map to actual bookmarks
bookmark_dict = {b['url']: b for b in bookmarks}
reading_list = [bookmark_dict.get(item.bookmark_id) for item in due
                if bookmark_dict.get(item.bookmark_id)]
```

## License

Part of the BTK (Bookmark Toolkit) project.
