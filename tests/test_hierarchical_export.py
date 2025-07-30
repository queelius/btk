"""
Tests for hierarchical export functionality.
"""
import pytest
import os
import json
from pathlib import Path

from btk.tools import export_bookmarks_hierarchical
from btk import utils


class TestHierarchicalExport:
    """Test hierarchical export functionality."""
    
    def create_test_bookmarks_with_hierarchy(self):
        """Create test bookmarks with hierarchical tags."""
        return [
            {
                'id': 1,
                'url': 'https://python.org',
                'title': 'Python',
                'tags': ['programming/languages/python', 'documentation'],
                'description': 'Python programming language',
                'stars': True
            },
            {
                'id': 2,
                'url': 'https://docs.python.org',
                'title': 'Python Docs',
                'tags': ['programming/languages/python', 'programming/documentation'],
                'description': 'Official Python documentation',
                'stars': True
            },
            {
                'id': 3,
                'url': 'https://golang.org',
                'title': 'Go',
                'tags': ['programming/languages/go'],
                'description': 'Go programming language',
                'stars': False
            },
            {
                'id': 4,
                'url': 'https://github.com',
                'title': 'GitHub',
                'tags': ['development/tools', 'programming/vcs'],
                'description': 'Code hosting platform',
                'stars': True
            },
            {
                'id': 5,
                'url': 'https://stackoverflow.com',
                'title': 'Stack Overflow',
                'tags': ['programming/qa', 'development/resources'],
                'description': 'Q&A for programmers',
                'stars': False
            },
            {
                'id': 6,
                'url': 'https://example.com',
                'title': 'Example',
                'tags': [],  # Untagged
                'description': 'Example site',
                'stars': False
            },
            {
                'id': 7,
                'url': 'https://news.ycombinator.com',
                'title': 'Hacker News',
                'tags': ['news', 'technology'],  # Simple tags
                'description': 'Tech news',
                'stars': True
            }
        ]
    
    def test_hierarchical_export_markdown(self, temp_lib_dir):
        """Test hierarchical export to markdown format."""
        bookmarks = self.create_test_bookmarks_with_hierarchy()
        output_dir = Path(temp_lib_dir) / 'hierarchical_export'
        
        # Export hierarchically
        exported_files = export_bookmarks_hierarchical(bookmarks, str(output_dir), format='markdown')
        
        # Check directory structure
        assert output_dir.exists()
        assert (output_dir / 'index.md').exists()
        assert (output_dir / 'programming').exists()
        assert (output_dir / 'development').exists()
        assert (output_dir / 'documentation').exists()
        assert (output_dir / 'news').exists()
        assert (output_dir / 'technology').exists()
        assert (output_dir / 'untagged.md').exists()
        
        # Check programming category file
        prog_file = output_dir / 'programming' / 'programming.md'
        assert prog_file.exists()
        content = prog_file.read_text()
        
        # Should have subcategories
        assert '## languages > python' in content
        assert '## languages > go' in content
        assert '## documentation' in content
        assert '## qa' in content
        assert '## vcs' in content
        
        # Should have bookmarks
        assert 'Python' in content
        assert 'https://python.org' in content
        assert '⭐' in content  # Starred bookmark
        
        # Check index file
        index_content = (output_dir / 'index.md').read_text()
        assert '# Bookmark Export Index' in index_content
        assert '[Programming]' in index_content
        assert '[Development]' in index_content
        assert '[Untagged]' in index_content
    
    def test_hierarchical_export_json(self, temp_lib_dir):
        """Test hierarchical export to JSON format."""
        bookmarks = self.create_test_bookmarks_with_hierarchy()
        output_dir = Path(temp_lib_dir) / 'hierarchical_json'
        
        # Export hierarchically
        exported_files = export_bookmarks_hierarchical(bookmarks, str(output_dir), format='json')
        
        # Check JSON files
        prog_file = output_dir / 'programming' / 'programming.json'
        assert prog_file.exists()
        
        with open(prog_file) as f:
            prog_data = json.load(f)
        
        # Should have category and subcategory info
        python_bookmarks = [b for b in prog_data if 'python' in b.get('subcategory', '')]
        assert len(python_bookmarks) > 0
        assert python_bookmarks[0]['category'] == 'programming'
        assert 'languages/python' in python_bookmarks[0]['subcategory']
    
    def test_hierarchical_export_html(self, temp_lib_dir):
        """Test hierarchical export to HTML format."""
        bookmarks = self.create_test_bookmarks_with_hierarchy()
        output_dir = Path(temp_lib_dir) / 'hierarchical_html'
        
        # Export hierarchically
        exported_files = export_bookmarks_hierarchical(bookmarks, str(output_dir), format='html')
        
        # Check HTML files
        prog_file = output_dir / 'programming' / 'programming.html'
        assert prog_file.exists()
        
        content = prog_file.read_text()
        assert '<!DOCTYPE NETSCAPE-Bookmark-file-1>' in content
        assert 'https://python.org' in content
    
    def test_hierarchical_export_custom_separator(self, temp_lib_dir):
        """Test hierarchical export with custom separator."""
        bookmarks = [
            {
                'id': 1,
                'url': 'https://example.com',
                'title': 'Example',
                'tags': ['work:projects:client-a', 'work:important'],
                'description': 'Client A project',
                'stars': True
            }
        ]
        
        output_dir = Path(temp_lib_dir) / 'custom_separator'
        
        # Export with custom separator
        exported_files = export_bookmarks_hierarchical(bookmarks, str(output_dir), 
                                                      format='markdown', separator=':')
        
        # Check structure
        work_dir = output_dir / 'work'
        assert work_dir.exists()
        
        work_file = work_dir / 'work.md'
        content = work_file.read_text()
        
        # Should use custom separator
        assert '## projects > client-a' in content
        assert '## important' in content
    
    def test_hierarchical_export_empty(self, temp_lib_dir):
        """Test hierarchical export with empty bookmarks."""
        output_dir = Path(temp_lib_dir) / 'empty_export'
        
        exported_files = export_bookmarks_hierarchical([], str(output_dir))
        
        # Should still create index
        assert (output_dir / 'index.md').exists()
        assert len(exported_files) == 0