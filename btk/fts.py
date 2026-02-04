"""
Full-Text Search Module for BTK.

Provides SQLite FTS5 based full-text search capabilities for bookmarks.
FTS5 enables fast, ranked search with support for:
- Prefix matching (word*)
- Phrase matching ("exact phrase")
- Boolean operators (AND, OR, NOT)
- Search result ranking by relevance
"""
import sqlite3
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class SearchResult:
    """Represents a search result with relevance scoring."""
    bookmark_id: int
    url: str
    title: str
    description: str
    rank: float
    snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'bookmark_id': self.bookmark_id,
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'rank': self.rank,
            'snippet': self.snippet
        }


class FTSIndex:
    """Full-Text Search index manager using SQLite FTS5."""

    FTS_TABLE = 'bookmarks_fts'

    def __init__(self, db_path: str):
        """Initialize FTS index.

        Args:
            db_path: Path to the SQLite database
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def create_index(self) -> bool:
        """Create the FTS5 virtual table if it doesn't exist.

        Returns:
            True if created or already exists
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name=?
            """, (self.FTS_TABLE,))

            if cursor.fetchone() is None:
                # Create FTS5 virtual table
                cursor.execute(f"""
                    CREATE VIRTUAL TABLE {self.FTS_TABLE} USING fts5(
                        bookmark_id UNINDEXED,
                        url,
                        title,
                        description,
                        tags,
                        content,
                        tokenize='porter unicode61'
                    )
                """)
                conn.commit()
                return True
            return True
        except Exception as e:
            print(f"Error creating FTS index: {e}")
            return False
        finally:
            conn.close()

    def drop_index(self) -> bool:
        """Drop the FTS index table.

        Returns:
            True if dropped successfully
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {self.FTS_TABLE}")
            conn.commit()
            return True
        except Exception as e:
            print(f"Error dropping FTS index: {e}")
            return False
        finally:
            conn.close()

    def rebuild_index(self, progress_callback=None) -> int:
        """Rebuild the FTS index from scratch.

        Args:
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Number of documents indexed
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Drop and recreate
            cursor.execute(f"DROP TABLE IF EXISTS {self.FTS_TABLE}")
            cursor.execute(f"""
                CREATE VIRTUAL TABLE {self.FTS_TABLE} USING fts5(
                    bookmark_id UNINDEXED,
                    url,
                    title,
                    description,
                    tags,
                    content,
                    tokenize='porter unicode61'
                )
            """)

            # Get all bookmarks
            cursor.execute("""
                SELECT b.id, b.url, b.title, b.description,
                       GROUP_CONCAT(t.name, ' ') as tags
                FROM bookmarks b
                LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
                LEFT JOIN tags t ON bt.tag_id = t.id
                GROUP BY b.id
            """)
            bookmarks = cursor.fetchall()

            total = len(bookmarks)
            indexed = 0

            for idx, (bid, url, title, desc, tags) in enumerate(bookmarks):
                # Get content if available
                cursor.execute("""
                    SELECT markdown_content FROM content_cache
                    WHERE bookmark_id = ?
                """, (bid,))
                content_row = cursor.fetchone()
                content = content_row[0] if content_row and content_row[0] else ''

                # Insert into FTS
                cursor.execute(f"""
                    INSERT INTO {self.FTS_TABLE}
                    (bookmark_id, url, title, description, tags, content)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (bid, url or '', title or '', desc or '', tags or '', content))

                indexed += 1
                if progress_callback:
                    progress_callback(indexed, total)

            conn.commit()
            return indexed

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def index_bookmark(self, bookmark_id: int) -> bool:
        """Add or update a single bookmark in the index.

        Args:
            bookmark_id: ID of the bookmark to index

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Remove existing entry
            cursor.execute(f"""
                DELETE FROM {self.FTS_TABLE} WHERE bookmark_id = ?
            """, (bookmark_id,))

            # Get bookmark data
            cursor.execute("""
                SELECT b.id, b.url, b.title, b.description,
                       GROUP_CONCAT(t.name, ' ') as tags
                FROM bookmarks b
                LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
                LEFT JOIN tags t ON bt.tag_id = t.id
                WHERE b.id = ?
                GROUP BY b.id
            """, (bookmark_id,))

            row = cursor.fetchone()
            if not row:
                return False

            bid, url, title, desc, tags = row

            # Get content
            cursor.execute("""
                SELECT markdown_content FROM content_cache
                WHERE bookmark_id = ?
            """, (bookmark_id,))
            content_row = cursor.fetchone()
            content = content_row[0] if content_row and content_row[0] else ''

            # Insert into FTS
            cursor.execute(f"""
                INSERT INTO {self.FTS_TABLE}
                (bookmark_id, url, title, description, tags, content)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (bid, url or '', title or '', desc or '', tags or '', content))

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            print(f"Error indexing bookmark {bookmark_id}: {e}")
            return False
        finally:
            conn.close()

    def remove_bookmark(self, bookmark_id: int) -> bool:
        """Remove a bookmark from the index.

        Args:
            bookmark_id: ID of the bookmark to remove

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                DELETE FROM {self.FTS_TABLE} WHERE bookmark_id = ?
            """, (bookmark_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error removing bookmark {bookmark_id} from index: {e}")
            return False
        finally:
            conn.close()

    def search(self, query: str, limit: int = 50,
               in_content: bool = True) -> List[SearchResult]:
        """Search the index.

        Args:
            query: Search query (supports FTS5 syntax)
            limit: Maximum number of results
            in_content: If True, also search in content field

        Returns:
            List of SearchResult objects sorted by relevance
        """
        if not query or not query.strip():
            return []

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Check if FTS table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name=?
            """, (self.FTS_TABLE,))
            if cursor.fetchone() is None:
                return []

            # Clean query for FTS5
            clean_query = self._prepare_query(query)

            # Build match expression
            if in_content:
                match_cols = f"{self.FTS_TABLE}"  # Search all columns
            else:
                match_cols = "{url title description tags}"

            # Search with BM25 ranking
            cursor.execute(f"""
                SELECT bookmark_id, url, title, description,
                       bm25({self.FTS_TABLE}) as rank,
                       snippet({self.FTS_TABLE}, 5, '<mark>', '</mark>', '...', 32) as snippet
                FROM {self.FTS_TABLE}
                WHERE {self.FTS_TABLE} MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (clean_query, limit))

            results = []
            for row in cursor.fetchall():
                results.append(SearchResult(
                    bookmark_id=row[0],
                    url=row[1],
                    title=row[2],
                    description=row[3],
                    rank=abs(row[4]),  # BM25 returns negative scores
                    snippet=row[5]
                ))

            return results

        except sqlite3.OperationalError as e:
            # Handle invalid FTS queries gracefully
            if "syntax error" in str(e).lower() or "fts5" in str(e).lower():
                # Fall back to simple contains search
                return self._fallback_search(query, limit, in_content)
            raise
        finally:
            conn.close()

    def _prepare_query(self, query: str) -> str:
        """Prepare query for FTS5.

        Handles common query patterns and escapes special characters.
        """
        # If it looks like a phrase query, keep it
        if query.startswith('"') and query.endswith('"'):
            return query

        # If it contains FTS5 operators, use as-is
        fts_operators = ['AND', 'OR', 'NOT', 'NEAR', '*']
        if any(op in query.upper() for op in fts_operators):
            return query

        # For simple queries, add prefix matching for better results
        words = query.split()
        if len(words) == 1:
            # Single word: add prefix matching
            return f"{query}*"
        else:
            # Multiple words: treat as implicit AND
            return ' '.join(f"{word}*" for word in words)

    def _fallback_search(self, query: str, limit: int,
                         in_content: bool) -> List[SearchResult]:
        """Fallback search using LIKE when FTS query fails."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            pattern = f"%{query}%"

            cursor.execute("""
                SELECT DISTINCT b.id, b.url, b.title, b.description
                FROM bookmarks b
                WHERE b.title LIKE ? OR b.url LIKE ? OR b.description LIKE ?
                LIMIT ?
            """, (pattern, pattern, pattern, limit))

            results = []
            for row in cursor.fetchall():
                results.append(SearchResult(
                    bookmark_id=row[0],
                    url=row[1],
                    title=row[2],
                    description=row[3],
                    rank=0.0,
                    snippet=None
                ))

            return results
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get FTS index statistics.

        Returns:
            Dictionary with index stats
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name=?
            """, (self.FTS_TABLE,))
            if cursor.fetchone() is None:
                return {'exists': False, 'documents': 0}

            # Count documents
            cursor.execute(f"SELECT COUNT(*) FROM {self.FTS_TABLE}")
            count = cursor.fetchone()[0]

            return {
                'exists': True,
                'documents': count,
                'table_name': self.FTS_TABLE
            }
        except Exception as e:
            return {'exists': False, 'error': str(e)}
        finally:
            conn.close()


def get_fts_index(db_path: str) -> FTSIndex:
    """Get an FTS index instance for the given database.

    Args:
        db_path: Path to the SQLite database

    Returns:
        FTSIndex instance
    """
    return FTSIndex(db_path)
