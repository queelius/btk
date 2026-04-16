"""Tests for bookmark_memex.config module."""
import os
import pytest


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Remove BOOKMARK_MEMEX_* env vars and point XDG dirs to tmp_path."""
    for key in list(os.environ.keys()):
        if key.startswith("BOOKMARK_MEMEX_"):
            monkeypatch.delenv(key, raising=False)

    xdg_config = tmp_path / "config"
    xdg_data = tmp_path / "data"
    xdg_config.mkdir()
    xdg_data.mkdir()

    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))
    monkeypatch.chdir(tmp_path)

    # Reset module-level singleton so each test gets a fresh Config
    import bookmark_memex.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_config", None)

    return tmp_path


def test_default_database_path(clean_env, tmp_path):
    """Default database path ends with bookmark-memex/bookmarks.db."""
    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.database.endswith("bookmark-memex/bookmarks.db")


def test_default_detectors_dir(clean_env, tmp_path):
    """Default detectors_dir ends with bookmark-memex/detectors."""
    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.detectors_dir.endswith("bookmark-memex/detectors")


def test_default_timeout(clean_env):
    """Default timeout is 10."""
    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.timeout == 10


def test_default_batch_size(clean_env):
    """Default batch_size is 100."""
    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.batch_size == 100


def test_default_user_agent(clean_env):
    """Default user_agent is bookmark-memex/0.1."""
    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.user_agent == "bookmark-memex/0.1"


def test_env_var_overrides_database(clean_env, monkeypatch, tmp_path):
    """BOOKMARK_MEMEX_DATABASE env var overrides the default database path."""
    custom_db = str(tmp_path / "custom.db")
    monkeypatch.setenv("BOOKMARK_MEMEX_DATABASE", custom_db)

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.database == custom_db


def test_env_var_overrides_timeout(clean_env, monkeypatch):
    """BOOKMARK_MEMEX_TIMEOUT env var overrides the default timeout."""
    monkeypatch.setenv("BOOKMARK_MEMEX_TIMEOUT", "42")

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.timeout == 42


def test_env_var_overrides_batch_size(clean_env, monkeypatch):
    """BOOKMARK_MEMEX_BATCH_SIZE env var overrides the default batch_size."""
    monkeypatch.setenv("BOOKMARK_MEMEX_BATCH_SIZE", "500")

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.batch_size == 500


def test_env_var_overrides_user_agent(clean_env, monkeypatch):
    """BOOKMARK_MEMEX_USER_AGENT env var overrides the default user_agent."""
    monkeypatch.setenv("BOOKMARK_MEMEX_USER_AGENT", "my-agent/1.0")

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.user_agent == "my-agent/1.0"


def test_toml_user_config_sets_database(clean_env, tmp_path, monkeypatch):
    """User config TOML file sets the database field."""
    xdg_config = tmp_path / "config"
    bm_dir = xdg_config / "bookmark-memex"
    bm_dir.mkdir(parents=True)
    config_file = bm_dir / "config.toml"
    config_file.write_text('[settings]\ndatabase = "/from/user/config.db"\n')

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.database == "/from/user/config.db"


def test_toml_user_config_sets_timeout(clean_env, tmp_path, monkeypatch):
    """User config TOML file sets the timeout field."""
    xdg_config = tmp_path / "config"
    bm_dir = xdg_config / "bookmark-memex"
    bm_dir.mkdir(parents=True)
    (bm_dir / "config.toml").write_text("[settings]\ntimeout = 30\n")

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.timeout == 30


def test_local_config_overrides_user_config(clean_env, tmp_path, monkeypatch):
    """Local bookmark-memex.toml overrides user config TOML."""
    xdg_config = tmp_path / "config"
    bm_dir = xdg_config / "bookmark-memex"
    bm_dir.mkdir(parents=True)
    (bm_dir / "config.toml").write_text('[settings]\ndatabase = "/user/config.db"\n')

    local_cfg = tmp_path / "bookmark-memex.toml"
    local_cfg.write_text('[settings]\ndatabase = "/local/config.db"\n')

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.database == "/local/config.db"


def test_explicit_config_file_overrides_local(clean_env, tmp_path):
    """Explicit config_file argument overrides local config."""
    local_cfg = tmp_path / "bookmark-memex.toml"
    local_cfg.write_text('[settings]\ndatabase = "/local/config.db"\n')

    explicit_cfg = tmp_path / "explicit.toml"
    explicit_cfg.write_text('[settings]\ndatabase = "/explicit/config.db"\n')

    from bookmark_memex.config import Config
    cfg = Config.load(config_file=str(explicit_cfg))
    assert cfg.database == "/explicit/config.db"


def test_env_overrides_toml(clean_env, tmp_path, monkeypatch):
    """BOOKMARK_MEMEX_DATABASE env var overrides a TOML config file setting."""
    xdg_config = tmp_path / "config"
    bm_dir = xdg_config / "bookmark-memex"
    bm_dir.mkdir(parents=True)
    (bm_dir / "config.toml").write_text('[settings]\ndatabase = "/from/toml.db"\n')

    monkeypatch.setenv("BOOKMARK_MEMEX_DATABASE", "/from/env.db")

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.database == "/from/env.db"


def test_get_config_returns_singleton(clean_env):
    """get_config() returns the same object on repeated calls."""
    from bookmark_memex.config import get_config
    cfg1 = get_config()
    cfg2 = get_config()
    assert cfg1 is cfg2


def test_get_config_reset_by_fixture(clean_env):
    """The clean_env fixture resets the singleton so load() produces a fresh Config."""
    from bookmark_memex.config import get_config, Config
    cfg = get_config()
    assert isinstance(cfg, Config)


def test_unknown_settings_key_ignored(clean_env, tmp_path):
    """Unknown keys in [settings] do not raise errors."""
    xdg_config = tmp_path / "config"
    bm_dir = xdg_config / "bookmark-memex"
    bm_dir.mkdir(parents=True)
    (bm_dir / "config.toml").write_text('[settings]\nunknown_key = "whatever"\n')

    from bookmark_memex.config import Config
    cfg = Config.load()
    # Should not raise; unknown key is silently ignored
    assert cfg.timeout == 10  # default still applies


def test_database_uses_xdg_data_home(clean_env, tmp_path, monkeypatch):
    """Default database path uses XDG_DATA_HOME, not ~/.local/share."""
    custom_data = tmp_path / "mydata"
    custom_data.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(custom_data))

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.database.startswith(str(custom_data))


def test_detectors_dir_uses_xdg_config_home(clean_env, tmp_path, monkeypatch):
    """Default detectors_dir uses XDG_CONFIG_HOME."""
    custom_config = tmp_path / "myconfig"
    custom_config.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_config))

    from bookmark_memex.config import Config
    cfg = Config.load()
    assert cfg.detectors_dir.startswith(str(custom_config))
