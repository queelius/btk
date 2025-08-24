"""
Tests for content cache functionality.
"""

import pytest
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from btk.content_cache import ContentCache, get_cache, search_cached_content, _extract_snippet


class TestContentCache:
    """Test ContentCache class."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for cache testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def cache(self, temp_cache_dir):
        """Create a cache instance with temporary directory."""
        return ContentCache(
            cache_dir=temp_cache_dir,
            max_memory_items=2,
            max_disk_items=5,
            ttl_days=1
        )
    
    def test_cache_initialization(self, cache, temp_cache_dir):
        """Test cache initialization."""
        assert cache.cache_dir == Path(temp_cache_dir)
        assert cache.max_memory_items == 2
        assert cache.max_disk_items == 5
        assert cache.ttl_seconds == 86400
        assert len(cache.memory_cache) == 0
        assert len(cache.disk_index) == 0
    
    def test_cache_set_and_get(self, cache):
        """Test setting and getting cached content."""
        url = "https://example.com"
        content = {
            'title': 'Example Page',
            'text': 'This is example content',
            'description': 'An example page'
        }
        
        # Set content
        cache.set(url, content)
        
        # Get content
        retrieved = cache.get(url)
        assert retrieved == content
        assert cache.stats['hits'] == 1
    
    def test_cache_miss(self, cache):
        """Test cache miss."""
        result = cache.get("https://nonexistent.com")
        assert result is None
        assert cache.stats['misses'] == 1
    
    def test_memory_cache_eviction(self, cache):
        """Test LRU eviction from memory cache."""
        # Add items up to max_memory_items
        cache.set("https://example1.com", {'data': 1})
        cache.set("https://example2.com", {'data': 2})
        assert len(cache.memory_cache) == 2
        
        # Add one more - should evict the least recently used
        cache.set("https://example3.com", {'data': 3})
        assert len(cache.memory_cache) == 2
        assert cache.stats['evictions'] == 1
        
        # First item should be evicted from memory (but still on disk)
        cache_key1 = cache._get_cache_key("https://example1.com")
        assert cache_key1 not in cache.memory_cache
        assert cache_key1 in cache.disk_index
    
    def test_disk_cache_eviction(self, cache):
        """Test eviction from disk cache."""
        # Add items up to max_disk_items
        for i in range(6):
            cache.set(f"https://example{i}.com", {'data': i})
        
        # Should have evicted some items
        assert len(cache.disk_index) <= cache.max_disk_items
        assert cache.stats['evictions'] > 0
    
    def test_cache_expiration(self, cache):
        """Test TTL expiration."""
        url = "https://example.com"
        content = {'data': 'test'}
        
        # Set content
        current_time = time.time()
        cache.set(url, content)
        
        # Mock time to simulate expiration - patch where it's used
        with patch('btk.content_cache.time.time') as mock_time:
            # Return a time in the future past TTL
            mock_time.return_value = current_time + cache.ttl_seconds + 1
            
            result = cache.get(url)
            assert result is None
            assert cache.stats['misses'] == 1
    
    def test_cache_invalidation(self, cache):
        """Test cache invalidation."""
        url = "https://example.com"
        content = {'data': 'test'}
        
        cache.set(url, content)
        assert cache.get(url) is not None
        
        cache.invalidate(url)
        assert cache.get(url) is None
    
    def test_cache_clear(self, cache):
        """Test clearing all cached content."""
        # Add multiple items
        cache.set("https://example1.com", {'data': 1})
        cache.set("https://example2.com", {'data': 2})
        
        cache.clear()
        
        assert len(cache.memory_cache) == 0
        assert len(cache.disk_index) == 0
        assert cache.get("https://example1.com") is None
    
    def test_cache_stats(self, cache):
        """Test cache statistics."""
        cache.set("https://example.com", {'data': 'test'})
        cache.get("https://example.com")  # Hit
        cache.get("https://nonexistent.com")  # Miss
        
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['memory_items'] == 1
        assert stats['disk_items'] == 1
        assert 0 <= stats['hit_rate'] <= 1
    
    def test_export_as_markdown(self, cache, tmp_path):
        """Test markdown export of cached content."""
        url = "https://example.com"
        content = {
            'title': 'Example Page',
            'text': 'This is the main content of the page.',
            'description': 'A test page',
            'author': 'Test Author',
            'keywords': ['test', 'example'],
            'reading_time': 2,
            'links': [
                {'url': 'https://link1.com', 'text': 'Link 1'},
                {'url': 'https://link2.com', 'text': 'Link 2'}
            ]
        }
        
        cache.set(url, content)
        
        # Export to string
        markdown = cache.export_as_markdown(url)
        assert markdown is not None
        assert 'Example Page' in markdown
        assert 'Test Author' in markdown
        assert 'test, example' in markdown
        
        # Export to file
        output_file = tmp_path / "export.md"
        cache.export_as_markdown(url, str(output_file))
        assert output_file.exists()
        with open(output_file) as f:
            file_content = f.read()
            assert 'Example Page' in file_content
    
    def test_force_update(self, cache):
        """Test force update of cached content."""
        url = "https://example.com"
        content1 = {'data': 'version1'}
        content2 = {'data': 'version2'}
        
        cache.set(url, content1)
        assert cache.get(url) == content1
        
        # Try to set again without force (should not update)
        cache.set(url, content2)
        assert cache.get(url) == content1
        
        # Force update
        cache.set(url, content2, force_update=True)
        assert cache.get(url) == content2
        assert cache.stats['updates'] == 1


class TestSearchCachedContent:
    """Test search functionality in cached content."""
    
    @pytest.fixture
    def cache_with_content(self):
        """Create cache with sample content."""
        cache = get_cache()
        cache.clear()
        
        # Add test content
        cache.set("https://python.org", {
            'title': 'Python Programming Language',
            'text': 'Python is a high-level programming language.',
            'description': 'Official Python website',
            'keywords': ['python', 'programming', 'language']
        })
        
        cache.set("https://javascript.com", {
            'title': 'JavaScript Guide',
            'text': 'JavaScript is the programming language of the web.',
            'description': 'Learn JavaScript',
            'keywords': ['javascript', 'web', 'programming']
        })
        
        return cache
    
    def test_search_in_title(self, cache_with_content):
        """Test searching in title."""
        bookmarks = [
            {'url': 'https://python.org'},
            {'url': 'https://javascript.com'}
        ]
        
        results = search_cached_content('Python', bookmarks)
        assert len(results) == 1
        assert results[0]['bookmark']['url'] == 'https://python.org'
        assert 'title' in results[0]['matches']
    
    def test_search_in_text(self, cache_with_content):
        """Test searching in text content."""
        bookmarks = [
            {'url': 'https://python.org'},
            {'url': 'https://javascript.com'}
        ]
        
        results = search_cached_content('programming', bookmarks)
        assert len(results) == 2  # Both have 'programming' in text
    
    def test_search_scoring(self, cache_with_content):
        """Test search result scoring."""
        bookmarks = [
            {'url': 'https://python.org'},
            {'url': 'https://javascript.com'}
        ]
        
        results = search_cached_content('python', bookmarks)
        assert len(results) == 1
        assert results[0]['score'] > 0
        
        # Title match should score higher
        python_result = results[0]
        assert 'title' in python_result['matches']
    
    def test_extract_snippet(self):
        """Test snippet extraction."""
        text = "This is a long text with the word Python in the middle of it and more text after."
        query = "python"
        
        snippet = _extract_snippet(text, query, context_chars=20)
        assert 'Python' in snippet
        assert '...' in snippet  # Should have ellipsis
    
    def test_search_no_cache(self):
        """Test search with no cached content."""
        cache = get_cache()
        cache.clear()
        
        bookmarks = [{'url': 'https://uncached.com'}]
        results = search_cached_content('test', bookmarks)
        assert len(results) == 0


class TestGlobalCache:
    """Test global cache instance."""
    
    def test_singleton_cache(self):
        """Test that get_cache returns singleton."""
        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2