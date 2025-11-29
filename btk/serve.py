"""
BTK REST API Server.

A lightweight REST API server for BTK that serves:
- JSON API endpoints for bookmark operations
- Static frontend files from tools/btk-frontend

Usage:
    btk serve              # Start on default port 8000
    btk serve --port 3000  # Custom port
"""

import json
import os
import sys
import mimetypes
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from typing import Optional, Dict, Any
from functools import partial

from .db import Database


class BTKAPIHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for BTK REST API."""

    def __init__(self, *args, db: Database, frontend_dir: Path, **kwargs):
        self.db = db
        self.frontend_dir = frontend_dir
        super().__init__(*args, **kwargs)

    def send_json(self, data: Any, status: int = 200):
        """Send JSON response."""
        response = json.dumps(data, default=str, indent=2)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(response.encode())

    def send_error_json(self, message: str, status: int = 400):
        """Send JSON error response."""
        self.send_json({'error': message}, status)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # API routes
        if path == '/bookmarks':
            self.handle_list_bookmarks(query)
        elif path == '/stats':
            self.handle_stats()
        elif path == '/tags':
            self.handle_tags(query)
        elif path.startswith('/bookmarks/'):
            bookmark_id = path.split('/')[-1]
            self.handle_get_bookmark(bookmark_id)
        elif path.startswith('/export/'):
            format_type = path.split('/')[-1]
            self.handle_export(format_type)
        else:
            # Serve static files
            self.serve_static(path)

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error_json('Invalid JSON', 400)
            return

        if path == '/bookmarks':
            self.handle_add_bookmark(data)
        elif path == '/search':
            self.handle_search(data)
        else:
            self.send_error_json('Not found', 404)

    def do_DELETE(self):
        """Handle DELETE requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/bookmarks/'):
            bookmark_id = path.split('/')[-1]
            self.handle_delete_bookmark(bookmark_id)
        else:
            self.send_error_json('Not found', 404)

    def do_PUT(self):
        """Handle PUT requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error_json('Invalid JSON', 400)
            return

        if path.startswith('/bookmarks/'):
            bookmark_id = path.split('/')[-1]
            self.handle_update_bookmark(bookmark_id, data)
        else:
            self.send_error_json('Not found', 404)

    # =========================================================================
    # API Handlers
    # =========================================================================

    def handle_list_bookmarks(self, query: Dict):
        """List all bookmarks."""
        limit = int(query.get('limit', [100])[0])
        offset = int(query.get('offset', [0])[0])

        bookmarks = self.db.list(limit=limit, offset=offset)
        result = [self._bookmark_to_dict(b) for b in bookmarks]
        self.send_json(result)

    def handle_get_bookmark(self, bookmark_id: str):
        """Get a single bookmark."""
        try:
            bookmark = self.db.get(id=int(bookmark_id))
            if bookmark:
                self.send_json(self._bookmark_to_dict(bookmark))
            else:
                self.send_error_json('Bookmark not found', 404)
        except ValueError:
            self.send_error_json('Invalid bookmark ID', 400)

    def handle_add_bookmark(self, data: Dict):
        """Add a new bookmark."""
        url = data.get('url')
        if not url:
            self.send_error_json('URL is required', 400)
            return

        bookmark = self.db.add(
            url=url,
            title=data.get('title'),
            description=data.get('description'),
            tags=data.get('tags', [])
        )
        self.send_json(self._bookmark_to_dict(bookmark), 201)

    def handle_update_bookmark(self, bookmark_id: str, data: Dict):
        """Update a bookmark."""
        try:
            success = self.db.update(int(bookmark_id), **data)
            if success:
                bookmark = self.db.get(id=int(bookmark_id))
                self.send_json(self._bookmark_to_dict(bookmark))
            else:
                self.send_error_json('Failed to update', 500)
        except ValueError:
            self.send_error_json('Invalid bookmark ID', 400)

    def handle_delete_bookmark(self, bookmark_id: str):
        """Delete a bookmark."""
        try:
            success = self.db.delete(int(bookmark_id))
            if success:
                self.send_json({'deleted': True})
            else:
                self.send_error_json('Bookmark not found', 404)
        except ValueError:
            self.send_error_json('Invalid bookmark ID', 400)

    def handle_search(self, data: Dict):
        """Search bookmarks."""
        query = data.get('query', '')
        bookmarks = self.db.search(query=query)
        result = [self._bookmark_to_dict(b) for b in bookmarks]
        self.send_json(result)

    def handle_stats(self):
        """Get database statistics."""
        stats = self.db.stats()
        self.send_json(stats)

    def handle_tags(self, query: Dict):
        """Get tags with optional format."""
        format_type = query.get('format', ['list'])[0]

        if format_type == 'stats':
            # Return tag statistics
            from .tag_utils import get_tag_statistics
            bookmarks = self.db.list(limit=10000)
            bookmark_dicts = [
                {'id': b.id, 'tags': [t.name for t in b.tags]}
                for b in bookmarks
            ]
            stats = get_tag_statistics(bookmark_dicts)
            self.send_json(stats)
        else:
            # Return simple tag list
            bookmarks = self.db.list(limit=10000)
            tags = set()
            for b in bookmarks:
                for t in b.tags:
                    tags.add(t.name)
            self.send_json(sorted(list(tags)))

    def handle_export(self, format_type: str):
        """Export bookmarks."""
        from .exporters import export_to_string

        bookmarks = self.db.list(limit=10000)

        if format_type not in ['json', 'html', 'csv', 'markdown']:
            self.send_error_json(f'Unknown format: {format_type}', 400)
            return

        content = export_to_string(bookmarks, format_type)

        content_types = {
            'json': 'application/json',
            'html': 'text/html',
            'csv': 'text/csv',
            'markdown': 'text/markdown'
        }

        self.send_response(200)
        self.send_header('Content-Type', content_types.get(format_type, 'text/plain'))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content.encode())

    # =========================================================================
    # Static File Serving
    # =========================================================================

    def serve_static(self, path: str):
        """Serve static files from frontend directory."""
        if path == '/':
            path = '/index.html'

        file_path = self.frontend_dir / path.lstrip('/')

        if not file_path.exists() or not file_path.is_file():
            # Try index.html for SPA routing
            file_path = self.frontend_dir / 'index.html'
            if not file_path.exists():
                self.send_error_json('Not found', 404)
                return

        # Security: ensure we're still within frontend_dir
        try:
            file_path.resolve().relative_to(self.frontend_dir.resolve())
        except ValueError:
            self.send_error_json('Forbidden', 403)
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = 'application/octet-stream'

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.end_headers()

        with open(file_path, 'rb') as f:
            self.wfile.write(f.read())

    # =========================================================================
    # Helpers
    # =========================================================================

    def _bookmark_to_dict(self, bookmark) -> Dict:
        """Convert bookmark model to dictionary."""
        return {
            'id': bookmark.id,
            'unique_id': bookmark.unique_id,
            'url': bookmark.url,
            'title': bookmark.title,
            'description': bookmark.description,
            'added': bookmark.added.isoformat() if bookmark.added else None,
            'last_visited': bookmark.last_visited.isoformat() if bookmark.last_visited else None,
            'visit_count': bookmark.visit_count,
            'stars': bookmark.stars,
            'archived': bookmark.archived,
            'pinned': bookmark.pinned,
            'tags': [t.name for t in bookmark.tags]
        }

    def log_message(self, format, *args):
        """Override to customize logging."""
        print(f"[{self.log_date_time_string()}] {args[0]}")


def run_server(db_path: str = 'btk.db', port: int = 8000, host: str = '127.0.0.1'):
    """
    Start the BTK REST API server.

    Args:
        db_path: Path to the SQLite database
        port: Port to listen on
        host: Host to bind to
    """
    # Find frontend directory
    btk_dir = Path(__file__).parent.parent
    frontend_dir = btk_dir / 'tools' / 'btk-frontend'

    if not frontend_dir.exists():
        print(f"Warning: Frontend not found at {frontend_dir}")
        print("API will work but no web UI available")
        frontend_dir = btk_dir  # Fallback

    # Initialize database
    db = Database(db_path)

    # Create handler with database
    handler = partial(BTKAPIHandler, db=db, frontend_dir=frontend_dir)

    # Start server
    server = HTTPServer((host, port), handler)

    print(f"BTK Server running at http://{host}:{port}")
    print(f"Database: {db_path}")
    print(f"Frontend: {frontend_dir}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
