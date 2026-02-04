"""
Tests for btk/media_detector.py

Tests URL pattern matching for various media platforms.
"""
import pytest

from btk.media_detector import (
    MediaDetector, MediaInfo, detect_media,
    MEDIA_TYPE_VIDEO, MEDIA_TYPE_AUDIO, MEDIA_TYPE_DOCUMENT, MEDIA_TYPE_CODE,
    URL_TYPE_VIDEO, URL_TYPE_PLAYLIST, URL_TYPE_CHANNEL, URL_TYPE_TRACK,
    URL_TYPE_ALBUM, URL_TYPE_PAPER, URL_TYPE_REPO
)


class TestMediaDetector:
    """Test MediaDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a MediaDetector instance."""
        return MediaDetector()

    # ===== YouTube Tests =====

    def test_detect_youtube_watch_url(self, detector):
        """Test YouTube watch URL detection."""
        info = detector.detect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "dQw4w9WgXcQ"
        assert info.media_type == MEDIA_TYPE_VIDEO
        assert info.url_type == URL_TYPE_VIDEO

    def test_detect_youtube_short_url(self, detector):
        """Test YouTube short URL (youtu.be) detection."""
        info = detector.detect("https://youtu.be/dQw4w9WgXcQ")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "dQw4w9WgXcQ"
        assert info.media_type == MEDIA_TYPE_VIDEO

    def test_detect_youtube_embed_url(self, detector):
        """Test YouTube embed URL detection."""
        info = detector.detect("https://www.youtube.com/embed/dQw4w9WgXcQ")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "dQw4w9WgXcQ"

    def test_detect_youtube_shorts_url(self, detector):
        """Test YouTube Shorts URL detection."""
        info = detector.detect("https://www.youtube.com/shorts/abc123-xyz")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "abc123-xyz"
        assert info.url_type == URL_TYPE_VIDEO

    def test_detect_youtube_playlist_url(self, detector):
        """Test YouTube playlist URL detection."""
        info = detector.detect("https://www.youtube.com/playlist?list=PLxyz123abc")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "PLxyz123abc"
        assert info.url_type == URL_TYPE_PLAYLIST

    def test_detect_youtube_channel_url(self, detector):
        """Test YouTube channel URL detection."""
        info = detector.detect("https://www.youtube.com/channel/UCxyz123")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "UCxyz123"
        assert info.url_type == URL_TYPE_CHANNEL

    def test_detect_youtube_handle_url(self, detector):
        """Test YouTube @ handle URL detection."""
        info = detector.detect("https://www.youtube.com/@username")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "username"
        assert info.url_type == URL_TYPE_CHANNEL

    def test_detect_youtube_with_extra_params(self, detector):
        """Test YouTube URL with additional query parameters."""
        info = detector.detect("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLtest")
        assert info is not None
        assert info.source == "youtube"
        assert info.media_id == "dQw4w9WgXcQ"

    # ===== Vimeo Tests =====

    def test_detect_vimeo_url(self, detector):
        """Test Vimeo video URL detection."""
        info = detector.detect("https://vimeo.com/123456789")
        assert info is not None
        assert info.source == "vimeo"
        assert info.media_id == "123456789"
        assert info.media_type == MEDIA_TYPE_VIDEO

    def test_detect_vimeo_player_url(self, detector):
        """Test Vimeo player embed URL detection."""
        info = detector.detect("https://player.vimeo.com/video/123456789")
        assert info is not None
        assert info.source == "vimeo"
        assert info.media_id == "123456789"

    # ===== Spotify Tests =====

    def test_detect_spotify_track(self, detector):
        """Test Spotify track URL detection."""
        info = detector.detect("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
        assert info is not None
        assert info.source == "spotify"
        assert info.media_id == "4cOdK2wGLETKBW3PvgPWqT"
        assert info.media_type == MEDIA_TYPE_AUDIO
        assert info.url_type == URL_TYPE_TRACK

    def test_detect_spotify_album(self, detector):
        """Test Spotify album URL detection."""
        info = detector.detect("https://open.spotify.com/album/6QaVfG1pHYl1z15ZxkvVDW")
        assert info is not None
        assert info.source == "spotify"
        assert info.url_type == URL_TYPE_ALBUM

    def test_detect_spotify_playlist(self, detector):
        """Test Spotify playlist URL detection."""
        info = detector.detect("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
        assert info is not None
        assert info.source == "spotify"
        assert info.url_type == URL_TYPE_PLAYLIST

    # ===== SoundCloud Tests =====

    def test_detect_soundcloud_track(self, detector):
        """Test SoundCloud track URL detection."""
        info = detector.detect("https://soundcloud.com/artist-name/track-name")
        assert info is not None
        assert info.source == "soundcloud"
        assert info.media_type == MEDIA_TYPE_AUDIO

    # ===== arXiv Tests =====

    def test_detect_arxiv_abs(self, detector):
        """Test arXiv abstract URL detection."""
        info = detector.detect("https://arxiv.org/abs/2301.07041")
        assert info is not None
        assert info.source == "arxiv"
        assert info.media_id == "2301.07041"
        assert info.media_type == MEDIA_TYPE_DOCUMENT
        assert info.url_type == URL_TYPE_PAPER

    def test_detect_arxiv_pdf(self, detector):
        """Test arXiv PDF URL detection."""
        info = detector.detect("https://arxiv.org/pdf/2301.07041")
        assert info is not None
        assert info.source == "arxiv"
        assert info.media_id == "2301.07041"

    # ===== GitHub Tests =====

    def test_detect_github_repo(self, detector):
        """Test GitHub repository URL detection."""
        info = detector.detect("https://github.com/username/repository")
        assert info is not None
        assert info.source == "github"
        assert info.media_id == "username/repository"
        assert info.media_type == MEDIA_TYPE_CODE
        assert info.url_type == URL_TYPE_REPO

    def test_detect_github_repo_with_path(self, detector):
        """Test GitHub repository URL with subpath."""
        info = detector.detect("https://github.com/user-name/repo-name/tree/main/src")
        assert info is not None
        assert info.source == "github"
        assert info.media_id == "user-name/repo-name"

    def test_detect_github_gist(self, detector):
        """Test GitHub Gist URL detection."""
        info = detector.detect("https://gist.github.com/username/abc123def456")
        assert info is not None
        assert info.source == "github"

    # ===== Twitter/X Tests =====

    def test_detect_twitter_status(self, detector):
        """Test Twitter status URL detection."""
        info = detector.detect("https://twitter.com/username/status/1234567890123456789")
        assert info is not None
        assert info.source == "twitter"
        assert info.media_id == "username"

    def test_detect_x_status(self, detector):
        """Test X (formerly Twitter) status URL detection."""
        info = detector.detect("https://x.com/username/status/1234567890123456789")
        assert info is not None
        assert info.source == "twitter"

    # ===== Reddit Tests =====

    def test_detect_reddit_post(self, detector):
        """Test Reddit post URL detection."""
        info = detector.detect("https://www.reddit.com/r/programming/comments/abc123/title_here")
        assert info is not None
        assert info.source == "reddit"
        assert info.media_id == "abc123"
        assert info.media_type == MEDIA_TYPE_DOCUMENT

    def test_detect_reddit_short_url(self, detector):
        """Test Reddit short URL detection."""
        info = detector.detect("https://redd.it/abc123")
        assert info is not None
        assert info.source == "reddit"
        assert info.media_id == "abc123"

    # ===== PDF Tests =====

    def test_detect_pdf_url(self, detector):
        """Test direct PDF URL detection."""
        info = detector.detect("https://example.com/document.pdf")
        assert info is not None
        assert info.source == "pdf"
        assert info.media_type == MEDIA_TYPE_DOCUMENT
        assert info.media_id == "document.pdf"

    def test_detect_pdf_with_query_string(self, detector):
        """Test PDF URL with query string."""
        info = detector.detect("https://example.com/files/report.pdf?version=2")
        assert info is not None
        assert info.source == "pdf"

    # ===== Non-Media URL Tests =====

    def test_detect_non_media_url(self, detector):
        """Test that non-media URLs return None."""
        info = detector.detect("https://example.com/page")
        assert info is None

    def test_detect_empty_url(self, detector):
        """Test empty URL handling."""
        info = detector.detect("")
        assert info is None

    def test_detect_none_url(self, detector):
        """Test None URL handling."""
        info = detector.detect(None)
        assert info is None

    # ===== Batch Detection Tests =====

    def test_detect_batch(self, detector):
        """Test batch URL detection."""
        urls = [
            "https://youtube.com/watch?v=abc123",
            "https://example.com/page",
            "https://arxiv.org/abs/2301.07041"
        ]
        results = detector.detect_batch(urls)

        assert len(results) == 3
        assert results[urls[0]] is not None
        assert results[urls[0]].source == "youtube"
        assert results[urls[1]] is None  # Non-media
        assert results[urls[2]] is not None
        assert results[urls[2]].source == "arxiv"

    # ===== Helper Method Tests =====

    def test_is_media_url(self, detector):
        """Test is_media_url helper."""
        assert detector.is_media_url("https://youtube.com/watch?v=abc") is True
        assert detector.is_media_url("https://example.com") is False

    def test_get_media_type(self, detector):
        """Test get_media_type helper."""
        assert detector.get_media_type("https://youtube.com/watch?v=abc") == MEDIA_TYPE_VIDEO
        assert detector.get_media_type("https://open.spotify.com/track/abc") == MEDIA_TYPE_AUDIO
        assert detector.get_media_type("https://example.com") is None

    def test_get_source(self, detector):
        """Test get_source helper."""
        assert detector.get_source("https://youtube.com/watch?v=abc") == "youtube"
        assert detector.get_source("https://vimeo.com/123") == "vimeo"
        assert detector.get_source("https://example.com") is None

    # ===== Class Method Tests =====

    def test_get_supported_sources(self):
        """Test getting list of supported sources."""
        sources = MediaDetector.get_supported_sources()
        assert "youtube" in sources
        assert "spotify" in sources
        assert "arxiv" in sources
        assert "github" in sources

    def test_get_patterns_for_source(self):
        """Test getting patterns for a specific source."""
        patterns = MediaDetector.get_patterns_for_source("youtube")
        assert len(patterns) > 0
        assert any("watch" in p for p in patterns)

    def test_get_patterns_for_unknown_source(self):
        """Test getting patterns for unknown source."""
        patterns = MediaDetector.get_patterns_for_source("unknown_source")
        assert patterns == []


class TestConvenienceFunction:
    """Test the detect_media convenience function."""

    def test_detect_media_convenience(self):
        """Test detect_media function."""
        info = detect_media("https://youtube.com/watch?v=abc123")
        assert info is not None
        assert info.source == "youtube"

    def test_detect_media_non_media(self):
        """Test detect_media with non-media URL."""
        info = detect_media("https://example.com")
        assert info is None


class TestCaseInsensitivity:
    """Test case-insensitive matching."""

    @pytest.fixture
    def detector(self):
        return MediaDetector()

    def test_youtube_mixed_case(self, detector):
        """Test YouTube URL with mixed case."""
        info = detector.detect("https://WWW.YouTube.COM/watch?v=abc123")
        assert info is not None
        assert info.source == "youtube"

    def test_vimeo_uppercase(self, detector):
        """Test Vimeo URL with uppercase."""
        info = detector.detect("https://VIMEO.COM/123456")
        assert info is not None
        assert info.source == "vimeo"
