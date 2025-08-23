"""
BTK Plugin Architecture

This module provides the plugin system for BTK, allowing integrations to extend
core functionality without modifying the core codebase.

The plugin system uses abstract base classes to define interfaces that integrations
can implement. Core BTK can then use these implementations when available.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================================
# Plugin Interfaces
# ============================================================================

class TagSuggester(ABC):
    """Interface for tag suggestion implementations."""
    
    @abstractmethod
    def suggest_tags(self, url: str, title: str = None, content: str = None, 
                    description: str = None) -> List[str]:
        """
        Suggest tags for a bookmark based on its content.
        
        Args:
            url: The bookmark URL
            title: Optional page title
            content: Optional page content (text)
            description: Optional bookmark description
            
        Returns:
            List of suggested tags
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this tag suggester."""
        pass


class ContentExtractor(ABC):
    """Interface for content extraction implementations."""
    
    @abstractmethod
    def extract(self, url: str) -> Dict[str, Any]:
        """
        Extract content from a URL.
        
        Args:
            url: The URL to extract content from
            
        Returns:
            Dictionary with extracted content:
                - title: Page title
                - text: Main text content
                - description: Meta description
                - keywords: Meta keywords
                - author: Author if available
                - published_date: Publication date if available
                - reading_time: Estimated reading time in minutes
                - word_count: Number of words
                - language: Detected language
                - images: List of image URLs
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this content extractor."""
        pass


class SimilarityFinder(ABC):
    """Interface for finding similar bookmarks."""
    
    @abstractmethod
    def find_similar(self, bookmark: Dict[str, Any], bookmarks: List[Dict[str, Any]], 
                    threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Find bookmarks similar to the given bookmark.
        
        Args:
            bookmark: The reference bookmark
            bookmarks: List of bookmarks to search
            threshold: Similarity threshold (0-1)
            
        Returns:
            List of similar bookmarks with similarity scores
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this similarity finder."""
        pass


class SearchEnhancer(ABC):
    """Interface for enhanced search implementations."""
    
    @abstractmethod
    def search(self, query: str, bookmarks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Perform enhanced search on bookmarks.
        
        Args:
            query: Search query (can be natural language)
            bookmarks: List of bookmarks to search
            
        Returns:
            List of matching bookmarks ranked by relevance
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this search enhancer."""
        pass


class BookmarkEnricher(ABC):
    """Interface for bookmark enrichment (adding metadata)."""
    
    @abstractmethod
    def enrich(self, bookmark: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a bookmark with additional metadata.
        
        Args:
            bookmark: The bookmark to enrich
            
        Returns:
            Enriched bookmark with additional fields
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this enricher."""
        pass


# ============================================================================
# Plugin Registry
# ============================================================================

@dataclass
class Plugin:
    """Container for plugin metadata."""
    name: str
    type: str
    instance: Any
    priority: int = 0  # Higher priority plugins are used first
    enabled: bool = True


class PluginRegistry:
    """Central registry for all plugins."""
    
    def __init__(self):
        self._plugins: Dict[str, List[Plugin]] = {
            'tag_suggester': [],
            'content_extractor': [],
            'similarity_finder': [],
            'search_enhancer': [],
            'bookmark_enricher': [],
        }
        self._features: Set[str] = set()
        self._hooks: Dict[str, List[Callable]] = {}
    
    def register(self, plugin_type: str, instance: Any, name: str = None, 
                priority: int = 0) -> None:
        """
        Register a plugin instance.
        
        Args:
            plugin_type: Type of plugin (e.g., 'tag_suggester')
            instance: The plugin instance
            name: Optional name override
            priority: Plugin priority (higher = used first)
        """
        if plugin_type not in self._plugins:
            raise ValueError(f"Unknown plugin type: {plugin_type}")
        
        plugin_name = name or getattr(instance, 'name', instance.__class__.__name__)
        
        plugin = Plugin(
            name=plugin_name,
            type=plugin_type,
            instance=instance,
            priority=priority,
            enabled=True
        )
        
        self._plugins[plugin_type].append(plugin)
        self._plugins[plugin_type].sort(key=lambda p: p.priority, reverse=True)
        
        # Add feature flag
        self._features.add(plugin_type)
        self._features.add(f"{plugin_type}:{plugin_name}")
        
        logger.info(f"Registered {plugin_type}: {plugin_name} (priority: {priority})")
    
    def get_plugins(self, plugin_type: str, enabled_only: bool = True) -> List[Any]:
        """
        Get all plugins of a specific type.
        
        Args:
            plugin_type: Type of plugin to retrieve
            enabled_only: Only return enabled plugins
            
        Returns:
            List of plugin instances
        """
        if plugin_type not in self._plugins:
            return []
        
        plugins = self._plugins[plugin_type]
        if enabled_only:
            plugins = [p for p in plugins if p.enabled]
        
        return [p.instance for p in plugins]
    
    def get_plugin(self, plugin_type: str, name: str = None) -> Optional[Any]:
        """
        Get a specific plugin or the highest priority one.
        
        Args:
            plugin_type: Type of plugin
            name: Optional specific plugin name
            
        Returns:
            Plugin instance or None
        """
        plugins = self.get_plugins(plugin_type)
        
        if not plugins:
            return None
        
        if name:
            for plugin in self._plugins[plugin_type]:
                if plugin.name == name and plugin.enabled:
                    return plugin.instance
            return None
        
        return plugins[0]  # Return highest priority
    
    def has_feature(self, feature: str) -> bool:
        """Check if a feature is available."""
        return feature in self._features
    
    def list_features(self) -> List[str]:
        """List all available features."""
        return sorted(list(self._features))
    
    def disable_plugin(self, plugin_type: str, name: str) -> bool:
        """Disable a specific plugin."""
        for plugin in self._plugins[plugin_type]:
            if plugin.name == name:
                plugin.enabled = False
                return True
        return False
    
    def enable_plugin(self, plugin_type: str, name: str) -> bool:
        """Enable a specific plugin."""
        for plugin in self._plugins[plugin_type]:
            if plugin.name == name:
                plugin.enabled = True
                return True
        return False
    
    # Hook system for event-based plugins
    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)
    
    def trigger_hook(self, event: str, *args, **kwargs) -> List[Any]:
        """Trigger all callbacks for an event."""
        results = []
        for callback in self._hooks.get(event, []):
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {callback.__name__} failed for event {event}: {e}")
        return results


# Global registry instance
_registry = PluginRegistry()


# ============================================================================
# Public API
# ============================================================================

def register_plugin(plugin_type: str, instance: Any, name: str = None, 
                   priority: int = 0) -> None:
    """Register a plugin with the global registry."""
    _registry.register(plugin_type, instance, name, priority)


def get_plugins(plugin_type: str) -> List[Any]:
    """Get all plugins of a specific type."""
    return _registry.get_plugins(plugin_type)


def get_plugin(plugin_type: str, name: str = None) -> Optional[Any]:
    """Get a specific plugin or the highest priority one."""
    return _registry.get_plugin(plugin_type, name)


def has_feature(feature: str) -> bool:
    """Check if a feature is available."""
    return _registry.has_feature(feature)


def list_features() -> List[str]:
    """List all available features."""
    return _registry.list_features()


def register_hook(event: str, callback: Callable) -> None:
    """Register a callback for an event."""
    _registry.register_hook(event, callback)


def trigger_hook(event: str, *args, **kwargs) -> List[Any]:
    """Trigger all callbacks for an event."""
    return _registry.trigger_hook(event, *args, **kwargs)


# ============================================================================
# Built-in Core Implementations
# ============================================================================

class DomainBasedTagSuggester(TagSuggester):
    """Simple domain-based tag suggester (built into core)."""
    
    def __init__(self):
        self.domain_rules = {
            'github.com': ['code', 'development'],
            'stackoverflow.com': ['qa', 'programming'],
            'arxiv.org': ['research', 'paper'],
            'youtube.com': ['video'],
            'wikipedia.org': ['reference'],
            'reddit.com': ['discussion', 'community'],
            'medium.com': ['article', 'blog'],
            'twitter.com': ['social'],
            'linkedin.com': ['professional', 'network'],
            'news.ycombinator.com': ['tech', 'news'],
        }
    
    def suggest_tags(self, url: str, title: str = None, content: str = None,
                    description: str = None) -> List[str]:
        """Suggest tags based on domain."""
        tags = []
        
        # Extract domain
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        domain = domain.replace('www.', '')
        
        # Apply domain rules
        if domain in self.domain_rules:
            tags.extend(self.domain_rules[domain])
        
        # Extract from URL path
        path = urlparse(url).path.lower()
        if '/blog/' in path or '/posts/' in path:
            tags.append('blog')
        if '/docs/' in path or '/documentation/' in path:
            tags.append('documentation')
        if '/api/' in path:
            tags.append('api')
        if '/tutorial/' in path or '/guide/' in path:
            tags.append('tutorial')
        
        # Simple keyword extraction from title
        if title:
            title_lower = title.lower()
            keywords = {
                'python': 'python',
                'javascript': 'javascript',
                'react': 'react',
                'vue': 'vue',
                'machine learning': 'ml',
                'artificial intelligence': 'ai',
                'data science': 'data-science',
                'web development': 'webdev',
                'tutorial': 'tutorial',
                'guide': 'guide',
                'introduction': 'intro',
                'advanced': 'advanced',
            }
            for keyword, tag in keywords.items():
                if keyword in title_lower:
                    tags.append(tag)
        
        return list(set(tags))  # Remove duplicates
    
    @property
    def name(self) -> str:
        return "domain_based"


class KeywordTagSuggester(TagSuggester):
    """Simple keyword-based tag suggester (built into core)."""
    
    def suggest_tags(self, url: str, title: str = None, content: str = None,
                    description: str = None) -> List[str]:
        """Extract tags from keywords in title and description."""
        tags = []
        
        # Combine all text
        text = ' '.join(filter(None, [title, description]))
        if not text:
            return tags
        
        # Simple keyword frequency analysis
        import re
        from collections import Counter
        
        # Extract words
        words = re.findall(r'\b[a-z]+\b', text.lower())
        
        # Filter common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 
                    'for', 'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through',
                    'during', 'how', 'when', 'where', 'why', 'what', 'which', 'who',
                    'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had',
                    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
                    'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i',
                    'you', 'he', 'she', 'it', 'we', 'they', 'them', 'their', 'as'}
        
        words = [w for w in words if w not in stopwords and len(w) > 2]
        
        # Get most common words as tags
        word_freq = Counter(words)
        tags = [word for word, _ in word_freq.most_common(5)]
        
        return tags
    
    @property
    def name(self) -> str:
        return "keyword_based"


# Register built-in plugins
register_plugin('tag_suggester', DomainBasedTagSuggester(), priority=10)
register_plugin('tag_suggester', KeywordTagSuggester(), priority=5)


# ============================================================================
# Plugin Discovery
# ============================================================================

def discover_plugins(plugin_dir: Path = None) -> None:
    """
    Discover and load plugins from a directory.
    
    Args:
        plugin_dir: Directory to search for plugins (default: ~/.btk/plugins)
    """
    if plugin_dir is None:
        plugin_dir = Path.home() / '.btk' / 'plugins'
    
    if not plugin_dir.exists():
        return
    
    import importlib.util
    import sys
    
    for plugin_file in plugin_dir.glob('*.py'):
        if plugin_file.name.startswith('_'):
            continue
        
        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(
                f"btk_plugin_{plugin_file.stem}", 
                plugin_file
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            
            # Module should register itself
            logger.info(f"Loaded plugin from {plugin_file}")
            
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_file}: {e}")


# Auto-discover plugins on import
try:
    discover_plugins()
except Exception as e:
    logger.warning(f"Plugin discovery failed: {e}")