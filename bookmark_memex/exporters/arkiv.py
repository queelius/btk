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

from bookmark_memex.models import Bookmark, HistoryUrl, HistoryVisit, Marginalia
from bookmark_memex.uri import (
    build_bookmark_uri,
    build_history_url_uri,
    build_marginalia_uri,
    build_visit_uri,
)


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
            "description": "A free-form note attached to any record kind.",
            "uri": "bookmark-memex://marginalia/<uuid>",
            "fields": {
                "kind": "Always 'marginalia'.",
                "uri": "Canonical bookmark-memex URI for this note.",
                "uuid": "UUID hex string (durable note identifier).",
                "bookmark_uri": (
                    "URI of the parent bookmark, or null if not attached "
                    "to a bookmark."
                ),
                "history_url_uri": (
                    "URI of the parent history-url, or null."
                ),
                "visit_uri": (
                    "URI of the parent visit, or null."
                ),
                "text": "Free-form note text.",
                "created_at": "ISO-8601 UTC datetime when the note was created.",
                "updated_at": "ISO-8601 UTC datetime when the note was last updated.",
            },
        },
        "history-url": {
            "description": (
                "Aggregate per-URL browser history record. Emitted only "
                "when the exporter runs with include_history=True. "
                "Observational, not curated: the presence of a history-url "
                "record does not imply the user saved the URL."
            ),
            "uri": "bookmark-memex://history-url/<unique_id>",
            "fields": {
                "kind": "Always 'history-url'.",
                "uri": "Canonical URI for this history-url.",
                "unique_id": (
                    "16-hex content-hash. Derived from a stricter "
                    "canonical form than the bookmark unique_id: tracking "
                    "parameters (utm_*, gclid, fbclid, ...) are stripped "
                    "and fragments dropped before hashing."
                ),
                "url": "The stripped, canonical form of the URL.",
                "title": "Latest observed page title, or null.",
                "first_visited": "ISO-8601 UTC of earliest observed visit.",
                "last_visited": "ISO-8601 UTC of most recent observed visit.",
                "visit_count": "Total observed visits across all sources.",
                "typed_count": (
                    "Number of visits the browser marked as 'typed' "
                    "(user typed the URL rather than clicking a link)."
                ),
                "media": "Optional media metadata dict from detectors.",
            },
        },
        "visit": {
            "description": (
                "A single observed visit event. Emitted only when the "
                "exporter runs with include_history=True."
            ),
            "uri": "bookmark-memex://visit/<uuid>",
            "fields": {
                "kind": "Always 'visit'.",
                "uri": "Canonical URI for this visit.",
                "uuid": "UUID hex string, stable across re-imports.",
                "history_url_uri": "URI of the parent history-url.",
                "visited_at": "ISO-8601 UTC datetime when the visit occurred.",
                "transition": (
                    "How the user arrived at the URL: 'link', 'typed', "
                    "'bookmark', 'reload', 'redirect', 'generated', "
                    "'subframe', 'form_submit', 'download', or 'other'."
                ),
                "duration_ms": (
                    "How long the page was in foreground (Chrome only; "
                    "null for Firefox)."
                ),
                "from_visit_uri": (
                    "URI of the referring visit, or null if the referrer "
                    "was pruned by the browser before capture."
                ),
                "source_type": "'chrome' or 'firefox'.",
                "source_name": (
                    "Profile identifier, e.g. 'Chrome/Default' or "
                    "'Firefox/default-release'."
                ),
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


def _build_records(
    db,
    *,
    include_history: bool = False,
) -> List[Dict[str, Any]]:
    """Collect arkiv records from the DB.

    Order: bookmarks (by id) first, then history-urls (by id) if
    *include_history*, then visits (by visited_at) if *include_history*,
    then marginalia (by created_at) last so every note's parent URI has
    already appeared in the stream.

    History records are opt-in because history is both large and more
    sensitive than curated bookmarks. See
    ``specs/2026-04-20-history-capture.md``.
    """
    records: List[Dict[str, Any]] = []

    with db._session() as session:
        bm_query = (
            select(Bookmark)
            .where(Bookmark.archived_at.is_(None))
            .order_by(Bookmark.id)
        )
        bookmarks = list(session.execute(bm_query).scalars())

        # Preload unique_ids so marginalia can reference parent URIs
        # without per-note lookups.
        bookmark_id_to_unique: Dict[int, str] = {
            bm.id: bm.unique_id for bm in bookmarks
        }

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

        history_url_id_to_unique: Dict[int, str] = {}
        history_visit_id_to_unique: Dict[int, str] = {}

        if include_history:
            hu_query = (
                select(HistoryUrl)
                .where(HistoryUrl.archived_at.is_(None))
                .order_by(HistoryUrl.id)
            )
            history_urls = list(session.execute(hu_query).scalars())
            for hu in history_urls:
                history_url_id_to_unique[hu.id] = hu.unique_id
                records.append(
                    {
                        "kind": "history-url",
                        "uri": build_history_url_uri(hu.unique_id),
                        "unique_id": hu.unique_id,
                        "url": hu.url,
                        "title": hu.title,
                        "first_visited": (
                            hu.first_visited.isoformat() if hu.first_visited else None
                        ),
                        "last_visited": (
                            hu.last_visited.isoformat() if hu.last_visited else None
                        ),
                        "visit_count": hu.visit_count or 0,
                        "typed_count": hu.typed_count or 0,
                        "media": hu.media,
                    }
                )

            hv_query = (
                select(HistoryVisit)
                .where(HistoryVisit.archived_at.is_(None))
                .order_by(HistoryVisit.visited_at)
            )
            visits = list(session.execute(hv_query).scalars())
            # First pass: record every visit's unique_id so referrers in
            # the same batch can be resolved without a second DB hit.
            for v in visits:
                history_visit_id_to_unique[v.id] = v.unique_id

            for v in visits:
                parent_url_unique = history_url_id_to_unique.get(v.url_id)
                parent_history_url_uri = (
                    build_history_url_uri(parent_url_unique)
                    if parent_url_unique is not None
                    else None
                )
                from_visit_uri = None
                if v.from_visit_id is not None:
                    from_uid = history_visit_id_to_unique.get(v.from_visit_id)
                    if from_uid is not None:
                        from_visit_uri = build_visit_uri(from_uid)
                records.append(
                    {
                        "kind": "visit",
                        "uri": build_visit_uri(v.unique_id),
                        "uuid": v.unique_id,
                        "history_url_uri": parent_history_url_uri,
                        "visited_at": v.visited_at.isoformat(),
                        "transition": v.transition,
                        "duration_ms": v.duration_ms,
                        "from_visit_uri": from_visit_uri,
                        "source_type": v.source_type,
                        "source_name": v.source_name,
                    }
                )

        # Marginalia always comes last so every parent URI it might
        # reference has already appeared in the stream.
        note_query = (
            select(Marginalia)
            .where(Marginalia.archived_at.is_(None))
            .order_by(Marginalia.created_at)
        )
        for note in session.execute(note_query).scalars():
            parent_bookmark_uri: Optional[str] = None
            if note.bookmark_id is not None:
                parent_unique = bookmark_id_to_unique.get(note.bookmark_id)
                if parent_unique is not None:
                    parent_bookmark_uri = build_bookmark_uri(parent_unique)

            parent_history_url_uri_note: Optional[str] = None
            if note.history_url_id is not None:
                parent_hu = history_url_id_to_unique.get(note.history_url_id)
                if parent_hu is None and include_history is False:
                    # Look up on demand when history wasn't otherwise loaded.
                    hu_row = session.get(HistoryUrl, note.history_url_id)
                    if hu_row is not None:
                        parent_hu = hu_row.unique_id
                if parent_hu is not None:
                    parent_history_url_uri_note = build_history_url_uri(parent_hu)

            parent_visit_uri_note: Optional[str] = None
            if note.history_visit_id is not None:
                parent_v = history_visit_id_to_unique.get(note.history_visit_id)
                if parent_v is None and include_history is False:
                    v_row = session.get(HistoryVisit, note.history_visit_id)
                    if v_row is not None:
                        parent_v = v_row.unique_id
                if parent_v is not None:
                    parent_visit_uri_note = build_visit_uri(parent_v)

            records.append(
                {
                    "kind": "marginalia",
                    "uri": build_marginalia_uri(note.id),
                    "uuid": note.id,
                    "bookmark_uri": parent_bookmark_uri,
                    "history_url_uri": parent_history_url_uri_note,
                    "visit_uri": parent_visit_uri_note,
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
    """Render schema.yaml with declared field docs + live per-kind counts.

    Only kinds that actually appear in *records* contribute documented
    entries so consumers can tell at a glance whether the bundle
    includes history, marginalia, or only bookmarks.
    """
    counts = {"bookmark": 0, "marginalia": 0, "history-url": 0, "visit": 0}
    for rec in records:
        kind = rec.get("kind")
        if kind in counts:
            counts[kind] += 1

    # bookmark + marginalia are always potentially present (they get
    # exported unconditionally); history kinds only appear when the
    # caller opted in. Show docs for (a) the two unconditional kinds
    # and (b) any optional kind that actually has records.
    _ALWAYS_PRESENT = {"bookmark", "marginalia"}
    present_kinds = {
        k: v for k, v in SCHEMA["kinds"].items()
        if k in _ALWAYS_PRESENT or counts.get(k, 0) > 0
    }
    present_counts = {
        k: counts.get(k, 0) for k in counts
        if k in _ALWAYS_PRESENT or counts.get(k, 0) > 0
    }

    doc = {
        "scheme": SCHEMA["scheme"],
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": present_counts,
        "kinds": present_kinds,
    }
    buf = io.StringIO()
    buf.write("# Auto-generated by bookmark-memex. Edit freely.\n")
    yaml.safe_dump(doc, buf, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return buf.getvalue().encode("utf-8")


def _readme_bytes(
    num_bookmarks: int,
    num_marginalia: int,
    num_history_urls: int = 0,
    num_visits: int = 0,
) -> bytes:
    """Render README.md with ECHO frontmatter + usage notes."""
    try:
        from importlib.metadata import version as _pkg_version

        version = _pkg_version("bookmark-memex")
    except Exception:
        version = "unknown"

    today = date.today().isoformat()

    if num_history_urls or num_visits:
        description = (
            f"{num_bookmarks} bookmarks + {num_marginalia} marginalia + "
            f"{num_history_urls} history-urls + {num_visits} visits "
            f"exported from bookmark-memex"
        )
    else:
        description = (
            f"{num_bookmarks} bookmarks + {num_marginalia} marginalia "
            f"exported from bookmark-memex"
        )

    lines = [
        "---",
        "name: bookmark-memex archive",
        f'description: "{description}"',
        f"datetime: {today}",
        f"generator: bookmark-memex {version}",
        "contents:",
        "  - path: records.jsonl",
        "    description: Typed records (arkiv JSONL format)",
        "  - path: schema.yaml",
        "    description: Record schema + per-kind counts",
        "---",
        "",
        "# bookmark-memex Archive",
        "",
    ]

    if num_history_urls or num_visits:
        lines.append(
            f"This archive contains {num_bookmarks} bookmark(s), "
            f"{num_marginalia} note(s) (marginalia), "
            f"{num_history_urls} history URL(s), and {num_visits} visit(s) "
            "exported from bookmark-memex in "
            "[arkiv](https://github.com/alonzo-church/arkiv) format."
        )
    else:
        lines.append(
            f"This archive contains {num_bookmarks} bookmark(s) and "
            f"{num_marginalia} note(s) (marginalia) exported from "
            "bookmark-memex in "
            "[arkiv](https://github.com/alonzo-church/arkiv) format."
        )

    lines.extend([
        "",
        "Each line in `records.jsonl` is one record. Records are typed by `kind`:",
        "",
        "- `bookmark`: a saved URL with title, description, tags, and media metadata.",
        "- `marginalia`: a free-form note attached (by URI) to a bookmark, history-url, or visit.",
    ])

    if num_history_urls or num_visits:
        lines.extend([
            "- `history-url`: aggregate per-URL record from browser history (observational, not curated).",
            "- `visit`: individual visit event (timestamp, transition, referrer).",
            "",
            "History records are deliberately distinct from bookmarks. A",
            "`history-url` is something the user *visited*, not something they",
            "*saved*. When reimporting this bundle you can treat the two",
            "layers independently.",
        ])

    lines.extend([
        "",
        "URIs follow the cross-archive `bookmark-memex://` scheme and stay stable",
        "across re-imports, so marginalia survive their parent record being",
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
    ])
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


def export_arkiv(
    db,
    out_path,
    *,
    include_history: bool = False,
) -> dict:
    """Export active records as an arkiv bundle.

    Bookmarks and marginalia are always exported. History
    (``history-url`` and ``visit`` records) is opt-in via
    *include_history*, because history is both larger and more sensitive
    than curated bookmarks.

    Output format is inferred from *out_path*'s extension:

    - ``path.zip``            single zip file
    - ``path.tar.gz``/`.tgz`  single gzip-compressed tarball
    - any other path          directory containing records.jsonl,
                              schema.yaml, and README.md

    Parameters
    ----------
    db:
        A ``bookmark_memex.db.Database`` instance.
    out_path:
        Destination path. Extension determines bundle format.
    include_history:
        If True, also emit ``history-url`` and ``visit`` records.
        Defaults to False.

    Returns
    -------
    dict
        ``{"path": str, "format": "dir"|"zip"|"tar.gz",
           "counts": {"bookmark": N, "marginalia": N, "annotation": N,
                      "history-url": N, "visit": N}}``

        The ``annotation`` key is a backwards-compat alias for
        ``marginalia``. ``history-url`` and ``visit`` are present only
        when *include_history* is True.
    """
    out_path_str = str(out_path)
    records = _build_records(db, include_history=include_history)
    counts = {"bookmark": 0, "marginalia": 0, "history-url": 0, "visit": 0}
    for rec in records:
        kind = rec.get("kind")
        if kind in counts:
            counts[kind] += 1

    jsonl_bytes = _records_to_jsonl_bytes(records)
    schema_bytes = _schema_yaml_bytes(records)
    readme_bytes = _readme_bytes(
        counts["bookmark"],
        counts["marginalia"],
        counts["history-url"],
        counts["visit"],
    )

    fmt = _detect_compression(out_path_str)
    if fmt == "zip":
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
    # the pre-rename shape. Drop zero-count history keys so the caller
    # sees identical return shape when include_history is False.
    counts_out = {k: v for k, v in counts.items() if k in ("bookmark", "marginalia") or v > 0}
    counts_out["annotation"] = counts["marginalia"]

    return {
        "path": out_path_str,
        "format": fmt,
        "counts": counts_out,
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
