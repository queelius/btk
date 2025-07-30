import pytest
import json
import tempfile
import shutil
import os
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