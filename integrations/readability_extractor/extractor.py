"""
Readability-based content extraction for BTK bookmarks.

This module provides clean content extraction from web pages using
readability algorithms, making bookmarks more searchable and useful.
"""

import re
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from btk.plugins import ContentExtractor, PluginMetadata, PluginPriority

logger = logging.getLogger(__name__)


class ReadabilityExtractor(ContentExtractor):
    """
    Extract clean, readable content from web pages.
    
    This extractor uses readability heuristics to extract the main content
    from web pages, removing ads, navigation, and other clutter.
    """
    
    def __init__(self, timeout: int = 10, max_content_length: int = 50000):
        """
        Initialize the readability extractor.
        
        Args:
            timeout: Request timeout in seconds
            max_content_length: Maximum content length to store
        """
        self._metadata = PluginMetadata(
            name="readability_extractor",
            version="1.0.0",
            author="BTK Team",
            description="Extract clean, readable content from web pages",
            priority=PluginPriority.NORMAL.value
        )
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; BTK/1.0; +https://github.com/btk)'
        })
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Return plugin name."""
        return self._metadata.name
    
    def extract(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Extract content from a URL.
        
        Args:
            url: The URL to extract content from
            **kwargs: Additional extraction options
            
        Returns:
            Dictionary containing extracted content and metadata
        """
        result = {
            'url': url,
            'success': False,
            'error': None,
            'content': None,
            'title': None,
            'author': None,
            'published_date': None,
            'excerpt': None,
            'word_count': 0,
            'reading_time': 0,
            'language': None,
            'domain': urlparse(url).netloc,
            'extracted_at': datetime.utcnow().isoformat()
        }
        
        try:
            # Fetch the page
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract metadata
            result['title'] = self._extract_title(soup)
            result['author'] = self._extract_author(soup)
            result['published_date'] = self._extract_date(soup)
            result['language'] = self._extract_language(soup, response)
            result['excerpt'] = self._extract_excerpt(soup)
            
            # Extract main content
            content = self._extract_content(soup)
            if content:
                # Clean and limit content
                content = self._clean_content(content)
                if len(content) > self.max_content_length:
                    content = content[:self.max_content_length] + "..."
                
                result['content'] = content
                result['word_count'] = len(content.split())
                result['reading_time'] = max(1, result['word_count'] // 250)  # ~250 wpm
                result['success'] = True
            else:
                result['error'] = "Could not extract content"
            
        except requests.RequestException as e:
            result['error'] = f"Failed to fetch URL: {str(e)}"
            logger.warning(f"Failed to fetch {url}: {e}")
        except Exception as e:
            result['error'] = f"Extraction failed: {str(e)}"
            logger.error(f"Error extracting content from {url}: {e}")
        
        return result
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page title."""
        # Try Open Graph first
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content'].strip()
        
        # Try Twitter Card
        twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
        if twitter_title and twitter_title.get('content'):
            return twitter_title['content'].strip()
        
        # Try article title
        article_title = soup.find('h1')
        if article_title:
            return article_title.get_text().strip()
        
        # Fall back to page title
        if soup.title:
            return soup.title.string.strip()
        
        return None
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract author information."""
        # Try meta tags
        for meta_name in ['author', 'article:author', 'twitter:creator']:
            author = soup.find('meta', attrs={'name': meta_name}) or \
                    soup.find('meta', property=meta_name)
            if author and author.get('content'):
                return author['content'].strip()
        
        # Try schema.org
        schema = soup.find('script', type='application/ld+json')
        if schema:
            try:
                import json
                data = json.loads(schema.string)
                if isinstance(data, dict):
                    author = data.get('author')
                    if isinstance(author, dict):
                        return author.get('name')
                    elif isinstance(author, str):
                        return author
            except:
                pass
        
        # Try common author class/id patterns
        for selector in ['.author', '.byline', '.by-author', '#author', '[rel="author"]']:
            author_elem = soup.select_one(selector)
            if author_elem:
                text = author_elem.get_text().strip()
                # Clean common prefixes
                text = re.sub(r'^(by|written by|author:)\s*', '', text, flags=re.IGNORECASE)
                if text:
                    return text
        
        return None
    
    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication date."""
        # Try meta tags
        for meta_name in ['article:published_time', 'publish_date', 'publication_date']:
            date_elem = soup.find('meta', property=meta_name) or \
                       soup.find('meta', attrs={'name': meta_name})
            if date_elem and date_elem.get('content'):
                return date_elem['content']
        
        # Try time element
        time_elem = soup.find('time')
        if time_elem:
            if time_elem.get('datetime'):
                return time_elem['datetime']
            elif time_elem.string:
                return time_elem.string.strip()
        
        return None
    
    def _extract_language(self, soup: BeautifulSoup, response: requests.Response) -> Optional[str]:
        """Extract page language."""
        # Try HTML lang attribute
        if soup.html and soup.html.get('lang'):
            return soup.html['lang'][:2]  # Just the language code
        
        # Try Content-Language header
        content_lang = response.headers.get('Content-Language')
        if content_lang:
            return content_lang[:2]
        
        # Try meta tag
        lang_meta = soup.find('meta', attrs={'http-equiv': 'content-language'})
        if lang_meta and lang_meta.get('content'):
            return lang_meta['content'][:2]
        
        return None
    
    def _extract_excerpt(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract excerpt/description."""
        # Try Open Graph
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            return og_desc['content'].strip()
        
        # Try meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content'].strip()
        
        # Try Twitter Card
        twitter_desc = soup.find('meta', attrs={'name': 'twitter:description'})
        if twitter_desc and twitter_desc.get('content'):
            return twitter_desc['content'].strip()
        
        return None
    
    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract main content using readability heuristics.
        """
        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        
        # Try article tag first
        article = soup.find('article')
        if article:
            return article.get_text()
        
        # Try main tag
        main_elem = soup.find('main')
        if main_elem:
            return main_elem.get_text()
        
        # Try common content containers
        content_selectors = [
            '.content', '.article-content', '.post-content', '.entry-content',
            '#content', '#article', '#main-content', '.main-content',
            '[role="main"]', '.story-body', '.article-body'
        ]
        
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                return content.get_text()
        
        # Fallback: Find the container with the most paragraph tags
        containers = soup.find_all(['div', 'section'], recursive=True)
        best_container = None
        max_p_count = 0
        
        for container in containers:
            # Skip if container has navigation-like classes
            if container.get('class'):
                classes = ' '.join(container.get('class'))
                if any(skip in classes.lower() for skip in ['nav', 'menu', 'sidebar', 'footer', 'header', 'comment']):
                    continue
            
            p_count = len(container.find_all('p', recursive=False))
            if p_count > max_p_count:
                max_p_count = p_count
                best_container = container
        
        if best_container and max_p_count >= 3:
            return best_container.get_text()
        
        # Last resort: get all paragraph text
        paragraphs = soup.find_all('p')
        if len(paragraphs) >= 3:
            return '\n'.join(p.get_text() for p in paragraphs)
        
        return None
    
    def _clean_content(self, content: str) -> str:
        """Clean extracted content."""
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Remove common artifacts
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            # Skip very short lines (likely navigation items)
            if len(line) < 20:
                continue
            # Skip lines that look like menu items
            if re.match(r'^(Home|About|Contact|Privacy|Terms|Subscribe|Share|Tweet|Pin)', line):
                continue
            # Skip lines with too many special characters (likely code or data)
            if len(re.findall(r'[^\w\s]', line)) > len(line) * 0.3:
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()


def register_plugins(registry):
    """Register the readability extractor with the plugin registry."""
    extractor = ReadabilityExtractor()
    registry.register(extractor, 'content_extractor')
    logger.info("Registered readability content extractor")