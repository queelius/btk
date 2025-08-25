"""
Social media metadata extractor for BTK bookmarks.

This module extracts Open Graph, Twitter Card, and other social metadata
from web pages to enrich bookmark information.
"""

import logging
import requests
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from btk.plugins import BookmarkEnricher, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


class SocialMetadataExtractor(BookmarkEnricher):
    """
    Extract social media metadata from web pages.
    
    This plugin extracts:
    - Open Graph tags (og:title, og:description, og:image, etc.)
    - Twitter Card tags (twitter:title, twitter:description, etc.)
    - Schema.org structured data
    - Standard meta tags
    """
    
    def __init__(self, timeout: int = 10, user_agent: str = None):
        """
        Initialize the social metadata extractor.
        
        Args:
            timeout: Request timeout in seconds
            user_agent: Custom user agent string
        """
        self._metadata = PluginMetadata(
            name="social_metadata",
            version="1.0.0",
            author="BTK Team",
            description="Extract Open Graph and Twitter Card metadata",
            priority=PluginPriority.HIGH.value
        )
        
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent or 'BTK-Social-Metadata/1.0 (https://github.com/btk)'
        })
    
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
        Enrich a bookmark with social media metadata.
        
        Args:
            bookmark: The bookmark to enrich
            
        Returns:
            Enriched bookmark with social metadata
        """
        url = bookmark.get('url')
        if not url:
            return bookmark
        
        # Skip if already has rich metadata
        if bookmark.get('social_metadata'):
            logger.debug(f"Bookmark already has social metadata: {url}")
            return bookmark
        
        try:
            # Fetch and parse the page
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract all metadata
            metadata = self.extract_all_metadata(soup, url)
            
            if metadata:
                # Enrich bookmark with extracted metadata
                bookmark = self._apply_metadata(bookmark, metadata)
                bookmark['social_metadata'] = metadata
                logger.info(f"Enriched bookmark with social metadata: {url}")
            
        except requests.RequestException as e:
            logger.debug(f"Failed to fetch {url}: {e}")
        except Exception as e:
            logger.warning(f"Error extracting metadata from {url}: {e}")
        
        return bookmark
    
    def extract_all_metadata(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """
        Extract all available metadata from the page.
        
        Args:
            soup: BeautifulSoup parsed HTML
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Dictionary containing all extracted metadata
        """
        metadata = {}
        
        # Extract Open Graph
        og_data = self.extract_open_graph(soup, base_url)
        if og_data:
            metadata['open_graph'] = og_data
        
        # Extract Twitter Card
        twitter_data = self.extract_twitter_card(soup, base_url)
        if twitter_data:
            metadata['twitter_card'] = twitter_data
        
        # Extract standard meta tags
        meta_data = self.extract_meta_tags(soup)
        if meta_data:
            metadata['meta_tags'] = meta_data
        
        # Extract Schema.org JSON-LD
        schema_data = self.extract_schema_org(soup)
        if schema_data:
            metadata['schema_org'] = schema_data
        
        # Extract page info
        page_info = self.extract_page_info(soup, base_url)
        if page_info:
            metadata['page_info'] = page_info
        
        return metadata
    
    def extract_open_graph(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """
        Extract Open Graph metadata.
        
        Args:
            soup: BeautifulSoup parsed HTML
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Dictionary of Open Graph properties
        """
        og_data = {}
        
        # Find all Open Graph meta tags
        og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
        
        for tag in og_tags:
            property_name = tag.get('property', '').replace('og:', '')
            content = tag.get('content', '').strip()
            
            if property_name and content:
                # Handle special cases
                if property_name == 'image':
                    # Resolve relative URLs
                    content = urljoin(base_url, content)
                    # Support multiple images
                    if 'image' in og_data:
                        if isinstance(og_data['image'], list):
                            og_data['image'].append(content)
                        else:
                            og_data['image'] = [og_data['image'], content]
                    else:
                        og_data['image'] = content
                elif property_name in ['image:width', 'image:height', 'image:alt']:
                    # Group image properties
                    if 'image_details' not in og_data:
                        og_data['image_details'] = {}
                    og_data['image_details'][property_name.replace('image:', '')] = content
                else:
                    og_data[property_name] = content
        
        return og_data
    
    def extract_twitter_card(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """
        Extract Twitter Card metadata.
        
        Args:
            soup: BeautifulSoup parsed HTML
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Dictionary of Twitter Card properties
        """
        twitter_data = {}
        
        # Find all Twitter Card meta tags
        twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
        
        for tag in twitter_tags:
            property_name = tag.get('name', '').replace('twitter:', '')
            content = tag.get('content', '').strip()
            
            if property_name and content:
                # Handle image URLs
                if 'image' in property_name:
                    content = urljoin(base_url, content)
                twitter_data[property_name] = content
        
        return twitter_data
    
    def extract_meta_tags(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        Extract standard meta tags.
        
        Args:
            soup: BeautifulSoup parsed HTML
            
        Returns:
            Dictionary of meta tag values
        """
        meta_data = {}
        
        # Standard meta tags to extract
        standard_tags = ['description', 'author', 'keywords', 'generator', 
                         'robots', 'viewport', 'theme-color']
        
        for tag_name in standard_tags:
            tag = soup.find('meta', attrs={'name': tag_name})
            if tag and tag.get('content'):
                meta_data[tag_name] = tag['content'].strip()
        
        # Also check for charset
        charset_tag = soup.find('meta', charset=True)
        if charset_tag:
            meta_data['charset'] = charset_tag.get('charset')
        
        return meta_data
    
    def extract_schema_org(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Extract Schema.org JSON-LD structured data.
        
        Args:
            soup: BeautifulSoup parsed HTML
            
        Returns:
            List of Schema.org objects
        """
        import json
        
        schema_data = []
        
        # Find all JSON-LD script tags
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                schema_data.append(data)
            except json.JSONDecodeError:
                logger.debug("Failed to parse JSON-LD data")
            except Exception as e:
                logger.debug(f"Error extracting Schema.org data: {e}")
        
        return schema_data
    
    def extract_page_info(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """
        Extract general page information.
        
        Args:
            soup: BeautifulSoup parsed HTML
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Dictionary of page information
        """
        page_info = {}
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            page_info['title'] = title_tag.get_text().strip()
        
        # Extract canonical URL
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            page_info['canonical_url'] = urljoin(base_url, canonical['href'])
        
        # Extract favicon
        favicon = soup.find('link', rel=lambda x: x and 'icon' in x.lower())
        if favicon and favicon.get('href'):
            page_info['favicon'] = urljoin(base_url, favicon['href'])
        
        # Extract RSS/Atom feeds
        feeds = []
        for feed in soup.find_all('link', type=['application/rss+xml', 'application/atom+xml']):
            if feed.get('href'):
                feeds.append({
                    'type': feed.get('type'),
                    'title': feed.get('title', ''),
                    'href': urljoin(base_url, feed['href'])
                })
        if feeds:
            page_info['feeds'] = feeds
        
        # Extract language
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            page_info['language'] = html_tag['lang']
        
        return page_info
    
    def _apply_metadata(self, bookmark: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply extracted metadata to enrich the bookmark.
        
        Args:
            bookmark: Original bookmark
            metadata: Extracted metadata
            
        Returns:
            Enriched bookmark
        """
        # Prefer Open Graph title, then Twitter, then page title
        if not bookmark.get('title') or bookmark['title'] == bookmark.get('url'):
            if metadata.get('open_graph', {}).get('title'):
                bookmark['title'] = metadata['open_graph']['title']
            elif metadata.get('twitter_card', {}).get('title'):
                bookmark['title'] = metadata['twitter_card']['title']
            elif metadata.get('page_info', {}).get('title'):
                bookmark['title'] = metadata['page_info']['title']
        
        # Enrich description
        if not bookmark.get('description'):
            if metadata.get('open_graph', {}).get('description'):
                bookmark['description'] = metadata['open_graph']['description']
            elif metadata.get('twitter_card', {}).get('description'):
                bookmark['description'] = metadata['twitter_card']['description']
            elif metadata.get('meta_tags', {}).get('description'):
                bookmark['description'] = metadata['meta_tags']['description']
        
        # Add preview image
        if not bookmark.get('preview_image'):
            if metadata.get('open_graph', {}).get('image'):
                og_image = metadata['open_graph']['image']
                bookmark['preview_image'] = og_image[0] if isinstance(og_image, list) else og_image
            elif metadata.get('twitter_card', {}).get('image'):
                bookmark['preview_image'] = metadata['twitter_card']['image']
        
        # Add site name
        if not bookmark.get('site_name'):
            if metadata.get('open_graph', {}).get('site_name'):
                bookmark['site_name'] = metadata['open_graph']['site_name']
        
        # Add author
        if not bookmark.get('author'):
            if metadata.get('meta_tags', {}).get('author'):
                bookmark['author'] = metadata['meta_tags']['author']
            elif metadata.get('open_graph', {}).get('article:author'):
                bookmark['author'] = metadata['open_graph']['article:author']
        
        # Add published date
        if not bookmark.get('published_date'):
            if metadata.get('open_graph', {}).get('article:published_time'):
                bookmark['published_date'] = metadata['open_graph']['article:published_time']
        
        # Add keywords as tags
        if metadata.get('meta_tags', {}).get('keywords'):
            keywords = metadata['meta_tags']['keywords'].split(',')
            keywords = [k.strip() for k in keywords if k.strip()]
            
            existing_tags = set(bookmark.get('tags', []))
            existing_tags.update(keywords[:5])  # Limit to 5 keywords
            bookmark['tags'] = sorted(list(existing_tags))
        
        # Add language
        if not bookmark.get('language'):
            if metadata.get('page_info', {}).get('language'):
                bookmark['language'] = metadata['page_info']['language']
        
        return bookmark


def register_plugins(registry):
    """Register the social metadata extractor with the plugin registry."""
    extractor = SocialMetadataExtractor()
    registry.register(extractor, 'bookmark_enricher')
    logger.info("Registered social metadata extractor")