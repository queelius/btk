"""
Simplified database interface for BTK.

Provides a clean, minimal API for database operations using SQLAlchemy.
Works with single database files instead of library directories.
"""
import logging
from pathlib import Path
from typing import Optional, List, Generator, Any, Dict
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, select, func, or_, and_, text,
    event
)
from sqlalchemy.orm import Session, sessionmaker, selectinload
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import IntegrityError

from btk.models import Base, Bookmark, Tag, Event
from btk.config import get_config

logger = logging.getLogger(__name__)

# Global lock for tag creation to prevent race conditions
import threading
_tag_creation_lock = threading.Lock()


class Database:
    """
    Minimal database interface for BTK.

    Provides a clean API for bookmark operations without the complexity
    of library directories. Works directly with database files.
    """

    def __init__(self, path: Optional[str] = None, url: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            path: Database file path (for SQLite). Uses config default if not provided.
            url: Full database URL (overrides path). Supports PostgreSQL, MySQL, etc.

        Examples:
            Database()  # Uses config default
            Database(path="bookmarks.db")  # SQLite file
            Database(url="postgresql://user:pass@localhost/bookmarks")  # PostgreSQL
        """
        config = get_config()

        # Determine database URL
        if url:
            # Full URL provided - use directly
            self.url = url
            self.path = None
        elif path:
            # Path provided - construct SQLite URL
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.url = f"sqlite:///{self.path}"
        else:
            # Use config default
            self.url = config.get_database_url()
            if config.is_sqlite():
                self.path = config.get_database_path()
                self.path.parent.mkdir(parents=True, exist_ok=True)
            else:
                self.path = None

        # Create engine with appropriate settings
        if self.url.startswith("sqlite:"):
            self.engine = create_engine(
                self.url,
                connect_args={"check_same_thread": False},
                poolclass=NullPool,  # NullPool for thread-safe SQLite access
                echo=config.database_echo
            )
            # Configure SQLite for performance
            event.listen(self.engine, "connect", self._configure_sqlite)
        else:
            # PostgreSQL, MySQL, etc.
            self.engine = create_engine(
                self.url,
                pool_pre_ping=True,
                pool_size=config.connection_pool_size,
                pool_recycle=3600,
                connect_args={"connect_timeout": config.connection_timeout},
                echo=config.database_echo
            )

        # Create session factory
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

        # Initialize schema
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _configure_sqlite(dbapi_conn, connection_record):
        """Configure SQLite for optimal performance."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA cache_size = -64000")  # 64MB cache
        cursor.execute("PRAGMA temp_store = MEMORY")
        cursor.close()

    @contextmanager
    def session(self, expire_on_commit: bool = True) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.

        Args:
            expire_on_commit: If False, objects won't expire after commit (useful for detached access)

        Yields:
            SQLAlchemy session with automatic commit/rollback
        """
        session = self.Session()
        session.expire_on_commit = expire_on_commit
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def emit_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        entity_url: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit an event for the audit trail.

        Args:
            event_type: Type of event (bookmark_added, tag_removed, etc.)
            entity_type: Entity type (bookmark, tag, collection)
            entity_id: ID of the entity (nullable for deletions)
            entity_url: URL for bookmarks (preserved even after deletion)
            event_data: Additional event-specific data
        """
        with self.session() as session:
            event = Event(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_url=entity_url,
                event_data=event_data
            )
            session.add(event)

    def add(self, url: str, title: Optional[str] = None, skip_duplicates: bool = True, **kwargs) -> Optional[Bookmark]:
        """
        Add a bookmark to the database.

        Args:
            url: The URL to bookmark
            title: Optional title (fetched if not provided)
            skip_duplicates: If True, skip duplicate URLs; if False, raise error
            **kwargs: Additional bookmark fields (tags, description, stars, etc.)

        Returns:
            Created bookmark instance or None if duplicate was skipped
        """
        with self.session(expire_on_commit=False) as session:
            # Generate unique ID
            from hashlib import sha256
            unique_id = sha256(url.encode()).hexdigest()[:8]

            # Check for existing bookmark
            existing = session.query(Bookmark).filter_by(unique_id=unique_id).first()
            if existing:
                if skip_duplicates:
                    return None  # Skip duplicate
                else:
                    raise ValueError(f"Bookmark with URL already exists: {url}")

            # Create bookmark
            # Extract added from kwargs if provided, otherwise use current time
            added_time = kwargs.pop("added", None) or datetime.now(timezone.utc)

            bookmark = Bookmark(
                url=url,
                title=title or self._fetch_title(url) or url,
                unique_id=unique_id,
                added=added_time,
                **{k: v for k, v in kwargs.items() if k not in ["tags"]}
            )

            # Handle tags
            tag_names = kwargs.get("tags", [])
            if tag_names:
                bookmark.tags = self._get_or_create_tags(session, tag_names)

            session.add(bookmark)
            session.flush()  # Get the ID before commit

            # Emit event for bookmark creation
            event = Event(
                event_type="bookmark_added",
                entity_type="bookmark",
                entity_id=bookmark.id,
                entity_url=url,
                event_data={"title": bookmark.title, "tags": tag_names if tag_names else []}
            )
            session.add(event)

            # Commit will happen in context manager, and expire_on_commit=False
            # means the object stays accessible
            return bookmark

    def get(self, id: Optional[int] = None, unique_id: Optional[str] = None) -> Optional[Bookmark]:
        """
        Get a bookmark by ID or unique ID.

        Args:
            id: Numeric bookmark ID
            unique_id: 8-character unique ID

        Returns:
            Bookmark instance or None
        """
        with self.session(expire_on_commit=False) as session:
            query = select(Bookmark).options(selectinload(Bookmark.tags))

            if id:
                query = query.where(Bookmark.id == id)
            elif unique_id:
                query = query.where(Bookmark.unique_id == unique_id)
            else:
                return None

            return session.execute(query).scalar_one_or_none()

    def query(self, sql: Optional[str] = None, **filters) -> List[Bookmark]:
        """
        Query bookmarks using SQL or keyword filters.

        Args:
            sql: Raw SQL WHERE clause (e.g., "tags LIKE '%python%'")
            **filters: Keyword filters (url, title, tags, stars, etc.)

        Returns:
            List of matching bookmarks
        """
        with self.session(expire_on_commit=False) as session:
            query = select(Bookmark).options(selectinload(Bookmark.tags))

            if sql:
                # Parse simplified SQL-like syntax
                query = query.where(text(sql))
            else:
                # Apply keyword filters
                if "url" in filters:
                    query = query.where(Bookmark.url.contains(filters["url"]))
                if "title" in filters:
                    query = query.where(Bookmark.title.contains(filters["title"]))
                if "stars" in filters:
                    query = query.where(Bookmark.stars == filters["stars"])
                if "tags" in filters:
                    tag_filter = filters["tags"]
                    query = query.join(Bookmark.tags).where(Tag.name.like(f"{tag_filter}%"))

            return list(session.execute(query).scalars())

    def list(self, limit: Optional[int] = None, offset: int = 0, order_by: str = "added", exclude_archived: bool = True) -> List[Bookmark]:
        """
        List bookmarks with pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            order_by: Sort field (added, title, visit_count, etc.)
            exclude_archived: If True, exclude archived bookmarks (default)

        Returns:
            List of bookmarks
        """
        with self.session(expire_on_commit=False) as session:
            query = select(Bookmark).options(selectinload(Bookmark.tags))

            # Filter archived bookmarks by default
            if exclude_archived:
                query = query.where(Bookmark.archived == False)

            # Apply ordering
            order_fields = {
                "added": Bookmark.added.desc(),
                "title": Bookmark.title,
                "visit_count": Bookmark.visit_count.desc(),
                "stars": Bookmark.stars.desc(),
            }
            query = query.order_by(order_fields.get(order_by, Bookmark.added.desc()))

            # Apply pagination
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            return list(session.execute(query).scalars())

    def update(self, id: int, **updates) -> bool:
        """
        Update a bookmark.

        Args:
            id: Bookmark ID
            **updates: Fields to update

        Returns:
            True if updated, False if not found
        """
        with self.session() as session:
            bookmark = session.get(Bookmark, id)
            if not bookmark:
                return False

            # Track changes for event emission
            changes = {}
            url = bookmark.url

            # Handle tags specially
            if "tags" in updates:
                tag_names = updates.pop("tags")
                old_tags = set(t.name for t in bookmark.tags)
                new_tags = set(tag_names)
                bookmark.tags = self._get_or_create_tags(session, tag_names)
                changes["tags"] = {"old": list(old_tags), "new": list(new_tags)}

                # Emit specific tag events
                added_tags = new_tags - old_tags
                removed_tags = old_tags - new_tags
                if added_tags:
                    session.add(Event(
                        event_type="tag_added", entity_type="bookmark",
                        entity_id=id, entity_url=bookmark.url,
                        event_data={"tags": list(added_tags)}
                    ))
                if removed_tags:
                    session.add(Event(
                        event_type="tag_removed", entity_type="bookmark",
                        entity_id=id, entity_url=bookmark.url,
                        event_data={"tags": list(removed_tags)}
                    ))

            # Update other fields and track changes
            for key, value in updates.items():
                if hasattr(bookmark, key):
                    old_value = getattr(bookmark, key)
                    if old_value != value:
                        changes[key] = {"old": old_value, "new": value}
                        setattr(bookmark, key, value)

            # Emit specific events for key boolean state changes
            _state_event_map = {
                "stars": ("bookmark_starred", "bookmark_unstarred"),
                "archived": ("bookmark_archived", "bookmark_unarchived"),
                "pinned": ("bookmark_pinned", "bookmark_unpinned"),
            }
            for field, (on_event, off_event) in _state_event_map.items():
                if field in changes:
                    event_type = on_event if changes[field]["new"] else off_event
                    session.add(Event(
                        event_type=event_type, entity_type="bookmark",
                        entity_id=id, entity_url=url
                    ))

            # Emit general update event if there were changes
            if changes:
                session.add(Event(
                    event_type="bookmark_updated", entity_type="bookmark",
                    entity_id=id, entity_url=url, event_data=changes
                ))

            return True

    def delete(self, id: int) -> bool:
        """
        Delete a bookmark.

        Args:
            id: Bookmark ID

        Returns:
            True if deleted, False if not found
        """
        with self.session() as session:
            bookmark = session.get(Bookmark, id)
            if bookmark:
                # Preserve URL and title before deletion for audit trail
                url = bookmark.url
                title = bookmark.title
                tags = [t.name for t in bookmark.tags]

                session.delete(bookmark)

                # Emit deletion event with preserved data
                session.add(Event(
                    event_type="bookmark_deleted", entity_type="bookmark",
                    entity_id=id, entity_url=url,
                    event_data={"title": title, "tags": tags}
                ))
                return True
            return False

    def stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dictionary with counts and statistics
        """
        with self.session() as session:
            stats = {
                "total_bookmarks": session.query(func.count(Bookmark.id)).scalar(),
                "total_tags": session.query(func.count(Tag.id)).scalar(),
                "starred_count": session.query(func.count(Bookmark.id)).filter(Bookmark.stars == True).scalar(),
                "total_visits": session.query(func.sum(Bookmark.visit_count)).scalar() or 0,
                "database_url": self.url,
            }

            # Add file size for SQLite
            if self.path and self.path.exists():
                stats["database_size"] = self.path.stat().st_size
                stats["database_path"] = str(self.path)

            return stats

    def info(self) -> Dict[str, Any]:
        """
        Get detailed database information.

        Returns:
            Dictionary with database metadata, schema info, and connection details
        """
        with self.session() as session:
            info = {
                "url": self.url,
                "engine": str(self.engine.url.drivername),
                "tables": list(Base.metadata.tables.keys()),
                "schema_version": "2.0",  # Update as schema evolves
            }

            # Add SQLite-specific info
            if self.url.startswith("sqlite:"):
                if self.path:
                    info["path"] = str(self.path)
                    if self.path.exists():
                        info["size_bytes"] = self.path.stat().st_size
                        info["size_mb"] = round(self.path.stat().st_size / 1024 / 1024, 2)

                # Get SQLite pragmas
                try:
                    result = session.execute(text("PRAGMA journal_mode")).scalar()
                    info["journal_mode"] = result
                    result = session.execute(text("PRAGMA page_count")).scalar()
                    info["page_count"] = result
                    result = session.execute(text("PRAGMA page_size")).scalar()
                    info["page_size"] = result
                except Exception:
                    pass

            return info

    def schema(self) -> Dict[str, Any]:
        """
        Get database schema information.

        Returns:
            Dictionary mapping table names to their column definitions
        """
        schema_info = {}

        for table_name, table in Base.metadata.tables.items():
            columns = []
            for col in table.columns:
                columns.append({
                    "name": col.name,
                    "type": str(col.type),
                    "nullable": col.nullable,
                    "primary_key": col.primary_key,
                    "unique": col.unique,
                    "default": str(col.default) if col.default else None,
                })

            indexes = [{"name": idx.name, "columns": [c.name for c in idx.columns]} for idx in table.indexes]

            schema_info[table_name] = {
                "columns": columns,
                "indexes": indexes,
            }

        return schema_info

    def all(self) -> List[Bookmark]:
        """
        Get all bookmarks.

        Returns:
            List of all bookmarks
        """
        with self.session(expire_on_commit=False) as session:
            result = session.execute(
                select(Bookmark)
                .options(selectinload(Bookmark.tags))
                .order_by(Bookmark.added.desc())
            )
            return list(result.scalars())

    def search(self, query: Optional[str] = None, in_content: bool = False, **filters) -> List[Bookmark]:
        """
        Search bookmarks with optional filters.

        Args:
            query: Text search query (searches title, URL, description, and optionally content)
            in_content: If True, also search within cached markdown content
            **filters: Additional filters (e.g., reachable=True, stars=True)

        Returns:
            List of matching bookmarks
        """
        from btk.models import ContentCache

        with self.session(expire_on_commit=False) as session:
            query_filters = []

            # Text search
            if query:
                if in_content:
                    # Join with ContentCache to search in markdown content
                    search_filter = or_(
                        Bookmark.title.contains(query),
                        Bookmark.url.contains(query),
                        Bookmark.description.contains(query),
                        ContentCache.markdown_content.contains(query)
                    )
                else:
                    search_filter = or_(
                        Bookmark.title.contains(query),
                        Bookmark.url.contains(query),
                        Bookmark.description.contains(query)
                    )
                query_filters.append(search_filter)

            # Additional filters
            if 'reachable' in filters:
                query_filters.append(Bookmark.reachable == filters['reachable'])
            if 'stars' in filters or 'starred' in filters:
                value = filters.get('stars', filters.get('starred'))
                query_filters.append(Bookmark.stars == value)
            if 'archived' in filters:
                query_filters.append(Bookmark.archived == filters['archived'])
            if 'pinned' in filters:
                query_filters.append(Bookmark.pinned == filters['pinned'])
            if 'tags' in filters:
                # Filter by specific tags (AND logic - bookmark must have all tags)
                tag_names = filters['tags']
                for tag_name in tag_names:
                    query_filters.append(Bookmark.tags.any(Tag.name == tag_name))
            if 'untagged' in filters and filters['untagged']:
                # Filter to bookmarks with no tags
                query_filters.append(~Bookmark.tags.any())
            if 'url' in filters:
                # Exact URL match
                query_filters.append(Bookmark.url == filters['url'])

            # Build query
            query_obj = select(Bookmark).options(selectinload(Bookmark.tags))

            if in_content:
                # Left join with ContentCache for content search
                query_obj = query_obj.outerjoin(ContentCache, Bookmark.id == ContentCache.bookmark_id)

            if query_filters:
                query_obj = query_obj.where(and_(*query_filters))

            query_obj = query_obj.order_by(Bookmark.visit_count.desc())

            result = session.execute(query_obj)

            return list(result.scalars().unique())

    def refresh_content(
        self,
        bookmark_id: int,
        update_metadata: bool = True,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Refresh cached content for a bookmark.

        Args:
            bookmark_id: Bookmark ID to refresh
            update_metadata: Update bookmark title/description from fetched content
            force: Force update even if content hasn't changed

        Returns:
            Dictionary with refresh status and details
        """
        from btk.content_fetcher import ContentFetcher
        from btk.models import ContentCache

        with self.session(expire_on_commit=False) as session:
            bookmark = session.get(Bookmark, bookmark_id)
            if not bookmark:
                return {"success": False, "error": "Bookmark not found"}

            # Fetch content
            fetcher = ContentFetcher()
            result = fetcher.fetch_and_process(bookmark.url)

            if not result["success"]:
                # Mark as unreachable but preserve existing data
                bookmark.reachable = False
                return {
                    "success": False,
                    "error": result["error"],
                    "status_code": result["status_code"],
                    "bookmark_id": bookmark_id,
                    "url": bookmark.url,
                }

            # Check if content changed
            content_changed = True
            existing_cache = session.execute(
                select(ContentCache).where(ContentCache.bookmark_id == bookmark_id)
            ).scalar_one_or_none()

            if existing_cache and not force:
                content_changed = existing_cache.content_hash != result["content_hash"]

            # Update or create content cache
            if content_changed or force or not existing_cache:
                if existing_cache:
                    # Update existing
                    existing_cache.html_content = result["html_content"]
                    existing_cache.markdown_content = result["markdown_content"]
                    existing_cache.content_hash = result["content_hash"]
                    existing_cache.content_length = result["content_length"]
                    existing_cache.compressed_size = result["compressed_size"]
                    existing_cache.status_code = result["status_code"]
                    existing_cache.response_time_ms = result["response_time_ms"]
                    existing_cache.content_type = result["content_type"]
                    existing_cache.encoding = result["encoding"]
                    existing_cache.fetched_at = datetime.now(timezone.utc)
                else:
                    # Create new
                    cache = ContentCache(
                        bookmark_id=bookmark_id,
                        html_content=result["html_content"],
                        markdown_content=result["markdown_content"],
                        content_hash=result["content_hash"],
                        content_length=result["content_length"],
                        compressed_size=result["compressed_size"],
                        status_code=result["status_code"],
                        response_time_ms=result["response_time_ms"],
                        content_type=result["content_type"],
                        encoding=result["encoding"],
                    )
                    session.add(cache)

            # Update bookmark metadata if requested and content is fresh
            if update_metadata and result["title"]:
                bookmark.title = result["title"]

            # Mark as reachable
            bookmark.reachable = True

            return {
                "success": True,
                "bookmark_id": bookmark_id,
                "url": bookmark.url,
                "status_code": result["status_code"],
                "content_changed": content_changed,
                "content_length": result["content_length"],
                "compressed_size": result["compressed_size"],
                "compression_ratio": (
                    (1 - result["compressed_size"] / result["content_length"]) * 100
                    if result["content_length"] > 0
                    else 0
                ),
                "title_updated": update_metadata and result["title"] and result["title"] != bookmark.title,
            }

    def _get_or_create_tags(self, session: Session, tag_names: List[str]) -> List[Tag]:
        """Get or create tags by name (thread-safe using global lock)."""
        tags = []
        for name in tag_names:
            # Use global lock to serialize tag creation across all threads
            with _tag_creation_lock:
                # Check if tag exists
                tag = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()

                if not tag:
                    # Tag doesn't exist, create it
                    tag = Tag(name=name)
                    session.add(tag)
                    # Flush immediately to persist it
                    try:
                        session.flush()
                    except IntegrityError:
                        # Extremely rare: another process (not thread) created it
                        session.rollback()
                        tag = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()

                tags.append(tag)

        return tags

    def _fetch_title(self, url: str) -> Optional[str]:
        """Fetch title from URL."""
        try:
            import requests
            from bs4 import BeautifulSoup
            config = get_config()

            response = requests.get(
                url,
                timeout=config.timeout,
                headers={"User-Agent": config.user_agent},
                verify=config.verify_ssl
            )
            soup = BeautifulSoup(response.text, "html.parser")
            title_tag = soup.find("title")
            return title_tag.text.strip() if title_tag else None
        except Exception:
            return None


# Global database instance
_db: Optional[Database] = None


def get_db(path: Optional[str] = None, reload: bool = False) -> Database:
    """
    Get the global database instance.

    Args:
        path: Database file path
        reload: Force new connection

    Returns:
        Database instance
    """
    global _db
    if _db is None or reload or path:
        _db = Database(path)
    return _db