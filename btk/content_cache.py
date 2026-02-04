"""
Content caching system for BTK.

This module provides a persistent LRU cache for webpage content to avoid
redundant fetches and enable offline content operations.
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from collections import OrderedDict
import pickle

logger = logging.getLogger(__name__)


class ContentCache:
    """
    LRU cache for webpage content with persistent storage.
    
    Stores content in both memory (for fast access) and disk (for persistence).
    Content is stored as structured data that can be used for various operations.
    """
    
    def __init__(self, cache_dir: Optional[str] = None, max_memory_items: int = 100, 
                 max_disk_items: int = 10000, ttl_days: int = 30):
        """
        Initialize the content cache.
        
        Args:
            cache_dir: Directory for persistent cache storage
            max_memory_items: Maximum items to keep in memory
            max_disk_items: Maximum items to keep on disk
            ttl_days: Time-to-live for cached content in days
        """
        if cache_dir is None:
            cache_dir = os.path.expanduser("~/.btk/content_cache")
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_memory_items = max_memory_items
        self.max_disk_items = max_disk_items
        self.ttl_seconds = ttl_days * 24 * 60 * 60
        
        # Memory cache (LRU)
        self.memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        
        # Index file for disk cache
        self.index_file = self.cache_dir / "index.json"
        self.disk_index = self._load_index()
        
        # Stats
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'updates': 0
        }
    
    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()
    
    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        """Load the disk cache index."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cache index: {e}")
        return {}
    
    def _save_index(self):
        """Save the disk cache index."""
        try:
            with open(self.index_file, 'w') as f:
                json.dump(self.disk_index, f)
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")
    
    def _evict_from_memory(self):
        """Evict least recently used item from memory cache."""
        if len(self.memory_cache) >= self.max_memory_items:
            # Remove least recently used (first item)
            evicted = self.memory_cache.popitem(last=False)
            self.stats['evictions'] += 1
            logger.debug(f"Evicted from memory: {evicted[0]}")
    
    def _evict_from_disk(self):
        """Evict oldest items from disk cache."""
        if len(self.disk_index) >= self.max_disk_items:
            # Sort by access time and remove oldest
            sorted_items = sorted(self.disk_index.items(), 
                                key=lambda x: x[1].get('accessed', 0))
            
            # Remove oldest 10% to avoid frequent evictions
            to_remove = max(1, len(sorted_items) // 10)
            
            for key, _ in sorted_items[:to_remove]:
                cache_file = self.cache_dir / f"{key}.pkl"
                if cache_file.exists():
                    cache_file.unlink()
                del self.disk_index[key]
                self.stats['evictions'] += 1
            
            self._save_index()
    
    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get cached content for a URL.
        
        Args:
            url: The URL to look up
            
        Returns:
            Cached content dictionary or None if not found/expired
        """
        cache_key = self._get_cache_key(url)
        current_time = time.time()
        
        # Check memory cache first
        if cache_key in self.memory_cache:
            content = self.memory_cache[cache_key]
            
            # Check if expired
            if current_time - content.get('cached_at', 0) > self.ttl_seconds:
                del self.memory_cache[cache_key]
                logger.debug(f"Memory cache expired for {url}")
                self.stats['misses'] += 1
                return None
            
            # Move to end (most recently used)
            self.memory_cache.move_to_end(cache_key)
            self.stats['hits'] += 1
            logger.debug(f"Memory cache hit for {url}")
            return content.get('data')
        
        # Check disk cache
        if cache_key in self.disk_index:
            cache_info = self.disk_index[cache_key]
            
            # Check if expired
            if current_time - cache_info.get('cached_at', 0) > self.ttl_seconds:
                # Remove expired entry
                cache_file = self.cache_dir / f"{cache_key}.pkl"
                if cache_file.exists():
                    cache_file.unlink()
                del self.disk_index[cache_key]
                self._save_index()
                logger.debug(f"Disk cache expired for {url}")
                self.stats['misses'] += 1
                return None
            
            # Load from disk
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            if cache_file.exists():
                try:
                    with open(cache_file, 'rb') as f:
                        content = pickle.load(f)
                    
                    # Update access time
                    self.disk_index[cache_key]['accessed'] = current_time
                    self._save_index()
                    
                    # Add to memory cache
                    self._evict_from_memory()
                    self.memory_cache[cache_key] = content
                    
                    self.stats['hits'] += 1
                    logger.debug(f"Disk cache hit for {url}")
                    return content.get('data')
                    
                except Exception as e:
                    logger.error(f"Failed to load cached content: {e}")
                    # Remove corrupted entry
                    del self.disk_index[cache_key]
                    self._save_index()
        
        self.stats['misses'] += 1
        logger.debug(f"Cache miss for {url}")
        return None
    
    def set(self, url: str, content: Dict[str, Any], force_update: bool = False):
        """
        Cache content for a URL.
        
        Args:
            url: The URL to cache
            content: The content to cache
            force_update: Force update even if already cached
        """
        cache_key = self._get_cache_key(url)
        current_time = time.time()
        
        # Check if already cached and not forcing update
        if not force_update and cache_key in self.memory_cache:
            cached_time = self.memory_cache[cache_key].get('cached_at', 0)
            if current_time - cached_time < self.ttl_seconds:
                logger.debug(f"Content already cached for {url}")
                return
        
        # Prepare cache entry
        cache_entry = {
            'url': url,
            'data': content,
            'cached_at': current_time,
            'accessed': current_time
        }
        
        # Add to memory cache
        self._evict_from_memory()
        self.memory_cache[cache_key] = cache_entry
        
        # Save to disk
        self._evict_from_disk()
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_entry, f)
            
            # Update disk index
            self.disk_index[cache_key] = {
                'url': url,
                'cached_at': current_time,
                'accessed': current_time,
                'size': cache_file.stat().st_size
            }
            self._save_index()
            
            if force_update:
                self.stats['updates'] += 1
            
            logger.info(f"Cached content for {url}")
            
        except Exception as e:
            logger.error(f"Failed to cache content: {e}")
    
    def invalidate(self, url: str):
        """Invalidate cached content for a URL."""
        cache_key = self._get_cache_key(url)
        
        # Remove from memory cache
        if cache_key in self.memory_cache:
            del self.memory_cache[cache_key]
        
        # Remove from disk cache
        if cache_key in self.disk_index:
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            if cache_file.exists():
                cache_file.unlink()
            del self.disk_index[cache_key]
            self._save_index()
        
        logger.info(f"Invalidated cache for {url}")
    
    def clear(self):
        """Clear all cached content."""
        self.memory_cache.clear()
        
        # Remove all cache files
        for cache_file in self.cache_dir.glob("*.pkl"):
            cache_file.unlink()
        
        self.disk_index.clear()
        self._save_index()
        
        logger.info("Cleared all cached content")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            **self.stats,
            'memory_items': len(self.memory_cache),
            'disk_items': len(self.disk_index),
            'cache_dir': str(self.cache_dir),
            'hit_rate': self.stats['hits'] / max(1, self.stats['hits'] + self.stats['misses'])
        }
    
    def export_as_markdown(self, url: str, output_file: Optional[str] = None) -> Optional[str]:
        """
        Export cached content as Markdown.
        
        Args:
            url: The URL to export
            output_file: Optional file to save to
            
        Returns:
            Markdown string or None if not cached
        """
        content = self.get(url)
        if not content:
            return None
        
        # Convert to Markdown
        lines = []
        
        # Title
        if content.get('title'):
            lines.append(f"# {content['title']}\n")
        
        # Metadata
        lines.append(f"**URL:** {url}")
        if content.get('author'):
            lines.append(f"**Author:** {content['author']}")
        if content.get('published_date'):
            lines.append(f"**Published:** {content['published_date']}")
        if content.get('reading_time'):
            lines.append(f"**Reading Time:** {content['reading_time']} minutes")
        lines.append("")
        
        # Description
        if content.get('description'):
            lines.append(f"> {content['description']}\n")
        
        # Keywords/Tags
        if content.get('keywords'):
            lines.append(f"**Keywords:** {', '.join(content['keywords'])}\n")
        
        # Main content
        if content.get('text'):
            lines.append("## Content\n")
            # Split into paragraphs
            paragraphs = content['text'].split('\n\n')
            for para in paragraphs[:20]:  # Limit to first 20 paragraphs
                if para.strip():
                    lines.append(para.strip())
                    lines.append("")
        
        # Links
        if content.get('links'):
            lines.append("\n## Links\n")
            for link in content['links'][:10]:
                text = link.get('text', 'Link')
                url = link.get('url', '')
                if url:
                    lines.append(f"- [{text}]({url})")
        
        markdown = "\n".join(lines)
        
        # Save if output file specified
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(markdown)
            logger.info(f"Exported content to {output_file}")
        
        return markdown


# Global cache instance
_content_cache = None


def get_cache() -> ContentCache:
    """Get the global content cache instance."""
    global _content_cache
    if _content_cache is None:
        _content_cache = ContentCache()
    return _content_cache


def search_cached_content(query: str, bookmarks: list) -> list:
    """
    Search through cached content for bookmarks.
    
    Args:
        query: Search query
        bookmarks: List of bookmarks to search
        
    Returns:
        List of matching bookmarks with relevance scores
    """
    cache = get_cache()
    results = []
    query_lower = query.lower()
    
    for bookmark in bookmarks:
        url = bookmark.get('url')
        if not url:
            continue
        
        # Get cached content
        content = cache.get(url)
        if not content:
            continue
        
        # Search in various fields
        score = 0
        matches = []
        
        # Search in title
        title = content.get('title', '')
        if query_lower in title.lower():
            score += 10
            matches.append('title')
        
        # Search in description
        description = content.get('description', '')
        if query_lower in description.lower():
            score += 5
            matches.append('description')
        
        # Search in main text
        text = content.get('text', '')
        if query_lower in text.lower():
            # Count occurrences
            occurrences = text.lower().count(query_lower)
            score += min(occurrences, 10)  # Cap at 10 points
            matches.append(f'text ({occurrences} times)')
        
        # Search in keywords
        keywords = content.get('keywords', [])
        for keyword in keywords:
            if query_lower in keyword.lower():
                score += 3
                matches.append('keywords')
                break
        
        if score > 0:
            results.append({
                'bookmark': bookmark,
                'score': score,
                'matches': matches,
                'snippet': _extract_snippet(text, query_lower)
            })
    
    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)
    return results


def _extract_snippet(text: str, query: str, context_chars: int = 100) -> str:
    """Extract a text snippet around the query match."""
    if not text or not query:
        return ""
    
    text_lower = text.lower()
    pos = text_lower.find(query)
    
    if pos == -1:
        return text[:200] + "..." if len(text) > 200 else text
    
    # Extract context around match
    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(query) + context_chars)
    
    snippet = text[start:end]
    
    # Add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    
    return snippet