"""
SQLAlchemy models for BTK bookmark management.

This module defines the database schema for bookmarks, tags, and their relationships.
Following best practices with proper indexes, constraints, and relationships.
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

    Attributes:
        id: Primary key
        unique_id: 8-character SHA-256 hash for external references
        url: The bookmark URL (indexed for fast lookups)
        title: Bookmark title
        description: Optional description
        added: Timestamp when bookmark was added
        last_visited: Last visit timestamp
        visit_count: Number of times visited
        stars: Whether bookmark is starred/favorited
        reachable: Whether URL is reachable (nullable for unchecked)
        favicon_path: Local path to favicon file
        extra_data: JSON field for additional flexible data

    Media Attributes (nullable, only for media bookmarks):
        media_type: Type of media (video, audio, document, image)
        media_source: Platform source (youtube, spotify, arxiv, etc.)
        media_id: Platform-specific identifier
        author_name: Content creator/channel name
        author_url: URL to creator's profile/channel
        thumbnail_url: URL to thumbnail image
        published_at: Original publication date
    """
    __tablename__ = 'bookmarks'

    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unique_id: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default='')

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

    # Favicon storage (both path and blob for backward compatibility and flexibility)
    favicon_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    favicon_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # Store favicon as BLOB
    favicon_mime_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # e.g., 'image/png'

    # Flexible metadata storage for additional fields
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    # Media metadata (nullable - only populated for media bookmarks)
    media_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # video, audio, document, image
    media_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # youtube, spotify, arxiv
    media_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # Platform-specific ID
    author_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # Content creator name
    author_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)  # Creator profile URL
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)  # Thumbnail image URL
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )  # Original publication date

    # Relationships
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary=bookmark_tags,
        back_populates="bookmarks",
        lazy="selectin"  # Eager load tags to avoid N+1 queries
    )
    content_cache: Mapped[Optional["ContentCache"]] = relationship(
        "ContentCache",
        back_populates="bookmark",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Indexes for common queries
    __table_args__ = (
        Index('ix_bookmarks_url_title', 'url', 'title'),  # Composite index for search
        Index('ix_bookmarks_added_desc', added.desc()),  # For recent bookmarks
        Index('ix_bookmarks_visit_count_desc', visit_count.desc()),  # For popular bookmarks
        UniqueConstraint('url', name='uq_bookmarks_url'),  # Ensure URL uniqueness
    )

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


class Tag(Base):
    """
    Tag model for categorizing bookmarks.

    Supports hierarchical tags using path notation (e.g., 'programming/python/web').
    """
    __tablename__ = 'tags'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color code

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    bookmarks: Mapped[List["Bookmark"]] = relationship(
        "Bookmark",
        secondary=bookmark_tags,
        back_populates="tags",
        lazy="dynamic"  # Use dynamic loading for large collections
    )

    @hybrid_property
    def bookmark_count(self) -> int:
        """Count of bookmarks with this tag."""
        return self.bookmarks.count()

    @hybrid_property
    def hierarchy_level(self) -> int:
        """Get the hierarchy level based on tag path separators."""
        return self.name.count('/')

    @hybrid_property
    def parent_path(self) -> Optional[str]:
        """Get parent tag path for hierarchical tags."""
        if '/' not in self.name:
            return None
        return '/'.join(self.name.split('/')[:-1])

    @hybrid_property
    def leaf_name(self) -> str:
        """Get the leaf name without parent path."""
        return self.name.split('/')[-1]

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"


class BookmarkHealth(Base):
    """
    Health metrics for bookmarks.

    Tracks URL reachability, content changes, and other health indicators.
    """
    __tablename__ = 'bookmark_health'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('bookmarks.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    # Health checks
    last_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    redirect_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Health score (0-100)
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)

    # Relationship
    bookmark: Mapped["Bookmark"] = relationship("Bookmark", backref="health", uselist=False)

    def calculate_health_score(self) -> float:
        """
        Calculate health score based on various factors.
        """
        score = 100.0

        # Deduct for bad status codes
        if self.status_code:
            if self.status_code >= 400:
                score -= 50
            elif self.status_code >= 300:
                score -= 10

        # Deduct for slow response
        if self.response_time_ms:
            if self.response_time_ms > 5000:
                score -= 20
            elif self.response_time_ms > 2000:
                score -= 10

        # Deduct for stale checks
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

    Similar to folders but more flexible - bookmarks can be in multiple collections.
    """
    __tablename__ = 'collections'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Auto-collection rules (JMESPath query)
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

    Long Echo preservation fields store thumbnails, transcripts, and other
    representations that survive even when the original URL is gone.
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

    # Content storage
    html_content: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # Compressed HTML
    markdown_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Converted for CLI/search

    # Metadata
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA256 for change detection
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Original size before compression
    compressed_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Size after compression
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Content type and encoding
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    encoding: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # ==========================================================================
    # Long Echo Preservation Fields
    # ==========================================================================

    # Thumbnail/Screenshot - visual representation of the content
    thumbnail_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    thumbnail_mime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # image/jpeg, image/png
    thumbnail_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Transcript - for videos, podcasts, audio content
    transcript_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extracted text - for PDFs and other documents
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Preservation metadata
    preservation_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # youtube, pdf, screenshot, etc.
    preserved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship
    bookmark: Mapped["Bookmark"] = relationship("Bookmark", back_populates="content_cache", uselist=False)

    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.content_length == 0:
            return 0.0
        return (1 - self.compressed_size / self.content_length) * 100

    def __repr__(self):
        return f"<ContentCache(bookmark_id={self.bookmark_id}, size={self.content_length}, compressed={self.compressed_size})>"


class Event(Base):
    """
    Event log for tracking all operations in BTK.

    Provides a full audit trail of bookmark activities for:
    - Activity feeds (recent activity)
    - Debugging and troubleshooting
    - Undo capabilities (future)
    - Analytics and insights

    Event types:
        bookmark_added, bookmark_updated, bookmark_deleted
        bookmark_visited, bookmark_starred, bookmark_unstarred
        bookmark_archived, bookmark_unarchived, bookmark_pinned
        tag_added, tag_removed, tag_renamed
        content_fetched, content_preserved
        health_checked
        queue_added, queue_removed, queue_completed
        import_completed, export_completed
    """
    __tablename__ = 'events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Event classification
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # bookmark, tag, collection

    # Entity reference (nullable for deletions where entity no longer exists)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    entity_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)  # Preserve URL even after deletion

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Flexible data for event-specific details
    # Examples: {"old_title": "...", "new_title": "..."} for updates
    #           {"tags": ["ai", "ml"]} for tag_added
    #           {"count": 50} for import_completed
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Composite index for efficient entity lookups
    __table_args__ = (
        Index('ix_events_entity', 'entity_type', 'entity_id'),
        Index('ix_events_timestamp_desc', timestamp.desc()),
    )

    def __repr__(self):
        return f"<Event(id={self.id}, type='{self.event_type}', entity={self.entity_type}:{self.entity_id})>"


# Association table for bookmark collections
bookmark_collections = Table(
    'bookmark_collections',
    Base.metadata,
    Column('bookmark_id', Integer, ForeignKey('bookmarks.id', ondelete='CASCADE'), primary_key=True),
    Column('collection_id', Integer, ForeignKey('collections.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Index('ix_bookmark_collections_bookmark_id', 'bookmark_id'),
    Index('ix_bookmark_collections_collection_id', 'collection_id')
)


# Update relationships
Bookmark.collections = relationship(
    "Collection",
    secondary=bookmark_collections,
    backref="bookmarks",
    lazy="selectin"
)