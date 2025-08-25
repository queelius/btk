"""
Social media metadata extractor for BTK.

This integration extracts Open Graph and Twitter Card metadata
from web pages to enrich bookmarks with better titles, descriptions,
and preview images.
"""

from .extractor import SocialMetadataExtractor, register_plugins

__all__ = ['SocialMetadataExtractor', 'register_plugins']