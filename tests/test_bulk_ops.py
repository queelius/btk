"""
Tests for bulk operations.
"""
import pytest
import os
import tempfile
from unittest.mock import patch, Mock

from btk.bulk_ops import (
    bulk_add_from_file,
    bulk_edit_bookmarks,
    bulk_remove_bookmarks,
    create_filter_from_criteria,
    parse_urls_from_text,
    fetch_url_title
)


class TestBulkAdd:
    """Test bulk add operations."""
    
    def test_bulk_add_from_file(self, temp_lib_dir):
        """Test bulk adding bookmarks from file."""
        # Create a file with URLs
        url_file = os.path.join(temp_lib_dir, 'urls.txt')
        with open(url_file, 'w') as f:
            f.write("""
https://example.com
https://test.org
# This is a comment
https://python.org

https://github.com
""")
        
        existing_bookmarks = []
        
        # Mock fetch_url_title to avoid network calls
        with patch('btk.bulk_ops.fetch_url_title') as mock_fetch:
            mock_fetch.side_effect = lambda url: f"Title for {url}"
            
            bookmarks, success_count, failed_urls = bulk_add_from_file(
                url_file, existing_bookmarks, temp_lib_dir,
                default_tags=['bulk', 'imported']
            )
        
        assert success_count == 4
        assert len(failed_urls) == 0
        assert len(bookmarks) == 4
        
        # Check bookmarks were added correctly
        urls = [b['url'] for b in bookmarks]
        assert 'https://example.com' in urls
        assert 'https://test.org' in urls
        assert 'https://python.org' in urls
        assert 'https://github.com' in urls
        
        # Check tags were applied
        for bookmark in bookmarks:
            assert 'bulk' in bookmark['tags']
            assert 'imported' in bookmark['tags']
    
    def test_bulk_add_skip_duplicates(self, temp_lib_dir):
        """Test that bulk add skips existing URLs."""
        url_file = os.path.join(temp_lib_dir, 'urls.txt')
        with open(url_file, 'w') as f:
            f.write("https://example.com\nhttps://test.org")
        
        existing_bookmarks = [
            {'url': 'https://example.com', 'title': 'Existing'}
        ]
        
        with patch('btk.bulk_ops.fetch_url_title') as mock_fetch:
            mock_fetch.return_value = "New Title"
            
            bookmarks, success_count, failed_urls = bulk_add_from_file(
                url_file, existing_bookmarks, temp_lib_dir
            )
        
        assert success_count == 1  # Only test.org added
        assert len(bookmarks) == 2
        assert bookmarks[0]['title'] == 'Existing'  # Original unchanged
    
    def test_bulk_add_no_fetch_titles(self, temp_lib_dir):
        """Test bulk add without fetching titles."""
        url_file = os.path.join(temp_lib_dir, 'urls.txt')
        with open(url_file, 'w') as f:
            f.write("https://example.com")
        
        bookmarks, success_count, failed_urls = bulk_add_from_file(
            url_file, [], temp_lib_dir, fetch_titles=False
        )
        
        assert success_count == 1
        assert bookmarks[0]['title'] == 'example.com'  # Domain as title


class TestBulkEdit:
    """Test bulk edit operations."""
    
    def test_bulk_edit_add_tags(self):
        """Test bulk editing to add tags."""
        bookmarks = [
            {'id': 1, 'tags': ['old'], 'stars': False},
            {'id': 2, 'tags': [], 'stars': False},
            {'id': 3, 'tags': ['keep'], 'stars': True}
        ]
        
        # Edit all bookmarks
        filter_func = lambda b: True
        
        bookmarks, edited_count = bulk_edit_bookmarks(
            bookmarks, filter_func, add_tags=['new', 'bulk']
        )
        
        assert edited_count == 3
        for bookmark in bookmarks:
            assert 'new' in bookmark['tags']
            assert 'bulk' in bookmark['tags']
    
    def test_bulk_edit_remove_tags(self):
        """Test bulk editing to remove tags."""
        bookmarks = [
            {'id': 1, 'tags': ['remove', 'keep']},
            {'id': 2, 'tags': ['remove', 'also-keep']},
            {'id': 3, 'tags': ['only-this']}
        ]
        
        filter_func = lambda b: True
        
        bookmarks, edited_count = bulk_edit_bookmarks(
            bookmarks, filter_func, remove_tags=['remove']
        )
        
        assert edited_count == 3
        assert 'keep' in bookmarks[0]['tags']
        assert 'remove' not in bookmarks[0]['tags']
        assert 'also-keep' in bookmarks[1]['tags']
        assert 'remove' not in bookmarks[1]['tags']
    
    def test_bulk_edit_set_properties(self):
        """Test bulk editing to set properties."""
        bookmarks = [
            {'id': 1, 'stars': False, 'description': ''},
            {'id': 2, 'stars': True, 'description': 'old'}
        ]
        
        filter_func = lambda b: True
        
        bookmarks, edited_count = bulk_edit_bookmarks(
            bookmarks, filter_func,
            set_stars=True,
            set_description='Bulk updated'
        )
        
        assert edited_count == 2
        for bookmark in bookmarks:
            assert bookmark['stars'] is True
            assert bookmark['description'] == 'Bulk updated'
    
    def test_bulk_edit_with_filter(self):
        """Test bulk editing with filter."""
        bookmarks = [
            {'id': 1, 'tags': ['edit-me'], 'stars': False},
            {'id': 2, 'tags': ['skip'], 'stars': False},
            {'id': 3, 'tags': ['edit-me', 'other'], 'stars': True}
        ]
        
        # Only edit bookmarks with 'edit-me' tag
        filter_func = lambda b: 'edit-me' in b.get('tags', [])
        
        bookmarks, edited_count = bulk_edit_bookmarks(
            bookmarks, filter_func, set_stars=True
        )
        
        assert edited_count == 2
        assert bookmarks[0]['stars'] is True
        assert bookmarks[1]['stars'] is False  # Not edited
        assert bookmarks[2]['stars'] is True


class TestBulkRemove:
    """Test bulk remove operations."""
    
    def test_bulk_remove_with_filter(self):
        """Test bulk removing bookmarks."""
        bookmarks = [
            {'id': 1, 'tags': ['remove-me']},
            {'id': 2, 'tags': ['keep']},
            {'id': 3, 'tags': ['remove-me', 'other']},
            {'id': 4, 'tags': []}
        ]
        
        # Remove bookmarks with 'remove-me' tag
        filter_func = lambda b: 'remove-me' in b.get('tags', [])
        
        remaining, removed = bulk_remove_bookmarks(bookmarks, filter_func)
        
        assert len(remaining) == 2
        assert len(removed) == 2
        
        # Check IDs were reindexed
        assert remaining[0]['id'] == 1
        assert remaining[1]['id'] == 2
        
        # Check correct bookmarks were removed
        assert remaining[0]['tags'] == ['keep']
        assert remaining[1]['tags'] == []


class TestFilterCreation:
    """Test filter creation functions."""
    
    def test_create_filter_tag_prefix(self):
        """Test creating filter for tag prefix."""
        filter_func = create_filter_from_criteria(tag_prefix='programming')
        
        assert filter_func({'tags': ['programming/python']}) is True
        assert filter_func({'tags': ['programming']}) is True
        assert filter_func({'tags': ['other']}) is False
        assert filter_func({'tags': []}) is False
    
    def test_create_filter_url_pattern(self):
        """Test creating filter for URL pattern."""
        filter_func = create_filter_from_criteria(url_pattern='github.com')
        
        assert filter_func({'url': 'https://github.com/user/repo'}) is True
        assert filter_func({'url': 'https://example.com'}) is False
    
    def test_create_filter_visit_range(self):
        """Test creating filter for visit count range."""
        filter_func = create_filter_from_criteria(min_visits=5, max_visits=10)
        
        assert filter_func({'visit_count': 7}) is True
        assert filter_func({'visit_count': 5}) is True
        assert filter_func({'visit_count': 10}) is True
        assert filter_func({'visit_count': 3}) is False
        assert filter_func({'visit_count': 15}) is False
    
    def test_create_filter_starred(self):
        """Test creating filter for starred status."""
        filter_func = create_filter_from_criteria(is_starred=True)
        
        assert filter_func({'stars': True}) is True
        assert filter_func({'stars': False}) is False
    
    def test_create_filter_combined(self):
        """Test creating filter with multiple criteria."""
        filter_func = create_filter_from_criteria(
            tag_prefix='dev',
            is_starred=True,
            min_visits=1
        )
        
        # Must match all criteria
        assert filter_func({
            'tags': ['dev/tools'],
            'stars': True,
            'visit_count': 5
        }) is True
        
        # Missing starred
        assert filter_func({
            'tags': ['dev/tools'],
            'stars': False,
            'visit_count': 5
        }) is False


class TestUrlParsing:
    """Test URL parsing functions."""
    
    def test_parse_urls_from_text(self):
        """Test extracting URLs from text."""
        text = """
        Check out https://example.com for more info.
        Also see http://test.org and https://github.com/user/repo
        
        Here's a [markdown link](https://markdown.example.com)
        And another [one](http://another.com)
        
        Not a URL: ftp://oldschool.com
        """
        
        urls = parse_urls_from_text(text)
        
        assert len(urls) == 5
        assert 'https://example.com' in urls
        assert 'http://test.org' in urls
        assert 'https://github.com/user/repo' in urls
        assert 'https://markdown.example.com' in urls
        assert 'http://another.com' in urls
        assert 'ftp://oldschool.com' not in urls
    
    def test_parse_urls_no_duplicates(self):
        """Test that URL parsing removes duplicates."""
        text = """
        https://example.com
        https://example.com
        [Example](https://example.com)
        """
        
        urls = parse_urls_from_text(text)
        assert len(urls) == 1
        assert urls[0] == 'https://example.com'