"""Auto-discovery engine for bookmark-memex media detectors.

Built-in detectors live in this package (youtube.py, arxiv.py, github.py, …).
User detectors live in ~/.config/bookmark-memex/detectors/ and override
built-ins when the filenames match.

Public API
----------
discover()          -> list[tuple[str, DetectFn]]
run_detectors()     -> dict | None
reset_cache()       -> None
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable, Optional

DetectFn = Callable[[str, Optional[str]], Optional[dict]]

# Module-level cache; None means "not yet loaded".
_detectors: Optional[list[tuple[str, DetectFn]]] = None


def _load_builtin_detectors() -> dict[str, DetectFn]:
    """Import every non-underscore .py file in this package directory."""
    package_dir = Path(__file__).parent
    result: dict[str, DetectFn] = {}
    for path in sorted(package_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = path.stem
        module = importlib.import_module(f"bookmark_memex.detectors.{name}")
        fn = getattr(module, "detect", None)
        if callable(fn):
            result[name] = fn
    return result


def _load_user_detectors(user_dir: str) -> dict[str, DetectFn]:
    """Load user detector modules from *user_dir* using spec_from_file_location."""
    result: dict[str, DetectFn] = {}
    dir_path = Path(user_dir)
    if not dir_path.is_dir():
        return result
    for path in sorted(dir_path.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = path.stem
        module_name = f"_bm_user_detector_{name}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        except Exception:
            continue
        fn = getattr(module, "detect", None)
        if callable(fn):
            result[name] = fn
    return result


def discover() -> list[tuple[str, DetectFn]]:
    """Return all detectors as a list of (name, detect_fn) tuples.

    Results are cached after the first call; call reset_cache() to reload.
    User detectors (from config.detectors_dir) override built-ins of the
    same name.
    """
    global _detectors
    if _detectors is not None:
        return _detectors

    # Built-ins first
    merged: dict[str, DetectFn] = _load_builtin_detectors()

    # User overrides
    user_dir = ""
    try:
        from bookmark_memex.config import get_config
        user_dir = get_config().detectors_dir
    except Exception:
        pass

    if user_dir:
        merged.update(_load_user_detectors(user_dir))

    _detectors = list(merged.items())
    return _detectors


def run_detectors(url: str, content: Optional[str] = None) -> Optional[dict]:
    """Run all detectors against *url*. First match wins. Returns dict or None."""
    for _name, fn in discover():
        result = fn(url, content)
        if result is not None:
            return result
    return None


def reset_cache() -> None:
    """Clear the cached detector list (forces reload on next discover() call)."""
    global _detectors
    _detectors = None
