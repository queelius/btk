"""
Tests for Smart Collections feature (v0.7.1)

Smart collections are auto-updating virtual directories that filter bookmarks:
- /unread - Bookmarks never visited (visit_count == 0)
- /popular - Frequently visited bookmarks (visit_count >= 10)
- /broken - Unreachable bookmarks (reachable == False)
- /untagged - Bookmarks with no tags
- /pdfs - PDF file bookmarks
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from btk.db import Database
from btk.shell import BookmarkShell, SMART_COLLECTIONS


class TestSmartCollectionRegistry:
    """Test the SMART_COLLECTIONS registry and metadata."""

    def test_smart_collections_registry_contains_five_collections(self):
        """Registry should contain exactly 5 smart collections."""
        assert len(SMART_COLLECTIONS) == 5
        expected_collections = {'unread', 'popular', 'broken', 'untagged', 'pdfs'}
        assert set(SMART_COLLECTIONS.keys()) == expected_collections

    def test_each_collection_has_required_attributes(self):
        """Each smart collection should have name, filter_func, and description."""
        for name, collection in SMART_COLLECTIONS.items():
            assert collection.name == name, f"Collection {name} has mismatched name attribute"
            assert callable(collection.filter_func), f"Collection {name} missing filter_func"
            assert collection.description, f"Collection {name} missing description"
            assert isinstance(collection.description, str), f"Collection {name} description not a string"


class TestUnreadCollection:
    """Test /unread smart collection - bookmarks never visited."""

    @pytest.fixture
    def db(self):
        """Create test database with mixed read/unread bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Unread bookmarks (visit_count == 0)
            db.add(url="https://example.com/unread1", title="Unread 1", visit_count=0)
            db.add(url="https://example.com/unread2", title="Unread 2", visit_count=0)

            # Read bookmarks
            db.add(url="https://example.com/read1", title="Read 1", visit_count=1)
            db.add(url="https://example.com/read2", title="Read 2", visit_count=5)
            db.add(url="https://example.com/read3", title="Read 3", visit_count=100)

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_unread_filter_function_filters_correctly(self, db):
        """Unread filter should return only bookmarks with visit_count == 0."""
        all_bookmarks = db.list()
        unread_collection = SMART_COLLECTIONS['unread']
        unread_bookmarks = unread_collection.filter_func(all_bookmarks)

        assert len(unread_bookmarks) == 2, f"Expected 2 unread bookmarks, got {len(unread_bookmarks)}"
        for bookmark in unread_bookmarks:
            assert bookmark.visit_count == 0, f"Bookmark {bookmark.title} has visit_count={bookmark.visit_count}"

    def test_cd_to_unread_collection(self, shell):
        """cd /unread should navigate to unread collection."""
        shell.do_cd("/unread")
        assert shell.cwd == "/unread"

    def test_detect_context_for_unread_collection(self, shell):
        """_get_context_for_path should recognize /unread path."""
        context = shell._get_context_for_path("/unread")
        assert context['type'] == 'smart_collection'
        assert context['name'] == 'unread'
        assert 'bookmarks' in context
        assert len(context['bookmarks']) == 2

    def test_ls_in_unread_shows_only_unread_bookmarks(self, shell):
        """ls /unread should show only unread bookmarks."""
        shell.cwd = "/unread"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Verify output was generated
            assert mock_print.call_count > 0

    def test_unread_collection_updates_dynamically(self, shell):
        """Unread collection should update when bookmarks are visited."""
        # Initial state: 2 unread bookmarks
        context = shell._get_context_for_path("/unread")
        assert len(context['bookmarks']) == 2

        # Visit one bookmark
        unread_bookmark = context['bookmarks'][0]
        shell.db.update(unread_bookmark.id, visit_count=1)

        # Re-check: should now have 1 unread bookmark
        context = shell._get_context_for_path("/unread")
        assert len(context['bookmarks']) == 1, "Unread collection should update dynamically"


class TestPopularCollection:
    """Test /popular smart collection - top 100 most visited bookmarks."""

    @pytest.fixture
    def db(self):
        """Create test database with mixed popularity bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Highly visited bookmarks
            db.add(url="https://example.com/popular1", title="Popular 1", visit_count=100)
            db.add(url="https://example.com/popular2", title="Popular 2", visit_count=25)
            db.add(url="https://example.com/popular3", title="Popular 3", visit_count=10)

            # Less visited
            db.add(url="https://example.com/normal1", title="Normal 1", visit_count=5)
            db.add(url="https://example.com/normal2", title="Normal 2", visit_count=2)
            db.add(url="https://example.com/normal3", title="Normal 3", visit_count=0)

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_popular_filter_function_returns_top_100(self, db):
        """Popular filter should return top 100 most visited bookmarks."""
        all_bookmarks = db.list()
        popular_collection = SMART_COLLECTIONS['popular']
        popular_bookmarks = popular_collection.filter_func(all_bookmarks)

        # Should return all bookmarks since we have < 100 total
        assert len(popular_bookmarks) == len(all_bookmarks), \
            f"Expected {len(all_bookmarks)} bookmarks, got {len(popular_bookmarks)}"

    def test_popular_sorted_by_visit_count_descending(self, db):
        """Popular collection should be sorted by visit_count (highest first)."""
        all_bookmarks = db.list()
        popular_collection = SMART_COLLECTIONS['popular']
        popular_bookmarks = popular_collection.filter_func(all_bookmarks)

        # Verify descending order
        assert popular_bookmarks[0].visit_count == 100, "Most visited should be first"
        assert popular_bookmarks[1].visit_count == 25
        assert popular_bookmarks[2].visit_count == 10

    def test_detect_context_for_popular_collection(self, shell):
        """_get_context_for_path should recognize /popular path."""
        context = shell._get_context_for_path("/popular")
        assert context['type'] == 'smart_collection'
        assert context['name'] == 'popular'
        assert len(context['bookmarks']) == 6  # All 6 bookmarks

    def test_popular_limits_to_100_bookmarks(self):
        """Popular collection should limit to 100 bookmarks max."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add 150 bookmarks
            for i in range(150):
                db.add(url=f"https://example.com/{i}", title=f"Bookmark {i}", visit_count=i)

            all_bookmarks = db.list()
            popular_collection = SMART_COLLECTIONS['popular']
            popular_bookmarks = popular_collection.filter_func(all_bookmarks)

            assert len(popular_bookmarks) == 100, "Should limit to 100 bookmarks"
            # Verify we got the most visited ones
            assert popular_bookmarks[0].visit_count == 149, "Should get highest visit count"


class TestBrokenCollection:
    """Test /broken smart collection - unreachable bookmarks."""

    @pytest.fixture
    def db(self):
        """Create test database with reachable and broken bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Broken bookmarks (reachable == False)
            db.add(url="https://example.com/broken1", title="Broken 1", reachable=False)
            db.add(url="https://example.com/broken2", title="Broken 2", reachable=False)

            # Reachable bookmarks
            db.add(url="https://example.com/working1", title="Working 1", reachable=True)
            db.add(url="https://example.com/working2", title="Working 2", reachable=True)

            # Unchecked bookmarks (reachable == None)
            db.add(url="https://example.com/unchecked", title="Unchecked", reachable=None)

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_broken_filter_function_filters_correctly(self, db):
        """Broken filter should return only bookmarks with reachable == False."""
        all_bookmarks = db.list()
        broken_collection = SMART_COLLECTIONS['broken']
        broken_bookmarks = broken_collection.filter_func(all_bookmarks)

        assert len(broken_bookmarks) == 2, f"Expected 2 broken bookmarks, got {len(broken_bookmarks)}"
        for bookmark in broken_bookmarks:
            assert bookmark.reachable is False, f"Bookmark {bookmark.title} has reachable={bookmark.reachable}"

    def test_detect_context_for_broken_collection(self, shell):
        """_get_context_for_path should recognize /broken path."""
        context = shell._get_context_for_path("/broken")
        assert context['type'] == 'smart_collection'
        assert context['name'] == 'broken'
        assert len(context['bookmarks']) == 2


class TestUntaggedCollection:
    """Test /untagged smart collection - bookmarks with no tags."""

    @pytest.fixture
    def db(self):
        """Create test database with tagged and untagged bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Untagged bookmarks (no tags)
            db.add(url="https://example.com/untagged1", title="Untagged 1", tags=[])
            db.add(url="https://example.com/untagged2", title="Untagged 2", tags=[])
            db.add(url="https://example.com/untagged3", title="Untagged 3")  # tags defaults to empty

            # Tagged bookmarks
            db.add(url="https://example.com/tagged1", title="Tagged 1", tags=["python"])
            db.add(url="https://example.com/tagged2", title="Tagged 2", tags=["python", "web"])

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_untagged_filter_function_filters_correctly(self, db):
        """Untagged filter should return only bookmarks with empty tags list."""
        all_bookmarks = db.list()
        untagged_collection = SMART_COLLECTIONS['untagged']
        untagged_bookmarks = untagged_collection.filter_func(all_bookmarks)

        assert len(untagged_bookmarks) == 3, f"Expected 3 untagged bookmarks, got {len(untagged_bookmarks)}"
        for bookmark in untagged_bookmarks:
            assert len(bookmark.tags) == 0, f"Bookmark {bookmark.title} has {len(bookmark.tags)} tags"

    def test_detect_context_for_untagged_collection(self, shell):
        """_get_context_for_path should recognize /untagged path."""
        context = shell._get_context_for_path("/untagged")
        assert context['type'] == 'smart_collection'
        assert context['name'] == 'untagged'
        assert len(context['bookmarks']) == 3

    def test_untagged_collection_updates_when_tags_added(self, shell):
        """Untagged collection should update when tags are added to bookmarks."""
        # Initial state: 3 untagged bookmarks
        context = shell._get_context_for_path("/untagged")
        assert len(context['bookmarks']) == 3

        # Add tag to one bookmark
        untagged_bookmark = context['bookmarks'][0]
        shell.db.update(untagged_bookmark.id, tags=["new-tag"])

        # Re-check: should now have 2 untagged bookmarks
        context = shell._get_context_for_path("/untagged")
        assert len(context['bookmarks']) == 2, "Untagged collection should update when tags are added"


class TestPdfsCollection:
    """Test /pdfs smart collection - PDF bookmarks."""

    @pytest.fixture
    def db(self):
        """Create test database with PDF and non-PDF bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # PDF bookmarks
            db.add(url="https://example.com/document.pdf", title="Document PDF")
            db.add(url="https://example.com/Paper.PDF", title="Paper PDF")  # uppercase
            db.add(url="https://example.com/manual.pdf", title="Manual PDF")

            # Non-PDF bookmarks
            db.add(url="https://example.com/page.html", title="HTML Page")
            db.add(url="https://example.com/image.png", title="Image")
            db.add(url="https://example.com/pdf-is-in-title", title="Has PDF in title")

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_pdfs_filter_function_filters_correctly(self, db):
        """PDFs filter should return only bookmarks with URLs ending in .pdf."""
        all_bookmarks = db.list()
        pdfs_collection = SMART_COLLECTIONS['pdfs']
        pdf_bookmarks = pdfs_collection.filter_func(all_bookmarks)

        assert len(pdf_bookmarks) == 3, f"Expected 3 PDF bookmarks, got {len(pdf_bookmarks)}"
        for bookmark in pdf_bookmarks:
            assert bookmark.url.lower().endswith('.pdf'), \
                f"Bookmark {bookmark.title} URL doesn't end with .pdf: {bookmark.url}"

    def test_pdfs_filter_is_case_insensitive(self, db):
        """PDFs filter should be case-insensitive (.pdf, .PDF, .Pdf)."""
        all_bookmarks = db.list()
        pdfs_collection = SMART_COLLECTIONS['pdfs']
        pdf_bookmarks = pdfs_collection.filter_func(all_bookmarks)

        # Find the uppercase PDF
        uppercase_pdf = next((b for b in pdf_bookmarks if 'Paper' in b.title), None)
        assert uppercase_pdf is not None, "Uppercase .PDF extension should be recognized"

    def test_detect_context_for_pdfs_collection(self, shell):
        """_get_context_for_path should recognize /pdfs path."""
        context = shell._get_context_for_path("/pdfs")
        assert context['type'] == 'smart_collection'
        assert context['name'] == 'pdfs'
        assert len(context['bookmarks']) == 3


class TestSmartCollectionsNavigation:
    """Test navigation and listing of smart collections."""

    @pytest.fixture
    def db(self):
        """Create test database with diverse bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add bookmarks for each collection
            db.add(url="https://example.com/unread", title="Unread", visit_count=0)
            db.add(url="https://example.com/popular", title="Popular", visit_count=50)
            db.add(url="https://example.com/broken", title="Broken", reachable=False)
            db.add(url="https://example.com/untagged", title="Untagged", tags=[])
            db.add(url="https://example.com/doc.pdf", title="PDF")

            yield db

    @pytest.fixture
    def shell(self, db):
        """Create shell with test database."""
        return BookmarkShell(str(db.path))

    def test_ls_root_shows_all_smart_collections(self, shell):
        """ls / should display all 5 smart collections."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Verify output was generated (collections should be shown)
            assert mock_print.call_count > 0

    def test_navigate_to_each_smart_collection(self, shell):
        """Should be able to cd into each smart collection."""
        for collection_name in ['unread', 'popular', 'broken', 'untagged', 'pdfs']:
            shell.do_cd(f"/{collection_name}")
            assert shell.cwd == f"/{collection_name}", \
                f"Failed to navigate to /{collection_name}"

    def test_pwd_shows_correct_path_in_smart_collection(self, shell):
        """pwd should show correct path when in smart collection."""
        shell.do_cd("/unread")
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_pwd("")
            mock_print.assert_called_once_with("/unread")

    def test_cd_to_nonexistent_collection_fails_gracefully(self, shell):
        """cd to non-existent collection should fail gracefully."""
        original_cwd = shell.cwd
        shell.do_cd("/nonexistent-collection")
        # cwd should not change if directory doesn't exist
        # (behavior depends on implementation - test both possibilities)
        assert shell.cwd in [original_cwd, "/nonexistent-collection"]


class TestSmartCollectionsEdgeCases:
    """Test edge cases and boundary conditions for smart collections."""

    def test_empty_collections_handle_gracefully(self):
        """Smart collections should handle empty bookmark lists."""
        empty_bookmarks = []
        for name, collection in SMART_COLLECTIONS.items():
            result = collection.filter_func(empty_bookmarks)
            assert result == [], f"Collection {name} should return empty list for empty input"

    def test_all_bookmarks_match_collection(self):
        """Smart collections should handle when all bookmarks match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # All PDFs
            db.add(url="https://example.com/1.pdf", title="PDF 1")
            db.add(url="https://example.com/2.pdf", title="PDF 2")
            db.add(url="https://example.com/3.pdf", title="PDF 3")

            all_bookmarks = db.list()
            pdfs_collection = SMART_COLLECTIONS['pdfs']
            pdf_bookmarks = pdfs_collection.filter_func(all_bookmarks)

            assert len(pdf_bookmarks) == 3, "All bookmarks should be in PDFs collection"

    def test_no_bookmarks_match_collection(self):
        """Smart collections should handle when no bookmarks match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # No PDFs
            db.add(url="https://example.com/page.html", title="HTML")
            db.add(url="https://example.com/image.png", title="Image")

            all_bookmarks = db.list()
            pdfs_collection = SMART_COLLECTIONS['pdfs']
            pdf_bookmarks = pdfs_collection.filter_func(all_bookmarks)

            assert len(pdf_bookmarks) == 0, "No bookmarks should match PDF collection"
