"""
Semantic search for BTK.

This integration provides vector/embedding-based semantic search using
sentence-transformers, enabling finding bookmarks by meaning rather than
just keyword matching.
"""

from .search import SemanticSearchEngine, register_plugins

__all__ = ['SemanticSearchEngine', 'register_plugins']