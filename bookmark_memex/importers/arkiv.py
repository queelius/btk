"""Import an arkiv bundle back into bookmark-memex.

Bundles emitted by :mod:`bookmark_memex.exporters.arkiv` (or any other
tool following the arkiv spec, within reason) are read, classified by
record kind, and inserted into the DB.

Supported input layouts (all auto-detected):

- directory with ``records.jsonl``, ``README.md``, and ``schema.yaml``
- ``.zip`` file containing those files
- ``.tar.gz`` / ``.tgz`` file containing those files
- bare ``.jsonl`` file of arkiv records (no README/schema needed)
- ``.jsonl.gz`` file of gzipped arkiv records — the format the browser
  SPA emits for round-tripping annotations back to the primary DB

This is intentionally forgiving: if ``README.md`` or ``schema.yaml`` is
missing but ``records.jsonl`` is present, we still import. The bundle's
"identity as a bookmark-memex arkiv" is a soft claim; the JSONL records
are what we actually need.

Round-trip fidelity:

- Bookmarks: identified by ``unique_id`` (16-char hash of normalised URL).
  Re-importing the same bundle is safe — duplicates are merged into the
  existing row via :meth:`Database.add`, which preserves local tags,
  title, starred/pinned flags, and description.
- Annotations: identified by UUID. Uses ``INSERT OR IGNORE`` semantics
  via :meth:`Database.merge_annotation`, so re-importing the same
  bundle does not create duplicate notes.

``--merge`` vs default: bookmark-memex's :meth:`Database.add` is already
merge-friendly on existing rows (never clobbers local state), so the
flag is effectively a no-op here. We accept it for CLI parity with
the rest of the ``*-memex`` ecosystem and to reserve the semantic for
a future stricter-add mode.
"""
from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from bookmark_memex.db import Database


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _jsonl_peek_first_record(reader) -> Optional[Dict[str, Any]]:
    """Return the first parsed JSONL record, or None if unparseable/empty."""
    try:
        for line in reader:
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            return rec if isinstance(rec, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return None


def _is_bookmark_memex_arkiv_record(rec: Dict[str, Any]) -> bool:
    """Heuristic: is this record from bookmark-memex?

    A record from bookmark-memex arkiv export has ``kind`` in
    {"bookmark", "annotation"} and either a ``uri`` that starts with
    ``bookmark-memex://`` (strict) or a recognisable shape.
    """
    if not isinstance(rec, dict):
        return False
    kind = rec.get("kind")
    if kind not in ("bookmark", "annotation"):
        return False
    uri = rec.get("uri", "")
    if isinstance(uri, str) and uri.startswith("bookmark-memex://"):
        return True
    # Permissive fallback: accept anything with a recognisable kind and
    # a required identifier (URL for bookmarks, UUID for annotations).
    if kind == "bookmark" and ("url" in rec or "unique_id" in rec):
        return True
    if kind == "annotation" and ("uuid" in rec or "text" in rec):
        return True
    return False


def detect(path: str | Path) -> bool:
    """Return True if *path* looks like an arkiv bundle we can read."""
    p = Path(path)
    if not p.exists():
        return False

    if p.is_dir():
        jsonl = p / "records.jsonl"
        if not jsonl.is_file():
            return False
        with open(jsonl, "r", encoding="utf-8") as f:
            rec = _jsonl_peek_first_record(f)
        return rec is not None and _is_bookmark_memex_arkiv_record(rec)

    lower = str(p).lower()

    if lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(p) as zf:
                names = set(zf.namelist())
                if "records.jsonl" not in names:
                    return False
                with zf.open("records.jsonl") as f:
                    rec = _jsonl_peek_first_record(f)
            return rec is not None and _is_bookmark_memex_arkiv_record(rec)
        except (zipfile.BadZipFile, KeyError):
            return False

    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        try:
            with tarfile.open(p, "r:gz") as tf:
                try:
                    member = tf.getmember("records.jsonl")
                except KeyError:
                    return False
                extracted = tf.extractfile(member)
                if extracted is None:
                    return False
                rec = _jsonl_peek_first_record(extracted)
            return rec is not None and _is_bookmark_memex_arkiv_record(rec)
        except tarfile.TarError:
            return False

    if lower.endswith(".jsonl.gz"):
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                rec = _jsonl_peek_first_record(f)
            return rec is not None and _is_bookmark_memex_arkiv_record(rec)
        except (OSError, gzip.BadGzipFile):
            return False

    if lower.endswith(".jsonl"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                rec = _jsonl_peek_first_record(f)
            return rec is not None and _is_bookmark_memex_arkiv_record(rec)
        except OSError:
            return False

    return False


# ---------------------------------------------------------------------------
# Bundle reading
# ---------------------------------------------------------------------------


def _open_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    """Yield records from the records.jsonl inside a bundle, whatever its shape."""
    p = Path(path)
    if p.is_dir():
        with open(p / "records.jsonl", "r", encoding="utf-8") as f:
            yield from _parse_jsonl_lines(f)
        return

    lower = str(p).lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(p) as zf:
            with zf.open("records.jsonl") as f:
                text = io.TextIOWrapper(f, encoding="utf-8")
                yield from _parse_jsonl_lines(text)
        return
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        with tarfile.open(p, "r:gz") as tf:
            member = tf.getmember("records.jsonl")
            extracted = tf.extractfile(member)
            if extracted is None:
                return
            text = io.TextIOWrapper(extracted, encoding="utf-8")
            yield from _parse_jsonl_lines(text)
        return
    if lower.endswith(".jsonl.gz"):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            yield from _parse_jsonl_lines(f)
        return
    if lower.endswith(".jsonl"):
        with open(p, "r", encoding="utf-8") as f:
            yield from _parse_jsonl_lines(f)
        return
    raise ValueError(f"unrecognized arkiv bundle: {path!r}")


def _parse_jsonl_lines(reader) -> Iterable[Dict[str, Any]]:
    for line in reader:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            # Tolerate individual bad lines rather than failing the whole import.
            continue


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    cleaned = ts.replace("Z", "+00:00").split("+")[0]
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_bookmark_unique_id_from_uri(uri: Optional[str]) -> Optional[str]:
    """Extract bookmark unique_id from a ``bookmark-memex://bookmark/<id>`` URI."""
    if not uri:
        return None
    prefix = "bookmark-memex://bookmark/"
    if not uri.startswith(prefix):
        return None
    tail = uri[len(prefix) :]
    # Fragment-only portion up to the first separator
    for sep in ("?", "#"):
        idx = tail.find(sep)
        if idx >= 0:
            tail = tail[:idx]
    return tail or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_arkiv(
    db: Database,
    path: str | Path,
    *,
    merge: bool = False,
    source_name: Optional[str] = None,
) -> Dict[str, int]:
    """Import an arkiv bundle into *db*.

    Parameters
    ----------
    db:
        Target :class:`Database`.
    path:
        Path to a directory, ``.zip``, ``.tar.gz``/``.tgz``, bare
        ``.jsonl``, or ``.jsonl.gz`` bundle.
    merge:
        Reserved for CLI parity with the rest of the ``*-memex``
        ecosystem. Currently a no-op because :meth:`Database.add` is
        always merge-friendly.
    source_name:
        Optional identifier written to every imported bookmark's
        source row. Defaults to the bundle path.

    Returns
    -------
    dict
        ``{"bookmarks_added": N, "bookmarks_seen": N,
           "annotations_added": N, "annotations_seen": N,
           "annotations_skipped_existing": N}``
    """
    stats = {
        "bookmarks_added": 0,
        "bookmarks_seen": 0,
        "annotations_added": 0,
        "annotations_seen": 0,
        "annotations_skipped_existing": 0,
    }
    src_name = source_name or str(path)

    # Two-pass: bookmarks first so annotations can find their parent.
    records = list(_open_jsonl(path))

    for rec in records:
        if not isinstance(rec, dict):
            continue
        if rec.get("kind") != "bookmark":
            continue
        stats["bookmarks_seen"] += 1

        url = rec.get("url")
        if not url:
            continue

        # Track whether the bookmark existed before we called add().
        # This gives us a meaningful "added" count distinct from "seen".
        existing = db.get_by_unique_id(rec.get("unique_id") or "") if rec.get("unique_id") else None

        db.add(
            url,
            title=rec.get("title") or "",
            description=rec.get("description") or None,
            tags=list(rec.get("tags") or []),
            starred=bool(rec.get("starred", False)),
            pinned=bool(rec.get("pinned", False)),
            source_type="arkiv",
            source_name=src_name,
        )

        if existing is None:
            stats["bookmarks_added"] += 1

    for rec in records:
        if not isinstance(rec, dict):
            continue
        if rec.get("kind") != "annotation":
            continue
        stats["annotations_seen"] += 1

        uuid = rec.get("uuid")
        text = rec.get("text") or ""
        if not uuid or not text:
            continue

        parent_uid = _parse_bookmark_unique_id_from_uri(rec.get("bookmark_uri"))
        created = _parse_timestamp(rec.get("created_at"))
        updated = _parse_timestamp(rec.get("updated_at"))

        inserted = db.merge_annotation(
            uuid=uuid,
            bookmark_unique_id=parent_uid,
            text=text,
            created_at=created,
            updated_at=updated,
        )
        if inserted:
            stats["annotations_added"] += 1
        else:
            stats["annotations_skipped_existing"] += 1

    return stats
