"""
Integration tests for BTK features.
"""
import pytest
import os
import json
import subprocess
import sys
from pathlib import Path


class TestBTKIntegration:
    """Test complete workflows using BTK."""
    
    def test_full_workflow(self, temp_lib_dir):
        """Test a complete workflow: import, tag, dedupe, export."""
        # 1. Create test data
        lib_dir = os.path.join(temp_lib_dir, 'test_lib')
        os.makedirs(lib_dir, exist_ok=True)
        urls_file = os.path.join(temp_lib_dir, 'urls.txt')
        
        with open(urls_file, 'w') as f:
            f.write("""
https://python.org
https://golang.org
https://python.org
https://github.com
https://stackoverflow.com
""")
        
        # 2. Bulk import URLs
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'bulk', 'add', lib_dir,
            '--from-file', urls_file,
            '--tags', 'imported,test',
            '--no-fetch-titles'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert 'Successfully added 4 bookmarks' in result.stdout
        
        # 3. Check for duplicates (bulk add already deduplicates, so should be 0)
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'dedupe', lib_dir,
            '--stats'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert 'Duplicate groups: 0' in result.stdout
        
        # 4. Add tags using bulk edit
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'bulk', 'edit', lib_dir,
            '--filter-url', 'python.org',
            '--add-tags', 'programming/languages/python'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert 'Successfully edited 1 bookmarks' in result.stdout
        
        # 5. View tag tree
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'tag', 'tree', lib_dir
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert 'programming' in result.stdout
        assert 'languages' in result.stdout
        
        # 6. Export hierarchically
        export_dir = os.path.join(temp_lib_dir, 'export')
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'export', lib_dir, 'hierarchical',
            '--output', export_dir
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert os.path.exists(os.path.join(export_dir, 'index.md'))
        assert os.path.exists(os.path.join(export_dir, 'programming'))
    
    def test_import_export_roundtrip(self, temp_lib_dir):
        """Test importing and exporting maintains data integrity."""
        # Create initial library
        lib1_dir = os.path.join(temp_lib_dir, 'lib1')
        os.makedirs(lib1_dir)
        
        initial_bookmarks = [
            {
                'id': 1,
                'unique_id': 'test1',
                'url': 'https://example.com',
                'title': 'Example',
                'tags': ['test', 'example'],
                'description': 'Test bookmark',
                'stars': True,
                'added': '2024-01-01T00:00:00Z',
                'visit_count': 5,
                'last_visited': None,
                'favicon': None,
                'reachable': True
            }
        ]
        
        with open(os.path.join(lib1_dir, 'bookmarks.json'), 'w') as f:
            json.dump(initial_bookmarks, f)
        
        # Export to JSON
        export_file = os.path.join(temp_lib_dir, 'export.json')
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'export', lib1_dir, 'json',
            '--output', export_file
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        
        # Import into new library
        lib2_dir = os.path.join(temp_lib_dir, 'lib2')
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'import', 'json', export_file,
            '--lib-dir', lib2_dir
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        
        # Compare libraries
        with open(os.path.join(lib2_dir, 'bookmarks.json')) as f:
            imported_bookmarks = json.load(f)
        
        assert len(imported_bookmarks) == 1
        assert imported_bookmarks[0]['url'] == initial_bookmarks[0]['url']
        assert imported_bookmarks[0]['tags'] == initial_bookmarks[0]['tags']
    
    def test_tag_operations(self, temp_lib_dir):
        """Test tag rename and merge operations."""
        # Create library with tagged bookmarks
        lib_dir = os.path.join(temp_lib_dir, 'tagtest')
        os.makedirs(lib_dir)
        
        bookmarks = [
            {
                'id': 1,
                'unique_id': 'b1',
                'url': 'https://url1.com',
                'title': 'URL 1',
                'tags': ['old-tag', 'keep-this'],
                'stars': False,
                'added': '2024-01-01T00:00:00Z',
                'visit_count': 0
            },
            {
                'id': 2,
                'unique_id': 'b2',
                'url': 'https://url2.com',
                'title': 'URL 2',
                'tags': ['old-tag', 'another-old'],
                'stars': False,
                'added': '2024-01-01T00:00:00Z',
                'visit_count': 0
            }
        ]
        
        with open(os.path.join(lib_dir, 'bookmarks.json'), 'w') as f:
            json.dump(bookmarks, f)
        
        # Rename tag
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'tag', 'rename', lib_dir,
            'old-tag', 'new-tag'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert '2 bookmarks affected' in result.stdout
        
        # Verify rename
        with open(os.path.join(lib_dir, 'bookmarks.json')) as f:
            updated = json.load(f)
        
        assert 'new-tag' in updated[0]['tags']
        assert 'old-tag' not in updated[0]['tags']
        
        # Merge tags
        result = subprocess.run([
            sys.executable, '-m', 'btk.cli', 'tag', 'merge', lib_dir,
            'new-tag', 'another-old', '--into', 'merged-tag'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        
        # Verify merge
        with open(os.path.join(lib_dir, 'bookmarks.json')) as f:
            final = json.load(f)
        
        assert 'merged-tag' in final[0]['tags']
        assert 'merged-tag' in final[1]['tags']
        assert 'new-tag' not in final[0]['tags']