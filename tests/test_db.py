"""
Comprehensive tests for btk/db.py

Tests the Database class and all its methods including:
- Database initialization (SQLite and PostgreSQL)
- CRUD operations (add, get, update, delete)
- Query and search operations
- Stats and info retrieval
- Content refresh functionality
"""
import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import select

from btk.db import Database, get_db
from btk.models import Bookmark, Tag, ContentCache
from btk.config import get_config


class TestDatabaseInit:
    """Test Database initialization."""

    def test_init_with_default_config(self):
        """Test initialization with default config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            assert db.path == Path(db_path)
            assert db.url == f"sqlite:///{db_path}"
            assert db.engine is not None
            assert db.Session is not None

    def test_init_with_path(self):
        """Test initialization with explicit path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "bookmarks.db")
            db = Database(path=db_path)

            assert db.path.exists()
            assert str(db.path) == db_path

    def test_init_with_url(self):
        """Test initialization with database URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            url = f"sqlite:///{db_path}"
            db = Database(url=url)

            assert db.url == url
            assert db.path is None  # path is None when URL is provided

    def test_init_creates_parent_directory(self):
        """Test that parent directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "subdir", "nested", "test.db")
            db = Database(path=db_path)

            assert Path(db_path).parent.exists()
            assert db.path.parent.exists()

    def test_schema_creation(self):
        """Test that schema is created on initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Check that tables exist
            with db.session() as session:
                # Should be able to query tables
                result = session.execute(select(Bookmark)).all()
                assert result == []


class TestDatabaseAdd:
    """Test Database.add() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database for each test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_add_simple_bookmark(self, db):
        """Test adding a simple bookmark."""
        bookmark = db.add(
            url="https://example.com",
            title="Example"
        )

        assert bookmark is not None
        assert bookmark.url == "https://example.com"
        assert bookmark.title == "Example"
        assert bookmark.unique_id is not None
        assert len(bookmark.unique_id) == 8

    def test_add_bookmark_with_tags(self, db):
        """Test adding bookmark with tags."""
        bookmark = db.add(
            url="https://example.com",
            title="Example",
            tags=["python", "programming"]
        )

        assert len(bookmark.tags) == 2
        tag_names = [t.name for t in bookmark.tags]
        assert "python" in tag_names
        assert "programming" in tag_names

    def test_add_bookmark_with_all_fields(self, db):
        """Test adding bookmark with all optional fields."""
        now = datetime.now(timezone.utc)

        bookmark = db.add(
            url="https://example.com",
            title="Example",
            description="Test description",
            tags=["test"],
            stars=True,
            visit_count=5,
            last_visited=now
        )

        assert bookmark.description == "Test description"
        assert bookmark.stars is True
        assert bookmark.visit_count == 5
        assert bookmark.last_visited == now

    def test_add_duplicate_url_skip(self, db):
        """Test that duplicate URLs are skipped by default."""
        db.add(url="https://example.com", title="First")
        result = db.add(url="https://example.com", title="Second")

        assert result is None  # Second add returns None (skipped)

        # Verify only one bookmark exists
        bookmarks = db.all()
        assert len(bookmarks) == 1
        assert bookmarks[0].title == "First"

    def test_add_duplicate_url_error(self, db):
        """Test that duplicate URLs raise error when skip_duplicates=False."""
        db.add(url="https://example.com", title="First")

        with pytest.raises(ValueError, match="already exists"):
            db.add(url="https://example.com", title="Second", skip_duplicates=False)

    @patch('btk.db.Database._fetch_title')
    def test_add_fetches_title_if_not_provided(self, mock_fetch, db):
        """Test that title is fetched if not provided."""
        mock_fetch.return_value = "Fetched Title"

        bookmark = db.add(url="https://example.com")

        mock_fetch.assert_called_once_with("https://example.com")
        assert bookmark.title == "Fetched Title"

    @patch('btk.db.Database._fetch_title')
    def test_add_uses_url_as_title_if_fetch_fails(self, mock_fetch, db):
        """Test that URL is used as title if fetch fails."""
        mock_fetch.return_value = None

        bookmark = db.add(url="https://example.com")

        assert bookmark.title == "https://example.com"


class TestDatabaseGet:
    """Test Database.get() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)

            # Add test bookmarks
            db_instance.add(url="https://example.com", title="Example")
            db_instance.add(url="https://test.com", title="Test", tags=["testing"])

            yield db_instance

    def test_get_by_id(self, db):
        """Test getting bookmark by numeric ID."""
        bookmark = db.get(id=1)

        assert bookmark is not None
        assert bookmark.id == 1
        assert bookmark.title == "Example"

    def test_get_by_unique_id(self, db):
        """Test getting bookmark by unique_id."""
        # First get the unique_id
        bookmark1 = db.get(id=1)
        unique_id = bookmark1.unique_id

        # Now get by unique_id
        bookmark2 = db.get(unique_id=unique_id)

        assert bookmark2 is not None
        assert bookmark2.id == bookmark1.id
        assert bookmark2.url == bookmark1.url

    def test_get_with_tags_loaded(self, db):
        """Test that tags are eagerly loaded."""
        bookmark = db.get(id=2)

        assert bookmark is not None
        assert len(bookmark.tags) == 1
        assert bookmark.tags[0].name == "testing"

    def test_get_nonexistent_id(self, db):
        """Test getting non-existent bookmark returns None."""
        bookmark = db.get(id=999)
        assert bookmark is None

    def test_get_without_id_or_unique_id(self, db):
        """Test that get returns None when no ID provided."""
        bookmark = db.get()
        assert bookmark is None


class TestDatabaseQuery:
    """Test Database.query() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)

            # Add test bookmarks
            db_instance.add(url="https://python.org", title="Python", tags=["python", "programming"])
            db_instance.add(url="https://github.com", title="GitHub", tags=["git", "development"])
            db_instance.add(url="https://example.com", title="Example", stars=True)

            yield db_instance

    def test_query_by_url(self, db):
        """Test querying by URL."""
        results = db.query(url="python")

        assert len(results) == 1
        assert results[0].url == "https://python.org"

    def test_query_by_title(self, db):
        """Test querying by title."""
        results = db.query(title="GitHub")

        assert len(results) == 1
        assert results[0].title == "GitHub"

    def test_query_by_stars(self, db):
        """Test querying by stars."""
        results = db.query(stars=True)

        assert len(results) == 1
        assert results[0].title == "Example"

    def test_query_by_tags(self, db):
        """Test querying by tags."""
        results = db.query(tags="python")

        assert len(results) >= 1
        # Should include bookmarks with tags starting with "python"
        assert any(b.url == "https://python.org" for b in results)

    def test_query_with_sql(self, db):
        """Test querying with raw SQL."""
        results = db.query(sql="url LIKE '%github%'")

        assert len(results) == 1
        assert results[0].url == "https://github.com"

    def test_query_no_filters(self, db):
        """Test query with no filters returns all bookmarks."""
        results = db.query()
        # With no filters, query returns all bookmarks due to the filter logic
        assert len(results) == 3


class TestDatabaseList:
    """Test Database.list() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)

            # Add bookmarks with different attributes
            db_instance.add(url="https://a.com", title="A", visit_count=10)
            db_instance.add(url="https://b.com", title="B", visit_count=5, stars=True)
            db_instance.add(url="https://c.com", title="C", visit_count=15)

            yield db_instance

    def test_list_all(self, db):
        """Test listing all bookmarks."""
        results = db.list()
        assert len(results) == 3

    def test_list_with_limit(self, db):
        """Test listing with limit."""
        results = db.list(limit=2)
        assert len(results) == 2

    def test_list_with_offset(self, db):
        """Test listing with offset."""
        results = db.list(offset=1)
        assert len(results) == 2

    def test_list_order_by_added(self, db):
        """Test ordering by added date (default)."""
        results = db.list(order_by="added")
        # Most recent first (reverse chronological)
        assert results[0].title == "C"

    def test_list_order_by_visit_count(self, db):
        """Test ordering by visit count."""
        results = db.list(order_by="visit_count")
        # Highest visit count first
        assert results[0].visit_count == 15

    def test_list_order_by_title(self, db):
        """Test ordering by title."""
        results = db.list(order_by="title")
        assert results[0].title == "A"

    def test_list_order_by_stars(self, db):
        """Test ordering by stars."""
        results = db.list(order_by="stars")
        assert results[0].stars is True


class TestDatabaseUpdate:
    """Test Database.update() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)
            db_instance.add(url="https://example.com", title="Original Title")
            yield db_instance

    def test_update_title(self, db):
        """Test updating bookmark title."""
        result = db.update(1, title="Updated Title")

        assert result is True
        bookmark = db.get(id=1)
        assert bookmark.title == "Updated Title"

    def test_update_description(self, db):
        """Test updating description."""
        result = db.update(1, description="New description")

        assert result is True
        bookmark = db.get(id=1)
        assert bookmark.description == "New description"

    def test_update_stars(self, db):
        """Test updating stars."""
        result = db.update(1, stars=True)

        assert result is True
        bookmark = db.get(id=1)
        assert bookmark.stars is True

    def test_update_tags(self, db):
        """Test updating tags."""
        result = db.update(1, tags=["new", "tags"])

        assert result is True
        bookmark = db.get(id=1)
        tag_names = [t.name for t in bookmark.tags]
        assert "new" in tag_names
        assert "tags" in tag_names

    def test_update_multiple_fields(self, db):
        """Test updating multiple fields at once."""
        result = db.update(
            1,
            title="New Title",
            description="New Description",
            stars=True,
            visit_count=10
        )

        assert result is True
        bookmark = db.get(id=1)
        assert bookmark.title == "New Title"
        assert bookmark.description == "New Description"
        assert bookmark.stars is True
        assert bookmark.visit_count == 10

    def test_update_nonexistent_bookmark(self, db):
        """Test updating non-existent bookmark returns False."""
        result = db.update(999, title="Should Fail")
        assert result is False


class TestDatabaseDelete:
    """Test Database.delete() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)
            db_instance.add(url="https://example.com", title="Example")
            db_instance.add(url="https://test.com", title="Test")
            yield db_instance

    def test_delete_existing_bookmark(self, db):
        """Test deleting existing bookmark."""
        result = db.delete(1)

        assert result is True
        bookmark = db.get(id=1)
        assert bookmark is None

        # Verify only one bookmark remains
        all_bookmarks = db.all()
        assert len(all_bookmarks) == 1

    def test_delete_nonexistent_bookmark(self, db):
        """Test deleting non-existent bookmark returns False."""
        result = db.delete(999)
        assert result is False

    def test_delete_cascades_to_tags(self, db):
        """Test that deleting bookmark doesn't delete tags."""
        # Add bookmark with tags
        db.add(url="https://tagged.com", title="Tagged", tags=["test"])

        # Delete the bookmark
        db.delete(3)

        # Tag should still exist (not deleted due to cascade)
        with db.session() as session:
            tags = session.execute(select(Tag)).scalars().all()
            tag_names = [t.name for t in tags]
            assert "test" in tag_names


class TestDatabaseStats:
    """Test Database.stats() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)

            # Add test data
            db_instance.add(url="https://a.com", title="A", stars=True, visit_count=10, tags=["tag1"])
            db_instance.add(url="https://b.com", title="B", stars=False, visit_count=5, tags=["tag2"])
            db_instance.add(url="https://c.com", title="C", stars=True, visit_count=3, tags=["tag1", "tag3"])

            yield db_instance

    def test_stats_total_bookmarks(self, db):
        """Test total bookmarks count."""
        stats = db.stats()
        assert stats["total_bookmarks"] == 3

    def test_stats_total_tags(self, db):
        """Test total tags count."""
        stats = db.stats()
        assert stats["total_tags"] == 3  # tag1, tag2, tag3

    def test_stats_starred_count(self, db):
        """Test starred bookmarks count."""
        stats = db.stats()
        assert stats["starred_count"] == 2

    def test_stats_total_visits(self, db):
        """Test total visits sum."""
        stats = db.stats()
        assert stats["total_visits"] == 18  # 10 + 5 + 3

    def test_stats_database_url(self, db):
        """Test database URL in stats."""
        stats = db.stats()
        assert "database_url" in stats
        assert stats["database_url"].startswith("sqlite:///")

    def test_stats_database_size(self, db):
        """Test database size for SQLite."""
        stats = db.stats()
        assert "database_size" in stats
        assert stats["database_size"] > 0
        assert "database_path" in stats


class TestDatabaseInfo:
    """Test Database.info() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_info_url(self, db):
        """Test info contains database URL."""
        info = db.info()
        assert "url" in info
        assert info["url"].startswith("sqlite:///")

    def test_info_engine(self, db):
        """Test info contains engine type."""
        info = db.info()
        assert "engine" in info
        assert info["engine"] == "sqlite"

    def test_info_tables(self, db):
        """Test info contains table list."""
        info = db.info()
        assert "tables" in info
        assert "bookmarks" in info["tables"]
        assert "tags" in info["tables"]

    def test_info_schema_version(self, db):
        """Test info contains schema version."""
        info = db.info()
        assert "schema_version" in info

    def test_info_sqlite_pragmas(self, db):
        """Test info contains SQLite pragmas."""
        info = db.info()
        assert "journal_mode" in info
        assert info["journal_mode"] == "wal"


class TestDatabaseSchema:
    """Test Database.schema() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_schema_returns_dict(self, db):
        """Test schema returns dictionary."""
        schema = db.schema()
        assert isinstance(schema, dict)

    def test_schema_contains_tables(self, db):
        """Test schema contains all tables."""
        schema = db.schema()
        assert "bookmarks" in schema
        assert "tags" in schema
        assert "content_cache" in schema

    def test_schema_table_structure(self, db):
        """Test schema table structure."""
        schema = db.schema()
        bookmarks = schema["bookmarks"]

        assert "columns" in bookmarks
        assert "indexes" in bookmarks
        assert isinstance(bookmarks["columns"], list)
        assert isinstance(bookmarks["indexes"], list)

    def test_schema_column_details(self, db):
        """Test schema column details."""
        schema = db.schema()
        columns = schema["bookmarks"]["columns"]

        # Find id column
        id_col = next(c for c in columns if c["name"] == "id")
        assert id_col["primary_key"] is True

        # Find url column
        url_col = next(c for c in columns if c["name"] == "url")
        assert url_col["nullable"] is False


class TestDatabaseAll:
    """Test Database.all() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)

            # Add bookmarks
            db_instance.add(url="https://a.com", title="A")
            db_instance.add(url="https://b.com", title="B")
            db_instance.add(url="https://c.com", title="C")

            yield db_instance

    def test_all_returns_all_bookmarks(self, db):
        """Test that all() returns all bookmarks."""
        results = db.all()
        assert len(results) == 3

    def test_all_ordered_by_added_desc(self, db):
        """Test that all() returns bookmarks in reverse chronological order."""
        results = db.all()
        # Most recent first
        assert results[0].title == "C"
        assert results[2].title == "A"

    def test_all_loads_tags(self, db):
        """Test that all() eagerly loads tags."""
        db.add(url="https://d.com", title="D", tags=["test"])
        results = db.all()

        # Find bookmark D
        bookmark_d = next(b for b in results if b.title == "D")
        assert len(bookmark_d.tags) == 1


class TestDatabaseSearch:
    """Test Database.search() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)

            # Add bookmarks with various attributes
            db_instance.add(
                url="https://python.org",
                title="Python Programming",
                description="Official Python website",
                tags=["python", "programming"]
            )
            db_instance.add(
                url="https://github.com",
                title="GitHub",
                description="Code hosting platform",
                stars=True
            )
            db_instance.add(
                url="https://unreachable.com",
                title="Broken Link",
                description="This link is broken"
            )
            # Mark last one as unreachable
            db_instance.update(3, reachable=False)

            yield db_instance

    def test_search_in_title(self, db):
        """Test searching in title."""
        results = db.search(query="Python")

        assert len(results) >= 1
        assert any(b.title == "Python Programming" for b in results)

    def test_search_in_url(self, db):
        """Test searching in URL."""
        results = db.search(query="github")

        assert len(results) == 1
        assert results[0].url == "https://github.com"

    def test_search_in_description(self, db):
        """Test searching in description."""
        results = db.search(query="hosting")

        assert len(results) == 1
        assert results[0].title == "GitHub"

    def test_search_with_reachable_filter(self, db):
        """Test searching with reachable filter."""
        results = db.search(reachable=False)

        assert len(results) == 1
        assert results[0].title == "Broken Link"

    def test_search_with_stars_filter(self, db):
        """Test searching with stars filter."""
        results = db.search(stars=True)

        assert len(results) == 1
        assert results[0].title == "GitHub"

    def test_search_no_query(self, db):
        """Test search with no query returns all bookmarks."""
        results = db.search()
        assert len(results) == 3

    def test_search_ordered_by_visit_count(self, db):
        """Test that search results are ordered by visit count."""
        # Update visit counts
        db.update(1, visit_count=10)
        db.update(2, visit_count=5)

        results = db.search()
        assert results[0].visit_count >= results[1].visit_count


class TestDatabaseRefreshContent:
    """Test Database.refresh_content() method."""

    @pytest.fixture
    def db(self):
        """Create a temporary database with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)
            db_instance.add(url="https://example.com", title="Example")
            yield db_instance

    @patch('btk.content_fetcher.ContentFetcher')
    def test_refresh_content_success(self, mock_fetcher_class, db):
        """Test successful content refresh."""
        # Setup mock
        mock_fetcher = Mock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.fetch_and_process.return_value = {
            "success": True,
            "title": "New Title",
            "html_content": b"compressed html",
            "markdown_content": "# Content",
            "content_hash": "abc123",
            "content_length": 1000,
            "compressed_size": 500,
            "status_code": 200,
            "response_time_ms": 100,
            "content_type": "text/html",
            "encoding": "utf-8"
        }

        result = db.refresh_content(1, update_metadata=True)

        assert result["success"] is True
        assert result["bookmark_id"] == 1
        assert result["status_code"] == 200
        assert result["content_length"] == 1000

        # Verify bookmark was updated
        bookmark = db.get(id=1)
        assert bookmark.reachable is True
        assert bookmark.title == "New Title"

    @patch('btk.content_fetcher.ContentFetcher')
    def test_refresh_content_failure(self, mock_fetcher_class, db):
        """Test failed content refresh."""
        # Setup mock
        mock_fetcher = Mock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.fetch_and_process.return_value = {
            "success": False,
            "error": "Connection timeout",
            "status_code": 0
        }

        result = db.refresh_content(1)

        assert result["success"] is False
        assert "error" in result

        # Verify bookmark marked as unreachable
        bookmark = db.get(id=1)
        assert bookmark.reachable is False

    def test_refresh_content_nonexistent_bookmark(self, db):
        """Test refreshing non-existent bookmark."""
        result = db.refresh_content(999)

        assert result["success"] is False
        assert result["error"] == "Bookmark not found"

    @patch('btk.content_fetcher.ContentFetcher')
    def test_refresh_content_creates_cache(self, mock_fetcher_class, db):
        """Test that content refresh creates cache entry."""
        # Setup mock
        mock_fetcher = Mock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.fetch_and_process.return_value = {
            "success": True,
            "title": "Title",
            "html_content": b"html",
            "markdown_content": "markdown",
            "content_hash": "hash",
            "content_length": 100,
            "compressed_size": 50,
            "status_code": 200,
            "response_time_ms": 50,
            "content_type": "text/html",
            "encoding": "utf-8"
        }

        db.refresh_content(1)

        # Verify cache was created
        with db.session() as session:
            cache = session.execute(
                select(ContentCache).where(ContentCache.bookmark_id == 1)
            ).scalar_one_or_none()

            assert cache is not None
            assert cache.content_hash == "hash"


class TestDatabaseHelperMethods:
    """Test Database helper methods."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_get_or_create_tags_creates_new(self, db):
        """Test _get_or_create_tags creates new tags."""
        with db.session() as session:
            tags = db._get_or_create_tags(session, ["new1", "new2"])

            assert len(tags) == 2
            assert tags[0].name == "new1"
            assert tags[1].name == "new2"

    def test_get_or_create_tags_reuses_existing(self, db):
        """Test _get_or_create_tags reuses existing tags."""
        # Create a tag first
        db.add(url="https://example.com", title="Example", tags=["existing"])

        with db.session() as session:
            tags = db._get_or_create_tags(session, ["existing", "new"])

            assert len(tags) == 2
            # Commit the session to persist the new tag
            session.commit()

        # Verify both tags exist after commit
        with db.session() as session:
            all_tags = session.execute(select(Tag)).scalars().all()
            assert len(all_tags) == 2

    @patch('requests.get')
    def test_fetch_title_success(self, mock_get, db):
        """Test _fetch_title successfully fetches title."""
        # Mock response
        mock_response = Mock()
        mock_response.text = "<html><head><title>Test Title</title></head></html>"
        mock_get.return_value = mock_response

        title = db._fetch_title("https://example.com")

        assert title == "Test Title"

    @patch('requests.get')
    def test_fetch_title_no_title_tag(self, mock_get, db):
        """Test _fetch_title returns None when no title tag."""
        # Mock response
        mock_response = Mock()
        mock_response.text = "<html><head></head></html>"
        mock_get.return_value = mock_response

        title = db._fetch_title("https://example.com")

        assert title is None

    @patch('requests.get')
    def test_fetch_title_handles_exception(self, mock_get, db):
        """Test _fetch_title handles exceptions gracefully."""
        mock_get.side_effect = Exception("Network error")

        title = db._fetch_title("https://example.com")

        assert title is None


class TestGetDbFunction:
    """Test the global get_db() function."""

    def test_get_db_creates_singleton(self):
        """Test that get_db creates a singleton instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            db1 = get_db(path=db_path)
            db2 = get_db()

            assert db1 is db2

    def test_get_db_reload_creates_new(self):
        """Test that reload=True creates new instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            db1 = get_db(path=db_path)
            db2 = get_db(reload=True)

            assert db1 is not db2

    def test_get_db_new_path_creates_new(self):
        """Test that new path creates new instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path1 = os.path.join(tmpdir, "test1.db")
            db_path2 = os.path.join(tmpdir, "test2.db")

            db1 = get_db(path=db_path1)
            db2 = get_db(path=db_path2)

            assert db1 is not db2


class TestDatabaseSessionContextManager:
    """Test Database.session() context manager."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_session_commits_on_success(self, db):
        """Test that session commits on successful completion."""
        with db.session() as session:
            bookmark = Bookmark(
                url="https://example.com",
                title="Example",
                unique_id="test1234"
            )
            session.add(bookmark)

        # Verify bookmark was committed
        bookmarks = db.all()
        assert len(bookmarks) == 1

    def test_session_rolls_back_on_exception(self, db):
        """Test that session rolls back on exception."""
        try:
            with db.session() as session:
                bookmark = Bookmark(
                    url="https://example.com",
                    title="Example",
                    unique_id="test1234"
                )
                session.add(bookmark)
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify bookmark was not committed
        bookmarks = db.all()
        assert len(bookmarks) == 0

    def test_session_expire_on_commit_false(self, db):
        """Test that expire_on_commit=False keeps objects accessible."""
        with db.session(expire_on_commit=False) as session:
            bookmark = Bookmark(
                url="https://example.com",
                title="Example",
                unique_id="test1234"
            )
            session.add(bookmark)

        # Object should still be accessible after commit
        assert bookmark.title == "Example"
