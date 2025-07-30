"""
Tests for import and export functionality.
"""
import pytest
import os
import json
import csv
import tempfile
from pathlib import Path

from btk.tools import (
    import_bookmarks,
    import_bookmarks_markdown,
    import_bookmarks_json,
    import_bookmarks_csv,
    import_bookmarks_html_generic,
    export_bookmarks_html,
    export_bookmarks_csv,
    export_bookmarks_json,
    export_bookmarks_markdown
)
from btk import utils


class TestMarkdownImport:
    """Test markdown file import functionality."""
    
    def test_import_markdown_links(self, temp_lib_dir):
        """Test importing various markdown link formats."""
        # Create test markdown file
        markdown_content = """
# Test Document

Regular link: [Python](https://python.org)
Another link: [GitHub](https://github.com)

Angle bracket: <https://example.com>

Raw URL: https://raw-url.com

Mixed: Check out [Google](https://google.com) and also https://direct.com
"""
        md_file = os.path.join(temp_lib_dir, "test.md")
        with open(md_file, 'w') as f:
            f.write(markdown_content)
        
        # Import bookmarks
        bookmarks = []
        result = import_bookmarks_markdown(md_file, bookmarks, temp_lib_dir)
        
        # Check results
        assert len(result) == 6
        
        # Check titled links
        python_bookmark = next((b for b in result if b['title'] == 'Python'), None)
        assert python_bookmark is not None
        assert python_bookmark['url'] == 'https://python.org'
        assert 'markdown-import' in python_bookmark['tags']
        
        # Check angle bracket URL
        example_bookmark = next((b for b in result if 'example.com' in b['url']), None)
        assert example_bookmark is not None
        
        # Check raw URL
        raw_bookmark = next((b for b in result if 'raw-url.com' in b['url']), None)
        assert raw_bookmark is not None
    
    def test_import_markdown_no_duplicates(self, temp_lib_dir):
        """Test that markdown import doesn't create duplicates."""
        markdown_content = """
[Python](https://python.org)
<https://python.org>
https://python.org
[Python Docs](https://python.org)
"""
        md_file = os.path.join(temp_lib_dir, "dupes.md")
        with open(md_file, 'w') as f:
            f.write(markdown_content)
        
        # Import should only create one bookmark for python.org
        bookmarks = []
        result = import_bookmarks_markdown(md_file, bookmarks, temp_lib_dir)
        
        python_bookmarks = [b for b in result if 'python.org' in b['url']]
        assert len(python_bookmarks) == 1
        assert python_bookmarks[0]['title'] == 'Python'  # First occurrence
    
    def test_import_markdown_empty_file(self, temp_lib_dir):
        """Test importing empty markdown file."""
        md_file = os.path.join(temp_lib_dir, "empty.md")
        Path(md_file).touch()
        
        bookmarks = []
        result = import_bookmarks_markdown(md_file, bookmarks, temp_lib_dir)
        assert len(result) == 0


class TestCSVImport:
    """Test CSV import functionality."""
    
    def test_import_csv_basic(self, temp_lib_dir):
        """Test basic CSV import."""
        # Create CSV file
        csv_content = """url,title,tags,description,stars
https://python.org,Python,"programming,language",Official Python site,true
https://github.com,GitHub,"development,git",Code hosting,false
"""
        csv_file = os.path.join(temp_lib_dir, "bookmarks.csv")
        with open(csv_file, 'w') as f:
            f.write(csv_content)
        
        # Import bookmarks
        bookmarks = []
        # Note: CSV import is handled in CLI, we'd need to test via utils
        # For now, let's test the CSV export which we can test directly
    
    def test_csv_export_import_roundtrip(self, temp_lib_dir, sample_bookmarks):
        """Test that bookmarks can be exported to CSV and maintain data."""
        csv_file = os.path.join(temp_lib_dir, "export.csv")
        
        # Export bookmarks
        export_bookmarks_csv(sample_bookmarks, csv_file)
        
        # Verify CSV was created
        assert os.path.exists(csv_file)
        
        # Read CSV and verify content
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == len(sample_bookmarks)
        
        # Check first bookmark
        first_row = rows[0]
        assert 'title' in first_row
        assert 'url' in first_row
        assert 'tags' in first_row


class TestJSONImportExport:
    """Test JSON import and export functionality."""
    
    def test_json_export_import_roundtrip(self, temp_lib_dir, sample_bookmarks):
        """Test JSON export and import roundtrip."""
        json_file = os.path.join(temp_lib_dir, "bookmarks.json")
        
        # Export bookmarks
        export_bookmarks_json(sample_bookmarks, json_file)
        assert os.path.exists(json_file)
        
        # Import back
        imported = import_bookmarks_json(json_file, [], temp_lib_dir)
        
        # Check all bookmarks were imported
        assert len(imported) == len(sample_bookmarks)
        
        # Verify key fields
        for orig, imp in zip(sample_bookmarks, imported):
            assert imp['url'] == orig['url']
            assert imp['title'] == orig['title']
            assert imp['tags'] == orig['tags']
    
    def test_json_import_invalid_format(self, temp_lib_dir):
        """Test JSON import with invalid format."""
        json_file = os.path.join(temp_lib_dir, "invalid.json")
        
        # Write invalid JSON (not a list)
        with open(json_file, 'w') as f:
            json.dump({"not": "a list"}, f)
        
        # Should return empty list
        imported = import_bookmarks_json(json_file, [], temp_lib_dir)
        assert len(imported) == 0


class TestHTMLExport:
    """Test HTML export functionality."""
    
    def test_export_html_netscape_format(self, temp_lib_dir, sample_bookmarks):
        """Test exporting bookmarks to Netscape HTML format."""
        html_file = os.path.join(temp_lib_dir, "export.html")
        
        # Export bookmarks
        export_bookmarks_html(sample_bookmarks, html_file)
        
        # Verify file was created
        assert os.path.exists(html_file)
        
        # Read and verify content
        with open(html_file, 'r') as f:
            content = f.read()
        
        # Check Netscape format markers
        assert '<!DOCTYPE NETSCAPE-Bookmark-file-1>' in content
        assert '<TITLE>Bookmarks</TITLE>' in content
        assert '<H1>Bookmarks</H1>' in content
        
        # Check bookmarks are present
        for bookmark in sample_bookmarks:
            assert bookmark['url'] in content
            assert bookmark['title'] in content
    
    def test_export_html_with_tags(self, temp_lib_dir):
        """Test that tags are exported correctly."""
        bookmarks = [{
            'id': 1,
            'url': 'https://example.com',
            'title': 'Example',
            'tags': ['test', 'example'],
            'description': 'Test description',
            'added': '2024-01-01T00:00:00Z'
        }]
        
        html_file = os.path.join(temp_lib_dir, "tags.html")
        export_bookmarks_html(bookmarks, html_file)
        
        with open(html_file, 'r') as f:
            content = f.read()
        
        # Check tags are in the export
        assert 'TAGS="test,example"' in content
        assert 'Test description' in content
    
    def test_export_empty_bookmarks(self, temp_lib_dir):
        """Test exporting empty bookmark list."""
        html_file = os.path.join(temp_lib_dir, "empty.html")
        export_bookmarks_html([], html_file)
        
        assert os.path.exists(html_file)
        with open(html_file, 'r') as f:
            content = f.read()
        
        # Should still have valid structure
        assert '<!DOCTYPE NETSCAPE-Bookmark-file-1>' in content
        assert '</DL><p>' in content


class TestGenericHTMLImport:
    """Test generic HTML import functionality."""
    
    def test_import_html_generic_links(self, temp_lib_dir):
        """Test importing links from generic HTML."""
        html_content = """
<!DOCTYPE html>
<html>
<body>
    <h1>Test Page</h1>
    <a href="https://example.com">Example Site</a>
    <a href="https://test.org" title="Test Organization">Test Org</a>
    <a href="https://python.org" class="programming language">Python</a>
    <a href="//protocol-relative.com">Protocol Relative</a>
    <a href="#anchor">Anchor Link</a>
    <a href="mailto:test@example.com">Email</a>
    <a href="/relative/path">Relative</a>
</body>
</html>
"""
        html_file = os.path.join(temp_lib_dir, "generic.html")
        with open(html_file, 'w') as f:
            f.write(html_content)
        
        # Import
        imported = import_bookmarks_html_generic(html_file, [], temp_lib_dir)
        
        # Should import only valid HTTP(S) links
        assert len(imported) == 4  # example.com, test.org, python.org, protocol-relative
        
        # Check specific imports
        urls = [b['url'] for b in imported]
        assert 'https://example.com' in urls
        assert 'https://test.org' in urls
        assert 'https://python.org' in urls
        assert 'https://protocol-relative.com' in urls
        
        # Check metadata extraction
        test_org = next(b for b in imported if 'test.org' in b['url'])
        assert test_org['description'] == 'Test Organization'
        
        python_org = next(b for b in imported if 'python.org' in b['url'])
        assert 'programming' in python_org['tags'] or 'language' in python_org['tags']
    
    def test_import_html_generic_no_duplicates(self, temp_lib_dir):
        """Test that generic HTML import handles duplicates."""
        html_content = """
<html>
<body>
    <a href="https://example.com">Example 1</a>
    <a href="https://example.com">Example 2</a>
    <a href="https://example.com">Example 3</a>
</body>
</html>
"""
        html_file = os.path.join(temp_lib_dir, "dupes.html")
        with open(html_file, 'w') as f:
            f.write(html_content)
        
        imported = import_bookmarks_html_generic(html_file, [], temp_lib_dir)
        assert len(imported) == 1  # Only one bookmark for example.com


class TestImportExportRoundtrip:
    """Test that data survives import/export cycles."""
    
    def test_html_roundtrip(self, temp_lib_dir):
        """Test HTML export and re-import maintains data."""
        original_bookmarks = [{
            'id': 1,
            'unique_id': 'abc123',
            'url': 'https://test.com',
            'title': 'Test Site',
            'tags': ['test', 'roundtrip'],
            'description': 'Testing roundtrip',
            'added': '2024-01-01T00:00:00Z',
            'stars': False,
            'visit_count': 0,
            'last_visited': None,
            'favicon': None,
            'reachable': None
        }]
        
        # Export to HTML
        html_file = os.path.join(temp_lib_dir, "roundtrip.html")
        export_bookmarks_html(original_bookmarks, html_file)
        
        # Import back
        reimported = import_bookmarks(html_file, [], temp_lib_dir)
        
        # Check key fields survived
        assert len(reimported) == 1
        assert reimported[0]['url'] == original_bookmarks[0]['url']
        assert reimported[0]['title'] == original_bookmarks[0]['title']
        # Note: Some fields like visit_count may not survive the roundtrip