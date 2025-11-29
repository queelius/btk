import pytest
import json
import tempfile
import shutil
import os
import sys
from io import StringIO
from contextlib import redirect_stdout
from datetime import datetime, timezone


@pytest.fixture
def sample_bookmarks():
    """Sample bookmark data for testing."""
    return [
        {
            "id": 1,
            "unique_id": "db558d9a",
            "title": "Python Documentation",
            "url": "https://docs.python.org",
            "added": "2023-02-24T13:59:56+00:00",
            "stars": False,
            "tags": ["python", "documentation"],
            "visit_count": 5,
            "description": "Official Python documentation",
            "favicon": "favicons/python.ico",
            "last_visited": "2025-01-19T06:14:54.355523+00:00",
            "reachable": True
        },
        {
            "id": 2,
            "unique_id": "9136cf33",
            "title": "GitHub",
            "url": "https://github.com",
            "added": "2023-03-15T10:30:00+00:00",
            "stars": True,
            "tags": ["development", "git"],
            "visit_count": 10,
            "description": "Code hosting platform",
            "favicon": "favicons/github.png",
            "last_visited": "2025-01-20T12:00:00.000000+00:00",
            "reachable": True
        },
        {
            "id": 3,
            "unique_id": "abc12345",
            "title": "Broken Link Example",
            "url": "https://this-site-does-not-exist-12345.com",
            "added": "2023-04-01T08:00:00+00:00",
            "stars": False,
            "tags": [],
            "visit_count": 0,
            "description": "",
            "favicon": "",
            "last_visited": None,
            "reachable": False
        }
    ]


@pytest.fixture
def temp_lib_dir():
    """Create a temporary library directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="btk_test_")
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir)


@pytest.fixture
def populated_lib_dir(temp_lib_dir, sample_bookmarks):
    """Create a populated library directory with sample bookmarks."""
    bookmarks_file = os.path.join(temp_lib_dir, "bookmarks.json")
    favicons_dir = os.path.join(temp_lib_dir, "favicons")
    
    # Create favicons directory
    os.makedirs(favicons_dir, exist_ok=True)
    
    # Save sample bookmarks
    with open(bookmarks_file, 'w', encoding='utf-8') as f:
        json.dump(sample_bookmarks, f, indent=2)
    
    return temp_lib_dir


@pytest.fixture
def sample_html_bookmarks():
    """Sample HTML bookmarks in Netscape format."""
    return """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3>Programming</H3>
    <DL><p>
        <DT><A HREF="https://www.python.org/" ADD_DATE="1677247196" ICON="data:image/png;base64,iVBORw0KGg...">Python.org</A>
        <DT><A HREF="https://docs.python.org/" ADD_DATE="1677247196" TAGS="python,docs">Python Documentation</A>
    </DL><p>
    <DT><H3>Tools</H3>
    <DL><p>
        <DT><A HREF="https://github.com/" ADD_DATE="1678969800" ICON="data:image/png;base64,iVBORw0KGg...">GitHub</A>
    </DL><p>
</DL><p>
"""


@pytest.fixture
def sample_csv_bookmarks():
    """Sample CSV bookmark data."""
    return """url,title,tags,description,stars
https://www.python.org/,Python.org,"python,programming",Official Python website,true
https://github.com/,GitHub,"git,development",Code hosting platform,true
https://stackoverflow.com/,Stack Overflow,"qa,programming",Q&A for programmers,false
"""


@pytest.fixture
def sample_json_bookmarks():
    """Sample JSON bookmark data for import."""
    return [
        {
            "url": "https://www.python.org/",
            "title": "Python.org",
            "tags": ["python", "programming"],
            "description": "Official Python website",
            "stars": True
        },
        {
            "url": "https://github.com/",
            "title": "GitHub",
            "tags": ["git", "development"],
            "description": "Code hosting platform",
            "stars": True
        }
    ]


@pytest.fixture
def mock_favicon_download(monkeypatch):
    """Mock favicon downloading to avoid network calls."""
    def mock_download(*args, **kwargs):
        return "favicons/mocked.ico"

    monkeypatch.setattr("btk.utils.download_favicon", mock_download)
    return mock_download


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    temp_dir = tempfile.mkdtemp(prefix="btk_test_db_")
    db_path = os.path.join(temp_dir, "test.db")
    yield db_path
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_shell(temp_db):
    """Create a BookmarkShell with test database."""
    from btk.shell import BookmarkShell
    shell = BookmarkShell(temp_db)
    return shell


@pytest.fixture
def populated_shell_db():
    """Create a shell with populated test database."""
    from btk.db import Database
    from btk.shell import BookmarkShell

    temp_dir = tempfile.mkdtemp(prefix="btk_test_shell_")
    db_path = os.path.join(temp_dir, "test.db")

    # Create database and populate
    db = Database(db_path)

    # Add diverse test data
    db.add(
        url="https://docs.python.org",
        title="Python Documentation",
        description="Official Python docs",
        tags=["programming/python", "documentation"],
        stars=True
    )
    db.add(
        url="https://www.rust-lang.org",
        title="Rust Programming Language",
        tags=["programming/rust"],
        stars=False
    )
    db.add(
        url="https://github.com",
        title="GitHub",
        tags=["development", "git"],
        stars=True
    )
    db.add(
        url="https://stackoverflow.com",
        title="Stack Overflow",
        tags=["qa", "programming"],
        stars=False
    )

    shell = BookmarkShell(db_path)

    yield shell

    # Cleanup
    shutil.rmtree(temp_dir)


# ============ Test Helpers ============

@pytest.fixture
def capture_output():
    """
    Fixture to capture stdout output from function calls.

    Usage:
        def test_something(capture_output):
            output = capture_output(some_func, arg1, arg2)
            assert "expected" in output
    """
    def _capture(func, *args, **kwargs):
        output = StringIO()
        with redirect_stdout(output):
            func(*args, **kwargs)
        return output.getvalue()
    return _capture


@pytest.fixture
def clean_btk_env(monkeypatch, tmp_path):
    """
    Fixture to create a clean BTK environment without affecting real config.

    Removes BTK_ environment variables and sets HOME to a temp directory.
    """
    # Remove existing BTK_ env vars
    for key in list(os.environ.keys()):
        if key.startswith("BTK_"):
            monkeypatch.delenv(key, raising=False)

    # Set up clean home directory
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))
    monkeypatch.chdir(tmp_path)

    return tmp_path


class BookmarkBuilder:
    """
    Test data builder for creating bookmarks with a fluent API.

    Usage:
        builder = BookmarkBuilder(db)
        builder.with_url("https://example.com").with_title("Example").starred().build()
    """
    def __init__(self, db):
        self.db = db
        self.url = "https://example.com"
        self.title = "Test Bookmark"
        self.description = ""
        self.tags = []
        self.stars = False
        self.pinned = False
        self.archived = False
        self.visit_count = 0
        self.reachable = True

    def with_url(self, url):
        self.url = url
        return self

    def with_title(self, title):
        self.title = title
        return self

    def with_description(self, description):
        self.description = description
        return self

    def with_tags(self, *tags):
        self.tags = list(tags)
        return self

    def starred(self):
        self.stars = True
        return self

    def pinned(self):
        self.pinned = True
        return self

    def archived(self):
        self.archived = True
        return self

    def with_visits(self, count):
        self.visit_count = count
        return self

    def unreachable(self):
        self.reachable = False
        return self

    def build(self):
        """Create the bookmark in the database and return it."""
        return self.db.add(
            url=self.url,
            title=self.title,
            description=self.description,
            tags=self.tags,
            stars=self.stars,
            pinned=self.pinned,
            archived=self.archived
        )


@pytest.fixture
def bookmark_builder():
    """
    Fixture to create a BookmarkBuilder factory.

    Usage:
        def test_something(bookmark_builder, temp_db):
            from btk.db import Database
            db = Database(temp_db)
            builder = bookmark_builder(db)
            builder.with_url("https://test.com").starred().build()
    """
    def _builder(db):
        return BookmarkBuilder(db)
    return _builder


# ============ Assertion Helpers ============

def assert_bookmark_in_list(bookmarks, url=None, title=None, tag=None):
    """
    Assert a bookmark with given properties exists in list.

    Args:
        bookmarks: List of Bookmark objects
        url: Expected URL (optional)
        title: Expected title (optional)
        tag: Expected tag name (optional)

    Raises:
        AssertionError if no matching bookmark found
    """
    for b in bookmarks:
        if url and b.url != url:
            continue
        if title and b.title != title:
            continue
        if tag and not any(t.name == tag for t in b.tags):
            continue
        return  # Found matching bookmark
    pytest.fail(f"No bookmark found with url={url}, title={title}, tag={tag}")


def assert_tag_on_bookmark(bookmark, tag_name):
    """
    Assert bookmark has the given tag.

    Args:
        bookmark: Bookmark object
        tag_name: Expected tag name

    Raises:
        AssertionError if tag not found on bookmark
    """
    tag_names = [t.name for t in bookmark.tags]
    assert tag_name in tag_names, f"Expected tag '{tag_name}' but found {tag_names}"


def assert_no_tag_on_bookmark(bookmark, tag_name):
    """
    Assert bookmark does NOT have the given tag.

    Args:
        bookmark: Bookmark object
        tag_name: Tag name that should NOT be present

    Raises:
        AssertionError if tag is found on bookmark
    """
    tag_names = [t.name for t in bookmark.tags]
    assert tag_name not in tag_names, f"Expected no tag '{tag_name}' but found it in {tag_names}"


# Make assertion helpers available at module level for direct import
@pytest.fixture
def bookmark_assertions():
    """
    Fixture providing bookmark assertion helpers.

    Usage:
        def test_something(bookmark_assertions):
            bookmark_assertions.in_list(bookmarks, url="https://test.com")
            bookmark_assertions.has_tag(bookmark, "python")
    """
    class Assertions:
        in_list = staticmethod(assert_bookmark_in_list)
        has_tag = staticmethod(assert_tag_on_bookmark)
        no_tag = staticmethod(assert_no_tag_on_bookmark)

    return Assertions()


# ============ Database Fixtures ============

@pytest.fixture
def empty_database():
    """Create an empty test database and return Database instance."""
    from btk.db import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        yield db


@pytest.fixture
def populated_database():
    """Create a populated test database with diverse bookmarks."""
    from btk.db import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        # Add diverse test data
        db.add(
            url="https://docs.python.org",
            title="Python Documentation",
            description="Official Python docs",
            tags=["programming/python", "documentation"],
            stars=True
        )
        db.add(
            url="https://www.rust-lang.org",
            title="Rust Programming Language",
            tags=["programming/rust"],
            stars=False
        )
        db.add(
            url="https://github.com",
            title="GitHub",
            tags=["development", "git"],
            stars=True
        )
        db.add(
            url="https://stackoverflow.com",
            title="Stack Overflow",
            tags=["qa", "programming"],
            stars=False
        )
        db.add(
            url="https://example.com/archived",
            title="Archived Site",
            tags=["old"],
            archived=True
        )
        db.add(
            url="https://broken-site.test",
            title="Broken Site",
            reachable=False
        )
        db.add(
            url="https://example.com/doc.pdf",
            title="PDF Document",
            tags=["docs", "pdf"]
        )

        yield db