"""
Clean utilities for BTK bookmark management.

This module provides helper functions that work with the modern database-first
architecture, without directory-based assumptions or JSON compatibility layers.
"""
import logging
import hashlib
import os
from typing import List, Optional, Tuple
from urllib.parse import urlparse
import requests

from btk.models import Bookmark

# Configure logging
logger = logging.getLogger(__name__)


def ensure_dir(path: str) -> None:
    """
    Ensure a directory exists (backward compatibility function).

    Args:
        path: Directory path to create

    Note:
        This function is kept for backward compatibility.
        New code should use pathlib.Path.mkdir(parents=True, exist_ok=True).
    """
    os.makedirs(path, exist_ok=True)


def generate_unique_id(url: Optional[str] = None, title: Optional[str] = None) -> str:
    """
    Generate a unique 8-character ID for a bookmark.

    Args:
        url: Optional URL for the bookmark
        title: Optional title for the bookmark

    Returns:
        8-character hash string
    """
    if url is None and title is None:
        import uuid
        unique_string = str(uuid.uuid4())
    else:
        unique_string = f"{url or ''}{title or ''}"

    hash_val = hashlib.sha256(unique_string.encode('utf-8')).hexdigest()
    return hash_val[:8]


def extract_domain(url: str) -> str:
    """
    Extract domain from a URL.

    Args:
        url: The URL to parse

    Returns:
        Domain name (e.g., 'example.com')
    """
    parsed = urlparse(url)
    return parsed.netloc


def download_favicon(url: str) -> Optional[Tuple[bytes, str]]:
    """
    Download favicon for a URL.

    Args:
        url: Website URL

    Returns:
        Tuple of (favicon_data, mime_type) or None if failed
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc

        # Try common favicon locations
        favicon_urls = [
            f"{parsed.scheme}://{domain}/favicon.ico",
            f"{parsed.scheme}://{domain}/favicon.png",
            f"{parsed.scheme}://{domain}/apple-touch-icon.png",
        ]

        for favicon_url in favicon_urls:
            try:
                response = requests.get(favicon_url, timeout=5)
                if response.status_code == 200 and len(response.content) > 0:
                    # Determine MIME type
                    content_type = response.headers.get('content-type', '')
                    if not content_type:
                        # Guess from URL extension
                        if favicon_url.endswith('.png'):
                            content_type = 'image/png'
                        elif favicon_url.endswith('.ico'):
                            content_type = 'image/x-icon'
                        else:
                            content_type = 'application/octet-stream'

                    return (response.content, content_type)
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"Failed to download favicon for {url}: {e}")

    return None


def filter_by_tags(bookmarks: List[Bookmark], tag_prefix: str) -> List[Bookmark]:
    """
    Filter bookmarks by tag prefix.

    Args:
        bookmarks: List of Bookmark objects
        tag_prefix: Tag prefix to match

    Returns:
        Filtered list of Bookmark objects
    """
    return [b for b in bookmarks if any(tag.name.startswith(tag_prefix) for tag in b.tags)]


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent storage and comparison.

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    # Remove trailing slashes
    url = url.rstrip('/')

    # Remove common tracking parameters
    parsed = urlparse(url)
    # You could filter query parameters here if needed

    return url


def validate_url(url: str) -> bool:
    """
    Validate that a string is a proper URL.

    Args:
        url: URL to validate

    Returns:
        True if valid URL
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc]) and result.scheme in ('http', 'https')
    except Exception:
        return False