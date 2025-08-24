"""
BTK Plugin Architecture

A clean, secure plugin system for extending BTK functionality.

Key features:
- Instantiable registry (not global) for better testing
- No import-time side effects
- Version compatibility checking
- Comprehensive error handling and validation
- Type-safe interfaces using ABCs
- Priority-based plugin selection
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set, Callable, Type
from dataclasses import dataclass, field
import logging
from enum import Enum
import inspect

logger = logging.getLogger(__name__)

# Version compatibility
BTK_PLUGIN_API_VERSION = "1.0"


# ============================================================================
# Plugin Metadata
# ============================================================================

@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    author: str = ""
    description: str = ""
    btk_version_required: str = BTK_PLUGIN_API_VERSION
    dependencies: List[str] = field(default_factory=list)
    priority: int = 50  # 0-100, with 50 as default
    enabled: bool = True


class PluginPriority(Enum):
    """Standard priority levels for plugins."""
    LOWEST = 0
    LOW = 25
    NORMAL = 50
    HIGH = 75
    HIGHEST = 100


# ============================================================================
# Plugin Interfaces
# ============================================================================

class Plugin(ABC):
    """Base class for all plugins."""
    
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        pass
    
    def validate(self) -> bool:
        """
        Validate that the plugin is properly configured.
        Override for custom validation logic.
        """
        return True
    
    def on_register(self, registry: 'PluginRegistry') -> None:
        """
        Called when plugin is registered.
        Override for initialization logic.
        """
        pass
    
    def on_unregister(self, registry: 'PluginRegistry') -> None:
        """
        Called when plugin is unregistered.
        Override for cleanup logic.
        """
        pass


class TagSuggester(Plugin):
    """Interface for tag suggestion implementations."""
    
    @abstractmethod
    def suggest_tags(self, url: str, title: str = None, content: str = None, 
                    description: str = None) -> List[str]:
        """Suggest tags for a bookmark based on its content."""
        pass


class ContentExtractor(Plugin):
    """Interface for content extraction implementations."""
    
    @abstractmethod
    def extract(self, url: str, **kwargs) -> Dict[str, Any]:
        """Extract content from a URL."""
        pass


class SimilarityFinder(Plugin):
    """Interface for finding similar bookmarks."""
    
    @abstractmethod
    def find_similar(self, bookmark: Dict[str, Any], bookmarks: List[Dict[str, Any]], 
                    threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Find bookmarks similar to the given bookmark."""
        pass


class SearchEnhancer(Plugin):
    """Interface for enhanced search implementations."""
    
    @abstractmethod
    def search(self, query: str, bookmarks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Perform enhanced search on bookmarks."""
        pass


class BookmarkEnricher(Plugin):
    """Interface for bookmark enrichment."""
    
    @abstractmethod
    def enrich(self, bookmark: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich a bookmark with additional metadata."""
        pass


# ============================================================================
# Plugin Registry
# ============================================================================

class PluginError(Exception):
    """Base exception for plugin-related errors."""
    pass


class PluginVersionError(PluginError):
    """Raised when plugin version is incompatible."""
    pass


class PluginValidationError(PluginError):
    """Raised when plugin validation fails."""
    pass


class PluginRegistry:
    """
    Central registry for all plugins.
    Now instantiable for better testing and isolation.
    """
    
    # Plugin type to interface mapping
    PLUGIN_INTERFACES = {
        'tag_suggester': TagSuggester,
        'content_extractor': ContentExtractor,
        'similarity_finder': SimilarityFinder,
        'search_enhancer': SearchEnhancer,
        'bookmark_enricher': BookmarkEnricher,
    }
    
    def __init__(self, validate_strict: bool = True):
        """
        Initialize the plugin registry.
        
        Args:
            validate_strict: If True, raise errors on validation failures.
                           If False, log warnings and skip invalid plugins.
        """
        self._plugins: Dict[str, List[Plugin]] = {
            plugin_type: [] for plugin_type in self.PLUGIN_INTERFACES
        }
        self._features: Set[str] = set()
        self._hooks: Dict[str, List[Callable]] = {}
        self.validate_strict = validate_strict
    
    def register(self, plugin: Plugin, plugin_type: str = None) -> None:
        """
        Register a plugin instance.
        
        Args:
            plugin: The plugin instance
            plugin_type: Type of plugin (auto-detected if not provided)
            
        Raises:
            PluginError: If plugin type is invalid or validation fails
            PluginVersionError: If plugin requires incompatible BTK version
            PluginValidationError: If plugin validation fails
        """
        # Auto-detect plugin type if not provided
        if plugin_type is None:
            plugin_type = self._detect_plugin_type(plugin)
        
        if plugin_type not in self.PLUGIN_INTERFACES:
            raise PluginError(f"Unknown plugin type: {plugin_type}")
        
        # Validate plugin implements correct interface
        expected_interface = self.PLUGIN_INTERFACES[plugin_type]
        if not isinstance(plugin, expected_interface):
            raise PluginError(
                f"Plugin {plugin.metadata.name} does not implement {expected_interface.__name__}"
            )
        
        # Check version compatibility
        if not self._check_version_compatibility(plugin.metadata.btk_version_required):
            error_msg = (
                f"Plugin {plugin.metadata.name} requires BTK API version "
                f"{plugin.metadata.btk_version_required}, but current version is "
                f"{BTK_PLUGIN_API_VERSION}"
            )
            if self.validate_strict:
                raise PluginVersionError(error_msg)
            else:
                logger.warning(error_msg)
                return
        
        # Validate plugin
        try:
            if not plugin.validate():
                error_msg = f"Plugin {plugin.metadata.name} validation failed"
                if self.validate_strict:
                    raise PluginValidationError(error_msg)
                else:
                    logger.warning(error_msg)
                    return
        except Exception as e:
            error_msg = f"Plugin {plugin.metadata.name} validation error: {e}"
            if self.validate_strict:
                raise PluginValidationError(error_msg) from e
            else:
                logger.warning(error_msg)
                return
        
        # Check for duplicate names
        for existing in self._plugins[plugin_type]:
            if existing.metadata.name == plugin.metadata.name:
                logger.warning(
                    f"Plugin {plugin.metadata.name} already registered for {plugin_type}, "
                    f"replacing"
                )
                self._plugins[plugin_type].remove(existing)
                existing.on_unregister(self)
                break
        
        # Register the plugin
        self._plugins[plugin_type].append(plugin)
        self._plugins[plugin_type].sort(
            key=lambda p: p.metadata.priority, 
            reverse=True
        )
        
        # Update features
        self._features.add(plugin_type)
        self._features.add(f"{plugin_type}:{plugin.metadata.name}")
        
        # Call registration hook
        plugin.on_register(self)
        
        logger.info(
            f"Registered {plugin_type}: {plugin.metadata.name} "
            f"(priority: {plugin.metadata.priority})"
        )
    
    def unregister(self, plugin_type: str, name: str) -> bool:
        """
        Unregister a plugin.
        
        Args:
            plugin_type: Type of plugin
            name: Plugin name
            
        Returns:
            True if plugin was found and unregistered
        """
        if plugin_type not in self._plugins:
            return False
        
        for plugin in self._plugins[plugin_type]:
            if plugin.metadata.name == name:
                plugin.on_unregister(self)
                self._plugins[plugin_type].remove(plugin)
                
                # Update features
                feature_key = f"{plugin_type}:{name}"
                if feature_key in self._features:
                    self._features.remove(feature_key)
                
                # Check if any plugins of this type remain
                if not self._plugins[plugin_type]:
                    self._features.discard(plugin_type)
                
                logger.info(f"Unregistered {plugin_type}: {name}")
                return True
        
        return False
    
    def get_plugins(self, plugin_type: str, enabled_only: bool = True) -> List[Plugin]:
        """Get all plugins of a specific type."""
        if plugin_type not in self._plugins:
            return []
        
        plugins = self._plugins[plugin_type]
        if enabled_only:
            plugins = [p for p in plugins if p.metadata.enabled]
        
        return plugins
    
    def get_plugin(self, plugin_type: str, name: str = None) -> Optional[Plugin]:
        """Get a specific plugin or the highest priority one."""
        plugins = self.get_plugins(plugin_type)
        
        if not plugins:
            return None
        
        if name:
            for plugin in plugins:
                if plugin.metadata.name == name:
                    return plugin
            return None
        
        return plugins[0]  # Return highest priority
    
    def has_feature(self, feature: str) -> bool:
        """Check if a feature is available."""
        return feature in self._features
    
    def list_features(self) -> List[str]:
        """List all available features."""
        return sorted(list(self._features))
    
    def set_plugin_enabled(self, plugin_type: str, name: str, enabled: bool) -> bool:
        """Enable or disable a plugin."""
        for plugin in self._plugins.get(plugin_type, []):
            if plugin.metadata.name == name:
                plugin.metadata.enabled = enabled
                logger.info(f"{'Enabled' if enabled else 'Disabled'} {plugin_type}: {name}")
                return True
        return False
    
    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)
        logger.debug(f"Registered hook for event: {event}")
    
    def unregister_hook(self, event: str, callback: Callable) -> bool:
        """Unregister a callback for an event."""
        if event in self._hooks and callback in self._hooks[event]:
            self._hooks[event].remove(callback)
            if not self._hooks[event]:
                del self._hooks[event]
            logger.debug(f"Unregistered hook for event: {event}")
            return True
        return False
    
    def trigger_hook(self, event: str, *args, **kwargs) -> List[Any]:
        """Trigger all callbacks for an event."""
        results = []
        for callback in self._hooks.get(event, []):
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {callback.__name__} failed for event {event}: {e}")
                if self.validate_strict:
                    raise
        return results
    
    def get_plugin_info(self, plugin_type: str = None) -> Dict[str, Any]:
        """Get information about registered plugins."""
        info = {}
        
        types_to_check = [plugin_type] if plugin_type else self._plugins.keys()
        
        for ptype in types_to_check:
            info[ptype] = []
            for plugin in self._plugins.get(ptype, []):
                info[ptype].append({
                    'name': plugin.metadata.name,
                    'version': plugin.metadata.version,
                    'author': plugin.metadata.author,
                    'description': plugin.metadata.description,
                    'priority': plugin.metadata.priority,
                    'enabled': plugin.metadata.enabled,
                    'dependencies': plugin.metadata.dependencies,
                })
        
        return info
    
    def _detect_plugin_type(self, plugin: Plugin) -> str:
        """Auto-detect plugin type based on inheritance."""
        for plugin_type, interface in self.PLUGIN_INTERFACES.items():
            if isinstance(plugin, interface):
                return plugin_type
        raise PluginError(f"Could not detect plugin type for {plugin.__class__.__name__}")
    
    def _check_version_compatibility(self, required_version: str) -> bool:
        """Check if required version is compatible with current API version."""
        # Simple major version check for now
        # Could be extended with semantic versioning
        current_major = BTK_PLUGIN_API_VERSION.split('.')[0]
        required_major = required_version.split('.')[0]
        return current_major == required_major
    
    def clear(self) -> None:
        """Clear all registered plugins. Useful for testing."""
        for plugin_type in self._plugins:
            for plugin in list(self._plugins[plugin_type]):
                plugin.on_unregister(self)
            self._plugins[plugin_type].clear()
        self._features.clear()
        self._hooks.clear()
        logger.info("Cleared all plugins from registry")


# ============================================================================
# Default Registry Instance (Optional)
# ============================================================================

def create_default_registry() -> PluginRegistry:
    """
    Create a default registry instance.
    This is now a factory function instead of a global variable.
    """
    registry = PluginRegistry(validate_strict=False)
    
    # Load built-in plugins from integrations if available
    try:
        from integrations import load_builtin_plugins
        load_builtin_plugins(registry)
    except ImportError:
        logger.debug("No built-in integrations found")
    
    return registry


# ============================================================================
# Plugin Loading from Integrations
# ============================================================================

def load_integration_plugins(registry: PluginRegistry, integration_names: List[str]) -> None:
    """
    Load plugins from specified integrations.
    
    Args:
        registry: The plugin registry to register to
        integration_names: List of integration names (e.g., ['cache', 'archive'])
    """
    for name in integration_names:
        try:
            # Try to import the integration module
            import importlib
            module = importlib.import_module(f'integrations.{name}')
            
            # Look for a register_plugins function
            if hasattr(module, 'register_plugins'):
                module.register_plugins(registry)
                logger.info(f"Loaded plugins from integration: {name}")
            else:
                logger.warning(f"Integration {name} has no register_plugins function")
                
        except ImportError as e:
            logger.debug(f"Integration {name} not available: {e}")
        except Exception as e:
            logger.error(f"Failed to load integration {name}: {e}")