# Smart Collections & Time-Based Recent Directories - Design Document

## Overview

This document outlines the design for two related features that enhance BTK's virtual filesystem:

1. **Smart Collections** - Auto-updating virtual directories based on dynamic criteria
2. **Time-Based /recent Directories** - Hierarchical time-based organization of recent activity

## Goals

- Provide intuitive ways to browse bookmarks by dynamic criteria
- Maintain Unix-like navigation consistency
- Keep implementation simple and performant
- Allow future extensibility for user-defined collections

## Current State

The shell already has basic collections:
- `/bookmarks` - All bookmarks
- `/tags/*` - Bookmarks filtered by tag hierarchy
- `/starred` - Starred bookmarks only
- `/archived` - Archived bookmarks only
- `/recent` - Recently added bookmarks (simple, not hierarchical)
- `/domains/*` - Bookmarks grouped by domain

## Feature 1: Enhanced Smart Collections

### Concept

Smart collections are virtual directories that dynamically filter bookmarks based on criteria. They auto-update as bookmarks change.

### Proposed Collections

#### Built-in Collections

```
/
├── starred          # Existing - bookmarks with stars=true
├── archived         # Existing - bookmarks with archived=true
├── recent           # Enhanced with time-based subdirectories (see Feature 2)
├── unread           # Bookmarks with visit_count=0
├── popular          # Bookmarks sorted by visit_count (top 100)
├── broken           # Bookmarks with reachable=false
├── untagged         # Bookmarks with no tags
├── pdfs             # Bookmarks pointing to PDF files (url ends with .pdf)
└── collections/     # User-defined collections (future)
```

### Architecture

#### 1. Collection Registry

```python
class SmartCollection:
    """Definition of a smart collection."""
    def __init__(self, name, filter_func, sort_func=None, description=""):
        self.name = name
        self.filter_func = filter_func  # Function: bookmarks -> filtered_bookmarks
        self.sort_func = sort_func      # Optional: bookmarks -> sorted_bookmarks
        self.description = description

# Registry of built-in collections
SMART_COLLECTIONS = {
    'unread': SmartCollection(
        name='unread',
        filter_func=lambda bms: [b for b in bms if b.visit_count == 0],
        description="Bookmarks never visited"
    ),
    'popular': SmartCollection(
        name='popular',
        filter_func=lambda bms: sorted(bms, key=lambda b: b.visit_count, reverse=True)[:100],
        description="100 most visited bookmarks"
    ),
    'broken': SmartCollection(
        name='broken',
        filter_func=lambda bms: [b for b in bms if b.reachable == False],
        description="Unreachable bookmarks"
    ),
    'untagged': SmartCollection(
        name='untagged',
        filter_func=lambda bms: [b for b in bms if len(b.tags) == 0],
        description="Bookmarks with no tags"
    ),
    'pdfs': SmartCollection(
        name='pdfs',
        filter_func=lambda bms: [b for b in bms if b.url.endswith('.pdf')],
        description="PDF bookmarks"
    ),
}
```

#### 2. Integration with Shell

Update `_get_context()` to recognize smart collections:

```python
elif parts[0] in SMART_COLLECTIONS:
    collection = SMART_COLLECTIONS[parts[0]]
    all_bookmarks = self.db.list()
    bookmarks = collection.filter_func(all_bookmarks)

    # Check if navigating to specific bookmark
    if len(parts) == 2 and parts[1].isdigit():
        bookmark_id = int(parts[1])
        bookmark = self.db.get(bookmark_id)
        if bookmark and bookmark in bookmarks:
            return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

    return {'type': 'smart_collection', 'name': parts[0], 'bookmarks': bookmarks}
```

Update `_ls_root()` to show new collections:

```python
def _ls_root(self):
    table = Table(show_header=False, box=None)
    table.add_column("Item", style="cyan")
    table.add_column("Description", style="dim")

    # Existing directories
    table.add_row("bookmarks/", "All bookmarks")
    table.add_row("tags/", "Browse by tag hierarchy")
    table.add_row("starred/", "Starred bookmarks")
    table.add_row("archived/", "Archived bookmarks")
    table.add_row("recent/", "Recently active bookmarks")
    table.add_row("domains/", "Browse by domain")

    # Smart collections
    table.add_row("unread/", "Never visited bookmarks")
    table.add_row("popular/", "Most visited bookmarks")
    table.add_row("broken/", "Unreachable bookmarks")
    table.add_row("untagged/", "Bookmarks without tags")
    table.add_row("pdfs/", "PDF documents")

    self.console.print(table)
```

### User Experience

```bash
btk:/$ ls
bookmarks/  tags/  starred/  archived/  recent/  domains/
unread/     popular/  broken/  untagged/  pdfs/

btk:/$ cd unread
btk:/unread$ ls
4201  4305  4506  4892  5001  5123  (bookmark IDs)

btk:/unread$ recent
# Shows recently added unread bookmarks

btk:/unread$ cat 4201/title
Interesting Article I Haven't Read Yet

btk:/unread$ visit 4201
# Opens bookmark, incrementing visit_count
# Bookmark automatically removed from /unread collection
```

## Feature 2: Time-Based /recent Directories

### Concept

Hierarchical organization of the `/recent` directory with time-based subdirectories for different activities (visited, added, starred).

### Proposed Structure

```
/recent/
├── today/
│   ├── visited/        # Bookmarks visited today
│   ├── added/          # Bookmarks added today
│   └── starred/        # Bookmarks starred today
├── yesterday/
│   ├── visited/
│   ├── added/
│   └── starred/
├── this-week/
│   ├── visited/
│   ├── added/
│   └── starred/
├── last-week/
│   ├── visited/
│   ├── added/
│   └── starred/
├── this-month/
│   ├── visited/
│   ├── added/
│   └── starred/
├── last-month/
│   ├── visited/
│   ├── added/
│   └── starred/
└── (bookmark IDs)      # Default: recently visited (backward compat)
```

### Time Period Definitions

```python
from datetime import datetime, timedelta, timezone

def get_time_ranges():
    """Get datetime ranges for time-based filtering."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        'today': (today_start, now),
        'yesterday': (today_start - timedelta(days=1), today_start),
        'this-week': (today_start - timedelta(days=now.weekday()), now),
        'last-week': (
            today_start - timedelta(days=now.weekday() + 7),
            today_start - timedelta(days=now.weekday())
        ),
        'this-month': (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now),
        'last-month': (
            (now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ),
    }
```

### Activity Types

```python
def filter_by_activity(bookmarks, activity_type, start_time, end_time):
    """Filter bookmarks by activity type and time range.

    Args:
        bookmarks: List of bookmarks
        activity_type: 'visited', 'added', or 'starred'
        start_time: Start of time range
        end_time: End of time range

    Returns:
        Filtered list of bookmarks
    """
    result = []

    for b in bookmarks:
        timestamp = None

        if activity_type == 'visited':
            timestamp = b.last_visited
        elif activity_type == 'added':
            timestamp = b.added
        elif activity_type == 'starred':
            # For starred, we need to check if they're starred
            # and use added as proxy for when they were starred
            # (would need starred_at field for precision)
            if b.stars:
                timestamp = b.added  # Approximation

        if timestamp:
            # Ensure timezone awareness
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            if start_time <= timestamp < end_time:
                result.append(b)

    return sorted(result, key=lambda b: timestamp, reverse=True)
```

### Integration with Shell

Update `_get_context()` for `/recent`:

```python
elif parts[0] == 'recent':
    # Handle time-based navigation: /recent/today/visited
    if len(parts) >= 2:
        time_period = parts[1]

        # Check if it's a bookmark ID (backward compat)
        if time_period.isdigit():
            bookmark_id = int(time_period)
            bookmark = self.db.get(bookmark_id)
            if bookmark:
                return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

        # Time-based directory
        time_ranges = get_time_ranges()
        if time_period in time_ranges:
            start_time, end_time = time_ranges[time_period]

            # Check for activity type: /recent/today/visited
            if len(parts) >= 3:
                activity_type = parts[2]
                if activity_type in ['visited', 'added', 'starred']:
                    # Check if navigating to specific bookmark
                    if len(parts) == 4 and parts[3].isdigit():
                        bookmark_id = int(parts[3])
                        bookmark = self.db.get(bookmark_id)
                        if bookmark:
                            return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

                    bookmarks = filter_by_activity(
                        self.db.list(), activity_type, start_time, end_time
                    )
                    return {
                        'type': 'recent_activity',
                        'period': time_period,
                        'activity': activity_type,
                        'bookmarks': bookmarks
                    }
            else:
                # /recent/today - show subdirectories
                return {
                    'type': 'recent_period',
                    'period': time_period,
                    'bookmarks': []
                }

    # Default: /recent - recently visited (backward compat)
    bookmarks = sorted(
        self.db.list(),
        key=lambda b: b.last_visited if b.last_visited else datetime.min,
        reverse=True
    )
    return {'type': 'recent', 'bookmarks': bookmarks}
```

Add display helper:

```python
def _ls_recent_period(self, period):
    """Display activity subdirectories for a time period."""
    table = Table(show_header=False, box=None)
    table.add_column("Activity", style="cyan")
    table.add_column("Count", style="dim")

    time_ranges = get_time_ranges()
    start_time, end_time = time_ranges[period]
    all_bookmarks = self.db.list()

    for activity in ['visited', 'added', 'starred']:
        filtered = filter_by_activity(all_bookmarks, activity, start_time, end_time)
        table.add_row(f"{activity}/", str(len(filtered)))

    self.console.print(table)
```

### User Experience

```bash
btk:/$ cd recent
btk:/recent$ ls
today/  yesterday/  this-week/  last-week/  this-month/  last-month/
4892  4765  4501  ...  (recently visited bookmarks - backward compat)

btk:/recent$ cd today
btk:/recent/today$ ls
visited/    12 bookmarks
added/      3 bookmarks
starred/    1 bookmark

btk:/recent/today$ cd visited
btk:/recent/today/visited$ ls
4892  4765  4501  4305  4201  ...

btk:/recent/today/visited$ cat 4892/title
Python Tutorial

btk:/recent/today$ cd ../added
btk:/recent/today/added$ ls
5001  5002  5003

btk:/recent$ cd last-week/starred
btk:/recent/last-week/starred$ ls
4876  4654  4321
```

## Implementation Plan

### Phase 1: Smart Collections Foundation
1. Create `SmartCollection` class
2. Define built-in collections registry
3. Update `_get_context()` to handle smart collections
4. Update `_ls_root()` to display collections
5. Add tests for smart collections

### Phase 2: Time-Based Recent
1. Create time range calculation functions
2. Create activity filtering functions
3. Update `/recent` context detection
4. Add `_ls_recent_period()` helper
5. Update backward compatibility for `/recent/<id>`
6. Add tests for time-based navigation

### Phase 3: Polish & Documentation
1. Add help text for new directories
2. Update shell documentation
3. Update README
4. Add examples to quickstart guide
5. Performance testing with large datasets

## Performance Considerations

### Caching
- Smart collections compute on access (lazy evaluation)
- For large bookmark collections (>10k), consider caching results
- Cache invalidation on bookmark changes

### Database Queries
- Current implementation loads all bookmarks into memory
- For future optimization, could push filtering to SQL queries
- Time-based filtering particularly benefits from indexed queries

```python
# Optimized database query (future enhancement)
def get_bookmarks_by_time_range(db, field, start, end):
    """Get bookmarks filtered by time range using SQL."""
    from btk.models import Bookmark
    with db.session() as session:
        if field == 'visited':
            return session.query(Bookmark).filter(
                Bookmark.last_visited.between(start, end)
            ).order_by(Bookmark.last_visited.desc()).all()
        elif field == 'added':
            return session.query(Bookmark).filter(
                Bookmark.added.between(start, end)
            ).order_by(Bookmark.added.desc()).all()
```

## Future Enhancements

### User-Defined Collections
Allow users to define custom collections in config:

```toml
# ~/.config/btk/config.toml
[collections.reading-list]
filter = "unread AND (tag:books OR tag:articles)"
sort = "added DESC"

[collections.work]
filter = "tag:work/* AND NOT archived"
sort = "visit_count DESC"
```

### Dynamic Collection Parameters
```bash
btk:/$ cd popular/50  # Top 50 instead of 100
btk:/$ cd recent/7-days/visited  # Custom time range
```

### Collection Operators
```bash
btk:/$ cd starred+unread  # Intersection
btk:/$ cd programming-python  # Difference
```

## Testing Strategy

### Unit Tests
- Test time range calculations for edge cases (month boundaries, leap years)
- Test activity filtering logic
- Test smart collection filters
- Test backward compatibility

### Integration Tests
- Test navigation through time-based directories
- Test context detection for nested paths
- Test that `ls` shows correct subdirectories
- Test bookmark access from collections

### Performance Tests
- Benchmark collection filtering with 10k, 100k bookmarks
- Test navigation speed
- Memory usage profiling

## Migration & Backward Compatibility

### Existing `/recent` Behavior
- Currently shows recently **added** bookmarks
- New behavior: shows recently **visited** bookmarks at root
- Backward compatible: `/recent/<id>` still works for bookmark access

### Migration Path
1. Phase 1: Add new directories alongside existing behavior
2. Phase 2: Update documentation to guide users to new structure
3. No breaking changes - old behavior still available

## Success Metrics

- ✅ All existing shell navigation still works
- ✅ New collections accessible via `cd`
- ✅ Time-based navigation intuitive and consistent
- ✅ Performance acceptable for 10k+ bookmarks
- ✅ Tests cover all new functionality
- ✅ Documentation updated and clear

## Open Questions

1. **Should starred bookmarks track `starred_at` timestamp?**
   - Currently approximating with `added` timestamp
   - Would require schema change to be accurate

2. **Should we cache collection results?**
   - How to invalidate cache?
   - Worth the complexity?

3. **Should collections show counts in `ls` output?**
   - `/unread/ (42 bookmarks)`
   - More informative but more verbose

4. **Default sort order for collections?**
   - Most recent first? Most visited? Alphabetical?
   - Should be configurable?
