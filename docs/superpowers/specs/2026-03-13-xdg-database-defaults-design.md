# XDG-Compliant Database Defaults

**Date:** 2026-03-13
**Status:** Proposed

## Problem

btk defaults to `./btk.db` in the current working directory. This requires users to `cd` to the right place or always pass `--db`. It also conflicts with the multi-database feature — named databases like `history` already default to `~/.local/share/btk/history.db`, but the primary database lives wherever you happen to run the command.

## Decision

Move the default database to `~/.local/share/btk/bookmarks.db` following the XDG Base Directory Specification. Auto-discover `./btk.db` in the working directory for backward compatibility.

Note: We hardcode `~/.local/share` rather than honoring `XDG_DATA_HOME`. This keeps the implementation simple and predictable. Full XDG compliance is out of scope.

## Default Layout

```
~/.config/btk/config.toml          # config (existing)
~/.config/btk/plugins/             # plugins (existing)
~/.config/btk/views.yaml           # view definitions (existing)
~/.local/share/btk/bookmarks.db    # default curated bookmarks (NEW)
~/.local/share/btk/history.db      # browser history (NEW default)
```

## Resolution Chain

Database path resolution follows this priority (highest wins):

1. CLI `--db` flag
2. `BTK_DATABASE` environment variable
3. Config file `database = "..."` (from `config.toml` or local `btk.toml`)
4. Local `./btk.db` if it exists in the working directory (auto-discover)
5. XDG default: `~/.local/share/btk/bookmarks.db`

## Local Auto-Discovery

When no config source explicitly sets `database`, btk checks for `./btk.db` in the current directory. If found, it uses that file (converted to an absolute path). This provides zero-breakage backward compatibility: existing users with `./btk.db` keep working without any config changes.

**Detection mechanism:** We track whether any config source touched `database` using a `_database_explicitly_set` flag. The flag is initialized to `False` in `__post_init__` and set to `True` in `_merge()` when a `database` key is present, and in `_apply_env_vars()` when `BTK_DATABASE` is found. After all config loading, if the flag is `False`, we check for local `./btk.db`:

```python
# In load(), after all merges and env vars, before _expand_paths():
if not config._database_explicitly_set and Path("btk.db").exists():
    config.database = str(Path.cwd() / "btk.db")
```

The local discovery runs before `_expand_paths()` so that the tilde-form default has not yet been expanded. The assigned path (`Path.cwd() / "btk.db"`) is already absolute, so `_expand_paths()` is a no-op on it.

This correctly handles the edge case where someone explicitly writes `database = "~/.local/share/btk/bookmarks.db"` in their TOML: the flag is set, so local discovery does not fire, and the explicit config wins (matching priority 3 > priority 4 in the resolution chain).

## Default Named Databases

The `databases` dict ships with a default entry:

```python
databases: Dict[str, str] = field(default_factory=lambda: {
    "history": "~/.local/share/btk/history.db",
})
```

This means `btk bookmark list --db history` works out of the box. Users can add more named databases in their TOML config, and the dict merge preserves the default.

## Code Changes

### `btk/config.py`

- New module-level constant: `_DEFAULT_DATABASE = "~/.local/share/btk/bookmarks.db"` (literal tilde form — `_expand_paths()` handles expansion in the correct HOME context)
- Default `database` field: `"btk.db"` -> `_DEFAULT_DATABASE`
- Default `databases` factory: `dict` -> `lambda: {"history": "~/.local/share/btk/history.db"}`
- New `__post_init__` method to initialize tracking attribute:
  ```python
  def __post_init__(self):
      self._database_explicitly_set: bool = False
  ```
- `_merge()`: set `self._database_explicitly_set = True` when data contains `"database"` key
- `_apply_env_vars()`: inside the `if hasattr(self, config_key):` guard, add `if config_key == "database": self._database_explicitly_set = True`
- In `load()`, after all merges and env vars, before `_expand_paths()`:
  ```python
  if not config._database_explicitly_set and Path("btk.db").exists():
      config.database = str(Path.cwd() / "btk.db")
  ```
- Note: relative paths in config files continue to be resolved against CWD by `get_database_path()` — this is existing behavior, unchanged.

### `btk/mcp.py`

- `_resolve_db_path` fallback: `"btk.db"` -> duplicate the default as a module-level literal:
  ```python
  _FALLBACK_DB = os.path.expanduser("~/.local/share/btk/bookmarks.db")
  ```
  Used in the `except ImportError` branch when `btk.config` is unavailable. This is intentionally a duplicated literal (not imported from `btk.config`) because the fallback exists precisely because that module failed to import.

### `btk/serve.py`

- `run_server` default kwarg: `db_path='btk.db'` -> `db_path=None`
- `run_server` body: when `db_path is None`, use `get_config().database` (same pattern as `Database(path=None)`)

### `btk/cli.py`

- Help text: `"Database file (default: btk.db)"` -> `"Database name or path"`
- Epilog: `"Database: ./btk.db (or BTK_DATABASE env, or --db flag)"` -> `"Database: ~/.local/share/btk/bookmarks.db (or ./btk.db, BTK_DATABASE env, --db flag)"`

### Tests

- `tests/test_config.py`: Update existing tests that assert `"btk.db"` as the default. Specific tests requiring update:
  - `test_default_config_values` — assert default database is expanded `_DEFAULT_DATABASE`
  - `test_load_creates_default_config_when_no_files_exist` — same
  - `test_default_databases_is_empty` — rename and update: default now includes `{"history": "~/.local/share/btk/history.db"}` (assert the raw tilde form since this test instantiates `BtkConfig()` directly without calling `load()`, so `_expand_paths()` does not run)
  - `test_resolve_database_returns_default_for_none` — update expected value
  - `test_resolve_database_returns_default_for_empty_string` — update expected value
  - `test_list_databases_includes_default` — update expected dict
  - `test_save_creates_config_file` — update expected TOML content
  - All tests using `config.database = "btk.db"` as setup — update to use new default or explicit paths
  - All `is_sqlite` / `get_database_url` / `get_database_path` tests that reference `"btk.db"` — update
  - `test_init_config_ignores_none_values` — update expected `config.database` from `"btk.db"` to the expanded default path
- New tests to add:
  - Local `./btk.db` discovery (mock `Path("btk.db").exists()`, monkeypatch CWD and HOME)
  - Explicit config overrides local (set database in TOML, verify local discovery does not fire)
  - `BTK_DATABASE` env var overrides local (set env, verify local discovery does not fire)
  - Default history database in `databases` dict
  - Explicit-default-in-TOML edge case (write default path explicitly, verify flag is set)
- No changes needed in `test_mcp.py`, `test_cli.py`, `test_db.py` (all use explicit paths via `init_config(database=db_path)` or `Database(db_path)`).

### Not Changed

- `Database.__init__` — delegates to config, no hardcoded paths
- `get_db()` — delegates to `Database()` which delegates to config
- `init_config()` — resolves via `config.resolve_database()`, works as-is
- Exporters, importers, views — all go through `get_db()` or `Database()`

## What We're NOT Doing

- No migration machinery — local auto-discover handles existing users
- No first-run wizard or `btk init` command
- No changes to `--db` flag behavior
- No changes to `Database.__init__` path resolution
- No `XDG_DATA_HOME` env var support — hardcoded `~/.local/share`
- No `config.save()` round-trip fix (expanded paths are written as-is — acceptable since `save()` is rarely used and the expanded form is still correct)
