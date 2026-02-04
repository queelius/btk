#!/usr/bin/env python3
"""
BTK Shell - A filesystem-like REPL for browsing bookmarks.

Navigation:
- ls              List bookmarks (in current context)
- cd <id>         Enter a bookmark context
- cd ..           Go back to bookmark list
- pwd             Show current location

Viewing:
- cat <field>     Show bookmark field (url, title, tags, etc.)
- head <field>    Show first few lines of field
- less <field>    Page through field content
- file            Show bookmark type/metadata summary

Operations:
- edit <field>    Edit a bookmark field
- rm              Remove current bookmark
- star            Toggle star on bookmark
- tag <tags>      Add tags to bookmark
- untag <tags>    Remove tags from bookmark

Search & Filter:
- find <query>    Search bookmarks
- grep <pattern>  Search in bookmark fields
- which <id>      Find bookmark by ID

Metadata:
- stat            Show detailed bookmark statistics
- du              Show bookmark size/visit stats
- history         Show visit history

Utilities:
- help [cmd]      Show help for command
- exit, quit      Exit shell
- clear           Clear screen
- !<cmd>          Execute system command
"""

import cmd
import sys
import os
import subprocess
from typing import List
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from datetime import datetime, timezone

# Add parent to path for imports when run standalone
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent))

from btk.db import Database
from datetime import timedelta


# ============================================================================
# Smart Collections & Time-Based Filtering
# ============================================================================

class SmartCollection:
    """Definition of a smart collection - a virtual directory with dynamic filtering."""

    def __init__(self, name: str, filter_func, description: str = ""):
        self.name = name
        self.filter_func = filter_func  # Function: bookmarks -> filtered_bookmarks
        self.description = description


# Registry of built-in smart collections
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
        filter_func=lambda bms: [b for b in bms if b.url.lower().endswith('.pdf')],
        description="PDF bookmarks"
    ),
    'queue': SmartCollection(
        name='queue',
        filter_func=lambda bms: [b for b in bms if (b.extra_data or {}).get('reading_queue', False)],
        description="Reading queue"
    ),
    'media': SmartCollection(
        name='media',
        filter_func=lambda bms: [b for b in bms if b.media_type is not None],
        description="All media bookmarks"
    ),
}


def get_time_ranges():
    """Get datetime ranges for time-based filtering.

    Returns dict mapping period names to (start, end) tuples.
    """
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


def filter_by_activity(bookmarks, activity_type: str, start_time, end_time):
    """Filter bookmarks by activity type and time range.

    Args:
        bookmarks: List of bookmarks
        activity_type: 'visited', 'added', or 'starred'
        start_time: Start of time range (datetime)
        end_time: End of time range (datetime)

    Returns:
        Filtered and sorted list of bookmarks
    """
    result = []

    for b in bookmarks:
        timestamp = None

        if activity_type == 'visited':
            timestamp = b.last_visited
        elif activity_type == 'added':
            timestamp = b.added
        elif activity_type == 'starred':
            # Use added as approximation (no starred_at field yet)
            if b.stars:
                timestamp = b.added

        if timestamp:
            # Ensure timezone awareness
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            if start_time <= timestamp < end_time:
                result.append(b)

    # Sort by the relevant timestamp
    def get_sort_key(b):
        if activity_type == 'visited':
            ts = b.last_visited
        elif activity_type == 'added':
            ts = b.added
        else:  # starred
            ts = b.added
        return ts if ts else datetime.min.replace(tzinfo=timezone.utc)

    return sorted(result, key=get_sort_key, reverse=True)


class BookmarkShell(cmd.Cmd):
    """Interactive shell for browsing bookmarks like a filesystem."""

    intro = '''
╔════════════════════════════════════════════════════════════════╗
║                     BTK Shell v0.9.0                            ║
║          Browse your bookmarks like a filesystem                ║
╚════════════════════════════════════════════════════════════════╝

Type 'help' or '?' to list commands.
Type 'help <command>' for command details.
Type 'tutorial' for a quick tour.
'''

    def __init__(self, db_path: str = 'btk.db'):
        """Initialize bookmark shell."""
        super().__init__()
        self.db = Database(db_path)
        self.console = Console()
        self.cwd = "/"  # Current working directory (path-based)
        self.update_prompt()

    def update_prompt(self):
        """Update shell prompt based on current location."""
        self.prompt = f'btk:{self.cwd}$ '

    def _parse_path(self, path: str) -> str:
        """Parse and normalize a path.

        Handles:
        - Absolute paths (/bookmarks/123)
        - Relative paths (../tags, bookmarks/123)
        - . and ..

        Returns normalized absolute path.
        """
        if not path:
            return self.cwd

        # Handle absolute paths
        if path.startswith('/'):
            parts = path.split('/')
        else:
            # Relative path - start from cwd
            parts = (self.cwd + '/' + path).split('/')

        # Normalize path (handle . and ..)
        normalized = []
        for part in parts:
            if part == '' or part == '.':
                continue
            elif part == '..':
                if normalized:
                    normalized.pop()
            else:
                normalized.append(part)

        return '/' + '/'.join(normalized) if normalized else '/'

    def _get_context(self):
        """Get current context (bookmark, tag filter, etc.) based on cwd.

        Returns dict with:
        - type: 'root', 'bookmarks', 'bookmark', 'tags', 'tag', 'starred', etc.
        - bookmark_id: if in a bookmark
        - tag_path: if in tags hierarchy
        - bookmarks: filtered list of bookmarks for current context
        """
        parts = [p for p in self.cwd.split('/') if p]

        if not parts:  # Root
            return {'type': 'root', 'bookmarks': []}

        if parts[0] == 'bookmarks':
            if len(parts) == 1:
                # /bookmarks - list all
                return {'type': 'bookmarks', 'bookmarks': self.db.list()}
            elif len(parts) == 2 and parts[1].isdigit():
                # /bookmarks/123 - specific bookmark
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

        elif parts[0] == 'tags':
            # Check if the last part is a bookmark ID
            if len(parts) > 1 and parts[-1].isdigit():
                bookmark_id = int(parts[-1])
                bookmark = self.db.get(bookmark_id)

                # Verify this bookmark has the tag prefix
                if bookmark and len(parts) > 2:
                    tag_prefix = '/'.join(parts[1:-1])
                    has_tag = any(
                        t.name == tag_prefix or t.name.startswith(tag_prefix + '/')
                        for t in bookmark.tags
                    )
                    if has_tag:
                        return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
                elif bookmark and len(parts) == 2:
                    # /tags/3309 - just check if bookmark exists
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

            # /tags or /tags/programming or /tags/programming/python
            tag_path = '/'.join(parts[1:]) if len(parts) > 1 else ''
            bookmarks = self._get_bookmarks_by_tag_prefix(tag_path)
            return {'type': 'tags', 'tag_path': tag_path, 'bookmarks': bookmarks}

        elif parts[0] == 'starred':
            # Check if navigating to a specific bookmark
            if len(parts) == 2 and parts[1].isdigit():
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                if bookmark and bookmark.stars:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
            bookmarks = [b for b in self.db.list() if b.stars]
            return {'type': 'starred', 'bookmarks': bookmarks}

        elif parts[0] == 'archived':
            # Check if navigating to a specific bookmark
            if len(parts) == 2 and parts[1].isdigit():
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                if bookmark and bookmark.archived:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
            bookmarks = [b for b in self.db.list() if b.archived]
            return {'type': 'archived', 'bookmarks': bookmarks}

        elif parts[0] == 'recent':
            # Enhanced time-based recent directory
            # Structure: /recent/today/visited, /recent/yesterday/added, etc.
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

            # Default: /recent - recently visited (more intuitive than added)
            def safe_get_last_visited(b):
                ts = b.last_visited if b.last_visited else datetime.min
                if ts and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                elif not ts:
                    ts = datetime.min.replace(tzinfo=timezone.utc)
                return ts

            bookmarks = sorted(self.db.list(), key=safe_get_last_visited, reverse=True)
            return {'type': 'recent', 'bookmarks': bookmarks}

        elif parts[0] == 'domains':
            if len(parts) == 1:
                return {'type': 'domains', 'bookmarks': []}
            else:
                # Check if last part is a bookmark ID
                if parts[-1].isdigit():
                    bookmark_id = int(parts[-1])
                    bookmark = self.db.get(bookmark_id)
                    if bookmark and len(parts) > 2:
                        # Verify bookmark is from this domain
                        domain = '/'.join(parts[1:-1])
                        from urllib.parse import urlparse
                        parsed = urlparse(bookmark.url)
                        if parsed.netloc == domain:
                            return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
                    elif bookmark and len(parts) == 2:
                        return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

                domain = '/'.join(parts[1:])
                bookmarks = self._get_bookmarks_by_domain(domain)
                return {'type': 'domain', 'domain': domain, 'bookmarks': bookmarks}

        elif parts[0] == 'by-date':
            return self._get_by_date_context(parts)

        # Media collection with hierarchical paths
        elif parts[0] == 'media':
            return self._get_media_context(parts)

        # Check for smart collections
        elif parts[0] in SMART_COLLECTIONS:
            collection = SMART_COLLECTIONS[parts[0]]
            all_bookmarks = self.db.list()
            bookmarks = collection.filter_func(all_bookmarks)

            # Check if navigating to specific bookmark
            if len(parts) == 2 and parts[1].isdigit():
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                # Verify bookmark is in this collection
                if bookmark and bookmark in bookmarks:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

            return {
                'type': 'smart_collection',
                'name': parts[0],
                'description': collection.description,
                'bookmarks': bookmarks
            }

        return {'type': 'unknown', 'bookmarks': []}

    def _get_bookmarks_by_tag_prefix(self, tag_prefix: str) -> List:
        """Get bookmarks that have tags starting with the given prefix."""
        if not tag_prefix:
            return []

        bookmarks = []
        for b in self.db.list():
            for tag in b.tags:
                if tag.name == tag_prefix or tag.name.startswith(tag_prefix + '/'):
                    if b not in bookmarks:
                        bookmarks.append(b)
                        break
        return bookmarks

    def _get_bookmarks_by_domain(self, domain: str) -> List:
        """Get bookmarks from a specific domain."""
        from urllib.parse import urlparse
        bookmarks = []
        for b in self.db.list():
            parsed = urlparse(b.url)
            if parsed.netloc == domain:
                bookmarks.append(b)
        return bookmarks

    def _get_all_tags(self) -> List[str]:
        """Get all unique tags from all bookmarks."""
        from btk.models import Tag
        with self.db.session() as session:
            tags = session.query(Tag).all()
            return [t.name for t in tags]

    def _get_all_domains(self) -> List[str]:
        """Get all unique domains from all bookmarks."""
        from urllib.parse import urlparse
        domains = set()
        for b in self.db.list():
            parsed = urlparse(b.url)
            if parsed.netloc:
                domains.add(parsed.netloc)
        return sorted(domains)

    def _get_context_for_path(self, path):
        """Get context for any path (not just cwd)."""
        parts = [p for p in path.split('/') if p]

        if not parts:  # Root
            return {'type': 'root'}

        if parts[0] == 'bookmarks':
            if len(parts) == 1:
                return {'type': 'bookmarks', 'bookmarks': self.db.list()}
            elif len(parts) == 2 and parts[1].isdigit():
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

        elif parts[0] == 'tags':
            # Check if the last part is a bookmark ID
            if len(parts) > 1 and parts[-1].isdigit():
                # Could be /tags/video/3309 where 3309 is a bookmark
                bookmark_id = int(parts[-1])
                bookmark = self.db.get(bookmark_id)

                # Verify this bookmark has the tag prefix
                if bookmark and len(parts) > 2:
                    tag_prefix = '/'.join(parts[1:-1])
                    has_tag = any(
                        t.name == tag_prefix or t.name.startswith(tag_prefix + '/')
                        for t in bookmark.tags
                    )
                    if has_tag:
                        return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
                elif bookmark and len(parts) == 2:
                    # /tags/3309 - just check if bookmark exists
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

            # Regular tag path
            tag_path = '/'.join(parts[1:]) if len(parts) > 1 else ''
            bookmarks = self._get_bookmarks_by_tag_prefix(tag_path)
            return {'type': 'tags', 'tag_path': tag_path, 'bookmarks': bookmarks}

        elif parts[0] == 'starred':
            # Check if navigating to a specific bookmark
            if len(parts) == 2 and parts[1].isdigit():
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                if bookmark and bookmark.stars:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
            bookmarks = [b for b in self.db.list() if b.stars]
            return {'type': 'starred', 'bookmarks': bookmarks}

        elif parts[0] == 'archived':
            # Check if navigating to a specific bookmark
            if len(parts) == 2 and parts[1].isdigit():
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                if bookmark and bookmark.archived:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
            bookmarks = [b for b in self.db.list() if b.archived]
            return {'type': 'archived', 'bookmarks': bookmarks}

        elif parts[0] == 'recent':
            # Enhanced time-based recent directory
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

            # Default: /recent - recently visited
            def safe_get_last_visited(b):
                ts = b.last_visited if b.last_visited else datetime.min
                if ts and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                elif not ts:
                    ts = datetime.min.replace(tzinfo=timezone.utc)
                return ts

            bookmarks = sorted(self.db.list(), key=safe_get_last_visited, reverse=True)
            return {'type': 'recent', 'bookmarks': bookmarks}

        elif parts[0] == 'domains':
            if len(parts) == 1:
                return {'type': 'domains'}
            else:
                # Check if last part is a bookmark ID
                if parts[-1].isdigit():
                    bookmark_id = int(parts[-1])
                    bookmark = self.db.get(bookmark_id)
                    if bookmark and len(parts) > 2:
                        # Verify bookmark is from this domain
                        domain = '/'.join(parts[1:-1])
                        from urllib.parse import urlparse
                        parsed = urlparse(bookmark.url)
                        if parsed.netloc == domain:
                            return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
                    elif bookmark and len(parts) == 2:
                        return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

                domain = '/'.join(parts[1:])
                bookmarks = self._get_bookmarks_by_domain(domain)
                return {'type': 'domain', 'domain': domain, 'bookmarks': bookmarks}

        elif parts[0] == 'by-date':
            return self._get_by_date_context(parts)

        # Media collection with hierarchical paths
        elif parts[0] == 'media':
            return self._get_media_context(parts)

        # Check for smart collections
        elif parts[0] in SMART_COLLECTIONS:
            collection = SMART_COLLECTIONS[parts[0]]
            all_bookmarks = self.db.list()
            bookmarks = collection.filter_func(all_bookmarks)

            # Check if navigating to specific bookmark
            if len(parts) == 2 and parts[1].isdigit():
                bookmark_id = int(parts[1])
                bookmark = self.db.get(bookmark_id)
                # Verify bookmark is in this collection
                if bookmark and bookmark in bookmarks:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

            return {
                'type': 'smart_collection',
                'name': parts[0],
                'description': collection.description,
                'bookmarks': bookmarks
            }

        return {'type': 'unknown'}

    def _get_by_date_context(self, parts):
        """Get context for /by-date navigation.

        Structure:
            /by-date                    - Show date field options (added/visited)
            /by-date/added              - Show years for added dates
            /by-date/added/2024         - Show months in 2024
            /by-date/added/2024/03      - Show days in March 2024
            /by-date/added/2024/03/15   - Show bookmarks from March 15, 2024
            /by-date/visited            - Show years for last_visited dates
        """
        all_bookmarks = self.db.list()

        if len(parts) == 1:
            # /by-date - show field options
            return {'type': 'by_date_root', 'bookmarks': []}

        field = parts[1]  # 'added' or 'visited'
        if field not in ('added', 'visited'):
            return {'type': 'unknown'}

        # Map field name to attribute
        attr_name = 'added' if field == 'added' else 'last_visited'

        if len(parts) == 2:
            # /by-date/added - show years
            years = self._get_date_groups(all_bookmarks, attr_name, 'year')
            return {'type': 'by_date_years', 'field': field, 'years': years, 'bookmarks': []}

        year = int(parts[2])

        if len(parts) == 3:
            # /by-date/added/2024 - show months
            months = self._get_date_groups(all_bookmarks, attr_name, 'month', year=year)
            return {'type': 'by_date_months', 'field': field, 'year': year, 'months': months, 'bookmarks': []}

        month = int(parts[3])

        if len(parts) == 4:
            # /by-date/added/2024/03 - show days
            days = self._get_date_groups(all_bookmarks, attr_name, 'day', year=year, month=month)
            return {'type': 'by_date_days', 'field': field, 'year': year, 'month': month, 'days': days, 'bookmarks': []}

        day = int(parts[4])

        # Check if navigating to specific bookmark
        if len(parts) == 6 and parts[5].isdigit():
            bookmark_id = int(parts[5])
            bookmark = self.db.get(bookmark_id)
            if bookmark:
                return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

        # /by-date/added/2024/03/15 - show bookmarks from that day
        bookmarks = self._get_bookmarks_by_date(all_bookmarks, attr_name, year, month, day)
        return {
            'type': 'by_date_bookmarks',
            'field': field,
            'year': year,
            'month': month,
            'day': day,
            'bookmarks': bookmarks
        }

    def _get_date_groups(self, bookmarks, attr_name, granularity, year=None, month=None):
        """Get unique date groups from bookmarks."""
        groups = {}

        for b in bookmarks:
            date_val = getattr(b, attr_name)
            if not date_val:
                continue

            if year and date_val.year != year:
                continue
            if month and date_val.month != month:
                continue

            if granularity == 'year':
                key = date_val.year
            elif granularity == 'month':
                key = date_val.month
            else:  # day
                key = date_val.day

            if key not in groups:
                groups[key] = 0
            groups[key] += 1

        return groups

    def _get_bookmarks_by_date(self, bookmarks, attr_name, year, month, day):
        """Get bookmarks from a specific date."""
        result = []
        for b in bookmarks:
            date_val = getattr(b, attr_name)
            if not date_val:
                continue
            if date_val.year == year and date_val.month == month and date_val.day == day:
                result.append(b)
        return result

    def _get_media_context(self, parts):
        """Get context for /media navigation.

        Structure:
            /media                      - Show media subdirectories
            /media/videos               - Video bookmarks
            /media/audio                - Audio bookmarks
            /media/documents            - Document bookmarks (papers, PDFs)
            /media/by-source            - Show source platforms
            /media/by-source/youtube    - YouTube bookmarks
            /media/by-channel           - Show channels/authors
            /media/by-channel/<name>    - Bookmarks by author
        """
        all_bookmarks = self.db.list()
        media_bookmarks = [b for b in all_bookmarks if b.media_type is not None]

        if len(parts) == 1:
            # /media root - show subdirectories
            return {'type': 'media_root', 'bookmarks': media_bookmarks}

        subpath = parts[1]

        # Check if navigating to specific bookmark
        if subpath.isdigit():
            bookmark_id = int(subpath)
            bookmark = self.db.get(bookmark_id)
            if bookmark and bookmark.media_type:
                return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}

        # Media type filters
        if subpath == 'videos':
            bookmarks = [b for b in media_bookmarks if b.media_type == 'video']
            if len(parts) == 3 and parts[2].isdigit():
                bookmark_id = int(parts[2])
                bookmark = self.db.get(bookmark_id)
                if bookmark:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
            return {
                'type': 'smart_collection',
                'name': 'media/videos',
                'description': 'Video bookmarks',
                'bookmarks': bookmarks
            }

        elif subpath == 'audio':
            bookmarks = [b for b in media_bookmarks if b.media_type == 'audio']
            if len(parts) == 3 and parts[2].isdigit():
                bookmark_id = int(parts[2])
                bookmark = self.db.get(bookmark_id)
                if bookmark:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
            return {
                'type': 'smart_collection',
                'name': 'media/audio',
                'description': 'Audio bookmarks',
                'bookmarks': bookmarks
            }

        elif subpath == 'documents':
            bookmarks = [b for b in media_bookmarks if b.media_type == 'document']
            if len(parts) == 3 and parts[2].isdigit():
                bookmark_id = int(parts[2])
                bookmark = self.db.get(bookmark_id)
                if bookmark:
                    return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
            return {
                'type': 'smart_collection',
                'name': 'media/documents',
                'description': 'Document bookmarks (papers, PDFs)',
                'bookmarks': bookmarks
            }

        # Source-based navigation
        elif subpath == 'by-source':
            if len(parts) == 2:
                # Show available sources
                sources = {}
                for b in media_bookmarks:
                    if b.media_source:
                        sources[b.media_source] = sources.get(b.media_source, 0) + 1
                return {'type': 'media_sources', 'sources': sources, 'bookmarks': []}
            else:
                source = parts[2]
                bookmarks = [b for b in media_bookmarks if b.media_source == source]
                if len(parts) == 4 and parts[3].isdigit():
                    bookmark_id = int(parts[3])
                    bookmark = self.db.get(bookmark_id)
                    if bookmark:
                        return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
                return {
                    'type': 'smart_collection',
                    'name': f'media/by-source/{source}',
                    'description': f'{source.title()} bookmarks',
                    'bookmarks': bookmarks
                }

        # Channel/author-based navigation
        elif subpath == 'by-channel':
            if len(parts) == 2:
                # Show available channels
                channels = {}
                for b in media_bookmarks:
                    if b.author_name:
                        channels[b.author_name] = channels.get(b.author_name, 0) + 1
                return {'type': 'media_channels', 'channels': channels, 'bookmarks': []}
            else:
                channel = '/'.join(parts[2:])
                # Handle bookmark ID at end
                channel_parts = channel.split('/')
                if channel_parts[-1].isdigit():
                    bookmark_id = int(channel_parts[-1])
                    bookmark = self.db.get(bookmark_id)
                    if bookmark:
                        return {'type': 'bookmark', 'bookmark_id': bookmark_id, 'bookmark': bookmark}
                    channel = '/'.join(channel_parts[:-1])

                bookmarks = [b for b in media_bookmarks if b.author_name == channel]
                return {
                    'type': 'smart_collection',
                    'name': f'media/by-channel/{channel}',
                    'description': f'Content by {channel}',
                    'bookmarks': bookmarks
                }

        return {'type': 'unknown'}

    def _get_current_bookmark(self):
        """Get current bookmark from context (if in a bookmark context)."""
        ctx = self._get_context()
        if ctx['type'] == 'bookmark':
            return ctx['bookmark']
        return None

    # ===== Navigation Commands =====

    def do_ls(self, arg):
        """List contents of current directory.

        Usage:
            ls              List current directory
            ls -l           Long format
            ls <path>       List specific path
        """
        long_format = '-l' in arg
        path_arg = arg.replace('-l', '').strip()

        # Determine what path to list
        if path_arg:
            target_path = self._parse_path(path_arg)
        else:
            target_path = self.cwd

        # Get context for this path
        ctx = self._get_context_for_path(target_path)

        if ctx['type'] == 'root':
            self._ls_root(long_format)
        elif ctx['type'] == 'bookmarks':
            self._ls_bookmarks(ctx['bookmarks'], long_format)
        elif ctx['type'] == 'bookmark':
            self._ls_bookmark_fields(ctx['bookmark'])
        elif ctx['type'] == 'tags':
            if ctx['tag_path']:
                # In a tag directory - show bookmarks with that tag
                self._ls_tag_directory(ctx['tag_path'], ctx['bookmarks'], long_format)
            else:
                # /tags root - show all tag hierarchies
                self._ls_tags_root()
        elif ctx['type'] in ('starred', 'archived'):
            self._ls_bookmarks(ctx['bookmarks'], long_format, title=ctx['type'].capitalize())
        elif ctx['type'] == 'recent':
            # Show time period directories first, then recent bookmarks
            self._ls_recent_root()
            self.console.print("\n[bold cyan]Recently Visited Bookmarks:[/bold cyan]")
            # Show first 10 recently visited
            self._ls_bookmarks(ctx['bookmarks'][:10], long_format=False)
        elif ctx['type'] == 'smart_collection':
            # Smart collection - show filtered bookmarks
            title = f"{ctx['name'].capitalize()} ({ctx['description']})"
            self._ls_bookmarks(ctx['bookmarks'], long_format, title=title)
        elif ctx['type'] == 'recent_period':
            # Time period directory - show activity subdirectories
            self._ls_recent_period(ctx['period'])
        elif ctx['type'] == 'recent_activity':
            # Specific activity in a time period - show bookmarks
            title = f"{ctx['period'].capitalize()} - {ctx['activity'].capitalize()}"
            self._ls_bookmarks(ctx['bookmarks'], long_format, title=title)
        elif ctx['type'] == 'domains':
            self._ls_domains()
        elif ctx['type'] == 'domain':
            self._ls_bookmarks(ctx['bookmarks'], long_format, title=f"Domain: {ctx['domain']}")
        elif ctx['type'] == 'by_date_root':
            self._ls_by_date_root()
        elif ctx['type'] == 'by_date_years':
            self._ls_by_date_years(ctx['field'], ctx['years'])
        elif ctx['type'] == 'by_date_months':
            self._ls_by_date_months(ctx['field'], ctx['year'], ctx['months'])
        elif ctx['type'] == 'by_date_days':
            self._ls_by_date_days(ctx['field'], ctx['year'], ctx['month'], ctx['days'])
        elif ctx['type'] == 'by_date_bookmarks':
            months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            title = f"{ctx['field'].capitalize()}: {months[ctx['month']]} {ctx['day']}, {ctx['year']}"
            self._ls_bookmarks(ctx['bookmarks'], long_format, title=title)
        elif ctx['type'] == 'media_root':
            self._ls_media_root()
        elif ctx['type'] == 'media_sources':
            self._ls_media_sources(ctx['sources'])
        elif ctx['type'] == 'media_channels':
            self._ls_media_channels(ctx['channels'])
        else:
            self.console.print(f"[red]Unknown path: {target_path}[/red]")

    def _ls_root(self, long_format=False):
        """List root directory - shows virtual folders with counts."""
        all_bookmarks = self.db.list()

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Directory", style="cyan")
        table.add_column("Count", style="dim", justify="right")
        table.add_column("Description", style="dim")

        # Core directories
        table.add_row("bookmarks/", f"({len(all_bookmarks)})", "All bookmarks")
        table.add_row("tags/", "", "Browse by tag hierarchy")

        # Special collections
        starred_count = len([b for b in all_bookmarks if b.stars])
        table.add_row("starred/", f"({starred_count})", "Starred bookmarks")

        archived_count = len([b for b in all_bookmarks if b.archived])
        table.add_row("archived/", f"({archived_count})", "Archived bookmarks")

        table.add_row("recent/", "", "Recently active (time-based)")
        table.add_row("by-date/", "", "Browse by date (year/month/day)")
        table.add_row("domains/", "", "Browse by domain")

        # Smart collections
        for name, collection in sorted(SMART_COLLECTIONS.items()):
            filtered = collection.filter_func(all_bookmarks)
            table.add_row(f"{name}/", f"({len(filtered)})", collection.description)

        self.console.print(table)

    def _ls_recent_root(self):
        """Display time period subdirectories at /recent."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Period", style="cyan")
        table.add_column("Description", style="dim")

        table.add_row("today/", "Activity from today")
        table.add_row("yesterday/", "Activity from yesterday")
        table.add_row("this-week/", "Activity from this week")
        table.add_row("last-week/", "Activity from last week")
        table.add_row("this-month/", "Activity from this month")
        table.add_row("last-month/", "Activity from last month")

        self.console.print(table)
        self.console.print("\n[dim]Tip: cd into a period to see activity types (visited/added/starred)[/dim]")

    def _ls_recent_period(self, period: str):
        """Display activity subdirectories for a time period."""
        time_ranges = get_time_ranges()
        if period not in time_ranges:
            self.console.print(f"[red]Unknown time period: {period}[/red]")
            return

        start_time, end_time = time_ranges[period]
        all_bookmarks = self.db.list()

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Activity", style="cyan")
        table.add_column("Count", style="dim", justify="right")

        for activity in ['visited', 'added', 'starred']:
            filtered = filter_by_activity(all_bookmarks, activity, start_time, end_time)
            table.add_row(f"{activity}/", f"({len(filtered)})")

        self.console.print(table)

    def _ls_tags_root(self):
        """List all tags in hierarchical view."""
        tags = self._get_all_tags()

        # Group tags by hierarchy
        root_tags = {}
        for tag in tags:
            if '/' in tag:
                prefix = tag.split('/')[0]
                if prefix not in root_tags:
                    root_tags[prefix] = []
                root_tags[prefix].append(tag)
            else:
                if tag not in root_tags:
                    root_tags[tag] = []

        self.console.print("[bold cyan]Tags:[/bold cyan]")
        for tag in sorted(root_tags.keys()):
            subtags = root_tags[tag]
            if subtags:
                self.console.print(f"  [blue]{tag}/[/blue]  ({len(subtags)} subtags)")
            else:
                self.console.print(f"  [yellow]{tag}[/yellow]")

    def _ls_tag_directory(self, tag_path, bookmarks, long_format=False):
        """List a tag directory - shows subtags and bookmarks."""
        # Get subtags
        all_tags = self._get_all_tags()
        subtags = set()
        for tag in all_tags:
            if tag.startswith(tag_path + '/'):
                remainder = tag[len(tag_path)+1:]
                if '/' in remainder:
                    subtags.add(remainder.split('/')[0])
                else:
                    subtags.add(remainder)

        if subtags:
            self.console.print(f"[bold cyan]Subtags in {tag_path}:[/bold cyan]")
            for subtag in sorted(subtags):
                self.console.print(f"  [blue]{subtag}/[/blue]")
            self.console.print()

        if bookmarks:
            self.console.print(f"[bold cyan]Bookmarks tagged with '{tag_path}':[/bold cyan]")
            self._ls_bookmarks(bookmarks, long_format)

    def _ls_domains(self):
        """List all domains."""
        domains = self._get_all_domains()
        self.console.print(f"[bold cyan]Domains ({len(domains)}):[/bold cyan]")
        for domain in domains:
            count = len(self._get_bookmarks_by_domain(domain))
            self.console.print(f"  [blue]{domain}/[/blue]  ({count} bookmarks)")

    def _ls_by_date_root(self):
        """List date field options at /by-date."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="cyan")
        table.add_column("Description", style="dim")

        table.add_row("added/", "Browse by date added")
        table.add_row("visited/", "Browse by last visited date")

        self.console.print("[bold cyan]Browse by Date:[/bold cyan]")
        self.console.print(table)
        self.console.print("\n[dim]Tip: cd into a field to see available years[/dim]")

    def _ls_by_date_years(self, field: str, years: dict):
        """List years for a date field."""
        self.console.print(f"[bold cyan]Years ({field}):[/bold cyan]")

        if not years:
            self.console.print("[yellow]No bookmarks with dates[/yellow]")
            return

        for year in sorted(years.keys(), reverse=True):
            count = years[year]
            self.console.print(f"  [blue]{year}/[/blue]  ({count} bookmarks)")

    def _ls_by_date_months(self, field: str, year: int, months: dict):
        """List months for a year."""
        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        self.console.print(f"[bold cyan]{year} ({field}):[/bold cyan]")

        if not months:
            self.console.print("[yellow]No bookmarks in this year[/yellow]")
            return

        for month in sorted(months.keys(), reverse=True):
            count = months[month]
            month_str = f"{month:02d}"
            self.console.print(f"  [blue]{month_str}/[/blue]  {month_names[month]}  ({count} bookmarks)")

    def _ls_by_date_days(self, field: str, year: int, month: int, days: dict):
        """List days for a month."""
        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        self.console.print(f"[bold cyan]{month_names[month]} {year} ({field}):[/bold cyan]")

        if not days:
            self.console.print("[yellow]No bookmarks in this month[/yellow]")
            return

        for day in sorted(days.keys(), reverse=True):
            count = days[day]
            day_str = f"{day:02d}"
            self.console.print(f"  [blue]{day_str}/[/blue]  ({count} bookmarks)")

    def _ls_bookmarks(self, bookmarks, long_format=False, title=None):
        """List bookmarks in various formats."""
        if not bookmarks:
            self.console.print("[yellow]No bookmarks[/yellow]")
            return

        if title:
            self.console.print(f"[bold cyan]{title} ({len(bookmarks)}):[/bold cyan]")

        if long_format:
            table = Table()
            table.add_column("ID", style="cyan")
            table.add_column("Title", style="white")
            table.add_column("URL", style="blue", max_width=40)
            table.add_column("Tags", style="green")
            table.add_column("★", style="yellow")

            for b in bookmarks[:50]:
                table.add_row(
                    str(b.id),
                    b.title[:40],
                    b.url[:40],
                    ", ".join(t.name for t in b.tags[:2]),
                    "★" if b.stars else ""
                )
            self.console.print(table)
        else:
            for b in bookmarks[:50]:
                star = "★ " if b.stars else "  "
                self.console.print(f"{star}[cyan]{b.id:5d}[/cyan]  {b.title[:60]}")

        if len(bookmarks) > 50:
            self.console.print(f"[dim]... and {len(bookmarks) - 50} more[/dim]")

    def _ls_bookmark_fields(self, bookmark):
        """List fields of a specific bookmark."""
        if not bookmark:
            self.console.print("[red]Bookmark not found[/red]")
            return

        table = Table(title=f"Bookmark: {bookmark.title}", box=box.SIMPLE)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        fields = {
            'id': str(bookmark.id),
            'url': bookmark.url,
            'title': bookmark.title,
            'description': bookmark.description or '',
            'tags': ', '.join(t.name for t in bookmark.tags),
            'stars': '★' if bookmark.stars else '',
            'visits': str(bookmark.visit_count),
            'added': str(bookmark.added) if bookmark.added else '',
        }

        for field, value in fields.items():
            table.add_row(field, value[:80])

        self.console.print(table)

    def _ls_media_root(self):
        """Display /media subdirectories with counts."""
        all_bms = self.db.list()

        # Count by type
        videos = [b for b in all_bms if b.media_type == 'video']
        audio = [b for b in all_bms if b.media_type == 'audio']
        documents = [b for b in all_bms if b.media_type == 'document']
        images = [b for b in all_bms if b.media_type == 'image']
        code = [b for b in all_bms if b.media_type == 'code']

        # Count sources
        sources = {}
        for b in all_bms:
            if b.media_source:
                sources[b.media_source] = sources.get(b.media_source, 0) + 1

        # Count channels
        channels = set()
        for b in all_bms:
            if b.author_name:
                channels.add(b.author_name)

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Dir", style="cyan")
        table.add_column("Count", style="dim", justify="right")
        table.add_column("Description", style="dim")

        # Media type directories
        table.add_row("videos/", f"({len(videos)})", "Video content")
        table.add_row("audio/", f"({len(audio)})", "Audio content")
        table.add_row("documents/", f"({len(documents)})", "Documents & papers")
        if images:
            table.add_row("images/", f"({len(images)})", "Image content")
        if code:
            table.add_row("code/", f"({len(code)})", "Code repositories")

        # Grouping directories
        table.add_row("by-source/", f"({len(sources)})", "Grouped by platform")
        table.add_row("by-channel/", f"({len(channels)})", "Grouped by creator")

        self.console.print(table)

    def _ls_media_sources(self, sources: dict):
        """Display available media sources."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Source", style="cyan")
        table.add_column("Count", style="dim", justify="right")

        for source, count in sorted(sources.items(), key=lambda x: -x[1]):
            table.add_row(f"{source}/", f"({count})")

        self.console.print(table)

    def _ls_media_channels(self, channels: dict):
        """Display channels with bookmark counts."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Channel", style="cyan")
        table.add_column("Count", style="dim", justify="right")

        # Sort by count, then name
        sorted_channels = sorted(channels.items(), key=lambda x: (-x[1], x[0]))
        for channel, count in sorted_channels[:50]:
            # Truncate long channel names
            display_name = channel[:40] + "..." if len(channel) > 43 else channel
            table.add_row(f"{display_name}/", f"({count})")

        if len(channels) > 50:
            self.console.print(f"[dim]... and {len(channels) - 50} more channels[/dim]")

        self.console.print(table)

    def do_cd(self, arg):
        """Change directory.

        Usage:
            cd <path>       Change to path
            cd ..           Go up one level
            cd /            Go to root
            cd bookmarks    Go to /bookmarks
            cd tags/python  Go to /tags/python
        """
        if not arg or arg == '/':
            self.cwd = '/'
        else:
            # Parse and normalize the path
            new_path = self._parse_path(arg)

            # Validate the path exists
            ctx = self._get_context_for_path(new_path)
            if ctx['type'] == 'unknown':
                self.console.print(f"[red]Path not found: {new_path}[/red]")
                return
            elif ctx['type'] == 'bookmark' and ctx['bookmark'] is None:
                self.console.print("[red]Bookmark not found[/red]")
                return

            self.cwd = new_path

        self.update_prompt()

    def do_pwd(self, arg):
        """Print working directory."""
        self.console.print(self.cwd)

    # ===== Viewing Commands =====

    def do_cat(self, arg):
        """Display bookmark field.

        Usage:
            cat url             Show URL of current bookmark
            cat title           Show title of current bookmark
            cat tags            Show tags of current bookmark
            cat description     Show description
            cat all             Show all fields
            cat <id>/url        Show URL of bookmark <id>
            cat <id>/title      Show title of bookmark <id>
            cat <id>/<field>    Show any field of bookmark <id>
        """
        # Handle path-like syntax: <id>/<field>
        if '/' in arg:
            parts = arg.split('/', 1)
            if parts[0].isdigit() and len(parts) == 2:
                bookmark_id = int(parts[0])
                field = parts[1]
                bookmark = self.db.get(bookmark_id)
                if not bookmark:
                    self.console.print(f"[red]Bookmark {bookmark_id} not found[/red]")
                    return
                self._cat_field(field, bookmark)
                return
            else:
                self.console.print("[red]Invalid path syntax. Use: cat <id>/<field>[/red]")
                return

        bookmark = self._get_current_bookmark()
        if not bookmark:
            self.console.print("[red]Not in a bookmark context. Use 'cd bookmarks/<id>' first.[/red]")
            return

        self._cat_field(arg, bookmark)

    def _cat_field(self, arg, bookmark):
        """Display a field of a bookmark."""
        b = bookmark

        if not arg or arg == 'all':
            # Show all fields
            panel = Panel(
                f"""[bold]Title:[/bold] {b.title}
[bold]URL:[/bold] {b.url}
[bold]Description:[/bold] {b.description or '[dim]none[/dim]'}
[bold]Tags:[/bold] {', '.join(t.name for t in b.tags) or '[dim]none[/dim]'}
[bold]Stars:[/bold] {'★' if b.stars else '[dim]none[/dim]'}
[bold]Visits:[/bold] {b.visit_count}
[bold]Added:[/bold] {b.added}
[bold]Last Visited:[/bold] {b.last_visited or '[dim]never[/dim]'}
[bold]Pinned:[/bold] {b.pinned}
[bold]Archived:[/bold] {b.archived}""",
                title=f"Bookmark {b.id}",
                border_style="cyan"
            )
            self.console.print(panel)
        elif arg == 'id':
            self.console.print(str(b.id))
        elif arg == 'url':
            self.console.print(b.url)
        elif arg == 'title':
            self.console.print(b.title)
        elif arg == 'tags':
            for tag in b.tags:
                self.console.print(tag.name)
        elif arg == 'description':
            self.console.print(b.description or "[dim]No description[/dim]")
        elif arg == 'stars':
            self.console.print('★' if b.stars else "[dim]Not starred[/dim]")
        elif arg == 'visits' or arg == 'visit_count':
            self.console.print(str(b.visit_count))
        elif arg == 'added':
            self.console.print(str(b.added) if b.added else "[dim]unknown[/dim]")
        elif arg == 'pinned':
            self.console.print('yes' if b.pinned else 'no')
        elif arg == 'archived':
            self.console.print('yes' if b.archived else 'no')
        elif arg == 'reachable':
            self.console.print(str(b.reachable) if b.reachable is not None else 'unknown')
        else:
            self.console.print(f"[red]Unknown field: {arg}[/red]")
            self.console.print("[dim]Available: id, url, title, tags, description, stars, visits, added, pinned, archived, reachable, all[/dim]")

    def do_file(self, arg):
        """Show bookmark type and metadata summary.

        Usage:
            file            Show info for current bookmark
            file .          Show info for current bookmark
            file <id>       Show info for bookmark <id>
        """
        # Handle relative paths and IDs
        if arg.strip() == '.':
            bookmark = self._get_current_bookmark()
            if not bookmark:
                self.console.print("[red]Not in a bookmark context[/red]")
                return
        elif arg.strip() and arg.strip().isdigit():
            bookmark_id = int(arg.strip())
            bookmark = self.db.get(bookmark_id)
            if not bookmark:
                self.console.print(f"[red]Bookmark {bookmark_id} not found[/red]")
                return
        else:
            bookmark = self._get_current_bookmark()
            if not bookmark:
                self.console.print("[red]Not in a bookmark context. Use 'cd bookmarks/<id>' or 'file <id>'[/red]")
                return

        # Determine type
        import urllib.parse
        parsed = urllib.parse.urlparse(bookmark.url)
        domain = parsed.netloc

        file_info = f"{bookmark.title}: BTK Bookmark"
        file_info += f"\n  Domain: {domain}"
        file_info += f"\n  Tags: {len(bookmark.tags)}"
        file_info += f"\n  Stars: {bookmark.stars}"
        file_info += f"\n  Visits: {bookmark.visit_count}"
        if bookmark.added:
            # Handle both timezone-aware and naive datetimes
            now = datetime.now(timezone.utc) if bookmark.added.tzinfo else datetime.now()
            age_days = (now - bookmark.added).days
            file_info += f"\n  Age: {age_days} days"

        self.console.print(file_info)

    def do_stat(self, arg):
        """Show detailed statistics.

        Usage:
            stat            Show collection stats (at root) or bookmark stats (in bookmark)
            stat .          Show current bookmark stats
            stat ..         Show collection stats (from bookmark context)
            stat <id>       Show stats for specific bookmark
        """
        # Handle relative paths
        if arg.strip() == '.':
            bookmark = self._get_current_bookmark()
            if bookmark:
                self._show_bookmark_stats(bookmark)
            else:
                self._show_collection_stats()
            return
        elif arg.strip() == '..':
            # Always show collection stats when using ..
            self._show_collection_stats()
            return

        # Handle stat <id>
        if arg.strip() and arg.strip().isdigit():
            bookmark_id = int(arg.strip())
            bookmark = self.db.get(bookmark_id)
            if bookmark:
                self._show_bookmark_stats(bookmark)
            else:
                self.console.print(f"[red]Bookmark {bookmark_id} not found[/red]")
            return

        bookmark = self._get_current_bookmark()
        if not bookmark:
            # Show collection stats
            self._show_collection_stats()
        else:
            # Show bookmark stats
            self._show_bookmark_stats(bookmark)

    def _show_collection_stats(self):
        """Show statistics for entire bookmark collection."""
        from btk.models import Tag

        with self.db.session() as session:
            # Get all bookmarks
            bookmarks = self.db.list()

            if not bookmarks:
                self.console.print("[yellow]No bookmarks in collection[/yellow]")
                return

            # Calculate stats
            total = len(bookmarks)
            starred = sum(1 for b in bookmarks if b.stars)
            archived = sum(1 for b in bookmarks if b.archived)
            pinned = sum(1 for b in bookmarks if b.pinned)
            total_visits = sum(b.visit_count for b in bookmarks)

            # Tag stats
            all_tags = session.query(Tag).all()
            tag_count = len(all_tags)

            # Domain stats
            domains = {}
            for b in bookmarks:
                from urllib.parse import urlparse
                domain = urlparse(b.url).netloc
                domains[domain] = domains.get(domain, 0) + 1
            top_domain = max(domains.items(), key=lambda x: x[1]) if domains else None

            # Date stats
            oldest = min(bookmarks, key=lambda b: b.added if b.added else datetime.max)
            newest = max(bookmarks, key=lambda b: b.added if b.added else datetime.min)

            table = Table(title="📚 Bookmark Collection Statistics", box=box.ROUNDED)
            table.add_column("Metric", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            table.add_row("Total Bookmarks", str(total))
            table.add_row("Starred", f"{starred} ({starred*100//total if total else 0}%)")
            table.add_row("Archived", f"{archived} ({archived*100//total if total else 0}%)")
            table.add_row("Pinned", f"{pinned}")
            table.add_row("Total Visits", str(total_visits))
            table.add_row("Avg Visits/Bookmark", f"{total_visits/total:.1f}" if total else "0")
            table.add_row("", "")
            table.add_row("Total Tags", str(tag_count))
            table.add_row("Avg Tags/Bookmark", f"{sum(len(b.tags) for b in bookmarks)/total:.1f}" if total else "0")
            table.add_row("", "")
            table.add_row("Unique Domains", str(len(domains)))
            if top_domain:
                table.add_row("Top Domain", f"{top_domain[0]} ({top_domain[1]} bookmarks)")
            table.add_row("", "")
            if oldest.added:
                table.add_row("Oldest Bookmark", f"{oldest.title[:30]} ({oldest.added.strftime('%Y-%m-%d')})")
            if newest.added:
                table.add_row("Newest Bookmark", f"{newest.title[:30]} ({newest.added.strftime('%Y-%m-%d')})")

            self.console.print(table)

    def _show_bookmark_stats(self, b):
        """Show statistics for a specific bookmark."""
        table = Table(title=f"Statistics for Bookmark {b.id}", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("ID", str(b.id))
        table.add_row("Title Length", f"{len(b.title)} characters")
        table.add_row("URL Length", f"{len(b.url)} characters")
        table.add_row("Description Length", f"{len(b.description or '')} characters")
        table.add_row("Tag Count", str(len(b.tags)))
        table.add_row("Stars", str(b.stars))
        table.add_row("Visit Count", str(b.visit_count))

        if b.added:
            # Handle both timezone-aware and naive datetimes
            now = datetime.now(timezone.utc) if b.added.tzinfo else datetime.now()
            age = (now - b.added).days
            table.add_row("Age", f"{age} days")

        if b.last_visited:
            last_visit = (datetime.now() - b.last_visited).days
            table.add_row("Days Since Visit", str(last_visit))

        table.add_row("Pinned", "Yes" if b.pinned else "No")
        table.add_row("Archived", "Yes" if b.archived else "No")

        self.console.print(table)

    # ===== Operations Commands =====

    def do_star(self, arg):
        """Toggle star on bookmark.

        Usage:
            star                Toggle star on current bookmark
            star on             Set star on current bookmark
            star off            Remove star from current bookmark
            star <id>           Toggle star on bookmark <id>
            star <id> on        Set star on bookmark <id>
            star <id> off       Remove star from bookmark <id>
        """
        # Parse arguments: can be "<id> <on/off>" or just "<on/off>" or just "<id>"
        parts = arg.split() if arg else []
        bookmark_id = None
        action = None

        if len(parts) == 2 and parts[0].isdigit():
            # star <id> <on/off>
            bookmark_id = int(parts[0])
            action = parts[1].lower()
        elif len(parts) == 1:
            if parts[0].isdigit():
                # star <id> (toggle)
                bookmark_id = int(parts[0])
            else:
                # star <on/off>
                action = parts[0].lower()
        elif len(parts) == 0:
            # star (toggle current)
            pass
        else:
            self.console.print("[red]Invalid syntax. Use: star [<id>] [on|off][/red]")
            return

        # Get the bookmark to operate on
        if bookmark_id is not None:
            bookmark = self.db.get(bookmark_id)
            if not bookmark:
                self.console.print(f"[red]Bookmark {bookmark_id} not found[/red]")
                return
        else:
            bookmark = self._get_current_bookmark()
            if not bookmark:
                self.console.print("[red]Not in a bookmark context. Use 'cd bookmarks/<id>' or 'star <id>'[/red]")
                return
            bookmark_id = bookmark.id

        # Determine new star value
        if action:
            if action in ('on', '1', 'true', 'yes'):
                new_stars = True
            elif action in ('off', '0', 'false', 'no'):
                new_stars = False
            else:
                self.console.print("[red]Invalid argument. Use 'on' or 'off'.[/red]")
                return
        else:
            # Toggle
            new_stars = not bookmark.stars

        # Update the bookmark
        self.db.update(bookmark_id, stars=new_stars)

        status = '★' if new_stars else '☆'
        self.console.print(f"[green]Star set to: {status} (bookmark {bookmark_id})[/green]")

    def do_tag(self, arg):
        """Add tags to bookmark.

        Usage:
            tag python,web          Add tags to current bookmark
            tag <id> python,web     Add tags to bookmark <id>
        """
        if not arg:
            self.console.print("[red]Please specify tags to add[/red]")
            self.console.print("[dim]Usage: tag [<id>] <tag1>,<tag2>,...[/dim]")
            return

        # Parse arguments: "id tags" or just "tags"
        parts = arg.split(None, 1)  # Split on first whitespace
        bookmark_id = None
        tags_str = None

        if len(parts) == 2 and parts[0].isdigit():
            # tag <id> <tags>
            bookmark_id = int(parts[0])
            tags_str = parts[1]
        elif len(parts) == 1:
            if parts[0].isdigit() and ',' not in parts[0]:
                # Just an ID with no tags - error
                self.console.print("[red]Please specify tags to add[/red]")
                self.console.print(f"[dim]Usage: tag {parts[0]} <tag1>,<tag2>,...[/dim]")
                return
            else:
                # Just tags, use current bookmark
                tags_str = parts[0]
        else:
            self.console.print("[red]Invalid syntax[/red]")
            self.console.print("[dim]Usage: tag [<id>] <tag1>,<tag2>,...[/dim]")
            return

        # Get the bookmark to operate on
        if bookmark_id is not None:
            bookmark = self.db.get(bookmark_id)
            if not bookmark:
                self.console.print(f"[red]Bookmark {bookmark_id} not found[/red]")
                return
        else:
            bookmark = self._get_current_bookmark()
            if not bookmark:
                self.console.print("[red]Not in a bookmark context. Use 'cd bookmarks/<id>' or 'tag <id> <tags>'[/red]")
                return
            bookmark_id = bookmark.id

        tags = [t.strip() for t in tags_str.split(',')]

        from btk.models import Tag
        with self.db.session() as session:
            # Get fresh bookmark from session
            bookmark_to_update = session.get(type(bookmark), bookmark_id)
            for tag_name in tags:
                # Check if tag exists
                tag = session.query(Tag).filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    session.add(tag)

                if tag not in bookmark_to_update.tags:
                    bookmark_to_update.tags.append(tag)

            session.commit()

        self.console.print(f"[green]✓ Tags added to bookmark {bookmark_id}: {', '.join(tags)}[/green]")

    # ===== Search Commands =====

    def do_find(self, arg):
        """Search bookmarks.

        Usage:
            find python         Search for 'python'
            find "rust lang"    Search for phrase
        """
        if not arg:
            self.console.print("[red]Please specify search query[/red]")
            return

        results = self.db.search(arg)

        if not results:
            self.console.print(f"[yellow]No bookmarks found for: {arg}[/yellow]")
            return

        self.console.print(f"\n[bold]Found {len(results)} bookmarks:[/bold]\n")

        for b in results[:20]:
            star = "★ " if b.stars else "  "
            tags = f"[{', '.join(t.name for t in b.tags[:2])}]" if b.tags else ""
            self.console.print(f"{star}[cyan]{b.id:3d}[/cyan]  {b.title[:50]:<50}  [dim]{tags}[/dim]")

        if len(results) > 20:
            self.console.print(f"\n[dim]... and {len(results) - 20} more[/dim]")

    def do_which(self, arg):
        """Find bookmark by ID.

        Usage:
            which 42        Find bookmark 42
        """
        if not arg:
            self.console.print("[red]Please specify bookmark ID[/red]")
            return

        try:
            bookmark_id = int(arg)
            bookmark = self.db.get(bookmark_id)
            if bookmark:
                self.console.print(f"[cyan]{bookmark.id}[/cyan]: {bookmark.title}")
                self.console.print(f"  URL: {bookmark.url}")
                self.console.print(f"  Tags: {', '.join(t.name for t in bookmark.tags)}")
            else:
                self.console.print(f"[yellow]Bookmark {bookmark_id} not found[/yellow]")
        except ValueError:
            self.console.print(f"[red]Invalid bookmark ID: {arg}[/red]")

    # ===== Utility Commands =====

    def do_top(self, arg):
        """Show top bookmarks by various metrics.

        Usage:
            top             Show recently added bookmarks (default 10)
            top 20          Show top 20 recent bookmarks
            top visits      Show most visited bookmarks
            top starred     Show starred bookmarks
        """
        limit = 10
        sort_by = 'recent'

        if arg.strip():
            parts = arg.strip().split()
            if parts[0].isdigit():
                limit = int(parts[0])
                if len(parts) > 1:
                    sort_by = parts[1]
            else:
                sort_by = parts[0]
                if len(parts) > 1 and parts[1].isdigit():
                    limit = int(parts[1])

        bookmarks = self.db.list()

        if sort_by == 'visits':
            bookmarks.sort(key=lambda b: b.visit_count, reverse=True)
            title = f"Top {limit} Most Visited Bookmarks"
        elif sort_by == 'starred':
            bookmarks = [b for b in bookmarks if b.stars]
            # Sort by ID descending (most recently starred appear first)
            bookmarks.sort(key=lambda b: b.id, reverse=True)
            title = f"Starred Bookmarks (showing {min(limit, len(bookmarks))})"
        else:  # recent
            bookmarks.sort(key=lambda b: b.added if b.added else datetime.min, reverse=True)
            title = f"Top {limit} Recently Added Bookmarks"

        bookmarks = bookmarks[:limit]

        if not bookmarks:
            self.console.print("[yellow]No bookmarks found[/yellow]")
            return

        table = Table(title=title, box=box.ROUNDED)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Tags", style="yellow")
        table.add_column("★", style="green", justify="center")
        table.add_column("Visits", style="blue", justify="right")
        table.add_column("Added", style="dim")

        for b in bookmarks:
            table.add_row(
                str(b.id),
                b.title[:40],
                ", ".join(t.name for t in b.tags[:3]),
                "★" if b.stars else "",
                str(b.visit_count),
                b.added.strftime("%Y-%m-%d") if b.added else ""
            )

        self.console.print(table)

    def do_recent(self, arg):
        """Show recently active bookmarks (context-aware).

        Usage:
            recent              Show recently visited bookmarks in current context (default 10)
            recent 20           Show 20 recently visited bookmarks
            recent visited      Show recently visited bookmarks
            recent added        Show recently added bookmarks
            recent starred      Show recently starred bookmarks
        """
        limit = 10
        sort_by = 'visited'  # Default to visited for "activity"

        if arg.strip():
            parts = arg.strip().split()
            if parts[0].isdigit():
                limit = int(parts[0])
                if len(parts) > 1:
                    sort_by = parts[1]
            else:
                sort_by = parts[0]
                if len(parts) > 1 and parts[1].isdigit():
                    limit = int(parts[1])

        # Get bookmarks from current context
        ctx = self._get_context()
        if ctx['bookmarks']:
            bookmarks = ctx['bookmarks']
            context_name = ctx.get('type', 'current')
        else:
            bookmarks = self.db.list()
            context_name = 'all'

        if sort_by == 'visited':
            # Filter only bookmarks that have been visited
            bookmarks = [b for b in bookmarks if b.last_visited]
            bookmarks.sort(key=lambda b: b.last_visited, reverse=True)
            title = f"Recently Visited Bookmarks ({context_name})"
        elif sort_by == 'added':
            bookmarks.sort(key=lambda b: b.added if b.added else datetime.min, reverse=True)
            title = f"Recently Added Bookmarks ({context_name})"
        elif sort_by == 'starred':
            bookmarks = [b for b in bookmarks if b.stars]
            bookmarks.sort(key=lambda b: b.id, reverse=True)
            title = f"Recently Starred Bookmarks ({context_name})"
        else:
            self.console.print(f"[red]Unknown sort option: {sort_by}[/red]")
            self.console.print("[dim]Available: visited, added, starred[/dim]")
            return

        bookmarks = bookmarks[:limit]

        if not bookmarks:
            self.console.print(f"[yellow]No bookmarks found for '{sort_by}'[/yellow]")
            return

        table = Table(title=title, box=box.ROUNDED)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Tags", style="yellow")
        table.add_column("★", style="green", justify="center")
        table.add_column("Visits", style="blue", justify="right")

        if sort_by == 'visited':
            table.add_column("Last Visited", style="dim")
        else:
            table.add_column("Added", style="dim")

        for b in bookmarks:
            date_str = ""
            if sort_by == 'visited' and b.last_visited:
                date_str = b.last_visited.strftime("%Y-%m-%d %H:%M")
            elif b.added:
                date_str = b.added.strftime("%Y-%m-%d")

            table.add_row(
                str(b.id),
                b.title[:30],
                ", ".join(t.name for t in b.tags[:2]),
                "★" if b.stars else "",
                str(b.visit_count),
                date_str
            )

        self.console.print(table)

    def do_mv(self, arg):
        """Rename/move tags (Unix mv-like for tag management).

        Usage:
            mv <old_tag> <new_tag>              Rename a tag
            mv programming/python python        Move tag to new hierarchy
            mv video/tutorial tutorials/video   Reorganize tag hierarchy

        This renames a tag across all bookmarks that have it.
        For hierarchical tags, all subtags are automatically updated.
        """
        if not arg:
            self.console.print("[red]Usage: mv <old_tag> <new_tag>[/red]")
            return

        parts = arg.split(None, 1)
        if len(parts) != 2:
            self.console.print("[red]Usage: mv <old_tag> <new_tag>[/red]")
            return

        old_tag = parts[0].strip()
        new_tag = parts[1].strip()

        if old_tag == new_tag:
            self.console.print("[yellow]Tags are the same, nothing to do[/yellow]")
            return

        # Get all bookmarks with the old tag
        all_bookmarks = self.db.list()
        affected_bookmarks = []

        for b in all_bookmarks:
            for tag in b.tags:
                if tag.name == old_tag:
                    affected_bookmarks.append(b)
                    break

        if not affected_bookmarks:
            self.console.print(f"[yellow]No bookmarks found with tag '{old_tag}'[/yellow]")
            return

        # Confirm the operation
        self.console.print(f"[yellow]This will rename tag '{old_tag}' to '{new_tag}' on {len(affected_bookmarks)} bookmark(s)[/yellow]")
        confirm = input("Continue? (y/N): ").strip().lower()

        if confirm != 'y':
            self.console.print("[dim]Cancelled[/dim]")
            return

        # Perform the rename
        from btk.models import Tag, Bookmark
        renamed_count = 0

        with self.db.session() as session:
            # Get or create the new tag ONCE before the loop
            new_tag_obj = session.query(Tag).filter_by(name=new_tag).first()
            if not new_tag_obj:
                new_tag_obj = Tag(name=new_tag)
                session.add(new_tag_obj)
                session.flush()  # Ensure it's created before we use it

            for bookmark in affected_bookmarks:
                # Reload bookmark in this session
                bookmark_in_session = session.get(Bookmark, bookmark.id)

                # Find and update the tag
                for tag in bookmark_in_session.tags:
                    if tag.name == old_tag:
                        # Remove old tag
                        bookmark_in_session.tags.remove(tag)

                        # Add new tag if not already present
                        if new_tag_obj not in bookmark_in_session.tags:
                            bookmark_in_session.tags.append(new_tag_obj)

                        renamed_count += 1
                        break

            session.commit()

        # Clean up orphaned tags
        with self.db.session() as session:
            orphan_tag = session.query(Tag).filter_by(name=old_tag).first()
            if orphan_tag:
                # Check if it has any bookmarks
                bookmark_count = session.query(Bookmark).join(Bookmark.tags).filter(Tag.name == old_tag).count()
                if bookmark_count == 0:
                    session.delete(orphan_tag)
                    session.commit()

        self.console.print(f"[green]✓ Renamed tag '{old_tag}' to '{new_tag}' on {renamed_count} bookmark(s)[/green]")

    def do_cp(self, arg):
        """Copy tags to bookmarks (Unix cp-like for tag management).

        Usage:
            cp <tag> <bookmark_id>              Copy tag to a specific bookmark
            cp <tag> .                          Copy tag to current bookmark
            cp <tag> *                          Copy tag to all bookmarks in current context

        This adds a tag to bookmark(s) without removing existing tags.
        """
        if not arg:
            self.console.print("[red]Usage: cp <tag> <target>[/red]")
            self.console.print("[dim]Target can be: <id>, '.', or '*'[/dim]")
            return

        parts = arg.split(None, 1)
        if len(parts) != 2:
            self.console.print("[red]Usage: cp <tag> <target>[/red]")
            return

        tag_name = parts[0].strip()
        target = parts[1].strip()

        # Determine target bookmarks
        target_bookmarks = []

        if target == '.':
            # Current bookmark
            bookmark = self._get_current_bookmark()
            if not bookmark:
                self.console.print("[red]Not in a bookmark context[/red]")
                return
            target_bookmarks = [bookmark]

        elif target == '*':
            # All bookmarks in current context
            ctx = self._get_context()
            if ctx['bookmarks']:
                target_bookmarks = ctx['bookmarks']
            else:
                self.console.print("[yellow]No bookmarks in current context[/yellow]")
                return

        elif target.isdigit():
            # Specific bookmark ID
            bookmark_id = int(target)
            bookmark = self.db.get(bookmark_id)
            if not bookmark:
                self.console.print(f"[red]Bookmark {bookmark_id} not found[/red]")
                return
            target_bookmarks = [bookmark]

        else:
            self.console.print(f"[red]Invalid target: {target}[/red]")
            self.console.print("[dim]Target must be: <id>, '.', or '*'[/dim]")
            return

        # Filter bookmarks that don't already have the tag
        bookmarks_to_update = []
        for b in target_bookmarks:
            has_tag = any(t.name == tag_name for t in b.tags)
            if not has_tag:
                bookmarks_to_update.append(b)

        if not bookmarks_to_update:
            self.console.print(f"[yellow]All target bookmarks already have tag '{tag_name}'[/yellow]")
            return

        # Confirm if updating multiple bookmarks
        if len(bookmarks_to_update) > 1:
            self.console.print(f"[yellow]This will add tag '{tag_name}' to {len(bookmarks_to_update)} bookmark(s)[/yellow]")
            confirm = input("Continue? (y/N): ").strip().lower()
            if confirm != 'y':
                self.console.print("[dim]Cancelled[/dim]")
                return

        # Add the tag
        from btk.models import Tag, Bookmark
        added_count = 0

        with self.db.session() as session:
            # Get or create the tag
            tag_obj = session.query(Tag).filter_by(name=tag_name).first()
            if not tag_obj:
                tag_obj = Tag(name=tag_name)
                session.add(tag_obj)

            for bookmark in bookmarks_to_update:
                # Reload bookmark in this session
                bookmark_in_session = session.get(Bookmark, bookmark.id)

                # Add tag
                if tag_obj not in bookmark_in_session.tags:
                    bookmark_in_session.tags.append(tag_obj)
                    added_count += 1

            session.commit()

        self.console.print(f"[green]✓ Added tag '{tag_name}' to {added_count} bookmark(s)[/green]")

    def do_clear(self, arg):
        """Clear the screen."""
        os.system('clear' if os.name != 'nt' else 'cls')

    def do_shell(self, arg):
        """Execute a shell command.

        Usage:
            !ls -la
            !git status
            shell echo "hello"
        """
        if not arg:
            self.console.print("[yellow]Usage: !<command> or shell <command>[/yellow]")
            return

        try:
            result = subprocess.run(
                arg,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.stdout:
                print(result.stdout, end='')
            if result.stderr:
                self.console.print(f"[red]{result.stderr}[/red]", end='')
        except subprocess.TimeoutExpired:
            self.console.print("[red]Command timed out (30s limit)[/red]")
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")

    def default(self, line):
        """Handle unrecognized commands and ! prefix for shell execution."""
        if line.startswith('!'):
            self.do_shell(line[1:])
        else:
            self.console.print(f"[red]Unknown command: {line.split()[0] if line else ''}[/red]")
            self.console.print("[dim]Type 'help' for available commands[/dim]")

    def do_tutorial(self, arg):
        """Show a quick tutorial."""
        tutorial = """
[bold cyan]BTK Shell Tutorial[/bold cyan]

[bold]Navigation:[/bold]
  ls                List bookmarks
  ls <id>           List fields of bookmark <id>
  ls .              List current bookmark
  ls ..             List all bookmarks (from bookmark)
  ls -l             Long format with details
  cd 42             Enter bookmark 42
  cd ..             Go back to root
  pwd               Show current location

[bold]Viewing:[/bold]
  cat url           Show URL of current bookmark
  cat title         Show title of current bookmark
  cat 42/url        Show URL of bookmark 42 (path-like)
  cat 42/title      Show title of bookmark 42
  cat all           Show all fields
  file              Show bookmark summary
  stat              Show detailed statistics (collection or bookmark)
  stat <id>         Show stats for specific bookmark

[bold]Operations:[/bold]
  star              Toggle star on current bookmark
  star 42           Toggle star on bookmark 42
  star 42 on        Set star on bookmark 42
  tag python,web    Add tags to current bookmark
  tag 42 python     Add tags to bookmark 42

[bold]Search:[/bold]
  find python       Search for 'python'
  which 42          Find bookmark 42
  top               Show recently added bookmarks
  top visits        Show most visited
  top starred       Show starred bookmarks

[bold]System:[/bold]
  !<command>        Execute shell command
  !ls -la           Run bash ls command
  help              Show all commands
  clear             Clear screen
  exit              Exit shell

[bold]Try it:[/bold]
  1. Type 'ls' to see your bookmarks
  2. Type 'cd <id>' to enter a bookmark
  3. Type 'cat all' to see all fields
  4. Type 'top' to see recent bookmarks
  5. Type '!date' to run a shell command
"""
        self.console.print(tutorial)

    def do_exit(self, arg):
        """Exit the shell."""
        self.console.print("\n[cyan]Goodbye![/cyan]\n")
        return True

    def do_quit(self, arg):
        """Exit the shell."""
        return self.do_exit(arg)

    def do_EOF(self, arg):
        """Handle Ctrl+D."""
        self.console.print()
        return self.do_exit(arg)

    def emptyline(self):
        """Do nothing on empty line."""
        pass

    def default(self, line):
        """Handle unknown commands."""
        if line.startswith('!'):
            # Execute system command
            os.system(line[1:])
        else:
            self.console.print(f"[red]Unknown command: {line}[/red]")
            self.console.print("[dim]Type 'help' for available commands[/dim]")


def main():
    """Main entry point for bookmark shell."""
    import argparse

    parser = argparse.ArgumentParser(description='BTK Shell - Interactive bookmark browser')
    parser.add_argument('--db', default='btk.db', help='Database file (default: btk.db)')
    args = parser.parse_args()

    try:
        shell = BookmarkShell(args.db)
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
