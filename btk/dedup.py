"""
Bookmark deduplication utilities.
"""
from typing import List, Dict, Set, Tuple, Optional, Callable
from collections import defaultdict
import logging
from btk.progress import with_progress


@with_progress("Finding duplicates")
def find_duplicates(bookmarks: List[Dict], key: str = 'url') -> Dict[str, List[Dict]]:
    """
    Find duplicate bookmarks based on a key.
    
    Args:
        bookmarks: List of bookmark dictionaries
        key: Key to use for deduplication (default: 'url')
    
    Returns:
        Dictionary mapping duplicate keys to lists of bookmarks
    """
    groups = defaultdict(list)
    
    for bookmark in bookmarks:
        if key in bookmark and bookmark[key]:
            groups[bookmark[key]].append(bookmark)
    
    # Filter to only duplicates (more than one bookmark)
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    
    return duplicates


def merge_bookmark_metadata(bookmarks: List[Dict]) -> Dict:
    """
    Merge metadata from multiple duplicate bookmarks.
    
    Args:
        bookmarks: List of duplicate bookmarks
    
    Returns:
        Merged bookmark with combined metadata
    """
    if not bookmarks:
        return {}
    
    # Start with the first bookmark
    merged = bookmarks[0].copy()
    
    # Merge tags (union of all tags)
    all_tags = set()
    for b in bookmarks:
        all_tags.update(b.get('tags', []))
    merged['tags'] = sorted(list(all_tags))
    
    # Merge visit counts (sum)
    total_visits = sum(b.get('visit_count', 0) for b in bookmarks)
    merged['visit_count'] = total_visits
    
    # Keep the longest description
    longest_desc = ''
    for b in bookmarks:
        desc = b.get('description', '')
        if len(desc) > len(longest_desc):
            longest_desc = desc
    merged['description'] = longest_desc
    
    # Keep starred if any bookmark is starred
    merged['stars'] = any(b.get('stars', False) for b in bookmarks)
    
    # Keep the earliest added date
    added_dates = [b.get('added') for b in bookmarks if b.get('added')]
    if added_dates:
        merged['added'] = min(added_dates)
    
    # Keep the most recent last_visited
    visit_dates = [b.get('last_visited') for b in bookmarks if b.get('last_visited')]
    if visit_dates:
        merged['last_visited'] = max(visit_dates)
    
    # Keep the best title (non-empty, preferably not a URL)
    best_title = merged.get('title', '')
    for b in bookmarks:
        title = b.get('title', '')
        if title and title != b.get('url'):
            if not best_title or best_title == merged.get('url'):
                best_title = title
            elif len(title) > len(best_title):
                best_title = title
    merged['title'] = best_title
    
    return merged


def deduplicate_bookmarks(bookmarks: List[Dict], 
                         strategy: str = 'merge',
                         key: str = 'url',
                         interactive: bool = False,
                         select_func: Optional[Callable] = None) -> Tuple[List[Dict], List[Dict]]:
    """
    Deduplicate bookmarks using the specified strategy.
    
    Args:
        bookmarks: List of bookmark dictionaries
        strategy: Deduplication strategy:
            - 'merge': Combine metadata from all duplicates (union tags, sum visits, etc.)
            - 'keep_first': Keep the first occurrence
            - 'keep_last': Keep the last occurrence  
            - 'keep_most_visited': Keep the bookmark with highest visit_count
            - 'interactive': Use custom select_func to choose
        key: Key to use for finding duplicates (default: 'url')
        interactive: Whether to prompt for each duplicate (only for 'interactive' strategy)
        select_func: Function(List[Dict]) -> Dict to select which bookmark to keep
    
    Returns:
        Tuple of (deduplicated bookmarks, removed bookmarks)
    
    Example:
        >>> bookmarks = [{'url': 'http://example.com', 'title': 'Ex1'}, 
        ...              {'url': 'http://example.com', 'title': 'Ex2'}]
        >>> deduped, removed = deduplicate_bookmarks(bookmarks, strategy='merge')
        >>> len(deduped) == 1  # True
    """
    duplicates = find_duplicates(bookmarks, key)
    
    if not duplicates:
        return bookmarks, []
    
    # Track which bookmarks to keep
    bookmarks_to_keep = []
    removed_bookmarks = []
    seen_keys = set()
    
    for bookmark in bookmarks:
        bookmark_key = bookmark.get(key)
        
        if bookmark_key not in duplicates:
            # Not a duplicate, keep it
            bookmarks_to_keep.append(bookmark)
        elif bookmark_key not in seen_keys:
            # First occurrence of a duplicate
            seen_keys.add(bookmark_key)
            
            duplicate_group = duplicates[bookmark_key]
            
            if strategy == 'merge':
                # Merge all duplicates
                merged = merge_bookmark_metadata(duplicate_group)
                bookmarks_to_keep.append(merged)
                # All but the merged one are removed
                removed_bookmarks.extend(duplicate_group)
                
            elif strategy == 'keep_first':
                # Keep the first one
                bookmarks_to_keep.append(duplicate_group[0])
                removed_bookmarks.extend(duplicate_group[1:])
                
            elif strategy == 'keep_last':
                # Keep the last one
                bookmarks_to_keep.append(duplicate_group[-1])
                removed_bookmarks.extend(duplicate_group[:-1])
                
            elif strategy == 'keep_most_visited':
                # Keep the most visited one
                most_visited = max(duplicate_group, key=lambda b: b.get('visit_count', 0))
                bookmarks_to_keep.append(most_visited)
                removed_bookmarks.extend([b for b in duplicate_group if b != most_visited])
                
            elif strategy == 'interactive' and select_func:
                # Use custom selection function
                selected = select_func(duplicate_group)
                if selected:
                    bookmarks_to_keep.append(selected)
                    removed_bookmarks.extend([b for b in duplicate_group if b != selected])
                else:
                    # If no selection, keep all
                    bookmarks_to_keep.extend(duplicate_group)
            
            else:
                # Default: keep first
                bookmarks_to_keep.append(duplicate_group[0])
                removed_bookmarks.extend(duplicate_group[1:])
        else:
            # Subsequent occurrence of duplicate, already handled
            continue
    
    return bookmarks_to_keep, removed_bookmarks


def get_duplicate_stats(bookmarks: List[Dict], key: str = 'url') -> Dict:
    """
    Get statistics about duplicates in the bookmark collection.
    
    Args:
        bookmarks: List of bookmark dictionaries
        key: Key to use for finding duplicates
    
    Returns:
        Dictionary with duplicate statistics
    """
    duplicates = find_duplicates(bookmarks, key)
    
    total_duplicates = sum(len(group) for group in duplicates.values())
    unique_urls = len(duplicates)
    
    # Find the most duplicated URLs
    most_duplicated = sorted(
        [(url, len(group)) for url, group in duplicates.items()],
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    return {
        'total_bookmarks': len(bookmarks),
        'duplicate_groups': len(duplicates),
        'total_duplicates': total_duplicates,
        'bookmarks_to_remove': total_duplicates - unique_urls,
        'most_duplicated': most_duplicated,
        'duplicate_percentage': (total_duplicates / len(bookmarks) * 100) if bookmarks else 0
    }


def preview_deduplication(bookmarks: List[Dict], strategy: str = 'merge', key: str = 'url') -> List[Dict]:
    """
    Preview the results of deduplication without modifying the original bookmarks.
    
    Args:
        bookmarks: List of bookmark dictionaries
        strategy: Deduplication strategy
        key: Key to use for deduplication
    
    Returns:
        List of bookmarks that would remain after deduplication
    """
    deduplicated, _ = deduplicate_bookmarks(bookmarks.copy(), strategy, key)
    return deduplicated