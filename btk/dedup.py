"""
Bookmark deduplication utilities with enhanced duplicate detection.

Supports smart URL matching, content fingerprinting, and redirect detection.
"""
from typing import List, Dict, Set, Tuple, Optional, Callable
from collections import defaultdict
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import logging
import re
import hashlib
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


def normalize_url(url: str, aggressive: bool = False) -> str:
    """
    Normalize a URL for duplicate detection.

    Args:
        url: URL to normalize
        aggressive: Use aggressive normalization (removes more variation)

    Returns:
        Normalized URL string
    """
    if not url:
        return url

    try:
        parsed = urlparse(url.lower())
    except:
        return url.lower()

    # Remove common URL variations
    scheme = parsed.scheme
    netloc = parsed.netloc
    path = parsed.path
    query = parsed.query

    # Normalize scheme
    if scheme == 'http':
        scheme = 'https'  # Treat http and https as same

    # Remove www prefix
    if netloc.startswith('www.'):
        netloc = netloc[4:]

    # Remove trailing slash from path
    if path.endswith('/') and len(path) > 1:
        path = path[:-1]

    # Remove index files
    index_files = ['/index.html', '/index.htm', '/index.php', '/default.html']
    for index in index_files:
        if path.endswith(index):
            path = path[:-len(index)]
            if not path:
                path = '/'
            break

    # Handle query parameters
    if query and aggressive:
        # Remove tracking parameters
        params = parse_qs(query)
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'ref', 'source', 'campaign'
        }
        cleaned_params = {k: v for k, v in params.items() if k not in tracking_params}
        query = urlencode(cleaned_params, doseq=True)

    # Remove fragment (anchor)
    fragment = '' if aggressive else parsed.fragment

    # Rebuild URL
    normalized = urlunparse((scheme, netloc, path, '', query, fragment))

    return normalized


@with_progress("Finding smart duplicates")
def find_smart_duplicates(bookmarks: List[Dict],
                         match_level: str = 'normal') -> Dict[str, List[Dict]]:
    """
    Find duplicates using intelligent URL matching.

    Args:
        bookmarks: List of bookmark dictionaries
        match_level: How aggressively to match URLs:
            - 'exact': Only exact URL matches
            - 'normal': Normalize URLs (default)
            - 'aggressive': Aggressive normalization (ignore tracking params)
            - 'fuzzy': Include similar titles and domains

    Returns:
        Dictionary mapping normalized URLs to lists of bookmarks
    """
    groups = defaultdict(list)

    for bookmark in bookmarks:
        url = bookmark.get('url')
        if not url:
            continue

        if match_level == 'exact':
            key = url
        elif match_level == 'aggressive':
            key = normalize_url(url, aggressive=True)
        elif match_level == 'fuzzy':
            # Use domain + title similarity for fuzzy matching
            key = normalize_url(url, aggressive=True)
            # Add title hash for fuzzy matching
            title = bookmark.get('title', '')
            if title:
                # Simple title normalization
                title_key = re.sub(r'\W+', '', title.lower())[:20]
                key = f"{urlparse(key).netloc}:{title_key}"
        else:  # normal
            key = normalize_url(url, aggressive=False)

        groups[key].append(bookmark)

    # Filter to only duplicates
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}

    return duplicates


def find_redirect_chains(bookmarks: List[Dict]) -> List[List[Dict]]:
    """
    Find potential redirect chains in bookmarks.

    Detects bookmarks that might be redirects of each other based on:
    - Similar titles but different URLs
    - Common redirect patterns (e.g., bit.ly -> full URL)
    - URLs with and without trailing slashes

    Args:
        bookmarks: List of bookmark dictionaries

    Returns:
        List of potential redirect chains (groups of related bookmarks)
    """
    chains = []
    processed = set()

    # Group by title similarity
    title_groups = defaultdict(list)
    for bookmark in bookmarks:
        title = bookmark.get('title', '')
        if title and len(title) > 3:
            # Normalize title for grouping
            title_key = re.sub(r'\W+', '', title.lower())
            title_groups[title_key].append(bookmark)

    # Find URL shortener patterns
    shortener_patterns = [
        r'bit\.ly/', r'tinyurl\.com/', r'goo\.gl/', r't\.co/',
        r'short\.link/', r'ow\.ly/', r'is\.gd/', r'buff\.ly/'
    ]

    for group in title_groups.values():
        if len(group) > 1:
            # Check if URLs look like redirects
            has_shortener = False
            has_full = False

            for bookmark in group:
                url = bookmark.get('url', '')
                if any(re.search(p, url) for p in shortener_patterns):
                    has_shortener = True
                elif len(url) > 50:  # Likely a full URL
                    has_full = True

            # If we have both shortened and full URLs, likely a redirect chain
            if has_shortener and has_full:
                chain_ids = [b.get('id') for b in group]
                if not any(id in processed for id in chain_ids):
                    chains.append(group)
                    processed.update(chain_ids)

    return chains


def content_fingerprint(bookmark: Dict) -> str:
    """
    Generate a content fingerprint for a bookmark.

    Uses title, description, and domain to create a hash that identifies
    similar content even if URLs differ.

    Args:
        bookmark: Bookmark dictionary

    Returns:
        Fingerprint hash string
    """
    components = []

    # Include domain
    url = bookmark.get('url', '')
    if url:
        try:
            domain = urlparse(url).netloc.replace('www.', '')
            components.append(domain)
        except:
            pass

    # Include normalized title
    title = bookmark.get('title', '')
    if title:
        # Remove common variations
        title_normalized = re.sub(r'[^\w\s]', '', title.lower())
        title_normalized = re.sub(r'\s+', ' ', title_normalized).strip()
        if title_normalized:
            components.append(title_normalized)

    # Include description if available
    desc = bookmark.get('description', '')
    if desc and len(desc) > 20:
        # Use first 100 chars of description
        desc_normalized = re.sub(r'[^\w\s]', '', desc.lower())[:100]
        components.append(desc_normalized)

    # Create fingerprint
    if components:
        fingerprint_str = '|'.join(components)
        return hashlib.md5(fingerprint_str.encode()).hexdigest()[:16]

    return ''


@with_progress("Finding content duplicates")
def find_content_duplicates(bookmarks: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Find duplicates based on content similarity rather than URLs.

    Args:
        bookmarks: List of bookmark dictionaries

    Returns:
        Dictionary mapping content fingerprints to lists of bookmarks
    """
    groups = defaultdict(list)

    for bookmark in bookmarks:
        fingerprint = content_fingerprint(bookmark)
        if fingerprint:
            groups[fingerprint].append(bookmark)

    # Filter to only duplicates
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}

    return duplicates


def analyze_duplicates(bookmarks: List[Dict]) -> Dict:
    """
    Comprehensive duplicate analysis using multiple detection methods.

    Args:
        bookmarks: List of bookmark dictionaries

    Returns:
        Dictionary with detailed duplicate analysis
    """
    # Run different duplicate detection methods
    exact_dupes = find_duplicates(bookmarks, 'url')
    smart_dupes = find_smart_duplicates(bookmarks, 'normal')
    aggressive_dupes = find_smart_duplicates(bookmarks, 'aggressive')
    content_dupes = find_content_duplicates(bookmarks)
    redirect_chains = find_redirect_chains(bookmarks)

    # Calculate statistics
    total_exact = sum(len(g) - 1 for g in exact_dupes.values())
    total_smart = sum(len(g) - 1 for g in smart_dupes.values())
    total_aggressive = sum(len(g) - 1 for g in aggressive_dupes.values())
    total_content = sum(len(g) - 1 for g in content_dupes.values())
    total_redirects = sum(len(chain) - 1 for chain in redirect_chains)

    return {
        'total_bookmarks': len(bookmarks),
        'exact_duplicates': {
            'groups': len(exact_dupes),
            'total': total_exact,
            'examples': list(exact_dupes.keys())[:5]
        },
        'smart_duplicates': {
            'groups': len(smart_dupes),
            'total': total_smart,
            'examples': list(smart_dupes.keys())[:5]
        },
        'aggressive_duplicates': {
            'groups': len(aggressive_dupes),
            'total': total_aggressive,
            'examples': list(aggressive_dupes.keys())[:5]
        },
        'content_duplicates': {
            'groups': len(content_dupes),
            'total': total_content
        },
        'redirect_chains': {
            'chains': len(redirect_chains),
            'total': total_redirects
        },
        'summary': {
            'removable_exact': total_exact,
            'removable_smart': total_smart,
            'removable_aggressive': total_aggressive,
            'potential_merges': total_content
        }
    }