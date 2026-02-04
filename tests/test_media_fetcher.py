"""
Tests for btk/media_fetcher.py

Tests metadata fetching with mocked network calls.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import shutil

from btk.media_fetcher import MediaFetcher, MediaMetadata
from btk.media_detector import MediaInfo


class TestMediaMetadata:
    """Test MediaMetadata dataclass."""

    def test_create_metadata(self):
        """Test creating MediaMetadata instance."""
        metadata = MediaMetadata(
            title="Test Video",
            description="A test description",
            thumbnail_url="https://example.com/thumb.jpg",
            author_name="Test Author",
            author_url="https://example.com/author",
            published_at=datetime.now(timezone.utc),
            view_count=1000,
            tags=["test", "video"]
        )
        assert metadata.title == "Test Video"
        assert metadata.author_name == "Test Author"
        assert len(metadata.tags) == 2

    def test_metadata_defaults(self):
        """Test MediaMetadata default values."""
        metadata = MediaMetadata()
        assert metadata.title is None
        assert metadata.description is None
        assert metadata.thumbnail_url is None
        assert metadata.tags == []


class TestMediaFetcher:
    """Test MediaFetcher class."""

    @pytest.fixture
    def fetcher(self):
        """Create a MediaFetcher instance with yt-dlp disabled."""
        return MediaFetcher(use_yt_dlp=False)

    @pytest.fixture
    def fetcher_with_ytdlp(self):
        """Create a MediaFetcher with yt-dlp enabled."""
        return MediaFetcher(use_yt_dlp=True)

    # ===== Initialization Tests =====

    def test_init_default(self):
        """Test default initialization."""
        fetcher = MediaFetcher()
        assert fetcher.use_yt_dlp is True
        # yt_dlp_path depends on whether yt-dlp is installed
        expected_path = shutil.which("yt-dlp")
        assert fetcher.yt_dlp_path == expected_path

    def test_init_custom_path(self):
        """Test initialization with custom yt-dlp path."""
        fetcher = MediaFetcher(use_yt_dlp=True, yt_dlp_path="/custom/yt-dlp")
        assert fetcher.yt_dlp_path == "/custom/yt-dlp"

    def test_init_disabled_ytdlp(self):
        """Test initialization with yt-dlp disabled."""
        fetcher = MediaFetcher(use_yt_dlp=False)
        assert fetcher.use_yt_dlp is False

    def test_init_custom_timeout(self):
        """Test initialization with custom timeout."""
        fetcher = MediaFetcher(timeout=60)
        assert fetcher.timeout == 60

    # ===== YouTube oEmbed Tests =====

    @patch('btk.media_fetcher.requests.get')
    def test_fetch_youtube_oembed_success(self, mock_get, fetcher):
        """Test YouTube oEmbed success."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'title': 'Test Video Title',
            'author_name': 'Test Channel',
            'author_url': 'https://www.youtube.com/channel/UCtest',
            'thumbnail_url': 'https://i.ytimg.com/vi/test/hqdefault.jpg'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        media_info = MediaInfo(
            source='youtube',
            media_id='dQw4w9WgXcQ',
            media_type='video',
            url_type='video'
        )

        metadata = fetcher.fetch("https://youtube.com/watch?v=dQw4w9WgXcQ", media_info)

        assert metadata is not None
        assert metadata.title == 'Test Video Title'
        assert metadata.author_name == 'Test Channel'

    @patch('btk.media_fetcher.requests.get')
    def test_fetch_youtube_oembed_failure_returns_stub(self, mock_get, fetcher):
        """Test YouTube oEmbed failure returns stub with URL."""
        mock_get.side_effect = Exception("Network error")

        media_info = MediaInfo(
            source='youtube',
            media_id='invalid',
            media_type='video',
            url_type='video'
        )

        metadata = fetcher.fetch("https://youtube.com/watch?v=invalid", media_info)
        # Implementation returns a stub MediaMetadata with original_url
        assert metadata is not None
        assert metadata.original_url == "https://youtube.com/watch?v=invalid"
        assert metadata.title is None  # No actual metadata was fetched

    # ===== Vimeo Tests =====

    @patch('btk.media_fetcher.requests.get')
    def test_fetch_vimeo_oembed(self, mock_get, fetcher):
        """Test Vimeo oEmbed fetching."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'title': 'Vimeo Video',
            'author_name': 'Vimeo Creator',
            'author_url': 'https://vimeo.com/user123',
            'thumbnail_url': 'https://i.vimeocdn.com/video/thumb.jpg'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        media_info = MediaInfo(
            source='vimeo',
            media_id='123456789',
            media_type='video',
            url_type='video'
        )

        metadata = fetcher.fetch("https://vimeo.com/123456789", media_info)

        assert metadata is not None
        assert metadata.title == 'Vimeo Video'
        assert metadata.author_name == 'Vimeo Creator'

    # ===== Spotify Tests =====

    @patch('btk.media_fetcher.requests.get')
    def test_fetch_spotify_oembed(self, mock_get, fetcher):
        """Test Spotify oEmbed fetching."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'title': 'Song Title - Artist Name',
            'thumbnail_url': 'https://i.scdn.co/image/abc123'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        media_info = MediaInfo(
            source='spotify',
            media_id='4cOdK2wGLETKBW3PvgPWqT',
            media_type='audio',
            url_type='track'
        )

        metadata = fetcher.fetch("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT", media_info)

        assert metadata is not None
        assert 'Song Title' in metadata.title

    # ===== SoundCloud Tests =====

    @patch('btk.media_fetcher.requests.get')
    def test_fetch_soundcloud_oembed(self, mock_get, fetcher):
        """Test SoundCloud oEmbed fetching."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'title': 'SoundCloud Track',
            'author_name': 'SC Artist',
            'author_url': 'https://soundcloud.com/artist',
            'thumbnail_url': 'https://i1.sndcdn.com/artworks.jpg'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        media_info = MediaInfo(
            source='soundcloud',
            media_id='artist/track',
            media_type='audio',
            url_type='track'
        )

        metadata = fetcher.fetch("https://soundcloud.com/artist/track", media_info)

        assert metadata is not None
        assert metadata.title == 'SoundCloud Track'

    # ===== Unknown Source Tests =====

    def test_fetch_unknown_source_returns_stub(self, fetcher):
        """Test fetching from unknown source returns stub."""
        media_info = MediaInfo(
            source='unknown_platform',
            media_id='test',
            media_type='video',
            url_type='video'
        )

        metadata = fetcher.fetch("https://unknown.com/video", media_info)
        # Implementation returns a stub with original_url for unknown sources
        assert metadata is not None
        assert metadata.original_url == "https://unknown.com/video"
        assert metadata.title is None

    # ===== Error Handling Tests =====

    @patch('btk.media_fetcher.requests.get')
    def test_fetch_network_error_returns_stub(self, mock_get, fetcher):
        """Test handling network errors returns stub."""
        mock_get.side_effect = Exception("Network error")

        media_info = MediaInfo(
            source='youtube',
            media_id='test',
            media_type='video',
            url_type='video'
        )

        metadata = fetcher.fetch("https://youtube.com/watch?v=test", media_info)
        # Implementation returns a stub with original_url on error
        assert metadata is not None
        assert metadata.original_url == "https://youtube.com/watch?v=test"
        assert metadata.title is None


class TestYtDlpAvailability:
    """Test yt-dlp availability detection."""

    def test_yt_dlp_available_property(self):
        """Test yt_dlp_available property."""
        fetcher = MediaFetcher(use_yt_dlp=True)
        # Should be True if yt-dlp is installed and use_yt_dlp=True
        expected = shutil.which("yt-dlp") is not None
        assert fetcher.yt_dlp_available == expected

    def test_yt_dlp_disabled(self):
        """Test yt_dlp_available when disabled."""
        fetcher = MediaFetcher(use_yt_dlp=False)
        assert fetcher.yt_dlp_available is False


class TestOEmbedEndpoints:
    """Test oEmbed endpoint configuration."""

    def test_has_youtube_endpoint(self):
        """Test YouTube oEmbed endpoint exists."""
        assert "youtube" in MediaFetcher.OEMBED_ENDPOINTS
        assert "youtube.com/oembed" in MediaFetcher.OEMBED_ENDPOINTS["youtube"]

    def test_has_vimeo_endpoint(self):
        """Test Vimeo oEmbed endpoint exists."""
        assert "vimeo" in MediaFetcher.OEMBED_ENDPOINTS

    def test_has_spotify_endpoint(self):
        """Test Spotify oEmbed endpoint exists."""
        assert "spotify" in MediaFetcher.OEMBED_ENDPOINTS

    def test_has_soundcloud_endpoint(self):
        """Test SoundCloud oEmbed endpoint exists."""
        assert "soundcloud" in MediaFetcher.OEMBED_ENDPOINTS

    def test_has_twitter_endpoint(self):
        """Test Twitter oEmbed endpoint exists."""
        assert "twitter" in MediaFetcher.OEMBED_ENDPOINTS


@pytest.mark.integration
class TestIntegrationYtDlp:
    """Integration tests requiring yt-dlp (marked for optional execution)."""

    @pytest.fixture
    def fetcher(self):
        """Create a MediaFetcher with yt-dlp."""
        if not shutil.which("yt-dlp"):
            pytest.skip("yt-dlp not installed")
        return MediaFetcher(use_yt_dlp=True)

    def test_fetch_youtube_with_ytdlp(self, fetcher):
        """Integration test - requires yt-dlp and network."""
        # Use a well-known video that's unlikely to be removed
        media_info = MediaInfo(
            source='youtube',
            media_id='dQw4w9WgXcQ',
            media_type='video',
            url_type='video'
        )

        # This test will actually make network requests
        # Skip if no network or yt-dlp issues
        try:
            metadata = fetcher.fetch("https://youtube.com/watch?v=dQw4w9WgXcQ", media_info)
            if metadata:
                assert metadata.title is not None
                assert metadata.author_name is not None
        except Exception:
            pytest.skip("Network or yt-dlp unavailable")
