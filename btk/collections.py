"""
Bookmark Collections Management for BTK.

This module provides functionality for managing sets of bookmark collections,
enabling organization of bookmarks into multiple named collections with metadata.

A collection is any directory that contains a bookmarks.json file following the
BTK format. Collections can optionally have metadata.json for additional info.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from dataclasses import dataclass, asdict

from . import utils
from . import tools
from . import merge

logger = logging.getLogger(__name__)


@dataclass
class CollectionInfo:
    """Information about a bookmark collection."""
    name: str
    path: Path
    description: str = ""
    created: str = ""
    modified: str = ""
    tags: List[str] = None
    source: str = ""  # e.g., "chrome", "firefox", "manual", "import"
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        self.path = Path(self.path) if not isinstance(self.path, Path) else self.path


class BookmarkCollection:
    """A bookmark collection - any directory with bookmarks.json."""
    
    def __init__(self, path: str):
        """
        Initialize a bookmark collection.
        
        Args:
            path: Path to the collection directory
        """
        self.path = Path(path)
        
        # Check if this is a valid collection
        self.bookmarks_file = self.path / "bookmarks.json"
        if not self.bookmarks_file.exists():
            # Create directory if needed and initialize
            self.path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initializing new collection at {path}")
            # Directly create empty bookmarks.json
            with open(self.bookmarks_file, 'w') as f:
                json.dump([], f)
        
        # Optional metadata
        self.metadata_file = self.path / "metadata.json"
        self.info = self._load_info()
        
        # Favicons directory (optional)
        self.favicons_dir = self.path / "favicons"
    
    def _load_info(self) -> CollectionInfo:
        """Load collection info from metadata file if it exists."""
        info = CollectionInfo(
            name=self.path.name,
            path=self.path
        )
        
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(info, key) and key != 'path':
                            setattr(info, key, value)
            except Exception as e:
                logger.warning(f"Could not load metadata for {self.path}: {e}")
        
        # Try to get modified time from bookmarks file
        if self.bookmarks_file.exists():
            stat = self.bookmarks_file.stat()
            info.modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        
        return info
    
    def _save_info(self):
        """Save collection info to metadata file."""
        try:
            data = asdict(self.info)
            data['path'] = str(data['path'])  # Convert Path to string
            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save metadata for {self.path}: {e}")
    
    def get_bookmarks(self) -> List[Dict[str, Any]]:
        """Get all bookmarks in this collection."""
        return utils.load_bookmarks(str(self.path))
    
    def save_bookmarks(self, bookmarks: List[Dict[str, Any]]):
        """Save bookmarks to this collection."""
        utils.save_bookmarks(bookmarks, None, str(self.path))
        self.info.modified = datetime.now().isoformat()
    
    def add_bookmark(self, bookmark: Dict[str, Any]) -> bool:
        """Add a bookmark to this collection."""
        bookmarks = self.get_bookmarks()
        
        # Check for duplicates
        for existing in bookmarks:
            if existing.get('url') == bookmark.get('url'):
                logger.warning(f"Bookmark already exists: {bookmark.get('url')}")
                return False
        
        # Add the bookmark
        if 'id' not in bookmark:
            bookmark['id'] = utils.generate_id(bookmarks)
        if 'unique_id' not in bookmark:
            bookmark['unique_id'] = utils.generate_unique_id()
        if 'added' not in bookmark:
            bookmark['added'] = datetime.now().isoformat()
        
        bookmarks.append(bookmark)
        self.save_bookmarks(bookmarks)
        return True
    
    def remove_bookmark(self, bookmark_id: int) -> bool:
        """Remove a bookmark from this collection."""
        bookmarks = self.get_bookmarks()
        original_count = len(bookmarks)
        bookmarks = [b for b in bookmarks if b.get('id') != bookmark_id]
        
        if len(bookmarks) < original_count:
            self.save_bookmarks(bookmarks)
            return True
        return False
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search bookmarks in this collection."""
        bookmarks = self.get_bookmarks()
        return tools.search_bookmarks(bookmarks, query)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for this collection."""
        bookmarks = self.get_bookmarks()
        
        # Count tags
        tag_counts = {}
        for bookmark in bookmarks:
            for tag in bookmark.get('tags', []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        return {
            'name': self.info.name,
            'path': str(self.path),
            'total_bookmarks': len(bookmarks),
            'starred': sum(1 for b in bookmarks if b.get('stars')),
            'total_tags': len(tag_counts),
            'top_tags': sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            'modified': self.info.modified
        }


class CollectionSet:
    """Manages a set of bookmark collections."""
    
    def __init__(self, root_path: str = None):
        """
        Initialize a collection set.
        
        Args:
            root_path: Root directory to search for collections.
                      If None, only explicitly added collections are managed.
        """
        self.root = Path(root_path) if root_path else None
        self.collections: Dict[str, BookmarkCollection] = {}
        
        # Auto-discover collections if root is provided
        if self.root and self.root.exists():
            self.discover_collections(str(self.root))
    
    def discover_collections(self, search_path: str, recursive: bool = True):
        """
        Discover bookmark collections in a directory.
        
        Args:
            search_path: Directory to search
            recursive: Whether to search subdirectories
        """
        search_dir = Path(search_path)
        if not search_dir.exists():
            logger.warning(f"Search path does not exist: {search_path}")
            return
        
        if recursive:
            # Find all bookmarks.json files
            for bookmarks_file in search_dir.glob("**/bookmarks.json"):
                collection_dir = bookmarks_file.parent
                self.add_collection(str(collection_dir))
        else:
            # Only check immediate subdirectories
            for item in search_dir.iterdir():
                if item.is_dir() and (item / "bookmarks.json").exists():
                    self.add_collection(str(item))
    
    def add_collection(self, path: str, name: str = None) -> BookmarkCollection:
        """
        Add a collection to the set.
        
        Args:
            path: Path to the collection directory
            name: Optional name for the collection (defaults to directory name)
            
        Returns:
            The added collection
        """
        collection_path = Path(path)
        
        # Use provided name or directory name
        if name is None:
            name = collection_path.name
        
        # Check if already added
        if name in self.collections:
            logger.warning(f"Collection '{name}' already exists, replacing")
        
        try:
            collection = BookmarkCollection(str(collection_path))
            self.collections[name] = collection
            logger.info(f"Added collection '{name}' from {collection_path}")
            return collection
        except ValueError as e:
            logger.error(f"Failed to add collection from {path}: {e}")
            raise
    
    def create_collection(self, path: str, name: str = None) -> BookmarkCollection:
        """
        Create a new collection.
        
        Args:
            path: Path where to create the collection
            name: Optional name for the collection
            
        Returns:
            The created collection
        """
        collection_path = Path(path)
        collection_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize as BTK collection with empty bookmarks.json
        bookmarks_file = collection_path / "bookmarks.json"
        with open(bookmarks_file, 'w') as f:
            json.dump([], f)
        
        return self.add_collection(str(collection_path), name)
    
    def get_collection(self, name: str) -> Optional[BookmarkCollection]:
        """Get a collection by name."""
        return self.collections.get(name)
    
    def list_collections(self) -> List[str]:
        """List all collection names."""
        return list(self.collections.keys())
    
    def remove_collection(self, name: str):
        """
        Remove a collection from the set (doesn't delete files).
        
        Args:
            name: Collection name
        """
        if name not in self.collections:
            raise ValueError(f"Collection '{name}' not found")
        
        del self.collections[name]
        logger.info(f"Removed collection '{name}' from set")
    
    def merge_collections(self, names: List[str], target_path: str,
                         operation: str = "union", target_name: str = None) -> BookmarkCollection:
        """
        Merge multiple collections into a new collection.
        
        Args:
            names: Collection names to merge
            target_path: Path for the merged collection
            operation: Merge operation (union, intersection, difference)
            target_name: Optional name for the merged collection
            
        Returns:
            The merged collection
        """
        # Get bookmarks from each collection
        all_bookmarks = []
        for name in names:
            if name not in self.collections:
                raise ValueError(f"Collection '{name}' not found")
            all_bookmarks.append(self.collections[name].get_bookmarks())
        
        # Perform merge operation
        if operation == "union":
            merged = merge.merge_union(all_bookmarks)
        elif operation == "intersection":
            merged = merge.merge_intersection(all_bookmarks)
        elif operation == "difference":
            if len(all_bookmarks) != 2:
                raise ValueError("Difference operation requires exactly 2 collections")
            merged = merge.merge_difference(all_bookmarks[0], all_bookmarks[1])
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        # Create new collection
        target = self.create_collection(target_path, target_name)
        target.save_bookmarks(merged)
        
        # Add metadata about the merge
        target.info.description = f"Merged from: {', '.join(names)} ({operation})"
        target.info.source = "merge"
        target._save_info()
        
        return target
    
    def search_all(self, query: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across all collections.
        
        Args:
            query: Search query
            
        Returns:
            Dictionary mapping collection names to matching bookmarks
        """
        results = {}
        for name, collection in self.collections.items():
            matches = collection.search(query)
            if matches:
                results[name] = matches
        return results
    
    def get_all_bookmarks(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all bookmarks from all collections."""
        return {
            name: collection.get_bookmarks()
            for name, collection in self.collections.items()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all collections."""
        stats = {
            'total_collections': len(self.collections),
            'total_bookmarks': 0,
            'collections': {}
        }
        
        for name, collection in self.collections.items():
            collection_stats = collection.get_stats()
            stats['collections'][name] = collection_stats
            stats['total_bookmarks'] += collection_stats['total_bookmarks']
        
        return stats
    
    def export_collection(self, name: str, output_file: str, format: str = "json"):
        """
        Export a collection to a file.
        
        Args:
            name: Collection name
            output_file: Output file path
            format: Export format (json, html, csv, markdown, hierarchical)
        """
        if name not in self.collections:
            raise ValueError(f"Collection '{name}' not found")
        
        bookmarks = self.collections[name].get_bookmarks()
        
        if format == "json":
            tools.export_bookmarks_json(bookmarks, output_file)
        elif format == "html":
            tools.export_bookmarks_html(bookmarks, output_file)
        elif format == "csv":
            tools.export_bookmarks_csv(bookmarks, output_file)
        elif format == "markdown":
            tools.export_bookmarks_markdown(bookmarks, output_file)
        elif format == "hierarchical":
            tools.export_bookmarks_hierarchical(bookmarks, output_file)
        else:
            raise ValueError(f"Unknown export format: {format}")
    
    def import_to_collection(self, name: str, file_path: str, format: str = None):
        """
        Import bookmarks into a collection.
        
        Args:
            name: Collection name
            file_path: File to import from
            format: Import format (auto-detected if None)
        """
        if name not in self.collections:
            raise ValueError(f"Collection '{name}' not found")
        
        collection = self.collections[name]
        existing = collection.get_bookmarks()
        
        # Determine format if not specified
        if format is None:
            if file_path.endswith('.json'):
                format = 'json'
            elif file_path.endswith('.csv'):
                format = 'csv'
            elif file_path.endswith('.html'):
                format = 'html'
            elif file_path.endswith('.md'):
                format = 'markdown'
            else:
                # Default to JSON
                format = 'json'
        
        # Import bookmarks based on format
        # Note: BTK import functions modify existing bookmarks list in-place
        # and return the modified list, expecting a lib_dir for favicon storage
        imported_bookmarks = []
        
        if format == 'json':
            imported_bookmarks = tools.import_bookmarks_json(
                file_path, [], str(collection.path)
            )
        elif format == 'csv':
            imported_bookmarks = tools.import_bookmarks_csv(
                file_path, [], str(collection.path)
            )
        elif format == 'html':
            imported_bookmarks = tools.import_bookmarks_html_generic(
                file_path, [], str(collection.path)
            )
        elif format == 'markdown':
            imported_bookmarks = tools.import_bookmarks_markdown(
                file_path, [], str(collection.path)
            )
        else:
            raise ValueError(f"Unknown import format: {format}")
        
        # Merge with existing (avoiding duplicates)
        existing_urls = {b.get('url') for b in existing}
        new_bookmarks = [b for b in imported_bookmarks if b.get('url') not in existing_urls]
        
        if new_bookmarks:
            combined = existing + new_bookmarks
            collection.save_bookmarks(combined)
            logger.info(f"Imported {len(new_bookmarks)} new bookmarks to '{name}'")
        else:
            logger.info(f"No new bookmarks to import to '{name}'")


# Convenience functions
def is_collection(path: str) -> bool:
    """Check if a directory is a valid BTK collection."""
    return (Path(path) / "bookmarks.json").exists()


def find_collections(search_path: str) -> List[str]:
    """Find all BTK collections in a directory tree."""
    collections = []
    search_dir = Path(search_path)
    
    if search_dir.exists():
        for bookmarks_file in search_dir.glob("**/bookmarks.json"):
            collections.append(str(bookmarks_file.parent))
    
    return collections