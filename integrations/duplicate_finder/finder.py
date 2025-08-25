"""
Advanced duplicate finder for BTK bookmarks.

This module provides sophisticated duplicate detection algorithms that go beyond
simple URL matching to find true duplicates and near-duplicates.
"""

import logging
import re
from typing import Dict, Any, List, Set, Tuple, Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from collections import defaultdict
import hashlib

from btk.plugins import Plugin, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)

# Try to import fuzzy string matching
try:
    from fuzzywuzzy import fuzz
    FUZZYWUZZY_AVAILABLE = True
except ImportError:
    FUZZYWUZZY_AVAILABLE = False
    logger.debug("fuzzywuzzy not available. Install with: pip install fuzzywuzzy")


class DuplicateFinder(Plugin):
    """
    Advanced duplicate finder for bookmarks.
    
    This plugin finds duplicates using multiple strategies:
    - URL normalization and canonicalization
    - Fuzzy title matching
    - Content similarity (if available)
    - Domain grouping for similar pages
    """
    
    def __init__(self, 
                 url_similarity_threshold: float = 0.95,
                 title_similarity_threshold: float = 0.85,
                 content_similarity_threshold: float = 0.90):
        """
        Initialize the duplicate finder.
        
        Args:
            url_similarity_threshold: Threshold for URL similarity (0-1)
            title_similarity_threshold: Threshold for title similarity (0-1)
            content_similarity_threshold: Threshold for content similarity (0-1)
        """
        self._metadata = PluginMetadata(
            name="duplicate_finder",
            version="1.0.0",
            author="BTK Team",
            description="Advanced duplicate detection with fuzzy matching",
            priority=PluginPriority.NORMAL.value
        )
        
        self.url_threshold = url_similarity_threshold
        self.title_threshold = title_similarity_threshold
        self.content_threshold = content_similarity_threshold
        
        # Compile regex patterns
        self.tracking_params = re.compile(r'(utm_[^&]+|fbclid|gclid|ref|source)=[^&]+&?')
        self.protocol_pattern = re.compile(r'^https?://')
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def find_duplicates(self, bookmarks: List[Dict[str, Any]], 
                       strategies: List[str] = None) -> Dict[str, List[List[Dict[str, Any]]]]:
        """
        Find duplicate bookmarks using multiple strategies.
        
        Args:
            bookmarks: List of bookmarks to check
            strategies: List of strategies to use (default: all)
                       Options: 'exact_url', 'normalized_url', 'fuzzy_title', 
                               'content_hash', 'domain_similar'
        
        Returns:
            Dictionary mapping strategy names to lists of duplicate groups
        """
        if strategies is None:
            strategies = ['exact_url', 'normalized_url', 'fuzzy_title']
            if any('content' in b for b in bookmarks):
                strategies.append('content_hash')
        
        results = {}
        
        for strategy in strategies:
            if strategy == 'exact_url':
                results[strategy] = self._find_exact_url_duplicates(bookmarks)
            elif strategy == 'normalized_url':
                results[strategy] = self._find_normalized_url_duplicates(bookmarks)
            elif strategy == 'fuzzy_title':
                results[strategy] = self._find_fuzzy_title_duplicates(bookmarks)
            elif strategy == 'content_hash':
                results[strategy] = self._find_content_duplicates(bookmarks)
            elif strategy == 'domain_similar':
                results[strategy] = self._find_domain_similar(bookmarks)
            else:
                logger.warning(f"Unknown strategy: {strategy}")
        
        return results
    
    def _find_exact_url_duplicates(self, bookmarks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Find bookmarks with exactly the same URL."""
        url_groups = defaultdict(list)
        
        for bookmark in bookmarks:
            url = bookmark.get('url', '')
            if url:
                url_groups[url].append(bookmark)
        
        # Return groups with more than one bookmark
        return [group for group in url_groups.values() if len(group) > 1]
    
    def _find_normalized_url_duplicates(self, bookmarks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Find bookmarks with the same normalized URL."""
        url_groups = defaultdict(list)
        
        for bookmark in bookmarks:
            url = bookmark.get('url', '')
            if url:
                normalized = self._normalize_url(url)
                url_groups[normalized].append(bookmark)
        
        return [group for group in url_groups.values() if len(group) > 1]
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize a URL for comparison.
        
        This removes tracking parameters, normalizes protocol,
        removes fragments, and sorts query parameters.
        """
        try:
            # Parse URL
            parsed = urlparse(url.lower())
            
            # Remove tracking parameters
            if parsed.query:
                query = self.tracking_params.sub('', parsed.query)
                # Parse and sort remaining parameters
                params = parse_qs(query, keep_blank_values=True)
                sorted_params = sorted(params.items())
                query = urlencode(sorted_params, doseq=True)
            else:
                query = ''
            
            # Rebuild URL without fragment and with normalized components
            normalized = urlunparse((
                'https',  # Normalize to https
                parsed.netloc.replace('www.', ''),  # Remove www
                parsed.path.rstrip('/'),  # Remove trailing slash
                '',  # params (rarely used)
                query,
                ''  # no fragment
            ))
            
            return normalized
            
        except Exception as e:
            logger.debug(f"Error normalizing URL {url}: {e}")
            return url
    
    def _find_fuzzy_title_duplicates(self, bookmarks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Find bookmarks with similar titles."""
        if not FUZZYWUZZY_AVAILABLE:
            logger.info("Fuzzy title matching not available without fuzzywuzzy")
            return []
        
        # Group by domain first to reduce comparisons
        domain_groups = defaultdict(list)
        for bookmark in bookmarks:
            url = bookmark.get('url', '')
            if url:
                try:
                    domain = urlparse(url).netloc
                    domain_groups[domain].append(bookmark)
                except:
                    pass
        
        duplicate_groups = []
        
        # Check for similar titles within each domain
        for domain, domain_bookmarks in domain_groups.items():
            if len(domain_bookmarks) < 2:
                continue
            
            # Track which bookmarks have been grouped
            grouped = set()
            
            for i, bookmark1 in enumerate(domain_bookmarks):
                if i in grouped:
                    continue
                
                title1 = bookmark1.get('title', '')
                if not title1:
                    continue
                
                group = [bookmark1]
                grouped.add(i)
                
                for j, bookmark2 in enumerate(domain_bookmarks[i+1:], i+1):
                    if j in grouped:
                        continue
                    
                    title2 = bookmark2.get('title', '')
                    if not title2:
                        continue
                    
                    # Calculate similarity
                    similarity = fuzz.ratio(title1, title2) / 100.0
                    
                    if similarity >= self.title_threshold:
                        group.append(bookmark2)
                        grouped.add(j)
                
                if len(group) > 1:
                    duplicate_groups.append(group)
        
        return duplicate_groups
    
    def _find_content_duplicates(self, bookmarks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Find bookmarks with identical or very similar content."""
        content_groups = defaultdict(list)
        
        for bookmark in bookmarks:
            content = bookmark.get('content', '')
            if content:
                # Create content hash
                content_hash = self._get_content_hash(content)
                content_groups[content_hash].append(bookmark)
        
        return [group for group in content_groups.values() if len(group) > 1]
    
    def _get_content_hash(self, content: str) -> str:
        """
        Create a hash of content for comparison.
        
        This normalizes whitespace and creates a hash.
        """
        # Normalize whitespace
        normalized = ' '.join(content.split())
        
        # Take first 1000 chars for efficiency (most duplicates will match here)
        normalized = normalized[:1000]
        
        # Create hash
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _find_domain_similar(self, bookmarks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        Find similar pages from the same domain.
        
        This is useful for finding different versions of the same content,
        like blog posts that have been republished or moved.
        """
        domain_groups = defaultdict(list)
        
        # Group by domain
        for bookmark in bookmarks:
            url = bookmark.get('url', '')
            if url:
                try:
                    domain = urlparse(url).netloc
                    domain_groups[domain].append(bookmark)
                except:
                    pass
        
        similar_groups = []
        
        # Look for similar pages within each domain
        for domain, domain_bookmarks in domain_groups.items():
            if len(domain_bookmarks) < 2:
                continue
            
            # Check for similar paths
            path_groups = defaultdict(list)
            for bookmark in domain_bookmarks:
                url = bookmark.get('url', '')
                try:
                    path = urlparse(url).path
                    # Extract base path (remove numbers, dates, etc.)
                    base_path = re.sub(r'/\d+', '/NUM', path)
                    base_path = re.sub(r'/\d{4}/\d{2}/\d{2}', '/DATE', base_path)
                    path_groups[base_path].append(bookmark)
                except:
                    pass
            
            # Add groups with similar paths
            for group in path_groups.values():
                if len(group) > 1:
                    similar_groups.append(group)
        
        return similar_groups
    
    def merge_duplicates(self, duplicate_group: List[Dict[str, Any]], 
                        strategy: str = 'merge_all') -> Dict[str, Any]:
        """
        Merge a group of duplicate bookmarks into one.
        
        Args:
            duplicate_group: List of duplicate bookmarks
            strategy: Merge strategy
                     'merge_all': Combine all information
                     'keep_first': Keep first bookmark
                     'keep_most_complete': Keep most complete bookmark
                     'keep_most_visited': Keep most visited bookmark
        
        Returns:
            Merged bookmark
        """
        if not duplicate_group:
            return {}
        
        if strategy == 'keep_first':
            return duplicate_group[0].copy()
        
        elif strategy == 'keep_most_visited':
            return max(duplicate_group, key=lambda b: b.get('visit_count', 0)).copy()
        
        elif strategy == 'keep_most_complete':
            # Score by completeness
            def completeness_score(bookmark):
                score = 0
                if bookmark.get('title'): score += 2
                if bookmark.get('description'): score += 3
                if bookmark.get('tags'): score += len(bookmark['tags'])
                if bookmark.get('content'): score += 5
                if bookmark.get('favicon'): score += 1
                return score
            
            return max(duplicate_group, key=completeness_score).copy()
        
        else:  # merge_all
            # Start with the most complete bookmark
            merged = self.merge_duplicates(duplicate_group, 'keep_most_complete')
            
            # Merge additional information
            all_tags = set()
            total_visits = 0
            all_descriptions = []
            
            for bookmark in duplicate_group:
                # Merge tags
                all_tags.update(bookmark.get('tags', []))
                
                # Sum visit counts
                total_visits += bookmark.get('visit_count', 0)
                
                # Collect descriptions
                desc = bookmark.get('description', '').strip()
                if desc and desc not in all_descriptions:
                    all_descriptions.append(desc)
                
                # Keep earliest added date
                if bookmark.get('added'):
                    if not merged.get('added') or bookmark['added'] < merged['added']:
                        merged['added'] = bookmark['added']
                
                # Keep any star
                if bookmark.get('stars'):
                    merged['stars'] = True
            
            # Apply merged data
            merged['tags'] = sorted(list(all_tags))
            merged['visit_count'] = total_visits
            
            # Combine descriptions if multiple
            if len(all_descriptions) > 1:
                merged['description'] = ' | '.join(all_descriptions)
            elif all_descriptions:
                merged['description'] = all_descriptions[0]
            
            # Add merge metadata
            merged['merged_from'] = len(duplicate_group)
            merged['merge_strategy'] = strategy
            
            return merged
    
    def get_duplicate_stats(self, bookmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about duplicates in the bookmark collection.
        
        Args:
            bookmarks: List of bookmarks
        
        Returns:
            Dictionary with duplicate statistics
        """
        all_duplicates = self.find_duplicates(bookmarks)
        
        stats = {
            'total_bookmarks': len(bookmarks),
            'duplicate_strategies': {}
        }
        
        total_duplicates = set()
        
        for strategy, groups in all_duplicates.items():
            strategy_duplicates = set()
            for group in groups:
                for bookmark in group:
                    bookmark_id = bookmark.get('id') or bookmark.get('unique_id')
                    if bookmark_id:
                        strategy_duplicates.add(bookmark_id)
                        total_duplicates.add(bookmark_id)
            
            stats['duplicate_strategies'][strategy] = {
                'groups': len(groups),
                'duplicates': len(strategy_duplicates),
                'largest_group': max(len(g) for g in groups) if groups else 0
            }
        
        stats['total_duplicates'] = len(total_duplicates)
        stats['duplicate_percentage'] = (len(total_duplicates) / len(bookmarks) * 100) if bookmarks else 0
        
        return stats


def register_plugins(registry):
    """Register the duplicate finder with the plugin registry."""
    finder = DuplicateFinder()
    registry.register(finder, 'duplicate_finder')
    logger.info("Registered advanced duplicate finder")