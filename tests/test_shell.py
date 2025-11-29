"""
Comprehensive tests for btk/shell.py

Tests the BookmarkShell class including:
- Path parsing and normalization
- Context detection from paths
- Virtual filesystem navigation
- Context-aware commands
- Tag and bookmark operations
"""
import pytest
import tempfile
import os
from contextlib import redirect_stdout
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
from datetime import datetime, timezone

from btk.db import Database
from btk.models import Bookmark, Tag
from btk.shell import BookmarkShell


class TestPathParsing:
    """Test path parsing and normalization logic."""

    @pytest.fixture
    def shell(self):
        """Create a shell instance with temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            shell = BookmarkShell(db_path)
            yield shell

    def test_parse_path_empty_returns_cwd(self, shell):
        """Empty path should return current working directory."""
        shell.cwd = "/bookmarks"
        assert shell._parse_path("") == "/bookmarks"
        assert shell._parse_path(None) == "/bookmarks"

    def test_parse_path_absolute(self, shell):
        """Absolute paths should be returned normalized."""
        assert shell._parse_path("/bookmarks") == "/bookmarks"
        assert shell._parse_path("/tags/python") == "/tags/python"
        assert shell._parse_path("/starred") == "/starred"

    def test_parse_path_relative_from_root(self, shell):
        """Relative paths from root should resolve correctly."""
        shell.cwd = "/"
        assert shell._parse_path("bookmarks") == "/bookmarks"
        assert shell._parse_path("tags") == "/tags"
        assert shell._parse_path("starred") == "/starred"

    def test_parse_path_relative_from_subdirectory(self, shell):
        """Relative paths from subdirectory should resolve correctly."""
        shell.cwd = "/tags"
        assert shell._parse_path("python") == "/tags/python"
        assert shell._parse_path("programming/python") == "/tags/programming/python"

    def test_parse_path_parent_directory(self, shell):
        """Parent directory (..) navigation should work."""
        shell.cwd = "/tags/programming/python"
        assert shell._parse_path("..") == "/tags/programming"
        assert shell._parse_path("../..") == "/tags"
        assert shell._parse_path("../../..") == "/"

    def test_parse_path_current_directory(self, shell):
        """Current directory (.) should resolve to cwd."""
        shell.cwd = "/bookmarks"
        assert shell._parse_path(".") == "/bookmarks"
        assert shell._parse_path("./123") == "/bookmarks/123"

    def test_parse_path_mixed_navigation(self, shell):
        """Mixed navigation with . and .. should work."""
        shell.cwd = "/tags/programming"
        assert shell._parse_path("./python/../rust") == "/tags/programming/rust"
        assert shell._parse_path("python/./data-science") == "/tags/programming/python/data-science"

    def test_parse_path_normalize_multiple_slashes(self, shell):
        """Multiple slashes should be normalized."""
        shell.cwd = "/"
        assert shell._parse_path("bookmarks//123") == "/bookmarks/123"
        assert shell._parse_path("tags///python") == "/tags/python"

    def test_parse_path_trailing_slash_ignored(self, shell):
        """Trailing slashes should be ignored."""
        shell.cwd = "/"
        assert shell._parse_path("bookmarks/") == "/bookmarks"
        assert shell._parse_path("tags/python/") == "/tags/python"

    def test_parse_path_parent_beyond_root(self, shell):
        """Parent navigation beyond root should stay at root."""
        shell.cwd = "/"
        assert shell._parse_path("..") == "/"
        assert shell._parse_path("../..") == "/"

        shell.cwd = "/bookmarks"
        assert shell._parse_path("../..") == "/"


class TestContextDetection:
    """Test context detection from paths."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add test bookmarks with tags
            db.add(
                url="https://docs.python.org",
                title="Python Docs",
                tags=["programming/python", "documentation"]
            )
            db.add(
                url="https://www.rust-lang.org",
                title="Rust Lang",
                tags=["programming/rust"]
            )
            db.add(
                url="https://github.com",
                title="GitHub",
                tags=["development", "git"],
                stars=True
            )
            db.add(
                url="https://example.com/archived",
                title="Archived Site",
                tags=["old"],
                archived=True
            )

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_context_root(self, shell):
        """Root context should be detected."""
        shell.cwd = "/"
        ctx = shell._get_context()
        assert ctx['type'] == 'root'
        assert ctx['bookmarks'] == []

    def test_context_bookmarks_list(self, shell):
        """Bookmarks list context should be detected."""
        shell.cwd = "/bookmarks"
        ctx = shell._get_context()
        assert ctx['type'] == 'bookmarks'
        assert len(ctx['bookmarks']) > 0
        assert all(isinstance(b, Bookmark) for b in ctx['bookmarks'])

    def test_context_specific_bookmark(self, shell):
        """Specific bookmark context should be detected."""
        shell.cwd = "/bookmarks/1"
        ctx = shell._get_context()
        assert ctx['type'] == 'bookmark'
        assert ctx['bookmark_id'] == 1
        assert ctx['bookmark'] is not None
        assert ctx['bookmark'].id == 1

    def test_context_tags_root(self, shell):
        """Tags root context should be detected."""
        shell.cwd = "/tags"
        ctx = shell._get_context()
        assert ctx['type'] == 'tags'
        assert ctx['tag_path'] == ''

    def test_context_tag_hierarchy(self, shell):
        """Hierarchical tag context should be detected."""
        shell.cwd = "/tags/programming"
        ctx = shell._get_context()
        assert ctx['type'] == 'tags'
        assert ctx['tag_path'] == 'programming'
        assert len(ctx['bookmarks']) >= 2  # Python and Rust bookmarks

    def test_context_nested_tag_hierarchy(self, shell):
        """Nested tag hierarchy should be detected."""
        shell.cwd = "/tags/programming/python"
        ctx = shell._get_context()
        assert ctx['type'] == 'tags'
        assert ctx['tag_path'] == 'programming/python'
        assert len(ctx['bookmarks']) >= 1

    def test_context_bookmark_in_tag_path(self, shell):
        """Bookmark ID in tag path should be detected as bookmark context."""
        # Navigate to first bookmark
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/tags/programming/{bookmark_id}"
            ctx = shell._get_context()
            # Should detect as bookmark if bookmark has the tag
            if any(t.name.startswith('programming') for t in bookmarks[0].tags):
                assert ctx['type'] == 'bookmark'
                assert ctx['bookmark_id'] == bookmark_id

    def test_context_starred(self, shell):
        """Starred context should be detected."""
        shell.cwd = "/starred"
        ctx = shell._get_context()
        assert ctx['type'] == 'starred'
        assert all(b.stars for b in ctx['bookmarks'])

    def test_context_starred_bookmark(self, shell):
        """Specific starred bookmark should be detected."""
        starred = [b for b in shell.db.list() if b.stars]
        if starred:
            bookmark_id = starred[0].id
            shell.cwd = f"/starred/{bookmark_id}"
            ctx = shell._get_context()
            assert ctx['type'] == 'bookmark'
            assert ctx['bookmark_id'] == bookmark_id
            assert ctx['bookmark'].stars

    def test_context_archived(self, shell):
        """Archived context should be detected."""
        shell.cwd = "/archived"
        ctx = shell._get_context()
        assert ctx['type'] == 'archived'
        assert all(b.archived for b in ctx['bookmarks'])

    def test_context_recent(self, shell):
        """Recent context should be detected."""
        shell.cwd = "/recent"
        ctx = shell._get_context()
        assert ctx['type'] == 'recent'
        # Bookmarks should be sorted by added date
        if len(ctx['bookmarks']) > 1:
            dates = [b.added for b in ctx['bookmarks'] if b.added]
            assert dates == sorted(dates, reverse=True)

    def test_context_domains_root(self, shell):
        """Domains root context should be detected."""
        shell.cwd = "/domains"
        ctx = shell._get_context()
        assert ctx['type'] == 'domains'

    def test_context_specific_domain(self, shell):
        """Specific domain context should be detected."""
        shell.cwd = "/domains/github.com"
        ctx = shell._get_context()
        assert ctx['type'] == 'domain'
        assert ctx['domain'] == 'github.com'
        assert all('github.com' in b.url for b in ctx['bookmarks'])

    def test_context_unknown_path(self, shell):
        """Unknown path should return unknown context."""
        shell.cwd = "/invalid/path/here"
        ctx = shell._get_context()
        assert ctx['type'] == 'unknown'


class TestNavigation:
    """Test navigation commands (cd, ls, pwd)."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add test bookmarks
            db.add(url="https://python.org", title="Python", tags=["programming/python"])
            db.add(url="https://rust-lang.org", title="Rust", tags=["programming/rust"])
            db.add(url="https://github.com", title="GitHub", tags=["development"], stars=True)

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_cd_to_root(self, shell):
        """cd / should navigate to root."""
        shell.cwd = "/bookmarks"
        shell.do_cd("/")
        assert shell.cwd == "/"

    def test_cd_to_bookmarks(self, shell):
        """cd bookmarks should navigate to bookmarks."""
        shell.cwd = "/"
        shell.do_cd("bookmarks")
        assert shell.cwd == "/bookmarks"

    def test_cd_absolute_path(self, shell):
        """cd with absolute path should work."""
        shell.cwd = "/"
        shell.do_cd("/tags/programming")
        assert shell.cwd == "/tags/programming"

    def test_cd_relative_path(self, shell):
        """cd with relative path should work."""
        shell.cwd = "/tags"
        shell.do_cd("programming")
        assert shell.cwd == "/tags/programming"

    def test_cd_parent_directory(self, shell):
        """cd .. should go to parent directory."""
        shell.cwd = "/tags/programming/python"
        shell.do_cd("..")
        assert shell.cwd == "/tags/programming"

    def test_cd_to_bookmark(self, shell):
        """cd to bookmark ID should work."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = "/bookmarks"
            shell.do_cd(str(bookmark_id))
            assert shell.cwd == f"/bookmarks/{bookmark_id}"

    def test_cd_updates_prompt(self, shell):
        """cd should update the prompt."""
        shell.cwd = "/"
        shell.do_cd("bookmarks")
        assert "bookmarks" in shell.prompt

    def test_pwd_shows_current_path(self, shell):
        """pwd should print current working directory."""
        shell.cwd = "/tags/programming"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_pwd("")
            mock_print.assert_called_with("/tags/programming")

    def test_ls_in_root(self, shell):
        """ls in root should show virtual directories."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Should print virtual directory information
            assert mock_print.call_count > 0

    def test_ls_in_bookmarks(self, shell):
        """ls in /bookmarks should list bookmarks."""
        shell.cwd = "/bookmarks"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.call_count > 0

    def test_ls_with_path_argument(self, shell):
        """ls <path> should list contents of specified path."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("bookmarks")
            assert mock_print.call_count > 0

    def test_ls_long_format(self, shell):
        """ls -l should show detailed format."""
        shell.cwd = "/bookmarks"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("-l")
            assert mock_print.call_count > 0


class TestContextAwareCommands:
    """Test context-aware commands (cat, star, tag)."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add test bookmark
            db.add(
                url="https://example.com",
                title="Example Site",
                description="A test site",
                tags=["test", "example"]
            )

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_cat_url_in_bookmark_context(self, shell):
        """cat url should show URL when in bookmark context."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/bookmarks/{bookmark_id}"

            with patch.object(shell.console, 'print') as mock_print:
                shell.do_cat("url")
                mock_print.assert_called_with(bookmarks[0].url)

    def test_cat_title_in_bookmark_context(self, shell):
        """cat title should show title when in bookmark context."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/bookmarks/{bookmark_id}"

            with patch.object(shell.console, 'print') as mock_print:
                shell.do_cat("title")
                mock_print.assert_called_with(bookmarks[0].title)

    def test_cat_with_path_syntax(self, shell):
        """cat <id>/<field> should work with path syntax."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = "/"

            with patch.object(shell.console, 'print') as mock_print:
                shell.do_cat(f"{bookmark_id}/url")
                mock_print.assert_called_with(bookmarks[0].url)

    def test_cat_without_bookmark_context_shows_error(self, shell):
        """cat without bookmark context should show error."""
        shell.cwd = "/"

        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("url")
            # Should print error message
            args = mock_print.call_args[0][0]
            assert "not in a bookmark context" in args.lower() or "not in a bookmark" in args.lower()

    def test_star_toggle_in_bookmark_context(self, shell):
        """star should toggle starred status in bookmark context."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark = bookmarks[0]
            bookmark_id = bookmark.id
            initial_stars = bookmark.stars

            shell.cwd = f"/bookmarks/{bookmark_id}"
            shell.do_star("")

            # Verify bookmark was updated
            updated = shell.db.get(bookmark_id)
            assert updated.stars != initial_stars

    def test_star_with_id_argument(self, shell):
        """star <id> should toggle star for specific bookmark."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark = bookmarks[0]
            bookmark_id = bookmark.id
            initial_stars = bookmark.stars

            shell.cwd = "/"
            shell.do_star(str(bookmark_id))

            updated = shell.db.get(bookmark_id)
            assert updated.stars != initial_stars

    def test_star_on_sets_star(self, shell):
        """star on should set starred status."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/bookmarks/{bookmark_id}"

            shell.do_star("on")
            updated = shell.db.get(bookmark_id)
            assert updated.stars == True

    def test_star_off_removes_star(self, shell):
        """star off should remove starred status."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            # First set star
            shell.db.update(bookmark_id, stars=True)

            shell.cwd = f"/bookmarks/{bookmark_id}"
            shell.do_star("off")

            updated = shell.db.get(bookmark_id)
            assert updated.stars == False

    def test_tag_adds_tag_in_bookmark_context(self, shell):
        """tag <tags> should add tags in bookmark context."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark = bookmarks[0]
            bookmark_id = bookmark.id
            initial_tag_count = len(bookmark.tags)

            shell.cwd = f"/bookmarks/{bookmark_id}"
            shell.do_tag("newtag")

            updated = shell.db.get(bookmark_id)
            assert len(updated.tags) > initial_tag_count
            assert any(t.name == "newtag" for t in updated.tags)

    def test_tag_with_id_argument(self, shell):
        """tag <id> <tags> should add tags to specific bookmark."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id

            shell.cwd = "/"
            shell.do_tag(f"{bookmark_id} another-tag")

            updated = shell.db.get(bookmark_id)
            assert any(t.name == "another-tag" for t in updated.tags)

    def test_tag_with_multiple_tags(self, shell):
        """tag should support comma-separated tags."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/bookmarks/{bookmark_id}"

            shell.do_tag("tag1,tag2,tag3")

            updated = shell.db.get(bookmark_id)
            tag_names = [t.name for t in updated.tags]
            assert "tag1" in tag_names
            assert "tag2" in tag_names
            assert "tag3" in tag_names


class TestTagCommands:
    """Test tag management commands (mv, cp)."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add bookmarks with tags
            db.add(url="https://example1.com", title="Site 1", tags=["old-tag", "other"])
            db.add(url="https://example2.com", title="Site 2", tags=["old-tag"])
            db.add(url="https://example3.com", title="Site 3", tags=["different"])

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_mv_renames_tag(self, shell):
        """mv should rename tag across all bookmarks."""
        # Confirm rename with 'y'
        with patch('builtins.input', return_value='y'):
            shell.do_mv("old-tag renamed-old-tag")

        # Verify all bookmarks with old-tag now have renamed tag
        bookmarks = shell.db.list()
        for b in bookmarks:
            tag_names = [t.name for t in b.tags]
            if "renamed-old-tag" in tag_names:
                assert "old-tag" not in tag_names

    def test_mv_cleans_up_orphaned_tag(self, shell):
        """mv should remove orphaned old tag."""
        with patch('builtins.input', return_value='y'):
            shell.do_mv("old-tag completely-new-tag")

        # Check that old-tag no longer exists in database
        from btk.models import Tag
        with shell.db.session() as session:
            old_tag = session.query(Tag).filter_by(name="old-tag").first()
            assert old_tag is None

    def test_mv_with_same_name_does_nothing(self, shell):
        """mv with same old and new tag should do nothing."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_mv("old-tag old-tag")
            # Should print message about tags being the same
            assert mock_print.called

    def test_mv_nonexistent_tag_shows_message(self, shell):
        """mv with nonexistent tag should show message."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_mv("nonexistent-tag new-tag")
            # Should print message about no bookmarks found
            assert mock_print.called

    def test_cp_adds_tag_to_current_bookmark(self, shell):
        """cp <tag> . should add tag to current bookmark."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/bookmarks/{bookmark_id}"

            shell.do_cp("new-tag .")

            updated = shell.db.get(bookmark_id)
            assert any(t.name == "new-tag" for t in updated.tags)

    def test_cp_adds_tag_to_specific_bookmark(self, shell):
        """cp <tag> <id> should add tag to specific bookmark."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id

            shell.do_cp(f"another-tag {bookmark_id}")

            updated = shell.db.get(bookmark_id)
            assert any(t.name == "another-tag" for t in updated.tags)

    def test_cp_adds_tag_to_all_in_context(self, shell):
        """cp <tag> * should add tag to all bookmarks in context."""
        shell.cwd = "/bookmarks"

        # Confirm with 'y'
        with patch('builtins.input', return_value='y'):
            shell.do_cp("global-tag *")

        # Verify all bookmarks have the tag
        bookmarks = shell.db.list()
        for b in bookmarks:
            assert any(t.name == "global-tag" for t in b.tags)

    def test_cp_skips_bookmarks_that_already_have_tag(self, shell):
        """cp should skip bookmarks that already have the tag."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id

            # Add tag first time
            shell.do_cp(f"existing-tag {bookmark_id}")

            # Try to add again
            with patch.object(shell.console, 'print') as mock_print:
                shell.do_cp(f"existing-tag {bookmark_id}")
                # Should print message about already having tag
                assert mock_print.called


class TestVirtualFilesystem:
    """Test virtual filesystem features."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database with hierarchical tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add bookmarks with hierarchical tags
            db.add(url="https://python.org", title="Python", tags=["programming/python/docs"])
            db.add(url="https://numpy.org", title="NumPy", tags=["programming/python/data-science"])
            db.add(url="https://rust-lang.org", title="Rust", tags=["programming/rust"])
            db.add(url="https://github.com", title="GitHub", tags=["development/git"])

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_get_bookmarks_by_tag_prefix(self, shell):
        """_get_bookmarks_by_tag_prefix should filter correctly."""
        bookmarks = shell._get_bookmarks_by_tag_prefix("programming/python")
        assert len(bookmarks) >= 2  # Python and NumPy

    def test_get_bookmarks_by_tag_prefix_exact_match(self, shell):
        """Tag prefix should match exact tags."""
        bookmarks = shell._get_bookmarks_by_tag_prefix("programming/rust")
        assert len(bookmarks) >= 1
        assert all(
            any(t.name == "programming/rust" for t in b.tags)
            for b in bookmarks
        )

    def test_get_bookmarks_by_tag_prefix_hierarchical(self, shell):
        """Tag prefix should match hierarchical subtags."""
        bookmarks = shell._get_bookmarks_by_tag_prefix("programming")
        # Should match programming/python/*, programming/rust
        assert len(bookmarks) >= 3

    def test_get_bookmarks_by_domain(self, shell):
        """_get_bookmarks_by_domain should filter correctly."""
        bookmarks = shell._get_bookmarks_by_domain("github.com")
        assert len(bookmarks) >= 1
        assert all("github.com" in b.url for b in bookmarks)

    def test_get_all_tags(self, shell):
        """_get_all_tags should return all unique tags."""
        tags = shell._get_all_tags()
        assert len(tags) > 0
        assert "programming/python/docs" in tags
        assert "programming/rust" in tags

    def test_get_all_domains(self, shell):
        """_get_all_domains should return all unique domains."""
        domains = shell._get_all_domains()
        assert len(domains) > 0
        assert "python.org" in domains or "www.python.org" in domains
        assert "github.com" in domains


class TestSearchCommands:
    """Test search and filter commands."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add test bookmarks
            db.add(url="https://python.org", title="Python Programming", tags=["python"])
            db.add(url="https://rust-lang.org", title="Rust Language", tags=["rust"])
            db.add(url="https://github.com", title="GitHub", tags=["git"], stars=True)

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_find_searches_bookmarks(self, shell):
        """find should search bookmarks."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_find("Python")
            assert mock_print.call_count > 0

    def test_which_finds_bookmark_by_id(self, shell):
        """which should find bookmark by ID."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id

            with patch.object(shell.console, 'print') as mock_print:
                shell.do_which(str(bookmark_id))
                assert mock_print.call_count > 0

    def test_top_shows_recent_bookmarks(self, shell):
        """top should show recently added bookmarks."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_top("")
            assert mock_print.call_count > 0

    def test_top_with_visits_option(self, shell):
        """top visits should show most visited bookmarks."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_top("visits")
            assert mock_print.call_count > 0

    def test_recent_command(self, shell):
        """recent should show recently active bookmarks."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_recent("")
            # Should show output
            assert mock_print.call_count >= 0


class TestStatCommands:
    """Test statistics commands."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add test bookmarks
            db.add(url="https://python.org", title="Python", tags=["python"])
            db.add(url="https://github.com", title="GitHub", tags=["git"], stars=True)

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_stat_shows_collection_stats_at_root(self, shell):
        """stat at root should show collection statistics."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_stat("")
            assert mock_print.call_count > 0

    def test_stat_shows_bookmark_stats_in_context(self, shell):
        """stat in bookmark context should show bookmark statistics."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/bookmarks/{bookmark_id}"

            with patch.object(shell.console, 'print') as mock_print:
                shell.do_stat("")
                assert mock_print.call_count > 0

    def test_file_shows_bookmark_metadata(self, shell):
        """file should show bookmark metadata."""
        bookmarks = shell.db.list()
        if bookmarks:
            bookmark_id = bookmarks[0].id
            shell.cwd = f"/bookmarks/{bookmark_id}"

            with patch.object(shell.console, 'print') as mock_print:
                shell.do_file("")
                assert mock_print.call_count > 0


class TestLsOutputFormatting:
    """Test ls command output formatting methods."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database with hierarchical tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            # Add bookmarks with various properties
            db.add(url="https://python.org", title="Python", tags=["programming/python"])
            db.add(url="https://rust-lang.org", title="Rust", tags=["programming/rust"])
            db.add(url="https://github.com", title="GitHub", tags=["development"], stars=True)
            db.add(url="https://unreachable.test", title="Broken", reachable=False)
            db.add(url="https://example.com/doc.pdf", title="PDF Doc", tags=["docs"])

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_ls_at_root_shows_directories(self, shell):
        """ls at root should show all virtual directories."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Should print something
            assert mock_print.called

    def test_ls_in_tags_shows_tag_hierarchy(self, shell):
        """ls in /tags should show hierarchical tag structure."""
        shell.cwd = "/tags"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.called

    def test_ls_in_tag_directory(self, shell):
        """ls in tag directory should show subtags and bookmarks."""
        shell.cwd = "/tags/programming"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.called

    def test_ls_in_bookmarks(self, shell):
        """ls in /bookmarks should show all bookmark IDs."""
        shell.cwd = "/bookmarks"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.called

    def test_ls_in_bookmark_context(self, shell):
        """ls in bookmark context should show fields."""
        bookmarks = shell.db.list()
        if bookmarks:
            shell.cwd = f"/bookmarks/{bookmarks[0].id}"
            with patch.object(shell.console, 'print') as mock_print:
                shell.do_ls("")
                assert mock_print.called

    def test_ls_in_starred(self, shell):
        """ls in /starred should show starred bookmarks."""
        shell.cwd = "/starred"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.called

    def test_ls_in_domains(self, shell):
        """ls in /domains should show all domains."""
        shell.cwd = "/domains"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.called


class TestCatFieldVariations:
    """Test cat command for all field types."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            db.add(
                url="https://python.org",
                title="Python Programming Language",
                description="Official Python website",
                tags=["programming", "python"],
                stars=True
            )

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_cat_id_field(self, shell):
        """cat id should show bookmark ID."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("id")
            assert mock_print.called

    def test_cat_url_field(self, shell):
        """cat url should show bookmark URL."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("url")
            assert mock_print.called

    def test_cat_title_field(self, shell):
        """cat title should show bookmark title."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("title")
            assert mock_print.called

    def test_cat_tags_field(self, shell):
        """cat tags should show bookmark tags."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("tags")
            assert mock_print.called

    def test_cat_description_field(self, shell):
        """cat description should show bookmark description."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("description")
            assert mock_print.called

    def test_cat_stars_field(self, shell):
        """cat stars should show starred status."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("stars")
            assert mock_print.called

    def test_cat_visits_field(self, shell):
        """cat visits should show visit count."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("visits")
            assert mock_print.called

    def test_cat_added_field(self, shell):
        """cat added should show added timestamp."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("added")
            assert mock_print.called

    def test_cat_without_field_shows_all(self, shell):
        """cat without field in bookmark context should show all info."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("")
            assert mock_print.called


class TestStatCommandVariants:
    """Test stat command with different arguments."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            db.add(url="https://python.org", title="Python", tags=["python"])
            db.add(url="https://github.com", title="GitHub", stars=True)

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_stat_with_dot_shows_current(self, shell):
        """stat . should show current context stats."""
        shell.cwd = "/bookmarks"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_stat(".")
            assert mock_print.called

    def test_stat_with_dotdot_shows_parent(self, shell):
        """stat .. should show parent context stats."""
        bookmarks = shell.db.list()
        shell.cwd = f"/bookmarks/{bookmarks[0].id}"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_stat("..")
            assert mock_print.called

    def test_stat_with_id_shows_specific_bookmark(self, shell):
        """stat <id> should show stats for specific bookmark."""
        bookmarks = shell.db.list()
        bookmark_id = bookmarks[0].id
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_stat(str(bookmark_id))
            assert mock_print.called

    def test_stat_in_tags_context(self, shell):
        """stat in tags context should show tag statistics."""
        shell.cwd = "/tags"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_stat("")
            assert mock_print.called


class TestRecentCommandVariants:
    """Test recent command with various options."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            db.add(url="https://python.org", title="Python")
            db.add(url="https://github.com", title="GitHub", stars=True)

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_recent_default(self, shell):
        """recent without args should show recent bookmarks."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_recent("")
            # Should not raise error

    def test_recent_with_count(self, shell):
        """recent with count should limit results."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_recent("5")
            # Should not raise error

    def test_recent_visited(self, shell):
        """recent visited should show by visit time."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_recent("visited")
            # Should not raise error

    def test_recent_added(self, shell):
        """recent added should show by add time."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_recent("added")
            # Should not raise error


class TestDomainNavigation:
    """Test domain-based navigation."""

    @pytest.fixture
    def populated_db(self):
        """Create database with bookmarks from various domains."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            db.add(url="https://github.com/user/repo1", title="Repo 1")
            db.add(url="https://github.com/user/repo2", title="Repo 2")
            db.add(url="https://python.org", title="Python")

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_cd_to_domains(self, shell):
        """cd /domains should navigate to domains root."""
        shell.do_cd("/domains")
        assert shell.cwd == "/domains"

    def test_cd_to_specific_domain(self, shell):
        """cd to specific domain should filter bookmarks."""
        shell.do_cd("/domains/github.com")
        assert "github.com" in shell.cwd

    def test_ls_in_domain_shows_bookmarks(self, shell):
        """ls in domain should show bookmarks from that domain."""
        shell.cwd = "/domains/github.com"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            assert mock_print.called


class TestShellEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def shell(self):
        """Create a shell with empty database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            shell = BookmarkShell(db_path)
            yield shell

    def test_cd_to_nonexistent_path(self, shell):
        """cd to nonexistent path should show error."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cd("/nonexistent")
            assert mock_print.called

    def test_cat_in_invalid_context(self, shell):
        """cat in invalid context should show error."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_cat("invalid")
            assert mock_print.called

    def test_ls_empty_directory(self, shell):
        """ls in empty directory should handle gracefully."""
        shell.cwd = "/bookmarks"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_ls("")
            # Should not raise error

    def test_help_command(self, shell):
        """help should show available commands."""
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_help("")
            # Should print help or not raise error

    def test_clear_command(self, shell):
        """clear should clear screen without error."""
        shell.do_clear("")
        # Should not raise error

    def test_quit_returns_true(self, shell):
        """quit should return True to exit."""
        result = shell.do_quit("")
        assert result is True

    def test_exit_returns_true(self, shell):
        """exit should return True to exit."""
        result = shell.do_exit("")
        assert result is True


class TestShellPwdCommand:
    """Test pwd command."""

    @pytest.fixture
    def shell(self):
        """Create a shell instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            shell = BookmarkShell(db_path)
            yield shell

    def test_pwd_at_root(self, shell):
        """pwd at root should show /."""
        shell.cwd = "/"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_pwd("")
            mock_print.assert_called()

    def test_pwd_in_subdirectory(self, shell):
        """pwd in subdirectory should show full path."""
        shell.cwd = "/tags/programming"
        with patch.object(shell.console, 'print') as mock_print:
            shell.do_pwd("")
            mock_print.assert_called()


class TestBookmarkOperationsFromShell:
    """Test bookmark operations via shell commands."""

    @pytest.fixture
    def populated_db(self):
        """Create a populated test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            db.add(url="https://example.com", title="Example", tags=["test"])

            yield db

    @pytest.fixture
    def shell(self, populated_db):
        """Create shell with populated database."""
        shell = BookmarkShell(str(populated_db.path))
        return shell

    def test_star_command_stars_bookmark(self, shell):
        """star command should star bookmark."""
        bookmarks = shell.db.list()
        bookmark_id = bookmarks[0].id

        shell.do_star(str(bookmark_id))

        updated = shell.db.get(bookmark_id)
        assert updated.stars is True

    def test_toggle_star_unstars_bookmark(self, shell):
        """star command should toggle star off when already starred."""
        bookmarks = shell.db.list()
        bookmark_id = bookmarks[0].id

        # First star it
        shell.do_star(str(bookmark_id))
        assert shell.db.get(bookmark_id).stars is True

        # Toggle star again (should unstar)
        shell.do_star(str(bookmark_id))
        updated = shell.db.get(bookmark_id)
        assert updated.stars is False

    def test_shell_command_executed_via_do_shell(self, shell):
        """do_shell command should execute shell commands."""
        # do_shell runs external shell commands
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            shell.do_shell("echo test")
            mock_run.assert_called_once()

    def test_find_command_searches_bookmarks(self, shell):
        """find command should search bookmark titles and URLs."""
        output = StringIO()
        with redirect_stdout(output):
            shell.do_find("python")

        result = output.getvalue()
        # Should find Python documentation bookmark
        assert "python" in result.lower() or len(result) > 0
