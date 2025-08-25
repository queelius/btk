#!/usr/bin/env python3
"""
BTK FastAPI Server - REST API for Bookmark Toolkit

This provides a REST API interface to BTK functionality, enabling:
- Browser extensions to interact with BTK
- Web UIs for bookmark management
- Programmatic access to bookmarks
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from fastapi import FastAPI, HTTPException, Query, File, UploadFile, Body, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, HttpUrl
import uvicorn
import asyncio
import json as json_module

# Add BTK to path
btk_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(btk_path))

import btk.utils as utils
import btk.tools as tools
import btk.dedup as dedup
import btk.tag_utils as tag_utils
from btk.bulk_ops import bulk_add_from_file, bulk_edit_bookmarks, bulk_remove_bookmarks, create_filter_from_criteria
from btk.repl import BtkReplCore, WebSocketReplHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="BTK API",
    description="REST API for Bookmark Toolkit",
    version="1.0.0"
)

# Configure CORS - allow browser extensions and local web apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:5000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:5173",
        "chrome-extension://*",
        "moz-extension://*",
        "null"  # For file:// protocol
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
DEFAULT_LIB_DIR = os.environ.get("BTK_LIB_DIR", os.path.expanduser("~/.btk/bookmarks"))


# Pydantic models for request/response
class BookmarkBase(BaseModel):
    """Base bookmark model."""
    url: HttpUrl
    title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    stars: bool = False


class BookmarkCreate(BookmarkBase):
    """Model for creating a bookmark."""
    pass


class BookmarkUpdate(BaseModel):
    """Model for updating a bookmark."""
    title: Optional[str] = None
    url: Optional[HttpUrl] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    stars: Optional[bool] = None


class Bookmark(BookmarkBase):
    """Complete bookmark model."""
    id: int
    unique_id: str
    added: str
    visit_count: int = 0
    last_visited: Optional[str] = None
    favicon: Optional[str] = None
    reachable: Optional[bool] = None
    
    class Config:
        from_attributes = True


class BulkEditRequest(BaseModel):
    """Request model for bulk edit operations."""
    filter_tags: Optional[str] = None
    filter_url: Optional[str] = None
    filter_starred: Optional[bool] = None
    add_tags: Optional[List[str]] = None
    remove_tags: Optional[List[str]] = None
    set_stars: Optional[bool] = None
    set_description: Optional[str] = None


class DedupeRequest(BaseModel):
    """Request model for deduplication."""
    strategy: str = Field(default="merge", pattern="^(merge|keep_first|keep_last|keep_most_visited)$")
    preview: bool = False


class ImportResponse(BaseModel):
    """Response model for import operations."""
    success: bool
    count: int
    message: str


class StatsResponse(BaseModel):
    """Response model for statistics."""
    total_bookmarks: int
    total_tags: int
    starred_count: int
    duplicate_count: int
    unreachable_count: Optional[int] = None


# Helper functions
def get_lib_dir(lib_dir: Optional[str] = None) -> str:
    """Get the library directory."""
    return lib_dir or DEFAULT_LIB_DIR


def ensure_lib_exists(lib_dir: str):
    """Ensure library directory exists."""
    os.makedirs(lib_dir, exist_ok=True)
    bookmarks_file = os.path.join(lib_dir, "bookmarks.json")
    if not os.path.exists(bookmarks_file):
        utils.save_bookmarks([], None, lib_dir)


# API Endpoints

@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "BTK API",
        "version": "1.0.0",
        "endpoints": {
            "bookmarks": "/bookmarks",
            "tags": "/tags",
            "import": "/import/{format}",
            "export": "/export/{format}",
            "stats": "/stats",
            "docs": "/docs"
        }
    }


@app.get("/bookmarks", response_model=List[Bookmark])
async def get_bookmarks(
    lib_dir: Optional[str] = Query(None, description="Library directory"),
    search: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Filter by tag prefix"),
    starred: Optional[bool] = Query(None, description="Filter by starred status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results")
):
    """Get bookmarks with optional filtering."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    # Apply filters
    if search:
        bookmarks = tools.search_bookmarks(bookmarks, search)
    
    if tag:
        bookmarks = tag_utils.filter_bookmarks_by_tag_prefix(bookmarks, tag)
    
    if starred is not None:
        bookmarks = [b for b in bookmarks if b.get("stars", False) == starred]
    
    # Limit results
    bookmarks = bookmarks[:limit]
    
    return bookmarks


@app.get("/bookmarks/{bookmark_id}", response_model=Bookmark)
async def get_bookmark(
    bookmark_id: int,
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Get a specific bookmark by ID."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    for bookmark in bookmarks:
        if bookmark.get("id") == bookmark_id:
            return bookmark
    
    raise HTTPException(status_code=404, detail="Bookmark not found")


@app.post("/bookmarks", response_model=Bookmark, status_code=201)
async def create_bookmark(
    bookmark: BookmarkCreate,
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Create a new bookmark."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    # Check for duplicates
    url_str = str(bookmark.url)
    for existing in bookmarks:
        if existing.get("url") == url_str:
            raise HTTPException(status_code=409, detail="Bookmark already exists")
    
    # Create new bookmark
    new_bookmark = tools.add_bookmark(
        bookmarks,
        bookmark.title or url_str,
        url_str,
        bookmark.stars,
        bookmark.tags,
        bookmark.description or "",
        lib
    )
    
    # Save bookmarks
    utils.save_bookmarks(bookmarks, None, lib)
    
    # Return the newly created bookmark
    return bookmarks[-1]


@app.put("/bookmarks/{bookmark_id}", response_model=Bookmark)
async def update_bookmark(
    bookmark_id: int,
    update: BookmarkUpdate,
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Update an existing bookmark."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    # Find and update bookmark
    for bookmark in bookmarks:
        if bookmark.get("id") == bookmark_id:
            if update.title is not None:
                bookmark["title"] = update.title
            if update.url is not None:
                bookmark["url"] = str(update.url)
            if update.tags is not None:
                bookmark["tags"] = update.tags
            if update.description is not None:
                bookmark["description"] = update.description
            if update.stars is not None:
                bookmark["stars"] = update.stars
            
            utils.save_bookmarks(bookmarks, None, lib)
            return bookmark
    
    raise HTTPException(status_code=404, detail="Bookmark not found")


@app.delete("/bookmarks/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: int,
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Delete a bookmark."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    # Find and remove bookmark
    for i, bookmark in enumerate(bookmarks):
        if bookmark.get("id") == bookmark_id:
            removed = bookmarks.pop(i)
            # Reindex remaining bookmarks
            for j, b in enumerate(bookmarks[i:], start=i):
                b["id"] = j + 1
            utils.save_bookmarks(bookmarks, None, lib)
            return {"message": f"Bookmark {bookmark_id} deleted", "bookmark": removed}
    
    raise HTTPException(status_code=404, detail="Bookmark not found")


@app.get("/tags")
async def get_tags(
    lib_dir: Optional[str] = Query(None, description="Library directory"),
    format: str = Query("flat", pattern="^(flat|tree|stats)$", description="Output format")
):
    """Get all tags in various formats."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    if format == "tree":
        tree = tag_utils.get_tag_tree(bookmarks)
        return tree
    elif format == "stats":
        stats = tag_utils.get_tag_statistics(bookmarks)
        return stats
    else:  # flat
        all_tags = set()
        for bookmark in bookmarks:
            all_tags.update(bookmark.get("tags", []))
        return sorted(list(all_tags))


@app.post("/tags/rename")
async def rename_tag(
    old_tag: str = Body(..., description="Tag to rename"),
    new_tag: str = Body(..., description="New tag name"),
    lib_dir: Optional[str] = Body(None, description="Library directory")
):
    """Rename a tag and all its children."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    try:
        bookmarks, affected = tag_utils.rename_tag_hierarchy(bookmarks, old_tag, new_tag)
        utils.save_bookmarks(bookmarks, None, lib)
        return {"message": f"Renamed {old_tag} to {new_tag}", "affected_bookmarks": affected}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/bulk/edit")
async def bulk_edit(
    request: BulkEditRequest,
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Bulk edit bookmarks matching criteria."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    # Create filter
    filter_func = create_filter_from_criteria(
        tag_prefix=request.filter_tags,
        url_pattern=request.filter_url,
        is_starred=request.filter_starred
    )
    
    # Apply edits
    bookmarks, edited_count = bulk_edit_bookmarks(
        bookmarks,
        filter_func,
        add_tags=request.add_tags,
        remove_tags=request.remove_tags,
        set_stars=request.set_stars,
        set_description=request.set_description
    )
    
    if edited_count > 0:
        utils.save_bookmarks(bookmarks, None, lib)
    
    return {"message": f"Edited {edited_count} bookmarks", "count": edited_count}


@app.post("/dedupe")
async def deduplicate(
    request: DedupeRequest,
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Find and remove duplicate bookmarks."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    if request.preview:
        stats = dedup.get_duplicate_stats(bookmarks)
        return stats
    else:
        deduplicated, removed = dedup.deduplicate_bookmarks(bookmarks, strategy=request.strategy)
        if removed:
            utils.save_bookmarks(deduplicated, None, lib)
            return {"message": f"Removed {len(removed)} duplicates", "removed_count": len(removed)}
        else:
            return {"message": "No duplicates found", "removed_count": 0}


@app.post("/import/{format}", response_model=ImportResponse)
async def import_bookmarks(
    format: str,
    file: UploadFile = File(...),
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Import bookmarks from various formats."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    initial_count = len(bookmarks)
    
    # Save uploaded file temporarily
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        if format == "html":
            bookmarks = tools.import_bookmarks(tmp_path, bookmarks, lib, format='netscape')
        elif format == "json":
            bookmarks = tools.import_bookmarks_json(tmp_path, bookmarks, lib)
        elif format == "csv":
            # For CSV, we need to determine fields
            import csv
            with open(tmp_path, 'r') as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames
            bookmarks = tools.import_bookmarks_csv(tmp_path, bookmarks, lib, fields)
        elif format == "markdown":
            bookmarks = tools.import_bookmarks_markdown(tmp_path, bookmarks, lib)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
        
        utils.save_bookmarks(bookmarks, None, lib)
        new_count = len(bookmarks) - initial_count
        
        return ImportResponse(
            success=True,
            count=new_count,
            message=f"Imported {new_count} bookmarks"
        )
    
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        os.unlink(tmp_path)


@app.get("/export/{format}")
async def export_bookmarks(
    format: str,
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Export bookmarks to various formats."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    # Create temporary file for export
    import tempfile
    
    if format == "html":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            tools.export_bookmarks_html(bookmarks, tmp.name)
            return FileResponse(tmp.name, media_type="text/html", filename="bookmarks.html")
    
    elif format == "json":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            tools.export_bookmarks_json(bookmarks, tmp.name)
            return FileResponse(tmp.name, media_type="application/json", filename="bookmarks.json")
    
    elif format == "csv":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tools.export_bookmarks_csv(bookmarks, tmp.name)
            return FileResponse(tmp.name, media_type="text/csv", filename="bookmarks.csv")
    
    elif format == "markdown":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as tmp:
            tools.export_bookmarks_markdown(bookmarks, tmp.name)
            return FileResponse(tmp.name, media_type="text/markdown", filename="bookmarks.md")
    
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@app.get("/stats", response_model=StatsResponse)
async def get_statistics(
    lib_dir: Optional[str] = Query(None, description="Library directory")
):
    """Get bookmark library statistics."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    
    # Calculate statistics
    all_tags = set()
    starred_count = 0
    unreachable_count = 0
    
    for bookmark in bookmarks:
        all_tags.update(bookmark.get("tags", []))
        if bookmark.get("stars", False):
            starred_count += 1
        if bookmark.get("reachable") is False:
            unreachable_count += 1
    
    # Get duplicate stats
    dup_stats = dedup.get_duplicate_stats(bookmarks)
    
    return StatsResponse(
        total_bookmarks=len(bookmarks),
        total_tags=len(all_tags),
        starred_count=starred_count,
        duplicate_count=dup_stats["bookmarks_to_remove"],
        unreachable_count=unreachable_count if unreachable_count > 0 else None
    )


@app.post("/search")
async def search_bookmarks(
    query: str = Body(..., description="Search query"),
    lib_dir: Optional[str] = Body(None, description="Library directory"),
    limit: int = Body(100, ge=1, le=1000, description="Maximum results")
):
    """Search bookmarks using BTK's search functionality."""
    lib = get_lib_dir(lib_dir)
    ensure_lib_exists(lib)
    
    bookmarks = utils.load_bookmarks(lib)
    results = tools.search_bookmarks(bookmarks, query)
    
    return results[:limit]


# WebSocket endpoint for REPL
@app.websocket("/ws/repl")
async def websocket_repl(websocket: WebSocket):
    """WebSocket endpoint for BTK REPL interaction."""
    await websocket.accept()
    
    # Create REPL handler
    handler = WebSocketReplHandler()
    
    try:
        # Send initial welcome message
        await websocket.send_json({
            "type": "output",
            "content": "BTK REPL WebSocket Connected\nType 'help' for available commands\n"
        })
        
        while True:
            # Receive command from client
            data = await websocket.receive_text()
            
            try:
                # Parse the command
                command_data = json_module.loads(data)
                command = command_data.get("command", "")
                
                # Execute command through the handler
                response = await handler.handle_message({
                    "type": "command",
                    "data": command
                })
                
                # Send response back to client
                await websocket.send_json(response)
                
            except json_module.JSONDecodeError:
                # If not JSON, treat as raw command
                response = await handler.handle_message({
                    "type": "command", 
                    "data": data
                })
                await websocket.send_json(response)
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Error processing command: {str(e)}"
                })
    
    except WebSocketDisconnect:
        logger.info("WebSocket REPL client disconnected")
    except Exception as e:
        logger.error(f"WebSocket REPL error: {e}")
        await websocket.close()


if __name__ == "__main__":
    # Run the server
    port = int(os.environ.get("BTK_API_PORT", 8000))
    host = os.environ.get("BTK_API_HOST", "127.0.0.1")
    
    logger.info(f"Starting BTK API server on {host}:{port}")
    logger.info(f"Using library directory: {DEFAULT_LIB_DIR}")
    logger.info(f"API documentation available at http://{host}:{port}/docs")
    
    uvicorn.run(app, host=host, port=port)