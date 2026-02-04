"""
Media Preservation for BTK - Long Echo Implementation

This module provides media-specific preservation to ensure useful representations
of bookmarked content survive even when original sources disappear.

Philosophy:
- Not full archival (that's ArchiveBox/Wayback Machine)
- Useful representations for discovery, understanding, and recovery
- Graceful degradation: content remains accessible at multiple levels

Preservers:
- YouTubePreserver: thumbnails + transcripts
- PDFPreserver: extracted text
- ImagePreserver: download and optimize images
- GenericPreserver: fallback for standard web content
"""

import re
import io
import logging
import requests
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

from .plugins import MediaPreserver, PreservationResult, PluginMetadata

logger = logging.getLogger(__name__)

# Request settings
DEFAULT_TIMEOUT = 30
USER_AGENT = 'Mozilla/5.0 (compatible; BTK/1.0; Long Echo Preservation)'


# =============================================================================
# YouTube Preserver
# =============================================================================

class YouTubePreserver(MediaPreserver):
    """
    Preserve YouTube videos with thumbnails and transcripts.

    For Long Echo, we capture:
    - Thumbnail image (visual recognition)
    - Transcript text (actual content/knowledge)
    - Video metadata (discovery)

    Requires: pip install youtube-transcript-api (optional, for transcripts)
    """

    service_name = "youtube"

    def __init__(self, fetch_thumbnail: bool = True, fetch_transcript: bool = True):
        self.fetch_thumbnail = fetch_thumbnail
        self.fetch_transcript = fetch_transcript
        self._transcript_api = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="youtube_preserver",
            version="1.0.0",
            author="BTK",
            description="Preserve YouTube videos with thumbnails and transcripts",
            priority=80,
            dependencies=["youtube-transcript-api"],
        )

    @property
    def supported_domains(self) -> List[str]:
        return ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com']

    def can_preserve(self, url: str) -> bool:
        """Check if URL is a YouTube video."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        if domain not in ['youtube.com', 'youtu.be', 'm.youtube.com']:
            return False
        # Must be a video, not a channel or playlist
        video_id = self._extract_video_id(url)
        return video_id is not None

    def preserve(self, url: str, **kwargs) -> PreservationResult:
        """Preserve YouTube video content."""
        video_id = self._extract_video_id(url)
        if not video_id:
            return PreservationResult(
                success=False,
                url=url,
                preservation_type='youtube',
                error_message="Could not extract video ID"
            )

        result = PreservationResult(
            success=True,
            url=url,
            preservation_type='youtube',
            extra={'video_id': video_id}
        )

        # Fetch thumbnail
        if self.fetch_thumbnail:
            try:
                thumb_data, thumb_mime = self._fetch_thumbnail(video_id)
                result.thumbnail_data = thumb_data
                result.thumbnail_mime = thumb_mime
            except Exception as e:
                logger.warning(f"Failed to fetch thumbnail for {video_id}: {e}")

        # Fetch transcript
        if self.fetch_transcript:
            try:
                transcript = self._fetch_transcript(video_id)
                if transcript:
                    result.transcript_text = transcript
                    result.word_count = len(transcript.split())
            except Exception as e:
                logger.warning(f"Failed to fetch transcript for {video_id}: {e}")

        return result

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL."""
        patterns = [
            r'(?:v=|/)([0-9A-Za-z_-]{11})(?:\?|&|$|#)',
            r'youtu\.be/([0-9A-Za-z_-]{11})',
            r'embed/([0-9A-Za-z_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _fetch_thumbnail(self, video_id: str) -> Tuple[bytes, str]:
        """Fetch the best available thumbnail."""
        # Try quality levels from best to worst
        quality_urls = [
            f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/sddefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/default.jpg",
        ]

        for thumb_url in quality_urls:
            try:
                response = requests.get(
                    thumb_url,
                    timeout=DEFAULT_TIMEOUT,
                    headers={'User-Agent': USER_AGENT}
                )
                if response.status_code == 200 and len(response.content) > 1000:
                    # Valid image (not the "no thumbnail" placeholder)
                    return response.content, 'image/jpeg'
            except requests.RequestException:
                continue

        raise ValueError("No thumbnail available")

    def _fetch_transcript(self, video_id: str) -> Optional[str]:
        """Fetch video transcript using youtube-transcript-api."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api._errors import (
                TranscriptsDisabled,
                NoTranscriptFound,
                VideoUnavailable
            )
        except ImportError:
            logger.debug("youtube-transcript-api not installed, skipping transcript")
            return None

        try:
            # Create API instance (required in v1.2+)
            ytt_api = YouTubeTranscriptApi()

            # Try to get transcript, preferring manual captions
            transcript_list = ytt_api.list(video_id)

            # Prefer manual transcripts in English
            transcript = None
            try:
                transcript = transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-GB'])
            except Exception:
                pass

            # Fall back to auto-generated
            if transcript is None:
                try:
                    transcript = transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB'])
                except Exception:
                    pass

            # Try any available transcript
            if transcript is None:
                try:
                    transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
                except Exception:
                    # Get first available and translate
                    for t in transcript_list:
                        try:
                            transcript = t.translate('en')
                            break
                        except Exception:
                            continue

            if transcript:
                # Fetch and join transcript segments
                segments = transcript.fetch()
                text_parts = [segment.text for segment in segments]
                return ' '.join(text_parts)

        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            logger.debug(f"Transcript not available for {video_id}: {e}")
        except Exception as e:
            logger.warning(f"Error fetching transcript for {video_id}: {e}")

        return None


# =============================================================================
# PDF Preserver
# =============================================================================

class PDFPreserver(MediaPreserver):
    """
    Preserve PDF documents by extracting text.

    For Long Echo, we capture:
    - Extracted text content (searchable, readable)
    - Page count and metadata

    Requires: pip install pypdf (optional)
    """

    def __init__(self, max_pages: int = 100, max_size_mb: int = 50):
        self.max_pages = max_pages
        self.max_size_bytes = max_size_mb * 1024 * 1024

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="pdf_preserver",
            version="1.0.0",
            author="BTK",
            description="Preserve PDFs by extracting text content",
            priority=70,
            dependencies=["pypdf"],
        )

    @property
    def supported_domains(self) -> List[str]:
        # PDFs can be on any domain
        return ['*']

    def can_preserve(self, url: str) -> bool:
        """Check if URL points to a PDF."""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        # Check file extension
        if path_lower.endswith('.pdf'):
            return True
        # Check query parameters (some systems use ?format=pdf)
        if 'pdf' in parsed.query.lower():
            return True
        return False

    def preserve(self, url: str, **kwargs) -> PreservationResult:
        """Download and extract text from PDF."""
        try:
            from pypdf import PdfReader
        except ImportError:
            return PreservationResult(
                success=False,
                url=url,
                preservation_type='pdf',
                error_message="pypdf not installed"
            )

        try:
            # Download PDF
            response = requests.get(
                url,
                timeout=DEFAULT_TIMEOUT * 2,  # PDFs can be large
                headers={'User-Agent': USER_AGENT},
                stream=True
            )
            response.raise_for_status()

            # Check size
            content_length = int(response.headers.get('content-length', 0))
            if content_length > self.max_size_bytes:
                return PreservationResult(
                    success=False,
                    url=url,
                    preservation_type='pdf',
                    error_message=f"PDF too large: {content_length / 1024 / 1024:.1f} MB"
                )

            # Read PDF
            pdf_bytes = io.BytesIO(response.content)
            reader = PdfReader(pdf_bytes)

            # Extract text from pages
            text_parts = []
            page_count = min(len(reader.pages), self.max_pages)

            for i in range(page_count):
                try:
                    page = reader.pages[i]
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                except Exception as e:
                    logger.debug(f"Failed to extract text from page {i}: {e}")

            extracted_text = '\n\n'.join(text_parts)

            return PreservationResult(
                success=True,
                url=url,
                preservation_type='pdf',
                extracted_text=extracted_text,
                word_count=len(extracted_text.split()) if extracted_text else 0,
                extra={
                    'page_count': len(reader.pages),
                    'pages_extracted': page_count,
                    'metadata': dict(reader.metadata) if reader.metadata else {},
                }
            )

        except requests.RequestException as e:
            return PreservationResult(
                success=False,
                url=url,
                preservation_type='pdf',
                error_message=f"Download failed: {e}"
            )
        except Exception as e:
            return PreservationResult(
                success=False,
                url=url,
                preservation_type='pdf',
                error_message=f"PDF extraction failed: {e}"
            )


# =============================================================================
# Image Preserver
# =============================================================================

class ImagePreserver(MediaPreserver):
    """
    Preserve images by downloading and optionally resizing.

    For Long Echo, we capture:
    - Image data (optionally resized/compressed)
    - Image metadata
    """

    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}

    def __init__(self, max_size_bytes: int = 5 * 1024 * 1024, resize_max_dim: int = 1920):
        self.max_size_bytes = max_size_bytes
        self.resize_max_dim = resize_max_dim

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="image_preserver",
            version="1.0.0",
            author="BTK",
            description="Preserve images by downloading and optionally resizing",
            priority=60,
        )

    @property
    def supported_domains(self) -> List[str]:
        return ['*']

    def can_preserve(self, url: str) -> bool:
        """Check if URL points to an image."""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        return any(path_lower.endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)

    def preserve(self, url: str, **kwargs) -> PreservationResult:
        """Download and preserve image."""
        try:
            response = requests.get(
                url,
                timeout=DEFAULT_TIMEOUT,
                headers={'User-Agent': USER_AGENT},
                stream=True
            )
            response.raise_for_status()

            content_type = response.headers.get('content-type', 'image/jpeg')

            # Check size
            content = response.content
            if len(content) > self.max_size_bytes:
                # Try to resize if PIL is available
                try:
                    content, content_type = self._resize_image(content)
                except ImportError:
                    return PreservationResult(
                        success=False,
                        url=url,
                        preservation_type='image',
                        error_message="Image too large and PIL not installed for resizing"
                    )

            return PreservationResult(
                success=True,
                url=url,
                preservation_type='image',
                thumbnail_data=content,
                thumbnail_mime=content_type,
                extra={'original_size': len(response.content)}
            )

        except requests.RequestException as e:
            return PreservationResult(
                success=False,
                url=url,
                preservation_type='image',
                error_message=f"Download failed: {e}"
            )

    def _resize_image(self, image_data: bytes) -> Tuple[bytes, str]:
        """Resize image to fit within max dimensions."""
        from PIL import Image

        img = Image.open(io.BytesIO(image_data))

        # Calculate new size maintaining aspect ratio
        width, height = img.size
        if width > self.resize_max_dim or height > self.resize_max_dim:
            ratio = min(self.resize_max_dim / width, self.resize_max_dim / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Save as JPEG for compression
        output = io.BytesIO()
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        img.save(output, format='JPEG', quality=85, optimize=True)
        return output.getvalue(), 'image/jpeg'


# =============================================================================
# Preservation Manager
# =============================================================================

class PreservationManager:
    """
    Orchestrates media preservation across multiple preservers.

    Usage:
        manager = PreservationManager()
        result = manager.preserve(url)
        if result.success:
            # Store result.thumbnail_data, result.transcript_text, etc.
    """

    def __init__(self):
        self.preservers: List[MediaPreserver] = []
        self._register_default_preservers()

    def _register_default_preservers(self):
        """Register built-in preservers."""
        self.preservers = [
            YouTubePreserver(),
            PDFPreserver(),
            ImagePreserver(),
        ]
        # Sort by priority
        self.preservers.sort(key=lambda p: p.metadata.priority, reverse=True)

    def register_preserver(self, preserver: MediaPreserver):
        """Register a custom preserver."""
        self.preservers.append(preserver)
        self.preservers.sort(key=lambda p: p.metadata.priority, reverse=True)

    def can_preserve(self, url: str) -> bool:
        """Check if any preserver can handle this URL."""
        return any(p.can_preserve(url) for p in self.preservers)

    def get_preserver_for_url(self, url: str) -> Optional[MediaPreserver]:
        """Get the best preserver for a URL."""
        for preserver in self.preservers:
            if preserver.can_preserve(url):
                return preserver
        return None

    def preserve(self, url: str, **kwargs) -> Optional[PreservationResult]:
        """
        Preserve content from URL using the appropriate preserver.

        Returns:
            PreservationResult or None if no preserver can handle the URL
        """
        preserver = self.get_preserver_for_url(url)
        if preserver is None:
            return None

        logger.info(f"Preserving {url} with {preserver.metadata.name}")
        return preserver.preserve(url, **kwargs)

    def list_preservers(self) -> List[Dict[str, Any]]:
        """List all registered preservers."""
        return [
            {
                'name': p.metadata.name,
                'description': p.metadata.description,
                'priority': p.metadata.priority,
                'domains': p.supported_domains,
            }
            for p in self.preservers
        ]


# =============================================================================
# Database Storage
# =============================================================================

def store_preservation_result(db, bookmark_id: int, result: PreservationResult) -> bool:
    """
    Store preservation result in the database.

    Updates the content_cache table with preserved content using the
    Long Echo preservation fields.
    """
    from datetime import datetime, timezone
    from .models import ContentCache

    try:
        with db.session() as session:
            # Get or create content cache entry
            cache = session.query(ContentCache).filter_by(bookmark_id=bookmark_id).first()

            if cache is None:
                cache = ContentCache(bookmark_id=bookmark_id)
                session.add(cache)

            # Store thumbnail data directly in dedicated fields
            if result.thumbnail_data:
                cache.thumbnail_data = result.thumbnail_data
                cache.thumbnail_mime = result.thumbnail_mime

                # Try to get image dimensions
                if result.thumbnail_mime and result.thumbnail_mime.startswith('image/'):
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(result.thumbnail_data))
                        cache.thumbnail_width = img.width
                        cache.thumbnail_height = img.height
                    except Exception:
                        pass  # Dimensions are optional

            # Store transcript in dedicated field
            if result.transcript_text:
                cache.transcript_text = result.transcript_text
                # Also add to markdown for FTS indexing
                transcript_md = f"## Transcript\n\n{result.transcript_text}"
                if cache.markdown_content:
                    cache.markdown_content += f"\n\n---\n\n{transcript_md}"
                else:
                    cache.markdown_content = transcript_md

            # Store extracted text (PDF, etc.) in dedicated field
            if result.extracted_text:
                cache.extracted_text = result.extracted_text
                # Also add to markdown for FTS indexing
                text_md = f"## Extracted Content\n\n{result.extracted_text}"
                if cache.markdown_content:
                    cache.markdown_content += f"\n\n---\n\n{text_md}"
                else:
                    cache.markdown_content = text_md

            # Store preservation metadata
            cache.preservation_type = result.preservation_type
            cache.preserved_at = datetime.now(timezone.utc)

            session.commit()
            return True

    except Exception as e:
        logger.error(f"Failed to store preservation result: {e}")
        return False


def get_preservation_status(db, bookmark_id: int) -> Optional[Dict[str, Any]]:
    """
    Get preservation status for a bookmark.

    Returns:
        Dict with preservation info or None if no preservation exists
    """
    from .models import ContentCache

    try:
        with db.session() as session:
            cache = session.query(ContentCache).filter_by(bookmark_id=bookmark_id).first()

            if cache is None or cache.preservation_type is None:
                return None

            return {
                'bookmark_id': bookmark_id,
                'preservation_type': cache.preservation_type,
                'preserved_at': cache.preserved_at.isoformat() if cache.preserved_at else None,
                'has_thumbnail': cache.thumbnail_data is not None,
                'thumbnail_size': len(cache.thumbnail_data) if cache.thumbnail_data else 0,
                'thumbnail_dimensions': (cache.thumbnail_width, cache.thumbnail_height)
                    if cache.thumbnail_width else None,
                'has_transcript': cache.transcript_text is not None,
                'transcript_words': len(cache.transcript_text.split()) if cache.transcript_text else 0,
                'has_extracted_text': cache.extracted_text is not None,
                'extracted_text_words': len(cache.extracted_text.split()) if cache.extracted_text else 0,
            }

    except Exception as e:
        logger.error(f"Failed to get preservation status: {e}")
        return None


def get_preserved_thumbnail(db, bookmark_id: int) -> Optional[Tuple[bytes, str]]:
    """
    Get preserved thumbnail for a bookmark.

    Returns:
        Tuple of (data, mime_type) or None
    """
    from .models import ContentCache

    try:
        with db.session() as session:
            cache = session.query(ContentCache).filter_by(bookmark_id=bookmark_id).first()
            if cache and cache.thumbnail_data:
                return (cache.thumbnail_data, cache.thumbnail_mime or 'image/jpeg')
            return None
    except Exception as e:
        logger.error(f"Failed to get thumbnail: {e}")
        return None


def get_preserved_transcript(db, bookmark_id: int) -> Optional[str]:
    """Get preserved transcript for a bookmark."""
    from .models import ContentCache

    try:
        with db.session() as session:
            cache = session.query(ContentCache).filter_by(bookmark_id=bookmark_id).first()
            return cache.transcript_text if cache else None
    except Exception as e:
        logger.error(f"Failed to get transcript: {e}")
        return None


def get_preserved_text(db, bookmark_id: int) -> Optional[str]:
    """Get preserved extracted text for a bookmark."""
    from .models import ContentCache

    try:
        with db.session() as session:
            cache = session.query(ContentCache).filter_by(bookmark_id=bookmark_id).first()
            return cache.extracted_text if cache else None
    except Exception as e:
        logger.error(f"Failed to get extracted text: {e}")
        return None


# =============================================================================
# Website Screenshot Preserver
# =============================================================================

class WebsiteScreenshotPreserver(MediaPreserver):
    """
    Capture screenshots of web pages as thumbnails.

    For Long Echo, this provides visual preservation of web pages.
    Requires a headless browser (playwright or selenium).

    This is a placeholder for future implementation - it requires
    additional dependencies and setup.
    """

    def __init__(self, width: int = 1280, height: int = 720, timeout: int = 30):
        self.width = width
        self.height = height
        self.timeout = timeout
        self._browser = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="website_screenshot",
            version="1.0.0",
            author="BTK",
            description="Capture screenshots of web pages",
            priority=30,  # Lower priority - use as fallback
            dependencies=["playwright"],
        )

    @property
    def supported_domains(self) -> List[str]:
        return ['*']

    def can_preserve(self, url: str) -> bool:
        """Can preserve any HTTP(S) URL."""
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https')

    def preserve(self, url: str, **kwargs) -> PreservationResult:
        """
        Capture screenshot of web page.

        Note: This is a placeholder. Full implementation requires
        playwright or selenium to be installed and configured.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return PreservationResult(
                success=False,
                url=url,
                preservation_type='screenshot',
                error_message="playwright not installed (pip install playwright && playwright install chromium)"
            )

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': self.width, 'height': self.height})
                page.goto(url, timeout=self.timeout * 1000)
                page.wait_for_load_state('networkidle', timeout=self.timeout * 1000)

                screenshot = page.screenshot(type='jpeg', quality=85)
                browser.close()

                return PreservationResult(
                    success=True,
                    url=url,
                    preservation_type='screenshot',
                    thumbnail_data=screenshot,
                    thumbnail_mime='image/jpeg',
                    extra={'width': self.width, 'height': self.height}
                )

        except Exception as e:
            return PreservationResult(
                success=False,
                url=url,
                preservation_type='screenshot',
                error_message=f"Screenshot failed: {e}"
            )


# =============================================================================
# CLI Integration Helpers
# =============================================================================

def preserve_bookmark(db, bookmark_id: int, manager: Optional[PreservationManager] = None) -> Optional[PreservationResult]:
    """
    Preserve content for a single bookmark.

    Args:
        db: Database instance
        bookmark_id: ID of bookmark to preserve
        manager: PreservationManager instance (creates default if None)

    Returns:
        PreservationResult or None
    """
    if manager is None:
        manager = PreservationManager()

    bookmark = db.get(bookmark_id)
    if bookmark is None:
        logger.warning(f"Bookmark {bookmark_id} not found")
        return None

    url = bookmark.url
    if not manager.can_preserve(url):
        logger.debug(f"No preserver available for {url}")
        return None

    result = manager.preserve(url)
    if result and result.success:
        store_preservation_result(db, bookmark_id, result)

    return result


def preserve_bookmarks_batch(
    db,
    bookmark_ids: Optional[List[int]] = None,
    limit: Optional[int] = None,
    media_types: Optional[List[str]] = None,
    manager: Optional[PreservationManager] = None,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Preserve content for multiple bookmarks.

    Args:
        db: Database instance
        bookmark_ids: Specific IDs to preserve (None = all preservable)
        limit: Maximum number to process
        media_types: Filter by media type (e.g., ['video', 'pdf'])
        manager: PreservationManager instance
        progress_callback: Called with (current, total, bookmark) for progress

    Returns:
        Summary dict with counts and results
    """
    if manager is None:
        manager = PreservationManager()

    from .models import Bookmark

    # Get bookmarks to preserve
    with db.session() as session:
        query = session.query(Bookmark)

        if bookmark_ids:
            query = query.filter(Bookmark.id.in_(bookmark_ids))

        if media_types:
            query = query.filter(Bookmark.media_type.in_(media_types))

        bookmarks = query.all()

    # Filter to preservable URLs
    preservable = [b for b in bookmarks if manager.can_preserve(b.url)]

    if limit:
        preservable = preservable[:limit]

    # Process
    results = {
        'total': len(preservable),
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'by_type': {},
    }

    for i, bookmark in enumerate(preservable):
        if progress_callback:
            progress_callback(i + 1, len(preservable), bookmark)

        try:
            result = manager.preserve(bookmark.url)
            if result and result.success:
                store_preservation_result(db, bookmark.id, result)
                results['success'] += 1

                # Track by type
                ptype = result.preservation_type
                results['by_type'][ptype] = results['by_type'].get(ptype, 0) + 1
            else:
                results['failed'] += 1
        except Exception as e:
            logger.error(f"Failed to preserve bookmark {bookmark.id}: {e}")
            results['failed'] += 1

    return results
