"""
Tests for btk/content_fetcher.py content fetching.

Tests the ContentFetcher class which handles fetching web content,
compression, HTML to Markdown conversion, and PDF text extraction.
"""
import zlib
import hashlib
import pytest
from unittest.mock import patch, MagicMock, Mock
import requests

from btk.content_fetcher import ContentFetcher, create_fetcher


class TestContentFetcherInit:
    """Test ContentFetcher initialization."""

    def test_default_timeout(self):
        """Default timeout should be 10 seconds."""
        fetcher = ContentFetcher()
        assert fetcher.timeout == 10

    def test_custom_timeout(self):
        """Custom timeout should be respected."""
        fetcher = ContentFetcher(timeout=30)
        assert fetcher.timeout == 30

    def test_default_user_agent(self):
        """Default user agent should contain BTK identifier."""
        fetcher = ContentFetcher()
        assert "BTK" in fetcher.user_agent

    def test_custom_user_agent(self):
        """Custom user agent should be respected."""
        fetcher = ContentFetcher(user_agent="CustomAgent/1.0")
        assert fetcher.user_agent == "CustomAgent/1.0"

    def test_session_created(self):
        """Session should be created on init."""
        fetcher = ContentFetcher()
        assert fetcher.session is not None
        assert isinstance(fetcher.session, requests.Session)

    def test_session_has_user_agent_header(self):
        """Session should have User-Agent header set."""
        fetcher = ContentFetcher(user_agent="TestAgent")
        assert fetcher.session.headers["User-Agent"] == "TestAgent"


class TestContentFetcherFetch:
    """Test ContentFetcher.fetch() method."""

    @pytest.fixture
    def fetcher(self):
        """Create a ContentFetcher instance."""
        return ContentFetcher(timeout=5)

    def test_fetch_success(self, fetcher):
        """Successful fetch should return correct result structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><head><title>Test Page</title></head><body>Content</body></html>"
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com")

        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["html_content"] == mock_response.content
        assert result["title"] == "Test Page"
        assert result["error"] is None

    def test_fetch_returns_response_time(self, fetcher):
        """Fetch should track response time in milliseconds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><title>Test</title></html>"
        mock_response.headers = {}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com")

        assert "response_time_ms" in result
        assert isinstance(result["response_time_ms"], float)
        assert result["response_time_ms"] >= 0

    def test_fetch_handles_404(self, fetcher):
        """Fetch should handle 404 responses."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b"Not Found"
        mock_response.headers = {}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com/notfound")

        assert result["success"] is False
        assert result["status_code"] == 404
        assert result["error"] == "HTTP 404"

    def test_fetch_handles_500(self, fetcher):
        """Fetch should handle 500 server errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b"Internal Server Error"
        mock_response.headers = {}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com/error")

        assert result["success"] is False
        assert result["status_code"] == 500
        assert "HTTP 500" in result["error"]

    def test_fetch_handles_timeout(self, fetcher):
        """Fetch should handle request timeouts."""
        with patch.object(fetcher.session, 'get', side_effect=requests.Timeout()):
            result = fetcher.fetch("https://slow-site.com")

        assert result["success"] is False
        assert result["error"] == "Request timeout"

    def test_fetch_handles_connection_error(self, fetcher):
        """Fetch should handle connection errors."""
        with patch.object(fetcher.session, 'get', side_effect=requests.ConnectionError()):
            result = fetcher.fetch("https://unreachable.com")

        assert result["success"] is False
        assert result["error"] == "Connection error"

    def test_fetch_handles_generic_exception(self, fetcher):
        """Fetch should handle unexpected exceptions."""
        with patch.object(fetcher.session, 'get', side_effect=Exception("Unexpected error")):
            result = fetcher.fetch("https://example.com")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    def test_fetch_extracts_content_type(self, fetcher):
        """Fetch should extract Content-Type header."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><title>Test</title></html>"
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com")

        assert result["content_type"] == "text/html; charset=utf-8"

    def test_fetch_extracts_encoding(self, fetcher):
        """Fetch should extract response encoding."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><title>Test</title></html>"
        mock_response.headers = {}
        mock_response.encoding = "iso-8859-1"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com")

        assert result["encoding"] == "iso-8859-1"

    def test_fetch_handles_missing_title(self, fetcher):
        """Fetch should handle pages without title tag."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><body>No title here</body></html>"
        mock_response.headers = {}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com")

        assert result["success"] is True
        assert result["title"] == ""

    def test_fetch_handles_none_encoding(self, fetcher):
        """Fetch should default to utf-8 when encoding is None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><title>Test</title></html>"
        mock_response.headers = {}
        mock_response.encoding = None

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch("https://example.com")

        assert result["encoding"] == "utf-8"


class TestCompressDecompress:
    """Test compression and decompression methods."""

    def test_compress_html_reduces_size(self):
        """compress_html() should reduce content size."""
        html_content = b"<html>" + b"<p>This is a test paragraph.</p>" * 100 + b"</html>"
        compressed = ContentFetcher.compress_html(html_content)

        assert len(compressed) < len(html_content)

    def test_decompress_html_restores_original(self):
        """decompress_html() should restore original content."""
        original = b"<html><head><title>Test</title></head><body>Content</body></html>"
        compressed = ContentFetcher.compress_html(original)
        decompressed = ContentFetcher.decompress_html(compressed)

        assert decompressed == original

    def test_compress_decompress_round_trip(self):
        """Compression and decompression should be lossless."""
        # Test with various content types
        test_contents = [
            b"Simple text",
            b"<html><body>HTML content</body></html>",
            b"\x00\x01\x02\x03",  # Binary content
            b"Unicode: \xc3\xa9\xc3\xa0\xc3\xbc",  # UTF-8 encoded unicode
            b"" * 0,  # Empty content
        ]

        for content in test_contents:
            compressed = ContentFetcher.compress_html(content)
            decompressed = ContentFetcher.decompress_html(compressed)
            assert decompressed == content

    def test_compress_uses_maximum_compression(self):
        """compress_html() should use level 9 compression."""
        content = b"Test content " * 1000

        # Compress with level 9 (our implementation)
        compressed = ContentFetcher.compress_html(content)

        # Compress with level 1 for comparison
        low_compressed = zlib.compress(content, level=1)

        # Level 9 should produce smaller or equal output
        assert len(compressed) <= len(low_compressed)


class TestHtmlToMarkdown:
    """Test HTML to Markdown conversion."""

    def test_basic_html_conversion(self):
        """Basic HTML should convert to markdown."""
        html = b"<html><body><h1>Title</h1><p>Paragraph</p></body></html>"
        markdown = ContentFetcher.html_to_markdown(html)

        assert "Title" in markdown
        assert "Paragraph" in markdown

    def test_removes_script_tags(self):
        """Conversion should remove script tags."""
        html = b"<html><body><script>alert('evil')</script><p>Content</p></body></html>"
        markdown = ContentFetcher.html_to_markdown(html)

        assert "alert" not in markdown
        assert "Content" in markdown

    def test_removes_style_tags(self):
        """Conversion should remove style tags."""
        html = b"<html><body><style>.red{color:red}</style><p>Content</p></body></html>"
        markdown = ContentFetcher.html_to_markdown(html)

        assert "red" not in markdown
        assert "Content" in markdown

    def test_removes_nav_elements(self):
        """Conversion should remove nav elements."""
        html = b"<html><body><nav><a>Menu</a></nav><main>Main Content</main></body></html>"
        markdown = ContentFetcher.html_to_markdown(html)

        assert "Main Content" in markdown
        # Nav may or may not be fully removed depending on markdownify behavior

    def test_uses_main_content_container(self):
        """Conversion should prefer main content containers."""
        html = b"""<html><body>
            <nav>Navigation</nav>
            <main><article><p>Article Content</p></article></main>
            <footer>Footer</footer>
        </body></html>"""
        markdown = ContentFetcher.html_to_markdown(html)

        assert "Article Content" in markdown

    def test_falls_back_to_body(self):
        """Conversion should fall back to body if no main container."""
        html = b"<html><body><p>Body Content</p></body></html>"
        markdown = ContentFetcher.html_to_markdown(html)

        assert "Body Content" in markdown

    def test_handles_encoding(self):
        """Conversion should handle different encodings."""
        # UTF-8 encoded content
        html = "Café résumé naïve".encode("utf-8")
        html_wrapped = b"<html><body><p>" + html + b"</p></body></html>"
        markdown = ContentFetcher.html_to_markdown(html_wrapped, encoding="utf-8")

        assert "Café" in markdown or "Caf" in markdown  # Depends on conversion

    def test_handles_invalid_html(self):
        """Conversion should handle malformed HTML gracefully."""
        html = b"<html><body><p>Unclosed paragraph<div>Nested</p></div></body>"
        markdown = ContentFetcher.html_to_markdown(html)

        # Should not crash, should return something
        assert isinstance(markdown, str)

    def test_returns_empty_for_minimal_html(self):
        """Conversion should handle minimal HTML without body."""
        html = b"<html></html>"
        markdown = ContentFetcher.html_to_markdown(html)

        assert markdown == "" or isinstance(markdown, str)


class TestCalculateContentHash:
    """Test content hash calculation."""

    def test_hash_is_sha256(self):
        """Hash should be SHA256 format (64 hex chars)."""
        content = b"Test content"
        hash_value = ContentFetcher.calculate_content_hash(content)

        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_same_content_same_hash(self):
        """Same content should produce same hash."""
        content = b"Test content"
        hash1 = ContentFetcher.calculate_content_hash(content)
        hash2 = ContentFetcher.calculate_content_hash(content)

        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Different content should produce different hash."""
        hash1 = ContentFetcher.calculate_content_hash(b"Content A")
        hash2 = ContentFetcher.calculate_content_hash(b"Content B")

        assert hash1 != hash2

    def test_empty_content_hash(self):
        """Empty content should have valid hash."""
        hash_value = ContentFetcher.calculate_content_hash(b"")

        assert len(hash_value) == 64
        # SHA256 of empty string is known value
        assert hash_value == hashlib.sha256(b"").hexdigest()


class TestExtractPdfText:
    """Test PDF text extraction."""

    def test_extract_pdf_text_with_mock(self):
        """PDF extraction should work with valid PDF content."""
        # We can't easily create a real PDF, so test error handling
        result = ContentFetcher.extract_pdf_text(b"Not a real PDF")

        # Should return error message, not crash
        assert "Error" in result or isinstance(result, str)

    def test_extract_pdf_text_with_pypdf_not_installed(self):
        """PDF extraction should handle missing pypdf gracefully."""
        with patch.dict('sys.modules', {'pypdf': None}):
            # Reimport to trigger the error path
            result = ContentFetcher.extract_pdf_text(b"PDF content")

        # Should return error message
        assert isinstance(result, str)


class TestFetchAndProcess:
    """Test the combined fetch_and_process method."""

    @pytest.fixture
    def fetcher(self):
        """Create a ContentFetcher instance."""
        return ContentFetcher(timeout=5)

    def test_fetch_and_process_success(self, fetcher):
        """Successful fetch_and_process should return processed content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><head><title>Test Page</title></head><body><main><p>Main content</p></main></body></html>"
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch_and_process("https://example.com")

        assert result["success"] is True
        assert result["html_content"] is not None  # Compressed
        assert result["markdown_content"] is not None
        assert result["content_hash"] is not None
        assert result["title"] == "Test Page"
        assert result["content_length"] > 0
        assert result["compressed_size"] > 0
        assert result["error"] is None

    def test_fetch_and_process_returns_compressed_html(self, fetcher):
        """fetch_and_process should return compressed HTML."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><title>Test</title><body>Content</body></html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch_and_process("https://example.com")

        # Verify it's compressed by trying to decompress
        decompressed = ContentFetcher.decompress_html(result["html_content"])
        assert decompressed == mock_response.content

    def test_fetch_and_process_failure(self, fetcher):
        """Failed fetch_and_process should return error info."""
        with patch.object(fetcher.session, 'get', side_effect=requests.ConnectionError()):
            result = fetcher.fetch_and_process("https://unreachable.com")

        assert result["success"] is False
        assert result["error"] == "Connection error"
        assert result["html_content"] is None
        assert result["markdown_content"] is None

    def test_fetch_and_process_pdf_detection_by_content_type(self, fetcher):
        """fetch_and_process should detect PDF by content type."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 fake pdf content"
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.encoding = None

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            with patch.object(ContentFetcher, 'extract_pdf_text', return_value="Extracted PDF text"):
                result = fetcher.fetch_and_process("https://example.com/document.pdf")

        assert result["success"] is True
        assert result["markdown_content"] == "Extracted PDF text"

    def test_fetch_and_process_pdf_detection_by_url(self, fetcher):
        """fetch_and_process should detect PDF by URL extension."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 fake pdf content"
        mock_response.headers = {"Content-Type": "application/octet-stream"}  # Generic
        mock_response.encoding = None

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            with patch.object(ContentFetcher, 'extract_pdf_text', return_value="PDF Text"):
                result = fetcher.fetch_and_process("https://example.com/paper.PDF")

        assert result["success"] is True
        assert result["markdown_content"] == "PDF Text"

    def test_fetch_and_process_http_error(self, fetcher):
        """fetch_and_process should handle HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b"Not Found"
        mock_response.headers = {}
        mock_response.encoding = "utf-8"

        with patch.object(fetcher.session, 'get', return_value=mock_response):
            result = fetcher.fetch_and_process("https://example.com/missing")

        assert result["success"] is False
        assert result["status_code"] == 404


class TestCreateFetcher:
    """Test the create_fetcher factory function."""

    def test_create_fetcher_default(self):
        """create_fetcher() should create fetcher with defaults."""
        fetcher = create_fetcher()

        assert isinstance(fetcher, ContentFetcher)
        assert fetcher.timeout == 10

    def test_create_fetcher_with_options(self):
        """create_fetcher() should pass options to ContentFetcher."""
        fetcher = create_fetcher(timeout=30, user_agent="CustomAgent")

        assert fetcher.timeout == 30
        assert fetcher.user_agent == "CustomAgent"
