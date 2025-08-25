"""
Advanced duplicate finder for BTK bookmarks.

This integration provides sophisticated duplicate detection including:
- URL normalization and fuzzy matching
- Title similarity detection
- Content-based deduplication
"""

from .finder import DuplicateFinder, register_plugins

__all__ = ['DuplicateFinder', 'register_plugins']