"""File-based importers for bookmark-memex.

Supports Netscape HTML, JSON, CSV, Markdown, and plain-text URL lists.
Each importer returns the count of bookmarks successfully added (new or
merged), and records the import source on every bookmark it touches.
"""
from __future__ import annotations

import csv
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from bookmark_memex.db import Database
from bookmark_memex.detectors import run_detectors


# ---------------------------------------------------------------------------
# Format dispatch
# ---------------------------------------------------------------------------

_EXT_MAP: dict[str, str] = {
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".csv": "csv",
    ".md": "markdown",
    ".txt": "text",
}

_IMPORTERS = {
    "html": lambda db, path: import_html(db, path),
    "json": lambda db, path: import_json(db, path),
    "csv": lambda db, path: import_csv(db, path),
    "markdown": lambda db, path: import_markdown(db, path),
    "text": lambda db, path: import_text(db, path),
}


def import_file(
    db: Database,
    path: Path,
    format: Optional[str] = None,
) -> int:
    """Import bookmarks from *path*.

    Auto-detects format from the file extension when *format* is ``None``.
    Returns the count of bookmarks imported.

    Raises ``ValueError`` for unknown format strings.
    """
    if format is None:
        format = _EXT_MAP.get(Path(path).suffix.lower(), "html")

    importer = _IMPORTERS.get(format)
    if importer is None:
        raise ValueError(f"Unknown format: {format!r}")

    return importer(db, path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_detectors(db: Database, bm_id: int, url: str) -> None:
    """Run detectors for *url* and store any result in bm.media."""
    result = run_detectors(url)
    if result is not None:
        db.update(bm_id, media=result)


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


# ---------------------------------------------------------------------------
# HTML importer (Netscape Bookmark format)
# ---------------------------------------------------------------------------


class _NetscapeParser(HTMLParser):
    """Parses Netscape-format HTML bookmark files.

    Extracts (url, title, tags, folder_path) for each <A> link.
    Folder names are gathered from the H3 elements in the DL/DT hierarchy.
    """

    def __init__(self) -> None:
        super().__init__()
        self.bookmarks: list[dict] = []
        self._folder_stack: list[str] = []
        self._in_h3 = False
        self._h3_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag.lower() == "h3":
            self._in_h3 = True
            self._h3_buf = []

        elif tag.lower() == "dl":
            # Push a placeholder; the real folder name is set when we see the
            # following H3 (already buffered before the DL opens).
            # We push an empty string here; handle_data fills it.
            self._folder_stack.append("")

        elif tag.lower() == "a":
            href = attr_dict.get("href", "")
            title = ""  # filled in handle_data
            raw_tags = attr_dict.get("tags", "")
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []
            folder_path = "/".join(f for f in self._folder_stack if f) or None

            self.bookmarks.append(
                {
                    "url": href,
                    "title": title,
                    "tags": tags,
                    "folder_path": folder_path,
                    "_awaiting_title": True,
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "h3":
            self._in_h3 = False
            name = "".join(self._h3_buf).strip()
            # Update the top of the folder stack with the real name.
            if self._folder_stack:
                self._folder_stack[-1] = name
            self._h3_buf = []

        elif tag.lower() == "dl":
            if self._folder_stack:
                self._folder_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_h3:
            self._h3_buf.append(data)
            return

        # Fill in title for the most-recently opened <A>.
        if self.bookmarks and self.bookmarks[-1].get("_awaiting_title"):
            entry = self.bookmarks[-1]
            entry["title"] = data.strip()
            del entry["_awaiting_title"]


def import_html(db: Database, path: Path) -> int:
    """Import bookmarks from a Netscape HTML bookmark file.

    Extracts ``<DT><A href>`` links, parses the ``TAGS`` attribute, and
    derives a folder tag from the surrounding H3/DL hierarchy.
    Only HTTP(S) URLs are imported.  Returns the count imported.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8", errors="replace")

    parser = _NetscapeParser()
    parser.feed(content)

    count = 0
    for entry in parser.bookmarks:
        url = entry["url"]
        if not _is_http(url):
            continue

        tags = list(entry["tags"])
        folder_path = entry.get("folder_path")

        # Turn folder path into a tag (using the leaf folder name, lowercased).
        if folder_path:
            folder_tag = folder_path.replace(" ", "-").lower()
            if folder_tag not in tags:
                tags.append(folder_tag)

        bm = db.add(
            url,
            title=entry["title"] or "",
            tags=tags or None,
            source_type="html_file",
            source_name=path.name,
            folder_path=folder_path,
        )
        _apply_detectors(db, bm.id, url)
        count += 1

    return count


# ---------------------------------------------------------------------------
# JSON importer
# ---------------------------------------------------------------------------


def import_json(db: Database, path: Path) -> int:
    """Import bookmarks from a JSON file.

    Accepts a JSON array of objects with fields:
    ``url``, ``title``, ``tags`` (list or comma-string),
    ``description``, ``starred``.

    Returns the count of bookmarks imported.
    """
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    count = 0
    for item in raw:
        if not isinstance(item, dict):
            continue

        url = item.get("url", "")
        if not url or not _is_http(url):
            continue

        raw_tags = item.get("tags", [])
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in raw_tags if t]

        bm = db.add(
            url,
            title=item.get("title") or "",
            description=item.get("description") or None,
            tags=tags or None,
            starred=bool(item.get("starred", False)),
            source_type="json_file",
            source_name=Path(path).name,
        )
        _apply_detectors(db, bm.id, url)
        count += 1

    return count


# ---------------------------------------------------------------------------
# CSV importer
# ---------------------------------------------------------------------------


def import_csv(db: Database, path: Path) -> int:
    """Import bookmarks from a CSV file.

    Expected columns (case-insensitive): ``url``, ``title``, ``tags``,
    ``description``.  Tags are comma-separated within their cell.
    Returns the count of bookmarks imported.
    """
    path = Path(path)
    count = 0

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Normalise column names to lowercase.
            row_lower = {k.lower(): v for k, v in row.items()}

            url = row_lower.get("url", "").strip()
            if not url or not _is_http(url):
                continue

            raw_tags = row_lower.get("tags", "")
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

            bm = db.add(
                url,
                title=row_lower.get("title", "").strip() or "",
                description=row_lower.get("description", "").strip() or None,
                tags=tags or None,
                source_type="csv_file",
                source_name=path.name,
            )
            _apply_detectors(db, bm.id, url)
            count += 1

    return count


# ---------------------------------------------------------------------------
# Markdown importer
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")


def import_markdown(db: Database, path: Path) -> int:
    """Import bookmarks from a Markdown file.

    Extracts ``[text](https://url)`` patterns.  The link text becomes the
    bookmark title.  Only HTTP(S) URLs are imported.
    Returns the count of bookmarks imported.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8", errors="replace")

    seen: set[str] = set()
    count = 0

    for match in _MD_LINK_RE.finditer(content):
        title = match.group(1).strip()
        url = match.group(2).strip()

        if url in seen:
            continue
        seen.add(url)

        bm = db.add(
            url,
            title=title or "",
            source_type="markdown_file",
            source_name=path.name,
        )
        _apply_detectors(db, bm.id, url)
        count += 1

    return count


# ---------------------------------------------------------------------------
# Text importer
# ---------------------------------------------------------------------------


def import_text(db: Database, path: Path) -> int:
    """Import bookmarks from a plain-text file (one URL per line).

    Lines starting with ``#`` and blank lines are skipped.
    Only HTTP(S) URLs are imported.  Returns the count of bookmarks imported.
    """
    path = Path(path)
    count = 0

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not _is_http(line):
            continue

        bm = db.add(
            line,
            title=line,
            source_type="text_file",
            source_name=path.name,
        )
        _apply_detectors(db, bm.id, line)
        count += 1

    return count
