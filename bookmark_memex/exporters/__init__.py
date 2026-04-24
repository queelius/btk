"""Exporters for bookmark-memex.

Public API
----------
``export_file(db, path, format, bookmark_ids, **kwargs)``
    Dispatch to the format-specific exporter.  Supported formats:
    ``json``, ``csv``, ``text``, ``markdown``, ``m3u``, ``arkiv``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from bookmark_memex.exporters.formats import (
    export_csv,
    export_json,
    export_m3u,
    export_markdown,
    export_text,
)
from bookmark_memex.exporters.arkiv import export_arkiv
from bookmark_memex.exporters.html_app import export_html_app

_DISPATCHERS = {
    "json": export_json,
    "csv": export_csv,
    "text": export_text,
    "markdown": export_markdown,
    "m3u": export_m3u,
}

_SUPPORTED_FORMATS = sorted(list(_DISPATCHERS) + ["arkiv", "html-app"])


def export_file(
    db,
    path: Path,
    format: str = "json",
    bookmark_ids: Optional[list[int]] = None,
    **kwargs,
) -> None:
    """Export bookmarks to a file in the given format.

    Parameters
    ----------
    db:
        A ``bookmark_memex.db.Database`` instance.
    path:
        Destination file path. For ``arkiv`` a directory or bundle
        (``.zip``/``.tar.gz``); for ``html-app`` a directory.
    format:
        One of ``json``, ``csv``, ``text``, ``markdown``, ``m3u``,
        ``arkiv``, ``html-app``.
    bookmark_ids:
        Optional list of primary-key IDs to restrict the export.
        Not applicable to ``arkiv`` or ``html-app`` (which always
        include all active records).
    **kwargs:
        Forwarded to the format-specific function.

    Raises
    ------
    ValueError
        For unrecognised format strings.
    """
    path = Path(path)

    if format == "arkiv":
        # arkiv exporter doesn't accept html-app kwargs.
        kwargs.pop("single_file", None)
        export_arkiv(db, path, **kwargs)
        return

    if format == "html-app":
        # html-app exporter doesn't accept arkiv kwargs.
        kwargs.pop("include_history", None)
        export_html_app(db, path, **kwargs)
        return

    fn = _DISPATCHERS.get(format)
    if fn is None:
        raise ValueError(
            f"unknown format {format!r}. Choose from: {', '.join(_SUPPORTED_FORMATS)}"
        )

    # Flat-file formats don't take format-specific options.
    kwargs.pop("single_file", None)
    kwargs.pop("include_history", None)
    fn(db, path, bookmark_ids=bookmark_ids, **kwargs)
