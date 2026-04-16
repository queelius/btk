"""
Tests for bookmark_memex.content pipeline (extractor and fetcher).

Tests cover pure functions in extractor.py and the ContentFetcher class
in fetcher.py. No network calls are made.
"""

import zlib
import hashlib
import pytest
import requests
from unittest.mock import patch, MagicMock

from bookmark_memex.content.extractor import (
    compress_html,
    decompress_html,
    content_hash,
    html_to_markdown,
    extract_text,
    extract_pdf_text,
)
from bookmark_memex.content.fetcher import ContentFetcher
from bookmark_memex.content import (
    ContentFetcher as ContentFetcherFromInit,
    compress_html as compress_from_init,
    decompress_html as decompress_from_init,
    content_hash as hash_from_init,
    html_to_markdown as md_from_init,
    extract_text as extract_from_init,
    extract_pdf_text as pdf_from_init,
)


# ---------------------------------------------------------------------------
# compress / decompress
# ---------------------------------------------------------------------------

class TestCompressDecompress:
    """Test zlib compression and decompression."""

    def test_roundtrip(self):
        """compress then decompress returns original bytes."""
        original = b"<html><body><p>Hello world!</p></body></html>"
        assert decompress_html(compress_html(original)) == original

    def test_roundtrip_empty(self):
        """Roundtrip works for empty bytes."""
        assert decompress_html(compress_html(b"")) == b""

    def test_compression_reduces_size_on_large_input(self):
        """Compressing a large repetitive payload produces smaller output."""
        large = b"<p>repeat content here</p>" * 500
        compressed = compress_html(large)
        assert len(compressed) < len(large)

    def test_uses_level_9(self):
        """compress_html uses zlib level 9 (matches manual reference)."""
        data = b"some content " * 200
        expected = zlib.compress(data, level=9)
        assert compress_html(data) == expected

    def test_roundtrip_binary_data(self):
        """Roundtrip preserves arbitrary binary bytes."""
        data = bytes(range(256))
        assert decompress_html(compress_html(data)) == data


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------

class TestContentHash:
    """Test SHA-256 content hashing."""

    def test_returns_hex_string(self):
        """content_hash returns a hex string."""
        result = content_hash(b"some bytes")
        assert isinstance(result, str)
        assert all(c in "0123456789abcdef" for c in result)

    def test_length_is_64(self):
        """SHA-256 hex digest is always 64 characters."""
        assert len(content_hash(b"test")) == 64
        assert len(content_hash(b"")) == 64

    def test_consistent(self):
        """Same input always gives same digest."""
        data = b"hello world"
        assert content_hash(data) == content_hash(data)

    def test_different_inputs_differ(self):
        """Different inputs produce different digests."""
        assert content_hash(b"aaa") != content_hash(b"bbb")

    def test_matches_hashlib(self):
        """content_hash matches hashlib.sha256 reference."""
        data = b"reference data"
        assert content_hash(data) == hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# html_to_markdown
# ---------------------------------------------------------------------------

class TestHtmlToMarkdown:
    """Test HTML-to-Markdown conversion."""

    def test_extracts_title_text(self):
        """Content in heading tags is preserved."""
        html = b"<html><body><h1>My Title</h1><p>Body text.</p></body></html>"
        result = html_to_markdown(html)
        assert "My Title" in result

    def test_extracts_paragraph_text(self):
        """Paragraph text appears in output."""
        html = b"<html><body><p>Hello paragraph</p></body></html>"
        result = html_to_markdown(html)
        assert "Hello paragraph" in result

    def test_strips_script_tags(self):
        """<script> content is removed."""
        html = b"<html><body><script>alert('evil')</script><p>Safe</p></body></html>"
        result = html_to_markdown(html)
        assert "alert" not in result
        assert "Safe" in result

    def test_strips_nav_tags(self):
        """<nav> content is removed; main content is preserved."""
        html = (
            b"<html><body><nav><a href='/'>Home</a></nav>"
            b"<main><p>Main content</p></main></body></html>"
        )
        result = html_to_markdown(html)
        assert "Main content" in result
        # The nav link text should not bleed into the output
        assert "Home" not in result

    def test_empty_input_returns_empty(self):
        """Empty bytes returns empty string."""
        result = html_to_markdown(b"")
        assert result == ""

    def test_returns_string(self):
        """Return type is always str."""
        assert isinstance(html_to_markdown(b"<html></html>"), str)
        assert isinstance(html_to_markdown(b""), str)

    def test_prefers_main_container(self):
        """Prefers <main> over <body> when both present."""
        html = (
            b"<html><body>"
            b"<div>sidebar noise</div>"
            b"<main><p>primary content</p></main>"
            b"</body></html>"
        )
        result = html_to_markdown(html)
        assert "primary content" in result

    def test_falls_back_to_body(self):
        """Falls back to <body> when no main/article/div.content present."""
        html = b"<html><body><p>body text</p></body></html>"
        result = html_to_markdown(html)
        assert "body text" in result


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    """Test markdown-to-plain-text stripping."""

    def test_strips_heading_markers(self):
        """## headings become plain text."""
        md = "## Section Header\n\nSome text."
        result = extract_text(md)
        assert "Section Header" in result
        assert "##" not in result

    def test_strips_bold_markers(self):
        """**bold** markers are removed."""
        md = "This is **bold** text."
        result = extract_text(md)
        assert "bold" in result
        assert "**" not in result

    def test_strips_italic_markers(self):
        """*italic* markers are removed."""
        md = "This is *italic* text."
        result = extract_text(md)
        assert "italic" in result
        assert "*" not in result

    def test_strips_inline_code_backticks(self):
        """`code` backticks are removed."""
        md = "Use `print()` to output."
        result = extract_text(md)
        assert "print()" in result
        assert "`" not in result

    def test_strips_link_syntax(self):
        """[text](url) becomes just text."""
        md = "Visit [Google](https://google.com) for search."
        result = extract_text(md)
        assert "Google" in result
        assert "https://google.com" not in result
        assert "[" not in result

    def test_empty_input_returns_empty(self):
        """Empty string returns empty string."""
        assert extract_text("") == ""

    def test_returns_string(self):
        """Return type is always str."""
        assert isinstance(extract_text("some markdown"), str)

    def test_collapses_blank_lines(self):
        """Multiple consecutive blank lines become single blank line."""
        md = "Line one\n\n\n\n\nLine two"
        result = extract_text(md)
        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in result


# ---------------------------------------------------------------------------
# extract_pdf_text
# ---------------------------------------------------------------------------

class TestExtractPdfText:
    """Test PDF text extraction (optional dependency)."""

    def test_invalid_pdf_returns_error_string(self):
        """Non-PDF bytes return an error string rather than raising."""
        result = extract_pdf_text(b"not a pdf")
        assert isinstance(result, str)

    def test_returns_string(self):
        """Return type is always str."""
        assert isinstance(extract_pdf_text(b""), str)


# ---------------------------------------------------------------------------
# ContentFetcher
# ---------------------------------------------------------------------------

class TestContentFetcherInit:
    """Test ContentFetcher construction."""

    def test_default_timeout_is_10(self):
        """Default timeout is 10 seconds."""
        fetcher = ContentFetcher()
        assert fetcher.timeout == 10

    def test_custom_timeout(self):
        """Custom timeout is respected."""
        fetcher = ContentFetcher(timeout=30)
        assert fetcher.timeout == 30

    def test_session_is_requests_session(self):
        """A requests.Session is created on init."""
        fetcher = ContentFetcher()
        assert isinstance(fetcher.session, requests.Session)

    def test_default_user_agent_set_on_session(self):
        """Default User-Agent header is present on the session."""
        fetcher = ContentFetcher()
        ua = fetcher.session.headers.get("User-Agent", "")
        assert ua  # non-empty

    def test_custom_user_agent_passed_through(self):
        """Custom user_agent is set on the session."""
        fetcher = ContentFetcher(user_agent="TestBot/2.0")
        assert fetcher.session.headers["User-Agent"] == "TestBot/2.0"


class TestContentFetcherFetch:
    """Test ContentFetcher.fetch() method (network mocked)."""

    @pytest.fixture
    def fetcher(self):
        return ContentFetcher(timeout=5)

    def _mock_response(self, status=200, body=b"", content_type="text/html", encoding="utf-8"):
        resp = MagicMock()
        resp.status_code = status
        resp.content = body
        resp.headers = {"Content-Type": content_type}
        resp.encoding = encoding
        return resp

    def test_success_200(self, fetcher):
        """200 response gives success=True and html_content."""
        body = b"<html><head><title>Page Title</title></head><body>content</body></html>"
        resp = self._mock_response(200, body)
        with patch.object(fetcher.session, "get", return_value=resp):
            result = fetcher.fetch("https://example.com")
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["html_content"] == body
        assert result["title"] == "Page Title"
        assert result["error"] is None

    def test_non_200_gives_failure(self, fetcher):
        """Non-200 status gives success=False."""
        resp = self._mock_response(404)
        with patch.object(fetcher.session, "get", return_value=resp):
            result = fetcher.fetch("https://example.com/missing")
        assert result["success"] is False
        assert result["status_code"] == 404

    def test_timeout_error(self, fetcher):
        """requests.Timeout gives success=False with descriptive error."""
        with patch.object(fetcher.session, "get", side_effect=requests.Timeout()):
            result = fetcher.fetch("https://slow.example.com")
        assert result["success"] is False
        assert result["error"] is not None

    def test_connection_error(self, fetcher):
        """requests.ConnectionError gives success=False."""
        with patch.object(fetcher.session, "get", side_effect=requests.ConnectionError()):
            result = fetcher.fetch("https://unreachable.example.com")
        assert result["success"] is False
        assert result["error"] is not None

    def test_response_time_ms_present(self, fetcher):
        """Result includes response_time_ms as a float."""
        resp = self._mock_response(200, b"<html></html>")
        with patch.object(fetcher.session, "get", return_value=resp):
            result = fetcher.fetch("https://example.com")
        assert "response_time_ms" in result
        assert isinstance(result["response_time_ms"], float)

    def test_content_type_extracted(self, fetcher):
        """content_type field mirrors the Content-Type header."""
        resp = self._mock_response(200, b"<html></html>", content_type="text/html; charset=utf-8")
        with patch.object(fetcher.session, "get", return_value=resp):
            result = fetcher.fetch("https://example.com")
        assert result["content_type"] == "text/html; charset=utf-8"


class TestContentFetcherFetchAndProcess:
    """Test ContentFetcher.fetch_and_process() (network mocked)."""

    @pytest.fixture
    def fetcher(self):
        return ContentFetcher(timeout=5)

    def test_success_returns_processed_dict(self, fetcher):
        """Successful fetch_and_process populates all expected fields."""
        body = (
            b"<html><head><title>Processed</title></head>"
            b"<body><main><p>Content here</p></main></body></html>"
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.content = body
        resp.headers = {"Content-Type": "text/html"}
        resp.encoding = "utf-8"

        with patch.object(fetcher.session, "get", return_value=resp):
            result = fetcher.fetch_and_process("https://example.com")

        assert result["success"] is True
        assert result["html_content"] is not None   # compressed bytes
        assert result["markdown_content"] is not None
        assert result["content_hash"] is not None
        assert result["content_length"] > 0
        assert result["compressed_size"] > 0
        assert result["error"] is None

    def test_html_content_is_compressed(self, fetcher):
        """html_content in result is zlib-compressed original HTML."""
        body = b"<html><body><p>hello</p></body></html>"
        resp = MagicMock()
        resp.status_code = 200
        resp.content = body
        resp.headers = {"Content-Type": "text/html"}
        resp.encoding = "utf-8"

        with patch.object(fetcher.session, "get", return_value=resp):
            result = fetcher.fetch_and_process("https://example.com")

        assert zlib.decompress(result["html_content"]) == body

    def test_failure_propagates_error(self, fetcher):
        """Failed fetch gives success=False and no html_content."""
        with patch.object(fetcher.session, "get", side_effect=requests.ConnectionError()):
            result = fetcher.fetch_and_process("https://unreachable.example.com")
        assert result["success"] is False
        assert result["html_content"] is None
        assert result["error"] is not None


# ---------------------------------------------------------------------------
# Re-exports from content/__init__.py
# ---------------------------------------------------------------------------

class TestReExports:
    """Verify that content/__init__.py re-exports all public symbols."""

    def test_content_fetcher_class(self):
        assert ContentFetcherFromInit is ContentFetcher

    def test_compress_html(self):
        assert compress_from_init is compress_html

    def test_decompress_html(self):
        assert decompress_from_init is decompress_html

    def test_content_hash(self):
        assert hash_from_init is content_hash

    def test_html_to_markdown(self):
        assert md_from_init is html_to_markdown

    def test_extract_text(self):
        assert extract_from_init is extract_text

    def test_extract_pdf_text(self):
        assert pdf_from_init is extract_pdf_text
