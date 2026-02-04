"""
Content extraction for BTK bookmarks.

This module provides webpage content extraction functionality to enrich
bookmarks with text content, metadata, and other information from the
actual webpage.
"""

import logging
import re
from typing import Optional, Dict, Any
import requests
from bs4 import BeautifulSoup

from .plugins import ContentExtractor, TagSuggester, PluginMetadata
from .constants import DEFAULT_REQUEST_TIMEOUT
from . import content_cache

logger = logging.getLogger(__name__)


class BasicContentExtractor(ContentExtractor):
    """Basic content extractor using BeautifulSoup (built into core)."""
    
    def __init__(self, timeout: int = DEFAULT_REQUEST_TIMEOUT, use_cache: bool = True):
        self.timeout = timeout
        self.use_cache = use_cache
        self.cache = content_cache.get_cache() if use_cache else None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; BTK/1.0; +https://github.com/queelius/btk)'
        })
    
    def extract(self, url: str, force_fetch: bool = False) -> Dict[str, Any]:
        """
        Extract content from a URL.
        
        Args:
            url: URL to extract from
            force_fetch: Force fetching even if cached
        
        Returns:
            Dictionary with extracted content
        """
        # Check cache first if not forcing fetch
        if self.cache and not force_fetch:
            cached = self.cache.get(url)
            if cached:
                logger.debug(f"Using cached content for {url}")
                return cached
        
        result = {
            'url': url,
            'title': None,
            'text': None,
            'description': None,
            'keywords': None,
            'author': None,
            'published_date': None,
            'reading_time': None,
            'word_count': 0,
            'language': None,
            'images': [],
            'links': [],
            'meta_tags': {}
        }
        
        try:
            # Fetch the page
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract title
            title_tag = soup.find('title')
            if title_tag:
                result['title'] = title_tag.get_text(strip=True)
            
            # Extract meta tags
            meta_tags = {}
            for meta in soup.find_all('meta'):
                name = meta.get('name') or meta.get('property')
                content = meta.get('content')
                if name and content:
                    meta_tags[name] = content
            
            result['meta_tags'] = meta_tags
            
            # Extract description
            if 'description' in meta_tags:
                result['description'] = meta_tags['description']
            elif 'og:description' in meta_tags:
                result['description'] = meta_tags['og:description']
            elif 'twitter:description' in meta_tags:
                result['description'] = meta_tags['twitter:description']
            
            # Extract keywords
            if 'keywords' in meta_tags:
                result['keywords'] = [k.strip() for k in meta_tags['keywords'].split(',')]
            
            # Extract author
            if 'author' in meta_tags:
                result['author'] = meta_tags['author']
            elif 'article:author' in meta_tags:
                result['author'] = meta_tags['article:author']
            
            # Extract published date
            if 'article:published_time' in meta_tags:
                result['published_date'] = meta_tags['article:published_time']
            elif 'publish_date' in meta_tags:
                result['published_date'] = meta_tags['publish_date']
            
            # Extract language
            lang_tag = soup.find('html', lang=True)
            if lang_tag:
                result['language'] = lang_tag.get('lang')
            
            # Extract main text content
            text_content = self._extract_text_content(soup)
            result['text'] = text_content
            
            # Calculate word count and reading time
            if text_content:
                words = text_content.split()
                result['word_count'] = len(words)
                # Average reading speed: 200-250 words per minute
                result['reading_time'] = max(1, round(len(words) / 225))
            
            # Extract images
            images = []
            for img in soup.find_all('img', src=True):
                img_url = img['src']
                if not img_url.startswith('http'):
                    # Make relative URLs absolute
                    from urllib.parse import urljoin
                    img_url = urljoin(url, img_url)
                images.append({
                    'url': img_url,
                    'alt': img.get('alt', ''),
                    'title': img.get('title', '')
                })
            result['images'] = images[:10]  # Limit to 10 images
            
            # Extract links
            links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith('http'):
                    links.append({
                        'url': href,
                        'text': link.get_text(strip=True)[:100]
                    })
            result['links'] = links[:20]  # Limit to 20 links
            
            logger.info(f"Successfully extracted content from {url}")
            
            # Cache the result
            if self.cache:
                self.cache.set(url, result)
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
        except Exception as e:
            logger.error(f"Failed to extract content from {url}: {e}")
        
        return result
    
    def _extract_text_content(self, soup: BeautifulSoup) -> str:
        """
        Extract main text content from the page.
        
        Args:
            soup: BeautifulSoup parsed HTML
            
        Returns:
            Extracted text content
        """
        # Remove script and style elements
        for script in soup(['script', 'style', 'noscript']):
            script.decompose()
        
        # Try to find main content areas
        main_content = None
        
        # Look for common content containers
        content_selectors = [
            'main',
            'article',
            '[role="main"]',
            '.content',
            '#content',
            '.main-content',
            '#main-content',
            '.post-content',
            '.entry-content',
            '.article-content',
            '.blog-content'
        ]
        
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                main_content = content
                break
        
        # If no main content found, use body
        if not main_content:
            main_content = soup.find('body') or soup
        
        # Extract text
        text = main_content.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Limit to reasonable size (e.g., 10000 characters for tagging)
        return text[:10000]
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="basic_content_extractor",
            version="1.0.0",
            description="Basic content extractor using BeautifulSoup",
            dependencies=["beautifulsoup4", "requests"]
        )


class EnhancedTagSuggester(TagSuggester):
    """Enhanced tag suggester that uses extracted content."""
    
    def suggest_tags(self, url: str, title: Optional[str] = None, content: Optional[str] = None,
                    description: Optional[str] = None) -> list[str]:
        """Suggest tags based on extracted content."""
        tags = []
        
        # Use all available text
        all_text = ' '.join(filter(None, [title, description, content]))
        if not all_text:
            return tags
        
        all_text_lower = all_text.lower()
        
        # Programming languages
        languages = {
            'python': ['python', 'py', 'django', 'flask', 'pytest'],
            'javascript': ['javascript', 'js', 'node', 'react', 'vue', 'angular'],
            'typescript': ['typescript', 'ts'],
            'rust': ['rust', 'cargo', 'rustc'],
            'go': ['golang', 'go '],
            'java': ['java ', 'spring', 'junit'],
            'cpp': ['c++', 'cpp', 'stl'],
            'csharp': ['c#', 'csharp', '.net', 'dotnet'],
            'ruby': ['ruby', 'rails'],
            'php': ['php', 'laravel', 'symfony'],
            'swift': ['swift', 'ios', 'xcode'],
            'kotlin': ['kotlin', 'android'],
        }
        
        for tag, keywords in languages.items():
            if any(kw in all_text_lower for kw in keywords):
                tags.append(tag)
        
        # Topics
        topics = {
            'machine-learning': ['machine learning', 'ml ', 'neural network', 'deep learning'],
            'ai': ['artificial intelligence', ' ai ', 'gpt', 'llm', 'transformer'],
            'data-science': ['data science', 'data analysis', 'pandas', 'numpy'],
            'web-development': ['web development', 'frontend', 'backend', 'full stack'],
            'devops': ['devops', 'docker', 'kubernetes', 'ci/cd', 'jenkins'],
            'security': ['security', 'encryption', 'vulnerability', 'penetration testing'],
            'database': ['database', 'sql', 'nosql', 'mongodb', 'postgresql', 'mysql'],
            'cloud': ['cloud', 'aws', 'azure', 'gcp', 'google cloud'],
            'api': ['api', 'rest', 'graphql', 'webhook'],
            'tutorial': ['tutorial', 'guide', 'how to', 'getting started'],
            'documentation': ['documentation', 'docs', 'reference', 'manual'],
            'news': ['news', 'announcement', 'release', 'update'],
            'research': ['research', 'paper', 'study', 'analysis'],
        }
        
        for tag, keywords in topics.items():
            if any(kw in all_text_lower for kw in keywords):
                tags.append(tag)
        
        # Content type detection
        if any(word in all_text_lower for word in ['video', 'youtube', 'watch']):
            tags.append('video')
        if any(word in all_text_lower for word in ['podcast', 'episode', 'listen']):
            tags.append('podcast')
        if any(word in all_text_lower for word in ['book', 'ebook', 'chapter']):
            tags.append('book')
        if any(word in all_text_lower for word in ['course', 'lesson', 'curriculum']):
            tags.append('course')
        
        # Technical terms
        tech_terms = {
            'git': ['git ', 'github', 'gitlab', 'version control'],
            'testing': ['testing', 'test ', 'unittest', 'pytest', 'jest'],
            'debugging': ['debug', 'troubleshoot', 'error', 'bug'],
            'performance': ['performance', 'optimization', 'speed', 'benchmark'],
            'algorithm': ['algorithm', 'data structure', 'complexity', 'big o'],
            'design-pattern': ['design pattern', 'singleton', 'factory', 'observer'],
            'microservices': ['microservice', 'service mesh', 'api gateway'],
            'blockchain': ['blockchain', 'crypto', 'bitcoin', 'ethereum', 'web3'],
        }
        
        for tag, keywords in tech_terms.items():
            if any(kw in all_text_lower for kw in keywords):
                tags.append(tag)
        
        return list(set(tags))  # Remove duplicates
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="enhanced_content",
            version="1.0.0",
            description="Enhanced tag suggester using content analysis",
            priority=20
        )


# Note: Plugins should be registered by the application when needed,
# not at import time. This allows for better testing and configuration.