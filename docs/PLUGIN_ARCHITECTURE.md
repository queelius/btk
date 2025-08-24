# BTK Plugin Architecture

## Overview

BTK uses a plugin architecture to keep the core lightweight while allowing powerful extensions through optional dependencies. This document describes the design decisions, motivations, and implementation details.

## Design Philosophy

### Core Principles

1. **Minimal Core**: The core BTK package contains only essential bookmark management functionality
2. **Optional Extensions**: Advanced features are provided as optional "extras" installable via pip
3. **Clean Separation**: Plugins live in the `integrations/` directory, separate from core
4. **No Import Side Effects**: Plugins register explicitly, not at import time
5. **Type Safety**: All plugins implement well-defined interfaces (ABCs)
6. **Testability**: Registry is instantiable, not global, making testing predictable

### Why This Architecture?

**Problem**: Traditional monolithic tools become bloated with features that not all users need, leading to:
- Heavy dependency chains
- Slow startup times  
- Complex installation requirements
- Difficult testing
- Poor maintainability

**Solution**: Our plugin architecture addresses these issues by:
- Installing only what you need: `pip install btk` for basics, `pip install btk[cache,ai]` for more
- Keeping dependencies isolated to their respective plugins
- Allowing third-party extensions without modifying core
- Making testing straightforward with mockable registries

## Installation Patterns

### Basic Installation
```bash
pip install btk  # Core functionality only
```

### With Specific Features
```bash
pip install btk[cache]        # Add content caching
pip install btk[archive]      # Add permanent archiving  
pip install btk[ai]          # Add AI-powered features
pip install btk[cache,archive,ai]  # Multiple features
```

### All Features
```bash
pip install btk[all]  # Install everything
```

## Project Structure

```
btk/
├── __init__.py
├── cli.py              # CLI interface
├── tools.py            # Core tools
├── utils.py            # Utilities
├── plugins.py          # Plugin system (registry, interfaces)
└── constants.py        # Core constants

integrations/           # Optional features (pip extras)
├── __init__.py
├── cache/             # btk[cache]
│   ├── __init__.py
│   ├── content_cache.py
│   └── register.py    # Plugin registration
├── archive/           # btk[archive]
│   ├── __init__.py
│   ├── archiver.py
│   └── register.py
├── extract/           # btk[extract]
│   ├── __init__.py
│   ├── content_extractor.py
│   ├── tag_suggester.py
│   └── register.py
└── ai/                # btk[ai]
    ├── __init__.py
    ├── ai_tagger.py
    └── register.py
```

## Plugin Interfaces

All plugins implement one of these interfaces:

```python
class TagSuggester(Plugin):
    """Suggests tags for bookmarks"""
    
class ContentExtractor(Plugin):
    """Extracts content from URLs"""
    
class SimilarityFinder(Plugin):
    """Finds similar bookmarks"""
    
class SearchEnhancer(Plugin):
    """Enhances search capabilities"""
    
class BookmarkEnricher(Plugin):
    """Enriches bookmarks with metadata"""
```

## Creating a Plugin

### 1. Implement the Interface

```python
# integrations/myfeature/my_plugin.py
from btk.plugins import Plugin, TagSuggester, PluginMetadata

class MyTagSuggester(TagSuggester):
    @property
    def metadata(self):
        return PluginMetadata(
            name="my_tagger",
            version="1.0.0",
            author="Your Name",
            description="Advanced ML-based tag suggestions",
            priority=75  # Higher priority than default
        )
    
    def suggest_tags(self, url, title=None, content=None, description=None):
        # Your implementation here
        return ["tag1", "tag2"]
    
    def validate(self):
        # Check if dependencies are available
        try:
            import tensorflow
            return True
        except ImportError:
            return False
```

### 2. Register the Plugin

```python
# integrations/myfeature/register.py
def register_plugins(registry):
    """Register all plugins from this integration."""
    from .my_plugin import MyTagSuggester
    
    registry.register(MyTagSuggester())
```

### 3. Update setup.py

```python
extras_require={
    'myfeature': ['tensorflow>=2.0'],
    # ... other extras
}
```

## Plugin Registry

The registry manages all plugins and provides a clean API:

```python
from btk.plugins import PluginRegistry

# Create registry (done automatically by BTK)
registry = PluginRegistry()

# Register a plugin
registry.register(my_plugin, 'tag_suggester')

# Get plugins
taggers = registry.get_plugins('tag_suggester')  # All enabled taggers
tagger = registry.get_plugin('tag_suggester')    # Highest priority tagger

# Check features
if registry.has_feature('tag_suggester:ml_tagger'):
    # ML tagger is available
    pass

# Plugin management
registry.set_plugin_enabled('tag_suggester', 'ml_tagger', False)
registry.unregister('tag_suggester', 'ml_tagger')
```

## Hooks System

Plugins can register hooks for events:

```python
def on_bookmark_added(bookmark):
    """Called when a bookmark is added"""
    # Auto-tag, fetch content, etc.
    pass

registry.register_hook('bookmark.added', on_bookmark_added)

# In core code:
results = registry.trigger_hook('bookmark.added', bookmark)
```

## Priority System

Plugins have priorities (0-100) that determine order of use:

- **0-24**: Low priority (fallback implementations)
- **25-49**: Below normal
- **50**: Normal (default)
- **51-74**: Above normal  
- **75-100**: High priority (preferred implementations)

When multiple plugins provide the same functionality, the highest priority wins.

## Version Compatibility

Plugins declare their required BTK API version:

```python
metadata = PluginMetadata(
    name="my_plugin",
    version="1.0.0",
    btk_version_required="1.0"  # Major version must match
)
```

This prevents incompatible plugins from loading.

## Testing Plugins

The registry is instantiable, making testing straightforward:

```python
def test_my_plugin():
    # Create isolated registry for testing
    registry = PluginRegistry()
    
    # Register your plugin
    plugin = MyTagSuggester()
    registry.register(plugin)
    
    # Test it
    assert registry.get_plugin('tag_suggester') == plugin
    
    # Clean up
    registry.clear()
```

## Security Considerations

### What We DON'T Do

- **No arbitrary code execution**: We don't load Python files from `~/.btk/plugins`
- **No eval/exec**: No dynamic code execution
- **No auto-discovery**: Plugins must be explicitly installed via pip

### What We DO

- **Explicit installation**: Plugins installed via pip are trusted
- **Dependency management**: pip handles security updates
- **Validation**: Plugins validate their dependencies are available
- **Sandboxing**: Each plugin is isolated in its module


## Best Practices

1. **Keep plugins focused**: One plugin should do one thing well
2. **Fail gracefully**: Use `validate()` to check dependencies
3. **Document dependencies**: List all requirements in metadata
4. **Use appropriate priority**: Don't use HIGH unless necessary
5. **Version your plugins**: Follow semantic versioning
6. **Test in isolation**: Create new registry for each test
7. **Log appropriately**: Use logger, not print statements

## Future Enhancements

Potential future improvements (not yet implemented):

- Plugin marketplace/repository
- Automatic dependency installation
- Plugin configuration files
- Remote plugin loading (with signatures)
- Plugin sandboxing/permissions
- Performance profiling per plugin
- Plugin compatibility matrix

## FAQ

**Q: Why not use existing plugin systems like setuptools entry points?**
A: Entry points are great for discovery but have limitations:
- Harder to control load order (priority)
- No built-in validation
- Less control over registration timing
- More complex for users to understand

**Q: Can third parties create plugins?**
A: Yes! They can either:
1. Submit PRs to add to `integrations/`
2. Create separate packages that use our plugin interfaces

**Q: How do I debug plugin issues?**
A: Enable debug logging:
```python
import logging
logging.getLogger('btk.plugins').setLevel(logging.DEBUG)
```

**Q: What if two plugins conflict?**
A: Use priority to control which is preferred, or disable one:
```python
registry.set_plugin_enabled('tag_suggester', 'conflicting_plugin', False)
```