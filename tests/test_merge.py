"""
Unit tests for the merge module.

Tests the set operations on bookmark libraries: union, intersection, and difference.
"""
import pytest
import json
import os
import tempfile
import shutil
from pathlib import Path
from btk import merge


class TestMergeOperations:
    """Test bookmark library merge operations."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test libraries."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    @pytest.fixture
    def create_library(self, temp_dir):
        """Factory to create test bookmark libraries."""
        def _create(name, bookmarks):
            lib_dir = Path(temp_dir) / name
            lib_dir.mkdir()
            with open(lib_dir / 'bookmarks.json', 'w') as f:
                json.dump(bookmarks, f)
            return str(lib_dir)
        return _create
    
    @pytest.fixture
    def sample_bookmarks(self):
        """Sample bookmarks for testing."""
        return {
            'lib1': [
                {'id': 1, 'unique_id': 'abc123', 'title': 'Site A', 'url': 'https://a.com'},
                {'id': 2, 'unique_id': 'def456', 'title': 'Site B', 'url': 'https://b.com'},
                {'id': 3, 'unique_id': 'ghi789', 'title': 'Site C', 'url': 'https://c.com'},
            ],
            'lib2': [
                {'id': 1, 'unique_id': 'def456', 'title': 'Site B', 'url': 'https://b.com'},
                {'id': 2, 'unique_id': 'ghi789', 'title': 'Site C', 'url': 'https://c.com'},
                {'id': 3, 'unique_id': 'jkl012', 'title': 'Site D', 'url': 'https://d.com'},
            ],
            'lib3': [
                {'id': 1, 'unique_id': 'ghi789', 'title': 'Site C', 'url': 'https://c.com'},
                {'id': 2, 'unique_id': 'mno345', 'title': 'Site E', 'url': 'https://e.com'},
            ]
        }
    
    def test_union_libraries(self, temp_dir, create_library, sample_bookmarks):
        """Test union of multiple bookmark libraries."""
        # Create test libraries
        lib1 = create_library('lib1', sample_bookmarks['lib1'])
        lib2 = create_library('lib2', sample_bookmarks['lib2'])
        output_dir = Path(temp_dir) / 'union_output'
        
        # Perform union
        merge.union_libraries([lib1, lib2], str(output_dir))
        
        # Check results
        assert output_dir.exists()
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        # Should have all unique bookmarks from both libraries
        unique_ids = {b['unique_id'] for b in result}
        assert unique_ids == {'abc123', 'def456', 'ghi789', 'jkl012'}
        assert len(result) == 4
    
    def test_union_single_library(self, temp_dir, create_library, sample_bookmarks):
        """Test union with a single library."""
        lib1 = create_library('lib1', sample_bookmarks['lib1'])
        output_dir = Path(temp_dir) / 'union_single'
        
        merge.union_libraries([lib1], str(output_dir))
        
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        assert len(result) == 3
        assert all(b['unique_id'] in ['abc123', 'def456', 'ghi789'] for b in result)
    
    def test_union_empty_library(self, temp_dir, create_library):
        """Test union with an empty library."""
        lib1 = create_library('lib1', [])
        lib2 = create_library('lib2', [{'id': 1, 'unique_id': 'test', 'title': 'Test', 'url': 'https://test.com'}])
        output_dir = Path(temp_dir) / 'union_empty'
        
        merge.union_libraries([lib1, lib2], str(output_dir))
        
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        assert len(result) == 1
        assert result[0]['unique_id'] == 'test'
    
    def test_intersection_libraries(self, temp_dir, create_library, sample_bookmarks):
        """Test intersection of multiple bookmark libraries."""
        lib1 = create_library('lib1', sample_bookmarks['lib1'])
        lib2 = create_library('lib2', sample_bookmarks['lib2'])
        lib3 = create_library('lib3', sample_bookmarks['lib3'])
        output_dir = Path(temp_dir) / 'intersection_output'
        
        # Perform intersection
        merge.intersection_libraries([lib1, lib2, lib3], str(output_dir))
        
        # Check results
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        # Only 'ghi789' (Site C) is in all three libraries
        assert len(result) == 1
        assert result[0]['unique_id'] == 'ghi789'
    
    def test_intersection_no_common(self, temp_dir, create_library):
        """Test intersection with no common bookmarks."""
        lib1 = create_library('lib1', [{'id': 1, 'unique_id': 'aaa', 'title': 'A', 'url': 'https://a.com'}])
        lib2 = create_library('lib2', [{'id': 1, 'unique_id': 'bbb', 'title': 'B', 'url': 'https://b.com'}])
        output_dir = Path(temp_dir) / 'intersection_empty'
        
        merge.intersection_libraries([lib1, lib2], str(output_dir))
        
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        assert len(result) == 0
    
    def test_intersection_empty_list(self, temp_dir):
        """Test intersection with empty library list."""
        output_dir = Path(temp_dir) / 'intersection_none'
        
        # Should handle empty list gracefully
        merge.intersection_libraries([], str(output_dir))
        
        # Output directory should not be created
        assert not output_dir.exists()
    
    def test_difference_libraries(self, temp_dir, create_library, sample_bookmarks):
        """Test difference of bookmark libraries (first minus others)."""
        lib1 = create_library('lib1', sample_bookmarks['lib1'])
        lib2 = create_library('lib2', sample_bookmarks['lib2'])
        output_dir = Path(temp_dir) / 'difference_output'
        
        # Perform difference (lib1 - lib2)
        merge.difference_libraries([lib1, lib2], str(output_dir))
        
        # Check results
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        # Only 'abc123' (Site A) is in lib1 but not in lib2
        assert len(result) == 1
        assert result[0]['unique_id'] == 'abc123'
    
    def test_difference_multiple_subtract(self, temp_dir, create_library, sample_bookmarks):
        """Test difference with multiple libraries to subtract."""
        lib1 = create_library('lib1', sample_bookmarks['lib1'])
        lib2 = create_library('lib2', sample_bookmarks['lib2'])
        lib3 = create_library('lib3', sample_bookmarks['lib3'])
        output_dir = Path(temp_dir) / 'difference_multi'
        
        # lib1 - lib2 - lib3
        merge.difference_libraries([lib1, lib2, lib3], str(output_dir))
        
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        # Only 'abc123' is unique to lib1
        assert len(result) == 1
        assert result[0]['unique_id'] == 'abc123'
    
    def test_difference_insufficient_libraries(self, temp_dir, create_library):
        """Test difference with insufficient libraries."""
        lib1 = create_library('lib1', [])
        output_dir = Path(temp_dir) / 'difference_single'
        
        # Should handle single library gracefully
        merge.difference_libraries([lib1], str(output_dir))
        
        # Output directory should not be created
        assert not output_dir.exists()
    
    def test_difference_empty_first(self, temp_dir, create_library):
        """Test difference when first library is empty."""
        lib1 = create_library('lib1', [])
        lib2 = create_library('lib2', [{'id': 1, 'unique_id': 'test', 'title': 'Test', 'url': 'https://test.com'}])
        output_dir = Path(temp_dir) / 'difference_empty_first'
        
        merge.difference_libraries([lib1, lib2], str(output_dir))
        
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        # Empty minus anything is empty
        assert len(result) == 0
    
    def test_merge_preserves_bookmark_data(self, temp_dir, create_library):
        """Test that merge operations preserve all bookmark fields."""
        complex_bookmark = [{
            'id': 1,
            'unique_id': 'complex123',
            'title': 'Complex Site',
            'url': 'https://complex.com',
            'tags': ['test', 'complex'],
            'description': 'A complex bookmark',
            'stars': True,
            'visit_count': 5,
            'added': '2024-01-01',
            'last_visited': '2024-01-15',
            'favicon': 'favicon.ico',
            'reachable': True
        }]
        
        lib1 = create_library('lib1', complex_bookmark)
        lib2 = create_library('lib2', [])
        output_dir = Path(temp_dir) / 'union_complex'
        
        merge.union_libraries([lib1, lib2], str(output_dir))
        
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        assert len(result) == 1
        saved_bookmark = result[0]
        
        # Check all fields are preserved
        assert saved_bookmark['unique_id'] == 'complex123'
        assert saved_bookmark['tags'] == ['test', 'complex']
        assert saved_bookmark['description'] == 'A complex bookmark'
        assert saved_bookmark['stars'] is True
        assert saved_bookmark['visit_count'] == 5


class TestMergeEdgeCases:
    """Test edge cases and error handling in merge operations."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test libraries."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_nonexistent_library(self, temp_dir):
        """Test handling of non-existent library paths."""
        output_dir = Path(temp_dir) / 'output'
        
        # Should handle non-existent paths gracefully
        merge.union_libraries(['/nonexistent/path'], str(output_dir))
        
        # Should still create output with empty result
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        assert result == []
    
    def test_duplicate_libraries_in_union(self, temp_dir):
        """Test union with the same library multiple times."""
        lib_dir = Path(temp_dir) / 'lib'
        lib_dir.mkdir()
        bookmarks = [{'id': 1, 'unique_id': 'test123', 'title': 'Test', 'url': 'https://test.com'}]
        with open(lib_dir / 'bookmarks.json', 'w') as f:
            json.dump(bookmarks, f)
        
        output_dir = Path(temp_dir) / 'union_dup'
        
        # Union of same library multiple times
        merge.union_libraries([str(lib_dir), str(lib_dir), str(lib_dir)], str(output_dir))
        
        with open(output_dir / 'bookmarks.json') as f:
            result = json.load(f)
        
        # Should still have only one bookmark (deduplication by unique_id)
        assert len(result) == 1
        assert result[0]['unique_id'] == 'test123'