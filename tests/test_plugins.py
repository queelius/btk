"""
Tests for the BTK plugin system.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch
from btk.plugins import (
    PluginRegistry, PluginMetadata, Plugin, PluginError,
    PluginVersionError, PluginValidationError, PluginPriority,
    TagSuggester, ContentExtractor, SimilarityFinder,
    SearchEnhancer, BookmarkEnricher,
    create_default_registry, load_plugins
)


# Test plugin implementations
class MockTagSuggesterPlugin(TagSuggester):
    """Test implementation of TagSuggester."""
    
    def __init__(self):
        self._metadata = PluginMetadata(
            name="test_tagger",
            version="1.0.0",
            author="Test Author",
            description="Test tag suggester",
            priority=50
        )
    
    @property
    def metadata(self):
        return self._metadata
    
    def suggest_tags(self, url, title=None, content=None, description=None):
        return ["test", "tag"]


class MockContentExtractorPlugin(ContentExtractor):
    """Test implementation of ContentExtractor."""
    
    def __init__(self):
        self._metadata = PluginMetadata(
            name="test_extractor",
            version="1.0.0",
            description="Test content extractor"
        )
    
    @property
    def metadata(self):
        return self._metadata
    
    def extract(self, url, **kwargs):
        return {"title": "Test", "content": "Test content"}


class InvalidPlugin(Plugin):
    """Invalid plugin that doesn't implement any interface."""
    
    @property
    def metadata(self):
        return PluginMetadata(name="invalid", version="1.0.0")


class FailingValidationPlugin(TagSuggester):
    """Plugin that fails validation."""
    
    @property
    def metadata(self):
        return PluginMetadata(name="failing", version="1.0.0")
    
    def validate(self):
        return False
    
    def suggest_tags(self, url, title=None, content=None, description=None):
        return []


class IncompatibleVersionPlugin(TagSuggester):
    """Plugin with incompatible version."""
    
    @property
    def metadata(self):
        return PluginMetadata(
            name="incompatible",
            version="1.0.0",
            btk_version_required="2.0"  # Incompatible
        )
    
    def suggest_tags(self, url, title=None, content=None, description=None):
        return []


class TestPluginRegistry:
    """Test PluginRegistry functionality."""
    
    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return PluginRegistry()
    
    @pytest.fixture
    def lenient_registry(self):
        """Create a registry with lenient validation."""
        return PluginRegistry(validate_strict=False)
    
    def test_registry_initialization(self, registry):
        """Test registry initialization."""
        assert registry.validate_strict == True
        assert len(registry._plugins) == 6  # 6 plugin types (including media_preserver)
        assert len(registry._features) == 0
        assert len(registry._hooks) == 0
    
    def test_register_valid_plugin(self, registry):
        """Test registering a valid plugin."""
        plugin = MockTagSuggesterPlugin()
        registry.register(plugin)
        
        assert registry.has_feature("tag_suggester")
        assert registry.has_feature("tag_suggester:test_tagger")
        assert len(registry.get_plugins("tag_suggester")) == 1
    
    def test_register_auto_detect_type(self, registry):
        """Test auto-detection of plugin type."""
        plugin = MockTagSuggesterPlugin()
        registry.register(plugin)  # No type specified
        
        assert registry.get_plugin("tag_suggester") == plugin
    
    def test_register_invalid_type(self, registry):
        """Test registering with invalid plugin type."""
        plugin = MockTagSuggesterPlugin()
        
        with pytest.raises(PluginError, match="Unknown plugin type"):
            registry.register(plugin, "invalid_type")
    
    def test_register_wrong_interface(self, registry):
        """Test registering plugin with wrong interface."""
        plugin = MockTagSuggesterPlugin()
        
        with pytest.raises(PluginError, match="does not implement"):
            registry.register(plugin, "content_extractor")
    
    def test_version_compatibility_check(self, registry):
        """Test version compatibility checking."""
        plugin = IncompatibleVersionPlugin()
        
        with pytest.raises(PluginVersionError):
            registry.register(plugin)
    
    def test_version_compatibility_lenient(self, lenient_registry):
        """Test lenient version compatibility."""
        plugin = IncompatibleVersionPlugin()
        lenient_registry.register(plugin)  # Should not raise
        
        # Plugin should not be registered due to incompatibility
        assert len(lenient_registry.get_plugins("tag_suggester")) == 0
    
    def test_plugin_validation(self, registry):
        """Test plugin validation."""
        plugin = FailingValidationPlugin()
        
        with pytest.raises(PluginValidationError):
            registry.register(plugin)
    
    def test_plugin_validation_lenient(self, lenient_registry):
        """Test lenient plugin validation."""
        plugin = FailingValidationPlugin()
        lenient_registry.register(plugin)  # Should not raise
        
        # Plugin should not be registered due to failed validation
        assert len(lenient_registry.get_plugins("tag_suggester")) == 0
    
    def test_duplicate_plugin_replacement(self, registry):
        """Test replacing duplicate plugins."""
        plugin1 = MockTagSuggesterPlugin()
        plugin2 = MockTagSuggesterPlugin()
        
        registry.register(plugin1)
        registry.register(plugin2)  # Should replace plugin1
        
        plugins = registry.get_plugins("tag_suggester")
        assert len(plugins) == 1
        assert plugins[0] == plugin2
    
    def test_plugin_priority_ordering(self, registry):
        """Test plugins are ordered by priority."""
        class LowPriorityPlugin(TagSuggester):
            @property
            def metadata(self):
                return PluginMetadata(name="low", version="1.0.0", priority=25)
            def suggest_tags(self, url, title=None, content=None, description=None):
                return []
        
        class HighPriorityPlugin(TagSuggester):
            @property
            def metadata(self):
                return PluginMetadata(name="high", version="1.0.0", priority=75)
            def suggest_tags(self, url, title=None, content=None, description=None):
                return []
        
        low_priority = LowPriorityPlugin()
        high_priority = HighPriorityPlugin()
        
        registry.register(low_priority)
        registry.register(high_priority)
        
        plugins = registry.get_plugins("tag_suggester")
        assert plugins[0].metadata.name == "high"
        assert plugins[1].metadata.name == "low"
    
    def test_get_plugin_by_name(self, registry):
        """Test getting plugin by name."""
        plugin = MockTagSuggesterPlugin()
        registry.register(plugin)
        
        result = registry.get_plugin("tag_suggester", "test_tagger")
        assert result == plugin
        
        result = registry.get_plugin("tag_suggester", "nonexistent")
        assert result is None
    
    def test_unregister_plugin(self, registry):
        """Test unregistering a plugin."""
        plugin = MockTagSuggesterPlugin()
        registry.register(plugin)
        
        success = registry.unregister("tag_suggester", "test_tagger")
        assert success == True
        assert not registry.has_feature("tag_suggester:test_tagger")
        
        # Try to unregister again
        success = registry.unregister("tag_suggester", "test_tagger")
        assert success == False
    
    def test_enable_disable_plugin(self, registry):
        """Test enabling and disabling plugins."""
        plugin = MockTagSuggesterPlugin()
        registry.register(plugin)
        
        # Disable
        success = registry.set_plugin_enabled("tag_suggester", "test_tagger", False)
        assert success == True
        
        # Check the plugin's metadata was updated directly
        assert plugin.metadata.enabled == False
        
        # Get plugins should filter disabled ones
        enabled_plugins = registry.get_plugins("tag_suggester", enabled_only=True)
        all_plugins = registry.get_plugins("tag_suggester", enabled_only=False)
        assert len(enabled_plugins) == 0
        assert len(all_plugins) == 1
        
        # Enable
        success = registry.set_plugin_enabled("tag_suggester", "test_tagger", True)
        assert success == True
        assert plugin.metadata.enabled == True
        
        # Check again from registry
        enabled_plugins = registry.get_plugins("tag_suggester", enabled_only=True)
        assert len(enabled_plugins) == 1
    
    def test_list_features(self, registry):
        """Test listing features."""
        plugin1 = MockTagSuggesterPlugin()
        plugin2 = MockContentExtractorPlugin()
        
        registry.register(plugin1)
        registry.register(plugin2)
        
        features = registry.list_features()
        assert "tag_suggester" in features
        assert "tag_suggester:test_tagger" in features
        assert "content_extractor" in features
        assert "content_extractor:test_extractor" in features
    
    def test_plugin_lifecycle_hooks(self, registry):
        """Test on_register and on_unregister hooks."""
        plugin = MockTagSuggesterPlugin()
        plugin.on_register = Mock()
        plugin.on_unregister = Mock()
        
        registry.register(plugin)
        plugin.on_register.assert_called_once_with(registry)
        
        registry.unregister("tag_suggester", "test_tagger")
        plugin.on_unregister.assert_called_once_with(registry)
    
    def test_hook_system(self, registry):
        """Test hook registration and triggering."""
        callback1 = Mock(return_value="result1")
        callback2 = Mock(return_value="result2")
        
        registry.register_hook("test_event", callback1)
        registry.register_hook("test_event", callback2)
        
        results = registry.trigger_hook("test_event", "arg1", key="value")
        
        assert results == ["result1", "result2"]
        callback1.assert_called_once_with("arg1", key="value")
        callback2.assert_called_once_with("arg1", key="value")
    
    def test_hook_unregister(self, registry):
        """Test unregistering hooks."""
        callback = Mock()
        
        registry.register_hook("test_event", callback)
        success = registry.unregister_hook("test_event", callback)
        assert success == True
        
        results = registry.trigger_hook("test_event")
        assert results == []
        callback.assert_not_called()
    
    def test_hook_error_handling(self, registry):
        """Test hook error handling."""
        failing_callback = Mock(side_effect=Exception("Hook failed"))
        working_callback = Mock(return_value="success")
        
        registry.register_hook("test_event", failing_callback)
        registry.register_hook("test_event", working_callback)
        
        with pytest.raises(Exception):
            registry.trigger_hook("test_event")
    
    def test_hook_error_handling_lenient(self, lenient_registry):
        """Test lenient hook error handling."""
        failing_callback = Mock(side_effect=Exception("Hook failed"))
        failing_callback.__name__ = "failing_callback"  # Add name for logging
        working_callback = Mock(return_value="success")
        working_callback.__name__ = "working_callback"
        
        lenient_registry.register_hook("test_event", failing_callback)
        lenient_registry.register_hook("test_event", working_callback)
        
        results = lenient_registry.trigger_hook("test_event")
        assert results == ["success"]  # Only successful result
    
    def test_get_plugin_info(self, registry):
        """Test getting plugin information."""
        plugin = MockTagSuggesterPlugin()
        registry.register(plugin)
        
        info = registry.get_plugin_info()
        assert "tag_suggester" in info
        assert len(info["tag_suggester"]) == 1
        assert info["tag_suggester"][0]["name"] == "test_tagger"
        assert info["tag_suggester"][0]["version"] == "1.0.0"
        assert info["tag_suggester"][0]["author"] == "Test Author"
    
    def test_clear_registry(self, registry):
        """Test clearing the registry."""
        plugin = MockTagSuggesterPlugin()
        plugin.on_unregister = Mock()
        
        registry.register(plugin)
        registry.register_hook("test_event", lambda: None)
        
        registry.clear()
        
        assert len(registry.list_features()) == 0
        assert len(registry._hooks) == 0
        plugin.on_unregister.assert_called_once()
    
    def test_detect_invalid_plugin_type(self, registry):
        """Test detecting type for invalid plugin."""
        plugin = InvalidPlugin()
        
        with pytest.raises(PluginError, match="Could not detect plugin type"):
            registry.register(plugin)


class TestPluginPriority:
    """Test PluginPriority enum."""
    
    def test_priority_values(self):
        """Test priority enum values."""
        assert PluginPriority.LOWEST.value == 0
        assert PluginPriority.LOW.value == 25
        assert PluginPriority.NORMAL.value == 50
        assert PluginPriority.HIGH.value == 75
        assert PluginPriority.HIGHEST.value == 100


class TestPluginMetadata:
    """Test PluginMetadata dataclass."""
    
    def test_metadata_defaults(self):
        """Test metadata default values."""
        metadata = PluginMetadata(name="test", version="1.0.0")
        
        assert metadata.name == "test"
        assert metadata.version == "1.0.0"
        assert metadata.author == ""
        assert metadata.description == ""
        assert metadata.btk_version_required == "1.0"
        assert metadata.dependencies == []
        assert metadata.priority == 50
        assert metadata.enabled == True
    
    def test_metadata_custom_values(self):
        """Test metadata with custom values."""
        metadata = PluginMetadata(
            name="custom",
            version="2.0.0",
            author="Custom Author",
            description="Custom plugin",
            btk_version_required="1.0",
            dependencies=["dep1", "dep2"],
            priority=75,
            enabled=False
        )
        
        assert metadata.name == "custom"
        assert metadata.priority == 75
        assert metadata.enabled == False
        assert metadata.dependencies == ["dep1", "dep2"]


class TestFactoryFunctions:
    """Test factory and loading functions."""
    
    @patch('btk.plugins.logger')
    def test_create_default_registry(self, mock_logger):
        """Test creating default registry."""
        registry = create_default_registry()
        
        assert isinstance(registry, PluginRegistry)
        assert registry.validate_strict == False
    
    @patch('importlib.import_module')
    def test_load_plugins(self, mock_import):
        """Test loading plugins."""
        mock_module = Mock()
        mock_module.register_plugins = Mock()
        mock_import.return_value = mock_module

        registry = PluginRegistry()
        load_plugins(registry, ["test_plugin"])

        mock_import.assert_called_once_with("plugins.test_plugin")
        mock_module.register_plugins.assert_called_once_with(registry)

    @patch('importlib.import_module')
    def test_load_plugin_no_register_function(self, mock_import):
        """Test loading plugin without register function."""
        mock_module = Mock(spec=[])  # No register_plugins attribute
        mock_import.return_value = mock_module

        registry = PluginRegistry()
        load_plugins(registry, ["test_plugin"])

        # Should not raise, just log warning

    @patch('importlib.import_module')
    def test_load_plugin_import_error(self, mock_import):
        """Test handling import errors when loading plugins."""
        mock_import.side_effect = ImportError("Module not found")

        registry = PluginRegistry()
        load_plugins(registry, ["nonexistent"])

        # Should not raise, just log debug message