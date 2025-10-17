"""
Comprehensive tests for btk/utils.py

Tests utility functions including:
- ensure_dir
- generate_unique_id
- extract_domain
- download_favicon
- filter_by_tags
- normalize_url
- validate_url
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from btk.utils import (
    ensure_dir,
    generate_unique_id,
    extract_domain,
    download_favicon,
    filter_by_tags,
    normalize_url,
    validate_url
)
from btk.models import Bookmark, Tag
from btk.db import Database


class TestEnsureDir:
    """Test ensure_dir function."""

    def test_create_directory(self):
        """Test creating a new directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "test_dir")
            ensure_dir(new_dir)

            assert os.path.exists(new_dir)
            assert os.path.isdir(new_dir)

    def test_create_nested_directories(self):
        """Test creating nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = os.path.join(tmpdir, "parent", "child", "grandchild")
            ensure_dir(nested_dir)

            assert os.path.exists(nested_dir)
            assert os.path.isdir(nested_dir)

    def test_existing_directory(self):
        """Test with existing directory (should not error)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ensure_dir(tmpdir)  # Should not raise error
            assert os.path.exists(tmpdir)


class TestGenerateUniqueId:
    """Test generate_unique_id function."""

    def test_with_url(self):
        """Test generating ID with URL."""
        unique_id = generate_unique_id(url="https://example.com")

        assert len(unique_id) == 8
        assert isinstance(unique_id, str)
        assert unique_id.isalnum() or all(c in '0123456789abcdef' for c in unique_id)

    def test_with_title(self):
        """Test generating ID with title."""
        unique_id = generate_unique_id(title="Example Title")

        assert len(unique_id) == 8
        assert isinstance(unique_id, str)

    def test_with_url_and_title(self):
        """Test generating ID with both URL and title."""
        unique_id = generate_unique_id(url="https://example.com", title="Example")

        assert len(unique_id) == 8
        assert isinstance(unique_id, str)

    def test_same_input_produces_same_id(self):
        """Test that same input produces same ID."""
        url = "https://example.com"
        id1 = generate_unique_id(url=url)
        id2 = generate_unique_id(url=url)

        assert id1 == id2

    def test_different_input_produces_different_id(self):
        """Test that different input produces different ID."""
        id1 = generate_unique_id(url="https://example.com")
        id2 = generate_unique_id(url="https://test.com")

        assert id1 != id2

    def test_without_url_or_title(self):
        """Test generating ID without URL or title (uses UUID)."""
        id1 = generate_unique_id()
        id2 = generate_unique_id()

        # Should generate different IDs each time (UUID-based)
        assert len(id1) == 8
        assert len(id2) == 8
        # Most likely different (UUID is random)
        # We can't assert they're different as there's a tiny chance they could be the same


class TestExtractDomain:
    """Test extract_domain function."""

    def test_simple_url(self):
        """Test extracting domain from simple URL."""
        domain = extract_domain("https://example.com")
        assert domain == "example.com"

    def test_url_with_path(self):
        """Test extracting domain from URL with path."""
        domain = extract_domain("https://example.com/path/to/page")
        assert domain == "example.com"

    def test_url_with_subdomain(self):
        """Test extracting domain from URL with subdomain."""
        domain = extract_domain("https://www.example.com")
        assert domain == "www.example.com"

    def test_url_with_port(self):
        """Test extracting domain from URL with port."""
        domain = extract_domain("https://example.com:8080")
        assert domain == "example.com:8080"

    def test_url_with_query(self):
        """Test extracting domain from URL with query parameters."""
        domain = extract_domain("https://example.com?param=value")
        assert domain == "example.com"


class TestDownloadFavicon:
    """Test download_favicon function."""

    @patch('requests.get')
    def test_successful_favicon_download(self, mock_get):
        """Test successful favicon download."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake_favicon_data"
        mock_response.headers = {'content-type': 'image/x-icon'}
        mock_get.return_value = mock_response

        result = download_favicon("https://example.com")

        assert result is not None
        data, mime_type = result
        assert data == b"fake_favicon_data"
        assert mime_type == 'image/x-icon'

    @patch('requests.get')
    def test_favicon_download_with_png(self, mock_get):
        """Test favicon download with PNG format."""
        # Mock successful response for PNG
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake_png_data"
        mock_response.headers = {'content-type': 'image/png'}
        mock_get.return_value = mock_response

        result = download_favicon("https://example.com")

        assert result is not None
        data, mime_type = result
        assert mime_type == 'image/png'

    @patch('requests.get')
    def test_favicon_download_no_content_type(self, mock_get):
        """Test favicon download when server doesn't provide content-type."""
        # Mock response without content-type header
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake_data"
        mock_response.headers = {}
        mock_get.return_value = mock_response

        result = download_favicon("https://example.com/favicon.ico")

        assert result is not None
        data, mime_type = result
        # Should guess from URL
        assert 'image' in mime_type or mime_type == 'application/octet-stream'

    @patch('requests.get')
    def test_favicon_download_404(self, mock_get):
        """Test favicon download when URL returns 404."""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.content = b""
        mock_get.return_value = mock_response

        result = download_favicon("https://example.com")

        assert result is None

    @patch('requests.get')
    def test_favicon_download_network_error(self, mock_get):
        """Test favicon download with network error."""
        # Mock network error
        mock_get.side_effect = Exception("Network error")

        result = download_favicon("https://example.com")

        assert result is None


class TestFilterByTags:
    """Test filter_by_tags function."""

    @pytest.fixture
    def bookmarks_with_tags(self):
        """Create bookmarks with various tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            db.add(url="https://example.com", title="Example", tags=["programming/python"])
            db.add(url="https://test.com", title="Test", tags=["programming/java"])
            db.add(url="https://another.com", title="Another", tags=["tools"])

            yield db.all()

    def test_filter_by_exact_prefix(self, bookmarks_with_tags):
        """Test filtering by exact tag prefix."""
        filtered = filter_by_tags(bookmarks_with_tags, "programming/python")

        assert len(filtered) == 1
        assert filtered[0].url == "https://example.com"

    def test_filter_by_partial_prefix(self, bookmarks_with_tags):
        """Test filtering by partial tag prefix."""
        filtered = filter_by_tags(bookmarks_with_tags, "programming")

        assert len(filtered) == 2
        urls = [b.url for b in filtered]
        assert "https://example.com" in urls
        assert "https://test.com" in urls

    def test_filter_no_matches(self, bookmarks_with_tags):
        """Test filtering with no matches."""
        filtered = filter_by_tags(bookmarks_with_tags, "nonexistent")

        assert len(filtered) == 0

    def test_filter_empty_list(self):
        """Test filtering empty bookmark list."""
        filtered = filter_by_tags([], "anything")

        assert len(filtered) == 0


class TestNormalizeUrl:
    """Test normalize_url function."""

    def test_remove_trailing_slash(self):
        """Test removing trailing slash."""
        url = normalize_url("https://example.com/")
        assert url == "https://example.com"

    def test_preserve_path(self):
        """Test that path is preserved."""
        url = normalize_url("https://example.com/path")
        assert url == "https://example.com/path"

    def test_url_without_trailing_slash(self):
        """Test URL without trailing slash remains unchanged."""
        url = normalize_url("https://example.com")
        assert url == "https://example.com"

    def test_preserve_query_params(self):
        """Test that query parameters are preserved."""
        url = normalize_url("https://example.com?param=value")
        assert url == "https://example.com?param=value"

    def test_complex_url(self):
        """Test normalizing complex URL."""
        url = normalize_url("https://example.com/path/to/page?param=value&other=test")
        assert url == "https://example.com/path/to/page?param=value&other=test"


class TestValidateUrl:
    """Test validate_url function."""

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        assert validate_url("http://example.com") is True

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        assert validate_url("https://example.com") is True

    def test_url_with_path(self):
        """Test valid URL with path."""
        assert validate_url("https://example.com/path") is True

    def test_url_with_query(self):
        """Test valid URL with query parameters."""
        assert validate_url("https://example.com?param=value") is True

    def test_url_with_subdomain(self):
        """Test valid URL with subdomain."""
        assert validate_url("https://www.example.com") is True

    def test_invalid_scheme(self):
        """Test invalid scheme (not http/https)."""
        assert validate_url("ftp://example.com") is False

    def test_no_scheme(self):
        """Test URL without scheme."""
        assert validate_url("example.com") is False

    def test_no_domain(self):
        """Test URL without domain."""
        assert validate_url("https://") is False

    def test_empty_string(self):
        """Test empty string."""
        assert validate_url("") is False

    def test_invalid_format(self):
        """Test completely invalid format."""
        assert validate_url("not a url") is False
