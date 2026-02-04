"""
Media detection for bookmark URLs.

This module provides URL pattern matching to detect media content from various
platforms like YouTube, Spotify, arXiv, etc., and extract platform-specific
identifiers.
"""
import re
from dataclasses import dataclass
from typing import Optional, Dict, List
from urllib.parse import urlparse, parse_qs


@dataclass
class MediaInfo:
    """Information about detected media in a URL."""

    source: str  # Platform name: youtube, spotify, arxiv, etc.
    media_id: str  # Platform-specific identifier
    media_type: str  # video, audio, document, image, code
    url_type: str  # video, playlist, channel, profile, track, album, paper, repo


# Media type constants
MEDIA_TYPE_VIDEO = "video"
MEDIA_TYPE_AUDIO = "audio"
MEDIA_TYPE_DOCUMENT = "document"
MEDIA_TYPE_IMAGE = "image"
MEDIA_TYPE_CODE = "code"

# URL type constants
URL_TYPE_VIDEO = "video"
URL_TYPE_PLAYLIST = "playlist"
URL_TYPE_CHANNEL = "channel"
URL_TYPE_PROFILE = "profile"
URL_TYPE_TRACK = "track"
URL_TYPE_ALBUM = "album"
URL_TYPE_EPISODE = "episode"
URL_TYPE_PODCAST = "podcast"
URL_TYPE_PAPER = "paper"
URL_TYPE_REPO = "repo"
URL_TYPE_POST = "post"
URL_TYPE_THREAD = "thread"


class MediaDetector:
    """
    Detect media type and source from URLs.

    Supports various platforms including:
    - Video: YouTube, Vimeo, Twitch, Dailymotion
    - Audio: Spotify, SoundCloud, Bandcamp, Apple Music
    - Documents: arXiv, DOI, PDF links
    - Code: GitHub, GitLab, Bitbucket
    - Social: Twitter/X, Reddit, Hacker News
    """

    # Pattern definitions: source -> [(pattern, url_type, media_type)]
    PATTERNS: Dict[str, List[tuple]] = {
        # Video platforms
        "youtube": [
            (r"youtube\.com/watch\?.*v=(?P<id>[\w-]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"youtu\.be/(?P<id>[\w-]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/embed/(?P<id>[\w-]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/v/(?P<id>[\w-]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/shorts/(?P<id>[\w-]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/playlist\?.*list=(?P<id>[\w-]+)", URL_TYPE_PLAYLIST, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/channel/(?P<id>[\w-]+)", URL_TYPE_CHANNEL, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/@(?P<id>[\w.-]+)", URL_TYPE_CHANNEL, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/c/(?P<id>[\w-]+)", URL_TYPE_CHANNEL, MEDIA_TYPE_VIDEO),
            (r"youtube\.com/user/(?P<id>[\w-]+)", URL_TYPE_CHANNEL, MEDIA_TYPE_VIDEO),
        ],
        "vimeo": [
            (r"vimeo\.com/(?P<id>\d+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"vimeo\.com/channels/[\w-]+/(?P<id>\d+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"vimeo\.com/groups/[\w-]+/videos/(?P<id>\d+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"player\.vimeo\.com/video/(?P<id>\d+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
        ],
        "twitch": [
            (r"twitch\.tv/videos/(?P<id>\d+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"twitch\.tv/(?P<id>[\w]+)(?:/clip/[\w-]+)?", URL_TYPE_CHANNEL, MEDIA_TYPE_VIDEO),
            (r"clips\.twitch\.tv/(?P<id>[\w-]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
        ],
        "dailymotion": [
            (r"dailymotion\.com/video/(?P<id>[\w]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
            (r"dai\.ly/(?P<id>[\w]+)", URL_TYPE_VIDEO, MEDIA_TYPE_VIDEO),
        ],
        # Audio platforms
        "spotify": [
            (r"open\.spotify\.com/track/(?P<id>\w+)", URL_TYPE_TRACK, MEDIA_TYPE_AUDIO),
            (r"open\.spotify\.com/album/(?P<id>\w+)", URL_TYPE_ALBUM, MEDIA_TYPE_AUDIO),
            (r"open\.spotify\.com/playlist/(?P<id>\w+)", URL_TYPE_PLAYLIST, MEDIA_TYPE_AUDIO),
            (r"open\.spotify\.com/episode/(?P<id>\w+)", URL_TYPE_EPISODE, MEDIA_TYPE_AUDIO),
            (r"open\.spotify\.com/show/(?P<id>\w+)", URL_TYPE_PODCAST, MEDIA_TYPE_AUDIO),
            (r"open\.spotify\.com/artist/(?P<id>\w+)", URL_TYPE_PROFILE, MEDIA_TYPE_AUDIO),
        ],
        "soundcloud": [
            (r"soundcloud\.com/(?P<id>[\w-]+/[\w-]+)", URL_TYPE_TRACK, MEDIA_TYPE_AUDIO),
            (r"soundcloud\.com/(?P<id>[\w-]+)/sets/[\w-]+", URL_TYPE_PLAYLIST, MEDIA_TYPE_AUDIO),
            (r"soundcloud\.com/(?P<id>[\w-]+)$", URL_TYPE_PROFILE, MEDIA_TYPE_AUDIO),
        ],
        "bandcamp": [
            (r"(?P<id>[\w-]+)\.bandcamp\.com/track/[\w-]+", URL_TYPE_TRACK, MEDIA_TYPE_AUDIO),
            (r"(?P<id>[\w-]+)\.bandcamp\.com/album/[\w-]+", URL_TYPE_ALBUM, MEDIA_TYPE_AUDIO),
            (r"(?P<id>[\w-]+)\.bandcamp\.com/?$", URL_TYPE_PROFILE, MEDIA_TYPE_AUDIO),
        ],
        "apple_music": [
            (r"music\.apple\.com/[\w-]+/album/[\w-]+/(?P<id>\d+)", URL_TYPE_ALBUM, MEDIA_TYPE_AUDIO),
            (r"music\.apple\.com/[\w-]+/playlist/[\w-]+/(?P<id>pl\.[\w-]+)", URL_TYPE_PLAYLIST, MEDIA_TYPE_AUDIO),
        ],
        # Document/Academic platforms
        "arxiv": [
            (r"arxiv\.org/abs/(?P<id>[\d.]+)", URL_TYPE_PAPER, MEDIA_TYPE_DOCUMENT),
            (r"arxiv\.org/pdf/(?P<id>[\d.]+)", URL_TYPE_PAPER, MEDIA_TYPE_DOCUMENT),
        ],
        "doi": [
            (r"doi\.org/(?P<id>10\.\d{4,}/[\S]+)", URL_TYPE_PAPER, MEDIA_TYPE_DOCUMENT),
        ],
        "pubmed": [
            (r"pubmed\.ncbi\.nlm\.nih\.gov/(?P<id>\d+)", URL_TYPE_PAPER, MEDIA_TYPE_DOCUMENT),
            (r"ncbi\.nlm\.nih\.gov/pubmed/(?P<id>\d+)", URL_TYPE_PAPER, MEDIA_TYPE_DOCUMENT),
        ],
        "semantic_scholar": [
            (r"semanticscholar\.org/paper/(?P<id>[\w]+)", URL_TYPE_PAPER, MEDIA_TYPE_DOCUMENT),
        ],
        # Code platforms
        "github": [
            (r"github\.com/(?P<id>[\w.-]+/[\w.-]+)(?:/|$)", URL_TYPE_REPO, MEDIA_TYPE_CODE),
            (r"gist\.github\.com/(?P<id>[\w.-]+/[\w]+)", URL_TYPE_REPO, MEDIA_TYPE_CODE),
        ],
        "gitlab": [
            (r"gitlab\.com/(?P<id>[\w.-]+/[\w.-]+)(?:/|$)", URL_TYPE_REPO, MEDIA_TYPE_CODE),
        ],
        "bitbucket": [
            (r"bitbucket\.org/(?P<id>[\w.-]+/[\w.-]+)(?:/|$)", URL_TYPE_REPO, MEDIA_TYPE_CODE),
        ],
        # Social/Discussion platforms
        "twitter": [
            (r"(?:twitter|x)\.com/(?P<id>\w+)/status/\d+", URL_TYPE_POST, MEDIA_TYPE_VIDEO),
            (r"(?:twitter|x)\.com/(?P<id>\w+)$", URL_TYPE_PROFILE, MEDIA_TYPE_VIDEO),
        ],
        "reddit": [
            (r"reddit\.com/r/\w+/comments/(?P<id>\w+)", URL_TYPE_THREAD, MEDIA_TYPE_DOCUMENT),
            (r"redd\.it/(?P<id>\w+)", URL_TYPE_THREAD, MEDIA_TYPE_DOCUMENT),
        ],
        "hackernews": [
            (r"news\.ycombinator\.com/item\?id=(?P<id>\d+)", URL_TYPE_THREAD, MEDIA_TYPE_DOCUMENT),
        ],
        # Podcast platforms
        "podcast_rss": [
            # Generic podcast feed detection by content type or extension
            (r"feeds\.[\w.-]+\.com/(?P<id>[\w/-]+)", URL_TYPE_PODCAST, MEDIA_TYPE_AUDIO),
            (r"(?P<id>[\w.-]+)/feed\.xml", URL_TYPE_PODCAST, MEDIA_TYPE_AUDIO),
            (r"(?P<id>[\w.-]+)\.rss", URL_TYPE_PODCAST, MEDIA_TYPE_AUDIO),
        ],
        "apple_podcasts": [
            (r"podcasts\.apple\.com/[\w-]+/podcast/[\w-]+/id(?P<id>\d+)", URL_TYPE_PODCAST, MEDIA_TYPE_AUDIO),
        ],
    }

    # Compiled patterns cache
    _compiled_patterns: Dict[str, List[tuple]] = {}

    def __init__(self):
        """Initialize and compile regex patterns."""
        if not MediaDetector._compiled_patterns:
            for source, patterns in self.PATTERNS.items():
                MediaDetector._compiled_patterns[source] = [
                    (re.compile(pattern, re.IGNORECASE), url_type, media_type)
                    for pattern, url_type, media_type in patterns
                ]

    def detect(self, url: str) -> Optional[MediaInfo]:
        """
        Detect media information from a URL.

        Args:
            url: The URL to analyze

        Returns:
            MediaInfo if the URL matches a known media pattern, None otherwise
        """
        if not url:
            return None

        # Normalize URL
        url = url.strip()

        # Check for direct PDF links
        if self._is_pdf_url(url):
            return MediaInfo(
                source="pdf",
                media_id=self._extract_filename(url),
                media_type=MEDIA_TYPE_DOCUMENT,
                url_type=URL_TYPE_PAPER,
            )

        # Try each source's patterns
        for source, patterns in self._compiled_patterns.items():
            for pattern, url_type, media_type in patterns:
                match = pattern.search(url)
                if match:
                    media_id = match.group("id")

                    # Special handling for YouTube video IDs from query params
                    if source == "youtube" and url_type == URL_TYPE_VIDEO:
                        media_id = self._extract_youtube_id(url) or media_id

                    return MediaInfo(
                        source=source,
                        media_id=media_id,
                        media_type=media_type,
                        url_type=url_type,
                    )

        return None

    def detect_batch(self, urls: List[str]) -> Dict[str, Optional[MediaInfo]]:
        """
        Detect media info for multiple URLs.

        Args:
            urls: List of URLs to analyze

        Returns:
            Dict mapping each URL to its MediaInfo (or None)
        """
        return {url: self.detect(url) for url in urls}

    def is_media_url(self, url: str) -> bool:
        """
        Check if a URL is a recognized media URL.

        Args:
            url: The URL to check

        Returns:
            True if the URL matches a known media pattern
        """
        return self.detect(url) is not None

    def get_media_type(self, url: str) -> Optional[str]:
        """
        Get the media type for a URL.

        Args:
            url: The URL to analyze

        Returns:
            Media type string (video, audio, document, etc.) or None
        """
        info = self.detect(url)
        return info.media_type if info else None

    def get_source(self, url: str) -> Optional[str]:
        """
        Get the source platform for a URL.

        Args:
            url: The URL to analyze

        Returns:
            Source name (youtube, spotify, etc.) or None
        """
        info = self.detect(url)
        return info.source if info else None

    def _is_pdf_url(self, url: str) -> bool:
        """Check if URL points to a PDF file."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith(".pdf") or "pdf" in parsed.query.lower()

    def _extract_filename(self, url: str) -> str:
        """Extract filename from URL path."""
        parsed = urlparse(url)
        path = parsed.path
        if "/" in path:
            return path.rsplit("/", 1)[-1]
        return path

    def _extract_youtube_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL query parameters."""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if "v" in query_params:
            return query_params["v"][0]
        return None

    @classmethod
    def get_supported_sources(cls) -> List[str]:
        """Get list of all supported media sources."""
        return list(cls.PATTERNS.keys())

    @classmethod
    def get_patterns_for_source(cls, source: str) -> List[str]:
        """Get pattern strings for a specific source."""
        if source not in cls.PATTERNS:
            return []
        return [pattern for pattern, _, _ in cls.PATTERNS[source]]


# Convenience function for simple detection
def detect_media(url: str) -> Optional[MediaInfo]:
    """
    Detect media information from a URL.

    This is a convenience function that creates a MediaDetector instance.
    For batch operations, create a MediaDetector instance directly.

    Args:
        url: The URL to analyze

    Returns:
        MediaInfo if the URL matches a known media pattern, None otherwise
    """
    return MediaDetector().detect(url)
