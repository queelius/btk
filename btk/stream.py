"""
Stream processing and watch mode for BTK.

Enables BTK to work with Unix pipelines and provides real-time monitoring.
Outputs JSON Lines format for easy integration with jq and other tools.
"""

import json
import sys
import time
import logging
from typing import List, Dict, Any, Optional, Iterator, Callable
from pathlib import Path
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class BookmarkStream:
    """
    Stream bookmarks in JSON Lines format for pipeline processing.

    Examples:
        btk stream lib_dir | jq '.url' | xargs -I {} curl {}
        btk stream lib_dir --filter 'stars == true' | wc -l
        btk stream lib_dir --watch | grep -E 'github.com'
    """

    def __init__(self, lib_dir: str):
        """Initialize stream with bookmark library directory."""
        self.lib_dir = Path(lib_dir)
        self.bookmarks_file = self.lib_dir / "bookmarks.json"
        self._last_checksum = None
        self._last_bookmarks = []

    def stream(self,
              filter_func: Optional[Callable[[Dict], bool]] = None,
              fields: Optional[List[str]] = None,
              format: str = 'jsonl') -> Iterator[str]:
        """
        Stream bookmarks as JSON Lines.

        Args:
            filter_func: Optional function to filter bookmarks
            fields: Optional list of fields to include (None = all fields)
            format: Output format ('jsonl', 'json', 'csv', 'urls')

        Yields:
            Formatted bookmark strings
        """
        bookmarks = self._load_bookmarks()

        # Apply filter if provided
        if filter_func:
            bookmarks = [b for b in bookmarks if filter_func(b)]

        # Format and yield bookmarks
        for bookmark in bookmarks:
            output = self._format_bookmark(bookmark, fields, format)
            if output:
                yield output

    def watch(self,
             interval: int = 5,
             filter_func: Optional[Callable[[Dict], bool]] = None,
             fields: Optional[List[str]] = None,
             format: str = 'jsonl',
             on_change: Optional[Callable[[List[Dict], List[Dict]], None]] = None) -> Iterator[str]:
        """
        Watch bookmarks file for changes and stream updates.

        Args:
            interval: Check interval in seconds
            filter_func: Optional function to filter bookmarks
            fields: Optional list of fields to include
            format: Output format
            on_change: Optional callback for changes (old_bookmarks, new_bookmarks)

        Yields:
            Formatted bookmark strings when changes occur
        """
        self._last_bookmarks = self._load_bookmarks()
        self._last_checksum = self._calculate_checksum()

        # Initial output
        for line in self.stream(filter_func, fields, format):
            yield line

        # Watch for changes
        while True:
            try:
                time.sleep(interval)
                current_checksum = self._calculate_checksum()

                if current_checksum != self._last_checksum:
                    # File changed, reload and stream changes
                    new_bookmarks = self._load_bookmarks()

                    # Find changes
                    changes = self._find_changes(self._last_bookmarks, new_bookmarks)

                    # Call change handler if provided
                    if on_change:
                        on_change(self._last_bookmarks, new_bookmarks)

                    # Stream changed bookmarks
                    for change_type, bookmark in changes:
                        if filter_func and not filter_func(bookmark):
                            continue

                        # Add change metadata
                        bookmark_with_meta = bookmark.copy()
                        bookmark_with_meta['_change'] = change_type
                        bookmark_with_meta['_timestamp'] = datetime.now().isoformat()

                        output = self._format_bookmark(bookmark_with_meta, fields, format)
                        if output:
                            yield output

                    self._last_bookmarks = new_bookmarks
                    self._last_checksum = current_checksum

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in watch mode: {e}")
                time.sleep(interval)

    def tail(self,
            n: int = 10,
            follow: bool = False,
            filter_func: Optional[Callable[[Dict], bool]] = None,
            fields: Optional[List[str]] = None,
            format: str = 'jsonl') -> Iterator[str]:
        """
        Tail bookmarks (show last N, optionally follow changes).

        Args:
            n: Number of recent bookmarks to show
            follow: Follow mode (like tail -f)
            filter_func: Optional filter function
            fields: Fields to include
            format: Output format

        Yields:
            Formatted bookmark strings
        """
        bookmarks = self._load_bookmarks()

        # Apply filter
        if filter_func:
            bookmarks = [b for b in bookmarks if filter_func(b)]

        # Get last N bookmarks
        recent = bookmarks[-n:] if len(bookmarks) > n else bookmarks

        # Output recent bookmarks
        for bookmark in recent:
            output = self._format_bookmark(bookmark, fields, format)
            if output:
                yield output

        # Follow mode
        if follow:
            seen_ids = {b.get('id') for b in recent}

            for line in self.watch(5, filter_func, fields, format):
                # Parse the line to get bookmark ID
                try:
                    bookmark_data = json.loads(line) if format == 'jsonl' else {}
                    bookmark_id = bookmark_data.get('id')

                    if bookmark_id and bookmark_id not in seen_ids:
                        seen_ids.add(bookmark_id)
                        yield line
                except:
                    yield line

    def diff(self,
            other_lib_dir: str,
            show_only: str = 'all') -> Iterator[str]:
        """
        Stream differences between two bookmark libraries.

        Args:
            other_lib_dir: Path to other library
            show_only: 'left', 'right', 'both', or 'all'

        Yields:
            Difference entries in JSON Lines format
        """
        bookmarks1 = self._load_bookmarks()
        bookmarks2 = self._load_bookmarks(other_lib_dir)

        # Create URL maps
        urls1 = {b.get('url'): b for b in bookmarks1}
        urls2 = {b.get('url'): b for b in bookmarks2}

        # Find differences
        only_in_1 = set(urls1.keys()) - set(urls2.keys())
        only_in_2 = set(urls2.keys()) - set(urls1.keys())
        in_both = set(urls1.keys()) & set(urls2.keys())

        # Output based on show_only
        if show_only in ('left', 'all'):
            for url in only_in_1:
                diff_entry = {
                    'diff': 'left_only',
                    'library': str(self.lib_dir),
                    'bookmark': urls1[url]
                }
                yield json.dumps(diff_entry)

        if show_only in ('right', 'all'):
            for url in only_in_2:
                diff_entry = {
                    'diff': 'right_only',
                    'library': other_lib_dir,
                    'bookmark': urls2[url]
                }
                yield json.dumps(diff_entry)

        if show_only in ('both', 'all'):
            for url in in_both:
                # Check if bookmarks differ in metadata
                if self._bookmarks_differ(urls1[url], urls2[url]):
                    diff_entry = {
                        'diff': 'both_different',
                        'url': url,
                        'left': urls1[url],
                        'right': urls2[url],
                        'differences': self._find_field_differences(urls1[url], urls2[url])
                    }
                    yield json.dumps(diff_entry)

    def _load_bookmarks(self, lib_dir: Optional[str] = None) -> List[Dict]:
        """Load bookmarks from library."""
        if lib_dir:
            bookmarks_file = Path(lib_dir) / "bookmarks.json"
        else:
            bookmarks_file = self.bookmarks_file

        try:
            if bookmarks_file.exists():
                with open(bookmarks_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading bookmarks: {e}")

        return []

    def _calculate_checksum(self) -> Optional[str]:
        """Calculate file checksum for change detection."""
        try:
            if self.bookmarks_file.exists():
                with open(self.bookmarks_file, 'rb') as f:
                    return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"Error calculating checksum: {e}")
        return None

    def _find_changes(self, old: List[Dict], new: List[Dict]) -> List[tuple]:
        """Find changes between bookmark lists."""
        changes = []

        # Create ID maps
        old_ids = {b.get('id'): b for b in old if b.get('id')}
        new_ids = {b.get('id'): b for b in new if b.get('id')}

        # Find added bookmarks
        added_ids = set(new_ids.keys()) - set(old_ids.keys())
        for id in added_ids:
            changes.append(('added', new_ids[id]))

        # Find removed bookmarks
        removed_ids = set(old_ids.keys()) - set(new_ids.keys())
        for id in removed_ids:
            changes.append(('removed', old_ids[id]))

        # Find modified bookmarks
        common_ids = set(old_ids.keys()) & set(new_ids.keys())
        for id in common_ids:
            if self._bookmarks_differ(old_ids[id], new_ids[id]):
                changes.append(('modified', new_ids[id]))

        return changes

    def _bookmarks_differ(self, b1: Dict, b2: Dict) -> bool:
        """Check if two bookmarks differ in any field."""
        # Ignore internal fields
        ignore_fields = {'_change', '_timestamp'}

        keys1 = set(b1.keys()) - ignore_fields
        keys2 = set(b2.keys()) - ignore_fields

        if keys1 != keys2:
            return True

        for key in keys1:
            if b1.get(key) != b2.get(key):
                return True

        return False

    def _find_field_differences(self, b1: Dict, b2: Dict) -> List[str]:
        """Find which fields differ between bookmarks."""
        differences = []
        all_keys = set(b1.keys()) | set(b2.keys())

        for key in all_keys:
            v1 = b1.get(key)
            v2 = b2.get(key)
            if v1 != v2:
                differences.append(key)

        return differences

    def _format_bookmark(self,
                        bookmark: Dict,
                        fields: Optional[List[str]],
                        format: str) -> Optional[str]:
        """Format bookmark for output."""
        # Filter fields if specified
        if fields:
            bookmark = {k: bookmark.get(k) for k in fields if k in bookmark}

        # Format based on type
        if format == 'jsonl':
            return json.dumps(bookmark)
        elif format == 'json':
            return json.dumps(bookmark, indent=2)
        elif format == 'csv':
            # Simple CSV output
            values = [str(bookmark.get(f, '')) for f in (fields or ['id', 'url', 'title'])]
            return ','.join(values)
        elif format == 'urls':
            return bookmark.get('url', '')
        elif format == 'tsv':
            # Tab-separated values
            values = [str(bookmark.get(f, '')) for f in (fields or ['id', 'url', 'title'])]
            return '\t'.join(values)
        else:
            return json.dumps(bookmark)


def create_filter(filter_expr: str) -> Callable[[Dict], bool]:
    """
    Create a filter function from a simple expression.

    Supports expressions like:
        - stars == true
        - visit_count > 5
        - "github.com" in url
        - tags contains "python"

    Args:
        filter_expr: Filter expression string

    Returns:
        Filter function
    """
    def filter_func(bookmark: Dict) -> bool:
        try:
            # Simple expression evaluation (safe subset)
            # This is a basic implementation - could be enhanced

            # Handle boolean comparisons
            if '==' in filter_expr:
                parts = filter_expr.split('==')
                if len(parts) == 2:
                    field = parts[0].strip()
                    value = parts[1].strip()

                    if value == 'true':
                        return bookmark.get(field) is True
                    elif value == 'false':
                        return bookmark.get(field) is False
                    else:
                        return str(bookmark.get(field)) == value.strip('"')

            # Handle numeric comparisons
            elif '>' in filter_expr:
                parts = filter_expr.split('>')
                if len(parts) == 2:
                    field = parts[0].strip()
                    value = int(parts[1].strip())
                    return bookmark.get(field, 0) > value

            elif '<' in filter_expr:
                parts = filter_expr.split('<')
                if len(parts) == 2:
                    field = parts[0].strip()
                    value = int(parts[1].strip())
                    return bookmark.get(field, 0) < value

            # Handle 'in' operator
            elif ' in ' in filter_expr:
                parts = filter_expr.split(' in ')
                if len(parts) == 2:
                    needle = parts[0].strip().strip('"')
                    field = parts[1].strip()
                    haystack = bookmark.get(field, '')
                    if isinstance(haystack, str):
                        return needle in haystack
                    elif isinstance(haystack, list):
                        return needle in haystack

            # Handle 'contains' for lists
            elif ' contains ' in filter_expr:
                parts = filter_expr.split(' contains ')
                if len(parts) == 2:
                    field = parts[0].strip()
                    value = parts[1].strip().strip('"')
                    field_value = bookmark.get(field, [])
                    if isinstance(field_value, list):
                        return value in field_value
                    elif isinstance(field_value, str):
                        return value in field_value

            return True  # Default to including bookmark

        except Exception as e:
            logger.error(f"Error in filter expression: {e}")
            return True

    return filter_func


def stream_bookmarks(lib_dir: str,
                    filter: Optional[str] = None,
                    fields: Optional[List[str]] = None,
                    format: str = 'jsonl',
                    watch: bool = False,
                    tail: Optional[int] = None,
                    follow: bool = False) -> None:
    """
    Main streaming function for CLI integration.

    Args:
        lib_dir: Bookmark library directory
        filter: Filter expression
        fields: Fields to output
        format: Output format
        watch: Watch mode
        tail: Tail mode (show last N)
        follow: Follow mode (with tail)
    """
    stream = BookmarkStream(lib_dir)

    # Create filter function
    filter_func = None
    if filter:
        filter_func = create_filter(filter)

    try:
        if tail is not None:
            # Tail mode
            for line in stream.tail(tail, follow, filter_func, fields, format):
                print(line)
                sys.stdout.flush()
        elif watch:
            # Watch mode
            for line in stream.watch(5, filter_func, fields, format):
                print(line)
                sys.stdout.flush()
        else:
            # Regular streaming
            for line in stream.stream(filter_func, fields, format):
                print(line)
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:
        # Handle pipe being closed (e.g., | head)
        pass