"""
Enhanced REPL command utilities with options parsing.

This module provides utilities for parsing command options and 
implementing paging, filtering, and other common command features.
"""

import re
import argparse
import shlex
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import math


class OutputFormat(Enum):
    """Output format options."""
    COMPACT = "compact"
    DETAILED = "detailed"
    JSON = "json"
    TABLE = "table"
    CSV = "csv"


@dataclass
class ListOptions:
    """Options for list/ls command."""
    limit: Optional[int] = 20  # Default page size
    offset: int = 0
    sort_by: str = "id"  # id, title, url, added, modified, visits
    reverse: bool = False
    filter_tags: Optional[List[str]] = None
    filter_starred: Optional[bool] = None
    filter_text: Optional[str] = None
    format: OutputFormat = OutputFormat.COMPACT
    page: Optional[int] = None  # Page number (1-based)
    all: bool = False  # Show all without paging
    range: Optional[Tuple[int, int]] = None  # ID range
    fields: Optional[List[str]] = None  # Fields to display
    no_color: bool = False
    group_by: Optional[str] = None  # Group by tag, domain, etc.


@dataclass  
class SearchOptions:
    """Options for search command."""
    limit: Optional[int] = 10
    offset: int = 0
    format: OutputFormat = OutputFormat.COMPACT
    case_sensitive: bool = False
    regex: bool = False
    fields: List[str] = None  # Fields to search in
    highlight: bool = True
    page: Optional[int] = None
    all: bool = False


@dataclass
class ExportOptions:
    """Options for export command."""
    format: str = "json"
    output: Optional[str] = None
    filter_tags: Optional[List[str]] = None
    filter_starred: Optional[bool] = None
    range: Optional[Tuple[int, int]] = None
    include_content: bool = False
    pretty: bool = True


class CommandParser:
    """
    Parse command arguments with Unix-style options.
    
    This parser handles:
    - Short options: -l 10, -s, -r
    - Long options: --limit 10, --starred, --reverse
    - Ranges: 1-10, 1..10, 1:10
    - Combined short options: -sr (starred + reverse)
    """
    
    @staticmethod
    def parse_range(range_str: str) -> Optional[Tuple[int, int]]:
        """
        Parse range specifications.
        
        Supports formats:
        - 1-10
        - 1..10  
        - 1:10
        - :10 (from start to 10)
        - 10: (from 10 to end)
        """
        if not range_str:
            return None
        
        # Match different range patterns
        patterns = [
            r'^(\d+)-(\d+)$',     # 1-10
            r'^(\d+)\.\.(\d+)$',  # 1..10
            r'^(\d+):(\d+)$',     # 1:10
            r'^:(\d+)$',          # :10
            r'^(\d+):$',          # 10:
        ]
        
        for pattern in patterns[:-2]:  # First three are start-end
            match = re.match(pattern, range_str)
            if match:
                start, end = match.groups()
                return (int(start), int(end))
        
        # Handle :10 (from start)
        match = re.match(patterns[-2], range_str)
        if match:
            return (1, int(match.group(1)))
        
        # Handle 10: (to end)
        match = re.match(patterns[-1], range_str)
        if match:
            return (int(match.group(1)), None)
        
        return None
    
    @staticmethod
    def parse_list_options(args: List[str]) -> Tuple[ListOptions, List[str]]:
        """
        Parse list/ls command options.
        
        Returns:
            Tuple of (options, remaining_args)
        """
        options = ListOptions()
        remaining = []
        i = 0
        
        while i < len(args):
            arg = args[i]
            
            if arg in ['-l', '--limit']:
                if i + 1 < len(args):
                    options.limit = int(args[i + 1])
                    i += 2
                else:
                    i += 1
            
            elif arg in ['-p', '--page']:
                if i + 1 < len(args):
                    options.page = int(args[i + 1])
                    options.offset = (options.page - 1) * (options.limit or 20)
                    i += 2
                else:
                    i += 1
            
            elif arg in ['-a', '--all']:
                options.all = True
                options.limit = None
                i += 1
            
            elif arg in ['-s', '--sort']:
                if i + 1 < len(args):
                    options.sort_by = args[i + 1]
                    i += 2
                else:
                    i += 1
            
            elif arg in ['-r', '--reverse']:
                options.reverse = True
                i += 1
            
            elif arg == '--starred':
                options.filter_starred = True
                i += 1
            
            elif arg == '--unstarred':
                options.filter_starred = False
                i += 1
            
            elif arg in ['-t', '--tag', '--tags']:
                if i + 1 < len(args):
                    options.filter_tags = args[i + 1].split(',')
                    i += 2
                else:
                    i += 1
            
            elif arg in ['-f', '--format']:
                if i + 1 < len(args):
                    try:
                        options.format = OutputFormat(args[i + 1])
                    except ValueError:
                        pass
                    i += 2
                else:
                    i += 1
            
            elif arg == '--fields':
                if i + 1 < len(args):
                    options.fields = args[i + 1].split(',')
                    i += 2
                else:
                    i += 1
            
            elif arg in ['-g', '--group', '--group-by']:
                if i + 1 < len(args):
                    options.group_by = args[i + 1]
                    i += 2
                else:
                    i += 1
            
            elif arg == '--no-color':
                options.no_color = True
                i += 1
            
            elif arg.startswith('-') and not arg.startswith('--'):
                # Handle combined short options like -sr
                for char in arg[1:]:
                    if char == 'r':
                        options.reverse = True
                    elif char == 'a':
                        options.all = True
                        options.limit = None
                    elif char == 's' and i + 1 < len(args) and not args[i + 1].startswith('-'):
                        # -s followed by sort field
                        options.sort_by = args[i + 1]
                        i += 1
                        break
                i += 1
            
            else:
                # Check if it's a range
                range_tuple = CommandParser.parse_range(arg)
                if range_tuple:
                    options.range = range_tuple
                else:
                    remaining.append(arg)
                i += 1
        
        return options, remaining
    
    @staticmethod
    def parse_search_options(args: List[str]) -> Tuple[SearchOptions, List[str]]:
        """Parse search command options."""
        options = SearchOptions()
        remaining = []
        i = 0
        
        while i < len(args):
            arg = args[i]
            
            if arg in ['-l', '--limit']:
                if i + 1 < len(args):
                    options.limit = int(args[i + 1])
                    i += 2
                else:
                    i += 1
            
            elif arg in ['-p', '--page']:
                if i + 1 < len(args):
                    options.page = int(args[i + 1])
                    options.offset = (options.page - 1) * (options.limit or 10)
                    i += 2
                else:
                    i += 1
            
            elif arg in ['-a', '--all']:
                options.all = True
                options.limit = None
                i += 1
            
            elif arg in ['-c', '--case-sensitive']:
                options.case_sensitive = True
                i += 1
            
            elif arg in ['-r', '--regex']:
                options.regex = True
                i += 1
            
            elif arg in ['-f', '--fields']:
                if i + 1 < len(args):
                    options.fields = args[i + 1].split(',')
                    i += 2
                else:
                    i += 1
            
            elif arg == '--no-highlight':
                options.highlight = False
                i += 1
            
            elif arg == '--format':
                if i + 1 < len(args):
                    try:
                        options.format = OutputFormat(args[i + 1])
                    except ValueError:
                        pass
                    i += 2
                else:
                    i += 1
            
            else:
                remaining.append(arg)
                i += 1
        
        return options, remaining


class Paginator:
    """Handle pagination of results."""
    
    def __init__(self, items: List[Any], page_size: int = 20):
        """
        Initialize paginator.
        
        Args:
            items: List of items to paginate
            page_size: Number of items per page
        """
        self.items = items
        self.page_size = page_size
        self.total_items = len(items)
        self.total_pages = math.ceil(self.total_items / page_size) if page_size else 1
        self.current_page = 1
    
    def get_page(self, page_num: int) -> List[Any]:
        """Get a specific page."""
        if page_num < 1 or page_num > self.total_pages:
            return []
        
        start = (page_num - 1) * self.page_size
        end = start + self.page_size
        return self.items[start:end]
    
    def get_current_page(self) -> List[Any]:
        """Get current page."""
        return self.get_page(self.current_page)
    
    def next_page(self) -> bool:
        """Move to next page. Returns True if successful."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            return True
        return False
    
    def prev_page(self) -> bool:
        """Move to previous page. Returns True if successful."""
        if self.current_page > 1:
            self.current_page -= 1
            return True
        return False
    
    def get_page_info(self) -> str:
        """Get page information string."""
        if self.total_pages <= 1:
            return f"Showing all {self.total_items} items"
        
        start = (self.current_page - 1) * self.page_size + 1
        end = min(self.current_page * self.page_size, self.total_items)
        
        return f"Page {self.current_page}/{self.total_pages} (items {start}-{end} of {self.total_items})"


def format_bookmark_compact(bookmark: Dict[str, Any], show_color: bool = True) -> str:
    """Format bookmark in compact form."""
    stars = "★" if bookmark.get('stars') else " "
    id_str = f"[{bookmark.get('id', '?')}]"
    title = bookmark.get('title', 'Untitled')[:50]
    url = bookmark.get('url', '')[:40]
    
    if show_color:
        from rich.text import Text
        text = Text()
        text.append(stars, style="yellow" if bookmark.get('stars') else "dim")
        text.append(f" {id_str}", style="cyan")
        text.append(f" {title}", style="bold")
        text.append(f" - {url}", style="dim")
        return text
    else:
        return f"{stars} {id_str} {title} - {url}"


def format_bookmark_detailed(bookmark: Dict[str, Any], show_color: bool = True) -> str:
    """Format bookmark in detailed form."""
    lines = []
    
    # Header line
    stars = "★" if bookmark.get('stars') else "☆"
    lines.append(f"{stars} [{bookmark.get('id', '?')}] {bookmark.get('title', 'Untitled')}")
    
    # URL
    lines.append(f"  URL: {bookmark.get('url', '')}")
    
    # Tags
    if bookmark.get('tags'):
        tags_str = ', '.join(bookmark['tags'])
        lines.append(f"  Tags: {tags_str}")
    
    # Description
    if bookmark.get('description'):
        desc = bookmark['description'][:100]
        if len(bookmark['description']) > 100:
            desc += "..."
        lines.append(f"  Description: {desc}")
    
    # Stats
    stats = []
    if bookmark.get('visit_count'):
        stats.append(f"visits: {bookmark['visit_count']}")
    if bookmark.get('added'):
        added_date = bookmark['added'].split('T')[0]
        stats.append(f"added: {added_date}")
    if stats:
        lines.append(f"  Stats: {', '.join(stats)}")
    
    return '\n'.join(lines)


def apply_filters(bookmarks: List[Dict[str, Any]], options: ListOptions) -> List[Dict[str, Any]]:
    """Apply filters to bookmarks based on options."""
    filtered = bookmarks
    
    # Filter by tags
    if options.filter_tags:
        filtered = [b for b in filtered 
                   if any(tag in b.get('tags', []) for tag in options.filter_tags)]
    
    # Filter by starred status
    if options.filter_starred is not None:
        filtered = [b for b in filtered 
                   if b.get('stars', False) == options.filter_starred]
    
    # Filter by text
    if options.filter_text:
        text_lower = options.filter_text.lower()
        filtered = [b for b in filtered
                   if text_lower in (b.get('title', '') + b.get('url', '') + 
                                    b.get('description', '')).lower()]
    
    # Filter by range
    if options.range:
        start, end = options.range
        if end is None:
            filtered = [b for b in filtered if b.get('id', 0) >= start]
        else:
            filtered = [b for b in filtered if start <= b.get('id', 0) <= end]
    
    return filtered


def sort_bookmarks(bookmarks: List[Dict[str, Any]], sort_by: str, reverse: bool = False) -> List[Dict[str, Any]]:
    """Sort bookmarks by specified field."""
    sort_keys = {
        'id': lambda b: b.get('id', 0),
        'title': lambda b: b.get('title', '').lower(),
        'url': lambda b: b.get('url', ''),
        'added': lambda b: b.get('added', ''),
        'modified': lambda b: b.get('modified', b.get('added', '')),
        'visits': lambda b: b.get('visit_count', 0),
        'stars': lambda b: (b.get('stars', False), b.get('id', 0)),
    }
    
    key_func = sort_keys.get(sort_by, sort_keys['id'])
    return sorted(bookmarks, key=key_func, reverse=reverse)


def group_bookmarks(bookmarks: List[Dict[str, Any]], group_by: str) -> Dict[str, List[Dict[str, Any]]]:
    """Group bookmarks by specified field."""
    from urllib.parse import urlparse
    from collections import defaultdict
    
    groups = defaultdict(list)
    
    for bookmark in bookmarks:
        if group_by == 'tag':
            # Group by each tag
            tags = bookmark.get('tags', [])
            if not tags:
                groups['untagged'].append(bookmark)
            else:
                for tag in tags:
                    groups[tag].append(bookmark)
        
        elif group_by == 'domain':
            # Group by domain
            url = bookmark.get('url', '')
            try:
                domain = urlparse(url).netloc or 'unknown'
            except:
                domain = 'unknown'
            groups[domain].append(bookmark)
        
        elif group_by == 'starred':
            # Group by starred status
            key = 'starred' if bookmark.get('stars') else 'unstarred'
            groups[key].append(bookmark)
        
        elif group_by == 'date':
            # Group by added date
            added = bookmark.get('added', '')
            date = added.split('T')[0] if added else 'unknown'
            groups[date].append(bookmark)
        
        else:
            # Default: no grouping
            groups['all'].append(bookmark)
    
    return dict(groups)