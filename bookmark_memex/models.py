"""ORM models for bookmark-memex.

Uses SQLAlchemy 2.0 declarative style (Mapped / mapped_column).

Key design decisions:
- Soft delete on Bookmark, ContentCache, and Marginalia via ``archived_at``.
- Marginalia.bookmark_id uses ON DELETE SET NULL so marginalia survive
  bookmark deletion (orphan survival).
- bookmark_tags junction cascades DELETE on both FK sides.
- Bookmark.tags loaded with ``lazy="selectin"`` for efficient retrieval.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Table,
    Text,
    Column,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from bookmark_memex.uri import build_bookmark_uri, build_marginalia_uri


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (for SQLite compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Junction table: bookmark_tags
# ---------------------------------------------------------------------------

bookmark_tags = Table(
    "bookmark_tags",
    Base.metadata,
    Column(
        "bookmark_id",
        Integer,
        ForeignKey("bookmarks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_bookmark_tags_tag_id", "tag_id"),
)


# ---------------------------------------------------------------------------
# Bookmark
# ---------------------------------------------------------------------------


class Bookmark(Base):
    """A single bookmarked URL."""

    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unique_id: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(
        String(2048), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bookmark_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="bookmark", index=True
    )

    added: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    last_visited: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reachable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    favicon_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    favicon_mime_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    media: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )

    # Relationships
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary=bookmark_tags,
        back_populates="bookmarks",
        lazy="selectin",
    )
    sources: Mapped[List["BookmarkSource"]] = relationship(
        "BookmarkSource",
        back_populates="bookmark",
        cascade="all, delete-orphan",
        order_by="BookmarkSource.imported_at.desc()",
    )
    content_cache: Mapped[Optional["ContentCache"]] = relationship(
        "ContentCache",
        back_populates="bookmark",
        cascade="all, delete-orphan",
        uselist=False,
    )
    marginalia: Mapped[List["Marginalia"]] = relationship(
        "Marginalia",
        back_populates="bookmark",
        foreign_keys="Marginalia.bookmark_id",
        # No cascade delete — marginalia survive via ON DELETE SET NULL.
    )

    __table_args__ = (
        Index("ix_bookmarks_added_desc", "added"),
    )

    # ------------------------------------------------------------------
    # Hybrid properties
    # ------------------------------------------------------------------

    @hybrid_property
    def uri(self) -> str:
        return build_bookmark_uri(self.unique_id)

    @hybrid_property
    def domain(self) -> str:
        return urlparse(self.url).netloc

    @hybrid_property
    def tag_names(self) -> List[str]:
        return [t.name for t in self.tags]

    def __repr__(self) -> str:
        return f"<Bookmark id={self.id!r} title={self.title!r}>"


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------


class Tag(Base):
    """A hierarchical tag.  Path separator is ``/``."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    bookmarks: Mapped[List["Bookmark"]] = relationship(
        "Bookmark",
        secondary=bookmark_tags,
        back_populates="tags",
        lazy="dynamic",
    )

    # ------------------------------------------------------------------
    # Hybrid properties
    # ------------------------------------------------------------------

    @hybrid_property
    def hierarchy_level(self) -> int:
        """Number of ``/`` separators in the tag name (root = 0)."""
        return self.name.count("/")

    @hybrid_property
    def parent_path(self) -> Optional[str]:
        """Path of the parent tag, or ``None`` for root tags."""
        parts = self.name.rsplit("/", 1)
        return parts[0] if len(parts) == 2 else None

    @hybrid_property
    def leaf_name(self) -> str:
        """The last component after the final ``/``."""
        return self.name.rsplit("/", 1)[-1]

    def __repr__(self) -> str:
        return f"<Tag id={self.id!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# BookmarkSource
# ---------------------------------------------------------------------------


class BookmarkSource(Base):
    """Records where a bookmark was imported from (supports multiple origins)."""

    __tablename__ = "bookmark_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bookmarks.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    folder_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    bookmark: Mapped["Bookmark"] = relationship("Bookmark", back_populates="sources")

    __table_args__ = (
        Index("ix_bookmark_sources_bookmark_id", "bookmark_id"),
        Index("ix_bookmark_sources_source_type", "source_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<BookmarkSource id={self.id!r} bookmark_id={self.bookmark_id!r}"
            f" source_type={self.source_type!r}>"
        )


# ---------------------------------------------------------------------------
# ContentCache
# ---------------------------------------------------------------------------


class ContentCache(Base):
    """Cached web content for a bookmark (one-to-one)."""

    __tablename__ = "content_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bookmarks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    html_content: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compressed_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    bookmark: Mapped["Bookmark"] = relationship(
        "Bookmark", back_populates="content_cache"
    )

    def __repr__(self) -> str:
        return (
            f"<ContentCache id={self.id!r} bookmark_id={self.bookmark_id!r}"
            f" content_length={self.content_length!r}>"
        )


# ---------------------------------------------------------------------------
# Marginalia
# ---------------------------------------------------------------------------


class Marginalia(Base):
    """A free-form note attachable to any bookmark.

    Uses ``ON DELETE SET NULL`` on ``bookmark_id`` so marginalia survive
    bookmark deletion (orphan survival per the ecosystem contract).

    Called "marginalia" across the ``*-memex`` ecosystem — the metaphor
    is handwritten notes in the margin of a book, generalised to
    notes-on-anything.
    """

    __tablename__ = "marginalia"

    # UUID hex string — durable, survives re-imports
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    bookmark_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("bookmarks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    bookmark: Mapped[Optional["Bookmark"]] = relationship(
        "Bookmark",
        back_populates="marginalia",
        foreign_keys=[bookmark_id],
    )

    @hybrid_property
    def uri(self) -> str:
        return build_marginalia_uri(self.id)

    def __repr__(self) -> str:
        return (
            f"<Marginalia id={self.id!r} bookmark_id={self.bookmark_id!r}>"
        )


# Backwards-compat alias for callers that still import ``Annotation``.
# Deprecated; will be removed once the ecosystem has fully migrated.
Annotation = Marginalia


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class Event(Base):
    """Append-only event log for auditing and replaying mutations."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, index=True
    )
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_events_entity_type_id", "entity_type", "entity_id"),
        Index("ix_events_timestamp_desc", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<Event id={self.id!r} event_type={self.event_type!r}"
            f" entity_type={self.entity_type!r} entity_id={self.entity_id!r}>"
        )


# ---------------------------------------------------------------------------
# SchemaVersion
# ---------------------------------------------------------------------------


class SchemaVersion(Base):
    """Tracks applied schema migrations."""

    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<SchemaVersion version={self.version!r}>"
