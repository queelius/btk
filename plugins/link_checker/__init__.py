"""
Link checker for BTK.

This integration periodically checks bookmarks for dead links, redirects,
and other issues, helping maintain a healthy bookmark collection.
"""

from .checker import LinkChecker, register_plugins

__all__ = ['LinkChecker', 'register_plugins']