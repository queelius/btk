"""
MiniWeb - Static site generator for bookmarks with network-aware navigation.

Export bookmarks as an interactive static website where you can:
- Navigate based on graph distance (hops between pages)
- Navigate based on semantic similarity (content-based)
- View pages embedded in a larger context with metadata and graph visualization
- Zoom in/out between graph overview and page content
"""

from .generator import MiniWebGenerator, NavigationType
from .graph import BookmarkGraph

__version__ = "1.0.0"
__all__ = ['MiniWebGenerator', 'BookmarkGraph', 'NavigationType']
