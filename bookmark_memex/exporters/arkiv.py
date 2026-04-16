"""Arkiv JSONL + schema.yaml exporter for bookmark-memex.

Produces two files inside *out_path*:
- ``records.jsonl``: one JSON line per active bookmark/annotation.
- ``schema.yaml``: YAML document describing the exported data schema.

Record URI scheme follows the cross-archive contract:
    bookmark-memex://bookmark/<unique_id>
    bookmark-memex://annotation/<uuid>
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import select

from bookmark_memex.models import Annotation, Bookmark
from bookmark_memex.uri import build_annotation_uri, build_bookmark_uri


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
        "annotation": {
            "description": "A note attached to a bookmark (marginalia).",
            "uri": "bookmark-memex://annotation/<uuid>",
            "fields": {
                "kind": "Always 'annotation'.",
                "uri": "Canonical bookmark-memex URI for this annotation.",
                "uuid": "UUID hex string — durable annotation identifier.",
                "bookmark_uri": (
                    "URI of the parent bookmark, or null if the parent was deleted."
                ),
                "text": "Free-form annotation text.",
                "created_at": "ISO-8601 UTC datetime when the annotation was created.",
                "updated_at": "ISO-8601 UTC datetime when the annotation was last updated.",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------


def export_arkiv(db, out_path: Path) -> dict:
    """Export active bookmarks and annotations as arkiv JSONL + schema.yaml.

    Parameters
    ----------
    db:
        A ``bookmark_memex.db.Database`` instance.
    out_path:
        Directory to create (or reuse).  Will contain ``records.jsonl`` and
        ``schema.yaml``.

    Returns
    -------
    dict
        ``{"records_path": str, "schema_path": str, "counts": {"bookmark": N, "annotation": N}}``
    """
    out_path = Path(out_path)
    out_path.mkdir(parents=True, exist_ok=True)

    records_path = out_path / "records.jsonl"
    schema_path = out_path / "schema.yaml"

    bm_count = 0
    ann_count = 0

    with db._session() as session:
        # -----------------------------------------------------------------
        # Build a mapping from bookmark_id → unique_id for annotation lookups.
        # We use this to construct bookmark URIs for annotations without an
        # extra per-annotation round-trip.
        # -----------------------------------------------------------------
        bm_query = (
            select(Bookmark)
            .where(Bookmark.archived_at.is_(None))
            .order_by(Bookmark.id)
        )
        bookmarks = list(session.execute(bm_query).scalars())

        id_to_unique: dict[int, str] = {bm.id: bm.unique_id for bm in bookmarks}

        with open(records_path, "w", encoding="utf-8") as fh:
            # --- Bookmarks ---
            for bm in bookmarks:
                # Ensure tags are loaded while session is still open.
                tag_names = [t.name for t in bm.tags]
                record = {
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
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                bm_count += 1

            # --- Annotations ---
            ann_query = (
                select(Annotation)
                .where(Annotation.archived_at.is_(None))
                .order_by(Annotation.created_at)
            )
            annotations = list(session.execute(ann_query).scalars())

            for ann in annotations:
                parent_uri: str | None = None
                if ann.bookmark_id is not None:
                    parent_unique = id_to_unique.get(ann.bookmark_id)
                    if parent_unique is not None:
                        parent_uri = build_bookmark_uri(parent_unique)

                record = {
                    "kind": "annotation",
                    "uri": build_annotation_uri(ann.id),
                    "uuid": ann.id,
                    "bookmark_uri": parent_uri,
                    "text": ann.text,
                    "created_at": ann.created_at.isoformat() if ann.created_at else None,
                    "updated_at": ann.updated_at.isoformat() if ann.updated_at else None,
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                ann_count += 1

    # --- schema.yaml ---
    schema_doc = {
        "scheme": SCHEMA["scheme"],
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "kinds": SCHEMA["kinds"],
    }
    schema_path.write_text(yaml.safe_dump(schema_doc, allow_unicode=True), encoding="utf-8")

    return {
        "records_path": str(records_path),
        "schema_path": str(schema_path),
        "counts": {"bookmark": bm_count, "annotation": ann_count},
    }
