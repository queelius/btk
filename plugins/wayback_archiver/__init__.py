"""
Wayback Machine archiver for BTK.

This integration automatically submits bookmarks to the Internet Archive's
Wayback Machine, ensuring they're preserved even if the original site goes down.
"""

from .archiver import WaybackArchiver, register_plugins

__all__ = ['WaybackArchiver', 'register_plugins']