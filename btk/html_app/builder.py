"""
Export database builder for sql.js HTML-app export.

Creates an in-memory SQLite database with the btk export schema,
inserts bookmark data from ORM objects, and serializes to bytes.
Supports multi-database merging with ID remapping.
"""
import base64
import json
import sqlite3
from typing import Dict, List, Optional

from btk.models import Bookmark

_EXPORT_SCHEMA = """\
CREATE TABLE bookmarks (
    id INTEGER PRIMARY KEY,
    unique_id VARCHAR(8),
    url VARCHAR(2048),
    title VARCHAR(512),
    description TEXT,
    bookmark_type VARCHAR(16) NOT NULL DEFAULT 'bookmark',
    added DATETIME,
    stars INTEGER DEFAULT 0,
    pinned INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0,
    reachable INTEGER,
    visit_count INTEGER DEFAULT 0,
    last_visited DATETIME,
    favicon_data BLOB,
    favicon_mime_type VARCHAR(64),
    extra_data JSON,
    source_db VARCHAR(64) NOT NULL DEFAULT 'default'
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name VARCHAR(256),
    description TEXT,
    color VARCHAR(7)
);

CREATE TABLE bookmark_tags (
    bookmark_id INTEGER REFERENCES bookmarks(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (bookmark_id, tag_id)
);

CREATE TABLE bookmark_media (
    id INTEGER PRIMARY KEY,
    bookmark_id INTEGER REFERENCES bookmarks(id) UNIQUE,
    media_type VARCHAR(32),
    media_source VARCHAR(64),
    media_id VARCHAR(128),
    author_name VARCHAR(256),
    author_url VARCHAR(2048),
    thumbnail_url VARCHAR(2048),
    published_at DATETIME
);
"""


def _insert_bookmarks(
    conn: sqlite3.Connection,
    bookmarks: List[Bookmark],
    source_db: str = "default",
    tag_name_to_id: Optional[Dict[str, int]] = None,
) -> Dict[int, int]:
    """Insert bookmarks into the export database, returning old_id -> new_id map.

    Args:
        conn: SQLite connection to the export database.
        bookmarks: ORM Bookmark objects to insert.
        source_db: Value for the source_db discriminator column.
        tag_name_to_id: Shared tag name -> export ID mapping (mutated in place).

    Returns:
        Dict mapping original bookmark IDs to new export IDs.
    """
    if tag_name_to_id is None:
        tag_name_to_id = {}

    id_map: Dict[int, int] = {}

    for b in bookmarks:
        extra_json = json.dumps(b.extra_data) if b.extra_data else None
        added_str = b.added.isoformat() if b.added else None
        last_visited_str = b.last_visited.isoformat() if b.last_visited else None

        cursor = conn.execute(
            "INSERT INTO bookmarks "
            "(unique_id, url, title, description, bookmark_type, added, "
            "stars, pinned, archived, reachable, visit_count, last_visited, "
            "favicon_data, favicon_mime_type, extra_data, source_db) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                b.unique_id, b.url, b.title, b.description,
                b.bookmark_type or "bookmark", added_str,
                int(b.stars or 0), int(b.pinned or 0), int(b.archived or 0),
                1 if b.reachable is True else (0 if b.reachable is False else None),
                b.visit_count or 0, last_visited_str,
                b.favicon_data, b.favicon_mime_type,
                extra_json, source_db,
            ),
        )
        new_id = cursor.lastrowid
        id_map[b.id] = new_id

        # Insert tags, deduplicating by name
        for tag in b.tags:
            if tag.name not in tag_name_to_id:
                cursor = conn.execute(
                    "INSERT INTO tags (name, description, color) VALUES (?, ?, ?)",
                    (tag.name, tag.description, tag.color),
                )
                tag_name_to_id[tag.name] = cursor.lastrowid
            tag_id = tag_name_to_id[tag.name]
            conn.execute(
                "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag_id) VALUES (?, ?)",
                (new_id, tag_id),
            )

        # Insert media if present
        media = b.media
        if media:
            published_str = media.published_at.isoformat() if media.published_at else None
            conn.execute(
                "INSERT INTO bookmark_media "
                "(bookmark_id, media_type, media_source, media_id, "
                "author_name, author_url, thumbnail_url, published_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id, media.media_type, media.media_source,
                    media.media_id, media.author_name, media.author_url,
                    media.thumbnail_url, published_str,
                ),
            )

    return id_map


def build_export_db(
    bookmarks: List[Bookmark],
    include_dbs: Optional[Dict[str, List[Bookmark]]] = None,
) -> bytes:
    """Build an in-memory SQLite export database and return its serialized bytes.

    Args:
        bookmarks: Main database bookmarks (source_db='default').
        include_dbs: Optional dict mapping database names to bookmark lists
                     for multi-database export.

    Returns:
        Raw bytes of the serialized SQLite database.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(_EXPORT_SCHEMA)

    tag_name_to_id: Dict[str, int] = {}

    # Insert main database bookmarks
    _insert_bookmarks(conn, bookmarks, source_db="default", tag_name_to_id=tag_name_to_id)

    # Insert included databases
    if include_dbs:
        for db_name, db_bookmarks in include_dbs.items():
            _insert_bookmarks(conn, db_bookmarks, source_db=db_name, tag_name_to_id=tag_name_to_id)

    conn.commit()

    # conn.serialize() requires Python 3.11+. For compatibility with
    # Python 3.8+, write to a temporary file and read back the bytes.
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        backup = sqlite3.connect(tmp_path)
        conn.backup(backup)
        backup.close()
        conn.close()
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def encode_export_db(db_bytes: bytes) -> str:
    """Base64-encode serialized database bytes for embedding in HTML.

    Args:
        db_bytes: Raw SQLite database bytes from build_export_db().

    Returns:
        Base64-encoded string.
    """
    return base64.b64encode(db_bytes).decode("ascii")
