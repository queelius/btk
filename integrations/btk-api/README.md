# BTK FastAPI Server

A REST API server for Bookmark Toolkit (BTK), providing programmatic access to bookmark management functionality.

## Features

- **Full CRUD operations** for bookmarks
- **Tag management** with hierarchical support
- **Import/Export** in multiple formats (HTML, JSON, CSV, Markdown)
- **Bulk operations** for editing multiple bookmarks
- **Deduplication** with various strategies
- **Search and filtering** capabilities
- **CORS support** for browser extensions
- **Interactive API documentation** via Swagger UI

## Installation

```bash
# From the btk-api directory
pip install -r requirements.txt
```

## Usage

### Starting the Server

```bash
# Default (localhost:8000)
python server.py

# Custom host and port
BTK_API_HOST=0.0.0.0 BTK_API_PORT=8080 python server.py

# Custom bookmark library location
BTK_LIB_DIR=/path/to/bookmarks python server.py
```

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Bookmarks

- `GET /bookmarks` - List bookmarks with optional filtering
- `GET /bookmarks/{id}` - Get specific bookmark
- `POST /bookmarks` - Create new bookmark
- `PUT /bookmarks/{id}` - Update bookmark
- `DELETE /bookmarks/{id}` - Delete bookmark

### Tags

- `GET /tags` - Get all tags (flat, tree, or stats format)
- `POST /tags/rename` - Rename tag and its children

### Bulk Operations

- `POST /bulk/edit` - Edit multiple bookmarks matching criteria
- `POST /dedupe` - Remove duplicate bookmarks

### Import/Export

- `POST /import/{format}` - Import bookmarks (html, json, csv, markdown)
- `GET /export/{format}` - Export bookmarks

### Other

- `GET /stats` - Get library statistics
- `POST /search` - Search bookmarks

## Example Requests

### Add a Bookmark

```bash
curl -X POST "http://localhost:8000/bookmarks" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "title": "Example Site",
    "tags": ["example", "test"],
    "description": "An example bookmark",
    "stars": true
  }'
```

### Search Bookmarks

```bash
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "python",
    "limit": 10
  }'
```

### Export as JSON

```bash
curl "http://localhost:8000/export/json" -o bookmarks.json
```

### Get Tag Statistics

```bash
curl "http://localhost:8000/tags?format=stats"
```

## Environment Variables

- `BTK_API_HOST` - Server host (default: 127.0.0.1)
- `BTK_API_PORT` - Server port (default: 8000)
- `BTK_LIB_DIR` - Bookmark library directory (default: ~/.btk/bookmarks)

## CORS Configuration

The server is configured to accept requests from:
- `http://localhost:*`
- `http://127.0.0.1:*`
- `chrome-extension://*`
- `moz-extension://*`

This allows browser extensions and local web applications to interact with the API.

## Development

### Running with Auto-reload

```bash
uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

### Testing the API

```python
import requests

# Base URL
base_url = "http://localhost:8000"

# Get all bookmarks
response = requests.get(f"{base_url}/bookmarks")
bookmarks = response.json()

# Add a bookmark
new_bookmark = {
    "url": "https://python.org",
    "title": "Python",
    "tags": ["programming", "python"]
}
response = requests.post(f"{base_url}/bookmarks", json=new_bookmark)
```

## Security Notes

- By default, the server only listens on localhost (127.0.0.1)
- No authentication is implemented - suitable for local use only
- For production use, add authentication and use HTTPS
- Consider using a reverse proxy (nginx, caddy) for production

## Future Enhancements

- WebSocket support for real-time updates
- Authentication and user management
- Rate limiting
- Batch operations
- Integration with visualization module
- Integration with MCP for AI features