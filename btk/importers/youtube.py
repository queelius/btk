"""
YouTube Importer for BTK

Import bookmarks from YouTube:
- User's liked videos
- User's watch later playlist
- User's subscriptions (as channel bookmarks)
- User's custom playlists
- Public playlists by URL/ID
- Channels by URL/ID
- Individual videos

Requires: pip install google-api-python-client google-auth-oauthlib
"""

import re
import os
import pickle
import logging
from typing import List, Optional, Dict, Generator, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from .base import ServiceImporter, ServiceConfig, ImportResult

logger = logging.getLogger(__name__)

# Try to import Google API libraries
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    HAS_YOUTUBE_API = True
except ImportError:
    HAS_YOUTUBE_API = False

# Constants
MAX_RESULTS_PER_PAGE = 50
YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
DEFAULT_TOKEN_PATH = Path.home() / '.config' / 'btk' / 'youtube_token.pickle'
DEFAULT_CREDENTIALS_PATH = Path.home() / '.config' / 'btk' / 'youtube_credentials.json'


@dataclass
class YouTubeConfig(ServiceConfig):
    """YouTube-specific configuration."""
    credentials_file: Optional[Path] = None
    token_file: Optional[Path] = None

    def __post_init__(self):
        if self.credentials_file is None:
            self.credentials_file = DEFAULT_CREDENTIALS_PATH
        if self.token_file is None:
            self.token_file = DEFAULT_TOKEN_PATH


class YouTubeImporter(ServiceImporter):
    """
    Import videos and playlists from YouTube.

    Supports two authentication modes:
    1. API Key: For public content only (playlists, channels, videos)
    2. OAuth2: For user-specific content (library, subscriptions, private playlists)

    Usage:
        # With API key (public content only)
        importer = YouTubeImporter(api_key="your-api-key")

        # With OAuth (user content)
        importer = YouTubeImporter()
        importer.authenticate()  # Opens browser for OAuth flow

        # Import liked videos
        for video in importer.import_library():
            print(video.title)

        # Import a playlist
        for video in importer.import_playlist("PLxxxxxx"):
            print(video.title)
    """

    service_name = "youtube"
    service_url = "youtube.com"
    requires_auth = True
    auth_type = "oauth2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        credentials_file: Optional[Path] = None,
        token_file: Optional[Path] = None,
        config: Optional[YouTubeConfig] = None,
    ):
        """
        Initialize YouTube importer.

        Args:
            api_key: YouTube Data API key (for public content)
            credentials_file: Path to OAuth client secrets JSON
            token_file: Path to store OAuth token
            config: Full configuration object
        """
        if not HAS_YOUTUBE_API:
            raise ImportError(
                "YouTube API libraries not installed. Run:\n"
                "  pip install google-api-python-client google-auth-oauthlib"
            )

        super().__init__(config)

        self.api_key = api_key or os.environ.get('YOUTUBE_API_KEY')
        self.credentials_file = credentials_file or DEFAULT_CREDENTIALS_PATH
        self.token_file = token_file or DEFAULT_TOKEN_PATH
        self._youtube = None
        self._use_oauth = False

    @property
    def youtube(self):
        """Lazy-load YouTube API client."""
        if self._youtube is None:
            if self._use_oauth:
                self._youtube = self._build_oauth_client()
            elif self.api_key:
                self._youtube = build('youtube', 'v3', developerKey=self.api_key)
            else:
                raise ValueError(
                    "No authentication configured. Either:\n"
                    "  1. Set YOUTUBE_API_KEY environment variable\n"
                    "  2. Call authenticate() for OAuth\n"
                    "  3. Pass api_key to constructor"
                )
        return self._youtube

    def authenticate(self, credentials_file: Optional[Path] = None, **kwargs) -> bool:
        """
        Authenticate with OAuth2 for user-specific content.

        This opens a browser window for the OAuth flow on first run.
        Subsequent runs use the cached token.

        Args:
            credentials_file: Path to OAuth client secrets JSON file

        Returns:
            True if authentication successful
        """
        creds_file = credentials_file or self.credentials_file

        if not creds_file.exists():
            raise FileNotFoundError(
                f"OAuth credentials file not found: {creds_file}\n"
                "Download from Google Cloud Console:\n"
                "  1. Go to https://console.cloud.google.com/apis/credentials\n"
                "  2. Create OAuth 2.0 Client ID (Desktop app)\n"
                "  3. Download JSON and save to: {creds_file}"
            )

        self.credentials_file = creds_file
        self._use_oauth = True
        self._youtube = None  # Reset to force rebuild

        # Test authentication by making a simple request
        try:
            self.youtube.channels().list(part="id", mine=True).execute()
            self._authenticated = True
            logger.info("YouTube OAuth authentication successful")
            return True
        except Exception as e:
            logger.error(f"YouTube authentication failed: {e}")
            self._authenticated = False
            return False

    def _build_oauth_client(self):
        """Build OAuth-authenticated YouTube client."""
        creds = None

        # Load existing token
        if self.token_file.exists():
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)

        # Refresh or get new token
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file),
                    scopes=YOUTUBE_SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for next run
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)

        return build('youtube', 'v3', credentials=creds)

    def get_import_targets(self) -> List[Dict[str, str]]:
        """List available import targets."""
        return [
            {
                'name': 'library',
                'description': 'Your liked videos',
                'requires_auth': True,
            },
            {
                'name': 'watch_later',
                'description': 'Your Watch Later playlist',
                'requires_auth': True,
            },
            {
                'name': 'subscriptions',
                'description': 'Channels you subscribe to',
                'requires_auth': True,
            },
            {
                'name': 'playlists',
                'description': 'Your playlists',
                'requires_auth': True,
            },
            {
                'name': 'playlist',
                'description': 'A specific playlist by ID or URL',
                'requires_auth': False,
            },
            {
                'name': 'channel',
                'description': 'All videos from a channel',
                'requires_auth': False,
            },
            {
                'name': 'video',
                'description': 'A single video by ID or URL',
                'requires_auth': False,
            },
        ]

    # =========================================================================
    # User-specific imports (require OAuth)
    # =========================================================================

    def import_library(self, limit: Optional[int] = None) -> Generator[ImportResult, None, None]:
        """
        Import user's liked videos.

        Args:
            limit: Maximum number of videos to import

        Yields:
            ImportResult for each liked video
        """
        yield from self._import_playlist_videos('LL', limit=limit, extra_tags=['liked'])

    def import_watch_later(self, limit: Optional[int] = None) -> Generator[ImportResult, None, None]:
        """
        Import user's Watch Later playlist.

        Args:
            limit: Maximum number of videos to import

        Yields:
            ImportResult for each video
        """
        yield from self._import_playlist_videos('WL', limit=limit, extra_tags=['watch-later'])

    def import_subscriptions(self, limit: Optional[int] = None) -> Generator[ImportResult, None, None]:
        """
        Import user's subscriptions as channel bookmarks.

        Args:
            limit: Maximum number of subscriptions to import

        Yields:
            ImportResult for each subscribed channel
        """
        page_token = None
        count = 0

        while True:
            response = self.youtube.subscriptions().list(
                part="snippet",
                mine=True,
                maxResults=min(MAX_RESULTS_PER_PAGE, limit - count if limit else MAX_RESULTS_PER_PAGE),
                pageToken=page_token
            ).execute()

            for item in response.get('items', []):
                snippet = item['snippet']
                channel_id = snippet['resourceId']['channelId']

                yield ImportResult(
                    url=f"https://www.youtube.com/channel/{channel_id}",
                    title=snippet['title'],
                    description=snippet.get('description', '')[:500],
                    tags=['youtube', 'subscription', 'channel'],
                    media_type='channel',
                    media_source='youtube',
                    media_id=channel_id,
                    author_name=snippet['title'],
                    author_url=f"https://www.youtube.com/channel/{channel_id}",
                    thumbnail_url=self._get_best_thumbnail(snippet.get('thumbnails', {})),
                    published_at=self._parse_datetime(snippet.get('publishedAt')),
                )

                count += 1
                if limit and count >= limit:
                    return

            page_token = response.get('nextPageToken')
            if not page_token:
                break

    def import_playlists(self, limit: Optional[int] = None) -> Generator[ImportResult, None, None]:
        """
        Import user's playlists (not the videos, just the playlists themselves).

        Args:
            limit: Maximum number of playlists to import

        Yields:
            ImportResult for each playlist
        """
        page_token = None
        count = 0

        while True:
            response = self.youtube.playlists().list(
                part="snippet,contentDetails",
                mine=True,
                maxResults=min(MAX_RESULTS_PER_PAGE, limit - count if limit else MAX_RESULTS_PER_PAGE),
                pageToken=page_token
            ).execute()

            for item in response.get('items', []):
                snippet = item['snippet']
                playlist_id = item['id']
                video_count = item['contentDetails'].get('itemCount', 0)

                yield ImportResult(
                    url=f"https://www.youtube.com/playlist?list={playlist_id}",
                    title=snippet['title'],
                    description=snippet.get('description', '')[:500],
                    tags=['youtube', 'playlist'],
                    media_type='playlist',
                    media_source='youtube',
                    media_id=playlist_id,
                    author_name=snippet.get('channelTitle'),
                    thumbnail_url=self._get_best_thumbnail(snippet.get('thumbnails', {})),
                    published_at=self._parse_datetime(snippet.get('publishedAt')),
                    extra_data={'video_count': video_count},
                )

                count += 1
                if limit and count >= limit:
                    return

            page_token = response.get('nextPageToken')
            if not page_token:
                break

    def import_playlist_with_videos(
        self,
        playlist_id: str,
        limit: Optional[int] = None
    ) -> Generator[ImportResult, None, None]:
        """
        Import all videos from a user playlist.

        Args:
            playlist_id: YouTube playlist ID
            limit: Maximum videos to import

        Yields:
            ImportResult for each video
        """
        # Get playlist title for tagging
        try:
            playlist_info = self.youtube.playlists().list(
                part="snippet",
                id=playlist_id
            ).execute()
            playlist_title = playlist_info['items'][0]['snippet']['title'] if playlist_info.get('items') else None
        except Exception:
            playlist_title = None

        extra_tags = ['playlist']
        if playlist_title:
            # Create a slug from playlist title
            tag_slug = re.sub(r'[^a-z0-9]+', '-', playlist_title.lower()).strip('-')[:30]
            extra_tags.append(f"playlist/{tag_slug}")

        yield from self._import_playlist_videos(playlist_id, limit=limit, extra_tags=extra_tags)

    # =========================================================================
    # Public imports (API key sufficient)
    # =========================================================================

    def import_playlist(
        self,
        playlist_id_or_url: str,
        limit: Optional[int] = None
    ) -> Generator[ImportResult, None, None]:
        """
        Import videos from a public playlist.

        Args:
            playlist_id_or_url: Playlist ID or full URL
            limit: Maximum videos to import

        Yields:
            ImportResult for each video
        """
        playlist_id = self._extract_playlist_id(playlist_id_or_url)
        if not playlist_id:
            raise ValueError(f"Could not extract playlist ID from: {playlist_id_or_url}")

        yield from self.import_playlist_with_videos(playlist_id, limit=limit)

    def import_channel(
        self,
        channel_id_or_url: str,
        limit: Optional[int] = None
    ) -> Generator[ImportResult, None, None]:
        """
        Import all videos from a channel.

        Args:
            channel_id_or_url: Channel ID, handle, or URL
            limit: Maximum videos to import

        Yields:
            ImportResult for each video
        """
        channel_id = self._resolve_channel_id(channel_id_or_url)
        if not channel_id:
            raise ValueError(f"Could not resolve channel: {channel_id_or_url}")

        # Get channel info and uploads playlist
        response = self.youtube.channels().list(
            part="contentDetails,snippet",
            id=channel_id
        ).execute()

        if not response.get('items'):
            raise ValueError(f"Channel not found: {channel_id}")

        channel = response['items'][0]
        uploads_playlist_id = channel['contentDetails']['relatedPlaylists']['uploads']
        channel_name = channel['snippet']['title']

        # Create channel tag
        tag_slug = re.sub(r'[^a-z0-9]+', '-', channel_name.lower()).strip('-')[:30]
        extra_tags = ['channel', f"channel/{tag_slug}"]

        yield from self._import_playlist_videos(
            uploads_playlist_id,
            limit=limit,
            extra_tags=extra_tags
        )

    def import_video(self, video_id_or_url: str) -> ImportResult:
        """
        Import a single video.

        Args:
            video_id_or_url: Video ID or full URL

        Returns:
            ImportResult for the video
        """
        video_id = self._extract_video_id(video_id_or_url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from: {video_id_or_url}")

        return self._fetch_video(video_id)

    def import_user_playlists(
        self,
        channel_id_or_url: str,
        limit: Optional[int] = None
    ) -> Generator[ImportResult, None, None]:
        """
        Import another user's public playlists.

        Args:
            channel_id_or_url: Channel ID, handle, or URL
            limit: Maximum playlists to import

        Yields:
            ImportResult for each playlist
        """
        channel_id = self._resolve_channel_id(channel_id_or_url)
        if not channel_id:
            raise ValueError(f"Could not resolve channel: {channel_id_or_url}")

        page_token = None
        count = 0

        while True:
            response = self.youtube.playlists().list(
                part="snippet,contentDetails",
                channelId=channel_id,
                maxResults=min(MAX_RESULTS_PER_PAGE, limit - count if limit else MAX_RESULTS_PER_PAGE),
                pageToken=page_token
            ).execute()

            for item in response.get('items', []):
                snippet = item['snippet']
                playlist_id = item['id']
                video_count = item['contentDetails'].get('itemCount', 0)

                yield ImportResult(
                    url=f"https://www.youtube.com/playlist?list={playlist_id}",
                    title=snippet['title'],
                    description=snippet.get('description', '')[:500],
                    tags=['youtube', 'playlist'],
                    media_type='playlist',
                    media_source='youtube',
                    media_id=playlist_id,
                    author_name=snippet.get('channelTitle'),
                    author_url=f"https://www.youtube.com/channel/{snippet.get('channelId')}",
                    thumbnail_url=self._get_best_thumbnail(snippet.get('thumbnails', {})),
                    published_at=self._parse_datetime(snippet.get('publishedAt')),
                    extra_data={'video_count': video_count},
                )

                count += 1
                if limit and count >= limit:
                    return

            page_token = response.get('nextPageToken')
            if not page_token:
                break

    # =========================================================================
    # Helper methods
    # =========================================================================

    def _import_playlist_videos(
        self,
        playlist_id: str,
        limit: Optional[int] = None,
        extra_tags: Optional[List[str]] = None
    ) -> Generator[ImportResult, None, None]:
        """Fetch all videos from a playlist."""
        page_token = None
        count = 0
        extra_tags = extra_tags or []

        while True:
            try:
                response = self.youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=min(MAX_RESULTS_PER_PAGE, limit - count if limit else MAX_RESULTS_PER_PAGE),
                    pageToken=page_token
                ).execute()
            except Exception as e:
                logger.error(f"Error fetching playlist {playlist_id}: {e}")
                break

            for item in response.get('items', []):
                try:
                    video_id = item['snippet']['resourceId']['videoId']
                    result = self._fetch_video(video_id, extra_tags=extra_tags)
                    yield result
                    count += 1

                    if limit and count >= limit:
                        return
                except Exception as e:
                    logger.warning(f"Failed to import video: {e}")
                    continue

            page_token = response.get('nextPageToken')
            if not page_token:
                break

    def _fetch_video(self, video_id: str, extra_tags: Optional[List[str]] = None) -> ImportResult:
        """Fetch video details and convert to ImportResult."""
        response = self.youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=video_id
        ).execute()

        if not response.get('items'):
            raise ValueError(f"Video not found: {video_id}")

        item = response['items'][0]
        snippet = item['snippet']
        content = item['contentDetails']
        stats = item.get('statistics', {})

        # Build tags
        tags = ['youtube', 'video']
        if extra_tags:
            tags.extend(extra_tags)

        # Add video tags (limited)
        video_tags = snippet.get('tags', [])[:5]
        for tag in video_tags:
            # Clean up tag
            clean_tag = re.sub(r'[^a-z0-9\-/]+', '-', tag.lower()).strip('-')
            if clean_tag and len(clean_tag) <= 30:
                tags.append(clean_tag)

        # Add category-based tags
        category_tags = self._get_category_tags(snippet.get('categoryId'))
        tags.extend(category_tags)

        # Parse duration
        duration_seconds = self._parse_duration(content.get('duration', 'PT0S'))

        return ImportResult(
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=snippet['title'],
            description=snippet.get('description', '')[:500],
            tags=list(set(tags)),  # Deduplicate
            media_type='video',
            media_source='youtube',
            media_id=video_id,
            author_name=snippet.get('channelTitle'),
            author_url=f"https://www.youtube.com/channel/{snippet.get('channelId')}",
            thumbnail_url=self._get_best_thumbnail(snippet.get('thumbnails', {})),
            published_at=self._parse_datetime(snippet.get('publishedAt')),
            extra_data={
                'duration_seconds': duration_seconds,
                'view_count': int(stats.get('viewCount', 0)),
                'like_count': int(stats.get('likeCount', 0)),
                'channel_id': snippet.get('channelId'),
            }
        )

    def _get_best_thumbnail(self, thumbnails: Dict) -> Optional[str]:
        """Get the best quality thumbnail URL."""
        quality_order = ['maxres', 'standard', 'high', 'medium', 'default']
        for quality in quality_order:
            if quality in thumbnails:
                return thumbnails[quality].get('url')
        return None

    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration to seconds."""
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except ValueError:
            return None

    def _get_category_tags(self, category_id: Optional[str]) -> List[str]:
        """Map YouTube category ID to tags."""
        # YouTube category IDs: https://developers.google.com/youtube/v3/docs/videoCategories
        categories = {
            '1': 'film-animation',
            '2': 'autos-vehicles',
            '10': 'music',
            '15': 'pets-animals',
            '17': 'sports',
            '19': 'travel-events',
            '20': 'gaming',
            '22': 'people-blogs',
            '23': 'comedy',
            '24': 'entertainment',
            '25': 'news-politics',
            '26': 'howto-style',
            '27': 'education',
            '28': 'science-technology',
            '29': 'nonprofits-activism',
        }
        if category_id and category_id in categories:
            return [f"category/{categories[category_id]}"]
        return []

    # =========================================================================
    # URL parsing
    # =========================================================================

    def validate_url(self, url: str) -> bool:
        """Check if URL is a valid YouTube URL."""
        patterns = [
            r'(https?://)?(www\.)?(youtube\.com|youtu\.be)',
            r'(https?://)?(www\.)?youtube\.com/(watch|playlist|channel|c|user|@)',
        ]
        return any(re.search(p, url) for p in patterns)

    def extract_id(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Extract content type and ID from YouTube URL.

        Returns:
            Tuple of (type, id) where type is 'video', 'playlist', or 'channel'
        """
        # Video
        video_id = self._extract_video_id(url)
        if video_id:
            return ('video', video_id)

        # Playlist
        playlist_id = self._extract_playlist_id(url)
        if playlist_id:
            return ('playlist', playlist_id)

        # Channel
        channel_match = re.search(r'(?:channel|c|user)/([^/?]+)', url)
        if channel_match:
            return ('channel', channel_match.group(1))

        # Handle pattern (e.g., @username)
        handle_match = re.search(r'@([^/?]+)', url)
        if handle_match:
            return ('channel', '@' + handle_match.group(1))

        return None

    def _extract_video_id(self, url_or_id: str) -> Optional[str]:
        """Extract video ID from URL or return if already an ID."""
        # Already an ID?
        if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
            return url_or_id

        # Full URL patterns
        patterns = [
            r'(?:v=|/)([0-9A-Za-z_-]{11})(?:\?|&|$|#)',
            r'youtu\.be/([0-9A-Za-z_-]{11})',
            r'embed/([0-9A-Za-z_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)
        return None

    def _extract_playlist_id(self, url_or_id: str) -> Optional[str]:
        """Extract playlist ID from URL or return if already an ID."""
        # Already an ID?
        if re.match(r'^[A-Za-z0-9_-]+$', url_or_id) and 'youtube' not in url_or_id:
            return url_or_id

        match = re.search(r'list=([A-Za-z0-9_-]+)', url_or_id)
        return match.group(1) if match else None

    def _resolve_channel_id(self, channel_id_or_url: str) -> Optional[str]:
        """Resolve a channel identifier to a channel ID."""
        # Already a channel ID?
        if re.match(r'^UC[A-Za-z0-9_-]{22}$', channel_id_or_url):
            return channel_id_or_url

        # Extract from URL
        patterns = [
            (r'channel/(UC[A-Za-z0-9_-]{22})', 'id'),
            (r'@([^/?]+)', 'handle'),
            (r'c/([^/?]+)', 'custom'),
            (r'user/([^/?]+)', 'user'),
        ]

        for pattern, id_type in patterns:
            match = re.search(pattern, channel_id_or_url)
            if match:
                identifier = match.group(1)
                if id_type == 'id':
                    return identifier
                return self._lookup_channel_id(identifier, id_type)

        # Try as handle if starts with @
        if channel_id_or_url.startswith('@'):
            return self._lookup_channel_id(channel_id_or_url[1:], 'handle')

        return None

    def _lookup_channel_id(self, identifier: str, id_type: str) -> Optional[str]:
        """Look up channel ID from handle, custom URL, or username."""
        try:
            if id_type == 'handle':
                # Use search to find channel by handle
                response = self.youtube.search().list(
                    part="snippet",
                    q=f"@{identifier}",
                    type="channel",
                    maxResults=1
                ).execute()
            else:
                # Try forUsername for legacy usernames
                response = self.youtube.channels().list(
                    part="id",
                    forUsername=identifier
                ).execute()

            if response.get('items'):
                item = response['items'][0]
                return item.get('id', {}).get('channelId') or item.get('id')
        except Exception as e:
            logger.warning(f"Could not resolve channel {identifier}: {e}")

        return None
