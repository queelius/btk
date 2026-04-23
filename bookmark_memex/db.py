"""Database layer for bookmark-memex.

Provides :class:`Database`, a thin façade over SQLAlchemy 2.0 that implements
the full CRUD contract required by the archive ecosystem.

URL normalisation and unique-ID derivation live here so that every code path
that touches bookmark identity uses the same logic.
"""

from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional
from urllib.parse import urlencode, parse_qsl, urlparse, urlunparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from bookmark_memex.models import (
    Annotation,
    Base,
    Bookmark,
    BookmarkSource,
    Event,
    Tag,
    bookmark_tags,
)
from bookmark_memex.soft_delete import archive, hard_delete, restore, filter_active


# ---------------------------------------------------------------------------
# URL utilities (public so tests can exercise them directly)
# ---------------------------------------------------------------------------


def normalize_url(url: str) -> str:
    """Return a canonical form of *url* for deduplication purposes.

    Normalisation steps:
    - Lowercase scheme and host.
    - Remove default ports (:80 for http, :443 for https).
    - Sort query parameters.
    - Strip trailing slash from path (but keep "/" for root).
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default ports.
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Sort query parameters for canonical representation.
    query = urlencode(sorted(parse_qsl(parsed.query)))

    # Strip trailing slash from path, but always keep root slash.
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def generate_unique_id(url: str) -> str:
    """Return the first 16 hex characters of sha256(normalize(url))."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _eager_load_bookmark(session: Session, bm: Bookmark) -> Bookmark:
    """Access all lazy relationships while *bm* is still bound to *session*.

    SQLAlchemy ``expire_on_commit=False`` keeps attribute values after commit,
    but lazy relationships that were never loaded still require a live session.
    Accessing them here forces the load before the session closes.
    """
    _ = bm.tags
    _ = bm.sources
    _ = bm.annotations
    _ = bm.content_cache
    return bm


def _get_or_create_tag(session: Session, name: str) -> Tag:
    """Return the Tag with *name*, creating it if it does not yet exist."""
    tag = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name)
        session.add(tag)
        session.flush()  # populate tag.id without committing
    return tag


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------


class Database:
    """Single-file SQLite bookmark store.

    All methods open and commit their own session.  No session is shared
    across calls.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        self._Session = sessionmaker(bind=engine, expire_on_commit=False)

    # ------------------------------------------------------------------
    # Session helper
    # ------------------------------------------------------------------

    @contextmanager
    def _session(self) -> Generator[Session, None, None]:
        """Yield a Session, committing on clean exit, rolling back on error."""
        s = self._Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        url: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        starred: bool = False,
        pinned: bool = False,
        bookmark_type: str = "bookmark",
        source_type: Optional[str] = None,
        source_name: Optional[str] = None,
        folder_path: Optional[str] = None,
    ) -> Bookmark:
        """Add a bookmark, returning the new or existing row.

        If a bookmark with the same normalised URL already exists:
        - New tags from *tags* are merged into the existing set.
        - If the existing title is empty/None and *title* is provided, the
          title is updated.
        - A new :class:`BookmarkSource` is appended when *source_type* is set.
        """
        unique_id = generate_unique_id(url)
        norm = normalize_url(url)
        title = title or ""

        with self._session() as s:
            existing = s.execute(
                select(Bookmark).where(Bookmark.unique_id == unique_id)
            ).scalar_one_or_none()

            if existing is not None:
                # Merge tags.
                if tags:
                    existing_names = {t.name for t in existing.tags}
                    for tag_name in tags:
                        if tag_name not in existing_names:
                            existing.tags.append(_get_or_create_tag(s, tag_name))

                # Fill in title if currently empty.
                if title and not existing.title:
                    existing.title = title

                # Record additional source.
                if source_type:
                    src = BookmarkSource(
                        bookmark_id=existing.id,
                        source_type=source_type,
                        source_name=source_name,
                        folder_path=folder_path,
                        imported_at=_utcnow(),
                    )
                    s.add(src)

                s.flush()
                s.refresh(existing)
                return _eager_load_bookmark(s, existing)

            # --- New bookmark ---
            bm = Bookmark(
                unique_id=unique_id,
                url=norm,
                title=title,
                description=description,
                bookmark_type=bookmark_type,
                starred=starred,
                pinned=pinned,
                added=_utcnow(),
                visit_count=0,
            )
            s.add(bm)
            s.flush()  # populate bm.id

            if tags:
                for tag_name in tags:
                    bm.tags.append(_get_or_create_tag(s, tag_name))

            if source_type:
                src = BookmarkSource(
                    bookmark_id=bm.id,
                    source_type=source_type,
                    source_name=source_name,
                    folder_path=folder_path,
                    imported_at=_utcnow(),
                )
                s.add(src)

            s.flush()
            s.refresh(bm)
            return _eager_load_bookmark(s, bm)

    def get(
        self,
        bookmark_id: int,
        *,
        include_archived: bool = False,
    ) -> Optional[Bookmark]:
        """Return bookmark by primary-key id, or *None* if not found."""
        with self._session() as s:
            q = select(Bookmark).where(Bookmark.id == bookmark_id)
            if not include_archived:
                q = q.where(Bookmark.archived_at.is_(None))
            bm = s.execute(q).scalar_one_or_none()
            return _eager_load_bookmark(s, bm) if bm is not None else None

    def get_by_unique_id(
        self,
        unique_id: str,
        *,
        include_archived: bool = False,
    ) -> Optional[Bookmark]:
        """Return bookmark by unique_id, or *None* if not found."""
        with self._session() as s:
            q = select(Bookmark).where(Bookmark.unique_id == unique_id)
            if not include_archived:
                q = q.where(Bookmark.archived_at.is_(None))
            bm = s.execute(q).scalar_one_or_none()
            return _eager_load_bookmark(s, bm) if bm is not None else None

    def update(self, bookmark_id: int, **kwargs: Any) -> Optional[Bookmark]:
        """Update fields on bookmark *bookmark_id*.  Returns updated row or *None*."""
        with self._session() as s:
            bm = s.get(Bookmark, bookmark_id)
            if bm is None:
                return None
            for key, value in kwargs.items():
                setattr(bm, key, value)
            s.flush()
            s.refresh(bm)
            return _eager_load_bookmark(s, bm)

    def visit(self, bookmark_id: int) -> None:
        """Increment visit_count and set last_visited to now."""
        with self._session() as s:
            bm = s.get(Bookmark, bookmark_id)
            if bm is not None:
                bm.visit_count = (bm.visit_count or 0) + 1
                bm.last_visited = _utcnow()

    def delete(self, bookmark_id: int, *, hard: bool = False) -> None:
        """Delete bookmark.  Soft delete by default; pass hard=True for physical delete."""
        with self._session() as s:
            bm = s.get(Bookmark, bookmark_id)
            if bm is None:
                return
            if hard:
                hard_delete(s, bm)
            else:
                archive(s, bm)

    def restore(self, bookmark_id: int) -> None:
        """Clear archived_at on a soft-deleted bookmark."""
        with self._session() as s:
            bm = s.get(Bookmark, bookmark_id)
            if bm is not None:
                restore(s, bm)

    def list(
        self,
        *,
        include_archived: bool = False,
        limit: Optional[int] = None,
    ) -> list[Bookmark]:
        """Return all bookmarks ordered by added DESC."""
        with self._session() as s:
            q = select(Bookmark).order_by(Bookmark.added.desc())
            if not include_archived:
                q = q.where(Bookmark.archived_at.is_(None))
            if limit is not None:
                q = q.limit(limit)
            bms = list(s.execute(q).scalars().all())
            for bm in bms:
                _eager_load_bookmark(s, bm)
            return bms

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def tag(
        self,
        bookmark_id: int,
        *,
        add: Optional[list[str]] = None,
        remove: Optional[list[str]] = None,
    ) -> None:
        """Add and/or remove tags on bookmark *bookmark_id*."""
        with self._session() as s:
            bm = s.get(Bookmark, bookmark_id)
            if bm is None:
                return

            if add:
                existing_names = {t.name for t in bm.tags}
                for name in add:
                    if name not in existing_names:
                        bm.tags.append(_get_or_create_tag(s, name))

            if remove:
                to_remove = {t for t in bm.tags if t.name in remove}
                for t in to_remove:
                    bm.tags.remove(t)

    def list_tags(self) -> list[Tag]:
        """Return all tags ordered by name."""
        with self._session() as s:
            return list(s.execute(select(Tag).order_by(Tag.name)).scalars().all())

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------

    def annotate(self, bookmark_unique_id: str, text: str) -> Annotation:
        """Create and return an Annotation linked to the bookmark with *bookmark_unique_id*."""
        with self._session() as s:
            bm = s.execute(
                select(Bookmark).where(Bookmark.unique_id == bookmark_unique_id)
            ).scalar_one_or_none()

            bookmark_id = bm.id if bm is not None else None
            ann = Annotation(
                id=uuid.uuid4().hex,
                bookmark_id=bookmark_id,
                text=text,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            s.add(ann)
            s.flush()
            s.refresh(ann)
            return ann

    def merge_annotation(
        self,
        uuid: str,
        bookmark_unique_id: Optional[str],
        text: str,
        *,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> bool:
        """INSERT OR IGNORE an annotation keyed by its UUID.

        Used by the arkiv importer to round-trip annotations without
        duplicating them on repeated imports. If the UUID already exists,
        the existing annotation is preserved unchanged and this method
        returns ``False``. If the UUID is new, the annotation is created
        and returns ``True``.

        *bookmark_unique_id* may be ``None`` (for orphaned annotations
        whose parent bookmark was deleted). If it is set but does not
        match any live bookmark, the annotation is still created but
        ``bookmark_id`` is left NULL (orphan) — this matches the
        ``ON DELETE SET NULL`` orphan-survival contract.
        """
        now = _utcnow()
        with self._session() as s:
            existing = s.get(Annotation, uuid)
            if existing is not None:
                return False

            bookmark_id: Optional[int] = None
            if bookmark_unique_id is not None:
                bm = s.execute(
                    select(Bookmark).where(
                        Bookmark.unique_id == bookmark_unique_id
                    )
                ).scalar_one_or_none()
                if bm is not None:
                    bookmark_id = bm.id

            ann = Annotation(
                id=uuid,
                bookmark_id=bookmark_id,
                text=text,
                created_at=created_at or now,
                updated_at=updated_at or created_at or now,
            )
            s.add(ann)
            s.flush()
            return True

    def get_annotations(self, bookmark_unique_id: str) -> list[Annotation]:
        """Return all annotations for the bookmark identified by *bookmark_unique_id*."""
        with self._session() as s:
            bm = s.execute(
                select(Bookmark).where(Bookmark.unique_id == bookmark_unique_id)
            ).scalar_one_or_none()
            if bm is None:
                return []
            anns = s.execute(
                select(Annotation)
                .where(Annotation.bookmark_id == bm.id)
                .order_by(Annotation.created_at)
            ).scalars().all()
            return list(anns)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def log_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> None:
        """Append an event to the audit log."""
        with self._session() as s:
            ev = Event(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                timestamp=_utcnow(),
                event_data=data,
            )
            s.add(ev)
