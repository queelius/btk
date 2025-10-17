"""
Configuration management for BTK.

Provides a clean, hierarchical configuration system with sensible defaults.
Supports both global (~/.config/btk/config.toml) and local (btk.toml) configurations.
"""
import os
import tomli
import tomli_w
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class BtkConfig:
    """
    BTK configuration with sensible defaults.

    Configuration hierarchy (highest to lowest priority):
    1. Command-line arguments
    2. Environment variables (BTK_*)
    3. Local config file (./btk.toml or ./.btkrc)
    4. User config file (~/.config/btk/config.toml)
    5. System defaults
    """

    # Database settings
    database: str = field(default="btk.db")
    database_url: Optional[str] = field(default=None)  # Full connection string (overrides database)
    database_echo: bool = field(default=False)  # SQLAlchemy echo for debugging
    connection_pool_size: int = field(default=5)
    connection_timeout: int = field(default=30)

    # Export defaults
    export_format: str = field(default="json")
    export_pretty: bool = field(default=True)

    # Browser integration
    default_browser: Optional[str] = field(default=None)
    browser_sync: bool = field(default=False)
    browser_profiles: Dict[str, str] = field(default_factory=dict)

    # Display settings
    output_format: str = field(default="table")  # table, json, csv, plain
    color_output: bool = field(default=True)
    page_size: int = field(default=20)

    # Network settings
    timeout: int = field(default=10)  # Request timeout in seconds
    user_agent: str = field(default="BTK/2.0")
    verify_ssl: bool = field(default=True)

    # Performance
    batch_size: int = field(default=100)
    cache_favicons: bool = field(default=True)
    parallel_downloads: int = field(default=4)

    # Advanced
    plugins_enabled: bool = field(default=True)
    plugins_dir: str = field(default="~/.config/btk/plugins")
    log_level: str = field(default="INFO")

    @classmethod
    def load(cls, config_file: Optional[Path] = None) -> "BtkConfig":
        """
        Load configuration from files and environment.

        Args:
            config_file: Specific config file to load (overrides search)

        Returns:
            Merged configuration object
        """
        config = cls()

        # Load system defaults (already set via dataclass defaults)

        # Load user config if exists
        user_config_path = Path.home() / ".config" / "btk" / "config.toml"
        if user_config_path.exists():
            config._merge(cls._load_toml(user_config_path))

        # Load local config if exists (check multiple locations)
        local_paths = [
            Path.cwd() / "btk.toml",
            Path.cwd() / ".btkrc",
            Path.cwd() / ".btk" / "config.toml"
        ]

        for path in local_paths:
            if path.exists():
                config._merge(cls._load_toml(path))
                break

        # Load specific config file if provided
        if config_file and config_file.exists():
            config._merge(cls._load_toml(config_file))

        # Apply environment variables (BTK_* prefix)
        config._apply_env_vars()

        # Expand paths
        config._expand_paths()

        return config

    @staticmethod
    def _load_toml(path: Path) -> Dict[str, Any]:
        """Load TOML configuration file."""
        with open(path, "rb") as f:
            return tomli.load(f)

    def _merge(self, data: Dict[str, Any]):
        """Merge configuration data into this instance."""
        for key, value in data.items():
            if hasattr(self, key):
                if isinstance(getattr(self, key), dict) and isinstance(value, dict):
                    # Merge dictionaries
                    getattr(self, key).update(value)
                else:
                    setattr(self, key, value)

    def _apply_env_vars(self):
        """Apply environment variables with BTK_ prefix."""
        prefix = "BTK_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                if hasattr(self, config_key):
                    # Convert string values to appropriate types
                    current_value = getattr(self, config_key)
                    if isinstance(current_value, bool):
                        setattr(self, config_key, value.lower() in ("true", "1", "yes"))
                    elif isinstance(current_value, int):
                        setattr(self, config_key, int(value))
                    else:
                        setattr(self, config_key, value)

    def _expand_paths(self):
        """Expand ~ and environment variables in paths."""
        path_fields = ["database", "plugins_dir"]
        for field_name in path_fields:
            value = getattr(self, field_name)
            if isinstance(value, str):
                expanded = os.path.expanduser(os.path.expandvars(value))
                setattr(self, field_name, expanded)

    def save(self, path: Optional[Path] = None):
        """
        Save current configuration to TOML file.

        Args:
            path: Path to save to (defaults to user config)
        """
        if path is None:
            path = Path.home() / ".config" / "btk" / "config.toml"

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            tomli_w.dump(asdict(self), f)

    def get_database_path(self) -> Path:
        """Get the resolved database path."""
        path = Path(self.database)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    def get_database_url(self) -> str:
        """
        Get SQLAlchemy database URL.

        Returns:
            Connection string for SQLAlchemy engine

        Examples:
            sqlite:///btk.db
            postgresql://user:pass@localhost/bookmarks
            mysql://user:pass@localhost/bookmarks
        """
        # If full URL is provided, use it directly
        if self.database_url:
            return self.database_url

        # Otherwise construct SQLite URL from path
        db_path = self.get_database_path()
        return f"sqlite:///{db_path}"

    def is_sqlite(self) -> bool:
        """Check if database is SQLite."""
        url = self.get_database_url()
        return url.startswith("sqlite:")

    def is_remote(self) -> bool:
        """Check if database is remote (PostgreSQL, MySQL, etc.)."""
        return not self.is_sqlite()


# Global configuration instance
_config: Optional[BtkConfig] = None


def get_config(reload: bool = False, config_file: Optional[Path] = None) -> BtkConfig:
    """
    Get the global configuration instance.

    Args:
        reload: Force reload configuration from files
        config_file: Specific config file to load

    Returns:
        Global configuration instance
    """
    global _config
    if _config is None or reload:
        _config = BtkConfig.load(config_file)
    return _config


def init_config(database: Optional[str] = None, **kwargs) -> BtkConfig:
    """
    Initialize configuration with command-line overrides.

    Args:
        database: Database path override
        **kwargs: Other configuration overrides

    Returns:
        Configured instance
    """
    config = get_config()

    if database:
        config.database = database

    for key, value in kwargs.items():
        if hasattr(config, key) and value is not None:
            setattr(config, key, value)

    return config