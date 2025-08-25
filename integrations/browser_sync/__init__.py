"""
Browser bookmark synchronization for BTK.

This integration enables two-way synchronization between BTK and browser bookmarks,
supporting Chrome, Firefox, Edge, and Safari bookmark formats.
"""

from .sync import BrowserSync, register_plugins

__all__ = ['BrowserSync', 'register_plugins']