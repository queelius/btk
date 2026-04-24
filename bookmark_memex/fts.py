"""Full-text search (FTS5) index for bookmark-memex.

Manages three independent FTS5 virtual tables:
  - bookmarks_fts : url, title, description, tags
  - content_fts   : extracted_text from content_cache
  - marginalia_fts: marginalia text (notes attached to bookmarks)

All operations use raw sqlite3 connections (not SQLAlchemy) so that FTS5
virtual-table DDL and the snippet()/bm25() auxiliary functions are accessible
without ORM overhead.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# SearchResult
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single ranked search hit."""

    bookmark_id: int
    url: str
    title: str
    description: str
    rank: float
    snippet: Optional[str] = None


# ---------------------------------------------------------------------------
# Table definitions (name → DDL)
# ---------------------------------------------------------------------------

_FTS_TABLES: Dict[str, str] = {
    "bookmarks_fts": """
        CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks_fts USING fts5(
            bookmark_id UNINDEXED,
            url,
            title,
            description,
            tags,
            tokenize='porter unicode61'
        )
    """,
    "content_fts": """
        CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
            bookmark_id UNINDEXED,
            extracted_text,
            tokenize='porter unicode61'
        )
    """,
    "marginalia_fts": """
        CREATE VIRTUAL TABLE IF NOT EXISTS marginalia_fts USING fts5(
            marginalia_id UNINDEXED,
            text,
            tokenize='porter unicode61'
        )
    """,
}


# ---------------------------------------------------------------------------
# FTSIndex
# ---------------------------------------------------------------------------


class FTSIndex:
    """Manages FTS5 virtual tables for bookmark-memex."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def create_indexes(self) -> None:
        """Create all three FTS5 virtual tables if they do not yet exist."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            for ddl in _FTS_TABLES.values():
                cur.execute(ddl)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Rebuild helpers
    # ------------------------------------------------------------------

    def rebuild_bookmarks_index(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Repopulate bookmarks_fts from bookmarks + tags.

        Only active (non-archived) bookmarks are indexed.

        Returns:
            Number of rows inserted.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookmarks_fts")

            cur.execute(
                """
                SELECT b.id, b.url, b.title, COALESCE(b.description, ''),
                       COALESCE(GROUP_CONCAT(t.name, ' '), '')
                FROM bookmarks b
                LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
                LEFT JOIN tags t ON bt.tag_id = t.id
                WHERE b.archived_at IS NULL
                GROUP BY b.id
                """
            )
            rows = cur.fetchall()
            total = len(rows)

            for idx, (bid, url, title, desc, tags) in enumerate(rows, start=1):
                cur.execute(
                    "INSERT INTO bookmarks_fts(bookmark_id, url, title, description, tags)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (bid, url or "", title or "", desc or "", tags or ""),
                )
                if progress_callback is not None:
                    progress_callback(idx, total)

            conn.commit()
            return total
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rebuild_content_index(self) -> int:
        """Repopulate content_fts from content_cache rows with extracted_text.

        Only rows where both the content_cache and its parent bookmark are
        active (archived_at IS NULL) and extracted_text is non-empty are
        included.

        Returns:
            Number of rows inserted.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM content_fts")

            cur.execute(
                """
                SELECT cc.bookmark_id, cc.extracted_text
                FROM content_cache cc
                JOIN bookmarks b ON b.id = cc.bookmark_id
                WHERE cc.archived_at IS NULL
                  AND b.archived_at IS NULL
                  AND cc.extracted_text IS NOT NULL
                  AND cc.extracted_text != ''
                """
            )
            rows = cur.fetchall()

            for bid, text in rows:
                cur.execute(
                    "INSERT INTO content_fts(bookmark_id, extracted_text) VALUES (?, ?)",
                    (bid, text),
                )

            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rebuild_marginalia_index(self) -> int:
        """Repopulate marginalia_fts from active marginalia.

        Returns:
            Number of rows inserted.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM marginalia_fts")

            cur.execute(
                """
                SELECT id, text
                FROM marginalia
                WHERE archived_at IS NULL
                """
            )
            rows = cur.fetchall()

            for note_id, text in rows:
                cur.execute(
                    "INSERT INTO marginalia_fts(marginalia_id, text) VALUES (?, ?)",
                    (note_id, text or ""),
                )

            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Deprecated alias kept for backward compatibility.
    rebuild_annotations_index = rebuild_marginalia_index

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 50) -> List[SearchResult]:
        """Full-text search over bookmarks_fts, BM25-ranked.

        Args:
            query: Raw query string. Phrase queries and FTS5 operators are
                   passed through unchanged; plain words get a ``*`` suffix
                   for prefix matching.
            limit: Maximum number of results.

        Returns:
            List of :class:`SearchResult`, ordered by descending relevance.
            Empty list for an empty query or no matches.
        """
        if not query or not query.strip():
            return []

        prepared = self._prepare_query(query)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT bookmark_id, url, title, description,
                       bm25(bookmarks_fts) AS rank,
                       snippet(bookmarks_fts, 2, '<mark>', '</mark>', '...', 32)
                FROM bookmarks_fts
                WHERE bookmarks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (prepared, limit),
            )
            results = [
                SearchResult(
                    bookmark_id=row[0],
                    url=row[1],
                    title=row[2],
                    description=row[3],
                    rank=abs(row[4]),  # BM25 returns negative scores
                    snippet=row[5],
                )
                for row in cur.fetchall()
            ]
            return results
        except sqlite3.OperationalError as exc:
            err = str(exc).lower()
            if "fts5" in err or "syntax" in err or "no such table" in err:
                return self._fallback_search(query, limit, conn)
            raise
        finally:
            conn.close()

    def _prepare_query(self, query: str) -> str:
        """Normalise a user query for FTS5.

        - Phrase queries (wrapped in ``"…"``) are left intact.
        - Queries containing FTS5 operators (AND, OR, NOT, NEAR, ``*``)
          are left intact.
        - Otherwise each whitespace-separated word gets a ``*`` suffix for
          prefix matching.
        """
        stripped = query.strip()

        # Phrase query.
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
            return stripped

        # Already contains FTS5 operators.
        upper = stripped.upper()
        for op in ("AND", "OR", "NOT", "NEAR", "*"):
            if op in upper:
                return stripped

        # Plain words — add prefix wildcard.
        words = stripped.split()
        return " ".join(f"{w}*" for w in words)

    def _fallback_search(
        self, query: str, limit: int, conn: sqlite3.Connection
    ) -> List[SearchResult]:
        """LIKE-based fallback when the FTS query is syntactically invalid."""
        pattern = f"%{query}%"
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, url, title, COALESCE(description, '')
            FROM bookmarks
            WHERE (title LIKE ? OR url LIKE ? OR description LIKE ?)
              AND archived_at IS NULL
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        )
        return [
            SearchResult(
                bookmark_id=row[0],
                url=row[1],
                title=row[2],
                description=row[3],
                rank=0.0,
                snippet=None,
            )
            for row in cur.fetchall()
        ]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Dict]:
        """Return existence and document count for each FTS5 table.

        Returns a dict keyed by table name with sub-dicts::

            {
                "bookmarks_fts":  {"exists": True,  "documents": 42},
                "content_fts":    {"exists": False, "documents": 0},
                "marginalia_fts": {"exists": True, "documents": 7},
            }
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            stats: Dict[str, Dict] = {}
            for table in _FTS_TABLES:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                if cur.fetchone() is None:
                    stats[table] = {"exists": False, "documents": 0}
                else:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                    count = cur.fetchone()[0]
                    stats[table] = {"exists": True, "documents": count}
            return stats
        finally:
            conn.close()
