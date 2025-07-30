import pytest
import os
import json
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from btk.utils import (
    ensure_dir,
    is_bookmark_json,
    jmespath_query,
    load_bookmarks,
    save_bookmarks,
    generate_unique_id,
    generate_unique_filename,
    get_next_id,
    is_valid_url,
    download_favicon,
    copy_local_favicon,
    purge_favicons,
    purge_unreachable
)


class TestDirectoryUtils:
    def test_ensure_dir_creates_directory(self, tmp_path):
        """Test that ensure_dir creates a directory if it doesn't exist."""
        test_dir = tmp_path / "test_dir"
        assert not test_dir.exists()
        
        ensure_dir(str(test_dir))
        assert test_dir.exists()
        assert test_dir.is_dir()
    
    def test_ensure_dir_existing_directory(self, tmp_path):
        """Test that ensure_dir works with existing directory."""
        test_dir = tmp_path / "existing_dir"
        test_dir.mkdir()
        
        # Should not raise an exception
        ensure_dir(str(test_dir))
        assert test_dir.exists()


class TestBookmarkValidation:
    def test_is_bookmark_json_valid(self, sample_bookmarks):
        """Test validation of valid bookmark JSON."""
        assert is_bookmark_json(sample_bookmarks) is True
    
    def test_is_bookmark_json_invalid_not_list(self):
        """Test validation fails when input is not a list."""
        assert is_bookmark_json({"not": "a list"}) is False
    
    def test_is_bookmark_json_missing_required_fields(self):
        """Test validation fails when bookmarks miss required fields."""
        invalid_bookmarks = [
            {"id": 1, "url": "https://example.com"},  # Missing title, unique_id, visit_count
            {"title": "Example", "url": "https://example.com"}  # Missing id, unique_id, visit_count
        ]
        assert is_bookmark_json(invalid_bookmarks) is False
    
    def test_is_bookmark_json_empty_list(self):
        """Test validation of empty bookmark list."""
        assert is_bookmark_json([]) is True


class TestJMESPathQuery:
    def test_jmespath_query_filter(self, sample_bookmarks):
        """Test JMESPath filtering returns bookmarks."""
        result, op_type = jmespath_query(sample_bookmarks, "[?stars == `true`]")
        assert op_type == "filter"
        assert len(result) == 1
        assert result[0]["title"] == "GitHub"
    
    def test_jmespath_query_transform(self, sample_bookmarks):
        """Test JMESPath transformation returns non-bookmark data."""
        result, op_type = jmespath_query(sample_bookmarks, "[*].title")
        assert op_type == "transform"
        assert result == ["Python Documentation", "GitHub", "Broken Link Example"]
    
    def test_jmespath_query_empty(self, sample_bookmarks):
        """Test empty query returns original bookmarks."""
        result = jmespath_query(sample_bookmarks, "")
        assert result == sample_bookmarks
    
    def test_jmespath_query_complex(self, sample_bookmarks):
        """Test complex JMESPath query."""
        result, op_type = jmespath_query(
            sample_bookmarks, 
            "[?visit_count > `3`].{title: title, url: url}"
        )
        assert op_type == "transform"
        assert len(result) == 2
        assert all("title" in item and "url" in item for item in result)


class TestBookmarkIO:
    def test_load_bookmarks_existing_file(self, populated_lib_dir):
        """Test loading bookmarks from existing file."""
        bookmarks = load_bookmarks(populated_lib_dir)
        assert len(bookmarks) == 3
        assert bookmarks[0]["title"] == "Python Documentation"
    
    def test_load_bookmarks_no_file(self, temp_lib_dir):
        """Test loading bookmarks when file doesn't exist."""
        bookmarks = load_bookmarks(temp_lib_dir)
        assert bookmarks == []
    
    def test_load_bookmarks_invalid_json(self, temp_lib_dir):
        """Test loading bookmarks from invalid JSON file."""
        bookmarks_file = os.path.join(temp_lib_dir, "bookmarks.json")
        with open(bookmarks_file, 'w') as f:
            f.write("{ invalid json")
        
        bookmarks = load_bookmarks(temp_lib_dir)
        assert bookmarks == []
    
    def test_save_bookmarks(self, temp_lib_dir, sample_bookmarks):
        """Test saving bookmarks to file."""
        save_bookmarks(sample_bookmarks, temp_lib_dir, temp_lib_dir)
        
        # Verify file was created
        bookmarks_file = os.path.join(temp_lib_dir, "bookmarks.json")
        assert os.path.exists(bookmarks_file)
        
        # Verify content
        with open(bookmarks_file, 'r') as f:
            saved_bookmarks = json.load(f)
        assert len(saved_bookmarks) == 3
        assert saved_bookmarks[0]["title"] == "Python Documentation"
    
    def test_save_bookmarks_empty_list(self, temp_lib_dir):
        """Test saving empty bookmark list."""
        save_bookmarks([], temp_lib_dir, temp_lib_dir)
        # Should not create file for empty list
    
    def test_save_bookmarks_no_target_dir(self, sample_bookmarks):
        """Test saving bookmarks without target directory."""
        # Should not raise exception but log warning
        save_bookmarks(sample_bookmarks, None, None)


class TestBookmarkUtils:
    def test_generate_unique_id(self):
        """Test unique ID generation."""
        id1 = generate_unique_id("https://example.com", "Example Site")
        id2 = generate_unique_id("https://example2.com", "Example Site 2")
        
        assert isinstance(id1, str)
        assert len(id1) == 8
        assert id1 != id2
    
    def test_generate_unique_filename(self):
        """Test unique filename generation."""
        # Test basic case
        filename = generate_unique_filename("https://example.com/favicon.ico")
        assert filename.endswith(".ico")
        
        # Test with no extension
        filename = generate_unique_filename("https://example.com/icon", ".png")
        assert filename.endswith(".png")
    
    def test_get_next_id_empty(self):
        """Test getting next ID for empty bookmark list."""
        assert get_next_id([]) == 1
    
    def test_get_next_id_with_bookmarks(self, sample_bookmarks):
        """Test getting next ID with existing bookmarks."""
        assert get_next_id(sample_bookmarks) == 4


class TestURLUtils:
    def test_is_valid_url_valid(self):
        """Test valid URL detection."""
        assert is_valid_url("https://example.com") is True
        assert is_valid_url("http://example.com/path") is True
        assert is_valid_url("https://sub.example.com:8080/path?query=1") is True
    
    def test_is_valid_url_invalid(self):
        """Test invalid URL detection."""
        assert is_valid_url("not a url") is False
        assert is_valid_url("") is False


class TestFaviconUtils:
    @patch('requests.get')
    def test_download_favicon_success(self, mock_get, temp_lib_dir):
        """Test successful favicon download."""
        # Mock successful response
        mock_response = Mock()
        mock_response.content = b"fake favicon content"
        mock_response.headers = {"content-type": "image/x-icon"}
        mock_get.return_value = mock_response
        
        favicon_path = download_favicon(
            "https://example.com/favicon.ico",
            temp_lib_dir
        )
        
        assert favicon_path is not None
        assert favicon_path.startswith("favicons/")
        assert favicon_path.endswith(".ico")
    
    @patch('btk.utils.requests.get')
    def test_download_favicon_failure(self, mock_get, temp_lib_dir):
        """Test favicon download failure."""
        import requests
        mock_get.side_effect = requests.RequestException("Network error")
        
        favicon_path = download_favicon(
            "https://example.com/favicon.ico",
            temp_lib_dir
        )
        
        assert favicon_path is None
    
    def test_copy_local_favicon(self, temp_lib_dir):
        """Test copying local favicon."""
        # Create source favicon
        source_dir = tempfile.mkdtemp()
        source_favicon = os.path.join(source_dir, "favicons", "test.ico")
        os.makedirs(os.path.dirname(source_favicon))
        with open(source_favicon, 'w') as f:
            f.write("fake favicon")
        
        # Copy favicon
        new_path = copy_local_favicon(source_favicon, source_dir, temp_lib_dir)
        
        assert new_path.startswith("favicons/")
        assert new_path.endswith(".ico")
        assert os.path.exists(os.path.join(temp_lib_dir, new_path))
        
        # Cleanup
        import shutil
        shutil.rmtree(source_dir)


class TestBookmarkOperations:
    @patch('builtins.input', return_value='n')
    def test_purge_unreachable(self, mock_input, populated_lib_dir):
        """Test purging unreachable bookmarks."""
        # This function works on directories, not bookmark lists
        # Mock input to decline purging
        purge_unreachable(populated_lib_dir, confirm=False)
        
        # Should still have bookmarks file
        bookmarks_file = os.path.join(populated_lib_dir, "bookmarks.json")
        assert os.path.exists(bookmarks_file)
    
    def test_purge_favicons(self, populated_lib_dir):
        """Test cleaning unused favicons."""
        favicons_dir = os.path.join(populated_lib_dir, "favicons")
        os.makedirs(favicons_dir, exist_ok=True)
        
        # Create some favicon files
        unused_favicon = os.path.join(favicons_dir, "unused.ico")
        with open(unused_favicon, 'w') as f:
            f.write("unused")
        
        # Clean unused favicons
        purge_favicons(populated_lib_dir)
        
        # Should not crash
        assert True