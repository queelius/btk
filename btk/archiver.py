"""
Content archiving system for BTK.

This module provides permanent archival of bookmark content, including
local storage and integration with the Internet Archive's Wayback Machine.
"""

import os
import json
import time
import hashlib
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from . import content_cache

logger = logging.getLogger(__name__)


class BookmarkArchiver:
    """
    Archives bookmark content permanently with versioning and Wayback Machine integration.
    
    Unlike the cache (which is LRU and temporary), the archive stores content
    permanently with full version history.
    """
    
    def __init__(self, archive_dir: Optional[str] = None):
        """
        Initialize the archiver.
        
        Args:
            archive_dir: Directory for permanent archive storage
        """
        if archive_dir is None:
            archive_dir = os.path.expanduser("~/.btk/archive")
        
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Archive index
        self.index_file = self.archive_dir / "archive_index.json"
        self.index = self._load_index()
        
        # Get cache and content extractor
        self.cache = content_cache.get_cache()
        # Note: extractors will be provided by the application
        self.extractors = []
    
    def set_extractors(self, extractors: List[Any]):
        """Set the content extractors to use."""
        self.extractors = extractors
    
    def _load_index(self) -> Dict[str, Any]:
        """Load the archive index."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load archive index: {e}")
        return {}
    
    def _save_index(self):
        """Save the archive index."""
        try:
            with open(self.index_file, 'w') as f:
                json.dump(self.index, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save archive index: {e}")
    
    def _get_archive_key(self, url: str) -> str:
        """Generate an archive key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]
    
    def archive_bookmark(self, bookmark: Dict[str, Any], 
                        force_fetch: bool = False,
                        save_to_wayback: bool = True) -> Dict[str, Any]:
        """
        Archive a bookmark's content.
        
        Args:
            bookmark: The bookmark to archive
            force_fetch: Force fetching even if cached
            save_to_wayback: Also save to Wayback Machine
            
        Returns:
            Archive metadata
        """
        url = bookmark.get('url')
        if not url:
            logger.error("Bookmark has no URL")
            return {}
        
        archive_key = self._get_archive_key(url)
        timestamp = datetime.now().isoformat()
        
        # Step 1: Get content (cache-first approach)
        content = None
        
        if not force_fetch:
            # Try cache first
            content = self.cache.get(url)
            logger.debug(f"Got content from cache for {url}")
        
        if content is None:
            # Fetch fresh content
            if self.extractors:
                extractor = self.extractors[0]
                try:
                    content = extractor.extract(url)
                    # Update cache with fresh content
                    self.cache.set(url, content)
                    logger.info(f"Fetched fresh content for {url}")
                except Exception as e:
                    logger.error(f"Failed to extract content: {e}")
                    return {}
            else:
                logger.error("No content extractors available")
                return {}
        
        # Step 2: Save to permanent archive
        archive_data = {
            'url': url,
            'title': bookmark.get('title') or content.get('title'),
            'timestamp': timestamp,
            'content': content,
            'bookmark_metadata': {
                'tags': bookmark.get('tags', []),
                'description': bookmark.get('description'),
                'stars': bookmark.get('stars', False),
                'added': bookmark.get('added')
            }
        }
        
        # Create archive directory for this URL
        url_dir = self.archive_dir / archive_key
        url_dir.mkdir(exist_ok=True)
        
        # Save with timestamp (allows multiple versions)
        version_file = url_dir / f"{timestamp.replace(':', '-')}.json"
        try:
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(archive_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Archived content to {version_file}")
        except Exception as e:
            logger.error(f"Failed to save archive: {e}")
            return {}
        
        # Step 3: Save to Wayback Machine
        wayback_url = None
        if save_to_wayback:
            wayback_url = self._save_to_wayback(url)
        
        # Update index
        if archive_key not in self.index:
            self.index[archive_key] = {
                'url': url,
                'versions': []
            }
        
        version_info = {
            'timestamp': timestamp,
            'file': str(version_file.name),
            'size': version_file.stat().st_size,
            'wayback_url': wayback_url
        }
        
        self.index[archive_key]['versions'].append(version_info)
        self.index[archive_key]['latest'] = timestamp
        self._save_index()
        
        return {
            'archive_key': archive_key,
            'timestamp': timestamp,
            'file': str(version_file),
            'wayback_url': wayback_url
        }
    
    def _save_to_wayback(self, url: str) -> Optional[str]:
        """
        Save a URL to the Wayback Machine.
        
        Args:
            url: URL to save
            
        Returns:
            Wayback Machine URL or None
        """
        try:
            # Request Wayback Machine to save the page
            save_url = f"https://web.archive.org/save/{url}"
            response = requests.get(save_url, timeout=30, allow_redirects=True)
            
            if response.status_code == 200:
                # Extract the archived URL from response
                # The URL format is typically: https://web.archive.org/web/TIMESTAMP/URL
                wayback_url = response.url
                logger.info(f"Saved to Wayback Machine: {wayback_url}")
                return wayback_url
            else:
                logger.warning(f"Wayback Machine returned status {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to save to Wayback Machine: {e}")
        
        return None
    
    def get_wayback_snapshots(self, url: str) -> List[Dict[str, Any]]:
        """
        Get available Wayback Machine snapshots for a URL.
        
        Args:
            url: URL to check
            
        Returns:
            List of snapshot metadata
        """
        try:
            # Use Wayback CDX API
            cdx_url = "http://web.archive.org/cdx/search/cdx"
            params = {
                'url': url,
                'output': 'json',
                'limit': 100,
                'fl': 'timestamp,original,statuscode,digest,length'
            }
            
            response = requests.get(cdx_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1:  # First row is headers
                    headers = data[0]
                    snapshots = []
                    
                    for row in data[1:]:
                        snapshot = dict(zip(headers, row))
                        # Convert timestamp to ISO format
                        ts = snapshot.get('timestamp', '')
                        if ts:
                            dt = datetime.strptime(ts, '%Y%m%d%H%M%S')
                            snapshot['datetime'] = dt.isoformat()
                            snapshot['wayback_url'] = f"https://web.archive.org/web/{ts}/{url}"
                        snapshots.append(snapshot)
                    
                    return snapshots
                    
        except Exception as e:
            logger.error(f"Failed to get Wayback snapshots: {e}")
        
        return []
    
    def get_archive_versions(self, url: str) -> List[Dict[str, Any]]:
        """
        Get all archived versions of a URL.
        
        Args:
            url: URL to check
            
        Returns:
            List of archive versions
        """
        archive_key = self._get_archive_key(url)
        
        if archive_key not in self.index:
            return []
        
        versions = []
        url_dir = self.archive_dir / archive_key
        
        for version_info in self.index[archive_key].get('versions', []):
            version_file = url_dir / version_info['file']
            if version_file.exists():
                versions.append({
                    'timestamp': version_info['timestamp'],
                    'file': str(version_file),
                    'size': version_info['size'],
                    'wayback_url': version_info.get('wayback_url')
                })
        
        return versions
    
    def get_archived_content(self, url: str, timestamp: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get archived content for a URL.
        
        Args:
            url: URL to retrieve
            timestamp: Specific version timestamp (latest if None)
            
        Returns:
            Archived content or None
        """
        archive_key = self._get_archive_key(url)
        
        if archive_key not in self.index:
            return None
        
        url_dir = self.archive_dir / archive_key
        
        if timestamp:
            # Get specific version
            version_file = url_dir / f"{timestamp.replace(':', '-')}.json"
        else:
            # Get latest version
            latest = self.index[archive_key].get('latest')
            if not latest:
                return None
            version_file = url_dir / f"{latest.replace(':', '-')}.json"
        
        if version_file.exists():
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load archived content: {e}")
        
        return None
    
    def bulk_archive(self, bookmarks: List[Dict[str, Any]], 
                     progress_callback=None) -> Dict[str, Any]:
        """
        Archive multiple bookmarks.
        
        Args:
            bookmarks: List of bookmarks to archive
            progress_callback: Optional callback for progress updates
            
        Returns:
            Archive statistics
        """
        stats = {
            'total': len(bookmarks),
            'archived': 0,
            'failed': 0,
            'wayback_saved': 0,
            'already_archived': 0
        }
        
        for i, bookmark in enumerate(bookmarks):
            url = bookmark.get('url')
            if not url:
                stats['failed'] += 1
                continue
            
            # Check if already archived recently (within last 7 days)
            archive_key = self._get_archive_key(url)
            if archive_key in self.index:
                latest = self.index[archive_key].get('latest')
                if latest:
                    latest_dt = datetime.fromisoformat(latest)
                    if (datetime.now() - latest_dt).days < 7:
                        stats['already_archived'] += 1
                        logger.debug(f"Skipping recently archived: {url}")
                        continue
            
            # Archive the bookmark
            result = self.archive_bookmark(bookmark, save_to_wayback=True)
            
            if result:
                stats['archived'] += 1
                if result.get('wayback_url'):
                    stats['wayback_saved'] += 1
            else:
                stats['failed'] += 1
            
            # Progress callback
            if progress_callback:
                progress_callback(i + 1, len(bookmarks), url)
            
            # Rate limiting for Wayback Machine
            time.sleep(1)
        
        return stats
    
    def export_archive_summary(self, output_file: Optional[str] = None) -> str:
        """
        Export a summary of the archive.
        
        Args:
            output_file: Optional file to save to
            
        Returns:
            Summary as markdown
        """
        lines = ["# BTK Archive Summary\n"]
        lines.append(f"Generated: {datetime.now().isoformat()}\n")
        
        total_urls = len(self.index)
        total_versions = sum(len(info.get('versions', [])) for info in self.index.values())
        
        lines.append(f"- **Total URLs archived:** {total_urls}")
        lines.append(f"- **Total versions:** {total_versions}")
        lines.append(f"- **Archive location:** {self.archive_dir}\n")
        
        lines.append("## Archived URLs\n")
        
        for archive_key, info in sorted(self.index.items(), 
                                      key=lambda x: x[1].get('latest', ''), 
                                      reverse=True):
            url = info['url']
            versions = info.get('versions', [])
            latest = info.get('latest', 'unknown')
            
            lines.append(f"### {url}\n")
            lines.append(f"- **Versions:** {len(versions)}")
            lines.append(f"- **Latest:** {latest}")
            
            # List recent versions
            recent = versions[-3:] if len(versions) > 3 else versions
            if recent:
                lines.append("- **Recent snapshots:**")
                for v in reversed(recent):
                    wb = " ([Wayback](" + v['wayback_url'] + "))" if v.get('wayback_url') else ""
                    lines.append(f"  - {v['timestamp']}{wb}")
            lines.append("")
        
        summary = "\n".join(lines)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            logger.info(f"Exported archive summary to {output_file}")
        
        return summary


# Global archiver instance
_archiver = None


def get_archiver() -> BookmarkArchiver:
    """Get the global archiver instance."""
    global _archiver
    if _archiver is None:
        _archiver = BookmarkArchiver()
    return _archiver