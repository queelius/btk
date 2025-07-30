"""
Tests for directory import functionality.
"""
import pytest
import os
import json
import tempfile
from pathlib import Path

from btk.tools import import_bookmarks_directory
from btk import utils


class TestDirectoryImport:
    """Test directory import functionality."""
    
    def create_test_directory_structure(self, base_dir):
        """Create a test directory structure with various file types."""
        # Create subdirectories
        docs_dir = Path(base_dir) / 'docs'
        resources_dir = Path(base_dir) / 'resources'
        nested_dir = Path(base_dir) / 'docs' / 'guides'
        
        for d in [docs_dir, resources_dir, nested_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # Create markdown files
        (Path(base_dir) / 'README.md').write_text("""
# Project README

- [Official Site](https://example.com)
- [Documentation](https://docs.example.com)

Check out <https://test.org> for more info.
""")
        
        (docs_dir / 'guide.md').write_text("""
# User Guide

## Resources
- [Python](https://python.org)
- [GitHub](https://github.com)
""")
        
        (nested_dir / 'advanced.md').write_text("""
# Advanced Topics

See https://advanced.example.com for details.
""")
        
        # Create HTML files
        (resources_dir / 'links.html').write_text("""
<!DOCTYPE html>
<html>
<body>
    <h1>Useful Links</h1>
    <a href="https://resource1.com">Resource 1</a>
    <a href="https://resource2.com" title="Second resource">Resource 2</a>
</body>
</html>
""")
        
        # Create JSON bookmark file
        bookmarks_data = [
            {
                "url": "https://json1.com",
                "title": "JSON Bookmark 1",
                "tags": ["json", "test"]
            },
            {
                "url": "https://json2.com",
                "title": "JSON Bookmark 2",
                "tags": ["json"]
            }
        ]
        (Path(base_dir) / 'bookmarks.json').write_text(json.dumps(bookmarks_data))
        
        # Create CSV file
        (resources_dir / 'data.csv').write_text("""url,title,tags,description,stars
https://csv1.com,CSV Site 1,"data,csv",First CSV bookmark,true
https://csv2.com,CSV Site 2,"data",Second CSV bookmark,false
""")
        
        # Create non-bookmark files to ignore
        (Path(base_dir) / 'script.py').write_text('print("Hello")')
        (docs_dir / 'image.png').write_bytes(b'fake image data')
        (Path(base_dir) / 'data.txt').write_text('Some text data')
    
    def test_import_directory_recursive(self, temp_lib_dir):
        """Test importing from directory recursively."""
        # Create test directory structure
        test_dir = Path(temp_lib_dir) / 'test_import'
        test_dir.mkdir()
        self.create_test_directory_structure(test_dir)
        
        # Import recursively
        bookmarks = []
        result = import_bookmarks_directory(str(test_dir), bookmarks, temp_lib_dir, recursive=True)
        
        # Verify all files were processed
        urls = [b['url'] for b in result]
        
        # From README.md
        assert 'https://example.com' in urls
        assert 'https://docs.example.com' in urls
        assert 'https://test.org' in urls
        
        # From docs/guide.md
        assert 'https://python.org' in urls
        assert 'https://github.com' in urls
        
        # From docs/guides/advanced.md (nested)
        assert 'https://advanced.example.com' in urls
        
        # From resources/links.html
        assert 'https://resource1.com' in urls
        assert 'https://resource2.com' in urls
        
        # From bookmarks.json
        assert 'https://json1.com' in urls
        assert 'https://json2.com' in urls
        
        # From resources/data.csv
        assert 'https://csv1.com' in urls
        assert 'https://csv2.com' in urls
        
        # Total bookmarks
        assert len(result) == 12
    
    def test_import_directory_non_recursive(self, temp_lib_dir):
        """Test importing from directory non-recursively."""
        # Create test directory structure
        test_dir = Path(temp_lib_dir) / 'test_import'
        test_dir.mkdir()
        self.create_test_directory_structure(test_dir)
        
        # Import non-recursively
        bookmarks = []
        result = import_bookmarks_directory(str(test_dir), bookmarks, temp_lib_dir, recursive=False)
        
        # Should only get files from root directory
        urls = [b['url'] for b in result]
        
        # From README.md
        assert 'https://example.com' in urls
        assert 'https://docs.example.com' in urls
        assert 'https://test.org' in urls
        
        # From bookmarks.json
        assert 'https://json1.com' in urls
        assert 'https://json2.com' in urls
        
        # Should NOT have files from subdirectories
        assert 'https://python.org' not in urls
        assert 'https://resource1.com' not in urls
        assert 'https://csv1.com' not in urls
        
        assert len(result) == 5
    
    def test_import_directory_specific_formats(self, temp_lib_dir):
        """Test importing only specific formats."""
        # Create test directory structure
        test_dir = Path(temp_lib_dir) / 'test_import'
        test_dir.mkdir()
        self.create_test_directory_structure(test_dir)
        
        # Import only markdown files
        bookmarks = []
        result = import_bookmarks_directory(str(test_dir), bookmarks, temp_lib_dir, 
                                          recursive=True, formats=['markdown'])
        
        # Should only have markdown URLs
        urls = [b['url'] for b in result]
        
        # From markdown files
        assert 'https://example.com' in urls
        assert 'https://python.org' in urls
        assert 'https://advanced.example.com' in urls
        
        # Should NOT have HTML, JSON, or CSV URLs
        assert 'https://resource1.com' not in urls
        assert 'https://json1.com' not in urls
        assert 'https://csv1.com' not in urls
        
        assert len(result) == 6  # All markdown links
    
    def test_import_directory_empty(self, temp_lib_dir):
        """Test importing from empty directory."""
        empty_dir = Path(temp_lib_dir) / 'empty'
        empty_dir.mkdir()
        
        bookmarks = []
        result = import_bookmarks_directory(str(empty_dir), bookmarks, temp_lib_dir)
        
        assert len(result) == 0
    
    def test_import_directory_with_errors(self, temp_lib_dir):
        """Test that import continues despite errors in some files."""
        test_dir = Path(temp_lib_dir) / 'test_errors'
        test_dir.mkdir()
        
        # Create valid file
        (test_dir / 'good.md').write_text("[Valid Link](https://valid.com)")
        
        # Create invalid JSON
        (test_dir / 'bad.json').write_text("{ invalid json")
        
        # Create valid file
        (test_dir / 'another.md').write_text("[Another](https://another.com)")
        
        bookmarks = []
        result = import_bookmarks_directory(str(test_dir), bookmarks, temp_lib_dir)
        
        # Should import valid files despite error
        urls = [b['url'] for b in result]
        assert 'https://valid.com' in urls
        assert 'https://another.com' in urls
        assert len(result) == 2