"""
Bulk operations for bookmarks.
"""
import os
import logging
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse
import concurrent.futures
import requests
from bs4 import BeautifulSoup

from btk import utils


def normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    # Simple normalization - just lowercase and remove trailing slash
    url = url.lower().rstrip('/')
    return url


def get_current_timestamp() -> str:
    """Get current ISO timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def bulk_add_from_file(file_path: str, bookmarks: List[Dict], lib_dir: str,
                      default_tags: Optional[List[str]] = None,
                      fetch_titles: bool = True,
                      max_workers: int = 5) -> Tuple[List[Dict], int, List[str]]:
    """
    Bulk add bookmarks from a file containing URLs.
    
    Args:
        file_path: Path to file containing URLs (one per line)
        bookmarks: Existing bookmarks list
        lib_dir: Library directory
        default_tags: Tags to apply to all new bookmarks
        fetch_titles: Whether to fetch titles from URLs
        max_workers: Maximum concurrent workers for fetching titles
    
    Returns:
        Tuple of (updated bookmarks, success count, list of failed URLs)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Read URLs from file
    urls = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):  # Skip empty lines and comments
                # Basic URL validation
                if '://' in line or line.startswith('//'):
                    urls.append(line)
    
    if not urls:
        return bookmarks, 0, []
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        normalized = normalize_url(url)
        if normalized not in seen:
            seen.add(normalized)
            unique_urls.append(url)
    
    # Check against existing bookmarks
    existing_urls = {normalize_url(b.get('url', '')) for b in bookmarks}
    new_urls = [url for url in unique_urls if normalize_url(url) not in existing_urls]
    
    if not new_urls:
        logging.info("No new URLs to add")
        return bookmarks, 0, []
    
    # Prepare for bulk processing
    success_count = 0
    failed_urls = []
    default_tags = default_tags or []
    
    if fetch_titles:
        # Fetch titles concurrently
        url_to_title = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(fetch_url_title, url): url for url in new_urls}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    title = future.result()
                    url_to_title[url] = title
                except Exception as e:
                    logging.warning(f"Failed to fetch title for {url}: {e}")
                    url_to_title[url] = None
    else:
        url_to_title = {url: None for url in new_urls}
    
    # Add bookmarks
    for url in new_urls:
        try:
            title = url_to_title.get(url)
            if not title:
                # Use domain as fallback title
                parsed = urlparse(url)
                title = parsed.netloc or url
            
            # Create new bookmark
            new_bookmark = {
                'id': len(bookmarks) + 1,
                'unique_id': utils.generate_unique_id(url, title),
                'url': url,
                'title': title,
                'tags': default_tags.copy(),
                'description': '',
                'stars': False,
                'added': get_current_timestamp(),
                'visit_count': 0,
                'last_visited': None,
                'favicon': None,
                'reachable': None
            }
            
            bookmarks.append(new_bookmark)
            success_count += 1
            
        except Exception as e:
            logging.error(f"Failed to add bookmark for {url}: {e}")
            failed_urls.append(url)
    
    return bookmarks, success_count, failed_urls


def fetch_url_title(url: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch the title from a URL.
    
    Args:
        url: URL to fetch title from
        timeout: Request timeout in seconds
    
    Returns:
        Title string or None if failed
    """
    try:
        response = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; BTK/1.0)'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        
        if title_tag and title_tag.string:
            return title_tag.string.strip()
        
    except Exception:
        pass
    
    return None


def bulk_edit_bookmarks(bookmarks: List[Dict], filter_func: callable,
                       add_tags: Optional[List[str]] = None,
                       remove_tags: Optional[List[str]] = None,
                       set_stars: Optional[bool] = None,
                       set_description: Optional[str] = None) -> Tuple[List[Dict], int]:
    """
    Bulk edit bookmarks matching a filter.
    
    Args:
        bookmarks: List of bookmarks
        filter_func: Function that returns True for bookmarks to edit
        add_tags: Tags to add
        remove_tags: Tags to remove
        set_stars: Set starred status
        set_description: Set description
    
    Returns:
        Tuple of (updated bookmarks, number of bookmarks edited)
    """
    edited_count = 0
    
    for bookmark in bookmarks:
        if filter_func(bookmark):
            # Add tags
            if add_tags:
                current_tags = set(bookmark.get('tags', []))
                current_tags.update(add_tags)
                bookmark['tags'] = sorted(list(current_tags))
            
            # Remove tags
            if remove_tags:
                current_tags = set(bookmark.get('tags', []))
                for tag in remove_tags:
                    current_tags.discard(tag)
                bookmark['tags'] = sorted(list(current_tags))
            
            # Set stars
            if set_stars is not None:
                bookmark['stars'] = set_stars
            
            # Set description
            if set_description is not None:
                bookmark['description'] = set_description
            
            edited_count += 1
    
    return bookmarks, edited_count


def bulk_remove_bookmarks(bookmarks: List[Dict], filter_func: callable) -> Tuple[List[Dict], List[Dict]]:
    """
    Bulk remove bookmarks matching a filter.
    
    Args:
        bookmarks: List of bookmarks
        filter_func: Function that returns True for bookmarks to remove
    
    Returns:
        Tuple of (remaining bookmarks, removed bookmarks)
    """
    remaining = []
    removed = []
    
    for bookmark in bookmarks:
        if filter_func(bookmark):
            removed.append(bookmark)
        else:
            remaining.append(bookmark)
    
    # Reindex remaining bookmarks
    for i, bookmark in enumerate(remaining):
        bookmark['id'] = i + 1
    
    return remaining, removed


def create_filter_from_criteria(tag_prefix: Optional[str] = None,
                               url_pattern: Optional[str] = None,
                               min_visits: Optional[int] = None,
                               max_visits: Optional[int] = None,
                               is_starred: Optional[bool] = None,
                               has_description: Optional[bool] = None) -> callable:
    """
    Create a filter function from various criteria.
    
    Args:
        tag_prefix: Filter by tag prefix
        url_pattern: Filter by URL pattern (substring match)
        min_visits: Minimum visit count
        max_visits: Maximum visit count
        is_starred: Filter by starred status
        has_description: Filter by presence of description
    
    Returns:
        Filter function that returns True for matching bookmarks
    """
    def filter_func(bookmark: Dict) -> bool:
        # Check tag prefix
        if tag_prefix is not None:
            tags = bookmark.get('tags', [])
            if not any(tag.startswith(tag_prefix) for tag in tags):
                return False
        
        # Check URL pattern
        if url_pattern is not None:
            url = bookmark.get('url', '')
            if url_pattern not in url:
                return False
        
        # Check visit count range
        visits = bookmark.get('visit_count', 0)
        if min_visits is not None and visits < min_visits:
            return False
        if max_visits is not None and visits > max_visits:
            return False
        
        # Check starred status
        if is_starred is not None:
            if bookmark.get('stars', False) != is_starred:
                return False
        
        # Check description
        if has_description is not None:
            has_desc = bool(bookmark.get('description', '').strip())
            if has_desc != has_description:
                return False
        
        return True
    
    return filter_func


def parse_urls_from_text(text: str) -> List[str]:
    """
    Extract URLs from text content.
    
    Args:
        text: Text containing URLs
    
    Returns:
        List of extracted URLs
    """
    import re
    
    # First, extract markdown links to avoid regex conflicts
    markdown_urls = []
    markdown_pattern = re.compile(r'\[([^\]]+)\]\((https?://[^)]+)\)')
    for match in markdown_pattern.finditer(text):
        markdown_urls.append(match.group(2))
    
    # Remove markdown links from text to avoid double extraction
    text_without_markdown = markdown_pattern.sub('', text)
    
    # Regex pattern for standalone URLs
    url_pattern = re.compile(
        r'https?://(?:www\.)?'
        r'[-a-zA-Z0-9@:%._\+~#=]{1,256}\.'
        r'[a-zA-Z0-9()]{1,6}\b'
        r'(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)'
    )
    
    standalone_urls = url_pattern.findall(text_without_markdown)
    
    # Combine all URLs
    all_urls = markdown_urls + standalone_urls
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls