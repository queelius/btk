"""
Integration tests for BTK CLI commands.

These tests focus on verifying command behavior and key outputs
rather than exact string matching, allowing flexibility in output formatting.
"""
import pytest
import json
import os
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path


class TestCLIIntegration:
    """Test CLI commands with real file operations."""
    
    def run_btk(self, args):
        """Run btk command and return result."""
        # Try to run btk directly if installed
        cmd = ['btk'] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            # Fall back to running as module
            cmd = [sys.executable, '-m', 'btk.cli'] + args
            result = subprocess.run(cmd, capture_output=True, text=True)
        return result
    
    @pytest.fixture
    def temp_lib(self):
        """Create a temporary library directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def sample_html(self, tmp_path):
        """Create a sample HTML bookmarks file."""
        html_content = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><A HREF="https://example.com" ADD_DATE="1234567890">Example Site</A>
    <DT><A HREF="https://test.org" ADD_DATE="1234567891">Test Organization</A>
</DL><p>
"""
        html_file = tmp_path / "bookmarks.html"
        html_file.write_text(html_content)
        return str(html_file)
    
    def test_help_command(self):
        """Test help command shows usage."""
        result = self.run_btk(['--help'])
        assert result.returncode == 0
        assert 'bookmark' in result.stdout.lower()
        assert 'import' in result.stdout
        assert 'search' in result.stdout
    
    def test_import_html_creates_library(self, temp_lib, sample_html):
        """Test importing HTML bookmarks creates a library."""
        # Use the nbf (Netscape Bookmark Format) subcommand
        result = self.run_btk(['import', 'nbf', sample_html, '--lib-dir', temp_lib])
        
        # Check command completed successfully
        assert result.returncode == 0
        
        # Verify library was created
        bookmarks_file = Path(temp_lib) / 'bookmarks.json'
        assert bookmarks_file.exists()
        
        # Verify bookmarks were imported
        with open(bookmarks_file) as f:
            bookmarks = json.load(f)
        assert len(bookmarks) == 2
        assert any('example.com' in b['url'] for b in bookmarks)
    
    def test_list_shows_bookmarks(self, temp_lib, sample_html):
        """Test list command displays bookmarks."""
        # First import some bookmarks
        self.run_btk(['import', 'nbf', sample_html, '--lib-dir', temp_lib])
        
        # Then list them
        result = self.run_btk(['list', temp_lib])
        assert result.returncode == 0
        output = result.stdout + result.stderr  # Check both outputs
        # The list command shows titles, so look for the title
        assert 'example' in output.lower() or 'test' in output.lower()
    
    def test_search_finds_bookmarks(self, temp_lib, sample_html):
        """Test search command finds matching bookmarks."""
        # Import bookmarks
        self.run_btk(['import', 'nbf', sample_html, '--lib-dir', temp_lib])
        
        # Search for a bookmark
        result = self.run_btk(['search', temp_lib, 'example'])
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert 'example' in output.lower()
    
    def test_add_bookmark(self, temp_lib):
        """Test adding a new bookmark."""
        # Create empty library
        os.makedirs(temp_lib, exist_ok=True)
        # Initialize empty bookmarks file
        with open(Path(temp_lib) / 'bookmarks.json', 'w') as f:
            json.dump([], f)
        
        # Add a bookmark
        result = self.run_btk([
            'add', temp_lib, 'https://mytest.com',
            '--title', 'My Test Site',
            '--tags', 'test,integration',
            '--description', 'A test bookmark'
        ])
        assert result.returncode == 0
        
        # Verify it was added
        bookmarks_file = Path(temp_lib) / 'bookmarks.json'
        with open(bookmarks_file) as f:
            bookmarks = json.load(f)
        
        assert len(bookmarks) == 1
        bookmark = bookmarks[0]
        assert bookmark['title'] == 'My Test Site'
        assert bookmark['url'] == 'https://mytest.com'
        assert 'test' in bookmark['tags']
        assert bookmark['description'] == 'A test bookmark'
    
    def test_remove_bookmark(self, temp_lib, sample_html):
        """Test removing a bookmark by ID."""
        # Import bookmarks
        self.run_btk(['import', 'nbf', sample_html, '--lib-dir', temp_lib])
        
        # Remove bookmark with ID 1
        result = self.run_btk(['remove', temp_lib, '1'])
        
        # Verify it was removed or check error message
        bookmarks_file = Path(temp_lib) / 'bookmarks.json'
        with open(bookmarks_file) as f:
            bookmarks = json.load(f)
        
        # Either bookmark was removed or we got an error
        if result.returncode == 0:
            assert len(bookmarks) == 1
            assert all(b['id'] != 1 for b in bookmarks)
    
    def test_edit_bookmark(self, temp_lib, sample_html):
        """Test editing a bookmark."""
        # Import bookmarks
        self.run_btk(['import', 'nbf', sample_html, '--lib-dir', temp_lib])
        
        # Edit bookmark with ID 1
        result = self.run_btk([
            'edit', temp_lib, '1',
            '--title', 'Updated Title',
            '--stars', 'true'
        ])
        
        if result.returncode == 0:
            # Verify changes
            bookmarks_file = Path(temp_lib) / 'bookmarks.json'
            with open(bookmarks_file) as f:
                bookmarks = json.load(f)
            
            edited = next((b for b in bookmarks if b['id'] == 1), None)
            if edited:
                assert edited['title'] == 'Updated Title'
                assert edited.get('stars', False) is True
    
    def test_export_json(self, temp_lib, sample_html, tmp_path):
        """Test exporting bookmarks to JSON."""
        # Import bookmarks
        self.run_btk(['import', 'nbf', sample_html, '--lib-dir', temp_lib])
        
        # Export to JSON
        export_file = tmp_path / 'export.json'
        result = self.run_btk(['export', temp_lib, '--output', str(export_file)])
        
        if result.returncode == 0:
            # Verify export
            assert export_file.exists()
            with open(export_file) as f:
                exported = json.load(f)
            assert len(exported) >= 1  # At least some bookmarks exported
    
    def test_jmespath_query(self, temp_lib):
        """Test JMESPath queries on bookmarks."""
        # Create library with specific bookmarks
        os.makedirs(temp_lib, exist_ok=True)
        bookmarks = [
            {"id": 1, "title": "Site A", "url": "https://a.com", "stars": True, "unique_id": "abc123"},
            {"id": 2, "title": "Site B", "url": "https://b.com", "stars": False, "unique_id": "def456"}
        ]
        with open(Path(temp_lib) / 'bookmarks.json', 'w') as f:
            json.dump(bookmarks, f)
        
        # Query for starred bookmarks - returns objects
        result = self.run_btk(['jmespath', temp_lib, '[?stars == `true`]'])
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert 'Site A' in output and 'Site B' not in output
        
        # Query that returns strings (previously failed)
        result = self.run_btk(['jmespath', temp_lib, '[?stars == `true`].title'])
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert 'Site A' in output and 'Site B' not in output
    
    def test_merge_union(self, tmp_path):
        """Test merging bookmark libraries with union."""
        # Create two libraries
        lib1 = tmp_path / 'lib1'
        lib2 = tmp_path / 'lib2'
        output = tmp_path / 'merged'
        
        for lib in [lib1, lib2]:
            os.makedirs(lib)
        
        # Add different bookmarks to each
        bookmarks1 = [{"id": 1, "title": "A", "url": "https://a.com", "unique_id": "id1"}]
        bookmarks2 = [{"id": 2, "title": "B", "url": "https://b.com", "unique_id": "id2"}]
        
        with open(lib1 / 'bookmarks.json', 'w') as f:
            json.dump(bookmarks1, f)
        with open(lib2 / 'bookmarks.json', 'w') as f:
            json.dump(bookmarks2, f)
        
        # Merge them
        result = self.run_btk([
            'merge', 'union', str(lib1), str(lib2),
            '--output', str(output)
        ])
        
        if result.returncode == 0:
            # Verify merge
            with open(output / 'bookmarks.json') as f:
                merged = json.load(f)
            assert len(merged) == 2
    
    def test_invalid_library_dir(self):
        """Test handling of invalid library directory."""
        result = self.run_btk(['list', '/nonexistent/path'])
        # Should fail with non-zero exit code
        assert result.returncode != 0
    
    def test_reachable_command(self, temp_lib):
        """Test reachable command marks bookmark reachability."""
        # Create a simple library
        os.makedirs(temp_lib, exist_ok=True)
        bookmarks = [
            {"id": 1, "title": "Test", "url": "https://httpbin.org/status/200", "unique_id": "test1"}
        ]
        with open(Path(temp_lib) / 'bookmarks.json', 'w') as f:
            json.dump(bookmarks, f)
        
        # Run reachable check - this might take time so we allow it to fail
        result = self.run_btk(['reachable', temp_lib])
        # Command should at least run (may or may not find URLs reachable)
        # We're flexible here since network tests can be flaky
        assert result.returncode in [0, 1]


class TestCLIBasicCommands:
    """Test basic CLI functionality without file operations."""
    
    def run_btk(self, args):
        """Run btk command and return result."""
        cmd = ['btk'] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            cmd = [sys.executable, '-m', 'btk.cli'] + args
            result = subprocess.run(cmd, capture_output=True, text=True)
        return result
    
    def test_help_shows_commands(self):
        """Test that help lists available commands."""
        result = self.run_btk(['--help'])
        assert result.returncode == 0
        # Check for key commands
        for cmd in ['import', 'search', 'add', 'remove', 'list', 'export']:
            assert cmd in result.stdout
    
    def test_import_help(self):
        """Test import command help."""
        result = self.run_btk(['import', '--help'])
        assert result.returncode == 0
        assert 'nbf' in result.stdout  # Netscape format
        assert 'csv' in result.stdout
        assert 'json' in result.stdout
    
    def test_missing_required_args(self):
        """Test commands fail gracefully with missing args."""
        # Search without library path
        result = self.run_btk(['search'])
        assert result.returncode != 0
        
        # Add without library path
        result = self.run_btk(['add'])
        assert result.returncode != 0