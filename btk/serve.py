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
        elif path == '/bookmarks/by-date':
            self.handle_bookmarks_by_date(query)
        elif path == '/queue':
            self.handle_get_queue(query)
        elif path == '/queue/next':
            self.handle_queue_next()
        elif path == '/queue/stats':
            self.handle_queue_stats()
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
        elif path == '/fts/stats':
            self.handle_fts_stats()
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
        elif path == '/import':
            self.handle_import(data)
        elif path == '/bookmarks/health':
            self.handle_health_check(data)
        elif path == '/queue':
            self.handle_queue_operation(data)
        elif path == '/fts/search':
            self.handle_fts_search(data)
        elif path == '/fts/build':
            self.handle_fts_build(data)
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

        try:
            bookmark = self.db.add(
                url=url,
                title=data.get('title'),
                description=data.get('description'),
                tags=data.get('tags', []),
                stars=data.get('stars', False)
            )
            if bookmark:
                # Re-fetch to get a fresh session with tags loaded
                fresh_bookmark = self.db.get(id=bookmark.id)
                self.send_json(self._bookmark_to_dict(fresh_bookmark), 201)
            else:
                # Duplicate - return the existing bookmark
                existing = self.db.get(url=url)
                if existing:
                    self.send_json(self._bookmark_to_dict(existing), 200)
                else:
                    self.send_error_json('Bookmark already exists', 409)
        except Exception as e:
            self.send_error_json(f'Failed to add bookmark: {str(e)}', 500)

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

    def handle_bookmarks_by_date(self, query: Dict):
        """Get bookmarks grouped by date.

        Query params:
            field: 'added', 'last_visited' (default: 'added')
            granularity: 'day', 'month', 'year' (default: 'month')
            year: filter to specific year (optional)
            month: filter to specific month 1-12 (optional, requires year)
            day: filter to specific day 1-31 (optional, requires year+month)
        """
        from datetime import datetime
        from collections import defaultdict

        field = query.get('field', ['added'])[0]
        granularity = query.get('granularity', ['month'])[0]

        # Validate field
        if field not in ['added', 'last_visited']:
            self.send_error_json(f'Invalid field: {field}. Use "added" or "last_visited"', 400)
            return

        # Validate granularity
        if granularity not in ['day', 'month', 'year']:
            self.send_error_json(f'Invalid granularity: {granularity}. Use "day", "month", or "year"', 400)
            return

        # Get filter parameters
        filter_year = query.get('year', [None])[0]
        filter_month = query.get('month', [None])[0]
        filter_day = query.get('day', [None])[0]

        # Convert to int if provided
        if filter_year:
            filter_year = int(filter_year)
        if filter_month:
            filter_month = int(filter_month)
        if filter_day:
            filter_day = int(filter_day)

        bookmarks = self.db.list(limit=10000)

        # Group bookmarks by date
        grouped = defaultdict(list)

        for b in bookmarks:
            date_value = getattr(b, field)
            if not date_value:
                continue

            # Apply filters
            if filter_year and date_value.year != filter_year:
                continue
            if filter_month and date_value.month != filter_month:
                continue
            if filter_day and date_value.day != filter_day:
                continue

            # Generate key based on granularity
            if granularity == 'year':
                key = str(date_value.year)
            elif granularity == 'month':
                key = f"{date_value.year}-{date_value.month:02d}"
            else:  # day
                key = f"{date_value.year}-{date_value.month:02d}-{date_value.day:02d}"

            grouped[key].append(self._bookmark_to_dict(b))

        # Sort keys in reverse chronological order
        sorted_keys = sorted(grouped.keys(), reverse=True)

        # Build result with counts
        result = {
            'field': field,
            'granularity': granularity,
            'filters': {
                'year': filter_year,
                'month': filter_month,
                'day': filter_day
            },
            'groups': [
                {
                    'key': key,
                    'count': len(grouped[key]),
                    'bookmarks': grouped[key]
                }
                for key in sorted_keys
            ],
            'total': sum(len(grouped[k]) for k in grouped)
        }

        self.send_json(result)

    def handle_import(self, data: Dict):
        """Import bookmarks from content."""
        import tempfile

        content = data.get('content', '')
        format_type = data.get('format', 'html')

        if not content:
            self.send_error_json('No content provided', 400)
            return

        # Write to temp file and use existing importers
        ext_map = {
            'html': '.html',
            'json': '.json',
            'csv': '.csv',
            'markdown': '.md',
            'text': '.txt'
        }

        ext = ext_map.get(format_type, '.html')

        try:
            from .importers import import_file

            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_path = f.name

            count = import_file(self.db, Path(temp_path), format=format_type)

            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

            self.send_json({'imported': count, 'format': format_type})
        except Exception as e:
            self.send_error_json(f'Import failed: {str(e)}', 500)

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

    def handle_health_check(self, data: Dict):
        """Check URL reachability for bookmarks.

        POST /bookmarks/health
        Body:
            ids: List of bookmark IDs to check (optional, checks all if not provided)
            broken_only: If true, only check previously broken bookmarks
            concurrency: Max concurrent requests (default: 10)
            timeout: Request timeout in seconds (default: 10)
            dry_run: If true, don't update database (default: false)
        """
        from .health_checker import run_health_check, summarize_results

        bookmark_ids = data.get('ids', [])
        broken_only = data.get('broken_only', False)
        concurrency = data.get('concurrency', 10)
        timeout = data.get('timeout', 10.0)
        dry_run = data.get('dry_run', False)

        # Get bookmarks to check
        if bookmark_ids:
            bookmarks = []
            for bid in bookmark_ids:
                b = self.db.get(id=int(bid))
                if b:
                    bookmarks.append(b)
        elif broken_only:
            bookmarks = self.db.search(reachable=False)
        else:
            bookmarks = self.db.list(limit=10000)

        if not bookmarks:
            self.send_json({
                'summary': {'total': 0, 'reachable': 0, 'unreachable': 0},
                'message': 'No bookmarks to check'
            })
            return

        # Prepare for health check
        bookmark_list = [(b.id, b.url) for b in bookmarks]

        # Run health check
        results = run_health_check(
            bookmark_list,
            concurrency=concurrency,
            timeout=timeout
        )

        # Update database if not dry run
        updated_count = 0
        if not dry_run:
            for result in results:
                self.db.update(result.bookmark_id, reachable=result.is_reachable)
                updated_count += 1

        # Generate summary
        summary = summarize_results(results)

        self.send_json({
            'summary': summary,
            'updated': updated_count if not dry_run else 0,
            'dry_run': dry_run,
            'results': [r.to_dict() for r in results]
        })

    def handle_get_queue(self, query: Dict):
        """Get reading queue items.

        GET /queue
        Query params:
            sort: Sort by (priority, queued_at, progress, title)
            include_completed: Include completed items (default: false)
        """
        from .reading_queue import get_queue

        sort_by = query.get('sort', ['priority'])[0]
        include_completed = query.get('include_completed', ['false'])[0].lower() == 'true'

        queue = get_queue(self.db, include_completed=include_completed, sort_by=sort_by)

        self.send_json({
            'items': [item.to_dict() for item in queue],
            'count': len(queue)
        })

    def handle_queue_next(self):
        """Get next recommended item to read.

        GET /queue/next
        """
        from .reading_queue import get_next_to_read

        item = get_next_to_read(self.db)
        if item:
            self.send_json(item.to_dict())
        else:
            self.send_json({'message': 'Queue is empty'}, 404)

    def handle_queue_stats(self):
        """Get reading queue statistics.

        GET /queue/stats
        """
        from .reading_queue import get_queue_stats

        stats = get_queue_stats(self.db)
        self.send_json(stats)

    def handle_queue_operation(self, data: Dict):
        """Handle queue operations.

        POST /queue
        Body:
            action: 'add', 'remove', 'progress', 'priority'
            bookmark_id: ID of the bookmark
            priority: Priority level (1-5, for add/priority actions)
            progress: Progress percentage (0-100, for progress action)
        """
        from .reading_queue import add_to_queue, remove_from_queue, update_progress, set_priority

        action = data.get('action')
        bookmark_id = data.get('bookmark_id')

        if not action:
            self.send_error_json('Missing action parameter', 400)
            return

        if not bookmark_id:
            self.send_error_json('Missing bookmark_id parameter', 400)
            return

        try:
            bookmark_id = int(bookmark_id)
        except ValueError:
            self.send_error_json('Invalid bookmark_id', 400)
            return

        success = False
        message = ''

        if action == 'add':
            priority = data.get('priority', 3)
            success = add_to_queue(self.db, bookmark_id, priority=priority)
            message = 'Added to queue' if success else 'Failed to add to queue'

        elif action == 'remove':
            success = remove_from_queue(self.db, bookmark_id)
            message = 'Removed from queue' if success else 'Failed to remove from queue'

        elif action == 'progress':
            progress = data.get('progress', 0)
            success = update_progress(self.db, bookmark_id, progress)
            message = f'Progress updated to {progress}%' if success else 'Failed to update progress'

        elif action == 'priority':
            priority = data.get('priority', 3)
            success = set_priority(self.db, bookmark_id, priority)
            message = f'Priority set to {priority}' if success else 'Failed to set priority'

        else:
            self.send_error_json(f'Unknown action: {action}', 400)
            return

        self.send_json({
            'success': success,
            'message': message,
            'bookmark_id': bookmark_id
        })

    # =========================================================================
    # FTS Search
    # =========================================================================

    def handle_fts_search(self, data: Dict):
        """Search bookmarks using full-text search.

        POST /fts/search
        Body:
            query: Search query (supports FTS5 syntax)
            limit: Max results (default: 50)
            in_content: Search in cached content too (default: True)
        """
        from .fts import get_fts_index

        query = data.get('query', '')
        limit = data.get('limit', 50)
        in_content = data.get('in_content', True)

        if not query:
            self.send_json([])
            return

        if not self.db.path:
            self.send_error_json('FTS not available for this database type', 400)
            return

        fts = get_fts_index(str(self.db.path))
        results = fts.search(query, limit=limit, in_content=in_content)

        # Enrich results with full bookmark data
        enriched = []
        for result in results:
            bookmark = self.db.get(id=result.bookmark_id)
            if bookmark:
                enriched.append({
                    'bookmark': self._bookmark_to_dict(bookmark),
                    'rank': result.rank,
                    'snippet': result.snippet
                })

        self.send_json(enriched)

    def handle_fts_stats(self):
        """Get FTS index statistics.

        GET /fts/stats
        """
        from .fts import get_fts_index

        if not self.db.path:
            self.send_error_json('FTS not available for this database type', 400)
            return

        fts = get_fts_index(str(self.db.path))
        stats = fts.get_stats()
        self.send_json(stats)

    def handle_fts_build(self, data: Dict):
        """Build or rebuild FTS index.

        POST /fts/build
        Body:
            rebuild: If True, rebuild from scratch (default: False)
        """
        from .fts import get_fts_index

        rebuild = data.get('rebuild', False)

        if not self.db.path:
            self.send_error_json('FTS not available for this database type', 400)
            return

        fts = get_fts_index(str(self.db.path))

        if rebuild:
            success = fts.rebuild()
        else:
            success = fts.create()
            if success:
                # Index all bookmarks
                bookmarks = self.db.all()
                for b in bookmarks:
                    fts.index_bookmark(b.id, b.url, b.title, b.description or '',
                                      [t.name for t in b.tags])

        stats = fts.get_stats()
        self.send_json({
            'success': success,
            'stats': stats
        })

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
