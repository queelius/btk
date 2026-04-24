"""Arkiv JSONL + schema.yaml exporter for bookmark-memex.

Output can be a directory, a ``.zip`` archive, or a ``.tar.gz`` tarball;
the choice is inferred from *out_path*'s extension. All three layouts
contain the same files:

- ``records.jsonl``: one JSON line per active bookmark/marginalia entry.
- ``schema.yaml``:   archive self-description + per-key metadata stats.
- ``README.md``:     arkiv ECHO frontmatter + human-readable explanation.

Record URI scheme follows the cross-archive contract::

    bookmark-memex://bookmark/<unique_id>
    bookmark-memex://marginalia/<uuid>

Compression choice prioritises longevity: ``.zip`` and ``.tar.gz`` are
both ubiquitous on every OS and scripting language (30+ years of tooling).
Modern compressors like ``zstd`` are deliberately avoided so the bundle
still opens in 2050.
"""
from __future__ import annotations

import io
import json
import os
import tarfile
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy import select

from bookmark_memex.models import Bookmark, Marginalia
from bookmark_memex.uri import build_bookmark_uri, build_marginalia_uri


# ---------------------------------------------------------------------------
# Schema declaration (module-level for introspection)
# ---------------------------------------------------------------------------

SCHEMA: dict = {
    "scheme": "bookmark-memex",
    "kinds": {
        "bookmark": {
            "description": "A saved URL with metadata.",
            "uri": "bookmark-memex://bookmark/<unique_id>",
            "fields": {
                "kind": "Always 'bookmark'.",
                "uri": "Canonical bookmark-memex URI for this bookmark.",
                "unique_id": "16-hex-character content-hash of the normalised URL.",
                "url": "The normalised bookmark URL.",
                "title": "Human-readable title.",
                "description": "Optional longer description.",
                "tags": "List of hierarchical tag strings.",
                "media": "Optional media metadata dict (may be null).",
                "starred": "Boolean — user has starred this bookmark.",
                "pinned": "Boolean — user has pinned this bookmark.",
                "visit_count": "Number of times this bookmark was visited.",
                "added": "ISO-8601 UTC datetime when the bookmark was added.",
            },
        },
        "marginalia": {
            "description": "A free-form note attached to a bookmark.",
            "uri": "bookmark-memex://marginalia/<uuid>",
            "fields": {
                "kind": "Always 'marginalia'.",
                "uri": "Canonical bookmark-memex URI for this note.",
                "uuid": "UUID hex string — durable note identifier.",
                "bookmark_uri": (
                    "URI of the parent bookmark, or null if the parent was deleted."
                ),
                "text": "Free-form note text.",
                "created_at": "ISO-8601 UTC datetime when the note was created.",
                "updated_at": "ISO-8601 UTC datetime when the note was last updated.",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Bundle format detection
# ---------------------------------------------------------------------------


def _detect_compression(path: str) -> str:
    """Infer output format from *path*'s extension.

    Returns one of ``"zip"``, ``"tar.gz"``, ``"dir"``.
    """
    lower = str(path).lower()
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return "tar.gz"
    return "dir"


# ---------------------------------------------------------------------------
# Record construction (single pass over the DB)
# ---------------------------------------------------------------------------


def _build_records(db) -> List[Dict[str, Any]]:
    """Collect all active bookmark + marginalia records from the DB.

    Returns a list of dicts in the order: bookmarks first (by id asc),
    then marginalia (by created_at asc).
    """
    records: List[Dict[str, Any]] = []

    with db._session() as session:
        bm_query = (
            select(Bookmark)
            .where(Bookmark.archived_at.is_(None))
            .order_by(Bookmark.id)
        )
        bookmarks = list(session.execute(bm_query).scalars())

        # Preload unique_ids so marginalia can reference the parent URI
        # without a second round-trip.
        id_to_unique: Dict[int, str] = {bm.id: bm.unique_id for bm in bookmarks}

        for bm in bookmarks:
            tag_names = [t.name for t in bm.tags]
            records.append(
                {
                    "kind": "bookmark",
                    "uri": build_bookmark_uri(bm.unique_id),
                    "unique_id": bm.unique_id,
                    "url": bm.url,
                    "title": bm.title,
                    "description": bm.description or "",
                    "tags": tag_names,
                    "media": bm.media,
                    "starred": bm.starred,
                    "pinned": bm.pinned,
                    "visit_count": bm.visit_count or 0,
                    "added": bm.added.isoformat() if bm.added else None,
                }
            )

        note_query = (
            select(Marginalia)
            .where(Marginalia.archived_at.is_(None))
            .order_by(Marginalia.created_at)
        )
        for note in session.execute(note_query).scalars():
            parent_uri: Optional[str] = None
            if note.bookmark_id is not None:
                parent_unique = id_to_unique.get(note.bookmark_id)
                if parent_unique is not None:
                    parent_uri = build_bookmark_uri(parent_unique)

            records.append(
                {
                    "kind": "marginalia",
                    "uri": build_marginalia_uri(note.id),
                    "uuid": note.id,
                    "bookmark_uri": parent_uri,
                    "text": note.text,
                    "created_at": note.created_at.isoformat() if note.created_at else None,
                    "updated_at": note.updated_at.isoformat() if note.updated_at else None,
                }
            )

    return records


# ---------------------------------------------------------------------------
# File serialisation helpers
# ---------------------------------------------------------------------------


def _records_to_jsonl_bytes(records: List[Dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    for rec in records:
        buf.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return buf.getvalue().encode("utf-8")


def _schema_yaml_bytes(records: List[Dict[str, Any]]) -> bytes:
    """Render schema.yaml with declared field docs + live per-kind counts."""
    counts = {"bookmark": 0, "marginalia": 0}
    for rec in records:
        kind = rec.get("kind")
        if kind in counts:
            counts[kind] += 1

    doc = {
        "scheme": SCHEMA["scheme"],
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "kinds": SCHEMA["kinds"],
    }
    buf = io.StringIO()
    buf.write("# Auto-generated by bookmark-memex. Edit freely.\n")
    yaml.safe_dump(doc, buf, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return buf.getvalue().encode("utf-8")


def _readme_bytes(num_bookmarks: int, num_marginalia: int) -> bytes:
    """Render README.md with ECHO frontmatter + usage notes."""
    try:
        from importlib.metadata import version as _pkg_version

        version = _pkg_version("bookmark-memex")
    except Exception:
        version = "unknown"

    today = date.today().isoformat()
    lines = [
        "---",
        "name: bookmark-memex archive",
        f'description: "{num_bookmarks} bookmarks + {num_marginalia} marginalia exported from bookmark-memex"',
        f"datetime: {today}",
        f"generator: bookmark-memex {version}",
        "contents:",
        "  - path: records.jsonl",
        "    description: Bookmark and marginalia records (arkiv JSONL format)",
        "  - path: schema.yaml",
        "    description: Record schema + per-kind counts",
        "---",
        "",
        "# bookmark-memex Archive",
        "",
        f"This archive contains {num_bookmarks} bookmark(s) and {num_marginalia} "
        "note(s) (marginalia)",
        "exported from bookmark-memex in [arkiv](https://github.com/alonzo-church/arkiv) format.",
        "",
        "Each line in `records.jsonl` is one record. Records are typed by `kind`:",
        "",
        "- `bookmark`: a saved URL with title, description, tags, and media metadata.",
        "- `marginalia`: a free-form note attached (by URI) to a bookmark.",
        "",
        "URIs follow the cross-archive `bookmark-memex://` scheme and stay stable",
        "across re-imports, so marginalia survive their parent bookmark being",
        "re-imported or round-tripped through another archive.",
        "",
        "## Importing back into bookmark-memex",
        "",
        "```bash",
        "# Replace local state (default): duplicates skipped by unique_id",
        "bookmark-memex import <this bundle> --format arkiv",
        "",
        "# Merge into existing bookmarks without clobbering local tags/notes",
        "bookmark-memex import <this bundle> --format arkiv --merge",
        "```",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _write_zip(path: str, jsonl: bytes, schema_yaml: bytes, readme: bytes) -> None:
    """Write the three bundle files into a single .zip archive."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("records.jsonl", jsonl)
        zf.writestr("schema.yaml", schema_yaml)
        zf.writestr("README.md", readme)


def _write_tar_gz(path: str, jsonl: bytes, schema_yaml: bytes, readme: bytes) -> None:
    """Write the three bundle files into a single .tar.gz archive."""
    with tarfile.open(path, "w:gz") as tf:
        for name, data in (
            ("records.jsonl", jsonl),
            ("schema.yaml", schema_yaml),
            ("README.md", readme),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_arkiv(db, out_path) -> dict:
    """Export active bookmarks and marginalia as an arkiv bundle.

    Output format is inferred from *out_path*'s extension:

    - ``path.zip``            → single zip file
    - ``path.tar.gz``/`.tgz`  → single gzip-compressed tarball
    - any other path          → directory containing records.jsonl,
                                schema.yaml, and README.md

    Parameters
    ----------
    db:
        A ``bookmark_memex.db.Database`` instance.
    out_path:
        Destination path. Extension determines bundle format.

    Returns
    -------
    dict
        ``{"path": str, "format": "dir"|"zip"|"tar.gz",
           "counts": {"bookmark": N, "marginalia": N, "annotation": N}}``

        The ``annotation`` key is a backwards-compat alias for
        ``marginalia`` so callers that read the old key still work.
    """
    out_path_str = str(out_path)
    records = _build_records(db)
    counts = {"bookmark": 0, "marginalia": 0}
    for rec in records:
        kind = rec.get("kind")
        if kind in counts:
            counts[kind] += 1

    jsonl_bytes = _records_to_jsonl_bytes(records)
    schema_bytes = _schema_yaml_bytes(records)
    readme_bytes = _readme_bytes(counts["bookmark"], counts["marginalia"])

    fmt = _detect_compression(out_path_str)
    if fmt == "zip":
        # Ensure parent directory exists before opening the zipfile.
        Path(out_path_str).parent.mkdir(parents=True, exist_ok=True)
        _write_zip(out_path_str, jsonl_bytes, schema_bytes, readme_bytes)
    elif fmt == "tar.gz":
        Path(out_path_str).parent.mkdir(parents=True, exist_ok=True)
        _write_tar_gz(out_path_str, jsonl_bytes, schema_bytes, readme_bytes)
    else:
        out_dir = Path(out_path_str)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_file(str(out_dir / "records.jsonl"), jsonl_bytes)
        _write_file(str(out_dir / "schema.yaml"), schema_bytes)
        _write_file(str(out_dir / "README.md"), readme_bytes)

    # Mirror marginalia count as "annotation" for any caller still reading
    # the pre-rename shape.
    counts_with_alias = dict(counts)
    counts_with_alias["annotation"] = counts["marginalia"]

    return {
        "path": out_path_str,
        "format": fmt,
        "counts": counts_with_alias,
        # Backcompat shape for existing callers that read these two keys.
        "records_path": (
            out_path_str
            if fmt != "dir"
            else str(Path(out_path_str) / "records.jsonl")
        ),
        "schema_path": (
            out_path_str
            if fmt != "dir"
            else str(Path(out_path_str) / "schema.yaml")
        ),
    }
