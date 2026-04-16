"""Configuration management for bookmark-memex.

Priority (highest wins):
1. CLI arguments (handled by caller)
2. BOOKMARK_MEMEX_* environment variables
3. Local config ./bookmark-memex.toml
4. User config ~/.config/bookmark-memex/config.toml  (XDG_CONFIG_HOME)
5. Defaults

Config file format (TOML):
    [settings]
    database = "/path/to/db"
    timeout = 30
"""
from __future__ import annotations

import dataclasses
import os
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


# ── XDG helpers ────────────────────────────────────────────────────────────────

def _xdg_config() -> str:
    """Return XDG_CONFIG_HOME, defaulting to ~/.config."""
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")


def _xdg_data() -> str:
    """Return XDG_DATA_HOME, defaulting to ~/.local/share."""
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


# ── Config dataclass ───────────────────────────────────────────────────────────

@dataclasses.dataclass
class Config:
    database: str = ""         # defaults to XDG_DATA_HOME/bookmark-memex/bookmarks.db
    detectors_dir: str = ""    # defaults to XDG_CONFIG_HOME/bookmark-memex/detectors
    timeout: int = 10
    user_agent: str = "bookmark-memex/0.1"
    batch_size: int = 100

    def __post_init__(self) -> None:
        # Fill in XDG-derived defaults when empty strings are left
        if not self.database:
            self.database = os.path.join(_xdg_data(), "bookmark-memex", "bookmarks.db")
        if not self.detectors_dir:
            self.detectors_dir = os.path.join(_xdg_config(), "bookmark-memex", "detectors")

    @classmethod
    def load(cls, config_file: Optional[str] = None) -> "Config":
        """Build a Config following the documented priority chain."""
        # Collect known field names (excluding private sentinel)
        field_names = {f.name for f in dataclasses.fields(cls) if not f.name.startswith("_")}

        merged: dict = {}

        # Layer 1 – user config (lowest file priority)
        user_cfg_path = os.path.join(_xdg_config(), "bookmark-memex", "config.toml")
        _load_toml_layer(user_cfg_path, merged, field_names)

        # Layer 2 – local config (overrides user)
        local_cfg_path = "bookmark-memex.toml"
        _load_toml_layer(local_cfg_path, merged, field_names)

        # Layer 3 – explicit config_file (overrides local)
        if config_file:
            _load_toml_layer(config_file, merged, field_names)

        # Layer 4 – environment variables (highest priority, override all files)
        for field_name in field_names:
            env_key = "BOOKMARK_MEMEX_" + field_name.upper()
            env_val = os.environ.get(env_key)
            if env_val is not None:
                merged[field_name] = env_val

        # Coerce int fields — compare against the actual type hint via __annotations__
        annotations = cls.__annotations__
        for field in dataclasses.fields(cls):
            if field.name.startswith("_"):
                continue
            ann = annotations.get(field.name)
            if ann is int or ann == "int":
                if field.name in merged:
                    merged[field.name] = int(merged[field.name])

        return cls(**merged)


def _load_toml_layer(path: str, merged: dict, field_names: set) -> None:
    """Read a TOML file and merge its [settings] section into *merged* (in-place)."""
    if not os.path.isfile(path):
        return
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    settings = data.get("settings", {})
    for key, value in settings.items():
        if key in field_names:
            merged[key] = value


# ── Module-level singleton ─────────────────────────────────────────────────────

_config: Optional[Config] = None


def get_config() -> Config:
    """Return the process-wide Config, loading it on first call."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config
