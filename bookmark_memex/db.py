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

from sqlalchemy import create_engine, insert as sa_insert, select
from sqlalchemy.orm import Session, sessionmaker

from bookmark_memex.models import (
    Marginalia,
    Base,
    Bookmark,
    BookmarkSource,
    Event,
    HistoryUrl,
    HistoryVisit,
    Tag,
    bookmark_tags,
)
from bookmark_memex.soft_delete import archive, hard_delete, restore, filter_active


# ---------------------------------------------------------------------------
# Pre-create migrations
# ---------------------------------------------------------------------------


def _apply_rename_annotations_to_marginalia(engine) -> None:
    """Rename legacy ``annotations`` / ``annotations_fts`` tables in place.

    Run once on first open of a pre-rename database. Idempotent: safe to
    re-run, and a fresh database (no legacy tables) is a no-op.

    Schema is otherwise identical — same columns, indexes, and FK targets —
    so ``ALTER TABLE ... RENAME TO`` preserves data and indexes intact.
    The FTS5 shadow table is dropped and will be recreated by the FTS
    bootstrap on first use (it is a derived index, not a source of truth).
    """
    with engine.begin() as conn:
        from sqlalchemy import text

        names = {
            r[0] for r in conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('annotations', 'marginalia', "
                    "             'annotations_fts', 'marginalia_fts')"
                )
            )
        }

        if "annotations" in names and "marginalia" not in names:
            conn.execute(text("ALTER TABLE annotations RENAME TO marginalia"))

        # Legacy FTS5 shadow: drop if it exists; the FTS bootstrap will
        # recreate a fresh one under the new name the next time it runs.
        if "annotations_fts" in names:
            conn.execute(text("DROP TABLE IF EXISTS annotations_fts"))


def _apply_add_marginalia_history_cols(engine) -> None:
    """Add history-record FK columns to an existing ``marginalia`` table.

    Run once on first open of a database that predates history-capture.
    Idempotent: inspects ``PRAGMA table_info`` and only adds columns that
    are missing. A fresh database already has the columns via
    ``Base.metadata.create_all``, so this is a no-op there.
    """
    with engine.begin() as conn:
        from sqlalchemy import text

        table_exists = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='marginalia'"
            )
        ).first()
        if not table_exists:
            return

        cols = {
            row[1]  # second column is the name
            for row in conn.execute(text("PRAGMA table_info(marginalia)"))
        }

        if "history_url_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE marginalia ADD COLUMN history_url_id INTEGER "
                    "REFERENCES history_urls(id) ON DELETE SET NULL"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_marginalia_history_url_id "
                    "ON marginalia(history_url_id)"
                )
            )

        if "history_visit_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE marginalia ADD COLUMN history_visit_id INTEGER "
                    "REFERENCES history_visits(id) ON DELETE SET NULL"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_marginalia_history_visit_id "
                    "ON marginalia(history_visit_id)"
                )
            )


def _install_history_triggers(engine) -> None:
    """Install SQL triggers that maintain ``history_urls`` aggregates.

    ``visit_count``, ``first_visited`` and ``last_visited`` on history_urls
    are derived from history_visits. Rather than recompute in Python for
    every import, SQL triggers maintain the invariants on insert and
    delete. Idempotent via ``CREATE TRIGGER IF NOT EXISTS``.

    Notes:
    - We use ``COALESCE(..., NEW.visited_at)`` for the first insert when
      the aggregate columns are still NULL.
    - The delete trigger is best-effort: for soft delete (``archived_at``)
      we do NOT recompute, which is deliberate. ``visit_count`` is
      "lifetime observed visits", not "active visits". Hard delete does
      recompute via the delete trigger so hard-delete stays consistent.
    """
    with engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_history_visits_insert
                AFTER INSERT ON history_visits
                BEGIN
                    UPDATE history_urls
                    SET visit_count = visit_count + 1,
                        first_visited = CASE
                            WHEN first_visited IS NULL
                                 OR NEW.visited_at < first_visited
                            THEN NEW.visited_at
                            ELSE first_visited
                        END,
                        last_visited = CASE
                            WHEN last_visited IS NULL
                                 OR NEW.visited_at > last_visited
                            THEN NEW.visited_at
                            ELSE last_visited
                        END
                    WHERE id = NEW.url_id;
                END;
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_history_visits_delete
                AFTER DELETE ON history_visits
                BEGIN
                    UPDATE history_urls
                    SET visit_count = (
                            SELECT COUNT(*) FROM history_visits
                            WHERE url_id = OLD.url_id
                        ),
                        first_visited = (
                            SELECT MIN(visited_at) FROM history_visits
                            WHERE url_id = OLD.url_id
                        ),
                        last_visited = (
                            SELECT MAX(visited_at) FROM history_visits
                            WHERE url_id = OLD.url_id
                        )
                    WHERE id = OLD.url_id;
                END;
                """
            )
        )


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


# Tracking parameters stripped by :func:`normalize_url_for_history`.
# Kept as a module-level set so tests and callers can inspect or extend
# it without patching the function body.
_HISTORY_TRACKING_PARAMS: frozenset[str] = frozenset({
    # UTM (Google Analytics and friends)
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "utm_id", "utm_name", "utm_reader",
    # Ad-network click IDs
    "gclid", "gclsrc", "dclid", "fbclid", "msclkid", "yclid", "twclid",
    "mc_eid", "mc_cid",
    # HubSpot and similar
    "_hsenc", "_hsmi", "__hssc", "__hstc", "__hsfp",
    # Social sharing noise
    "ref", "ref_src", "ref_url", "igshid", "feature",
    # Generic share/session pollution
    "share", "shared", "sharedid",
})


def normalize_url_for_history(url: str) -> str:
    """Return a history-grade canonical form of *url*.

    Layered on top of :func:`normalize_url`: first strip common tracking
    parameters, then apply the standard normalisation. The intent is
    aggressive canonicalisation so that visits to the same page from ten
    different utm-tagged links collapse to a single ``history_urls`` row.

    Bookmarks use :func:`normalize_url` (no stripping) so the URL the
    user chose to save stays faithful. History uses this. They are
    deliberately different.
    """
    parsed = urlparse(url)

    params = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _HISTORY_TRACKING_PARAMS
    ]
    stripped = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(params),
        "",  # drop fragment; it is client-side anchor noise in history
    ))
    return normalize_url(stripped)


def generate_history_unique_id(url: str) -> str:
    """Return the first 16 hex characters of sha256(normalize_for_history(url))."""
    return hashlib.sha256(
        normalize_url_for_history(url).encode("utf-8")
    ).hexdigest()[:16]


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
    _ = bm.marginalia
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
        # PRAGMA tuning on every connection:
        #   foreign_keys=ON   : SQLite defaults to off; without this, our
        #                       ON DELETE CASCADE / SET NULL FKs become
        #                       no-ops. Required for correctness.
        #   journal_mode=WAL  : write-ahead-log. Batches fsyncs so bulk
        #                       imports (history: 30k+ visits) run in
        #                       seconds rather than minutes. DELETE
        #                       journalling is restored before HTML-SPA
        #                       export per the C6b durability rule.
        #   synchronous=NORMAL: safe under WAL; fsync only at checkpoints.
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        # Run pre-create migrations before metadata.create_all so the
        # ORM doesn't try to create a new marginalia table alongside the
        # still-present legacy annotations table.
        _apply_rename_annotations_to_marginalia(engine)
        Base.metadata.create_all(engine)
        # Post-create migrations (ALTERs and triggers that reference
        # tables the metadata pass has just ensured exist).
        _apply_add_marginalia_history_cols(engine)
        _install_history_triggers(engine)
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
    # Marginalia (free-form notes on bookmarks)
    # ------------------------------------------------------------------

    def add_marginalia(self, bookmark_unique_id: str, text: str) -> Marginalia:
        """Create a note attached to the bookmark with *bookmark_unique_id*.

        Returns the new :class:`Marginalia` row. If the bookmark does not
        exist, the note is still created but orphaned (bookmark_id is NULL).
        """
        with self._session() as s:
            bm = s.execute(
                select(Bookmark).where(Bookmark.unique_id == bookmark_unique_id)
            ).scalar_one_or_none()

            bookmark_id = bm.id if bm is not None else None
            note = Marginalia(
                id=uuid.uuid4().hex,
                bookmark_id=bookmark_id,
                text=text,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            s.add(note)
            s.flush()
            s.refresh(note)
            return note

    def update_marginalia(
        self, uuid: str, text: str
    ) -> Optional[Marginalia]:
        """Update the note's text and bump ``updated_at``.

        Returns the updated row, or ``None`` if no note with that UUID
        exists (including if it is soft-deleted).
        """
        with self._session() as s:
            note = s.get(Marginalia, uuid)
            if note is None or note.archived_at is not None:
                return None
            note.text = text
            note.updated_at = _utcnow()
            s.flush()
            s.refresh(note)
            return note

    def delete_marginalia(self, uuid: str, *, hard: bool = False) -> bool:
        """Delete a note.

        Soft-deletes by default (sets ``archived_at``); hard-deletes when
        ``hard=True``. Returns ``True`` if the note existed.
        """
        with self._session() as s:
            note = s.get(Marginalia, uuid)
            if note is None:
                return False
            if hard:
                s.delete(note)
            else:
                note.archived_at = _utcnow()
            s.flush()
            return True

    def restore_marginalia(self, uuid: str) -> bool:
        """Clear ``archived_at`` on a soft-deleted note.

        Returns ``True`` if a note was restored, ``False`` if no matching
        note existed or the note was already active.
        """
        with self._session() as s:
            note = s.get(Marginalia, uuid)
            if note is None or note.archived_at is None:
                return False
            note.archived_at = None
            note.updated_at = _utcnow()
            s.flush()
            return True

    def merge_marginalia(
        self,
        uuid: str,
        bookmark_unique_id: Optional[str],
        text: str,
        *,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> bool:
        """INSERT OR IGNORE a note keyed by its UUID.

        Used by the arkiv importer to round-trip notes without duplicating
        them on repeated imports. If the UUID already exists, the existing
        note is preserved unchanged and this method returns ``False``. If
        the UUID is new, the note is created and returns ``True``.

        *bookmark_unique_id* may be ``None`` (for orphaned notes whose
        parent bookmark was deleted). If it is set but does not match any
        live bookmark, the note is still created but ``bookmark_id`` is
        left NULL — matching the ``ON DELETE SET NULL`` orphan-survival
        contract.
        """
        now = _utcnow()
        with self._session() as s:
            existing = s.get(Marginalia, uuid)
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

            note = Marginalia(
                id=uuid,
                bookmark_id=bookmark_id,
                text=text,
                created_at=created_at or now,
                updated_at=updated_at or created_at or now,
            )
            s.add(note)
            s.flush()
            return True

    def list_marginalia(
        self,
        bookmark_unique_id: Optional[str] = None,
        *,
        include_archived: bool = False,
    ) -> list[Marginalia]:
        """Return active notes.

        If *bookmark_unique_id* is given, restrict to notes on that
        bookmark. Otherwise return every active note (orphans included).
        Pass ``include_archived=True`` to include soft-deleted rows.
        """
        with self._session() as s:
            q = select(Marginalia)
            if bookmark_unique_id is not None:
                bm = s.execute(
                    select(Bookmark).where(
                        Bookmark.unique_id == bookmark_unique_id
                    )
                ).scalar_one_or_none()
                if bm is None:
                    return []
                q = q.where(Marginalia.bookmark_id == bm.id)
            if not include_archived:
                q = q.where(Marginalia.archived_at.is_(None))
            q = q.order_by(Marginalia.created_at)
            return list(s.execute(q).scalars().all())

    # -- Backwards-compat aliases (deprecated; callers should migrate) -----

    def annotate(self, bookmark_unique_id: str, text: str) -> Marginalia:
        """Deprecated alias for :meth:`add_marginalia`."""
        return self.add_marginalia(bookmark_unique_id, text)

    def merge_annotation(self, *args, **kwargs) -> bool:
        """Deprecated alias for :meth:`merge_marginalia`."""
        return self.merge_marginalia(*args, **kwargs)

    def get_annotations(self, bookmark_unique_id: str) -> list[Marginalia]:
        """Deprecated alias for :meth:`list_marginalia`."""
        return self.list_marginalia(bookmark_unique_id)

    # ------------------------------------------------------------------
    # History: bulk ingestion
    # ------------------------------------------------------------------

    def bulk_ingest_history(
        self,
        entries: "list[dict[str, Any]]",
        *,
        source_type: str,
        source_name: str,
    ) -> "tuple[int, int, int, int, int]":
        """Bulk-insert history URLs and visits in a single transaction.

        Returns (urls_added, urls_updated, visits_added, visits_skipped,
        urls_seen) counts.

        *entries* is a list of dicts (same shape ``browser_history``
        readers produce). This path uses a single session for both the
        URL upsert pass and the visit insert pass, avoiding the 30k+
        fsyncs that a per-entry ``_session()`` would incur under
        WAL+NORMAL.

        Referrer chain (``from_visit_id``) is resolved at the end using
        a source-id -> our-id map accumulated during the visit pass.
        """
        from sqlalchemy import update as _update

        urls_added = 0
        urls_updated = 0
        urls_seen = 0
        visits_added = 0
        visits_skipped = 0

        url_id_cache: dict[str, int] = {}             # unique_id -> history_urls.id
        src_to_ours: dict[int, Optional[int]] = {}    # source visit_id -> our id
        pending_fv: list[tuple[int, int]] = []        # (our id, source from_visit)

        # Dialect-native INSERT OR IGNORE keeps the dedup clean without
        # raising IntegrityError: on conflict SQLite just skips the row
        # and reports 0 rowcount. The session stays usable and we don't
        # lose state from aborted flushes.
        visit_insert = sa_insert(HistoryVisit).prefix_with("OR IGNORE")

        with self._session() as s:
            for entry in entries:
                url = entry.get("url") or ""
                if not url.startswith(("http://", "https://")):
                    continue

                uid = generate_history_unique_id(url)
                cached = url_id_cache.get(uid)
                if cached is None:
                    existing = s.execute(
                        select(HistoryUrl).where(HistoryUrl.unique_id == uid)
                    ).scalar_one_or_none()
                    if existing is None:
                        hu = HistoryUrl(
                            unique_id=uid,
                            url=normalize_url_for_history(url),
                            title=entry.get("title"),
                            typed_count=int(entry.get("typed_count") or 0),
                        )
                        s.add(hu)
                        s.flush()
                        urls_added += 1
                    else:
                        hu = existing
                        if entry.get("title") and not hu.title:
                            hu.title = entry.get("title")
                        # typed_count is a source-side URL-level total;
                        # accept monotone increases across re-imports.
                        new_typed = int(entry.get("typed_count") or 0)
                        if new_typed > (hu.typed_count or 0):
                            hu.typed_count = new_typed
                        urls_updated += 1
                    url_id_cache[uid] = hu.id
                    urls_seen += 1
                    cached = hu.id

                vuuid = uuid.uuid4().hex
                res = s.connection().execute(
                    visit_insert,
                    [{
                        "unique_id": vuuid,
                        "url_id": cached,
                        "visited_at": entry["visited_at"],
                        "duration_ms": entry.get("duration_ms"),
                        "transition": entry.get("transition"),
                        "from_visit_id": None,
                        "source_type": source_type,
                        "source_name": source_name,
                        "imported_at": _utcnow(),
                    }],
                )

                inserted = res.rowcount == 1
                if inserted:
                    our_id = s.execute(
                        select(HistoryVisit.id).where(
                            HistoryVisit.unique_id == vuuid
                        )
                    ).scalar_one()
                    visits_added += 1
                else:
                    # Dedup hit: re-query by the UNIQUE tuple so referrer
                    # chains across re-imports still resolve.
                    our_id = s.execute(
                        select(HistoryVisit.id).where(
                            HistoryVisit.url_id == cached,
                            HistoryVisit.visited_at == entry["visited_at"],
                            HistoryVisit.source_type == source_type,
                            HistoryVisit.source_name == source_name,
                        )
                    ).scalar()
                    visits_skipped += 1

                if our_id is not None:
                    src_vid = int(entry.get("visit_id") or 0)
                    if src_vid:
                        src_to_ours[src_vid] = our_id
                    fv = int(entry.get("from_visit") or 0)
                    if fv and inserted:
                        pending_fv.append((our_id, fv))

            # Pass 2: resolve referrer chain within the same transaction.
            for our_id, src_from in pending_fv:
                mapped = src_to_ours.get(src_from)
                if mapped is None or mapped == our_id:
                    continue
                s.execute(
                    _update(HistoryVisit)
                    .where(HistoryVisit.id == our_id)
                    .values(from_visit_id=mapped)
                )

        return urls_added, urls_updated, visits_added, visits_skipped, urls_seen

    # ------------------------------------------------------------------
    # History: URLs
    # ------------------------------------------------------------------

    def upsert_history_url(
        self,
        url: str,
        *,
        title: Optional[str] = None,
        typed_count_delta: int = 0,
        media: Optional[dict] = None,
    ) -> tuple[HistoryUrl, bool]:
        """Insert or update a history_urls row.

        Returns:
            ``(row, created)`` where ``created`` is True iff the row did
            not previously exist.

        ``visit_count``, ``first_visited``, ``last_visited`` are NOT set
        here. They are maintained by the INSERT/DELETE triggers on
        ``history_visits``.
        """
        unique_id = generate_history_unique_id(url)
        norm = normalize_url_for_history(url)

        with self._session() as s:
            row = s.execute(
                select(HistoryUrl).where(HistoryUrl.unique_id == unique_id)
            ).scalar_one_or_none()

            created = False
            if row is None:
                row = HistoryUrl(
                    unique_id=unique_id,
                    url=norm,
                    title=title,
                    typed_count=max(0, typed_count_delta),
                    media=media,
                )
                s.add(row)
                s.flush()
                created = True
            else:
                if title and not row.title:
                    row.title = title
                if typed_count_delta:
                    row.typed_count = (row.typed_count or 0) + typed_count_delta
                if media and not row.media:
                    row.media = media
                s.flush()

            s.refresh(row)
            return row, created

    def get_history_url(self, history_url_id: int) -> Optional[HistoryUrl]:
        """Return a history_urls row by primary key, or None."""
        with self._session() as s:
            return s.get(HistoryUrl, history_url_id)

    def get_history_url_by_unique_id(self, unique_id: str) -> Optional[HistoryUrl]:
        """Return a history_urls row by unique_id, or None."""
        with self._session() as s:
            return s.execute(
                select(HistoryUrl).where(HistoryUrl.unique_id == unique_id)
            ).scalar_one_or_none()

    # ------------------------------------------------------------------
    # History: Visits
    # ------------------------------------------------------------------

    def add_history_visit(
        self,
        *,
        url_id: int,
        visited_at: datetime,
        source_type: str,
        source_name: str,
        duration_ms: Optional[int] = None,
        transition: Optional[str] = None,
        from_visit_id: Optional[int] = None,
    ) -> tuple[Optional[HistoryVisit], bool]:
        """Insert a visit event with dedup on
        ``UNIQUE(url_id, visited_at, source_type, source_name)``.

        Returns:
            ``(row, created)``. On a dedup hit ``created`` is False and
            ``row`` is the existing row. The dedup path issues a SELECT
            only when the INSERT conflicts, so clean inserts cost one
            statement.
        """
        vuuid = uuid.uuid4().hex
        with self._session() as s:
            from sqlalchemy.exc import IntegrityError

            row = HistoryVisit(
                unique_id=vuuid,
                url_id=url_id,
                visited_at=visited_at,
                duration_ms=duration_ms,
                transition=transition,
                from_visit_id=from_visit_id,
                source_type=source_type,
                source_name=source_name,
                imported_at=_utcnow(),
            )
            s.add(row)
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                # Re-query the conflicting row so callers can map
                # source-side IDs (e.g. Chrome's ``from_visit``) to our
                # primary keys even on re-imports.
                existing = s.execute(
                    select(HistoryVisit).where(
                        HistoryVisit.url_id == url_id,
                        HistoryVisit.visited_at == visited_at,
                        HistoryVisit.source_type == source_type,
                        HistoryVisit.source_name == source_name,
                    )
                ).scalar_one_or_none()
                return existing, False

            s.refresh(row)
            return row, True

    def get_history_visit(self, visit_id: int) -> Optional[HistoryVisit]:
        """Return a history_visits row by primary key, or None."""
        with self._session() as s:
            return s.get(HistoryVisit, visit_id)

    def get_history_visit_by_unique_id(
        self, unique_id: str
    ) -> Optional[HistoryVisit]:
        """Return a history_visits row by unique_id, or None."""
        with self._session() as s:
            return s.execute(
                select(HistoryVisit).where(HistoryVisit.unique_id == unique_id)
            ).scalar_one_or_none()

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
