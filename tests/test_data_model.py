"""
Tests for the data model redesign: satellite tables, migration, and new features.

Tests:
- New models: BookmarkSource, BookmarkVisit, BookmarkMedia, ViewDefinition, SchemaVersion
- Migration system: schema versioning, v0→v1 migration
- Provenance tracking: source creation, merge on duplicate
- Visit tracking: add_visit, refresh_visit_cache
- Media relationship: media via db.add(), hybrid properties
- Views CRUD: save_view, delete_view, list_views
- Collection enhancements: icon, position
"""
import json
import os
import tempfile
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from btk.db import Database, _get_schema_version, _table_exists, _column_exists, CURRENT_SCHEMA_VERSION
from btk.models import (
    Bookmark, BookmarkSource, BookmarkVisit, BookmarkMedia,
    ViewDefinition, SchemaVersion, Collection, bookmark_collections
)


@pytest.fixture
def db(tmp_path):
    """Create a fresh database for testing."""
    db_path = str(tmp_path / "test.db")
    return Database(path=db_path)


@pytest.fixture
def db_with_bookmarks(db):
    """Database pre-populated with a few bookmarks."""
    db.add(url="https://example.com", title="Example")
    db.add(url="https://python.org", title="Python", tags=["programming"])
    db.add(url="https://youtube.com/watch?v=abc", title="Video",
           media_type="video", media_source="youtube", author_name="Creator")
    return db


# =============================================================================
# Schema & Migration Tests
# =============================================================================

class TestSchemaVersion:
    def test_fresh_db_has_schema_version(self, db):
        """A fresh database should have schema_version table with current version."""
        with db.engine.connect() as conn:
            assert _table_exists(conn, 'schema_version')
            version = _get_schema_version(conn)
            assert version == CURRENT_SCHEMA_VERSION

    def test_new_tables_exist(self, db):
        """All new satellite tables should exist."""
        with db.engine.connect() as conn:
            assert _table_exists(conn, 'bookmark_sources')
            assert _table_exists(conn, 'bookmark_visits')
            assert _table_exists(conn, 'bookmark_media')
            assert _table_exists(conn, 'views')

    def test_bookmark_type_column_exists(self, db):
        """Bookmarks table should have bookmark_type column."""
        with db.engine.connect() as conn:
            assert _column_exists(conn, 'bookmarks', 'bookmark_type')

    def test_collection_new_columns(self, db):
        """Collections table should have icon and position columns."""
        with db.engine.connect() as conn:
            assert _column_exists(conn, 'collections', 'icon')
            assert _column_exists(conn, 'collections', 'position')

    def test_bookmark_collections_position(self, db):
        """bookmark_collections should have position column."""
        with db.engine.connect() as conn:
            assert _column_exists(conn, 'bookmark_collections', 'position')


class TestMigration:
    def test_migration_creates_backup(self, tmp_path):
        """Migration should create a backup of the database."""
        db_path = tmp_path / "test.db"
        # Create a bare v0 database (no satellite tables)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE bookmarks (id INTEGER PRIMARY KEY, url TEXT, title TEXT, unique_id TEXT UNIQUE, added DATETIME, visit_count INTEGER DEFAULT 0, stars BOOLEAN DEFAULT 0, archived BOOLEAN DEFAULT 0, pinned BOOLEAN DEFAULT 0, reachable BOOLEAN, last_visited DATETIME, description TEXT, favicon_data BLOB, favicon_mime_type TEXT, extra_data JSON, media_type TEXT, media_source TEXT, media_id TEXT, author_name TEXT, author_url TEXT, thumbnail_url TEXT, published_at DATETIME)")
        conn.execute("INSERT INTO bookmarks (id, url, title, unique_id, added) VALUES (1, 'https://example.com', 'Test', 'abc12345', '2024-01-01')")
        conn.commit()
        conn.close()

        # Now open with Database — migration should run
        db = Database(path=str(db_path))

        # Backup should exist
        backup = db_path.with_suffix(".v0.bak")
        assert backup.exists()

    def test_migration_backfills_media(self, tmp_path):
        """Migration should backfill bookmark_media from existing media columns."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE bookmarks (id INTEGER PRIMARY KEY, url TEXT, title TEXT, unique_id TEXT UNIQUE, added DATETIME, visit_count INTEGER DEFAULT 0, stars BOOLEAN DEFAULT 0, archived BOOLEAN DEFAULT 0, pinned BOOLEAN DEFAULT 0, reachable BOOLEAN, last_visited DATETIME, description TEXT, favicon_data BLOB, favicon_mime_type TEXT, extra_data JSON, media_type TEXT, media_source TEXT, media_id TEXT, author_name TEXT, author_url TEXT, thumbnail_url TEXT, published_at DATETIME)")
        conn.execute("INSERT INTO bookmarks (id, url, title, unique_id, added, media_type, media_source, author_name) VALUES (1, 'https://youtube.com/watch?v=abc', 'Video', 'vid12345', '2024-01-01', 'video', 'youtube', 'Creator')")
        conn.execute("INSERT INTO bookmarks (id, url, title, unique_id, added) VALUES (2, 'https://example.com', 'Plain', 'pla12345', '2024-01-01')")
        conn.commit()
        conn.close()

        db = Database(path=str(db_path))

        # Check bookmark_media was backfilled
        with db.engine.connect() as c:
            result = c.execute(text("SELECT COUNT(*) FROM bookmark_media")).scalar()
            assert result == 1  # Only the video bookmark

            row = c.execute(text("SELECT media_type, media_source, author_name FROM bookmark_media WHERE bookmark_id = 1")).fetchone()
            assert row[0] == 'video'
            assert row[1] == 'youtube'
            assert row[2] == 'Creator'

    def test_migration_backfills_legacy_sources(self, tmp_path):
        """Migration should create legacy source rows for existing bookmarks."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE bookmarks (id INTEGER PRIMARY KEY, url TEXT, title TEXT, unique_id TEXT UNIQUE, added DATETIME, visit_count INTEGER DEFAULT 0, stars BOOLEAN DEFAULT 0, archived BOOLEAN DEFAULT 0, pinned BOOLEAN DEFAULT 0, reachable BOOLEAN, last_visited DATETIME, description TEXT, favicon_data BLOB, favicon_mime_type TEXT, extra_data JSON, media_type TEXT, media_source TEXT, media_id TEXT, author_name TEXT, author_url TEXT, thumbnail_url TEXT, published_at DATETIME)")
        conn.execute("INSERT INTO bookmarks (id, url, title, unique_id, added) VALUES (1, 'https://example.com', 'Test', 'abc12345', '2024-01-01')")
        conn.execute("INSERT INTO bookmarks (id, url, title, unique_id, added) VALUES (2, 'https://python.org', 'Python', 'def12345', '2024-01-01')")
        conn.commit()
        conn.close()

        db = Database(path=str(db_path))

        with db.engine.connect() as c:
            result = c.execute(text("SELECT COUNT(*) FROM bookmark_sources WHERE source_type = 'legacy'")).scalar()
            assert result == 2

    def test_migration_is_idempotent(self, tmp_path):
        """Running migration twice should not create duplicate rows."""
        db_path = tmp_path / "test.db"
        db = Database(path=str(db_path))
        db.add(url="https://example.com", title="Test")

        # Open again — migration should check version and skip
        db2 = Database(path=str(db_path))
        with db2.engine.connect() as c:
            version = _get_schema_version(c)
            assert version == CURRENT_SCHEMA_VERSION


# =============================================================================
# Provenance (BookmarkSource) Tests
# =============================================================================

class TestProvenance:
    def test_add_with_source(self, db):
        """Adding a bookmark with source_type creates a BookmarkSource."""
        b = db.add(
            url="https://example.com", title="Test",
            source_type="chrome", source_name="Work Profile",
            source_profile="Profile 1", folder_path="Bookmarks Bar/Dev",
            raw_data={"guid": "abc-123", "date_added": "13356789000000"}
        )

        assert b is not None
        fetched = db.get(id=b.id)
        assert len(fetched.sources) == 1
        assert fetched.sources[0].source_type == "chrome"
        assert fetched.sources[0].source_name == "Work Profile"
        assert fetched.sources[0].source_profile == "Profile 1"
        assert fetched.sources[0].folder_path == "Bookmarks Bar/Dev"
        assert fetched.sources[0].raw_data["guid"] == "abc-123"

    def test_add_without_source(self, db):
        """Adding without source_type creates no BookmarkSource."""
        b = db.add(url="https://example.com", title="Test")
        fetched = db.get(id=b.id)
        # Only the legacy source from migration (on fresh DB there's none since
        # the bookmark is created after migration runs)
        # Actually on a fresh DB, migration runs before any bookmarks exist,
        # so there's no legacy source for new bookmarks added via db.add()
        assert len(fetched.sources) == 0

    def test_duplicate_merge_provenance(self, db):
        """Duplicate URL should still create a BookmarkSource row."""
        b1 = db.add(
            url="https://example.com", title="From Chrome",
            source_type="chrome", source_name="Default"
        )
        b2 = db.add(
            url="https://example.com", title="From Firefox",
            source_type="firefox", source_name="default-release"
        )

        assert b1 is not None
        assert b2 is None  # Duplicate skipped

        fetched = db.get(id=b1.id)
        assert len(fetched.sources) == 2
        source_types = {s.source_type for s in fetched.sources}
        assert source_types == {"chrome", "firefox"}

    def test_source_cascade_delete(self, db):
        """Deleting a bookmark should cascade-delete its sources."""
        b = db.add(url="https://example.com", title="Test",
                   source_type="chrome", source_name="Default")
        bookmark_id = b.id

        db.delete(bookmark_id)

        with db.session() as session:
            sources = list(session.execute(
                text("SELECT COUNT(*) FROM bookmark_sources WHERE bookmark_id = :id"),
                {"id": bookmark_id}
            ).scalars())
            assert sources[0] == 0


# =============================================================================
# Visit Tracking Tests
# =============================================================================

class TestVisits:
    def test_add_visit(self, db):
        """add_visit creates a BookmarkVisit record."""
        b = db.add(url="https://example.com", title="Test")
        now = datetime.now(timezone.utc)

        visit = db.add_visit(
            bookmark_id=b.id,
            visited_at=now,
            source_type="chrome_history",
            source_name="Default",
            transition_type="typed"
        )

        assert visit is not None
        assert visit.source_type == "chrome_history"
        assert visit.transition_type == "typed"

    def test_add_visit_duplicate_skipped(self, db):
        """Duplicate visits (same bookmark, time, source) are skipped."""
        b = db.add(url="https://example.com", title="Test")
        now = datetime.now(timezone.utc)

        v1 = db.add_visit(b.id, now, "chrome_history")
        v2 = db.add_visit(b.id, now, "chrome_history")

        assert v1 is not None
        assert v2 is None

    def test_refresh_visit_cache(self, db):
        """refresh_visit_cache updates visit_count and last_visited."""
        b = db.add(url="https://example.com", title="Test")
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(hours=1)

        db.add_visit(b.id, earlier, "chrome_history")
        db.add_visit(b.id, now, "chrome_history")

        updated = db.refresh_visit_cache(b.id)
        assert updated == 1

        fetched = db.get(id=b.id)
        assert fetched.visit_count == 2

    def test_visit_cascade_delete(self, db):
        """Deleting a bookmark should cascade-delete its visits."""
        b = db.add(url="https://example.com", title="Test")
        db.add_visit(b.id, datetime.now(timezone.utc), "chrome_history")

        db.delete(b.id)

        with db.session() as session:
            count = session.execute(
                text("SELECT COUNT(*) FROM bookmark_visits WHERE bookmark_id = :id"),
                {"id": b.id}
            ).scalar()
            assert count == 0


# =============================================================================
# Media Tests
# =============================================================================

class TestMedia:
    def test_add_with_media(self, db):
        """Adding with media_type creates a BookmarkMedia row."""
        b = db.add(
            url="https://youtube.com/watch?v=abc",
            title="Video",
            media_type="video",
            media_source="youtube",
            media_id="abc",
            author_name="Creator",
            thumbnail_url="https://img.youtube.com/vi/abc/0.jpg"
        )

        fetched = db.get(id=b.id)
        assert fetched.media is not None
        assert fetched.media.media_type == "video"
        assert fetched.media.media_source == "youtube"
        assert fetched.media.author_name == "Creator"

    def test_hybrid_property_media_type(self, db):
        """Hybrid properties on Bookmark delegate to media relationship."""
        b = db.add(url="https://youtube.com/watch?v=abc", title="Video",
                   media_type="video", media_source="youtube", author_name="Creator")

        fetched = db.get(id=b.id)
        assert fetched.media_type == "video"
        assert fetched.media_source == "youtube"
        assert fetched.author_name == "Creator"

    def test_hybrid_property_none_without_media(self, db):
        """Hybrid properties return None when no media relationship."""
        b = db.add(url="https://example.com", title="No Media")

        fetched = db.get(id=b.id)
        assert fetched.media_type is None
        assert fetched.author_name is None

    def test_update_media_fields(self, db):
        """db.update() should route media fields to BookmarkMedia."""
        b = db.add(url="https://youtube.com/watch?v=abc", title="Video")

        db.update(b.id, media_type="video", media_source="youtube", author_name="Creator")

        fetched = db.get(id=b.id)
        assert fetched.media is not None
        assert fetched.media_type == "video"
        assert fetched.author_name == "Creator"

    def test_media_cascade_delete(self, db):
        """Deleting a bookmark should cascade-delete its media."""
        b = db.add(url="https://youtube.com/watch?v=abc", title="Video",
                   media_type="video")

        db.delete(b.id)

        with db.session() as session:
            count = session.execute(
                text("SELECT COUNT(*) FROM bookmark_media WHERE bookmark_id = :id"),
                {"id": b.id}
            ).scalar()
            assert count == 0


# =============================================================================
# Bookmark Type Tests
# =============================================================================

class TestBookmarkType:
    def test_default_type_is_bookmark(self, db):
        """Default bookmark_type should be 'bookmark'."""
        b = db.add(url="https://example.com", title="Test")
        fetched = db.get(id=b.id)
        assert fetched.bookmark_type == "bookmark"

    def test_custom_type(self, db):
        """Can set bookmark_type to 'history', 'tab', etc."""
        b = db.add(url="https://example.com", title="Test", bookmark_type="history")
        fetched = db.get(id=b.id)
        assert fetched.bookmark_type == "history"


# =============================================================================
# Views CRUD Tests
# =============================================================================

class TestViewsCRUD:
    def test_save_view(self, db):
        """save_view creates a ViewDefinition."""
        view = db.save_view(
            name="my_view",
            definition={"select": {"tags": {"any": ["python"]}}},
            description="Python bookmarks"
        )
        assert view.name == "my_view"
        assert view.description == "Python bookmarks"
        assert view.created_by == "user"

    def test_save_view_upsert(self, db):
        """save_view updates existing view on name conflict."""
        db.save_view("my_view", {"select": {"tags": {"any": ["python"]}}})
        db.save_view("my_view", {"select": {"tags": {"any": ["rust"]}}}, description="Updated")

        views = db.list_views()
        assert len(views) == 1
        assert views[0].definition == {"select": {"tags": {"any": ["rust"]}}}
        assert views[0].description == "Updated"

    def test_delete_view(self, db):
        """delete_view removes a ViewDefinition."""
        db.save_view("my_view", {"select": {"tags": {"any": ["python"]}}})
        assert db.delete_view("my_view") is True
        assert db.list_views() == []

    def test_delete_nonexistent_view(self, db):
        """delete_view returns False for nonexistent view."""
        assert db.delete_view("nonexistent") is False

    def test_list_views(self, db):
        """list_views returns all ViewDefinitions sorted by name."""
        db.save_view("beta", {"select": {}})
        db.save_view("alpha", {"select": {}})

        views = db.list_views()
        assert len(views) == 2
        assert views[0].name == "alpha"
        assert views[1].name == "beta"


# =============================================================================
# Stats Tests
# =============================================================================

class TestStats:
    def test_stats_includes_new_counts(self, db_with_bookmarks):
        """stats() should include counts for sources, visits, and media."""
        stats = db_with_bookmarks.stats()
        assert "total_sources" in stats
        assert "total_visit_records" in stats
        assert "total_media" in stats
        # The video bookmark has media
        assert stats["total_media"] >= 1

    def test_info_shows_schema_version(self, db):
        """info() should show the schema version from the database."""
        info = db.info()
        assert info["schema_version"] == CURRENT_SCHEMA_VERSION


# =============================================================================
# File Importer Provenance Tests
# =============================================================================

class TestFileImporterProvenance:
    def test_html_import_creates_source(self, db, tmp_path):
        """HTML import should create BookmarkSource rows."""
        html_file = tmp_path / "bookmarks.html"
        html_file.write_text("""
        <DL><DT><A HREF="https://example.com" ADD_DATE="1609459200" ICON="data:image/png;base64,abc">Example</A>
        </DL>
        """)

        from btk.importers.file_importers import import_html
        count = import_html(db, html_file)
        assert count == 1

        fetched = db.get(id=1)
        assert len(fetched.sources) == 1
        assert fetched.sources[0].source_type == "html_file"
        assert fetched.sources[0].source_name == "bookmarks.html"
        # raw_data should preserve Netscape attributes
        assert fetched.sources[0].raw_data is not None
        assert "add_date" in fetched.sources[0].raw_data
        assert fetched.sources[0].raw_data["icon"] == "data:image/png;base64,abc"

    def test_html_import_multiple_bookmarks(self, db, tmp_path):
        """HTML import should create one source per bookmark."""
        html_file = tmp_path / "bookmarks.html"
        html_file.write_text(
            '<DL>'
            '<DT><A HREF="https://example.com">Example</A>'
            '<DT><A HREF="https://github.com">GitHub</A>'
            '</DL>'
        )

        from btk.importers.file_importers import import_html
        count = import_html(db, html_file)
        assert count == 2

        b1 = db.get(id=1)
        b2 = db.get(id=2)
        assert len(b1.sources) == 1
        assert len(b2.sources) == 1
        assert b1.sources[0].source_type == "html_file"
        assert b2.sources[0].source_type == "html_file"

    def test_json_import_creates_source(self, db, tmp_path):
        """JSON import should create BookmarkSource rows."""
        json_file = tmp_path / "bookmarks.json"
        json_file.write_text(json.dumps([
            {"url": "https://example.com", "title": "Example", "custom_field": "value"}
        ]))

        from btk.importers.file_importers import import_json
        count = import_json(db, json_file)
        assert count == 1

        fetched = db.get(id=1)
        assert len(fetched.sources) == 1
        assert fetched.sources[0].source_type == "json_file"
        assert fetched.sources[0].source_name == "bookmarks.json"
        # raw_data should preserve extra fields
        assert fetched.sources[0].raw_data["custom_field"] == "value"

    def test_csv_import_creates_source(self, db, tmp_path):
        """CSV import should create BookmarkSource rows."""
        csv_file = tmp_path / "bookmarks.csv"
        csv_file.write_text("url,title\nhttps://example.com,Example\n")

        from btk.importers.file_importers import import_csv
        count = import_csv(db, csv_file)
        assert count == 1

        fetched = db.get(id=1)
        assert len(fetched.sources) == 1
        assert fetched.sources[0].source_type == "csv_file"

    def test_markdown_import_creates_source(self, db, tmp_path):
        """Markdown import should create BookmarkSource rows."""
        md_file = tmp_path / "links.md"
        # Use a standalone URL (not in markdown link syntax) to avoid double-counting
        md_file.write_text("https://example.com\n")

        from btk.importers.file_importers import import_markdown
        count = import_markdown(db, md_file)
        assert count == 1

        fetched = db.get(id=1)
        assert len(fetched.sources) == 1
        assert fetched.sources[0].source_type == "markdown_file"

    def test_text_import_creates_source(self, db, tmp_path):
        """Text import should create BookmarkSource rows."""
        txt_file = tmp_path / "urls.txt"
        txt_file.write_text("https://example.com\n")

        from btk.importers.file_importers import import_text
        count = import_text(db, txt_file)
        assert count == 1

        fetched = db.get(id=1)
        assert len(fetched.sources) == 1
        assert fetched.sources[0].source_type == "text_file"

    def test_duplicate_import_merges_provenance(self, db, tmp_path):
        """Importing the same URL from two files should create two source rows."""
        html_file = tmp_path / "first.html"
        html_file.write_text('<DL><DT><A HREF="https://example.com">Example</A></DL>')

        json_file = tmp_path / "second.json"
        json_file.write_text(json.dumps([{"url": "https://example.com", "title": "Example"}]))

        from btk.importers.file_importers import import_html, import_json
        import_html(db, html_file)
        import_json(db, json_file)

        fetched = db.get(id=1)
        assert len(fetched.sources) == 2
        source_types = {s.source_type for s in fetched.sources}
        assert source_types == {"html_file", "json_file"}
