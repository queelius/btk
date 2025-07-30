"""
Tests for deduplication functionality.
"""
import pytest
from btk.dedup import (
    find_duplicates,
    merge_bookmark_metadata,
    deduplicate_bookmarks,
    get_duplicate_stats,
    preview_deduplication
)


class TestFindDuplicates:
    """Test duplicate finding functions."""
    
    def test_find_duplicates_by_url(self):
        """Test finding duplicates by URL."""
        bookmarks = [
            {'id': 1, 'url': 'https://example.com', 'title': 'Example 1'},
            {'id': 2, 'url': 'https://example.com', 'title': 'Example 2'},
            {'id': 3, 'url': 'https://different.com', 'title': 'Different'},
            {'id': 4, 'url': 'https://example.com', 'title': 'Example 3'}
        ]
        
        duplicates = find_duplicates(bookmarks, key='url')
        
        assert len(duplicates) == 1
        assert 'https://example.com' in duplicates
        assert len(duplicates['https://example.com']) == 3
        assert all(b['url'] == 'https://example.com' for b in duplicates['https://example.com'])
    
    def test_find_duplicates_by_title(self):
        """Test finding duplicates by title."""
        bookmarks = [
            {'id': 1, 'url': 'https://url1.com', 'title': 'Same Title'},
            {'id': 2, 'url': 'https://url2.com', 'title': 'Same Title'},
            {'id': 3, 'url': 'https://url3.com', 'title': 'Different Title'}
        ]
        
        duplicates = find_duplicates(bookmarks, key='title')
        
        assert len(duplicates) == 1
        assert 'Same Title' in duplicates
        assert len(duplicates['Same Title']) == 2
    
    def test_find_duplicates_no_duplicates(self):
        """Test when there are no duplicates."""
        bookmarks = [
            {'id': 1, 'url': 'https://url1.com'},
            {'id': 2, 'url': 'https://url2.com'},
            {'id': 3, 'url': 'https://url3.com'}
        ]
        
        duplicates = find_duplicates(bookmarks, key='url')
        assert len(duplicates) == 0


class TestMergeBookmarkMetadata:
    """Test metadata merging functions."""
    
    def test_merge_bookmark_metadata(self):
        """Test merging metadata from duplicate bookmarks."""
        bookmarks = [
            {
                'id': 1,
                'url': 'https://example.com',
                'title': 'Example',
                'tags': ['tag1', 'tag2'],
                'description': 'Short desc',
                'stars': False,
                'visit_count': 5,
                'added': '2024-01-01T00:00:00Z',
                'last_visited': '2024-01-05T00:00:00Z'
            },
            {
                'id': 2,
                'url': 'https://example.com',
                'title': 'Example Site - Better Title',
                'tags': ['tag2', 'tag3'],
                'description': 'This is a much longer and better description',
                'stars': True,
                'visit_count': 10,
                'added': '2024-01-02T00:00:00Z',
                'last_visited': '2024-01-10T00:00:00Z'
            }
        ]
        
        merged = merge_bookmark_metadata(bookmarks)
        
        # Check merged tags (union)
        assert set(merged['tags']) == {'tag1', 'tag2', 'tag3'}
        
        # Check summed visit count
        assert merged['visit_count'] == 15
        
        # Check longest description
        assert merged['description'] == 'This is a much longer and better description'
        
        # Check starred (any is starred)
        assert merged['stars'] is True
        
        # Check earliest added date
        assert merged['added'] == '2024-01-01T00:00:00Z'
        
        # Check latest visit date
        assert merged['last_visited'] == '2024-01-10T00:00:00Z'
        
        # Check best title (longer, not URL)
        assert merged['title'] == 'Example Site - Better Title'
    
    def test_merge_empty_bookmarks(self):
        """Test merging empty bookmark list."""
        merged = merge_bookmark_metadata([])
        assert merged == {}


class TestDeduplicateBookmarks:
    """Test deduplication strategies."""
    
    def test_deduplicate_merge_strategy(self):
        """Test deduplication with merge strategy."""
        bookmarks = [
            {'id': 1, 'url': 'https://example.com', 'tags': ['tag1'], 'visit_count': 5},
            {'id': 2, 'url': 'https://example.com', 'tags': ['tag2'], 'visit_count': 10},
            {'id': 3, 'url': 'https://different.com', 'tags': ['tag3'], 'visit_count': 2}
        ]
        
        deduplicated, removed = deduplicate_bookmarks(bookmarks, strategy='merge')
        
        assert len(deduplicated) == 2
        assert len(removed) == 2  # Both duplicates are "removed" as they're merged
        
        # Find the merged bookmark
        merged = next(b for b in deduplicated if b['url'] == 'https://example.com')
        assert set(merged['tags']) == {'tag1', 'tag2'}
        assert merged['visit_count'] == 15
    
    def test_deduplicate_keep_first_strategy(self):
        """Test deduplication with keep_first strategy."""
        bookmarks = [
            {'id': 1, 'url': 'https://example.com', 'title': 'First'},
            {'id': 2, 'url': 'https://example.com', 'title': 'Second'},
            {'id': 3, 'url': 'https://example.com', 'title': 'Third'}
        ]
        
        deduplicated, removed = deduplicate_bookmarks(bookmarks, strategy='keep_first')
        
        assert len(deduplicated) == 1
        assert len(removed) == 2
        assert deduplicated[0]['title'] == 'First'
    
    def test_deduplicate_keep_last_strategy(self):
        """Test deduplication with keep_last strategy."""
        bookmarks = [
            {'id': 1, 'url': 'https://example.com', 'title': 'First'},
            {'id': 2, 'url': 'https://example.com', 'title': 'Second'},
            {'id': 3, 'url': 'https://example.com', 'title': 'Third'}
        ]
        
        deduplicated, removed = deduplicate_bookmarks(bookmarks, strategy='keep_last')
        
        assert len(deduplicated) == 1
        assert len(removed) == 2
        assert deduplicated[0]['title'] == 'Third'
    
    def test_deduplicate_keep_most_visited_strategy(self):
        """Test deduplication with keep_most_visited strategy."""
        bookmarks = [
            {'id': 1, 'url': 'https://example.com', 'visit_count': 5},
            {'id': 2, 'url': 'https://example.com', 'visit_count': 15},
            {'id': 3, 'url': 'https://example.com', 'visit_count': 10}
        ]
        
        deduplicated, removed = deduplicate_bookmarks(bookmarks, strategy='keep_most_visited')
        
        assert len(deduplicated) == 1
        assert len(removed) == 2
        assert deduplicated[0]['visit_count'] == 15
    
    def test_deduplicate_no_duplicates(self):
        """Test deduplication when there are no duplicates."""
        bookmarks = [
            {'id': 1, 'url': 'https://url1.com'},
            {'id': 2, 'url': 'https://url2.com'},
            {'id': 3, 'url': 'https://url3.com'}
        ]
        
        deduplicated, removed = deduplicate_bookmarks(bookmarks, strategy='merge')
        
        assert len(deduplicated) == 3
        assert len(removed) == 0
        assert deduplicated == bookmarks


class TestDuplicateStats:
    """Test duplicate statistics functions."""
    
    def test_get_duplicate_stats(self):
        """Test getting duplicate statistics."""
        bookmarks = [
            {'id': 1, 'url': 'https://example.com'},
            {'id': 2, 'url': 'https://example.com'},
            {'id': 3, 'url': 'https://example.com'},
            {'id': 4, 'url': 'https://different.com'},
            {'id': 5, 'url': 'https://different.com'},
            {'id': 6, 'url': 'https://unique.com'}
        ]
        
        stats = get_duplicate_stats(bookmarks)
        
        assert stats['total_bookmarks'] == 6
        assert stats['duplicate_groups'] == 2  # example.com and different.com
        assert stats['total_duplicates'] == 5  # 3 + 2
        assert stats['bookmarks_to_remove'] == 3  # 5 - 2
        assert stats['duplicate_percentage'] == pytest.approx(83.33, 0.01)
        
        # Check most duplicated
        assert len(stats['most_duplicated']) >= 2
        assert stats['most_duplicated'][0][0] == 'https://example.com'
        assert stats['most_duplicated'][0][1] == 3
    
    def test_get_duplicate_stats_empty(self):
        """Test duplicate stats with empty bookmarks."""
        stats = get_duplicate_stats([])
        
        assert stats['total_bookmarks'] == 0
        assert stats['duplicate_groups'] == 0
        assert stats['duplicate_percentage'] == 0


class TestPreviewDeduplication:
    """Test deduplication preview."""
    
    def test_preview_deduplication(self):
        """Test previewing deduplication results."""
        bookmarks = [
            {'id': 1, 'url': 'https://example.com', 'title': 'First'},
            {'id': 2, 'url': 'https://example.com', 'title': 'Second'},
            {'id': 3, 'url': 'https://different.com', 'title': 'Different'}
        ]
        
        # Preview should not modify original
        preview = preview_deduplication(bookmarks, strategy='keep_first')
        
        assert len(preview) == 2
        assert len(bookmarks) == 3  # Original unchanged
        assert preview[0]['title'] == 'First'
        assert preview[1]['title'] == 'Different'