"""Standard export formats for bookmark-memex.

Provides serializers for JSON, CSV, plain text, Markdown, and M3U playlist.
All functions accept an optional ``bookmark_ids`` list: when given, only those
bookmarks are exported; when omitted, all active bookmarks are exported.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional


def _bookmark_to_dict(b) -> dict:
    return {
        "url": b.url,
        "title": b.title,
        "description": b.description or "",
        "tags": b.tag_names,
        "starred": b.starred,
        "pinned": b.pinned,
        "added": b.added.isoformat() if b.added else None,
        "visit_count": b.visit_count,
        "unique_id": b.unique_id,
    }


def _get_bookmarks(db, bookmark_ids: Optional[list[int]]):
    """Return the appropriate bookmark sequence based on whether IDs were given."""
    if bookmark_ids is None:
        return db.list()
    bookmarks = []
    for bid in bookmark_ids:
        bm = db.get(bid)
        if bm is not None:
            bookmarks.append(bm)
    return bookmarks


def export_json(db, path: Path, bookmark_ids: Optional[list[int]] = None) -> None:
    """Write a JSON array of bookmark dicts to *path*."""
    bookmarks = _get_bookmarks(db, bookmark_ids)
    records = [_bookmark_to_dict(b) for b in bookmarks]
    Path(path).write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def export_csv(db, path: Path, bookmark_ids: Optional[list[int]] = None) -> None:
    """Write bookmarks as CSV to *path* with header: url,title,tags,description,starred."""
    bookmarks = _get_bookmarks(db, bookmark_ids)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "tags", "description", "starred"])
        for b in bookmarks:
            writer.writerow([
                b.url,
                b.title,
                ",".join(b.tag_names),
                b.description or "",
                str(b.starred).lower(),
            ])


def export_text(db, path: Path, bookmark_ids: Optional[list[int]] = None) -> None:
    """Write one URL per line to *path*."""
    bookmarks = _get_bookmarks(db, bookmark_ids)
    lines = [b.url for b in bookmarks]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def export_markdown(db, path: Path, bookmark_ids: Optional[list[int]] = None) -> None:
    """Write bookmarks as a Markdown list to *path*.

    Format::

        # Bookmarks

        - [title](url) (tag1, tag2)
    """
    bookmarks = _get_bookmarks(db, bookmark_ids)
    lines = ["# Bookmarks", ""]
    for b in bookmarks:
        tag_str = ", ".join(b.tag_names)
        tag_part = f" ({tag_str})" if tag_str else ""
        lines.append(f"- [{b.title}]({b.url}){tag_part}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_m3u(db, path: Path, bookmark_ids: Optional[list[int]] = None) -> None:
    """Write bookmarks as an M3U playlist to *path*.

    Format::

        #EXTM3U
        #EXTINF:-1,title
        url
    """
    bookmarks = _get_bookmarks(db, bookmark_ids)
    lines = ["#EXTM3U"]
    for b in bookmarks:
        lines.append(f"#EXTINF:-1,{b.title}")
        lines.append(b.url)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
