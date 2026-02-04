"""
Tests for the BTK media preservation system (Long Echo).
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, PropertyMock
from datetime import datetime, timezone
import io

from btk.preservation import (
    YouTubePreserver,
    PDFPreserver,
    ImagePreserver,
    WebsiteScreenshotPreserver,
    PreservationManager,
    store_preservation_result,
    get_preservation_status,
    get_preserved_thumbnail,
    get_preserved_transcript,
    get_preserved_text,
    preserve_bookmark,
    preserve_bookmarks_batch,
)
from btk.plugins import PreservationResult, PluginMetadata


class TestYouTubePreserver:
    """Tests for YouTubePreserver."""

    @pytest.fixture
    def preserver(self):
        """Create a YouTubePreserver instance."""
        return YouTubePreserver()

    def test_metadata(self, preserver):
        """Test preserver metadata."""
        meta = preserver.metadata
        assert meta.name == "youtube_preserver"
        assert meta.version == "1.0.0"
        assert "youtube-transcript-api" in meta.dependencies

    def test_supported_domains(self, preserver):
        """Test supported domains list."""
        domains = preserver.supported_domains
        assert 'youtube.com' in domains
        assert 'youtu.be' in domains
        assert 'www.youtube.com' in domains

    def test_can_preserve_youtube_video(self, preserver):
        """Test URL detection for YouTube videos."""
        # Valid YouTube URLs
        assert preserver.can_preserve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert preserver.can_preserve("https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert preserver.can_preserve("https://youtu.be/dQw4w9WgXcQ")
        assert preserver.can_preserve("https://m.youtube.com/watch?v=dQw4w9WgXcQ")
        assert preserver.can_preserve("https://www.youtube.com/embed/dQw4w9WgXcQ")

    def test_can_preserve_non_youtube(self, preserver):
        """Test URL detection rejects non-YouTube URLs."""
        assert not preserver.can_preserve("https://vimeo.com/123456789")
        assert not preserver.can_preserve("https://example.com/video.mp4")
        assert not preserver.can_preserve("https://www.youtube.com/channel/UCtest")

    def test_extract_video_id(self, preserver):
        """Test video ID extraction from various URL formats."""
        assert preserver._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert preserver._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert preserver._extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert preserver._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s") == "dQw4w9WgXcQ"

    def test_extract_video_id_invalid(self, preserver):
        """Test video ID extraction fails gracefully for invalid URLs."""
        assert preserver._extract_video_id("https://www.youtube.com/channel/UCtest") is None
        assert preserver._extract_video_id("https://example.com") is None

    @patch('btk.preservation.requests.get')
    def test_fetch_thumbnail_success(self, mock_get, preserver):
        """Test successful thumbnail fetching."""
        # Mock successful response - needs to be > 1000 bytes
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'x' * 1500  # > 1000 bytes threshold
        mock_get.return_value = mock_response

        data, mime = preserver._fetch_thumbnail("dQw4w9WgXcQ")
        assert len(data) > 1000
        assert mime == 'image/jpeg'

    @patch('btk.preservation.requests.get')
    def test_fetch_thumbnail_fallback(self, mock_get, preserver):
        """Test thumbnail fallback to lower quality."""
        # First call fails, second succeeds
        failed_response = Mock()
        failed_response.status_code = 404

        success_response = Mock()
        success_response.status_code = 200
        success_response.content = b'x' * 1500  # > 1000 bytes threshold

        mock_get.side_effect = [failed_response, success_response]

        data, mime = preserver._fetch_thumbnail("dQw4w9WgXcQ")
        assert len(data) > 1000

    def test_preserve_invalid_url(self, preserver):
        """Test preserve with invalid URL returns failure."""
        # Create a preserver instance with fetch disabled to avoid network calls
        preserver_no_fetch = YouTubePreserver(fetch_thumbnail=False, fetch_transcript=False)
        # Use a YouTube URL without a valid video ID
        result = preserver_no_fetch.preserve("https://www.youtube.com/channel/UCtest")
        assert not result.success
        assert "Could not extract video ID" in result.error_message

    @patch.object(YouTubePreserver, '_fetch_thumbnail')
    @patch.object(YouTubePreserver, '_fetch_transcript')
    def test_preserve_success(self, mock_transcript, mock_thumbnail, preserver):
        """Test successful preservation."""
        mock_thumbnail.return_value = (b'thumbnail_data', 'image/jpeg')
        mock_transcript.return_value = "This is the transcript text."

        result = preserver.preserve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert result.success
        assert result.preservation_type == 'youtube'
        assert result.thumbnail_data == b'thumbnail_data'
        assert result.thumbnail_mime == 'image/jpeg'
        assert result.transcript_text == "This is the transcript text."
        assert result.word_count == 5

    @patch.object(YouTubePreserver, '_fetch_thumbnail')
    @patch.object(YouTubePreserver, '_fetch_transcript')
    def test_preserve_thumbnail_only(self, mock_transcript, mock_thumbnail, preserver):
        """Test preservation with transcript failure."""
        mock_thumbnail.return_value = (b'thumbnail_data', 'image/jpeg')
        mock_transcript.side_effect = Exception("No transcript")

        result = preserver.preserve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert result.success
        assert result.thumbnail_data == b'thumbnail_data'
        assert result.transcript_text is None


class TestPDFPreserver:
    """Tests for PDFPreserver."""

    @pytest.fixture
    def preserver(self):
        """Create a PDFPreserver instance."""
        return PDFPreserver()

    def test_metadata(self, preserver):
        """Test preserver metadata."""
        meta = preserver.metadata
        assert meta.name == "pdf_preserver"
        assert "pypdf" in meta.dependencies

    def test_can_preserve_pdf_urls(self, preserver):
        """Test PDF URL detection."""
        assert preserver.can_preserve("https://arxiv.org/pdf/2301.00001.pdf")
        assert preserver.can_preserve("https://example.com/document.PDF")
        assert preserver.can_preserve("https://example.com/file?format=pdf")

    def test_can_preserve_non_pdf(self, preserver):
        """Test non-PDF URL rejection."""
        assert not preserver.can_preserve("https://example.com/page.html")
        assert not preserver.can_preserve("https://example.com/image.jpg")

    @patch('btk.preservation.requests.get')
    def test_preserve_large_pdf_rejected(self, mock_get, preserver):
        """Test large PDFs are rejected."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-length': str(100 * 1024 * 1024)}  # 100 MB
        mock_get.return_value = mock_response

        result = preserver.preserve("https://example.com/huge.pdf")
        assert not result.success
        assert "too large" in result.error_message


class TestImagePreserver:
    """Tests for ImagePreserver."""

    @pytest.fixture
    def preserver(self):
        """Create an ImagePreserver instance."""
        return ImagePreserver()

    def test_metadata(self, preserver):
        """Test preserver metadata."""
        meta = preserver.metadata
        assert meta.name == "image_preserver"

    def test_can_preserve_image_urls(self, preserver):
        """Test image URL detection."""
        assert preserver.can_preserve("https://example.com/photo.jpg")
        assert preserver.can_preserve("https://example.com/image.PNG")
        assert preserver.can_preserve("https://example.com/graphic.gif")
        assert preserver.can_preserve("https://example.com/image.webp")

    def test_can_preserve_non_image(self, preserver):
        """Test non-image URL rejection."""
        assert not preserver.can_preserve("https://example.com/page.html")
        assert not preserver.can_preserve("https://example.com/doc.pdf")

    @patch('btk.preservation.requests.get')
    def test_preserve_image_success(self, mock_get, preserver):
        """Test successful image preservation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_response.headers = {'content-type': 'image/jpeg'}
        mock_get.return_value = mock_response

        result = preserver.preserve("https://example.com/photo.jpg")

        assert result.success
        assert result.preservation_type == 'image'
        assert result.thumbnail_data == b'fake_image_data'
        assert result.thumbnail_mime == 'image/jpeg'


class TestWebsiteScreenshotPreserver:
    """Tests for WebsiteScreenshotPreserver."""

    @pytest.fixture
    def preserver(self):
        """Create a WebsiteScreenshotPreserver instance."""
        return WebsiteScreenshotPreserver()

    def test_metadata(self, preserver):
        """Test preserver metadata."""
        meta = preserver.metadata
        assert meta.name == "website_screenshot"
        assert meta.priority == 30  # Lower priority
        assert "playwright" in meta.dependencies

    def test_can_preserve_any_http_url(self, preserver):
        """Test any HTTP(S) URL can be preserved."""
        assert preserver.can_preserve("https://example.com")
        assert preserver.can_preserve("http://localhost:8080/page")
        assert preserver.can_preserve("https://github.com/user/repo")

    def test_can_preserve_non_http(self, preserver):
        """Test non-HTTP URLs are rejected."""
        assert not preserver.can_preserve("ftp://example.com/file")
        assert not preserver.can_preserve("file:///path/to/file")

    def test_preserve_without_playwright(self, preserver):
        """Test graceful failure when playwright not installed."""
        # This will fail because playwright is likely not installed in test env
        result = preserver.preserve("https://example.com")
        # Should fail gracefully
        assert not result.success or result.preservation_type == 'screenshot'


class TestPreservationManager:
    """Tests for PreservationManager."""

    @pytest.fixture
    def manager(self):
        """Create a PreservationManager instance."""
        return PreservationManager()

    def test_default_preservers(self, manager):
        """Test default preservers are registered."""
        preservers = manager.list_preservers()
        names = [p['name'] for p in preservers]

        assert 'youtube_preserver' in names
        assert 'pdf_preserver' in names
        assert 'image_preserver' in names

    def test_preserver_priority_order(self, manager):
        """Test preservers are ordered by priority."""
        preservers = manager.list_preservers()
        priorities = [p['priority'] for p in preservers]

        assert priorities == sorted(priorities, reverse=True)

    def test_can_preserve(self, manager):
        """Test can_preserve checks all preservers."""
        assert manager.can_preserve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert manager.can_preserve("https://example.com/file.pdf")
        assert manager.can_preserve("https://example.com/image.jpg")

    def test_get_preserver_for_url(self, manager):
        """Test correct preserver is selected for URL."""
        yt_preserver = manager.get_preserver_for_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert yt_preserver.metadata.name == "youtube_preserver"

        pdf_preserver = manager.get_preserver_for_url("https://example.com/doc.pdf")
        assert pdf_preserver.metadata.name == "pdf_preserver"

    def test_register_custom_preserver(self, manager):
        """Test registering a custom preserver."""
        from btk.plugins import MediaPreserver

        class CustomPreserver(MediaPreserver):
            @property
            def metadata(self):
                return PluginMetadata(name="custom", version="1.0.0", priority=100)

            @property
            def supported_domains(self):
                return ['custom.example.com']

            def can_preserve(self, url):
                return 'custom.example.com' in url

            def preserve(self, url, **kwargs):
                return PreservationResult(success=True, url=url, preservation_type='custom')

        custom = CustomPreserver()
        manager.register_preserver(custom)

        preserver = manager.get_preserver_for_url("https://custom.example.com/page")
        assert preserver.metadata.name == "custom"


class TestPreservationResult:
    """Tests for PreservationResult dataclass."""

    def test_success_result(self):
        """Test creating a success result."""
        result = PreservationResult(
            success=True,
            url="https://example.com",
            preservation_type="test",
            thumbnail_data=b'data',
            transcript_text="text"
        )

        assert result.success
        assert result.url == "https://example.com"
        assert result.thumbnail_data == b'data'
        assert result.transcript_text == "text"
        assert result.error_message is None

    def test_failure_result(self):
        """Test creating a failure result."""
        result = PreservationResult(
            success=False,
            url="https://example.com",
            preservation_type="test",
            error_message="Something went wrong"
        )

        assert not result.success
        assert result.error_message == "Something went wrong"

    def test_extra_metadata(self):
        """Test extra metadata storage."""
        result = PreservationResult(
            success=True,
            url="https://example.com",
            preservation_type="test",
            extra={'video_id': 'abc123', 'duration': 120}
        )

        assert result.extra['video_id'] == 'abc123'
        assert result.extra['duration'] == 120


class TestDatabaseStorage:
    """Tests for database storage functions."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        mock = MagicMock()
        mock_session = MagicMock()
        mock.session.return_value.__enter__ = Mock(return_value=mock_session)
        mock.session.return_value.__exit__ = Mock(return_value=False)
        return mock

    def test_store_preservation_result(self, mock_db):
        """Test storing preservation result."""
        from btk.models import ContentCache

        # Create a result
        result = PreservationResult(
            success=True,
            url="https://example.com",
            preservation_type="youtube",
            thumbnail_data=b'thumbnail',
            thumbnail_mime='image/jpeg',
            transcript_text="This is a transcript."
        )

        # Mock the session query
        mock_cache = MagicMock(spec=ContentCache)
        mock_cache.markdown_content = None
        mock_db.session.return_value.__enter__.return_value.query.return_value.filter_by.return_value.first.return_value = mock_cache

        success = store_preservation_result(mock_db, 1, result)

        # Verify fields were set
        assert mock_cache.thumbnail_data == b'thumbnail'
        assert mock_cache.thumbnail_mime == 'image/jpeg'
        assert mock_cache.transcript_text == "This is a transcript."
        assert mock_cache.preservation_type == 'youtube'

    def test_get_preservation_status(self, mock_db):
        """Test getting preservation status."""
        from btk.models import ContentCache

        # Mock cache with preservation data
        mock_cache = MagicMock(spec=ContentCache)
        mock_cache.preservation_type = 'youtube'
        mock_cache.preserved_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_cache.thumbnail_data = b'thumbnail'
        mock_cache.transcript_text = "hello world"
        mock_cache.extracted_text = None
        mock_cache.thumbnail_width = 1280
        mock_cache.thumbnail_height = 720

        mock_db.session.return_value.__enter__.return_value.query.return_value.filter_by.return_value.first.return_value = mock_cache

        status = get_preservation_status(mock_db, 1)

        assert status['preservation_type'] == 'youtube'
        assert status['has_thumbnail'] == True
        assert status['has_transcript'] == True
        assert status['transcript_words'] == 2
        assert status['thumbnail_dimensions'] == (1280, 720)

    def test_get_preserved_thumbnail(self, mock_db):
        """Test retrieving preserved thumbnail."""
        from btk.models import ContentCache

        mock_cache = MagicMock(spec=ContentCache)
        mock_cache.thumbnail_data = b'image_data'
        mock_cache.thumbnail_mime = 'image/png'

        mock_db.session.return_value.__enter__.return_value.query.return_value.filter_by.return_value.first.return_value = mock_cache

        result = get_preserved_thumbnail(mock_db, 1)

        assert result == (b'image_data', 'image/png')

    def test_get_preserved_transcript(self, mock_db):
        """Test retrieving preserved transcript."""
        from btk.models import ContentCache

        mock_cache = MagicMock(spec=ContentCache)
        mock_cache.transcript_text = "This is the transcript."

        mock_db.session.return_value.__enter__.return_value.query.return_value.filter_by.return_value.first.return_value = mock_cache

        result = get_preserved_transcript(mock_db, 1)

        assert result == "This is the transcript."


class TestPreservationHtmlExporter:
    """Tests for the preservation-html export format."""

    @pytest.fixture
    def sample_bookmarks(self):
        """Create sample bookmarks for testing."""
        from datetime import datetime, timezone

        # Simple mock without spec to avoid SQLAlchemy issues
        tag = Mock()
        tag.name = "test"

        bookmark = Mock()
        bookmark.id = 1
        bookmark.url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        bookmark.title = "Never Gonna Give You Up"
        bookmark.description = "Classic video"
        bookmark.tags = [tag]
        bookmark.stars = True
        bookmark.visit_count = 42
        bookmark.added = datetime(2024, 1, 1, tzinfo=timezone.utc)

        return [bookmark]

    def test_export_preservation_html_basic(self, sample_bookmarks, tmp_path):
        """Test basic preservation-html export."""
        from btk.exporters import export_preservation_html

        output_path = tmp_path / "archive.html"
        export_preservation_html(sample_bookmarks, output_path)

        assert output_path.exists()
        content = output_path.read_text()

        # Check structure
        assert "Bookmark Archive" in content
        assert "Never Gonna Give You Up" in content
        assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ" in content
        assert "Classic video" in content
        assert "test" in content  # tag

    def test_export_preservation_html_no_javascript_required(self, sample_bookmarks, tmp_path):
        """Test that preservation-html export works without JavaScript."""
        from btk.exporters import export_preservation_html

        output_path = tmp_path / "archive.html"
        export_preservation_html(sample_bookmarks, output_path)

        content = output_path.read_text()

        # Should have noscript notice
        assert "<noscript>" in content
        assert "works without JavaScript" in content

        # All content should be inline
        assert "</article>" in content  # Bookmark content is in HTML

    def test_export_preservation_html_self_contained(self, sample_bookmarks, tmp_path):
        """Test that preservation-html export is self-contained."""
        from btk.exporters import export_preservation_html

        output_path = tmp_path / "archive.html"
        export_preservation_html(sample_bookmarks, output_path)

        content = output_path.read_text()

        # Styles should be inline
        assert "<style>" in content
        # No external CSS
        assert 'href="http' not in content.lower() or 'stylesheet' not in content.lower()

    def test_export_file_preservation_html_format(self, sample_bookmarks, tmp_path):
        """Test export_file supports preservation-html format."""
        from btk.exporters import export_file

        output_path = tmp_path / "archive.html"
        export_file(sample_bookmarks, output_path, "preservation-html")

        assert output_path.exists()
        content = output_path.read_text()
        assert "Bookmark Archive" in content


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_escape_html(self):
        """Test HTML escaping."""
        from btk.exporters import _escape_html

        assert _escape_html("<script>alert('xss')</script>") == "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;"
        assert _escape_html("A & B") == "A &amp; B"
        assert _escape_html('"quoted"') == "&quot;quoted&quot;"
        assert _escape_html("") == ""
        assert _escape_html(None) == ""
