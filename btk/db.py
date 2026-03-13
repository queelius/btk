"""
Simplified database interface for BTK.

Provides a clean, minimal API for database operations using SQLAlchemy.
Works with single database files instead of library directories.

Includes a lightweight schema versioning system (no Alembic) with
migration functions that run on init.
"""
import logging
import shutil
from pathlib import Path
from typing import Optional, List, Generator, Any, Dict
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, select, func, or_, and_, text,
    event, inspect
)
from sqlalchemy.orm import Session, sessionmaker, selectinload
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import IntegrityError

from btk.models import (
    Base, Bookmark, Tag, Event,
    BookmarkSource, BookmarkVisit, BookmarkMedia, ViewDefinition, SchemaVersion,
)
from btk.config import get_config

logger = logging.getLogger(__name__)

# Global lock for tag creation to prevent race conditions
import threading
_tag_creation_lock = threading.Lock()

# Current schema version — bump when adding new migrations
CURRENT_SCHEMA_VERSION = 1


# =============================================================================
# Migration Functions
# =============================================================================

def _get_schema_version(conn) -> int:
    """Get current schema version from database, or -1 if no versioning yet."""
    try:
        result = conn.execute(text("SELECT MAX(version) FROM schema_version"))
        row = result.fetchone()
        return row[0] if row and row[0] is not None else 0
    except Exception:
        # Table doesn't exist yet
        return -1


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name}
    )
    return result.fetchone() is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result.fetchall()]
    return column_name in columns


def _run_migrations(engine, db_path: Optional[Path] = None):
    """
    Run any pending migrations.

    Called during Database.__init__ after create_all.
    """
    with engine.connect() as conn:
        current = _get_schema_version(conn)

        if current >= CURRENT_SCHEMA_VERSION:
            return  # Up to date

        # Ensure schema_version table exists (create_all should have done this,
        # but be safe for pre-existing databases)
        if not _table_exists(conn, 'schema_version'):
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                "  version INTEGER PRIMARY KEY,"
                "  applied_at DATETIME NOT NULL,"
                "  description TEXT"
                ")"
            ))
            conn.commit()

        # Run each pending migration
        migrations = {
            0: (_migrate_v0_to_v1, "Initial satellite tables: sources, visits, media, views"),
        }

        for version, (migrate_fn, description) in sorted(migrations.items()):
            if version >= current and version < CURRENT_SCHEMA_VERSION:
                logger.info(f"Running migration v{version} → v{version + 1}: {description}")

                # Backup before migration (SQLite only)
                if db_path and db_path.exists():
                    backup_path = db_path.with_suffix(f".v{version}.bak")
                    if not backup_path.exists():
                        shutil.copy2(db_path, backup_path)
                        logger.info(f"Database backed up to {backup_path}")

                migrate_fn(conn)

                # Record migration
                conn.execute(
                    text("INSERT INTO schema_version (version, applied_at, description) VALUES (:v, :at, :desc)"),
                    {"v": version + 1, "at": datetime.now(timezone.utc).isoformat(), "desc": description}
                )
                conn.commit()
                logger.info(f"Migration to v{version + 1} complete")


def _migrate_v0_to_v1(conn):
    """
    Migration: v0 → v1 — Satellite tables for the data model redesign.

    Creates: bookmark_sources, bookmark_visits, bookmark_media, views
    Modifies: bookmarks (add bookmark_type, drop media columns + favicon_path)
    Modifies: collections (add icon, position)
    Modifies: bookmark_collections (add position)
    Backfills: bookmark_media from existing media columns, bookmark_sources with legacy source
    """
    # --- Create new tables (if they don't already exist via create_all) ---
    if not _table_exists(conn, 'bookmark_sources'):
        conn.execute(text("""
            CREATE TABLE bookmark_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bookmark_id INTEGER NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
                source_type VARCHAR(32) NOT NULL,
                source_name VARCHAR(256),
                source_profile VARCHAR(256),
                folder_path VARCHAR(1024),
                imported_at DATETIME NOT NULL,
                raw_data JSON
            )
        """))
        conn.execute(text("CREATE INDEX ix_bookmark_sources_bookmark_id ON bookmark_sources(bookmark_id)"))
        conn.execute(text("CREATE INDEX ix_bookmark_sources_source_type ON bookmark_sources(source_type)"))
        conn.execute(text("CREATE INDEX ix_bookmark_sources_imported_at ON bookmark_sources(imported_at)"))

    if not _table_exists(conn, 'bookmark_visits'):
        conn.execute(text("""
            CREATE TABLE bookmark_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bookmark_id INTEGER NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
                visited_at DATETIME NOT NULL,
                source_type VARCHAR(32) NOT NULL,
                source_name VARCHAR(256),
                duration_secs INTEGER,
                transition_type VARCHAR(32)
            )
        """))
        conn.execute(text("CREATE INDEX ix_bookmark_visits_bookmark_id ON bookmark_visits(bookmark_id)"))
        conn.execute(text("CREATE INDEX ix_bookmark_visits_visited_at ON bookmark_visits(visited_at)"))
        conn.execute(text("CREATE INDEX ix_bookmark_visits_source_type ON bookmark_visits(source_type)"))
        conn.execute(text("CREATE UNIQUE INDEX uq_bookmark_visit ON bookmark_visits(bookmark_id, visited_at, source_type)"))

    if not _table_exists(conn, 'bookmark_media'):
        conn.execute(text("""
            CREATE TABLE bookmark_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bookmark_id INTEGER NOT NULL UNIQUE REFERENCES bookmarks(id) ON DELETE CASCADE,
                media_type VARCHAR(32),
                media_source VARCHAR(64),
                media_id VARCHAR(128),
                author_name VARCHAR(256),
                author_url VARCHAR(2048),
                thumbnail_url VARCHAR(2048),
                published_at DATETIME
            )
        """))
        conn.execute(text("CREATE INDEX ix_bookmark_media_bookmark_id ON bookmark_media(bookmark_id)"))
        conn.execute(text("CREATE INDEX ix_bookmark_media_source ON bookmark_media(media_source)"))

    if not _table_exists(conn, 'views'):
        conn.execute(text("""
            CREATE TABLE views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(256) UNIQUE NOT NULL,
                description TEXT,
                definition JSON NOT NULL,
                created_by VARCHAR(32),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX ix_views_name ON views(name)"))

    # --- Add bookmark_type to bookmarks if missing ---
    if _table_exists(conn, 'bookmarks') and not _column_exists(conn, 'bookmarks', 'bookmark_type'):
        conn.execute(text("ALTER TABLE bookmarks ADD COLUMN bookmark_type VARCHAR(16) NOT NULL DEFAULT 'bookmark'"))

    # --- Backfill bookmark_media from existing media columns ---
    if _table_exists(conn, 'bookmarks') and _column_exists(conn, 'bookmarks', 'media_type'):
        conn.execute(text("""
            INSERT OR IGNORE INTO bookmark_media (bookmark_id, media_type, media_source, media_id,
                                                  author_name, author_url, thumbnail_url, published_at)
            SELECT id, media_type, media_source, media_id,
                   author_name, author_url, thumbnail_url, published_at
            FROM bookmarks
            WHERE media_type IS NOT NULL
        """))

    # --- Backfill bookmark_sources with 'legacy' source for existing bookmarks ---
    # Only for bookmarks that don't already have a source row
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(text(f"""
        INSERT INTO bookmark_sources (bookmark_id, source_type, imported_at)
        SELECT b.id, 'legacy', '{now}'
        FROM bookmarks b
        WHERE NOT EXISTS (
            SELECT 1 FROM bookmark_sources bs WHERE bs.bookmark_id = b.id
        )
    """))

    # --- Add icon and position to collections if missing ---
    if _table_exists(conn, 'collections'):
        if not _column_exists(conn, 'collections', 'icon'):
            conn.execute(text("ALTER TABLE collections ADD COLUMN icon VARCHAR(32)"))
        if not _column_exists(conn, 'collections', 'position'):
            conn.execute(text("ALTER TABLE collections ADD COLUMN position INTEGER NOT NULL DEFAULT 0"))

    # --- Add position to bookmark_collections if missing ---
    if _table_exists(conn, 'bookmark_collections'):
        if not _column_exists(conn, 'bookmark_collections', 'position'):
            conn.execute(text("ALTER TABLE bookmark_collections ADD COLUMN position INTEGER DEFAULT 0"))

    # --- Drop old media columns from bookmarks using table rebuild ---
    # We use SQLite's table-rebuild pattern for broad compatibility.
    # However, since we have hybrid properties for backward compat,
    # we KEEP the old columns in the physical table to avoid breaking
    # existing raw SQL queries in the wild. The columns just become
    # dead weight — new data goes to bookmark_media only.
    # This is safer than a destructive rebuild on a 790MB database.

    conn.commit()


# =============================================================================
# Database Class
# =============================================================================

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
        """
        config = get_config()

        # Determine database URL
        if url:
            self.url = url
            self.path = None
        elif path:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.url = f"sqlite:///{self.path}"
        else:
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
                poolclass=NullPool,
                echo=config.database_echo
            )
            event.listen(self.engine, "connect", self._configure_sqlite)
        else:
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

        # Initialize schema (creates any missing tables)
        Base.metadata.create_all(self.engine)

        # Run migrations for existing databases
        if self.url.startswith("sqlite:"):
            _run_migrations(self.engine, self.path)

    @staticmethod
    def _configure_sqlite(dbapi_conn, connection_record):
        """Configure SQLite for optimal performance."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA cache_size = -64000")
        cursor.execute("PRAGMA temp_store = MEMORY")
        cursor.close()

    @contextmanager
    def session(self, expire_on_commit: bool = True) -> Generator[Session, None, None]:
        """Context manager for database sessions."""
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
        """Emit an event for the audit trail."""
        with self.session() as session:
            evt = Event(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_url=entity_url,
                event_data=event_data
            )
            session.add(evt)

    # =========================================================================
    # Bookmark CRUD
    # =========================================================================

    def add(self, url: str, title: Optional[str] = None, skip_duplicates: bool = True, **kwargs) -> Optional[Bookmark]:
        """
        Add a bookmark to the database.

        Supports provenance tracking via source_* kwargs:
            source_type: str — chrome, firefox, html_file, manual, etc.
            source_name: str — profile display name, filename
            source_profile: str — browser profile directory name
            folder_path: str — original folder hierarchy
            raw_data: dict — lossless preservation of source-specific fields
            bookmark_type: str — bookmark, history, tab, reference

        On duplicate URLs with skip_duplicates=True, creates a BookmarkSource
        row for merge provenance but returns None.

        Args:
            url: The URL to bookmark
            title: Optional title (fetched if not provided)
            skip_duplicates: If True, skip duplicate URLs; if False, raise error
            **kwargs: Additional bookmark fields (tags, description, stars, source_*, media_*, etc.)

        Returns:
            Created bookmark instance or None if duplicate was skipped
        """
        # Extract source metadata from kwargs
        source_type = kwargs.pop("source_type", None)
        source_name = kwargs.pop("source_name", None)
        source_profile = kwargs.pop("source_profile", None)
        folder_path = kwargs.pop("folder_path", None)
        raw_data = kwargs.pop("raw_data", None)

        # Extract media metadata from kwargs
        media_type = kwargs.pop("media_type", None)
        media_source = kwargs.pop("media_source", None)
        media_id = kwargs.pop("media_id", None)
        author_name = kwargs.pop("author_name", None)
        author_url = kwargs.pop("author_url", None)
        thumbnail_url = kwargs.pop("thumbnail_url", None)
        published_at = kwargs.pop("published_at", None)

        with self.session(expire_on_commit=False) as session:
            from hashlib import sha256
            unique_id = sha256(url.encode()).hexdigest()[:8]

            # Check for existing bookmark
            existing = session.query(Bookmark).filter_by(unique_id=unique_id).first()
            if existing:
                # Merge provenance: create source row even for duplicates
                if source_type:
                    source = BookmarkSource(
                        bookmark_id=existing.id,
                        source_type=source_type,
                        source_name=source_name,
                        source_profile=source_profile,
                        folder_path=folder_path,
                        raw_data=raw_data,
                    )
                    session.add(source)

                if skip_duplicates:
                    return None
                else:
                    raise ValueError(f"Bookmark with URL already exists: {url}")

            # Create bookmark
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
            session.flush()  # Get the ID before creating related rows

            # Create provenance source row
            if source_type:
                source = BookmarkSource(
                    bookmark_id=bookmark.id,
                    source_type=source_type,
                    source_name=source_name,
                    source_profile=source_profile,
                    folder_path=folder_path,
                    raw_data=raw_data,
                )
                session.add(source)

            # Create media row if media metadata provided
            if media_type:
                media = BookmarkMedia(
                    bookmark_id=bookmark.id,
                    media_type=media_type,
                    media_source=media_source,
                    media_id=media_id,
                    author_name=author_name,
                    author_url=author_url,
                    thumbnail_url=thumbnail_url,
                    published_at=published_at,
                )
                session.add(media)

            # Emit event for bookmark creation
            evt = Event(
                event_type="bookmark_added",
                entity_type="bookmark",
                entity_id=bookmark.id,
                entity_url=url,
                event_data={"title": bookmark.title, "tags": tag_names if tag_names else []}
            )
            session.add(evt)

            return bookmark

    def add_visit(self, bookmark_id: int, visited_at: datetime,
                  source_type: str, source_name: Optional[str] = None,
                  duration_secs: Optional[int] = None,
                  transition_type: Optional[str] = None) -> Optional[BookmarkVisit]:
        """
        Add a visit record for a bookmark.

        Skips duplicates based on (bookmark_id, visited_at, source_type).

        Returns:
            Created BookmarkVisit or None if duplicate
        """
        with self.session(expire_on_commit=False) as session:
            try:
                visit = BookmarkVisit(
                    bookmark_id=bookmark_id,
                    visited_at=visited_at,
                    source_type=source_type,
                    source_name=source_name,
                    duration_secs=duration_secs,
                    transition_type=transition_type,
                )
                session.add(visit)
                session.flush()
                return visit
            except IntegrityError:
                session.rollback()
                return None  # Duplicate visit

    def refresh_visit_cache(self, bookmark_id: Optional[int] = None) -> int:
        """
        Recompute visit_count and last_visited from bookmark_visits.

        Args:
            bookmark_id: If provided, refresh only this bookmark. Otherwise, refresh all.

        Returns:
            Number of bookmarks updated
        """
        with self.session() as session:
            if bookmark_id:
                bookmarks = [session.get(Bookmark, bookmark_id)]
                bookmarks = [b for b in bookmarks if b]
            else:
                bookmarks = list(session.execute(select(Bookmark)).scalars())

            updated = 0
            for bookmark in bookmarks:
                visit_stats = session.execute(
                    select(
                        func.count(BookmarkVisit.id),
                        func.max(BookmarkVisit.visited_at)
                    ).where(BookmarkVisit.bookmark_id == bookmark.id)
                ).one()

                count, last = visit_stats
                if count > 0:
                    bookmark.visit_count = count
                    bookmark.last_visited = last
                    updated += 1

            return updated

    def get(self, id: Optional[int] = None, unique_id: Optional[str] = None) -> Optional[Bookmark]:
        """Get a bookmark by ID or unique ID."""
        with self.session(expire_on_commit=False) as session:
            query = select(Bookmark).options(
                selectinload(Bookmark.tags),
                selectinload(Bookmark.media),
                selectinload(Bookmark.sources),
            )

            if id:
                query = query.where(Bookmark.id == id)
            elif unique_id:
                query = query.where(Bookmark.unique_id == unique_id)
            else:
                return None

            return session.execute(query).scalar_one_or_none()

    def query(self, sql: Optional[str] = None, **filters) -> List[Bookmark]:
        """Query bookmarks using SQL or keyword filters."""
        with self.session(expire_on_commit=False) as session:
            query = select(Bookmark).options(selectinload(Bookmark.tags))

            if sql:
                query = query.where(text(sql))
            else:
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
        """List bookmarks with pagination."""
        with self.session(expire_on_commit=False) as session:
            query = select(Bookmark).options(selectinload(Bookmark.tags))

            if exclude_archived:
                query = query.where(Bookmark.archived == False)

            order_fields = {
                "added": Bookmark.added.desc(),
                "title": Bookmark.title,
                "visit_count": Bookmark.visit_count.desc(),
                "stars": Bookmark.stars.desc(),
            }
            query = query.order_by(order_fields.get(order_by, Bookmark.added.desc()))

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            return list(session.execute(query).scalars())

    def update(self, id: int, **updates) -> bool:
        """Update a bookmark."""
        with self.session() as session:
            bookmark = session.get(Bookmark, id)
            if not bookmark:
                return False

            changes = {}
            url = bookmark.url

            # Handle tags specially
            if "tags" in updates:
                tag_names = updates.pop("tags")
                old_tags = set(t.name for t in bookmark.tags)
                new_tags = set(tag_names)
                bookmark.tags = self._get_or_create_tags(session, tag_names)
                changes["tags"] = {"old": list(old_tags), "new": list(new_tags)}

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

            # Handle media fields — route to BookmarkMedia
            media_fields = {"media_type", "media_source", "media_id",
                            "author_name", "author_url", "thumbnail_url", "published_at"}
            media_updates = {k: updates.pop(k) for k in list(updates) if k in media_fields}
            if media_updates:
                if not bookmark.media:
                    bookmark.media = BookmarkMedia(bookmark_id=bookmark.id)
                    session.add(bookmark.media)
                    session.flush()
                for key, value in media_updates.items():
                    old_value = getattr(bookmark.media, key, None)
                    if old_value != value:
                        changes[key] = {"old": old_value, "new": value}
                        setattr(bookmark.media, key, value)

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

            if changes:
                session.add(Event(
                    event_type="bookmark_updated", entity_type="bookmark",
                    entity_id=id, entity_url=url, event_data=changes
                ))

            return True

    def delete(self, id: int) -> bool:
        """Delete a bookmark."""
        with self.session() as session:
            bookmark = session.get(Bookmark, id)
            if bookmark:
                url = bookmark.url
                title = bookmark.title
                tags = [t.name for t in bookmark.tags]

                session.delete(bookmark)

                session.add(Event(
                    event_type="bookmark_deleted", entity_type="bookmark",
                    entity_id=id, entity_url=url,
                    event_data={"title": title, "tags": tags}
                ))
                return True
            return False

    # =========================================================================
    # Views CRUD
    # =========================================================================

    def save_view(self, name: str, definition: dict, description: Optional[str] = None,
                  created_by: str = "user") -> ViewDefinition:
        """Save a view definition to the database (upsert)."""
        with self.session(expire_on_commit=False) as session:
            existing = session.execute(
                select(ViewDefinition).where(ViewDefinition.name == name)
            ).scalar_one_or_none()

            if existing:
                existing.definition = definition
                existing.description = description
                existing.updated_at = datetime.now(timezone.utc)
                return existing
            else:
                view = ViewDefinition(
                    name=name,
                    definition=definition,
                    description=description,
                    created_by=created_by,
                )
                session.add(view)
                session.flush()
                return view

    def delete_view(self, name: str) -> bool:
        """Delete a view definition from the database."""
        with self.session() as session:
            view = session.execute(
                select(ViewDefinition).where(ViewDefinition.name == name)
            ).scalar_one_or_none()
            if view:
                session.delete(view)
                return True
            return False

    def list_views(self) -> List[ViewDefinition]:
        """List all view definitions from the database."""
        with self.session(expire_on_commit=False) as session:
            return list(session.execute(
                select(ViewDefinition).order_by(ViewDefinition.name)
            ).scalars())

    # =========================================================================
    # Statistics & Info
    # =========================================================================

    def stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.session() as session:
            stats = {
                "total_bookmarks": session.query(func.count(Bookmark.id)).scalar(),
                "total_tags": session.query(func.count(Tag.id)).scalar(),
                "starred_count": session.query(func.count(Bookmark.id)).filter(Bookmark.stars == True).scalar(),
                "total_visits": session.query(func.sum(Bookmark.visit_count)).scalar() or 0,
                "total_sources": session.query(func.count(BookmarkSource.id)).scalar(),
                "total_visit_records": session.query(func.count(BookmarkVisit.id)).scalar(),
                "total_media": session.query(func.count(BookmarkMedia.id)).scalar(),
                "database_url": self.url,
            }

            if self.path and self.path.exists():
                stats["database_size"] = self.path.stat().st_size
                stats["database_path"] = str(self.path)

            return stats

    def info(self) -> Dict[str, Any]:
        """Get detailed database information."""
        with self.session() as session:
            # Get schema version
            try:
                schema_ver = session.execute(
                    text("SELECT MAX(version) FROM schema_version")
                ).scalar() or 0
            except Exception:
                schema_ver = 0

            info = {
                "url": self.url,
                "engine": str(self.engine.url.drivername),
                "tables": list(Base.metadata.tables.keys()),
                "schema_version": schema_ver,
            }

            if self.url.startswith("sqlite:"):
                if self.path:
                    info["path"] = str(self.path)
                    if self.path.exists():
                        info["size_bytes"] = self.path.stat().st_size
                        info["size_mb"] = round(self.path.stat().st_size / 1024 / 1024, 2)

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
        """Get database schema information."""
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
        """Get all bookmarks."""
        with self.session(expire_on_commit=False) as session:
            result = session.execute(
                select(Bookmark)
                .options(selectinload(Bookmark.tags))
                .order_by(Bookmark.added.desc())
            )
            return list(result.scalars())

    def search(self, query: Optional[str] = None, in_content: bool = False, **filters) -> List[Bookmark]:
        """Search bookmarks with optional filters."""
        from btk.models import ContentCache

        with self.session(expire_on_commit=False) as session:
            query_filters = []

            if query:
                if in_content:
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
                tag_names = filters['tags']
                for tag_name in tag_names:
                    query_filters.append(Bookmark.tags.any(Tag.name == tag_name))
            if 'untagged' in filters and filters['untagged']:
                query_filters.append(~Bookmark.tags.any())
            if 'url' in filters:
                query_filters.append(Bookmark.url == filters['url'])

            query_obj = select(Bookmark).options(selectinload(Bookmark.tags))

            if in_content:
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
        """Refresh cached content for a bookmark."""
        from btk.content_fetcher import ContentFetcher
        from btk.models import ContentCache

        with self.session(expire_on_commit=False) as session:
            bookmark = session.get(Bookmark, bookmark_id)
            if not bookmark:
                return {"success": False, "error": "Bookmark not found"}

            fetcher = ContentFetcher()
            result = fetcher.fetch_and_process(bookmark.url)

            if not result["success"]:
                bookmark.reachable = False
                return {
                    "success": False,
                    "error": result["error"],
                    "status_code": result["status_code"],
                    "bookmark_id": bookmark_id,
                    "url": bookmark.url,
                }

            content_changed = True
            existing_cache = session.execute(
                select(ContentCache).where(ContentCache.bookmark_id == bookmark_id)
            ).scalar_one_or_none()

            if existing_cache and not force:
                content_changed = existing_cache.content_hash != result["content_hash"]

            if content_changed or force or not existing_cache:
                if existing_cache:
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

            if update_metadata and result["title"]:
                bookmark.title = result["title"]

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
            with _tag_creation_lock:
                tag = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()

                if not tag:
                    tag = Tag(name=name)
                    session.add(tag)
                    try:
                        session.flush()
                    except IntegrityError:
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
    """Get the global database instance.

    Args:
        path: A named database (e.g. "history"), a file path, or None for default.
              When provided, returns a fresh instance without affecting the global.
        reload: Force re-creation of the default database instance.
    """
    global _db
    if path:
        # Named/explicit databases are not cached in the global
        config = get_config()
        resolved = config.resolve_database(path)
        return Database(resolved)
    if _db is None or reload:
        _db = Database()
    return _db
