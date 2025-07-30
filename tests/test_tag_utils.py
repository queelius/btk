"""
Tests for tag utilities.
"""
import pytest
from btk.tag_utils import (
    parse_tag_hierarchy,
    get_tag_tree,
    filter_bookmarks_by_tag_prefix,
    get_tag_statistics,
    rename_tag_hierarchy,
    merge_tags,
    split_tag,
    suggest_tags,
    format_tag_tree
)


class TestTagHierarchy:
    """Test tag hierarchy functions."""
    
    def test_parse_tag_hierarchy(self):
        """Test parsing flat tags into hierarchy."""
        tags = ['programming/python', 'programming/go', 'news/tech', 'news']
        hierarchy = parse_tag_hierarchy(tags)
        
        assert '_root' in hierarchy
        assert 'news' in hierarchy['_root']
        assert 'programming' in hierarchy['_root']
        assert 'programming/python' in hierarchy['programming']
        assert 'programming/go' in hierarchy['programming']
        assert 'news/tech' in hierarchy['news']
    
    def test_parse_tag_hierarchy_custom_separator(self):
        """Test parsing with custom separator."""
        tags = ['work:projects:client-a', 'work:projects:client-b']
        hierarchy = parse_tag_hierarchy(tags, separator=':')
        
        assert 'work' in hierarchy['_root']
        assert 'work:projects' in hierarchy['work']
        assert 'work:projects:client-a' in hierarchy['work:projects']
    
    def test_get_tag_tree(self):
        """Test building tag tree from bookmarks."""
        bookmarks = [
            {'id': 1, 'tags': ['programming/python', 'documentation']},
            {'id': 2, 'tags': ['programming/go', 'documentation/official']},
            {'id': 3, 'tags': ['news/tech']}
        ]
        
        tree = get_tag_tree(bookmarks)
        
        assert 'programming' in tree
        assert 'python' in tree['programming']
        assert 'go' in tree['programming']
        assert 'documentation' in tree
        assert 'official' in tree['documentation']
        assert 'news' in tree
        assert 'tech' in tree['news']
    
    def test_format_tag_tree(self):
        """Test formatting tag tree for display."""
        tree = {
            'programming': {
                'languages': {
                    'python': {},
                    'go': {}
                },
                'tools': {}
            },
            'news': {
                'tech': {}
            }
        }
        
        output = format_tag_tree(tree)
        lines = output.split('\n')
        
        assert 'news' in output
        assert 'programming' in output
        assert '  languages' in output
        assert '    go' in output
        assert '    python' in output
        assert '  tools' in output


class TestTagFiltering:
    """Test tag filtering functions."""
    
    def test_filter_bookmarks_by_tag_prefix(self):
        """Test filtering bookmarks by tag prefix."""
        bookmarks = [
            {'id': 1, 'title': 'Python', 'tags': ['programming/python', 'docs']},
            {'id': 2, 'title': 'Go', 'tags': ['programming/go']},
            {'id': 3, 'title': 'News', 'tags': ['news/tech']},
            {'id': 4, 'title': 'Java', 'tags': ['programming/java']}
        ]
        
        # Filter by 'programming'
        filtered = filter_bookmarks_by_tag_prefix(bookmarks, 'programming')
        assert len(filtered) == 3
        assert all(b['id'] in [1, 2, 4] for b in filtered)
        
        # Filter by 'programming/python'
        filtered = filter_bookmarks_by_tag_prefix(bookmarks, 'programming/python')
        assert len(filtered) == 1
        assert filtered[0]['id'] == 1
        
        # Filter by 'news'
        filtered = filter_bookmarks_by_tag_prefix(bookmarks, 'news')
        assert len(filtered) == 1
        assert filtered[0]['id'] == 3
    
    def test_filter_empty_prefix(self):
        """Test filtering with empty prefix."""
        bookmarks = [
            {'id': 1, 'tags': ['programming']},
            {'id': 2, 'tags': []}
        ]
        
        filtered = filter_bookmarks_by_tag_prefix(bookmarks, '')
        assert len(filtered) == 1  # Only bookmarks with tags


class TestTagStatistics:
    """Test tag statistics functions."""
    
    def test_get_tag_statistics(self):
        """Test getting tag statistics."""
        bookmarks = [
            {'id': 1, 'tags': ['programming/python', 'docs']},
            {'id': 2, 'tags': ['programming/python', 'programming/go']},
            {'id': 3, 'tags': ['programming']},
            {'id': 4, 'tags': ['docs']}
        ]
        
        stats = get_tag_statistics(bookmarks)
        
        # Check direct counts
        assert stats['programming']['direct_count'] == 1
        assert stats['programming/python']['direct_count'] == 2
        assert stats['docs']['direct_count'] == 2
        
        # Check hierarchical counts
        assert stats['programming']['total_count'] == 4  # 1 direct + 2 python + 1 go
        assert stats['programming']['bookmark_count'] == 3  # bookmarks 1, 2, 3
        
        # Check leaf counts
        assert stats['programming/python']['total_count'] == 2
        assert stats['programming/python']['bookmark_count'] == 2


class TestTagOperations:
    """Test tag modification operations."""
    
    def test_rename_tag_hierarchy(self):
        """Test renaming tags in hierarchy."""
        bookmarks = [
            {'id': 1, 'tags': ['programming/python', 'docs']},
            {'id': 2, 'tags': ['programming/python/django']},
            {'id': 3, 'tags': ['programming/go']},
            {'id': 4, 'tags': ['other']}
        ]
        
        # Rename programming/python to development/python
        updated, affected = rename_tag_hierarchy(
            bookmarks.copy(), 'programming/python', 'development/python'
        )
        
        assert affected == 2
        assert 'development/python' in updated[0]['tags']
        assert 'development/python/django' in updated[1]['tags']
        assert 'programming/go' in updated[2]['tags']  # Unchanged
    
    def test_merge_tags(self):
        """Test merging multiple tags."""
        bookmarks = [
            {'id': 1, 'tags': ['python', 'py']},
            {'id': 2, 'tags': ['py', 'programming']},
            {'id': 3, 'tags': ['python']},
            {'id': 4, 'tags': ['java']}
        ]
        
        # Merge 'py' and 'python' into 'programming/python'
        updated, affected = merge_tags(
            bookmarks.copy(), ['py', 'python'], 'programming/python'
        )
        
        assert affected == 3
        assert 'programming/python' in updated[0]['tags']
        assert 'programming/python' in updated[1]['tags']
        assert 'programming/python' in updated[2]['tags']
        assert 'java' in updated[3]['tags']  # Unchanged
        
        # Check no duplicates
        assert updated[0]['tags'].count('programming/python') == 1
    
    def test_split_tag(self):
        """Test splitting a tag into multiple tags."""
        bookmarks = [
            {'id': 1, 'tags': ['webdev', 'tools']},
            {'id': 2, 'tags': ['webdev']},
            {'id': 3, 'tags': ['other']}
        ]
        
        # Split 'webdev' into 'web' and 'development'
        updated, affected = split_tag(
            bookmarks.copy(), 'webdev', ['web', 'development']
        )
        
        assert affected == 2
        assert 'web' in updated[0]['tags']
        assert 'development' in updated[0]['tags']
        assert 'webdev' not in updated[0]['tags']
        assert 'tools' in updated[0]['tags']  # Other tags preserved


class TestTagSuggestions:
    """Test tag suggestion functions."""
    
    def test_suggest_tags_prefix(self):
        """Test tag suggestions based on prefix."""
        existing_tags = {
            'programming',
            'programming/python',
            'programming/python/django',
            'programming/go',
            'project/personal',
            'project/work'
        }
        
        # Test prefix matching
        suggestions = suggest_tags('prog', existing_tags)
        assert 'programming' in suggestions
        assert 'programming/python' in suggestions
        assert 'project/personal' not in suggestions
        
        # Test exact match not included
        suggestions = suggest_tags('programming', existing_tags)
        assert 'programming' not in suggestions
        assert 'programming/python' in suggestions
    
    def test_suggest_tags_fuzzy(self):
        """Test fuzzy tag suggestions."""
        existing_tags = {'python', 'django', 'flask', 'javascript', 'java'}
        
        # Test fuzzy matching when not enough prefix matches
        suggestions = suggest_tags('jav', existing_tags, max_suggestions=5)
        assert 'java' in suggestions
        assert 'javascript' in suggestions
    
    def test_suggest_tags_max_limit(self):
        """Test max suggestions limit."""
        existing_tags = {f'tag{i}' for i in range(20)}
        
        suggestions = suggest_tags('tag', existing_tags, max_suggestions=5)
        assert len(suggestions) == 5