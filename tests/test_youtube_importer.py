"""
Tests for YouTube Importer.

These tests mock the YouTube API to avoid requiring actual API credentials.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from pathlib import Path

from btk.importers.base import ServiceConfig, ImportResult, ServiceImporter
from btk.importers.youtube import (
    YouTubeImporter,
    YouTubeConfig,
    HAS_YOUTUBE_API,
    DEFAULT_TOKEN_PATH,
    DEFAULT_CREDENTIALS_PATH,
)


# =============================================================================
# Base class tests
# =============================================================================

class TestServiceConfig:
    """Test ServiceConfig base class."""

    def test_basic_config(self):
        config = ServiceConfig(name="test")
        assert config.name == "test"
        assert config.api_key is None
        assert config.extra == {}

    def test_config_with_api_key(self):
        config = ServiceConfig(name="test", api_key="key123")
        assert config.api_key == "key123"

    def test_config_from_env(self):
        import os
        os.environ['TEST_API_KEY'] = 'env_key'
        os.environ['TEST_CLIENT_ID'] = 'env_client'
        try:
            config = ServiceConfig.from_env("test", "TEST")
            assert config.api_key == 'env_key'
            assert config.client_id == 'env_client'
        finally:
            del os.environ['TEST_API_KEY']
            del os.environ['TEST_CLIENT_ID']


class TestImportResult:
    """Test ImportResult data class."""

    def test_basic_result(self):
        result = ImportResult(
            url="https://example.com",
            title="Test Title",
        )
        assert result.url == "https://example.com"
        assert result.title == "Test Title"
        assert result.description == ""
        assert result.tags == []
        assert result.media_type is None

    def test_full_result(self):
        result = ImportResult(
            url="https://youtube.com/watch?v=abc123",
            title="Test Video",
            description="A test description",
            tags=["video", "youtube"],
            media_type="video",
            media_source="youtube",
            media_id="abc123",
            author_name="Test Channel",
            author_url="https://youtube.com/channel/UC123",
            thumbnail_url="https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            extra_data={"duration_seconds": 300},
        )
        assert result.media_id == "abc123"
        assert result.extra_data["duration_seconds"] == 300

    def test_to_bookmark_dict(self):
        result = ImportResult(
            url="https://youtube.com/watch?v=abc123",
            title="Test Video",
            description="Description",
            tags=["video"],
            media_type="video",
            media_source="youtube",
            media_id="abc123",
        )
        data = result.to_bookmark_dict()
        assert data["url"] == "https://youtube.com/watch?v=abc123"
        assert data["title"] == "Test Video"
        assert data["media_type"] == "video"
        assert "thumbnail_url" not in data  # None values should be removed

    def test_to_bookmark_dict_removes_none(self):
        result = ImportResult(
            url="https://example.com",
            title="Test",
        )
        data = result.to_bookmark_dict()
        assert "media_type" not in data
        assert "author_name" not in data
        assert "thumbnail_url" not in data


# =============================================================================
# YouTube Config tests
# =============================================================================

class TestYouTubeConfig:
    """Test YouTubeConfig class."""

    def test_default_paths(self):
        config = YouTubeConfig(name="youtube")
        assert config.credentials_file == DEFAULT_CREDENTIALS_PATH
        assert config.token_file == DEFAULT_TOKEN_PATH

    def test_custom_paths(self):
        config = YouTubeConfig(
            name="youtube",
            credentials_file=Path("/custom/creds.json"),
            token_file=Path("/custom/token.pickle"),
        )
        assert config.credentials_file == Path("/custom/creds.json")
        assert config.token_file == Path("/custom/token.pickle")


# =============================================================================
# YouTubeImporter tests (URL parsing - no API needed)
# =============================================================================

class TestYouTubeImporterURLParsing:
    """Test URL parsing methods (no API required)."""

    @pytest.fixture
    def importer(self):
        """Create importer without API connection."""
        return YouTubeImporter(api_key="fake_key")

    def test_validate_url_valid(self, importer):
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            "https://youtube.com/channel/UCXgGY0wkgOzynnHvSEVmE3A",
            "https://youtube.com/@username",
            "https://www.youtube.com/c/channelname",
        ]
        for url in valid_urls:
            assert importer.validate_url(url), f"Should be valid: {url}"

    def test_validate_url_invalid(self, importer):
        invalid_urls = [
            "https://example.com",
            "not-a-url",
            "https://vimeo.com/123456",
        ]
        for url in invalid_urls:
            assert not importer.validate_url(url), f"Should be invalid: {url}"

    def test_extract_video_id_from_url(self, importer):
        test_cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=10", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),  # Just the ID
        ]
        for url, expected_id in test_cases:
            result = importer._extract_video_id(url)
            assert result == expected_id, f"Failed for {url}: got {result}"

    def test_extract_video_id_invalid(self, importer):
        invalid = [
            "https://youtube.com/playlist?list=PLxxx",
            "not-an-id",
            "",
        ]
        for url in invalid:
            assert importer._extract_video_id(url) is None, f"Should be None: {url}"

    def test_extract_playlist_id_from_url(self, importer):
        test_cases = [
            ("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf", "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"),
            ("https://youtube.com/watch?v=abc&list=PLtest123", "PLtest123"),
            ("PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf", "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"),  # Just ID
        ]
        for url, expected_id in test_cases:
            result = importer._extract_playlist_id(url)
            assert result == expected_id, f"Failed for {url}: got {result}"

    def test_extract_id_combined(self, importer):
        test_cases = [
            ("https://youtube.com/watch?v=dQw4w9WgXcQ", ("video", "dQw4w9WgXcQ")),
            ("https://youtube.com/playlist?list=PLtest", ("playlist", "PLtest")),
            ("https://youtube.com/channel/UCtest123", ("channel", "UCtest123")),
            ("https://youtube.com/@username", ("channel", "@username")),
        ]
        for url, expected in test_cases:
            result = importer.extract_id(url)
            assert result == expected, f"Failed for {url}: got {result}"

    def test_parse_duration(self, importer):
        test_cases = [
            ("PT1H2M3S", 3723),  # 1 hour, 2 min, 3 sec
            ("PT5M30S", 330),   # 5 min, 30 sec
            ("PT30S", 30),      # 30 sec
            ("PT1H", 3600),     # 1 hour
            ("PT0S", 0),        # 0 seconds
        ]
        for duration, expected in test_cases:
            result = importer._parse_duration(duration)
            assert result == expected, f"Failed for {duration}: got {result}"

    def test_parse_datetime(self, importer):
        dt_str = "2024-01-15T10:30:00Z"
        result = importer._parse_datetime(dt_str)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_datetime_none(self, importer):
        assert importer._parse_datetime(None) is None
        assert importer._parse_datetime("invalid") is None

    def test_get_best_thumbnail(self, importer):
        thumbnails = {
            "default": {"url": "https://i.ytimg.com/default.jpg"},
            "medium": {"url": "https://i.ytimg.com/medium.jpg"},
            "high": {"url": "https://i.ytimg.com/high.jpg"},
            "maxres": {"url": "https://i.ytimg.com/maxres.jpg"},
        }
        result = importer._get_best_thumbnail(thumbnails)
        assert result == "https://i.ytimg.com/maxres.jpg"

    def test_get_best_thumbnail_fallback(self, importer):
        thumbnails = {
            "default": {"url": "https://i.ytimg.com/default.jpg"},
        }
        result = importer._get_best_thumbnail(thumbnails)
        assert result == "https://i.ytimg.com/default.jpg"

    def test_get_best_thumbnail_empty(self, importer):
        assert importer._get_best_thumbnail({}) is None

    def test_get_category_tags(self, importer):
        assert importer._get_category_tags("10") == ["category/music"]
        assert importer._get_category_tags("27") == ["category/education"]
        assert importer._get_category_tags("999") == []
        assert importer._get_category_tags(None) == []


# =============================================================================
# YouTubeImporter tests (with mocked API)
# =============================================================================

class TestYouTubeImporterWithMockedAPI:
    """Test import methods with mocked YouTube API."""

    @pytest.fixture
    def mock_youtube_service(self):
        """Create a mock YouTube API service."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def importer_with_mock(self, mock_youtube_service):
        """Create importer with mocked API service."""
        importer = YouTubeImporter(api_key="fake_key")
        importer._youtube = mock_youtube_service  # Set private attr directly
        importer._authenticated = True
        return importer

    def test_import_video(self, importer_with_mock):
        """Test importing a single video."""
        mock_response = {
            'items': [{
                'id': 'dQw4w9WgXcQ',  # 11-char video ID
                'snippet': {
                    'title': 'Test Video Title',
                    'description': 'Test description',
                    'channelTitle': 'Test Channel',
                    'channelId': 'UCtest',
                    'publishedAt': '2024-01-01T12:00:00Z',
                    'thumbnails': {
                        'high': {'url': 'https://i.ytimg.com/test.jpg'}
                    },
                    'tags': ['tag1', 'tag2'],
                    'categoryId': '27',
                },
                'contentDetails': {
                    'duration': 'PT5M30S'
                },
                'statistics': {
                    'viewCount': '1000',
                    'likeCount': '100',
                }
            }]
        }
        importer_with_mock.youtube.videos().list().execute.return_value = mock_response

        result = importer_with_mock.import_video('dQw4w9WgXcQ')

        assert result.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert result.title == "Test Video Title"
        assert result.media_type == "video"
        assert result.media_source == "youtube"
        assert result.media_id == "dQw4w9WgXcQ"
        assert result.author_name == "Test Channel"
        assert "youtube" in result.tags
        assert "video" in result.tags
        assert "category/education" in result.tags

    def test_import_video_not_found(self, importer_with_mock):
        """Test importing a non-existent video."""
        importer_with_mock.youtube.videos().list().execute.return_value = {'items': []}

        with pytest.raises(ValueError, match="Video not found"):
            importer_with_mock.import_video('xxxxxxxxxxx')  # Valid format but not found

    def test_import_subscriptions(self, importer_with_mock):
        """Test importing subscriptions."""
        mock_response = {
            'items': [
                {
                    'snippet': {
                        'title': 'Channel 1',
                        'description': 'First channel',
                        'resourceId': {'channelId': 'UC111'},
                        'publishedAt': '2023-01-01T00:00:00Z',
                        'thumbnails': {},
                    }
                },
                {
                    'snippet': {
                        'title': 'Channel 2',
                        'description': 'Second channel',
                        'resourceId': {'channelId': 'UC222'},
                        'publishedAt': '2023-06-01T00:00:00Z',
                        'thumbnails': {},
                    }
                }
            ],
            'nextPageToken': None,
        }
        importer_with_mock.youtube.subscriptions().list().execute.return_value = mock_response

        results = list(importer_with_mock.import_subscriptions())

        assert len(results) == 2
        assert results[0].title == 'Channel 1'
        assert results[0].media_type == 'channel'
        assert 'subscription' in results[0].tags
        assert results[1].title == 'Channel 2'

    def test_import_subscriptions_with_limit(self, importer_with_mock):
        """Test importing subscriptions with a limit."""
        mock_response = {
            'items': [
                {
                    'snippet': {
                        'title': f'Channel {i}',
                        'description': f'Channel {i} desc',
                        'resourceId': {'channelId': f'UC{i}'},
                        'publishedAt': '2023-01-01T00:00:00Z',
                        'thumbnails': {},
                    }
                }
                for i in range(5)
            ],
            'nextPageToken': None,
        }
        importer_with_mock.youtube.subscriptions().list().execute.return_value = mock_response

        results = list(importer_with_mock.import_subscriptions(limit=3))

        assert len(results) == 3

    def test_import_playlists(self, importer_with_mock):
        """Test importing user playlists."""
        mock_response = {
            'items': [{
                'id': 'PLtest123',
                'snippet': {
                    'title': 'My Playlist',
                    'description': 'Test playlist',
                    'channelTitle': 'My Channel',
                    'publishedAt': '2024-01-01T00:00:00Z',
                    'thumbnails': {},
                },
                'contentDetails': {
                    'itemCount': 10
                }
            }],
            'nextPageToken': None,
        }
        importer_with_mock.youtube.playlists().list().execute.return_value = mock_response

        results = list(importer_with_mock.import_playlists())

        assert len(results) == 1
        assert results[0].title == 'My Playlist'
        assert results[0].media_type == 'playlist'
        assert results[0].media_id == 'PLtest123'
        assert results[0].extra_data['video_count'] == 10

    def test_get_import_targets(self, importer_with_mock):
        """Test getting available import targets."""
        targets = importer_with_mock.get_import_targets()

        target_names = [t['name'] for t in targets]
        assert 'library' in target_names
        assert 'subscriptions' in target_names
        assert 'playlists' in target_names
        assert 'playlist' in target_names
        assert 'channel' in target_names
        assert 'video' in target_names

        # Check auth requirements
        library_target = next(t for t in targets if t['name'] == 'library')
        assert library_target['requires_auth'] is True

        video_target = next(t for t in targets if t['name'] == 'video')
        assert video_target['requires_auth'] is False


class TestYouTubeImporterAutoTagging:
    """Test auto-tagging functionality."""

    @pytest.fixture
    def importer(self):
        return YouTubeImporter(api_key="fake_key")

    def test_auto_tag_basic(self, importer):
        result = ImportResult(
            url="https://youtube.com/watch?v=test",
            title="Test Video",
            tags=["existing-tag"],
            media_type="video",
        )
        tags = importer.auto_tag(result)

        assert "existing-tag" in tags
        assert "youtube" in tags
        assert "content/video" in tags

    def test_auto_tag_deduplicates(self, importer):
        result = ImportResult(
            url="https://youtube.com/watch?v=test",
            title="Test",
            tags=["youtube", "video"],  # Already has youtube tag
            media_type="video",
        )
        tags = importer.auto_tag(result)

        # Should not have duplicates
        assert tags.count("youtube") == 1


class TestYouTubeImporterInitialization:
    """Test importer initialization."""

    def test_init_with_api_key(self):
        importer = YouTubeImporter(api_key="test_key")
        assert importer.api_key == "test_key"
        assert importer.credentials_file == DEFAULT_CREDENTIALS_PATH  # Has default

    def test_init_with_config(self):
        config = YouTubeConfig(
            name="youtube",
            api_key="config_key",
            credentials_file=Path("/path/to/creds.json"),
        )
        importer = YouTubeImporter(config=config)
        assert importer.config == config

    def test_service_properties(self):
        importer = YouTubeImporter(api_key="test")
        assert importer.service_name == "youtube"
        assert importer.service_url == "youtube.com"
        assert importer.requires_auth is True
        assert importer.auth_type == "oauth2"


# =============================================================================
# Integration-style tests (still mocked, but testing full flows)
# =============================================================================

class TestYouTubeImportFlows:
    """Test complete import flows."""

    @pytest.fixture
    def importer_with_mock(self):
        """Create importer with fully mocked service."""
        importer = YouTubeImporter(api_key="fake")
        importer._youtube = MagicMock()  # Set private attr directly
        importer._authenticated = True
        return importer

    def test_import_playlist_flow(self, importer_with_mock):
        """Test importing videos from a playlist."""
        # Mock playlist items
        playlist_response = {
            'items': [
                {'snippet': {'resourceId': {'videoId': 'vid1'}}, 'contentDetails': {}},
                {'snippet': {'resourceId': {'videoId': 'vid2'}}, 'contentDetails': {}},
            ],
            'nextPageToken': None,
        }

        # Mock video details
        video_response = {
            'items': [{
                'id': 'vid1',
                'snippet': {
                    'title': 'Video 1',
                    'description': 'Desc 1',
                    'channelTitle': 'Channel',
                    'channelId': 'UC123',
                    'publishedAt': '2024-01-01T00:00:00Z',
                    'thumbnails': {},
                    'tags': [],
                },
                'contentDetails': {'duration': 'PT5M'},
                'statistics': {'viewCount': '100', 'likeCount': '10'},
            }]
        }

        # Mock playlist info
        playlist_info = {
            'items': [{'snippet': {'title': 'Test Playlist'}}]
        }

        importer_with_mock.youtube.playlistItems().list().execute.return_value = playlist_response
        importer_with_mock.youtube.videos().list().execute.return_value = video_response
        importer_with_mock.youtube.playlists().list().execute.return_value = playlist_info

        results = list(importer_with_mock.import_playlist("PLtest"))

        assert len(results) == 2

    def test_hierarchical_tags_preserved(self, importer_with_mock):
        """Test that hierarchical tags (like /youtube/user) are preserved."""
        mock_response = {
            'items': [{
                'id': 'dQw4w9WgXcQ',  # Valid 11-char video ID
                'snippet': {
                    'title': 'Test Video',
                    'description': '',
                    'channelTitle': 'Test',
                    'channelId': 'UC123',
                    'publishedAt': '2024-01-01T00:00:00Z',
                    'thumbnails': {},
                    'tags': [],
                },
                'contentDetails': {'duration': 'PT1M'},
                'statistics': {'viewCount': '0', 'likeCount': '0'},
            }]
        }
        importer_with_mock.youtube.videos().list().execute.return_value = mock_response

        result = importer_with_mock.import_video('dQw4w9WgXcQ')

        # Add hierarchical tag manually (as CLI would do)
        result.tags = list(set(result.tags + ['/youtube/queelius']))

        assert '/youtube/queelius' in result.tags
        assert 'youtube' in result.tags
