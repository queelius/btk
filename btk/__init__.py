"""
BTK - Bookmark Toolkit

A modern, composable bookmark management system built on SQLAlchemy.

Design Principles:
- Single database file (btk.db) instead of directory-based libraries
- Clean, minimal API following Unix philosophy
- Database-first architecture with no JSON legacy code
- Support for SQLite, PostgreSQL, MySQL via connection strings
- Composable operations that pipe well together

Example Usage:
    >>> from btk import Database, get_config
    >>> db = Database()  # Uses config default
    >>> db.add("https://example.com", title="Example", tags=["demo"])
    >>> bookmarks = db.list(limit=10)
    >>> db.search("python")
"""

__version__ = "0.7.5"
__author__ = "BTK Contributors"

# Core database API
from btk.db import Database, get_db

# Configuration
from btk.config import BtkConfig, get_config, init_config

# Models
from btk.models import Bookmark, Tag, BookmarkHealth, Collection

# Import/Export
from btk.importers import import_file
from btk.exporters import export_file

# Utilities
from btk.utils import (
    generate_unique_id,
    extract_domain,
    download_favicon,
    filter_by_tags,
    normalize_url,
    validate_url,
)

__all__ = [
    # Database
    "Database",
    "get_db",
    # Config
    "BtkConfig",
    "get_config",
    "init_config",
    # Models
    "Bookmark",
    "Tag",
    "BookmarkHealth",
    "Collection",
    # Import/Export
    "import_file",
    "export_file",
    # Utilities
    "generate_unique_id",
    "extract_domain",
    "download_favicon",
    "filter_by_tags",
    "normalize_url",
    "validate_url",
]