"""HTML SPA exporter for bookmark-memex.

Produces a self-contained browsable directory (the C6 contract from the
workspace CLAUDE.md):

- ``index.html``                      — single-page app
- ``sql-wasm.js``, ``sql-wasm.wasm``  — vendored sql.js (no CDN dependency)
- ``bookmarks.db.gz``                 — gzipped copy of the source DB with
  FTS5 shadow tables dropped and journal_mode set to DELETE so no
  ``.db-wal``/``.db-shm`` sidecars travel with it.

The SPA fetches the ``.db.gz`` and decompresses transparently via the
browser's ``DecompressionStream('gzip')``, then uses sql.js to query it.
Search uses ``LIKE`` (sql.js cannot execute FTS5 MATCH); that limitation
is why we ship the DB without the FTS5 virtual tables — they are about
half of a typical archive's bytes on disk.

The exported bundle is *genuinely* offline: no CDN, no default API
endpoint, no authentication on the author's behalf. Any chat/LLM features
added later must stay behind an explicit user-configured Settings gate.

Hash routing keeps the URL bookmarkable:

- ``#/``                → home (recent bookmarks)
- ``#/search/<q>``      → full-library LIKE search
- ``#/tag/<name>``      → bookmarks with a given tag
- ``#/bookmark/<uid>``  → detail view for a specific bookmark
"""
from __future__ import annotations

import gzip
import shutil
import sqlite3
from pathlib import Path


_VENDORED_DIR = Path(__file__).parent / "vendored"
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_SQL_JS_FILES = ("sql-wasm.js", "sql-wasm.wasm")

# FTS5 virtual tables in bookmark-memex. Listed explicitly rather than
# discovered so we don't accidentally drop something else that happens
# to be named like an FTS5 shadow table.
_FTS5_TABLES = ("bookmarks_fts", "content_fts", "annotations_fts")

# gzip level 6 is the sweet spot: near-maximum ratio, modest CPU.
_DB_GZIP_LEVEL = 6


def _strip_fts5_and_vacuum(db_path: Path) -> None:
    """Drop FTS5 virtual tables, set journal_mode=DELETE, and VACUUM.

    sql.js (used by the HTML SPA) is not compiled with FTS5. The shadow
    tables are roughly half of a typical DB's bytes, so dropping them
    before export substantially shrinks the transferred gzip.

    Setting journal_mode=DELETE ensures no ``.db-wal`` or ``.db-shm``
    sidecar files are left next to the exported DB if the process is
    interrupted. VACUUM produces a fully-packed file.
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        for fts in _FTS5_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {fts}")
        conn.commit()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("VACUUM")


def _gzip_file(src: Path, dst: Path, level: int = _DB_GZIP_LEVEL) -> None:
    """Stream src → gzip → dst, then delete src.

    Chunked to avoid loading the whole DB into memory for big archives.
    """
    with open(src, "rb") as fin, gzip.open(
        str(dst), "wb", compresslevel=level
    ) as fout:
        shutil.copyfileobj(fin, fout, length=1024 * 1024)
    src.unlink()


def _read_template() -> str:
    """Return the SPA HTML template bundled with the package."""
    path = _TEMPLATES_DIR / "index.html"
    return path.read_text(encoding="utf-8")


def export_html_app(db, out_path, *, compress_db: bool = True) -> dict:
    """Export the archive as a self-contained HTML SPA directory.

    Parameters
    ----------
    db:
        A ``bookmark_memex.db.Database`` instance. ``db.path`` is used
        to locate the source SQLite file.
    out_path:
        Destination directory. Created if it does not exist.
    compress_db:
        Gzip the exported DB (default True). Set to False if you want
        the raw ``bookmarks.db`` next to ``index.html`` (e.g. for
        tooling that cannot handle ``DecompressionStream``).

    Returns
    -------
    dict
        ``{"path": <out_dir>, "db_file": <db filename>, "compressed": bool,
           "original_db_bytes": int, "shipped_db_bytes": int}``
    """
    out_dir = Path(out_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    src_db_path = Path(db.path)
    original_size = src_db_path.stat().st_size if src_db_path.exists() else 0

    # 1) Write index.html from the bundled template
    (out_dir / "index.html").write_text(_read_template(), encoding="utf-8")

    # 2) Vendor sql.js (copy, don't link — must survive being zipped up)
    for filename in _SQL_JS_FILES:
        src = _VENDORED_DIR / filename
        if src.exists():
            shutil.copy2(src, out_dir / filename)

    # 3) Copy DB, strip FTS5, optionally gzip
    dest_db = out_dir / "bookmarks.db"
    shutil.copy2(src_db_path, dest_db)
    _strip_fts5_and_vacuum(dest_db)

    if compress_db:
        gzipped = out_dir / "bookmarks.db.gz"
        _gzip_file(dest_db, gzipped)
        shipped_bytes = gzipped.stat().st_size
        db_filename = "bookmarks.db.gz"
    else:
        shipped_bytes = dest_db.stat().st_size
        db_filename = "bookmarks.db"

    return {
        "path": str(out_dir),
        "db_file": db_filename,
        "compressed": compress_db,
        "original_db_bytes": original_size,
        "shipped_db_bytes": shipped_bytes,
    }
