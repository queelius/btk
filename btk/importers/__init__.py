"""
BTK Importers

This package provides:
1. File importers - Import from HTML, JSON, CSV, Markdown files
2. Service importers - Import from YouTube, Twitter, Reddit, etc.
"""

# Re-export file importers (backwards compatibility)
from .file_importers import import_file, import_html, import_json, import_csv, import_markdown, import_text

# Service importer base classes
from .base import ServiceImporter, ImportResult, ServiceConfig

# Service importers (lazy load to avoid requiring dependencies)
def get_youtube_importer():
    """Get YouTube importer (requires google-api-python-client)."""
    from .youtube import YouTubeImporter
    return YouTubeImporter

__all__ = [
    # File importers
    'import_file',
    'import_html',
    'import_json',
    'import_csv',
    'import_markdown',
    'import_text',
    # Service importer base
    'ServiceImporter',
    'ImportResult',
    'ServiceConfig',
    # Service importers
    'get_youtube_importer',
]
