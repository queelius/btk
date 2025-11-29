"""
Tests for btk/config.py configuration management.

Tests the hierarchical configuration system with sensible defaults,
including file loading, environment variables, and path expansion.
"""
import os
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from btk.config import BtkConfig, get_config, init_config


class TestBtkConfigDefaults:
    """Test default configuration values."""

    def test_default_database_is_btk_db(self):
        """Default database should be 'btk.db'."""
        config = BtkConfig()
        assert config.database == "btk.db"

    def test_default_output_format_is_table(self):
        """Default output format should be 'table'."""
        config = BtkConfig()
        assert config.output_format == "table"

    def test_default_export_format_is_json(self):
        """Default export format should be 'json'."""
        config = BtkConfig()
        assert config.export_format == "json"

    def test_default_timeout_is_10(self):
        """Default timeout should be 10 seconds."""
        config = BtkConfig()
        assert config.timeout == 10

    def test_default_batch_size_is_100(self):
        """Default batch size should be 100."""
        config = BtkConfig()
        assert config.batch_size == 100

    def test_default_plugins_enabled_is_true(self):
        """Plugins should be enabled by default."""
        config = BtkConfig()
        assert config.plugins_enabled is True

    def test_default_color_output_is_true(self):
        """Color output should be enabled by default."""
        config = BtkConfig()
        assert config.color_output is True

    def test_default_verify_ssl_is_true(self):
        """SSL verification should be enabled by default."""
        config = BtkConfig()
        assert config.verify_ssl is True

    def test_default_database_url_is_none(self):
        """Database URL should be None by default (uses database path)."""
        config = BtkConfig()
        assert config.database_url is None

    def test_default_browser_profiles_is_empty_dict(self):
        """Browser profiles should be empty dict by default."""
        config = BtkConfig()
        assert config.browser_profiles == {}


class TestConfigLoading:
    """Test configuration loading from files."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directories for config testing."""
        temp_dir = tempfile.mkdtemp(prefix="btk_config_test_")
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_load_creates_default_config_when_no_files_exist(self, temp_config_dir, monkeypatch):
        """Load should return defaults when no config files exist."""
        monkeypatch.chdir(temp_config_dir)
        # Mock home directory to avoid loading real user config
        mock_home = Path(temp_config_dir) / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        config = BtkConfig.load()
        assert config.database == "btk.db"
        assert config.output_format == "table"

    def test_load_from_local_btk_toml(self, temp_config_dir, monkeypatch):
        """Should load config from ./btk.toml."""
        monkeypatch.chdir(temp_config_dir)
        # Mock home to avoid real user config
        mock_home = Path(temp_config_dir) / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create local config
        local_config = Path(temp_config_dir) / "btk.toml"
        local_config.write_text('database = "custom.db"\ntimeout = 30\n')

        config = BtkConfig.load()
        assert config.database == "custom.db"
        assert config.timeout == 30

    def test_load_from_btkrc(self, temp_config_dir, monkeypatch):
        """Should load config from ./.btkrc."""
        monkeypatch.chdir(temp_config_dir)
        mock_home = Path(temp_config_dir) / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create .btkrc config
        btkrc = Path(temp_config_dir) / ".btkrc"
        btkrc.write_text('database = "btkrc.db"\n')

        config = BtkConfig.load()
        assert config.database == "btkrc.db"

    def test_load_from_user_config_file(self, temp_config_dir, monkeypatch):
        """Should load config from ~/.config/btk/config.toml."""
        monkeypatch.chdir(temp_config_dir)

        # Create user config directory
        user_config_dir = Path(temp_config_dir) / ".config" / "btk"
        user_config_dir.mkdir(parents=True)
        user_config = user_config_dir / "config.toml"
        user_config.write_text('database = "user.db"\npage_size = 50\n')

        # Point HOME to temp dir
        monkeypatch.setenv("HOME", temp_config_dir)

        config = BtkConfig.load()
        assert config.database == "user.db"
        assert config.page_size == 50

    def test_local_config_overrides_user_config(self, temp_config_dir, monkeypatch):
        """Local config should override user config values."""
        monkeypatch.chdir(temp_config_dir)

        # Create user config
        user_config_dir = Path(temp_config_dir) / ".config" / "btk"
        user_config_dir.mkdir(parents=True)
        user_config = user_config_dir / "config.toml"
        user_config.write_text('database = "user.db"\ntimeout = 20\n')

        # Create local config (higher priority)
        local_config = Path(temp_config_dir) / "btk.toml"
        local_config.write_text('database = "local.db"\n')

        monkeypatch.setenv("HOME", temp_config_dir)

        config = BtkConfig.load()
        # database overridden by local
        assert config.database == "local.db"
        # timeout from user config preserved
        assert config.timeout == 20

    def test_explicit_config_file_overrides_all(self, temp_config_dir, monkeypatch):
        """Explicitly specified config file should override all others."""
        monkeypatch.chdir(temp_config_dir)
        mock_home = Path(temp_config_dir) / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create local config
        local_config = Path(temp_config_dir) / "btk.toml"
        local_config.write_text('database = "local.db"\n')

        # Create explicit config
        explicit_config = Path(temp_config_dir) / "explicit.toml"
        explicit_config.write_text('database = "explicit.db"\n')

        config = BtkConfig.load(config_file=explicit_config)
        assert config.database == "explicit.db"


class TestEnvironmentVariables:
    """Test environment variable overrides."""

    @pytest.fixture
    def clean_env(self, monkeypatch):
        """Remove any existing BTK_ environment variables."""
        for key in list(os.environ.keys()):
            if key.startswith("BTK_"):
                monkeypatch.delenv(key, raising=False)
        yield

    def test_env_var_overrides_file_config_string(self, clean_env, monkeypatch, tmp_path):
        """BTK_DATABASE environment variable should override file config."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))
        monkeypatch.setenv("BTK_DATABASE", "env_override.db")

        config = BtkConfig.load()
        assert config.database == "env_override.db"

    def test_env_var_overrides_boolean_true(self, clean_env, monkeypatch, tmp_path):
        """Boolean env vars should convert 'true' to True."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))
        monkeypatch.setenv("BTK_DATABASE_ECHO", "true")

        config = BtkConfig.load()
        assert config.database_echo is True

    def test_env_var_overrides_boolean_false(self, clean_env, monkeypatch, tmp_path):
        """Boolean env vars should convert 'false' to False."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))
        monkeypatch.setenv("BTK_COLOR_OUTPUT", "false")

        config = BtkConfig.load()
        assert config.color_output is False

    def test_env_var_overrides_boolean_1(self, clean_env, monkeypatch, tmp_path):
        """Boolean env vars should convert '1' to True."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))
        monkeypatch.setenv("BTK_DATABASE_ECHO", "1")

        config = BtkConfig.load()
        assert config.database_echo is True

    def test_env_var_overrides_integer(self, clean_env, monkeypatch, tmp_path):
        """Integer env vars should be converted properly."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))
        monkeypatch.setenv("BTK_TIMEOUT", "60")

        config = BtkConfig.load()
        assert config.timeout == 60

    def test_unknown_env_var_ignored(self, clean_env, monkeypatch, tmp_path):
        """Unknown BTK_ env vars should be ignored."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))
        monkeypatch.setenv("BTK_UNKNOWN_SETTING", "value")

        config = BtkConfig.load()
        assert not hasattr(config, "unknown_setting")


class TestConfigSaving:
    """Test configuration saving."""

    def test_save_creates_parent_directories(self, tmp_path):
        """save() should create parent directories if needed."""
        config = BtkConfig()
        # Set None fields to strings for TOML compatibility
        config.database_url = "sqlite:///test.db"
        config.default_browser = "firefox"
        save_path = tmp_path / "nested" / "dirs" / "config.toml"

        config.save(save_path)

        assert save_path.exists()
        assert save_path.parent.exists()

    def test_save_writes_valid_toml(self, tmp_path):
        """Saved config should be valid TOML that can be loaded."""
        import tomli

        config = BtkConfig()
        config.database = "saved.db"
        config.timeout = 45
        # Set None fields to strings for TOML compatibility
        config.database_url = "sqlite:///saved.db"
        config.default_browser = "chrome"

        save_path = tmp_path / "config.toml"
        config.save(save_path)

        # Verify file can be parsed as TOML
        with open(save_path, "rb") as f:
            loaded = tomli.load(f)

        assert loaded["database"] == "saved.db"
        assert loaded["timeout"] == 45

    def test_save_to_default_location(self, monkeypatch, tmp_path):
        """save() without path should use default user config location."""
        monkeypatch.setenv("HOME", str(tmp_path))

        config = BtkConfig()
        # Set None fields to strings for TOML compatibility
        config.database_url = "sqlite:///btk.db"
        config.default_browser = "default"
        config.save()

        expected_path = tmp_path / ".config" / "btk" / "config.toml"
        assert expected_path.exists()

    def test_save_fails_with_none_values(self, tmp_path):
        """save() should fail when Optional fields are None (TOML limitation)."""
        import pytest

        config = BtkConfig()  # Has None values for Optional fields
        save_path = tmp_path / "config.toml"

        # TOML doesn't support None values natively
        with pytest.raises(TypeError, match="NoneType"):
            config.save(save_path)


class TestDatabaseUrlGeneration:
    """Test database URL generation."""

    def test_sqlite_url_generation_relative(self, tmp_path, monkeypatch):
        """Should generate sqlite:/// URL for relative database path."""
        monkeypatch.chdir(tmp_path)
        config = BtkConfig()
        config.database = "btk.db"

        url = config.get_database_url()
        assert url.startswith("sqlite:///")
        assert "btk.db" in url

    def test_sqlite_url_generation_absolute(self):
        """Should generate sqlite:/// URL for absolute database path."""
        config = BtkConfig()
        config.database = "/absolute/path/btk.db"

        url = config.get_database_url()
        assert url == "sqlite:////absolute/path/btk.db"

    def test_full_url_overrides_path(self):
        """database_url should override database path completely."""
        config = BtkConfig()
        config.database = "btk.db"
        config.database_url = "postgresql://user:pass@localhost/bookmarks"

        url = config.get_database_url()
        assert url == "postgresql://user:pass@localhost/bookmarks"

    def test_is_sqlite_with_sqlite_url(self):
        """is_sqlite() should return True for SQLite databases."""
        config = BtkConfig()
        config.database = "btk.db"

        assert config.is_sqlite() is True

    def test_is_sqlite_with_postgresql_url(self):
        """is_sqlite() should return False for PostgreSQL."""
        config = BtkConfig()
        config.database_url = "postgresql://user:pass@localhost/db"

        assert config.is_sqlite() is False

    def test_is_remote_with_sqlite(self):
        """is_remote() should return False for SQLite."""
        config = BtkConfig()
        config.database = "btk.db"

        assert config.is_remote() is False

    def test_is_remote_with_postgresql(self):
        """is_remote() should return True for PostgreSQL."""
        config = BtkConfig()
        config.database_url = "postgresql://user:pass@localhost/db"

        assert config.is_remote() is True

    def test_is_remote_with_mysql(self):
        """is_remote() should return True for MySQL."""
        config = BtkConfig()
        config.database_url = "mysql://user:pass@localhost/db"

        assert config.is_remote() is True


class TestDatabasePath:
    """Test database path resolution."""

    def test_get_database_path_relative(self, tmp_path, monkeypatch):
        """Relative database path should be resolved to cwd."""
        monkeypatch.chdir(tmp_path)
        config = BtkConfig()
        config.database = "btk.db"

        path = config.get_database_path()
        assert path == tmp_path / "btk.db"

    def test_get_database_path_absolute(self):
        """Absolute database path should be returned as-is."""
        config = BtkConfig()
        config.database = "/absolute/path/btk.db"

        path = config.get_database_path()
        assert path == Path("/absolute/path/btk.db")


class TestPathExpansion:
    """Test path expansion for ~ and environment variables."""

    def test_expand_tilde_in_database(self, monkeypatch, tmp_path):
        """~ in database path should be expanded to home directory."""
        monkeypatch.setenv("HOME", str(tmp_path))

        config = BtkConfig()
        config.database = "~/bookmarks.db"
        config._expand_paths()

        assert config.database == str(tmp_path / "bookmarks.db")

    def test_expand_tilde_in_plugins_dir(self, monkeypatch, tmp_path):
        """~ in plugins_dir should be expanded to home directory."""
        monkeypatch.setenv("HOME", str(tmp_path))

        config = BtkConfig()
        config.plugins_dir = "~/.config/btk/plugins"
        config._expand_paths()

        assert config.plugins_dir == str(tmp_path / ".config/btk/plugins")

    def test_expand_env_vars_in_database(self, monkeypatch):
        """Environment variables in database path should be expanded."""
        monkeypatch.setenv("BTK_DATA_DIR", "/custom/data")

        config = BtkConfig()
        config.database = "$BTK_DATA_DIR/btk.db"
        config._expand_paths()

        assert config.database == "/custom/data/btk.db"


class TestMergeConfiguration:
    """Test configuration merging behavior."""

    def test_merge_overwrites_simple_values(self):
        """Simple values should be overwritten during merge."""
        config = BtkConfig()
        config.database = "original.db"

        config._merge({"database": "merged.db"})

        assert config.database == "merged.db"

    def test_merge_updates_dict_values(self):
        """Dict values should be updated (not replaced) during merge."""
        config = BtkConfig()
        config.browser_profiles = {"chrome": "/path/to/chrome"}

        config._merge({"browser_profiles": {"firefox": "/path/to/firefox"}})

        assert config.browser_profiles == {
            "chrome": "/path/to/chrome",
            "firefox": "/path/to/firefox"
        }

    def test_merge_ignores_unknown_keys(self):
        """Unknown keys in merge data should be ignored."""
        config = BtkConfig()

        config._merge({"unknown_key": "value"})

        assert not hasattr(config, "unknown_key")


class TestGlobalConfigFunctions:
    """Test module-level config functions."""

    def test_get_config_returns_same_instance(self, monkeypatch, tmp_path):
        """get_config() should return same instance on repeated calls."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Reset global config
        import btk.config
        btk.config._config = None

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_get_config_reload_creates_new_instance(self, monkeypatch, tmp_path):
        """get_config(reload=True) should create new instance."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Reset global config
        import btk.config
        btk.config._config = None

        config1 = get_config()
        config1.timeout = 999  # Modify

        config2 = get_config(reload=True)

        assert config2.timeout == 10  # Back to default

    def test_init_config_applies_overrides(self, monkeypatch, tmp_path):
        """init_config() should apply database and other overrides."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Reset global config
        import btk.config
        btk.config._config = None

        config = init_config(database="override.db", timeout=99)

        assert config.database == "override.db"
        assert config.timeout == 99

    def test_init_config_ignores_none_values(self, monkeypatch, tmp_path):
        """init_config() should ignore None values."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Reset global config
        import btk.config
        btk.config._config = None

        config = init_config(database=None)

        assert config.database == "btk.db"  # Default preserved
