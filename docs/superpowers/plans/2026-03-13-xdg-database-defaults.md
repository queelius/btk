# XDG Database Defaults Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the default database from `./btk.db` to `~/.local/share/btk/bookmarks.db` with local `./btk.db` auto-discovery for backward compatibility.

**Architecture:** Add `_DEFAULT_DATABASE` constant and `_database_explicitly_set` tracking flag to `BtkConfig`. The `load()` method checks for local `./btk.db` when no config source has explicitly set the database field. Pre-configure `history` in the default `databases` dict.

**Tech Stack:** Python dataclasses, TOML config, pytest

**Spec:** `docs/superpowers/specs/2026-03-13-xdg-database-defaults-design.md`

---

## Chunk 1: Core Config Changes

### Task 1: Update BtkConfig defaults and add tracking flag

**Files:**
- Modify: `btk/config.py:14-30` (constant + dataclass fields)
- Modify: `btk/config.py:65-107` (load method)
- Modify: `btk/config.py:115-123` (_merge method)
- Modify: `btk/config.py:125-139` (_apply_env_vars method)

- [ ] **Step 1: Add `_DEFAULT_DATABASE` constant and update field defaults**

In `btk/config.py`, add the constant before the dataclass and update the two field defaults:

```python
# Add after the imports, before @dataclass
_DEFAULT_DATABASE = "~/.local/share/btk/bookmarks.db"
_DEFAULT_HISTORY_DATABASE = "~/.local/share/btk/history.db"
```

Update the dataclass fields:

```python
# Line 29: change default
database: str = field(default=_DEFAULT_DATABASE)

# Line 30: change default_factory
databases: Dict[str, str] = field(default_factory=lambda: {
    "history": _DEFAULT_HISTORY_DATABASE,
})
```

- [ ] **Step 2: Add `__post_init__` to initialize tracking flag**

Add immediately after the last field in the dataclass (after `log_level`, line 63):

```python
def __post_init__(self):
    self._database_explicitly_set: bool = False
```

- [ ] **Step 3: Update `_merge()` to track database changes**

In `_merge()` (line 115-123), add flag tracking when `database` key is merged:

```python
def _merge(self, data: Dict[str, Any]):
    """Merge configuration data into this instance."""
    if "database" in data:
        self._database_explicitly_set = True
    for key, value in data.items():
        if hasattr(self, key):
            if isinstance(getattr(self, key), dict) and isinstance(value, dict):
                getattr(self, key).update(value)
            else:
                setattr(self, key, value)
```

- [ ] **Step 4: Update `_apply_env_vars()` to track BTK_DATABASE**

In `_apply_env_vars()` (line 125-139), add flag tracking inside the `if hasattr` guard:

```python
def _apply_env_vars(self):
    """Apply environment variables with BTK_ prefix."""
    prefix = "BTK_"
    for key, value in os.environ.items():
        if key.startswith(prefix):
            config_key = key[len(prefix):].lower()
            if hasattr(self, config_key):
                if config_key == "database":
                    self._database_explicitly_set = True
                current_value = getattr(self, config_key)
                if isinstance(current_value, bool):
                    setattr(self, config_key, value.lower() in ("true", "1", "yes"))
                elif isinstance(current_value, int):
                    setattr(self, config_key, int(value))
                else:
                    setattr(self, config_key, value)
```

- [ ] **Step 5: Add local `./btk.db` auto-discovery in `load()`**

In `load()`, add the discovery block after `config._apply_env_vars()` (line 102) and before `config._expand_paths()` (line 105):

```python
        # Apply environment variables (BTK_* prefix)
        config._apply_env_vars()

        # Auto-discover local ./btk.db for backward compatibility
        if not config._database_explicitly_set and Path("btk.db").exists():
            config.database = str(Path.cwd() / "btk.db")

        # Expand paths
        config._expand_paths()
```

- [ ] **Step 6: Run existing tests to see what breaks**

Run: `pytest tests/test_config.py -v --tb=short 2>&1 | tail -40`

Expected: Multiple failures on tests that assert `"btk.db"` as the default. This confirms the change took effect and tells us exactly which tests to update.

- [ ] **Step 7: Commit core config changes**

```bash
git add btk/config.py
git commit -m "feat: XDG-compliant database defaults with local auto-discovery

Default database moves from ./btk.db to ~/.local/share/btk/bookmarks.db.
History database pre-configured at ~/.local/share/btk/history.db.
Local ./btk.db auto-discovered for backward compatibility."
```

---

### Task 2: Update existing config tests for new defaults

**Files:**
- Modify: `tests/test_config.py`

The following tests assert `"btk.db"` as the default and need updating. The new default after `_expand_paths()` is the expanded form of `_DEFAULT_DATABASE`. For tests that construct `BtkConfig()` directly (no `load()`), the raw tilde form `"~/.local/share/btk/bookmarks.db"` is correct since `_expand_paths()` hasn't run.

- [ ] **Step 1: Import constant and define helper**

At the top of `tests/test_config.py`, add:

```python
from btk.config import BtkConfig, get_config, init_config, _DEFAULT_DATABASE, _DEFAULT_HISTORY_DATABASE
```

- [ ] **Step 2: Update `TestBtkConfigDefaults::test_default_database_is_btk_db`**

```python
def test_default_database_is_xdg_path(self):
    """Default database should be XDG data path."""
    config = BtkConfig()
    assert config.database == _DEFAULT_DATABASE
```

- [ ] **Step 3: Update `TestMultiDatabase::test_default_databases_is_empty`**

```python
def test_default_databases_includes_history(self):
    """Default databases should include history."""
    config = BtkConfig()
    assert "history" in config.databases
    assert config.databases["history"] == _DEFAULT_HISTORY_DATABASE
```

- [ ] **Step 4: Update `TestConfigLoading::test_load_creates_default_config_when_no_files_exist`**

The loaded config has `_expand_paths()` applied, so the expected value is the HOME-expanded path:

```python
def test_load_creates_default_config_when_no_files_exist(self, temp_config_dir, monkeypatch):
    """Load should return defaults when no config files exist."""
    monkeypatch.chdir(temp_config_dir)
    mock_home = Path(temp_config_dir) / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))

    config = BtkConfig.load()
    assert config.database == str(mock_home / ".local/share/btk/bookmarks.db")
    assert config.output_format == "table"
```

- [ ] **Step 5: Update `TestMultiDatabase` resolve/list tests**

For `test_resolve_database_returns_default_when_none` and `test_resolve_database_returns_default_for_empty_string`, these construct `BtkConfig()` directly and set `config.database` — they can keep using any explicit value (they're testing the method, not the default). However, update the ones that rely on the default:

```python
def test_resolve_database_returns_default_when_none(self):
    config = BtkConfig()
    config.database = "test.db"
    assert config.resolve_database(None) == "test.db"

def test_resolve_database_returns_default_for_empty_string(self):
    config = BtkConfig()
    config.database = "test.db"
    assert config.resolve_database("") == "test.db"

def test_list_databases_includes_default_and_named(self):
    config = BtkConfig()
    config.database = "test.db"
    config.databases = {"history": "/data/history.db", "tabs": "/data/tabs.db"}
    result = config.list_databases()
    assert result == {
        "default": "test.db",
        "history": "/data/history.db",
        "tabs": "/data/tabs.db",
    }
```

- [ ] **Step 6: Update `TestMultiDatabase::test_load_named_databases_from_toml`**

The TOML sets `database = "btk.db"` explicitly, which still works. But the default `databases` dict includes `history`, and the TOML overrides it. Update the assertion to account for the merged dict — the TOML's `history` overrides the default:

```python
def test_load_named_databases_from_toml(self, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))

    local_config = tmp_path / "btk.toml"
    local_config.write_text(
        'database = "btk.db"\n\n'
        '[databases]\n'
        'history = "/data/history.db"\n'
        'tabs = "/data/tabs.db"\n'
    )

    config = BtkConfig.load()
    assert config.databases == {
        "history": "/data/history.db",
        "tabs": "/data/tabs.db",
    }
```

(No change needed — the TOML's `[databases]` merges over the default, replacing `history` and adding `tabs`.)

- [ ] **Step 7: Update `TestDatabaseUrlGeneration` and `TestDatabasePath` tests**

These tests set `config.database = "btk.db"` as explicit setup — they're testing the URL/path methods, not the default. No changes needed since they set the value explicitly.

- [ ] **Step 8: Update `TestMultiDatabase::test_save_creates_config_file` (if exists) and `test_init_config_ignores_none_values`**

For `test_init_config_ignores_none_values` (line 610-623):

```python
def test_init_config_ignores_none_values(self, monkeypatch, tmp_path):
    """init_config() should ignore None values."""
    monkeypatch.chdir(tmp_path)
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))

    import btk.config
    btk.config._config = None

    config = init_config(database=None)

    expected_db = str(mock_home / ".local/share/btk/bookmarks.db")
    assert config.database == expected_db
```

- [ ] **Step 9: Run tests to verify all pass**

Run: `pytest tests/test_config.py -v --tb=short`
Expected: All tests pass.

- [ ] **Step 10: Commit test updates**

```bash
git add tests/test_config.py
git commit -m "test: update config tests for XDG database defaults"
```

---

### Task 3: Add new tests for auto-discovery and tracking flag

**Files:**
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add test class for local auto-discovery**

Add a new test class after `TestMultiDatabase`:

```python
class TestLocalDatabaseDiscovery:
    """Test backward-compatible ./btk.db auto-discovery."""

    def test_discovers_local_btk_db(self, tmp_path, monkeypatch):
        """Should use ./btk.db when it exists and no config sets database."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create a local btk.db
        (tmp_path / "btk.db").touch()

        config = BtkConfig.load()
        assert config.database == str(tmp_path / "btk.db")

    def test_xdg_default_when_no_local_btk_db(self, tmp_path, monkeypatch):
        """Should use XDG default when no ./btk.db exists."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # No btk.db in tmp_path
        config = BtkConfig.load()
        assert config.database == str(mock_home / ".local/share/btk/bookmarks.db")

    def test_explicit_config_overrides_local_btk_db(self, tmp_path, monkeypatch):
        """Config file database= should override local ./btk.db discovery."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create both a local btk.db AND a config file
        (tmp_path / "btk.db").touch()
        (tmp_path / "btk.toml").write_text('database = "custom.db"\n')

        config = BtkConfig.load()
        assert config.database == "custom.db"

    def test_env_var_overrides_local_btk_db(self, tmp_path, monkeypatch):
        """BTK_DATABASE env var should override local ./btk.db discovery."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create local btk.db AND set env var
        (tmp_path / "btk.db").touch()
        monkeypatch.setenv("BTK_DATABASE", "env.db")

        config = BtkConfig.load()
        assert config.database == "env.db"

    def test_explicit_default_in_toml_prevents_local_discovery(self, tmp_path, monkeypatch):
        """Explicitly writing the default path in TOML should prevent local discovery."""
        monkeypatch.chdir(tmp_path)
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create local btk.db AND config that explicitly sets the default path
        (tmp_path / "btk.db").touch()
        (tmp_path / "btk.toml").write_text(
            f'database = "{_DEFAULT_DATABASE}"\n'
        )

        config = BtkConfig.load()
        # Should use the explicit config value (expanded), NOT ./btk.db
        expected = str(mock_home / ".local/share/btk/bookmarks.db")
        assert config.database == expected
```

- [ ] **Step 2: Run new tests**

Run: `pytest tests/test_config.py::TestLocalDatabaseDiscovery -v`
Expected: All 5 pass.

- [ ] **Step 3: Run full config test suite**

Run: `pytest tests/test_config.py -v --tb=short`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_config.py
git commit -m "test: add local ./btk.db auto-discovery tests"
```

---

## Chunk 2: Peripheral Code Changes

### Task 4: Update mcp.py fallback

**Files:**
- Modify: `btk/mcp.py:1-29`

- [ ] **Step 1: Add `_FALLBACK_DB` and update fallback**

At the top of `btk/mcp.py`, add `os` import and the fallback constant, then update `_resolve_db_path`:

```python
import json
import os
from typing import Optional

import aiosqlite
from fastmcp import FastMCP

_ALLOWED_KEYWORDS = frozenset({"SELECT", "WITH", "EXPLAIN"})

_UPDATE_WHITELIST = frozenset({
    "title", "description", "stars", "archived", "pinned",
    "bookmark_type", "reachable", "visit_count", "last_visited",
})

# Duplicated from btk.config._DEFAULT_DATABASE (expanded) because this
# fallback only fires when btk.config fails to import.
_FALLBACK_DB = os.path.expanduser("~/.local/share/btk/bookmarks.db")


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    """Resolve the database path from explicit argument, config, or fallback."""
    try:
        from btk.config import get_config

        config = get_config()
        return config.resolve_database(db_path)
    except ImportError:
        return db_path or _FALLBACK_DB
```

- [ ] **Step 2: Run MCP tests**

Run: `pytest tests/test_mcp.py -v --tb=short`
Expected: All 32 pass (no changes to test expectations — tests use explicit paths).

- [ ] **Step 3: Commit**

```bash
git add btk/mcp.py
git commit -m "fix: update MCP fallback database path to XDG default"
```

---

### Task 5: Update serve.py default

**Files:**
- Modify: `btk/serve.py:956,975,984`

- [ ] **Step 1: Update `run_server` signature and body**

First, update the `typing` import at the top of `serve.py`. The current import is `from typing import Dict, Any` — add `Optional`:

```python
from typing import Dict, Any, Optional
```

Change the function signature:

```python
def run_server(db_path: Optional[str] = None, port: int = 8000, host: str = '127.0.0.1'):
```

At line 975, add config resolution before the Database call:

```python
    if db_path is None:
        from btk.config import get_config
        db_path = get_config().database
    db = Database(db_path)
```

The `print(f"Database: {db_path}")` at line 984 comes after this resolution, so it will correctly print the resolved path.

- [ ] **Step 2: Run serve tests**

Run: `pytest tests/test_serve.py -v --tb=short`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add btk/serve.py
git commit -m "fix: update serve.py default database path to use config"
```

---

### Task 6: Update CLI help text

**Files:**
- Modify: `btk/cli.py:3738,3744`

- [ ] **Step 1: Update help text and epilog**

At line 3738, change the epilog:
```python
  Database: ~/.local/share/btk/bookmarks.db (or ./btk.db, BTK_DATABASE, --db)
```

At line 3744, change the `--db` help:
```python
    parser.add_argument("--db", help="Database name or path")
```

- [ ] **Step 2: Run CLI tests**

Run: `pytest tests/test_cli.py -v --tb=short 2>&1 | tail -20`
Expected: All pass (no tests assert on help text).

- [ ] **Step 3: Commit**

```bash
git add btk/cli.py
git commit -m "docs: update CLI help text for XDG database defaults"
```

---

### Task 7: Full test suite validation

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All ~1150 tests pass, 0 failures.

- [ ] **Step 2: Run test coverage on config module**

Run: `pytest tests/test_config.py --cov=btk.config --cov-report=term-missing --tb=short`
Expected: Good coverage on `load()`, `_merge()`, `_apply_env_vars()`, including the new auto-discovery branch.

---

### Task 8: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the multi-database config example**

Change the CLAUDE.md section that shows the config TOML to reflect the new defaults:

```toml
database = "~/.local/share/btk/bookmarks.db"  # Default (curated bookmarks)

[databases]
history = "~/.local/share/btk/history.db"      # Browser history (pre-configured)
```

Update the note: "Default database is `~/.local/share/btk/bookmarks.db`. If `./btk.db` exists in the working directory, it is used automatically (backward compatibility)."

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for XDG database defaults"
```
