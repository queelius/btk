"""
Auto-tagging functionality for BTK bookmarks.

This module provides automatic tag generation for bookmarks using
the plugin system. It supports both single and bulk operations.
"""

import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from . import plugins
from . import utils

logger = logging.getLogger(__name__)

# Global plugin registry (created on first use)
_registry = None

def _get_registry():
    """Get or create the plugin registry."""
    global _registry
    if _registry is None:
        _registry = plugins.PluginRegistry(validate_strict=False)
        _load_default_plugins(_registry)
    return _registry

def _load_default_plugins(registry):
    """Load default tag suggester plugins."""
    # Try to load plugins
    try:
        # Try NLP tagger - use underscore in import
        import sys
        import os
        # Add plugins to path if needed
        plugins_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'plugins')
        if plugins_path not in sys.path:
            sys.path.insert(0, plugins_path)
        
        from auto_tag_nlp import register_plugins as register_nlp
        register_nlp(registry)
        logger.info("Loaded NLP tag suggester")
    except ImportError as e:
        logger.debug(f"NLP tag suggester not available: {e}")
    
    try:
        # Try LLM tagger
        from auto_tag_llm import register_plugins as register_llm
        register_llm(registry)
        logger.info("Loaded LLM tag suggester")
    except ImportError as e:
        logger.debug(f"LLM tag suggester not available: {e}")


def suggest_tags_for_bookmark(bookmark: Dict[str, Any], 
                             use_plugins: List[str] = None) -> List[str]:
    """
    Suggest tags for a single bookmark using available tag suggesters.
    
    Args:
        bookmark: The bookmark dictionary
        use_plugins: Optional list of specific plugin names to use
        
    Returns:
        List of suggested tags (deduplicated and sorted)
    """
    all_tags = []
    
    # Get all available tag suggesters
    registry = _get_registry()
    suggesters = registry.get_plugins('tag_suggester')
    
    if not suggesters:
        logger.warning("No tag suggesters available")
        return []
    
    # Filter by requested plugins if specified
    if use_plugins:
        suggesters = [s for s in suggesters if s.name in use_plugins]
    
    # Run each suggester
    for suggester in suggesters:
        try:
            tags = suggester.suggest_tags(
                url=bookmark.get('url', ''),
                title=bookmark.get('title'),
                content=bookmark.get('content'),  # If we've extracted content
                description=bookmark.get('description')
            )
            all_tags.extend(tags)
            logger.debug(f"Suggester {suggester.name} suggested: {tags}")
        except Exception as e:
            logger.error(f"Tag suggester {suggester.name} failed: {e}")
    
    # Deduplicate and sort
    unique_tags = sorted(list(set(all_tags)))
    
    # Trigger hook for tag post-processing
    registry = _get_registry()
    hook_results = registry.trigger_hook('tags_suggested', bookmark, unique_tags)
    if hook_results:
        # Allow hooks to modify the tag list
        for result in hook_results:
            if isinstance(result, list):
                unique_tags = result
                break
    
    return unique_tags


def auto_tag_bookmark(bookmark: Dict[str, Any], 
                      replace: bool = False,
                      confidence_threshold: float = 0.0) -> Dict[str, Any]:
    """
    Automatically add tags to a bookmark.
    
    Args:
        bookmark: The bookmark to tag
        replace: If True, replace existing tags; if False, append
        confidence_threshold: Minimum confidence for tags (future use)
        
    Returns:
        Updated bookmark with new tags
    """
    suggested_tags = suggest_tags_for_bookmark(bookmark)
    
    if not suggested_tags:
        logger.info(f"No tags suggested for bookmark {bookmark.get('id')}")
        return bookmark
    
    existing_tags = bookmark.get('tags', [])
    
    if replace:
        bookmark['tags'] = suggested_tags
        logger.info(f"Replaced tags with: {suggested_tags}")
    else:
        # Merge with existing tags
        combined_tags = existing_tags + suggested_tags
        bookmark['tags'] = sorted(list(set(combined_tags)))
        logger.info(f"Added tags: {[t for t in suggested_tags if t not in existing_tags]}")
    
    # Trigger hook for bookmark modification
    registry = _get_registry()
    registry.trigger_hook('bookmark_auto_tagged', bookmark)
    
    return bookmark


def auto_tag_bookmarks(bookmarks: List[Dict[str, Any]],
                       filter_func: Optional[callable] = None,
                       replace: bool = False,
                       dry_run: bool = False) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Auto-tag multiple bookmarks.
    
    Args:
        bookmarks: List of bookmarks to process
        filter_func: Optional function to filter which bookmarks to tag
        replace: If True, replace existing tags; if False, append
        dry_run: If True, don't actually modify bookmarks
        
    Returns:
        Tuple of (modified_bookmarks, statistics)
    """
    stats = {
        'total_processed': 0,
        'total_tagged': 0,
        'total_tags_added': 0,
        'tags_by_plugin': {},
        'most_common_tags': {}
    }
    
    modified_bookmarks = []
    tag_counter = {}
    
    for bookmark in bookmarks:
        # Apply filter if provided
        if filter_func and not filter_func(bookmark):
            modified_bookmarks.append(bookmark)
            continue
        
        stats['total_processed'] += 1
        
        # Get current tags
        original_tags = bookmark.get('tags', [])
        
        if dry_run:
            # Just get suggestions without modifying
            suggested_tags = suggest_tags_for_bookmark(bookmark)
            if suggested_tags:
                stats['total_tagged'] += 1
                new_tags = [t for t in suggested_tags if t not in original_tags]
                stats['total_tags_added'] += len(new_tags)
                
                # Count tag frequency
                for tag in suggested_tags:
                    tag_counter[tag] = tag_counter.get(tag, 0) + 1
            
            modified_bookmarks.append(bookmark)
        else:
            # Actually modify the bookmark
            modified = auto_tag_bookmark(bookmark, replace=replace)
            new_tags = [t for t in modified.get('tags', []) if t not in original_tags]
            
            if new_tags:
                stats['total_tagged'] += 1
                stats['total_tags_added'] += len(new_tags)
                
                # Count tag frequency
                for tag in new_tags:
                    tag_counter[tag] = tag_counter.get(tag, 0) + 1
            
            modified_bookmarks.append(modified)
    
    # Calculate most common tags
    if tag_counter:
        sorted_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)
        stats['most_common_tags'] = dict(sorted_tags[:10])
    
    return modified_bookmarks, stats


def create_filter_for_auto_tag(untagged_only: bool = False,
                               url_pattern: str = None,
                               domain: str = None,
                               no_tags: bool = False,
                               min_tags: int = None,
                               max_tags: int = None) -> callable:
    """
    Create a filter function for auto-tagging operations.
    
    Args:
        untagged_only: Only process bookmarks without tags
        url_pattern: URL pattern to match
        domain: Specific domain to filter
        no_tags: Only process bookmarks with no tags
        min_tags: Minimum number of existing tags
        max_tags: Maximum number of existing tags
        
    Returns:
        Filter function to use with auto_tag_bookmarks
    """
    def filter_func(bookmark: Dict[str, Any]) -> bool:
        # Check untagged condition
        if untagged_only or no_tags:
            if bookmark.get('tags'):
                return False
        
        # Check URL pattern
        if url_pattern:
            import re
            if not re.search(url_pattern, bookmark.get('url', ''), re.IGNORECASE):
                return False
        
        # Check domain
        if domain:
            bookmark_domain = urlparse(bookmark.get('url', '')).netloc.lower()
            if domain.lower() not in bookmark_domain:
                return False
        
        # Check tag count constraints
        tag_count = len(bookmark.get('tags', []))
        if min_tags is not None and tag_count < min_tags:
            return False
        if max_tags is not None and tag_count > max_tags:
            return False
        
        return True
    
    return filter_func


def enrich_bookmark_content(bookmark: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a bookmark with extracted content for better tagging.
    
    Args:
        bookmark: The bookmark to enrich
        
    Returns:
        Bookmark with added content field
    """
    extractors = plugins.get_plugins('content_extractor')
    
    if not extractors:
        logger.warning("No content extractors available")
        return bookmark
    
    # Use the first available extractor
    extractor = extractors[0]
    
    try:
        extracted = extractor.extract(bookmark.get('url', ''))
        
        # Add relevant extracted content to bookmark
        if extracted.get('text'):
            bookmark['content'] = extracted['text'][:5000]  # Limit size
        if extracted.get('keywords'):
            bookmark['meta_keywords'] = extracted['keywords']
        if extracted.get('reading_time'):
            bookmark['reading_time'] = extracted['reading_time']
        if extracted.get('word_count'):
            bookmark['word_count'] = extracted['word_count']
        
        # Update title if we got a better one
        if not bookmark.get('title') and extracted.get('title'):
            bookmark['title'] = extracted['title']
        
        # Update description if we don't have one
        if not bookmark.get('description') and extracted.get('description'):
            bookmark['description'] = extracted['description']
        
        logger.info(f"Enriched bookmark with content from {extractor.name}")
        
    except Exception as e:
        logger.error(f"Content extraction failed: {e}")
    
    return bookmark


def analyze_tagging_coverage(bookmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze the current tagging coverage of bookmarks.
    
    Args:
        bookmarks: List of bookmarks to analyze
        
    Returns:
        Statistics about tagging coverage
    """
    total = len(bookmarks)
    tagged = sum(1 for b in bookmarks if b.get('tags'))
    untagged = total - tagged
    
    tag_counts = {}
    for bookmark in bookmarks:
        for tag in bookmark.get('tags', []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Calculate statistics
    stats = {
        'total_bookmarks': total,
        'tagged_bookmarks': tagged,
        'untagged_bookmarks': untagged,
        'coverage_percentage': (tagged / total * 100) if total > 0 else 0,
        'total_unique_tags': len(tag_counts),
        'average_tags_per_bookmark': sum(len(b.get('tags', [])) for b in bookmarks) / total if total > 0 else 0,
        'most_used_tags': sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20],
        'single_use_tags': sum(1 for count in tag_counts.values() if count == 1),
    }
    
    # Find bookmarks that might benefit from auto-tagging
    candidates = []
    for bookmark in bookmarks:
        if not bookmark.get('tags') or len(bookmark.get('tags', [])) < 2:
            candidates.append({
                'id': bookmark.get('id'),
                'url': bookmark.get('url'),
                'title': bookmark.get('title'),
                'current_tags': bookmark.get('tags', [])
            })
    
    stats['auto_tag_candidates'] = candidates[:10]  # Top 10 candidates
    stats['total_candidates'] = len(candidates)
    
    return stats