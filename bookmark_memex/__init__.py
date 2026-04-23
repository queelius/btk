"""bookmark-memex: Personal bookmark archive for the memex ecosystem."""

# Read the installed-package version at runtime. This is robust to pytest
# configurations where `tests/bookmark_memex/` could shadow the real package
# on sys.path — `from bookmark_memex import __version__` would resolve to
# the shadow; importlib.metadata always consults dist-info.
try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("bookmark-memex")
except Exception:
    __version__ = "unknown"
