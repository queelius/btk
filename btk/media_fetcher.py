"""
Media metadata fetching for bookmark URLs.

This module provides metadata extraction from various media platforms using:
- yt-dlp for video platforms (YouTube, Vimeo, etc.) - optional
- feedparser for podcast RSS feeds - optional
- arXiv API for academic papers - optional
- oEmbed APIs for fallback metadata

All dependencies are optional and the module gracefully degrades without them.
"""
import json
import logging
import subprocess
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import requests

from btk.media_detector import MediaInfo, MediaDetector

logger = logging.getLogger(__name__)


@dataclass
class MediaMetadata:
    """Metadata extracted from a media URL."""

    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    author_name: Optional[str] = None
    author_url: Optional[str] = None
    published_at: Optional[datetime] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    tags: List[str] = field(default_factory=list)

    # Additional metadata that may be useful
    embed_url: Optional[str] = None
    original_url: Optional[str] = None


class YtDlpNotAvailableError(Exception):
    """Raised when yt-dlp is required but not available."""

    pass


class MediaFetchError(Exception):
    """Raised when metadata fetching fails."""

    pass


class MediaFetcher:
    """
    Fetch metadata for detected media URLs.

    This class provides methods to extract metadata from various media platforms.
    It uses yt-dlp when available for video platforms, with fallback to oEmbed APIs.

    Args:
        use_yt_dlp: Whether to try using yt-dlp for metadata extraction
        yt_dlp_path: Path to yt-dlp executable (default: auto-detect)
        timeout: Request timeout in seconds (default: 30)
    """

    # oEmbed endpoints for various platforms
    OEMBED_ENDPOINTS = {
        "youtube": "https://www.youtube.com/oembed",
        "vimeo": "https://vimeo.com/api/oembed.json",
        "spotify": "https://open.spotify.com/oembed",
        "soundcloud": "https://soundcloud.com/oembed",
        "twitter": "https://publish.twitter.com/oembed",
    }

    def __init__(
        self,
        use_yt_dlp: bool = True,
        yt_dlp_path: Optional[str] = None,
        timeout: int = 30,
    ):
        self.use_yt_dlp = use_yt_dlp
        self.timeout = timeout
        self._detector = MediaDetector()

        # Find yt-dlp path
        if yt_dlp_path:
            self.yt_dlp_path = yt_dlp_path
        else:
            self.yt_dlp_path = shutil.which("yt-dlp")

        self._yt_dlp_available = self.yt_dlp_path is not None and use_yt_dlp

    @property
    def yt_dlp_available(self) -> bool:
        """Check if yt-dlp is available."""
        return self._yt_dlp_available

    def fetch(self, url: str, media_info: Optional[MediaInfo] = None) -> MediaMetadata:
        """
        Fetch metadata for a URL.

        Args:
            url: The URL to fetch metadata for
            media_info: Pre-detected MediaInfo (optional, will detect if not provided)

        Returns:
            MediaMetadata with extracted information

        Raises:
            MediaFetchError: If metadata fetching fails
        """
        if media_info is None:
            media_info = self._detector.detect(url)

        if media_info is None:
            # Not a recognized media URL, return basic metadata
            return MediaMetadata(original_url=url)

        # Route to appropriate fetcher
        source = media_info.source

        # Try yt-dlp first for supported sources
        if self._yt_dlp_available and source in self._get_yt_dlp_sources():
            try:
                return self._fetch_with_yt_dlp(url, media_info)
            except Exception as e:
                logger.warning(f"yt-dlp failed for {url}: {e}, trying fallback")

        # Source-specific fetchers
        fetcher_map = {
            "youtube": self._fetch_youtube_oembed,
            "vimeo": self._fetch_vimeo_oembed,
            "spotify": self._fetch_spotify_oembed,
            "soundcloud": self._fetch_soundcloud_oembed,
            "arxiv": self._fetch_arxiv,
            "twitter": self._fetch_twitter_oembed,
            "github": self._fetch_github,
        }

        fetcher = fetcher_map.get(source)
        if fetcher:
            try:
                return fetcher(url, media_info)
            except Exception as e:
                logger.warning(f"Fetcher failed for {source}: {e}")

        # Return minimal metadata
        return MediaMetadata(original_url=url)

    def fetch_youtube(self, video_id: str) -> MediaMetadata:
        """
        Fetch metadata for a YouTube video.

        Args:
            video_id: YouTube video ID

        Returns:
            MediaMetadata with video information
        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        media_info = MediaInfo(
            source="youtube",
            media_id=video_id,
            media_type="video",
            url_type="video",
        )
        return self.fetch(url, media_info)

    def fetch_playlist(self, url: str) -> List[MediaMetadata]:
        """
        Fetch metadata for all items in a playlist.

        Requires yt-dlp for full playlist extraction.

        Args:
            url: Playlist URL (YouTube, Spotify, etc.)

        Returns:
            List of MediaMetadata for each item

        Raises:
            YtDlpNotAvailableError: If yt-dlp is not available
        """
        if not self._yt_dlp_available:
            raise YtDlpNotAvailableError(
                "yt-dlp is required for playlist extraction. "
                "Install with: pip install yt-dlp"
            )

        try:
            result = subprocess.run(
                [
                    self.yt_dlp_path,
                    "--flat-playlist",
                    "--dump-json",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout * 2,
            )

            items = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        data = json.loads(line)
                        items.append(self._parse_yt_dlp_output(data))
                    except json.JSONDecodeError:
                        continue

            return items

        except subprocess.TimeoutExpired:
            raise MediaFetchError(f"Timeout fetching playlist: {url}")
        except Exception as e:
            raise MediaFetchError(f"Failed to fetch playlist: {e}")

    def fetch_channel(self, url: str, limit: Optional[int] = None) -> List[MediaMetadata]:
        """
        Fetch metadata for videos from a channel.

        Requires yt-dlp for channel extraction.

        Args:
            url: Channel URL
            limit: Maximum number of videos to fetch (default: all)

        Returns:
            List of MediaMetadata for each video

        Raises:
            YtDlpNotAvailableError: If yt-dlp is not available
        """
        if not self._yt_dlp_available:
            raise YtDlpNotAvailableError(
                "yt-dlp is required for channel extraction. "
                "Install with: pip install yt-dlp"
            )

        cmd = [
            self.yt_dlp_path,
            "--flat-playlist",
            "--dump-json",
        ]

        if limit:
            cmd.extend(["--playlist-end", str(limit)])

        cmd.append(url)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout * 3,
            )

            items = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        data = json.loads(line)
                        items.append(self._parse_yt_dlp_output(data))
                    except json.JSONDecodeError:
                        continue

            return items

        except subprocess.TimeoutExpired:
            raise MediaFetchError(f"Timeout fetching channel: {url}")
        except Exception as e:
            raise MediaFetchError(f"Failed to fetch channel: {e}")

    def fetch_podcast_rss(self, feed_url: str, limit: Optional[int] = None) -> List[MediaMetadata]:
        """
        Fetch metadata from a podcast RSS feed.

        Args:
            feed_url: RSS feed URL
            limit: Maximum number of episodes to fetch

        Returns:
            List of MediaMetadata for each episode
        """
        try:
            import feedparser
        except ImportError:
            raise MediaFetchError(
                "feedparser is required for podcast parsing. "
                "Install with: pip install feedparser"
            )

        try:
            feed = feedparser.parse(feed_url)

            if feed.bozo and not feed.entries:
                raise MediaFetchError(f"Invalid RSS feed: {feed.bozo_exception}")

            podcast_title = feed.feed.get("title", "Unknown Podcast")
            podcast_author = feed.feed.get("author", feed.feed.get("itunes_author", ""))
            podcast_image = None

            # Try to get podcast image
            if hasattr(feed.feed, "image") and feed.feed.image:
                podcast_image = feed.feed.image.get("href")
            elif hasattr(feed.feed, "itunes_image"):
                podcast_image = feed.feed.itunes_image.get("href")

            episodes = []
            entries = feed.entries[:limit] if limit else feed.entries

            for entry in entries:
                # Parse publication date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass

                # Get episode URL
                episode_url = entry.get("link", "")
                if hasattr(entry, "enclosures") and entry.enclosures:
                    episode_url = entry.enclosures[0].get("href", episode_url)

                # Get thumbnail
                thumbnail = podcast_image
                if hasattr(entry, "itunes_image"):
                    thumbnail = entry.itunes_image.get("href", thumbnail)

                episodes.append(
                    MediaMetadata(
                        title=entry.get("title", ""),
                        description=entry.get("summary", entry.get("description", "")),
                        thumbnail_url=thumbnail,
                        author_name=podcast_author or podcast_title,
                        published_at=published,
                        original_url=episode_url,
                    )
                )

            return episodes

        except ImportError:
            raise
        except Exception as e:
            raise MediaFetchError(f"Failed to parse podcast feed: {e}")

    def _fetch_with_yt_dlp(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch metadata using yt-dlp."""
        try:
            result = subprocess.run(
                [
                    self.yt_dlp_path,
                    "--dump-json",
                    "--no-download",
                    "--no-warnings",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                raise MediaFetchError(f"yt-dlp error: {result.stderr}")

            data = json.loads(result.stdout)
            return self._parse_yt_dlp_output(data)

        except subprocess.TimeoutExpired:
            raise MediaFetchError(f"yt-dlp timeout for {url}")
        except json.JSONDecodeError as e:
            raise MediaFetchError(f"Invalid JSON from yt-dlp: {e}")

    def _parse_yt_dlp_output(self, data: Dict[str, Any]) -> MediaMetadata:
        """Parse yt-dlp JSON output into MediaMetadata."""
        # Parse upload date
        published = None
        upload_date = data.get("upload_date")
        if upload_date and len(upload_date) == 8:
            try:
                published = datetime.strptime(upload_date, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        return MediaMetadata(
            title=data.get("title"),
            description=data.get("description"),
            thumbnail_url=data.get("thumbnail"),
            author_name=data.get("uploader") or data.get("channel"),
            author_url=data.get("uploader_url") or data.get("channel_url"),
            published_at=published,
            view_count=data.get("view_count"),
            like_count=data.get("like_count"),
            tags=data.get("tags", []),
            original_url=data.get("webpage_url"),
        )

    def _fetch_youtube_oembed(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch YouTube metadata via oEmbed."""
        return self._fetch_oembed("youtube", url)

    def _fetch_vimeo_oembed(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch Vimeo metadata via oEmbed."""
        return self._fetch_oembed("vimeo", url)

    def _fetch_spotify_oembed(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch Spotify metadata via oEmbed."""
        return self._fetch_oembed("spotify", url)

    def _fetch_soundcloud_oembed(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch SoundCloud metadata via oEmbed."""
        return self._fetch_oembed("soundcloud", url)

    def _fetch_twitter_oembed(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch Twitter metadata via oEmbed."""
        return self._fetch_oembed("twitter", url)

    def _fetch_oembed(self, source: str, url: str) -> MediaMetadata:
        """Generic oEmbed fetcher."""
        endpoint = self.OEMBED_ENDPOINTS.get(source)
        if not endpoint:
            return MediaMetadata(original_url=url)

        try:
            response = requests.get(
                endpoint,
                params={"url": url, "format": "json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            return MediaMetadata(
                title=data.get("title"),
                author_name=data.get("author_name"),
                author_url=data.get("author_url"),
                thumbnail_url=data.get("thumbnail_url"),
                original_url=url,
            )

        except Exception as e:
            logger.warning(f"oEmbed fetch failed for {source}: {e}")
            return MediaMetadata(original_url=url)

    def _fetch_arxiv(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch arXiv paper metadata."""
        paper_id = media_info.media_id

        try:
            # Try using the arxiv library if available
            import arxiv

            search = arxiv.Search(id_list=[paper_id])
            paper = next(search.results(), None)

            if paper:
                return MediaMetadata(
                    title=paper.title,
                    description=paper.summary,
                    author_name=", ".join(a.name for a in paper.authors[:3]),
                    published_at=paper.published.replace(tzinfo=timezone.utc) if paper.published else None,
                    tags=[cat for cat in paper.categories],
                    original_url=paper.entry_id,
                )

        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"arxiv library fetch failed: {e}")

        # Fallback to API
        try:
            api_url = f"http://export.arxiv.org/api/query?id_list={paper_id}"
            response = requests.get(api_url, timeout=self.timeout)
            response.raise_for_status()

            # Basic XML parsing (avoid adding lxml dependency)
            import xml.etree.ElementTree as ET

            root = ET.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            entry = root.find("atom:entry", ns)
            if entry is not None:
                title = entry.findtext("atom:title", "", ns).strip()
                summary = entry.findtext("atom:summary", "", ns).strip()
                published = entry.findtext("atom:published", "", ns)

                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.findtext("atom:name", "", ns)
                    if name:
                        authors.append(name)

                published_dt = None
                if published:
                    try:
                        published_dt = datetime.fromisoformat(
                            published.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                return MediaMetadata(
                    title=title,
                    description=summary,
                    author_name=", ".join(authors[:3]),
                    published_at=published_dt,
                    original_url=url,
                )

        except Exception as e:
            logger.warning(f"arXiv API fetch failed: {e}")

        return MediaMetadata(original_url=url)

    def _fetch_github(self, url: str, media_info: MediaInfo) -> MediaMetadata:
        """Fetch GitHub repository metadata."""
        repo_path = media_info.media_id

        try:
            api_url = f"https://api.github.com/repos/{repo_path}"
            response = requests.get(
                api_url,
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            published = None
            if data.get("created_at"):
                try:
                    published = datetime.fromisoformat(
                        data["created_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            return MediaMetadata(
                title=data.get("full_name"),
                description=data.get("description"),
                author_name=data.get("owner", {}).get("login"),
                author_url=data.get("owner", {}).get("html_url"),
                published_at=published,
                view_count=data.get("stargazers_count"),  # Use stars as view count
                tags=data.get("topics", []),
                original_url=data.get("html_url"),
            )

        except Exception as e:
            logger.warning(f"GitHub API fetch failed: {e}")
            return MediaMetadata(original_url=url)

    def _get_yt_dlp_sources(self) -> set:
        """Get sources supported by yt-dlp."""
        return {
            "youtube",
            "vimeo",
            "twitch",
            "dailymotion",
            "soundcloud",
            "bandcamp",
            "twitter",
        }

# Convenience function
def fetch_media_metadata(url: str) -> MediaMetadata:
    """
    Fetch media metadata for a URL.

    This is a convenience function that creates a MediaFetcher instance.
    For batch operations, create a MediaFetcher instance directly.

    Args:
        url: The URL to fetch metadata for

    Returns:
        MediaMetadata with extracted information
    """
    return MediaFetcher().fetch(url)
