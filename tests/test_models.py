"""
Comprehensive tests for btk/models.py

Tests SQLAlchemy models including:
- Bookmark model with all fields and properties
- Tag model with hierarchical functionality
- BookmarkHealth model and health score calculation
- Collection model
- ContentCache model and compression ratio
- Many-to-many relationships
"""
import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from btk.models import (
    Base, Bookmark, Tag, BookmarkHealth, Collection, ContentCache,
    bookmark_tags, bookmark_collections
)


class TestBookmarkModel:
    """Test Bookmark model."""

    @pytest.fixture
    def session(self):
        """Create a temporary database session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            yield session
            session.close()

    def test_create_basic_bookmark(self, session):
        """Test creating a basic bookmark."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example Site"
        )
        session.add(bookmark)
        session.commit()

        assert bookmark.id is not None
        assert bookmark.unique_id == "test1234"
        assert bookmark.url == "https://example.com"
        assert bookmark.title == "Example Site"

    def test_bookmark_defaults(self, session):
        """Test bookmark default values."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        assert bookmark.description == ''
        assert bookmark.visit_count == 0
        assert bookmark.stars is False
        assert bookmark.archived is False
        assert bookmark.pinned is False
        assert bookmark.reachable is None
        assert bookmark.added is not None
        assert bookmark.last_visited is None

    def test_bookmark_with_all_fields(self, session):
        """Test bookmark with all optional fields."""
        now = datetime.now(timezone.utc)
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example",
            description="Test description",
            visit_count=10,
            stars=True,
            archived=True,
            pinned=True,
            reachable=True,
            last_visited=now,
            favicon_path="/path/to/favicon.ico",
            favicon_data=b"fake icon data",
            favicon_mime_type="image/x-icon",
            extra_data={"key": "value"}
        )
        session.add(bookmark)
        session.commit()

        assert bookmark.description == "Test description"
        assert bookmark.visit_count == 10
        assert bookmark.stars is True
        assert bookmark.archived is True
        assert bookmark.pinned is True
        assert bookmark.reachable is True
        # SQLite doesn't preserve timezone info, so just check the timestamp is close
        assert bookmark.last_visited is not None
        assert bookmark.favicon_path == "/path/to/favicon.ico"
        assert bookmark.favicon_data == b"fake icon data"
        assert bookmark.favicon_mime_type == "image/x-icon"
        assert bookmark.extra_data == {"key": "value"}

    def test_bookmark_domain_property(self, session):
        """Test domain hybrid property."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://docs.python.org/3/library/index.html",
            title="Python Docs"
        )
        session.add(bookmark)
        session.commit()

        assert bookmark.domain == "docs.python.org"

    def test_bookmark_tag_names_property(self, session):
        """Test tag_names hybrid property."""
        tag1 = Tag(name="python")
        tag2 = Tag(name="programming")

        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example",
            tags=[tag1, tag2]
        )
        session.add(bookmark)
        session.commit()

        tag_names = bookmark.tag_names
        assert "python" in tag_names
        assert "programming" in tag_names
        assert len(tag_names) == 2

    def test_bookmark_tags_relationship(self, session):
        """Test many-to-many tags relationship."""
        tag1 = Tag(name="python")
        tag2 = Tag(name="web")

        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example",
            tags=[tag1, tag2]
        )
        session.add(bookmark)
        session.commit()

        # Refresh and check relationship
        session.refresh(bookmark)
        assert len(bookmark.tags) == 2
        assert tag1 in bookmark.tags
        assert tag2 in bookmark.tags

    def test_bookmark_unique_url_constraint(self, session):
        """Test that URLs must be unique."""
        bookmark1 = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="First"
        )
        bookmark2 = Bookmark(
            unique_id="test5678",
            url="https://example.com",  # Duplicate URL
            title="Second"
        )
        session.add(bookmark1)
        session.commit()

        session.add(bookmark2)
        with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
            session.commit()

    def test_bookmark_repr(self, session):
        """Test bookmark string representation."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example Site"
        )
        session.add(bookmark)
        session.commit()

        repr_str = repr(bookmark)
        assert "Bookmark" in repr_str
        assert str(bookmark.id) in repr_str
        assert "Example Site" in repr_str


class TestTagModel:
    """Test Tag model."""

    @pytest.fixture
    def session(self):
        """Create a temporary database session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            yield session
            session.close()

    def test_create_basic_tag(self, session):
        """Test creating a basic tag."""
        tag = Tag(name="python")
        session.add(tag)
        session.commit()

        assert tag.id is not None
        assert tag.name == "python"

    def test_tag_with_description_and_color(self, session):
        """Test tag with optional fields."""
        tag = Tag(
            name="python",
            description="Python programming language",
            color="#3776AB"
        )
        session.add(tag)
        session.commit()

        assert tag.description == "Python programming language"
        assert tag.color == "#3776AB"

    def test_tag_hierarchy_level(self, session):
        """Test hierarchy_level property."""
        tag1 = Tag(name="python")
        tag2 = Tag(name="programming/python")
        tag3 = Tag(name="programming/python/web")

        session.add_all([tag1, tag2, tag3])
        session.commit()

        assert tag1.hierarchy_level == 0
        assert tag2.hierarchy_level == 1
        assert tag3.hierarchy_level == 2

    def test_tag_parent_path(self, session):
        """Test parent_path property."""
        tag1 = Tag(name="python")
        tag2 = Tag(name="programming/python")
        tag3 = Tag(name="programming/python/web")

        session.add_all([tag1, tag2, tag3])
        session.commit()

        assert tag1.parent_path is None
        assert tag2.parent_path == "programming"
        assert tag3.parent_path == "programming/python"

    def test_tag_leaf_name(self, session):
        """Test leaf_name property."""
        tag1 = Tag(name="python")
        tag2 = Tag(name="programming/python")
        tag3 = Tag(name="programming/python/web")

        session.add_all([tag1, tag2, tag3])
        session.commit()

        assert tag1.leaf_name == "python"
        assert tag2.leaf_name == "python"
        assert tag3.leaf_name == "web"

    def test_tag_bookmark_count(self, session):
        """Test bookmark_count property."""
        tag = Tag(name="python")
        bookmark1 = Bookmark(
            unique_id="test1234",
            url="https://example1.com",
            title="Example 1",
            tags=[tag]
        )
        bookmark2 = Bookmark(
            unique_id="test5678",
            url="https://example2.com",
            title="Example 2",
            tags=[tag]
        )

        session.add_all([bookmark1, bookmark2])
        session.commit()

        # Refresh to ensure relationship is loaded
        session.refresh(tag)
        assert tag.bookmark_count == 2

    def test_tag_bookmarks_relationship(self, session):
        """Test many-to-many bookmarks relationship."""
        tag = Tag(name="python")
        bookmark1 = Bookmark(
            unique_id="test1234",
            url="https://example1.com",
            title="Example 1"
        )
        bookmark2 = Bookmark(
            unique_id="test5678",
            url="https://example2.com",
            title="Example 2"
        )

        tag.bookmarks.append(bookmark1)
        tag.bookmarks.append(bookmark2)

        session.add(tag)
        session.commit()

        # Check relationship
        session.refresh(tag)
        assert tag.bookmarks.count() == 2

    def test_tag_unique_name_constraint(self, session):
        """Test that tag names must be unique."""
        tag1 = Tag(name="python")
        tag2 = Tag(name="python")  # Duplicate

        session.add(tag1)
        session.commit()

        session.add(tag2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_tag_created_at(self, session):
        """Test created_at timestamp."""
        tag = Tag(name="python")
        session.add(tag)
        session.commit()

        assert tag.created_at is not None
        assert isinstance(tag.created_at, datetime)

    def test_tag_repr(self, session):
        """Test tag string representation."""
        tag = Tag(name="python")
        session.add(tag)
        session.commit()

        repr_str = repr(tag)
        assert "Tag" in repr_str
        assert str(tag.id) in repr_str
        assert "python" in repr_str


class TestBookmarkHealthModel:
    """Test BookmarkHealth model."""

    @pytest.fixture
    def session(self):
        """Create a temporary database session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            yield session
            session.close()

    def test_create_bookmark_health(self, session):
        """Test creating bookmark health record."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            status_code=200,
            response_time_ms=150.5
        )
        session.add(health)
        session.commit()

        assert health.id is not None
        assert health.bookmark_id == bookmark.id
        assert health.status_code == 200
        assert health.response_time_ms == 150.5

    def test_calculate_health_score_perfect(self, session):
        """Test health score calculation for perfect health."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            status_code=200,
            response_time_ms=100,
            last_check=datetime.now(timezone.utc)
        )

        score = health.calculate_health_score()
        assert score == 100.0

    def test_calculate_health_score_bad_status(self, session):
        """Test health score with bad HTTP status."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            status_code=404,
            response_time_ms=100,
            last_check=datetime.now(timezone.utc)
        )

        score = health.calculate_health_score()
        assert score == 50.0  # 100 - 50 for 404

    def test_calculate_health_score_redirect(self, session):
        """Test health score with redirect status."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            status_code=301,
            response_time_ms=100,
            last_check=datetime.now(timezone.utc)
        )

        score = health.calculate_health_score()
        assert score == 90.0  # 100 - 10 for redirect

    def test_calculate_health_score_slow_response(self, session):
        """Test health score with slow response."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            status_code=200,
            response_time_ms=6000,  # Very slow
            last_check=datetime.now(timezone.utc)
        )

        score = health.calculate_health_score()
        assert score == 80.0  # 100 - 20 for very slow

    def test_calculate_health_score_stale_check(self, session):
        """Test health score with stale check."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        # 60 days old
        old_check = datetime.now(timezone.utc) - timedelta(days=60)
        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            status_code=200,
            response_time_ms=100,
            last_check=old_check
        )

        score = health.calculate_health_score()
        # 100 - 20 (for 30+ days old, capped at 20)
        assert score == 80.0

    def test_calculate_health_score_minimum_zero(self, session):
        """Test that health score doesn't go below zero."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        # All bad factors
        very_old = datetime.now(timezone.utc) - timedelta(days=100)
        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            status_code=500,
            response_time_ms=10000,
            last_check=very_old
        )

        score = health.calculate_health_score()
        assert score >= 0.0

    def test_bookmark_health_relationship(self, session):
        """Test relationship with bookmark."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        health = BookmarkHealth(
            bookmark_id=None,  # Will be set by relationship
            status_code=200
        )
        health.bookmark = bookmark

        session.add(health)
        session.commit()

        # Check relationship works both ways
        assert health.bookmark == bookmark
        # Note: bookmark.health is a list due to backref, not uselist=False
        assert health in bookmark.health or bookmark.health == health

    def test_bookmark_health_repr(self, session):
        """Test health record string representation."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        health = BookmarkHealth(
            bookmark_id=bookmark.id,
            health_score=85.5
        )
        session.add(health)
        session.commit()

        repr_str = repr(health)
        assert "BookmarkHealth" in repr_str
        assert str(bookmark.id) in repr_str
        assert "85.5" in repr_str


class TestCollectionModel:
    """Test Collection model."""

    @pytest.fixture
    def session(self):
        """Create a temporary database session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            yield session
            session.close()

    def test_create_basic_collection(self, session):
        """Test creating a basic collection."""
        collection = Collection(name="Python Resources")
        session.add(collection)
        session.commit()

        assert collection.id is not None
        assert collection.name == "Python Resources"

    def test_collection_with_all_fields(self, session):
        """Test collection with all optional fields."""
        collection = Collection(
            name="Python Resources",
            description="Collection of Python learning resources",
            is_public=True,
            auto_query="tags contains 'python'"
        )
        session.add(collection)
        session.commit()

        assert collection.description == "Collection of Python learning resources"
        assert collection.is_public is True
        assert collection.auto_query == "tags contains 'python'"

    def test_collection_timestamps(self, session):
        """Test collection created_at and updated_at."""
        collection = Collection(name="Test")
        session.add(collection)
        session.commit()

        assert collection.created_at is not None
        assert collection.updated_at is not None
        assert isinstance(collection.created_at, datetime)

    def test_collection_bookmarks_relationship(self, session):
        """Test many-to-many bookmarks relationship."""
        collection = Collection(name="Favorites")
        bookmark1 = Bookmark(
            unique_id="test1234",
            url="https://example1.com",
            title="Example 1",
            collections=[collection]
        )
        bookmark2 = Bookmark(
            unique_id="test5678",
            url="https://example2.com",
            title="Example 2",
            collections=[collection]
        )

        session.add_all([bookmark1, bookmark2])
        session.commit()

        # Check relationship
        session.refresh(collection)
        assert len(collection.bookmarks) == 2

    def test_collection_repr(self, session):
        """Test collection string representation."""
        collection = Collection(name="Python Resources")
        session.add(collection)
        session.commit()

        repr_str = repr(collection)
        assert "Collection" in repr_str
        assert str(collection.id) in repr_str
        assert "Python Resources" in repr_str


class TestContentCacheModel:
    """Test ContentCache model."""

    @pytest.fixture
    def session(self):
        """Create a temporary database session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            yield session
            session.close()

    def test_create_content_cache(self, session):
        """Test creating content cache."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        cache = ContentCache(
            bookmark_id=bookmark.id,
            html_content=b"<html>compressed</html>",
            markdown_content="# Markdown content",
            content_hash="abc123",
            content_length=1000,
            compressed_size=500,
            status_code=200
        )
        session.add(cache)
        session.commit()

        assert cache.id is not None
        assert cache.bookmark_id == bookmark.id
        assert cache.html_content == b"<html>compressed</html>"
        assert cache.markdown_content == "# Markdown content"
        assert cache.content_hash == "abc123"

    def test_content_cache_with_metadata(self, session):
        """Test content cache with all metadata."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        cache = ContentCache(
            bookmark_id=bookmark.id,
            html_content=b"<html></html>",
            content_length=1000,
            compressed_size=500,
            status_code=200,
            response_time_ms=150.5,
            content_type="text/html",
            encoding="utf-8"
        )
        session.add(cache)
        session.commit()

        assert cache.status_code == 200
        assert cache.response_time_ms == 150.5
        assert cache.content_type == "text/html"
        assert cache.encoding == "utf-8"

    def test_compression_ratio(self, session):
        """Test compression ratio calculation."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        cache = ContentCache(
            bookmark_id=bookmark.id,
            html_content=b"test",
            content_length=1000,
            compressed_size=500
        )
        session.add(cache)
        session.commit()

        # Compression ratio = (1 - 500/1000) * 100 = 50%
        assert cache.compression_ratio == 50.0

    def test_compression_ratio_zero_length(self, session):
        """Test compression ratio with zero content length."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        cache = ContentCache(
            bookmark_id=bookmark.id,
            html_content=b"",
            content_length=0,
            compressed_size=0
        )
        session.add(cache)
        session.commit()

        assert cache.compression_ratio == 0.0

    def test_content_cache_bookmark_relationship(self, session):
        """Test one-to-one relationship with bookmark."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        cache = ContentCache(
            bookmark_id=None,
            html_content=b"test",
            content_length=100,
            compressed_size=50
        )
        cache.bookmark = bookmark

        session.add(cache)
        session.commit()

        # Check relationship
        assert cache.bookmark == bookmark
        assert bookmark.content_cache == cache

    def test_content_cache_fetched_at(self, session):
        """Test fetched_at timestamp."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        cache = ContentCache(
            bookmark_id=bookmark.id,
            html_content=b"test",
            content_length=100,
            compressed_size=50
        )
        session.add(cache)
        session.commit()

        assert cache.fetched_at is not None
        assert isinstance(cache.fetched_at, datetime)

    def test_content_cache_repr(self, session):
        """Test content cache string representation."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        session.add(bookmark)
        session.commit()

        cache = ContentCache(
            bookmark_id=bookmark.id,
            html_content=b"test",
            content_length=1000,
            compressed_size=500
        )
        session.add(cache)
        session.commit()

        repr_str = repr(cache)
        assert "ContentCache" in repr_str
        assert str(bookmark.id) in repr_str
        assert "1000" in repr_str
        assert "500" in repr_str


class TestCascadeDeletes:
    """Test cascade delete behavior."""

    @pytest.fixture
    def session(self):
        """Create a temporary database session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            yield session
            session.close()

    def test_delete_bookmark_cascades_to_content_cache(self, session):
        """Test that deleting bookmark deletes its content cache."""
        bookmark = Bookmark(
            unique_id="test1234",
            url="https://example.com",
            title="Example"
        )
        cache = ContentCache(
            bookmark_id=None,
            html_content=b"test",
            content_length=100,
            compressed_size=50
        )
        cache.bookmark = bookmark

        session.add(cache)
        session.commit()
        cache_id = cache.id

        # Delete bookmark
        session.delete(bookmark)
        session.commit()

        # Cache should be gone
        result = session.execute(
            select(ContentCache).where(ContentCache.id == cache_id)
        ).scalar_one_or_none()
        assert result is None
