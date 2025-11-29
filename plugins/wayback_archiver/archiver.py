"""
Wayback Machine archiver for BTK bookmarks.

This module provides functionality to archive bookmarks to the Internet Archive's
Wayback Machine, ensuring permanent preservation of web content.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import requests
from urllib.parse import quote

from btk.plugins import BookmarkEnricher, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


class WaybackArchiver(BookmarkEnricher):
    """
    Archive bookmarks to the Internet Archive's Wayback Machine.
    
    This plugin submits URLs to the Wayback Machine for archival and
    enriches bookmarks with archive URLs and timestamps.
    """
    
    def __init__(self, timeout: int = 30, rate_limit_delay: float = 1.0):
        """
        Initialize the Wayback archiver.
        
        Args:
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between archive requests to respect rate limits
        """
        self._metadata = PluginMetadata(
            name="wayback_archiver",
            version="1.0.0",
            author="BTK Team",
            description="Archive bookmarks to the Internet Archive's Wayback Machine",
            priority=PluginPriority.LOW.value  # Run after other enrichers
        )
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BTK-Wayback-Archiver/1.0 (https://github.com/btk)'
        })
        
        # API endpoints
        self.save_api = "https://web.archive.org/save/"
        self.availability_api = "https://archive.org/wayback/available"
        self.cdx_api = "http://web.archive.org/cdx/search/cdx"
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def enrich(self, bookmark: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a bookmark with Wayback Machine archive information.
        
        This method:
        1. Checks if the URL is already archived
        2. If not recent, submits it for archival
        3. Adds archive metadata to the bookmark
        
        Args:
            bookmark: The bookmark to enrich
            
        Returns:
            Enriched bookmark with archive metadata
        """
        url = bookmark.get('url')
        if not url:
            return bookmark
        
        # Check existing archive metadata
        wayback_meta = bookmark.get('wayback', {})
        
        # Check if we've recently archived (within 30 days)
        last_archived = wayback_meta.get('last_archived')
        if last_archived:
            try:
                last_date = datetime.fromisoformat(last_archived)
                if datetime.utcnow() - last_date < timedelta(days=30):
                    logger.debug(f"URL {url} was recently archived, skipping")
                    return bookmark
            except:
                pass
        
        # Check current archive status
        archive_info = self.check_archive_status(url)
        
        # Determine if we should archive
        should_archive = False
        if not archive_info:
            should_archive = True
            logger.info(f"URL {url} has never been archived")
        else:
            # Check age of last archive
            last_snapshot = archive_info.get('timestamp')
            if last_snapshot:
                try:
                    # Wayback timestamp format: YYYYMMDDhhmmss
                    snapshot_date = datetime.strptime(last_snapshot, '%Y%m%d%H%M%S')
                    age_days = (datetime.utcnow() - snapshot_date).days
                    if age_days > 30:
                        should_archive = True
                        logger.info(f"URL {url} last archived {age_days} days ago")
                except:
                    pass
        
        # Archive if needed
        if should_archive:
            archive_result = self.archive_url(url)
            if archive_result and archive_result.get('success'):
                wayback_meta['last_archived'] = datetime.utcnow().isoformat()
                wayback_meta['archive_url'] = archive_result.get('archive_url')
                wayback_meta['job_id'] = archive_result.get('job_id')
                logger.info(f"Successfully archived {url}")
            else:
                wayback_meta['last_attempt'] = datetime.utcnow().isoformat()
                wayback_meta['error'] = archive_result.get('error') if archive_result else 'Unknown error'
                logger.warning(f"Failed to archive {url}: {wayback_meta['error']}")
        
        # Add latest snapshot info if available
        if archive_info:
            wayback_meta['latest_snapshot'] = archive_info.get('timestamp')
            wayback_meta['latest_snapshot_url'] = archive_info.get('url')
            wayback_meta['total_snapshots'] = archive_info.get('total_snapshots', 1)
        
        # Update bookmark
        bookmark['wayback'] = wayback_meta
        
        return bookmark
    
    def check_archive_status(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Check if a URL is already archived in the Wayback Machine.
        
        Args:
            url: The URL to check
            
        Returns:
            Archive information if available, None otherwise
        """
        try:
            # Use the availability API
            response = self.session.get(
                self.availability_api,
                params={'url': url},
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            if data.get('archived_snapshots', {}).get('closest'):
                snapshot = data['archived_snapshots']['closest']
                
                # Get total count using CDX API
                total_count = self.get_snapshot_count(url)
                
                return {
                    'available': snapshot.get('available', False),
                    'url': snapshot.get('url'),
                    'timestamp': snapshot.get('timestamp'),
                    'status': snapshot.get('status'),
                    'total_snapshots': total_count
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error checking archive status for {url}: {e}")
            return None
    
    def get_snapshot_count(self, url: str) -> int:
        """
        Get the total number of snapshots for a URL.
        
        Args:
            url: The URL to check
            
        Returns:
            Number of snapshots
        """
        try:
            response = self.session.get(
                self.cdx_api,
                params={
                    'url': url,
                    'showNumPages': 'true'
                },
                timeout=10
            )
            if response.status_code == 200:
                return int(response.text.strip())
        except:
            pass
        return 0
    
    def archive_url(self, url: str) -> Dict[str, Any]:
        """
        Submit a URL to the Wayback Machine for archival.
        
        Args:
            url: The URL to archive
            
        Returns:
            Dictionary with archive result
        """
        result = {
            'success': False,
            'error': None,
            'archive_url': None,
            'job_id': None
        }
        
        try:
            # Rate limiting
            time.sleep(self.rate_limit_delay)
            
            # Submit for archival
            save_url = self.save_api + url
            response = self.session.get(
                save_url,
                timeout=self.timeout,
                allow_redirects=True
            )
            
            # Check if successful (Wayback returns 200 even for some errors)
            if response.status_code == 200:
                # The final URL after redirects is the archive URL
                if 'web.archive.org/web/' in response.url:
                    result['success'] = True
                    result['archive_url'] = response.url
                    
                    # Extract job ID from headers if available
                    job_id = response.headers.get('X-Archive-Job-Id')
                    if job_id:
                        result['job_id'] = job_id
                else:
                    result['error'] = 'Archive request did not redirect to archive URL'
            else:
                result['error'] = f'HTTP {response.status_code}'
                
        except requests.Timeout:
            result['error'] = 'Request timeout'
        except requests.RequestException as e:
            result['error'] = str(e)
        except Exception as e:
            result['error'] = f'Unexpected error: {str(e)}'
            
        return result
    
    def bulk_archive(self, urls: List[str], callback=None) -> Dict[str, Dict[str, Any]]:
        """
        Archive multiple URLs with rate limiting.
        
        Args:
            urls: List of URLs to archive
            callback: Optional callback function(url, result) for progress
            
        Returns:
            Dictionary mapping URLs to their archive results
        """
        results = {}
        
        for i, url in enumerate(urls):
            logger.info(f"Archiving {i+1}/{len(urls)}: {url}")
            
            # Check if already archived recently
            archive_info = self.check_archive_status(url)
            if archive_info and archive_info.get('timestamp'):
                try:
                    # Check age
                    snapshot_date = datetime.strptime(archive_info['timestamp'], '%Y%m%d%H%M%S')
                    age_days = (datetime.utcnow() - snapshot_date).days
                    if age_days < 7:  # Skip if archived within a week
                        results[url] = {
                            'success': True,
                            'skipped': True,
                            'archive_url': archive_info.get('url'),
                            'message': f'Recently archived {age_days} days ago'
                        }
                        if callback:
                            callback(url, results[url])
                        continue
                except:
                    pass
            
            # Archive the URL
            result = self.archive_url(url)
            results[url] = result
            
            if callback:
                callback(url, result)
            
            # Rate limiting between requests
            if i < len(urls) - 1:
                time.sleep(self.rate_limit_delay)
        
        return results


def register_plugins(registry):
    """Register the Wayback archiver with the plugin registry."""
    archiver = WaybackArchiver()
    registry.register(archiver, 'bookmark_enricher')
    logger.info("Registered Wayback Machine archiver")