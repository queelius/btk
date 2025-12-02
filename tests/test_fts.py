"""Tests for the Full-Text Search module."""
import pytest
import tempfile
import sqlite3
from pathlib import Path

from btk.fts import FTSIndex, SearchResult, get_fts_index


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_basic_result(self):
        """Test creating a basic search result."""
        result = SearchResult(
            bookmark_id=1,
            url="https://example.com",
            title="Example Title",
            description="Example description",
            rank=1.5
        )
        assert result.bookmark_id == 1
        assert result.url == "https://example.com"
        assert result.title == "Example Title"
        assert result.rank == 1.5
        assert result.snippet is None

    def test_result_with_snippet(self):
        """Test result with snippet."""
        result = SearchResult(
            bookmark_id=1,
            url="https://example.com",
            title="Test",
            description="",
            rank=2.0,
            snippet="...this is the <mark>search</mark> result..."
        )
        assert result.snippet is not None
        assert "<mark>" in result.snippet

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = SearchResult(
            bookmark_id=42,
            url="https://test.com",
            title="Test Title",
            description="Test desc",
            rank=3.5,
            snippet="test snippet"
        )
        d = result.to_dict()
        assert d['bookmark_id'] == 42
        assert d['url'] == "https://test.com"
        assert d['title'] == "Test Title"
        assert d['description'] == "Test desc"
        assert d['rank'] == 3.5
        assert d['snippet'] == "test snippet"


class TestFTSIndex:
    """Tests for FTSIndex class."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with test data."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        # Create schema and test data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create minimal bookmark schema
        cursor.execute("""
            CREATE TABLE bookmarks (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE bookmark_tags (
                bookmark_id INTEGER,
                tag_id INTEGER,
                FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE content_cache (
                id INTEGER PRIMARY KEY,
                bookmark_id INTEGER,
                markdown_content TEXT
            )
        """)

        # Insert test bookmarks
        cursor.execute("""
            INSERT INTO bookmarks (id, url, title, description) VALUES
            (1, 'https://python.org', 'Python Programming Language', 'The official Python website'),
            (2, 'https://docs.python.org', 'Python Documentation', 'Python docs and tutorials'),
            (3, 'https://rust-lang.org', 'Rust Programming Language', 'Memory-safe systems programming'),
            (4, 'https://example.com', 'Example Domain', 'Just an example site')
        """)

        # Insert tags
        cursor.execute("""
            INSERT INTO tags (id, name) VALUES
            (1, 'programming'),
            (2, 'python'),
            (3, 'rust'),
            (4, 'documentation')
        """)

        # Associate tags with bookmarks
        cursor.execute("""
            INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES
            (1, 1), (1, 2),
            (2, 1), (2, 2), (2, 4),
            (3, 1), (3, 3)
        """)

        # Insert content cache
        cursor.execute("""
            INSERT INTO content_cache (bookmark_id, markdown_content) VALUES
            (1, 'Python is a high-level programming language with dynamic semantics'),
            (2, 'Welcome to Python documentation. Learn Python programming here'),
            (3, 'Rust is a systems programming language focused on safety and performance')
        """)

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    def test_create_index(self, temp_db):
        """Test creating FTS index."""
        fts = FTSIndex(temp_db)
        result = fts.create_index()
        assert result is True

        # Verify table was created
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='bookmarks_fts'
        """)
        assert cursor.fetchone() is not None
        conn.close()

    def test_rebuild_index(self, temp_db):
        """Test rebuilding FTS index."""
        fts = FTSIndex(temp_db)

        progress_calls = []
        def progress_callback(current, total):
            progress_calls.append((current, total))

        count = fts.rebuild_index(progress_callback=progress_callback)

        assert count == 4  # 4 test bookmarks
        assert len(progress_calls) == 4

    def test_search_by_title(self, temp_db):
        """Test searching by title."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        results = fts.search("Python")
        assert len(results) >= 2
        # Should find both Python entries
        ids = [r.bookmark_id for r in results]
        assert 1 in ids  # Python Programming Language
        assert 2 in ids  # Python Documentation

    def test_search_by_content(self, temp_db):
        """Test searching in content."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        results = fts.search("dynamic semantics", in_content=True)
        assert len(results) >= 1
        assert results[0].bookmark_id == 1

    def test_search_ranking(self, temp_db):
        """Test that results are ranked by relevance."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        results = fts.search("programming")
        assert len(results) >= 2

        # All results should have a positive rank
        for result in results:
            assert result.rank >= 0

    def test_search_no_results(self, temp_db):
        """Test search with no results."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        results = fts.search("xyznonexistent")
        assert len(results) == 0

    def test_search_empty_query(self, temp_db):
        """Test search with empty query."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        results = fts.search("")
        assert len(results) == 0

        results = fts.search("   ")
        assert len(results) == 0

    def test_search_prefix_matching(self, temp_db):
        """Test prefix matching (pyth* should match python)."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        results = fts.search("pyth*")
        assert len(results) >= 2

    def test_search_phrase(self, temp_db):
        """Test phrase searching."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        results = fts.search('"Python Programming"')
        assert len(results) >= 1

    def test_index_single_bookmark(self, temp_db):
        """Test indexing a single bookmark."""
        fts = FTSIndex(temp_db)
        fts.create_index()

        # Add a new bookmark to the database
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bookmarks (id, url, title, description)
            VALUES (5, 'https://golang.org', 'Go Programming Language', 'Go is a statically typed language')
        """)
        conn.commit()
        conn.close()

        # Index just the new bookmark
        result = fts.index_bookmark(5)
        assert result is True

        # Verify it's searchable
        results = fts.search("golang")
        assert len(results) >= 1
        assert results[0].bookmark_id == 5

    def test_remove_bookmark(self, temp_db):
        """Test removing a bookmark from the index."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        # Verify bookmark is searchable
        results = fts.search("rust")
        rust_found = any(r.bookmark_id == 3 for r in results)
        assert rust_found

        # Remove it
        result = fts.remove_bookmark(3)
        assert result is True

        # Verify it's no longer searchable
        results = fts.search("rust")
        rust_found = any(r.bookmark_id == 3 for r in results)
        assert not rust_found

    def test_get_stats(self, temp_db):
        """Test getting index statistics."""
        fts = FTSIndex(temp_db)

        # Before building
        stats = fts.get_stats()
        assert stats['exists'] is False

        # After building
        fts.rebuild_index()
        stats = fts.get_stats()
        assert stats['exists'] is True
        assert stats['documents'] == 4
        assert stats['table_name'] == 'bookmarks_fts'

    def test_drop_index(self, temp_db):
        """Test dropping the FTS index."""
        fts = FTSIndex(temp_db)
        fts.rebuild_index()

        # Verify it exists
        stats = fts.get_stats()
        assert stats['exists'] is True

        # Drop it
        result = fts.drop_index()
        assert result is True

        # Verify it's gone
        stats = fts.get_stats()
        assert stats['exists'] is False


class TestFTSQueryPrepare:
    """Tests for query preparation."""

    @pytest.fixture
    def fts(self):
        """Create an FTSIndex instance with a temp db."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        return FTSIndex(db_path)

    def test_simple_word_gets_prefix(self, fts):
        """Single word should get prefix matching."""
        result = fts._prepare_query("python")
        assert result == "python*"

    def test_phrase_preserved(self, fts):
        """Phrase queries should be preserved."""
        result = fts._prepare_query('"exact phrase"')
        assert result == '"exact phrase"'

    def test_operators_preserved(self, fts):
        """FTS operators should be preserved."""
        result = fts._prepare_query("python AND web")
        assert result == "python AND web"

        result = fts._prepare_query("python OR ruby")
        assert result == "python OR ruby"

    def test_multiple_words_get_prefix(self, fts):
        """Multiple words should each get prefix matching."""
        result = fts._prepare_query("python web")
        assert "python*" in result
        assert "web*" in result


class TestGetFTSIndex:
    """Tests for get_fts_index function."""

    def test_returns_fts_index(self):
        """Test that get_fts_index returns an FTSIndex."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        fts = get_fts_index(db_path)
        assert isinstance(fts, FTSIndex)
        assert fts.db_path == db_path

        Path(db_path).unlink(missing_ok=True)


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_db_build_index_help(self):
        """Test db build-index command is registered."""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'btk.cli', 'db', 'build-index', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

    def test_db_index_stats_help(self):
        """Test db index-stats command is registered."""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'btk.cli', 'db', 'index-stats', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

    def test_search_fts_flag(self):
        """Test search --fts flag is registered."""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'btk.cli', 'bookmark', 'search', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert '--fts' in result.stdout
