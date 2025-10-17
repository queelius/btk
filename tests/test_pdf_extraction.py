"""Tests for PDF text extraction in content fetching."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from btk.content_fetcher import ContentFetcher
import io


class TestPDFExtraction:
    """Test PDF text extraction functionality."""

    def test_extract_pdf_text_single_page(self):
        """Test extracting text from a single-page PDF."""
        # Create a mock PDF with one page
        mock_page = Mock()
        mock_page.extract_text.return_value = "This is a test PDF document."

        mock_reader = Mock()
        mock_reader.pages = [mock_page]

        with patch('pypdf.PdfReader', return_value=mock_reader):
            pdf_content = b"fake pdf bytes"
            result = ContentFetcher.extract_pdf_text(pdf_content)

            assert result == "This is a test PDF document."
            mock_page.extract_text.assert_called_once()

    def test_extract_pdf_text_multi_page(self):
        """Test extracting text from a multi-page PDF."""
        # Create mock PDF with multiple pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "First page content."

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Second page content."

        mock_page3 = Mock()
        mock_page3.extract_text.return_value = "Third page content."

        mock_reader = Mock()
        mock_reader.pages = [mock_page1, mock_page2, mock_page3]

        with patch('pypdf.PdfReader', return_value=mock_reader):
            pdf_content = b"fake pdf bytes"
            result = ContentFetcher.extract_pdf_text(pdf_content)

            expected = "First page content.\n\nSecond page content.\n\nThird page content."
            assert result == expected

    def test_extract_pdf_text_empty_pages(self):
        """Test extracting text from PDF with some empty pages."""
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "First page content."

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = ""  # Empty page

        mock_page3 = Mock()
        mock_page3.extract_text.return_value = None  # No text

        mock_page4 = Mock()
        mock_page4.extract_text.return_value = "Fourth page content."

        mock_reader = Mock()
        mock_reader.pages = [mock_page1, mock_page2, mock_page3, mock_page4]

        with patch('pypdf.PdfReader', return_value=mock_reader):
            pdf_content = b"fake pdf bytes"
            result = ContentFetcher.extract_pdf_text(pdf_content)

            # Should skip empty/None pages
            expected = "First page content.\n\nFourth page content."
            assert result == expected

    def test_fetch_and_process_pdf_by_content_type(self):
        """Test that fetch_and_process detects PDF by content-type."""
        fetcher = ContentFetcher()

        mock_fetch = {
            "success": True,
            "html_content": b"fake pdf content",
            "content_type": "application/pdf",
            "status_code": 200,
            "encoding": "utf-8",
            "response_time_ms": 100.0
        }

        with patch.object(fetcher, 'fetch', return_value=mock_fetch):
            with patch.object(fetcher, 'extract_pdf_text', return_value="Extracted PDF text") as mock_extract:
                with patch.object(fetcher, 'compress_html', return_value=b"compressed"):
                    result = fetcher.fetch_and_process("https://example.com/doc.pdf")

                    assert result["success"] is True
                    assert result["markdown_content"] == "Extracted PDF text"
                    mock_extract.assert_called_once_with(b"fake pdf content")

    def test_fetch_and_process_pdf_by_extension(self):
        """Test that fetch_and_process detects PDF by .pdf extension."""
        fetcher = ContentFetcher()

        mock_fetch = {
            "success": True,
            "html_content": b"fake pdf content",
            "content_type": "application/octet-stream",  # Not PDF content-type
            "status_code": 200,
            "encoding": "utf-8",
            "response_time_ms": 100.0
        }

        with patch.object(fetcher, 'fetch', return_value=mock_fetch):
            with patch.object(fetcher, 'extract_pdf_text', return_value="Extracted PDF text") as mock_extract:
                with patch.object(fetcher, 'compress_html', return_value=b"compressed"):
                    result = fetcher.fetch_and_process("https://example.com/document.pdf")

                    assert result["success"] is True
                    assert result["markdown_content"] == "Extracted PDF text"
                    mock_extract.assert_called_once_with(b"fake pdf content")

    def test_fetch_and_process_pdf_title_extraction(self):
        """Test that PDF title is extracted from first line if available."""
        fetcher = ContentFetcher()

        mock_fetch = {
            "success": True,
            "html_content": b"fake pdf content",
            "content_type": "application/pdf",
            "status_code": 200,
            "encoding": "utf-8",
            "response_time_ms": 100.0
        }

        pdf_text = "A Comprehensive Survey on Machine Learning\n\nThis is the abstract of the paper..."

        with patch.object(fetcher, 'fetch', return_value=mock_fetch):
            with patch.object(fetcher, 'extract_pdf_text', return_value=pdf_text):
                with patch.object(fetcher, 'compress_html', return_value=b"compressed"):
                    result = fetcher.fetch_and_process("https://example.com/paper.pdf")

                    assert result["success"] is True
                    assert result["title"] == "A Comprehensive Survey on Machine Learning"
                    assert result["markdown_content"] == pdf_text

    def test_fetch_and_process_html_not_pdf(self):
        """Test that HTML content is processed normally, not as PDF."""
        fetcher = ContentFetcher()

        mock_fetch = {
            "success": True,
            "html_content": b"<html><body>Test content</body></html>",
            "content_type": "text/html",
            "status_code": 200,
            "encoding": "utf-8",
            "response_time_ms": 100.0
        }

        with patch.object(fetcher, 'fetch', return_value=mock_fetch):
            with patch.object(fetcher, 'html_to_markdown', return_value="Test content") as mock_html:
                with patch.object(fetcher, 'compress_html', return_value=b"compressed"):
                    with patch.object(fetcher, 'extract_pdf_text') as mock_pdf:
                        result = fetcher.fetch_and_process("https://example.com/page.html")

                        assert result["success"] is True
                        mock_html.assert_called_once()
                        mock_pdf.assert_not_called()  # Should not call PDF extraction
