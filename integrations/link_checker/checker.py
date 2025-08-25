"""
Link checker for BTK bookmarks.

This module provides functionality to check bookmark URLs for availability,
redirects, and other issues, helping maintain bookmark quality.
"""

import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from btk.plugins import Plugin, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


class LinkChecker(Plugin):
    """
    Check bookmark URLs for availability and issues.
    
    This plugin checks URLs for:
    - Dead links (404, 500, etc.)
    - Redirects (permanent and temporary)
    - SSL certificate issues
    - Timeouts
    - Domain changes
    """
    
    def __init__(self, timeout: int = 10, max_workers: int = 5, 
                 follow_redirects: bool = True, verify_ssl: bool = True):
        """
        Initialize the link checker.
        
        Args:
            timeout: Request timeout in seconds
            max_workers: Maximum concurrent workers for checking
            follow_redirects: Whether to follow redirects
            verify_ssl: Whether to verify SSL certificates
        """
        self._metadata = PluginMetadata(
            name="link_checker",
            version="1.0.0",
            author="BTK Team",
            description="Check bookmark URLs for availability and issues",
            priority=PluginPriority.NORMAL.value
        )
        self.timeout = timeout
        self.max_workers = max_workers
        self.follow_redirects = follow_redirects
        self.verify_ssl = verify_ssl
        
        # Session for HTTP requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BTK-Link-Checker/1.0 (https://github.com/btk)'
        })
        
        # Status code categories
        self.status_categories = {
            'success': range(200, 300),
            'redirect': range(300, 400),
            'client_error': range(400, 500),
            'server_error': range(500, 600)
        }
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def check_url(self, url: str) -> Dict[str, Any]:
        """
        Check a single URL for availability and issues.
        
        Args:
            url: The URL to check
            
        Returns:
            Dictionary with check results
        """
        result = {
            'url': url,
            'checked_at': datetime.utcnow().isoformat(),
            'reachable': False,
            'status_code': None,
            'status_category': None,
            'error': None,
            'redirect_chain': [],
            'final_url': url,
            'response_time': None,
            'ssl_valid': None,
            'headers': {}
        }
        
        start_time = time.time()
        
        try:
            # Make request
            response = self.session.head(
                url,
                timeout=self.timeout,
                allow_redirects=self.follow_redirects,
                verify=self.verify_ssl
            )
            
            # Calculate response time
            result['response_time'] = round(time.time() - start_time, 2)
            
            # Basic info
            result['status_code'] = response.status_code
            result['reachable'] = response.status_code < 400
            
            # Categorize status
            for category, range_obj in self.status_categories.items():
                if response.status_code in range_obj:
                    result['status_category'] = category
                    break
            
            # Check for redirects
            if response.history:
                result['redirect_chain'] = [
                    {
                        'url': r.url,
                        'status_code': r.status_code
                    }
                    for r in response.history
                ]
                result['final_url'] = response.url
            
            # Extract useful headers
            useful_headers = [
                'content-type', 'content-length', 'last-modified',
                'etag', 'server', 'x-powered-by'
            ]
            for header in useful_headers:
                if header in response.headers:
                    result['headers'][header] = response.headers[header]
            
            # Check SSL if HTTPS
            if url.startswith('https://'):
                result['ssl_valid'] = True  # If we got here with verify=True, SSL is valid
            
            # For 4xx/5xx errors, try GET to get more info
            if result['status_code'] >= 400:
                try:
                    # Try a GET request for more details
                    get_response = self.session.get(
                        url,
                        timeout=self.timeout,
                        allow_redirects=False,
                        verify=self.verify_ssl
                    )
                    result['status_code'] = get_response.status_code
                    result['reachable'] = get_response.status_code < 400
                except:
                    pass  # Stick with HEAD results
                    
        except requests.exceptions.SSLError as e:
            result['error'] = f'SSL certificate error: {str(e)}'
            result['ssl_valid'] = False
            
        except requests.exceptions.Timeout:
            result['error'] = f'Request timeout after {self.timeout}s'
            result['response_time'] = self.timeout
            
        except requests.exceptions.ConnectionError as e:
            result['error'] = f'Connection error: {str(e)}'
            
        except requests.exceptions.TooManyRedirects:
            result['error'] = 'Too many redirects'
            
        except requests.exceptions.RequestException as e:
            result['error'] = f'Request failed: {str(e)}'
            
        except Exception as e:
            result['error'] = f'Unexpected error: {str(e)}'
            logger.error(f"Unexpected error checking {url}: {e}")
        
        return result
    
    def check_bookmarks(self, bookmarks: List[Dict[str, Any]], 
                       progress_callback=None) -> List[Dict[str, Any]]:
        """
        Check multiple bookmarks for link issues.
        
        Args:
            bookmarks: List of bookmarks to check
            progress_callback: Optional callback(bookmark, result) for progress
            
        Returns:
            List of bookmarks with link check results added
        """
        checked_bookmarks = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all checks
            future_to_bookmark = {
                executor.submit(self.check_url, bookmark['url']): bookmark
                for bookmark in bookmarks
                if bookmark.get('url')
            }
            
            # Process results as they complete
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                
                try:
                    result = future.result()
                    
                    # Add check results to bookmark
                    bookmark['link_check'] = result
                    
                    # Update main reachable field
                    bookmark['reachable'] = result['reachable']
                    
                    # Add to results
                    checked_bookmarks.append(bookmark)
                    
                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(bookmark, result)
                        
                except Exception as e:
                    logger.error(f"Error checking bookmark {bookmark.get('id')}: {e}")
                    bookmark['link_check'] = {
                        'error': str(e),
                        'checked_at': datetime.utcnow().isoformat(),
                        'reachable': False
                    }
                    bookmark['reachable'] = False
                    checked_bookmarks.append(bookmark)
        
        return checked_bookmarks
    
    def find_broken_links(self, bookmarks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Find all broken links in a bookmark collection.
        
        Args:
            bookmarks: List of bookmarks to check
            
        Returns:
            List of bookmarks with broken links
        """
        checked = self.check_bookmarks(bookmarks)
        return [
            b for b in checked 
            if not b.get('link_check', {}).get('reachable', False)
        ]
    
    def find_redirects(self, bookmarks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Find all bookmarks that redirect.
        
        Args:
            bookmarks: List of bookmarks to check
            
        Returns:
            List of bookmarks with redirects
        """
        checked = self.check_bookmarks(bookmarks)
        return [
            b for b in checked 
            if b.get('link_check', {}).get('redirect_chain')
        ]
    
    def suggest_fixes(self, bookmark: Dict[str, Any]) -> Dict[str, Any]:
        """
        Suggest fixes for bookmark issues.
        
        Args:
            bookmark: Bookmark with link_check results
            
        Returns:
            Dictionary with suggested fixes
        """
        fixes = {
            'suggested_actions': [],
            'auto_fixable': False
        }
        
        check = bookmark.get('link_check', {})
        
        if not check:
            fixes['suggested_actions'].append('Run link check first')
            return fixes
        
        # Handle different issues
        if check.get('redirect_chain'):
            final_url = check.get('final_url')
            if final_url and final_url != bookmark['url']:
                fixes['suggested_actions'].append(f'Update URL to: {final_url}')
                fixes['auto_fixable'] = True
                fixes['new_url'] = final_url
        
        status_code = check.get('status_code')
        if status_code:
            if status_code == 404:
                fixes['suggested_actions'].append('Page not found - check Wayback Machine archive')
                # Could add Wayback URL here
            elif status_code == 403:
                fixes['suggested_actions'].append('Access forbidden - may require authentication')
            elif status_code >= 500:
                fixes['suggested_actions'].append('Server error - try again later')
        
        if check.get('ssl_valid') is False:
            fixes['suggested_actions'].append('SSL certificate issue - verify site security')
        
        if check.get('error'):
            if 'timeout' in check['error'].lower():
                fixes['suggested_actions'].append('Site is slow - increase timeout or try later')
            elif 'connection' in check['error'].lower():
                fixes['suggested_actions'].append('Connection failed - site may be down')
        
        return fixes
    
    def generate_report(self, bookmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a comprehensive link check report.
        
        Args:
            bookmarks: List of bookmarks with link_check results
            
        Returns:
            Report dictionary
        """
        report = {
            'total_checked': 0,
            'reachable': 0,
            'broken': 0,
            'redirects': 0,
            'ssl_issues': 0,
            'timeouts': 0,
            'by_status_category': {},
            'broken_links': [],
            'redirect_links': [],
            'slow_links': [],
            'generated_at': datetime.utcnow().isoformat()
        }
        
        for bookmark in bookmarks:
            check = bookmark.get('link_check')
            if not check:
                continue
            
            report['total_checked'] += 1
            
            if check.get('reachable'):
                report['reachable'] += 1
            else:
                report['broken'] += 1
                report['broken_links'].append({
                    'id': bookmark.get('id'),
                    'url': bookmark.get('url'),
                    'title': bookmark.get('title'),
                    'error': check.get('error'),
                    'status_code': check.get('status_code')
                })
            
            if check.get('redirect_chain'):
                report['redirects'] += 1
                report['redirect_links'].append({
                    'id': bookmark.get('id'),
                    'url': bookmark.get('url'),
                    'final_url': check.get('final_url'),
                    'chain_length': len(check['redirect_chain'])
                })
            
            if check.get('ssl_valid') is False:
                report['ssl_issues'] += 1
            
            if check.get('error') and 'timeout' in check['error'].lower():
                report['timeouts'] += 1
            
            # Response time tracking
            response_time = check.get('response_time')
            if response_time and response_time > 5:
                report['slow_links'].append({
                    'id': bookmark.get('id'),
                    'url': bookmark.get('url'),
                    'response_time': response_time
                })
            
            # Status category tracking
            category = check.get('status_category')
            if category:
                report['by_status_category'][category] = \
                    report['by_status_category'].get(category, 0) + 1
        
        # Calculate percentages
        if report['total_checked'] > 0:
            report['reachable_percentage'] = round(
                (report['reachable'] / report['total_checked']) * 100, 2
            )
            report['broken_percentage'] = round(
                (report['broken'] / report['total_checked']) * 100, 2
            )
        
        return report


def register_plugins(registry):
    """Register the link checker with the plugin registry."""
    checker = LinkChecker()
    registry.register(checker, 'plugin')  # Generic plugin type
    logger.info("Registered link checker")