"""
Readability content extractor for BTK.

This integration extracts clean, readable content from web pages using
Mozilla's Readability algorithm, making bookmarks more searchable and
providing better context for tagging and analysis.
"""

from .extractor import ReadabilityExtractor, register_plugins

__all__ = ['ReadabilityExtractor', 'register_plugins']