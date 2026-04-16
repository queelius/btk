"""Tests for bookmark_memex.models ORM layer.

Uses an in-memory SQLite database — no external state needed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from bookmark_memex.models import (
    Annotation,
    Base,
    Bookmark,
    BookmarkSource,
    ContentCache,
    Event,
    SchemaVersion,
    Tag,
    bookmark_tags,
)
from bookmark_memex.uri import build_annotation_uri, build_bookmark_uri


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as sess:
        yield sess
        sess.rollback()


# ---------------------------------------------------------------------------
# Bookmark defaults
# ---------------------------------------------------------------------------


class TestBookmarkDefaults:
    def test_create_bookmark_minimal(self, session):
        bm = Bookmark(
            unique_id="a1b2c3d4e5f6a1b2",
            url="https://example.com",
            title="Example",
        )
        session.add(bm)
        session.flush()

        assert bm.id is not None
        assert bm.bookmark_type == "bookmark"
        assert bm.starred is False
        assert bm.pinned is False
        assert bm.visit_count == 0
        assert bm.archived_at is None
        assert bm.added is not None
        assert bm.reachable is None

    def test_added_is_set_automatically(self, session):
        bm = Bookmark(
            unique_id="aabbccddeeff0011",
            url="https://auto-time.example.com",
            title="Auto time",
        )
        session.add(bm)
        session.flush()
        assert isinstance(bm.added, datetime)

    def test_bookmark_type_defaults_to_bookmark(self, session):
        bm = Bookmark(
            unique_id="bb0011223344aabb",
            url="https://type-default.example.com",
            title="Type default",
        )
        session.add(bm)
        session.flush()
        assert bm.bookmark_type == "bookmark"

    def test_explicit_bookmark_type(self, session):
        bm = Bookmark(
            unique_id="cc1122334455bbcc",
            url="https://history.example.com",
            title="History entry",
            bookmark_type="history",
        )
        session.add(bm)
        session.flush()
        assert bm.bookmark_type == "history"


# ---------------------------------------------------------------------------
# Bookmark URI and domain hybrid properties
# ---------------------------------------------------------------------------


class TestBookmarkProperties:
    def test_uri_property(self, session):
        uid = "d1e2f3a4b5c6d1e2"
        bm = Bookmark(unique_id=uid, url="https://props.example.com", title="Props")
        session.add(bm)
        session.flush()
        assert bm.uri == build_bookmark_uri(uid)
        assert bm.uri == f"bookmark-memex://bookmark/{uid}"

    def test_domain_property(self, session):
        bm = Bookmark(
            unique_id="e2f3a4b5c6d1e2f3",
            url="https://docs.python.org/3/library/index.html",
            title="Python Docs",
        )
        session.add(bm)
        session.flush()
        assert bm.domain == "docs.python.org"

    def test_domain_property_simple(self, session):
        bm = Bookmark(
            unique_id="f3a4b5c6d1e2f3a4",
            url="https://github.com",
            title="GitHub",
        )
        session.add(bm)
        session.flush()
        assert bm.domain == "github.com"

    def test_tag_names_property_empty(self, session):
        bm = Bookmark(
            unique_id="a4b5c6d1e2f3a4b5",
            url="https://notags.example.com",
            title="No tags",
        )
        session.add(bm)
        session.flush()
        assert bm.tag_names == []

    def test_tag_names_property_with_tags(self, session):
        t1 = Tag(name="python-tt1")
        t2 = Tag(name="programming-tt1")
        bm = Bookmark(
            unique_id="b5c6d1e2f3a4b5c6",
            url="https://tagged.example.com",
            title="Tagged",
            tags=[t1, t2],
        )
        session.add(bm)
        session.flush()
        names = bm.tag_names
        assert "python-tt1" in names
        assert "programming-tt1" in names
        assert len(names) == 2


# ---------------------------------------------------------------------------
# Tag M2M relationship
# ---------------------------------------------------------------------------


class TestBookmarkTagRelationship:
    def test_m2m_tag_association(self, session):
        t = Tag(name="unique-test-tag-m2m")
        bm = Bookmark(
            unique_id="c6d1e2f3a4b5c6d1",
            url="https://m2m.example.com",
            title="M2M test",
            tags=[t],
        )
        session.add(bm)
        session.flush()
        assert t in bm.tags
        assert bm in t.bookmarks

    def test_multiple_tags(self, session):
        t1 = Tag(name="tag-mt-alpha")
        t2 = Tag(name="tag-mt-beta")
        t3 = Tag(name="tag-mt-gamma")
        bm = Bookmark(
            unique_id="d1e2f3a4b5c6d1e2",
            url="https://multitag.example.com",
            title="Multi-tag",
            tags=[t1, t2, t3],
        )
        session.add(bm)
        session.flush()
        assert len(bm.tags) == 3


# ---------------------------------------------------------------------------
# Media JSON field
# ---------------------------------------------------------------------------


class TestBookmarkMediaField:
    def test_media_json_stored_and_retrieved(self, session):
        media_data = {"type": "video", "duration_s": 3600, "platform": "youtube"}
        bm = Bookmark(
            unique_id="e2f3a4b5c6d1e2f3",
            url="https://youtube.example.com/watch",
            title="Some video",
            media=media_data,
        )
        session.add(bm)
        session.flush()
        session.expire(bm)
        session.refresh(bm)
        assert bm.media == media_data

    def test_media_none_by_default(self, session):
        bm = Bookmark(
            unique_id="f3a4b5c6d1e2f3a4",
            url="https://nomedia.example.com",
            title="No media",
        )
        session.add(bm)
        session.flush()
        assert bm.media is None


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------


class TestAnnotation:
    def test_create_annotation_with_bookmark(self, session):
        bm = Bookmark(
            unique_id="aa01bb02cc03dd04",
            url="https://annot.example.com",
            title="Annotated",
        )
        session.add(bm)
        session.flush()

        ann_id = uuid.uuid4().hex
        ann = Annotation(id=ann_id, bookmark_id=bm.id, text="Interesting point")
        session.add(ann)
        session.flush()

        assert ann.id == ann_id
        assert ann.bookmark_id == bm.id
        assert ann.text == "Interesting point"

    def test_annotation_uri_property(self, session):
        ann_id = uuid.uuid4().hex
        bm = Bookmark(
            unique_id="bb02cc03dd04ee05",
            url="https://annot-uri.example.com",
            title="Annot URI",
        )
        session.add(bm)
        session.flush()

        ann = Annotation(id=ann_id, bookmark_id=bm.id, text="Note")
        session.add(ann)
        session.flush()

        assert ann.uri == build_annotation_uri(ann_id)
        assert ann.uri == f"bookmark-memex://annotation/{ann_id}"

    def test_orphan_survival_on_bookmark_delete(self, session):
        """Deleting a bookmark sets annotation.bookmark_id to NULL, not deletes it."""
        bm = Bookmark(
            unique_id="cc03dd04ee05ff06",
            url="https://orphan.example.com",
            title="Orphan test",
        )
        session.add(bm)
        session.flush()
        bm_id = bm.id

        ann_id = uuid.uuid4().hex
        ann = Annotation(id=ann_id, bookmark_id=bm_id, text="Orphan note")
        session.add(ann)
        session.flush()

        # Delete bookmark
        session.delete(bm)
        session.flush()

        # Annotation should still exist with bookmark_id = None
        result = session.execute(
            select(Annotation).where(Annotation.id == ann_id)
        ).scalar_one_or_none()

        assert result is not None, "Annotation must survive bookmark deletion"
        assert result.bookmark_id is None, "bookmark_id should be NULL after parent delete"


# ---------------------------------------------------------------------------
# BookmarkSource
# ---------------------------------------------------------------------------


class TestBookmarkSource:
    def test_multiple_sources_per_bookmark(self, session):
        bm = Bookmark(
            unique_id="dd04ee05ff06aa07",
            url="https://sources.example.com",
            title="Multi-source",
        )
        session.add(bm)
        session.flush()

        src1 = BookmarkSource(
            bookmark_id=bm.id,
            source_type="html_import",
            source_name="bookmarks.html",
            folder_path="Programming/Python",
        )
        src2 = BookmarkSource(
            bookmark_id=bm.id,
            source_type="json_import",
            source_name="export.json",
        )
        session.add_all([src1, src2])
        session.flush()

        session.expire(bm)
        session.refresh(bm)
        assert len(bm.sources) == 2

    def test_source_imported_at_defaults(self, session):
        bm = Bookmark(
            unique_id="ee05ff06aa07bb08",
            url="https://srctime.example.com",
            title="Src time",
        )
        session.add(bm)
        session.flush()

        src = BookmarkSource(bookmark_id=bm.id, source_type="manual")
        session.add(src)
        session.flush()
        assert isinstance(src.imported_at, datetime)

    def test_source_raw_data_json(self, session):
        bm = Bookmark(
            unique_id="ff06aa07bb08cc09",
            url="https://srcjson.example.com",
            title="Src JSON",
        )
        session.add(bm)
        session.flush()

        raw = {"original_title": "Old Title", "folder": "Misc"}
        src = BookmarkSource(bookmark_id=bm.id, source_type="html_import", raw_data=raw)
        session.add(src)
        session.flush()
        session.expire(src)
        session.refresh(src)
        assert src.raw_data == raw


# ---------------------------------------------------------------------------
# Tag hierarchy properties
# ---------------------------------------------------------------------------


class TestTagHierarchyProperties:
    def test_root_tag_hierarchy_level(self, session):
        tag = Tag(name="standalone-hier-root")
        session.add(tag)
        session.flush()
        assert tag.hierarchy_level == 0

    def test_root_tag_parent_path_is_none(self, session):
        tag = Tag(name="standalone-hier-none")
        session.add(tag)
        session.flush()
        assert tag.parent_path is None

    def test_root_tag_leaf_name(self, session):
        tag = Tag(name="standalone-hier-leaf")
        session.add(tag)
        session.flush()
        assert tag.leaf_name == "standalone-hier-leaf"

    def test_deep_tag_hierarchy_level(self, session):
        tag = Tag(name="programming/python/web-hier")
        session.add(tag)
        session.flush()
        assert tag.hierarchy_level == 2

    def test_deep_tag_parent_path(self, session):
        tag = Tag(name="programming/python/web-pp")
        session.add(tag)
        session.flush()
        assert tag.parent_path == "programming/python"

    def test_deep_tag_leaf_name(self, session):
        tag = Tag(name="programming/python/web-ln")
        session.add(tag)
        session.flush()
        assert tag.leaf_name == "web-ln"

    def test_one_level_tag_hierarchy_level(self, session):
        tag = Tag(name="programming/py-lvl1")
        session.add(tag)
        session.flush()
        assert tag.hierarchy_level == 1

    def test_one_level_tag_parent_path(self, session):
        tag = Tag(name="programming/py-parent1")
        session.add(tag)
        session.flush()
        assert tag.parent_path == "programming"

    def test_one_level_tag_leaf_name(self, session):
        tag = Tag(name="programming/py-leafname")
        session.add(tag)
        session.flush()
        assert tag.leaf_name == "py-leafname"


# ---------------------------------------------------------------------------
# ContentCache
# ---------------------------------------------------------------------------


class TestContentCache:
    def test_create_content_cache(self, session):
        bm = Bookmark(
            unique_id="aa07bb08cc09dd0a",
            url="https://cache.example.com",
            title="Cached page",
        )
        session.add(bm)
        session.flush()

        cc = ContentCache(
            bookmark_id=bm.id,
            html_content=b"<html>hello</html>",
            markdown_content="# Hello",
            extracted_text="Hello",
            content_hash="abc123hash",
            content_length=18,
            compressed_size=10,
        )
        session.add(cc)
        session.flush()

        assert cc.id is not None
        assert cc.bookmark_id == bm.id

    def test_content_cache_relationship(self, session):
        bm = Bookmark(
            unique_id="bb08cc09dd0aee0b",
            url="https://cache-rel.example.com",
            title="Cache rel",
        )
        session.add(bm)
        session.flush()

        cc = ContentCache(bookmark_id=bm.id, extracted_text="text content")
        session.add(cc)
        session.flush()

        session.expire(bm)
        session.refresh(bm)
        assert bm.content_cache is cc

    def test_fetched_at_defaults(self, session):
        bm = Bookmark(
            unique_id="cc09dd0aee0bff0c",
            url="https://fetchtime.example.com",
            title="Fetch time",
        )
        session.add(bm)
        session.flush()

        cc = ContentCache(bookmark_id=bm.id)
        session.add(cc)
        session.flush()
        assert isinstance(cc.fetched_at, datetime)


# ---------------------------------------------------------------------------
# Event and SchemaVersion
# ---------------------------------------------------------------------------


class TestEvent:
    def test_create_event(self, session):
        ev = Event(
            event_type="bookmark_added",
            entity_type="bookmark",
            entity_id="someuniqueid123",
            event_data={"url": "https://example.com"},
        )
        session.add(ev)
        session.flush()
        assert ev.id is not None
        assert isinstance(ev.timestamp, datetime)

    def test_event_timestamp_defaults(self, session):
        ev = Event(event_type="test_event", entity_type="bookmark")
        session.add(ev)
        session.flush()
        assert ev.timestamp is not None


class TestSchemaVersion:
    def test_create_schema_version(self, session):
        sv = SchemaVersion(version=1, description="Initial schema")
        session.add(sv)
        session.flush()
        assert sv.version == 1
        assert isinstance(sv.applied_at, datetime)
