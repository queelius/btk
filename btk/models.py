"""
SQLAlchemy models for BTK bookmark management.

This module defines the database schema for bookmarks, tags, and their relationships.
The schema follows a satellite-table pattern: a slim core Bookmark table with related
tables for provenance (bookmark_sources), visit history (bookmark_visits), media
metadata (bookmark_media), and stored views (views).
"""
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey, Table, Index, UniqueConstraint,
    Float, JSON, LargeBinary
)
from sqlalchemy.orm import (
    DeclarativeBase, relationship, Mapped, mapped_column
)
from sqlalchemy.ext.hybrid import hybrid_property


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Association table for many-to-many relationship between bookmarks and tags
bookmark_tags = Table(
    'bookmark_tags',
    Base.metadata,
    Column('bookmark_id', Integer, ForeignKey('bookmarks.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_bookmark_tags_bookmark_id', 'bookmark_id'),
    Index('ix_bookmark_tags_tag_id', 'tag_id')
)


class Bookmark(Base):
    """
    Bookmark model representing a saved URL with metadata.

    Core fields only — media metadata lives in BookmarkMedia,
    provenance in BookmarkSource, visit history in BookmarkVisit.

    Attributes:
        id: Primary key
        unique_id: 8-character SHA-256 hash for external references
        url: The bookmark URL (indexed for fast lookups)
        title: Bookmark title
        description: Optional description
        bookmark_type: Classification — bookmark, history, tab, reference
        added: Timestamp when bookmark was added
        last_visited: Cached from bookmark_visits (recomputed after sync)
        visit_count: Cached from bookmark_visits (recomputed after sync)
        stars: Whether bookmark is starred/favorited
        reachable: Whether URL is reachable (nullable for unchecked)
        extra_data: JSON field for additional flexible data
    """
    __tablename__ = 'bookmarks'

    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unique_id: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default='')

    # Classification
    bookmark_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default='bookmark', index=True
    )  # bookmark, history, tab, reference

    # Timestamps
    added: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    last_visited: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    # Metrics and status
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stars: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reachable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, index=True)

    # Favicon storage
    favicon_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    favicon_mime_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Flexible metadata storage for additional fields
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    # --- Relationships ---
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary=bookmark_tags,
        back_populates="bookmarks",
        lazy="selectin"
    )
    content_cache: Mapped[Optional["ContentCache"]] = relationship(
        "ContentCache",
        back_populates="bookmark",
        uselist=False,
        cascade="all, delete-orphan"
    )
    media: Mapped[Optional["BookmarkMedia"]] = relationship(
        "BookmarkMedia",
        back_populates="bookmark",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    sources: Mapped[List["BookmarkSource"]] = relationship(
        "BookmarkSource",
        back_populates="bookmark",
        cascade="all, delete-orphan",
        order_by="BookmarkSource.imported_at.desc()"
    )
    visits: Mapped[List["BookmarkVisit"]] = relationship(
        "BookmarkVisit",
        back_populates="bookmark",
        cascade="all, delete-orphan",
        order_by="BookmarkVisit.visited_at.desc()"
    )

    # Indexes for common queries
    __table_args__ = (
        Index('ix_bookmarks_url_title', 'url', 'title'),
        Index('ix_bookmarks_added_desc', added.desc()),
        Index('ix_bookmarks_visit_count_desc', visit_count.desc()),
        UniqueConstraint('url', name='uq_bookmarks_url'),
    )

    # --- Convenience properties for backward compatibility with media fields ---
    @hybrid_property
    def media_type(self) -> Optional[str]:
        return self.media.media_type if self.media else None

    @hybrid_property
    def media_source(self) -> Optional[str]:
        return self.media.media_source if self.media else None

    @hybrid_property
    def media_id(self) -> Optional[str]:
        return self.media.media_id if self.media else None

    @hybrid_property
    def author_name(self) -> Optional[str]:
        return self.media.author_name if self.media else None

    @hybrid_property
    def author_url(self) -> Optional[str]:
        return self.media.author_url if self.media else None

    @hybrid_property
    def thumbnail_url(self) -> Optional[str]:
        return self.media.thumbnail_url if self.media else None

    @hybrid_property
    def published_at(self) -> Optional[datetime]:
        return self.media.published_at if self.media else None

    @hybrid_property
    def domain(self) -> str:
        """Extract domain from URL for grouping."""
        from urllib.parse import urlparse
        return urlparse(self.url).netloc

    @hybrid_property
    def tag_names(self) -> List[str]:
        """Get list of tag names for this bookmark."""
        return [tag.name for tag in self.tags]

    def __repr__(self):
        return f"<Bookmark(id={self.id}, title='{self.title[:50]}', url='{self.url[:50]}')>"


class BookmarkSource(Base):
    """
    Provenance tracking for bookmarks.

    Records where each bookmark came from — browser profile, file import,
    manual entry, API, etc. Multiple sources per bookmark enable merge
    provenance: one bookmark can be imported from Chrome AND Firefox.

    raw_data preserves all source-specific attributes for lossless round-trip.
    """
    __tablename__ = 'bookmark_sources'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bookmarks.id', ondelete='CASCADE'),
        nullable=False
    )

    # Source identification
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # chrome, firefox, safari, html_file, json_file, csv_file, manual, api
    source_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # profile display name, filename
    source_profile: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # browser profile dir name
    folder_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)  # original folder hierarchy

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Lossless preservation of source-specific fields
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationship
    bookmark: Mapped["Bookmark"] = relationship("Bookmark", back_populates="sources")

    __table_args__ = (
        Index('ix_bookmark_sources_bookmark_id', 'bookmark_id'),
        Index('ix_bookmark_sources_source_type', 'source_type'),
        Index('ix_bookmark_sources_imported_at', 'imported_at'),
    )

    def __repr__(self):
        return f"<BookmarkSource(bookmark_id={self.bookmark_id}, source={self.source_type})>"


class BookmarkVisit(Base):
    """
    Individual visit records from browser history sync.

    btk is a library catalog, not a browser — visits come exclusively
    from browser sync. visit_count and last_visited on Bookmark are
    cached denormalizations recomputed after each sync.
    """
    __tablename__ = 'bookmark_visits'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bookmarks.id', ondelete='CASCADE'),
        nullable=False
    )

    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # chrome_history, firefox_history, safari_history
    source_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # profile display name
    duration_secs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transition_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # typed, link, auto_bookmark, reload

    # Relationship
    bookmark: Mapped["Bookmark"] = relationship("Bookmark", back_populates="visits")

    __table_args__ = (
        Index('ix_bookmark_visits_bookmark_id', 'bookmark_id'),
        Index('ix_bookmark_visits_visited_at', 'visited_at'),
        Index('ix_bookmark_visits_source_type', 'source_type'),
        UniqueConstraint('bookmark_id', 'visited_at', 'source_type', name='uq_bookmark_visit'),
    )

    def __repr__(self):
        return f"<BookmarkVisit(bookmark_id={self.bookmark_id}, at={self.visited_at})>"


class BookmarkMedia(Base):
    """
    Media metadata for bookmarks.

    One-to-one with Bookmark. Stores platform-specific media information
    (YouTube videos, Spotify tracks, ArXiv papers, etc.).
    """
    __tablename__ = 'bookmark_media'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bookmarks.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    media_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # video, audio, document, image
    media_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # youtube, spotify, arxiv
    media_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # Platform-specific ID
    author_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    author_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship
    bookmark: Mapped["Bookmark"] = relationship("Bookmark", back_populates="media")

    __table_args__ = (
        Index('ix_bookmark_media_bookmark_id', 'bookmark_id'),
        Index('ix_bookmark_media_source', 'media_source'),
    )

    def __repr__(self):
        return f"<BookmarkMedia(bookmark_id={self.bookmark_id}, type={self.media_type})>"


class ViewDefinition(Base):
    """
    Stored view definitions.

    Views can come from: built-in defaults, YAML files, or the DB.
    DB-stored views enable AI-generated views and user saves via CLI.
    Load order: built-ins → DB → YAML (YAML wins on name conflict).
    """
    __tablename__ = 'views'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)  # Same dict structure as YAML views
    created_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # user, ai, system
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<ViewDefinition(name='{self.name}')>"


class SchemaVersion(Base):
    """
    Lightweight schema versioning — no Alembic needed for a personal CLI tool.

    Each row records a migration that has been applied.
    """
    __tablename__ = 'schema_version'

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self):
        return f"<SchemaVersion(version={self.version})>"


class Tag(Base):
    """
    Tag model for categorizing bookmarks.

    Supports hierarchical tags using path notation (e.g., 'programming/python/web').
    """
    __tablename__ = 'tags'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    bookmarks: Mapped[List["Bookmark"]] = relationship(
        "Bookmark",
        secondary=bookmark_tags,
        back_populates="tags",
        lazy="dynamic"
    )

    @hybrid_property
    def bookmark_count(self) -> int:
        return self.bookmarks.count()

    @hybrid_property
    def hierarchy_level(self) -> int:
        return self.name.count('/')

    @hybrid_property
    def parent_path(self) -> Optional[str]:
        if '/' not in self.name:
            return None
        return '/'.join(self.name.split('/')[:-1])

    @hybrid_property
    def leaf_name(self) -> str:
        return self.name.split('/')[-1]

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"


class BookmarkHealth(Base):
    """Health metrics for bookmarks."""
    __tablename__ = 'bookmark_health'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bookmarks.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    last_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    redirect_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)

    bookmark: Mapped["Bookmark"] = relationship("Bookmark", backref="health", uselist=False)

    def calculate_health_score(self) -> float:
        score = 100.0
        if self.status_code:
            if self.status_code >= 400:
                score -= 50
            elif self.status_code >= 300:
                score -= 10
        if self.response_time_ms:
            if self.response_time_ms > 5000:
                score -= 20
            elif self.response_time_ms > 2000:
                score -= 10
        if self.last_check:
            days_old = (datetime.now(timezone.utc) - self.last_check).days
            if days_old > 30:
                score -= min(20, days_old - 30)
        return max(0, min(100, score))

    def __repr__(self):
        return f"<BookmarkHealth(bookmark_id={self.bookmark_id}, score={self.health_score})>"


class Collection(Base):
    """
    Collections for organizing bookmarks into groups.

    Similar to folders but more flexible — bookmarks can be in multiple collections.
    """
    __tablename__ = 'collections'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    icon: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # emoji or icon name
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # display ordering

    auto_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Collection(id={self.id}, name='{self.name}')>"


class ContentCache(Base):
    """
    Cached content for bookmarks.

    Stores both raw HTML (compressed) and markdown version for offline viewing,
    archival, and full-text search capabilities.
    """
    __tablename__ = 'content_cache'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bookmarks.id', ondelete='CASCADE'),
        unique=True,
        nullable=False,
        index=True
    )

    html_content: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compressed_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    encoding: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Long Echo Preservation Fields
    thumbnail_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    thumbnail_mime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    thumbnail_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transcript_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preservation_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    preserved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    bookmark: Mapped["Bookmark"] = relationship("Bookmark", back_populates="content_cache", uselist=False)

    @property
    def compression_ratio(self) -> float:
        if self.content_length == 0:
            return 0.0
        return (1 - self.compressed_size / self.content_length) * 100

    def __repr__(self):
        return f"<ContentCache(bookmark_id={self.bookmark_id}, size={self.content_length}, compressed={self.compressed_size})>"


class Event(Base):
    """Event log for tracking all operations in BTK."""
    __tablename__ = 'events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    entity_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index('ix_events_entity', 'entity_type', 'entity_id'),
        Index('ix_events_timestamp_desc', timestamp.desc()),
    )

    def __repr__(self):
        return f"<Event(id={self.id}, type='{self.event_type}', entity={self.entity_type}:{self.entity_id})>"


# Association table for bookmark collections — with position for ordering
bookmark_collections = Table(
    'bookmark_collections',
    Base.metadata,
    Column('bookmark_id', Integer, ForeignKey('bookmarks.id', ondelete='CASCADE'), primary_key=True),
    Column('collection_id', Integer, ForeignKey('collections.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column('position', Integer, default=0),
    Index('ix_bookmark_collections_bookmark_id', 'bookmark_id'),
    Index('ix_bookmark_collections_collection_id', 'collection_id')
)


# Wire up Collection <-> Bookmark relationship
Bookmark.collections = relationship(
    "Collection",
    secondary=bookmark_collections,
    backref="bookmarks",
    lazy="selectin"
)
