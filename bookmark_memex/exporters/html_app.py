"""HTML SPA exporter for bookmark-memex.

Two output modes, both sharing the same template:

**single-file** (default) — one portable ``.html`` with sql-wasm.js
inlined as an inline ``<script>`` and sql-wasm.wasm + the gzipped
database embedded as base64 inside two ``<script type="application/base64">``
tags. The template decodes them client-side via ``atob`` +
``DecompressionStream('gzip')``. Produces exactly one file suitable
for email attachments, Dropbox, Netlify drop, etc.

**directory** (opt-in via ``single_file=False``) — a folder:

  - ``index.html``                      the same template, but with
    empty base64 script tags so the loader falls back to fetching
  - ``sql-wasm.js``, ``sql-wasm.wasm``  vendored sql.js
  - ``bookmarks.db.gz``                 gzipped copy of the source DB

Both modes honour the C6 workspace contract: no CDN dependency, FTS5
shadow tables stripped, ``journal_mode=DELETE`` on the shipped DB,
gzip compression for the DB, hash routing, no default API endpoint.

Why single-file is the default: the other single-archive-scope siblings
(mail-memex, book-memex, photo-memex) all emit single-file HTML. Only
llm-memex uses the directory form, and only because it has to ship a
sibling ``assets/`` directory for media blocks. Bookmarks have no peer
assets, so single-file is the natural fit.
"""
from __future__ import annotations

import base64
import gzip
import shutil
import sqlite3
import tempfile
from pathlib import Path


_VENDORED_DIR = Path(__file__).parent / "vendored"
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_SQL_JS_FILE = "sql-wasm.js"
_SQL_WASM_FILE = "sql-wasm.wasm"

# FTS5 virtual tables in bookmark-memex. Listed explicitly rather than
# discovered so we don't accidentally drop something else that happens
# to be named like an FTS5 shadow table. Includes the legacy
# "annotations_fts" name in case we're shipping a database that was
# migrated but hasn't rebuilt its FTS index yet.
_FTS5_TABLES = (
    "bookmarks_fts",
    "content_fts",
    "marginalia_fts",
    "annotations_fts",
)

# gzip level 6 is the sweet spot: near-maximum ratio, modest CPU.
_DB_GZIP_LEVEL = 6


def _strip_fts5_and_vacuum(db_path: Path) -> None:
    """Drop FTS5 virtual tables, set journal_mode=DELETE, and VACUUM."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        for fts in _FTS5_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {fts}")
        conn.commit()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("VACUUM")


def _gzip_file(src: Path, dst: Path, level: int = _DB_GZIP_LEVEL) -> None:
    """Stream src → gzip → dst, then delete src."""
    with open(src, "rb") as fin, gzip.open(
        str(dst), "wb", compresslevel=level
    ) as fout:
        shutil.copyfileobj(fin, fout, length=1024 * 1024)
    src.unlink()


def _gzip_bytes(data: bytes, level: int = _DB_GZIP_LEVEL) -> bytes:
    """Return gzip-compressed *data* as bytes (for single-file base64)."""
    return gzip.compress(data, compresslevel=level)


def _read_template() -> str:
    return (_TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")


def _read_vendor(name: str) -> bytes:
    return (_VENDORED_DIR / name).read_bytes()


def _snapshot_db(src_db_path: Path, dst_db_path: Path) -> None:
    """Snapshot the live DB to *dst_db_path* without mutating the source.

    Uses SQLite's backup API rather than a raw file copy. The live DB
    runs with ``journal_mode=WAL`` for import performance, so recent
    writes may still be in ``<db>-wal`` and missing from the main file.
    ``connection.backup()`` transparently reads both the main file and
    the WAL, producing a self-contained snapshot without needing a
    checkpoint on the source.
    """
    src = sqlite3.connect(str(src_db_path))
    dst = sqlite3.connect(str(dst_db_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _prepare_db_bytes(src_db_path: Path) -> bytes:
    """Return the bytes of a stripped-and-vacuumed copy of the source DB.

    Works in a temp file so we can run VACUUM (which operates only on
    on-disk databases) without disturbing the live library.
    """
    with tempfile.TemporaryDirectory(prefix="bm_html_app_") as tmp:
        tmp_db = Path(tmp) / "copy.db"
        _snapshot_db(src_db_path, tmp_db)
        _strip_fts5_and_vacuum(tmp_db)
        return tmp_db.read_bytes()


def _inline_script_src(html: str, filename: str, body: str) -> str:
    """Replace ``<script src="<filename>"></script>`` with inline JS."""
    marker = f'<script src="{filename}"></script>'
    # Guard: only one occurrence expected in the template.
    if marker not in html:
        raise RuntimeError(
            f"SPA template missing expected '{marker}'; template drift?"
        )
    # The closing </script> in the replacement must not be misread by the
    # HTML parser if `body` itself contains "</script>" — but sql-wasm.js
    # does not, and we control the template. Still, escape defensively.
    safe = body.replace("</script>", "<\\/script>")
    inline = f"<script>\n{safe}\n</script>"
    return html.replace(marker, inline, 1)


def _fill_base64_script(html: str, element_id: str, data: bytes) -> str:
    """Fill ``<script id="<id>" type="application/base64"></script>``."""
    marker = f'<script id="{element_id}" type="application/base64"></script>'
    if marker not in html:
        raise RuntimeError(
            f"SPA template missing expected '{marker}'; template drift?"
        )
    b64 = base64.b64encode(data).decode("ascii")
    replacement = (
        f'<script id="{element_id}" type="application/base64">\n{b64}\n</script>'
    )
    return html.replace(marker, replacement, 1)


def export_html_app(
    db,
    out_path,
    *,
    single_file: bool = True,
    compress_db: bool = True,
) -> dict:
    """Export the archive as a self-contained HTML SPA.

    Parameters
    ----------
    db:
        A ``bookmark_memex.db.Database`` instance.
    out_path:
        Target path. In ``single_file`` mode, a ``.html`` filename
        (``.html`` auto-appended if missing). In directory mode, a
        directory path to populate.
    single_file:
        ``True`` (default) → emit one portable ``index.html`` with
        sql.js and the DB base64-embedded. ``False`` → emit a directory
        with sibling assets.
    compress_db:
        Gzip the DB (default ``True``). Only relevant for directory mode;
        single-file mode always gzips before base64-encoding because the
        transfer-size win is the whole point.

    Returns
    -------
    dict
        For single-file mode::

            {"mode": "single-file", "path": <file path>,
             "html_bytes": int, "original_db_bytes": int,
             "embedded_db_bytes": int}

        For directory mode::

            {"mode": "dir", "path": <dir path>,
             "db_file": <filename>, "compressed": bool,
             "original_db_bytes": int, "shipped_db_bytes": int}
    """
    return (
        _export_single_file(db, out_path)
        if single_file
        else _export_directory(db, out_path, compress_db=compress_db)
    )


def _export_single_file(db, out_path) -> dict:
    """Emit a single self-contained HTML file."""
    out = Path(out_path)
    # Auto-append .html so `bookmark-memex export my_archive` does the
    # obvious thing rather than producing a file with no extension.
    if not out.suffix:
        out = out.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)

    src_db_path = Path(db.path)
    original_size = src_db_path.stat().st_size if src_db_path.exists() else 0

    template = _read_template()

    # 1) inline sql-wasm.js
    sqljs_src = _read_vendor(_SQL_JS_FILE).decode("utf-8")
    html = _inline_script_src(template, _SQL_JS_FILE, sqljs_src)

    # 2) base64-inline sql-wasm.wasm
    wasm_bytes = _read_vendor(_SQL_WASM_FILE)
    html = _fill_base64_script(html, "bm-wasm-b64", wasm_bytes)

    # 3) prep + gzip + base64-inline the DB
    db_raw = _prepare_db_bytes(src_db_path)
    db_gz = _gzip_bytes(db_raw)
    html = _fill_base64_script(html, "bm-db-b64", db_gz)

    out.write_text(html, encoding="utf-8")

    return {
        "mode": "single-file",
        "path": str(out),
        "html_bytes": out.stat().st_size,
        "original_db_bytes": original_size,
        "embedded_db_bytes": len(db_gz),
    }


def _export_directory(db, out_path, *, compress_db: bool) -> dict:
    """Emit a directory with the SPA and sibling asset files."""
    out_dir = Path(out_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    src_db_path = Path(db.path)
    original_size = src_db_path.stat().st_size if src_db_path.exists() else 0

    # 1) index.html (template verbatim — the placeholder <script src=...>
    #    stays, and the base64 script elements are left empty so the
    #    runtime loader falls back to fetching sibling files).
    (out_dir / "index.html").write_text(_read_template(), encoding="utf-8")

    # 2) vendored sql.js (sibling files)
    for filename in (_SQL_JS_FILE, _SQL_WASM_FILE):
        src = _VENDORED_DIR / filename
        if src.exists():
            shutil.copy2(src, out_dir / filename)

    # 3) DB snapshot (WAL-aware, read-only against source) + strip +
    #    optionally gzip.
    dest_db = out_dir / "bookmarks.db"
    _snapshot_db(src_db_path, dest_db)
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
        "mode": "dir",
        "path": str(out_dir),
        "db_file": db_filename,
        "compressed": compress_db,
        "original_db_bytes": original_size,
        "shipped_db_bytes": shipped_bytes,
    }
