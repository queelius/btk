import pytest
import os
import tempfile
from unittest.mock import Mock, patch, mock_open
from datetime import datetime, timezone

from btk.tools import (
    import_bookmarks,
    search_bookmarks,
    add_bookmark,
    remove_bookmark,
    list_bookmarks,
    visit_bookmark
)


class TestImportBookmarks:
    def test_import_bookmarks_html(self, temp_lib_dir, sample_html_bookmarks):
        """Test importing bookmarks from HTML file."""
        # Create temporary HTML file
        html_file = os.path.join(temp_lib_dir, "bookmarks.html")
        with open(html_file, 'w') as f:
            f.write(sample_html_bookmarks)
        
        # Import bookmarks
        bookmarks = []
        imported = import_bookmarks(html_file, bookmarks, temp_lib_dir)
        
        assert len(imported) == 3
        assert any(b["title"] == "Python.org" for b in imported)
        assert any(b["title"] == "GitHub" for b in imported)
    
    def test_import_bookmarks_no_duplicates(self, sample_bookmarks, temp_lib_dir):
        """Test that importing doesn't create duplicates with same URL and title."""
        # First, fix the unique_id in sample_bookmarks to match what would be generated
        import hashlib
        for bookmark in sample_bookmarks:
            unique_string = f"{bookmark['url']}{bookmark['title']}"
            bookmark['unique_id'] = hashlib.sha256(unique_string.encode('utf-8')).hexdigest()[:8]
        
        # Create HTML with exact duplicate (same URL and title)
        html_content = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
        <DL><p>
            <DT><A HREF="https://github.com">GitHub</A>
        </DL><p>
        """
        
        html_file = os.path.join(temp_lib_dir, "dup.html")
        with open(html_file, 'w') as f:
            f.write(html_content)
        
        # Import should skip duplicate
        original_len = len(sample_bookmarks)
        imported = import_bookmarks(html_file, sample_bookmarks.copy(), temp_lib_dir)
        assert len(imported) == original_len  # No new bookmark added


class TestSearchBookmarks:
    def test_search_bookmarks_by_title(self, sample_bookmarks):
        """Test searching bookmarks by title."""
        results = search_bookmarks(sample_bookmarks, "Python")
        assert len(results) == 1
        assert results[0]["title"] == "Python Documentation"
    
    def test_search_bookmarks_by_url(self, sample_bookmarks):
        """Test searching bookmarks by URL."""
        results = search_bookmarks(sample_bookmarks, "github")
        assert len(results) == 1
        assert results[0]["url"] == "https://github.com"
    
    def test_search_bookmarks_by_description(self, sample_bookmarks):
        """Test searching bookmarks by description."""
        results = search_bookmarks(sample_bookmarks, "hosting")
        assert len(results) == 1  # Search now includes description field
        assert results[0]["url"] == "https://github.com"
    
    def test_search_bookmarks_by_tags(self, sample_bookmarks):
        """Test searching bookmarks by tags."""
        results = search_bookmarks(sample_bookmarks, "development")
        assert len(results) == 1  # Search now includes tags field
        assert results[0]["url"] == "https://github.com"
    
    def test_search_bookmarks_case_insensitive(self, sample_bookmarks):
        """Test case-insensitive search."""
        results = search_bookmarks(sample_bookmarks, "PYTHON")
        assert len(results) == 1
        assert results[0]["title"] == "Python Documentation"
    
    def test_search_bookmarks_no_results(self, sample_bookmarks):
        """Test search with no results."""
        results = search_bookmarks(sample_bookmarks, "nonexistent")
        assert len(results) == 0


class TestAddBookmark:
    def test_add_bookmark_basic(self, temp_lib_dir):
        """Test adding a basic bookmark."""
        bookmarks = []
        result = add_bookmark(
            bookmarks,
            title="New Site",
            url="https://newsite.com",
            stars=False,
            tags=[],
            description="",
            lib_dir=temp_lib_dir
        )
        
        assert len(result) == 1
        assert result[0]["title"] == "New Site"
        assert result[0]["url"] == "https://newsite.com"
        assert result[0]["stars"] is False
        assert result[0]["tags"] == []
        assert result[0]["visit_count"] == 0
    
    def test_add_bookmark_with_metadata(self, temp_lib_dir):
        """Test adding bookmark with full metadata."""
        bookmarks = []
        result = add_bookmark(
            bookmarks,
            title="Starred Site",
            url="https://starred.com",
            stars=True,
            tags=["important", "reference"],
            description="A very important site",
            lib_dir=temp_lib_dir
        )
        
        assert result[0]["stars"] is True
        assert result[0]["tags"] == ["important", "reference"]
        assert result[0]["description"] == "A very important site"
    
    def test_add_bookmark_preserves_url(self, temp_lib_dir):
        """Test that URL is not added if invalid."""
        bookmarks = []
        result = add_bookmark(
            bookmarks,
            title="No Scheme",
            url="example.com",
            stars=False,
            tags=[],
            description="",
            lib_dir=temp_lib_dir
        )
        
        # URL validation should reject invalid URLs
        assert len(result) == 0  # Invalid URL not added
    
    def test_add_bookmark_generates_id(self, sample_bookmarks, temp_lib_dir):
        """Test ID generation for new bookmarks."""
        original_len = len(sample_bookmarks)
        result = add_bookmark(
            sample_bookmarks.copy(),
            title="New",
            url="https://new.com",
            stars=False,
            tags=[],
            description="",
            lib_dir=temp_lib_dir
        )
        
        assert len(result) == original_len + 1
        assert result[-1]["id"] == 4  # Next ID after 1, 2, 3
        assert len(result[-1]["unique_id"]) == 8


class TestRemoveBookmark:
    def test_remove_bookmark_by_id(self, sample_bookmarks):
        """Test removing bookmark by ID."""
        result = remove_bookmark(sample_bookmarks.copy(), 2)
        assert len(result) == 2
        assert not any(b["id"] == 2 for b in result)
    
    def test_remove_bookmark_not_found(self, sample_bookmarks):
        """Test removing non-existent bookmark."""
        original_len = len(sample_bookmarks)
        result = remove_bookmark(sample_bookmarks.copy(), 999)
        assert len(result) == original_len  # No change


class TestListBookmarks:
    def test_list_all_bookmarks(self, sample_bookmarks):
        """Test listing all bookmarks."""
        result = list_bookmarks(sample_bookmarks)
        assert len(result) == len(sample_bookmarks)
    
    def test_list_bookmarks_by_indices(self, sample_bookmarks):
        """Test listing specific bookmarks by index."""
        result = list_bookmarks(sample_bookmarks, indices=[1, 3])
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3
    
    def test_list_bookmarks_invalid_indices(self, sample_bookmarks):
        """Test listing with invalid indices."""
        result = list_bookmarks(sample_bookmarks, indices=[999])
        assert len(result) == 0


class TestVisitBookmark:
    @patch('webbrowser.open')
    def test_visit_bookmark_browser(self, mock_browser, sample_bookmarks):
        """Test visiting bookmark in browser."""
        visit_bookmark(sample_bookmarks, 1, method='browser')
        mock_browser.assert_called_once_with("https://docs.python.org")
    
    @patch('requests.get')
    def test_visit_bookmark_console(self, mock_get, sample_bookmarks):
        """Test fetching bookmark content via console method."""
        # Mock response
        mock_response = Mock()
        mock_response.text = "<html><head><title>Test</title></head><body>Content</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Should not raise exception
        visit_bookmark(sample_bookmarks, 1, method='console')
        mock_get.assert_called_once()
    
    def test_visit_bookmark_not_found(self, sample_bookmarks):
        """Test visiting non-existent bookmark."""
        # Should handle gracefully
        visit_bookmark(sample_bookmarks, 999, method='browser')
    
    def test_visit_bookmark_updates_stats(self, sample_bookmarks, temp_lib_dir):
        """Test that visiting updates visit count and last visited."""
        bookmarks = sample_bookmarks.copy()
        original_count = bookmarks[0]["visit_count"]
        
        with patch('webbrowser.open'):
            result = visit_bookmark(bookmarks, 1, method='browser', lib_dir=temp_lib_dir)
            
            visited = next(b for b in result if b["id"] == 1)
            assert visited["visit_count"] == original_count + 1
            assert visited["last_visited"] is not None


# Note: check_reachability function doesn't exist in tools.py, it's in utils.py as check_reachable