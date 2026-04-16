# bookmark-memex Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `bookmark-memex` package from the spec, producing a working MCP server, CLI, importers, exporters, content pipeline, and media detectors. Web UI is a separate follow-up plan.

**Architecture:** New Python package `bookmark_memex` in a fresh directory alongside btk. SQLAlchemy 2.0 ORM over SQLite with FTS5. MCP server via fastmcp + aiosqlite. Thin argparse CLI. Selective port of btk's content, importer, and FTS modules with updated imports.

**Tech Stack:** Python 3.10+, SQLAlchemy 2.0, fastmcp, aiosqlite, BeautifulSoup4, requests, rich, PyYAML, Jinja2

**Spec:** `docs/superpowers/specs/2026-04-16-bookmark-memex-design.md`

---

## File Map

### New files (created from scratch)

| File | Responsibility |
|------|---------------|
| `bookmark_memex/__init__.py` | Version, public API |
| `bookmark_memex/models.py` | SQLAlchemy ORM models (Bookmark, Tag, Annotation, etc.) |
| `bookmark_memex/db.py` | Database class: session management, CRUD, migrations |
| `bookmark_memex/config.py` | TOML config, XDG paths, env var resolution |
| `bookmark_memex/uri.py` | URI builder/parser for `bookmark-memex://` scheme |
| `bookmark_memex/soft_delete.py` | Soft delete helpers (filter_active, archive, restore) |
| `bookmark_memex/mcp.py` | MCP server: 6 tools per memex contract |
| `bookmark_memex/cli.py` | Thin argparse CLI |
| `bookmark_memex/exporters/__init__.py` | Export dispatcher |
| `bookmark_memex/exporters/formats.py` | JSON, CSV, Markdown, text, m3u exporters |
| `bookmark_memex/exporters/arkiv.py` | Arkiv JSONL + schema.yaml export |
| `bookmark_memex/detectors/__init__.py` | Auto-discovery engine for media detectors |
| `bookmark_memex/detectors/youtube.py` | YouTube URL/metadata detector |
| `bookmark_memex/detectors/arxiv.py` | ArXiv paper detector |
| `bookmark_memex/detectors/github.py` | GitHub repo/issue/PR detector |
| `bookmark_memex/migrations/__init__.py` | Migration runner |
| `pyproject.toml` | Package metadata for bookmark-memex |
| `Makefile` | Development commands |
| `tests/conftest.py` | Test fixtures |

### Ported files (from btk, with updated imports)

| File | Source | Changes needed |
|------|--------|---------------|
| `bookmark_memex/content/fetcher.py` | `btk/content_fetcher.py` | Remove btk imports, update user-agent string |
| `bookmark_memex/content/cache.py` | New, but logic from `btk/content_fetcher.py` | Extract compress/decompress into standalone module |
| `bookmark_memex/content/extractor.py` | `btk/content_fetcher.py` | Extract html_to_markdown, extract_pdf_text |
| `bookmark_memex/importers/file_importers.py` | `btk/importers/file_importers.py` | Change `from btk.db import Database` to `bookmark_memex.db` |
| `bookmark_memex/importers/browser.py` | `btk/browser_import.py` | Change model imports, use bookmark_sources for provenance |
| `bookmark_memex/fts.py` | `btk/fts.py` | Add content_fts and annotations_fts tables, use new schema |
| `bookmark_memex/exporters/html_app.py` | `btk/exporters.py` (html-app section) | Extract into standalone module |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `bookmark_memex/__init__.py`
- Create: `pyproject.toml`
- Create: `Makefile`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `CLAUDE.md`

- [ ] **Step 1: Create package directory structure**

```bash
mkdir -p bookmark_memex/{content,importers,exporters,detectors,migrations,web/{templates,static}}
mkdir -p tests
touch bookmark_memex/__init__.py bookmark_memex/content/__init__.py
touch bookmark_memex/importers/__init__.py bookmark_memex/exporters/__init__.py
touch bookmark_memex/detectors/__init__.py bookmark_memex/migrations/__init__.py
touch tests/__init__.py
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "bookmark-memex"
version = "0.1.0"
description = "Personal bookmark archive with MCP server, FTS5 search, and content caching"
readme = "README.md"
requires-python = ">=3.10"
license = {file = "LICENSE"}
authors = [
    {name = "Alex Towell", email = "lex@metafunctor.com"}
]
dependencies = [
    "sqlalchemy>=2.0",
    "beautifulsoup4",
    "requests",
    "rich",
    "pyyaml",
    "jinja2",
    "markdownify",
]

[project.optional-dependencies]
mcp = ["fastmcp>=2.0", "aiosqlite>=0.20"]
dev = [
    "pytest",
    "pytest-cov",
    "black",
    "flake8",
    "mypy",
]

[project.scripts]
bookmark-memex = "bookmark_memex.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["bookmark_memex", "bookmark_memex.*"]

[tool.black]
line-length = 120
target-version = ['py310', 'py311', 'py312']

[tool.mypy]
python_version = "3.10"
warn_return_any = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write bookmark_memex/__init__.py**

```python
"""bookmark-memex: Personal bookmark archive for the memex ecosystem."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write Makefile**

```makefile
.PHONY: help venv install-dev test test-coverage lint format typecheck check clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

help:
	@echo "bookmark-memex Development Commands"
	@echo "===================================="
	@echo "  make venv          - Create virtual environment"
	@echo "  make install-dev   - Install with dev dependencies"
	@echo "  make test          - Run all tests"
	@echo "  make test-coverage - Run tests with coverage"
	@echo "  make lint          - Run flake8"
	@echo "  make format        - Format with black"
	@echo "  make typecheck     - Run mypy"
	@echo "  make check         - All quality checks"
	@echo "  make clean         - Clean build artifacts"

venv:
	python3 -m venv $(VENV)

install-dev: venv
	$(PIP) install -e ".[dev,mcp]"

test: install-dev
	$(PYTEST) -v

test-coverage: install-dev
	$(PYTEST) --cov=bookmark_memex --cov-report=term-missing

lint: install-dev
	$(VENV)/bin/flake8 bookmark_memex tests --max-line-length 120

format: install-dev
	$(VENV)/bin/black bookmark_memex tests

typecheck: install-dev
	$(VENV)/bin/mypy bookmark_memex

check: lint typecheck

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
```

- [ ] **Step 5: Write tests/conftest.py with base fixtures**

```python
"""Shared test fixtures for bookmark-memex."""

import os
import tempfile
import shutil

import pytest


@pytest.fixture
def tmp_db_path():
    """Temporary database file path, cleaned up after test."""
    tmp_dir = tempfile.mkdtemp(prefix="bm_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    yield db_path
    shutil.rmtree(tmp_dir)


@pytest.fixture
def sample_bookmarks():
    """Sample bookmark data for testing imports and exports."""
    return [
        {
            "url": "https://docs.python.org/3/",
            "title": "Python Documentation",
            "description": "Official Python docs",
            "tags": ["programming/python", "documentation"],
            "starred": True,
        },
        {
            "url": "https://github.com",
            "title": "GitHub",
            "description": "Code hosting platform",
            "tags": ["development", "git"],
            "starred": True,
        },
        {
            "url": "https://arxiv.org/abs/2301.00001",
            "title": "Sample ArXiv Paper",
            "description": "",
            "tags": ["research", "ai"],
            "starred": False,
        },
    ]
```

- [ ] **Step 6: Verify the package installs**

Run: `cd /home/spinoza/github/memex/btk && make -f bookmark_memex_path/Makefile install-dev`

Actually, since this is a new package alongside btk, we need to decide where it lives. It will be created at `/home/spinoza/github/memex/btk/` root level (the btk repo IS becoming bookmark-memex). The `btk/` Python package directory stays for now; `bookmark_memex/` is the new package directory alongside it.

Run:
```bash
pip install -e ".[dev,mcp]"
python -c "import bookmark_memex; print(bookmark_memex.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml Makefile bookmark_memex/ tests/
git commit -m "feat: scaffold bookmark-memex package structure"
```

---

### Task 2: URI Module and Soft Delete

**Files:**
- Create: `bookmark_memex/uri.py`
- Create: `bookmark_memex/soft_delete.py`
- Test: `tests/test_uri.py`
- Test: `tests/test_soft_delete.py`

These are dependency-free modules needed by models and db.

- [ ] **Step 1: Write test_uri.py**

```python
"""Tests for bookmark-memex URI builder and parser."""

import pytest
from bookmark_memex.uri import (
    build_bookmark_uri,
    build_annotation_uri,
    parse_uri,
    InvalidUriError,
    ParsedUri,
    SCHEME,
)


class TestBuildUri:
    def test_build_bookmark_uri(self):
        uri = build_bookmark_uri("a1b2c3d4e5f6g7h8")
        assert uri == "bookmark-memex://bookmark/a1b2c3d4e5f6g7h8"

    def test_build_annotation_uri(self):
        uri = build_annotation_uri("550e8400e29b41d4a716446655440000")
        assert uri == "bookmark-memex://annotation/550e8400e29b41d4a716446655440000"

    def test_build_empty_id_raises(self):
        with pytest.raises(ValueError):
            build_bookmark_uri("")

    def test_build_annotation_empty_id_raises(self):
        with pytest.raises(ValueError):
            build_annotation_uri("")


class TestParseUri:
    def test_parse_bookmark(self):
        result = parse_uri("bookmark-memex://bookmark/a1b2c3d4")
        assert result == ParsedUri(scheme="bookmark-memex", kind="bookmark", id="a1b2c3d4", fragment=None)

    def test_parse_annotation(self):
        result = parse_uri("bookmark-memex://annotation/abc123")
        assert result == ParsedUri(scheme="bookmark-memex", kind="annotation", id="abc123", fragment=None)

    def test_parse_with_fragment(self):
        result = parse_uri("bookmark-memex://bookmark/abc123#paragraph=5")
        assert result.id == "abc123"
        assert result.fragment == "paragraph=5"

    def test_wrong_scheme_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("book-memex://book/abc123")

    def test_unknown_kind_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("bookmark-memex://photo/abc123")

    def test_empty_id_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("bookmark-memex://bookmark/")

    def test_not_a_uri_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("just a string")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_uri.py -v`
Expected: ImportError (module does not exist yet)

- [ ] **Step 3: Implement uri.py**

```python
"""bookmark-memex URI builder and parser.

URI kinds:
    bookmark-memex://bookmark/<unique_id>
    bookmark-memex://annotation/<uuid>

Fragments for positions within cached content:
    bookmark-memex://bookmark/<unique_id>#paragraph=12
    bookmark-memex://bookmark/<unique_id>#heading=introduction

No SQLAlchemy dependency. Usable by external consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SCHEME = "bookmark-memex"
KINDS = frozenset({"bookmark", "annotation"})


class InvalidUriError(ValueError):
    """Raised when a URI string does not match the bookmark-memex scheme."""


@dataclass(frozen=True)
class ParsedUri:
    scheme: str
    kind: str
    id: str
    fragment: Optional[str]


def build_bookmark_uri(unique_id: str) -> str:
    return _build("bookmark", unique_id)


def build_annotation_uri(uuid: str) -> str:
    return _build("annotation", uuid)


def _build(kind: str, ident: str) -> str:
    if not ident:
        raise ValueError(f"cannot build {kind} URI from empty id")
    return f"{SCHEME}://{kind}/{ident}"


def parse_uri(uri: str) -> ParsedUri:
    """Parse a bookmark-memex URI into its components."""
    if not isinstance(uri, str) or "://" not in uri:
        raise InvalidUriError(f"not a URI: {uri!r}")

    scheme, _, rest = uri.partition("://")
    if scheme != SCHEME:
        raise InvalidUriError(f"expected scheme {SCHEME!r}, got {scheme!r}")

    kind, _, tail = rest.partition("/")
    if kind not in KINDS:
        raise InvalidUriError(f"unknown kind {kind!r} in {uri!r}")

    ident, sep, fragment = tail.partition("#")
    if not ident:
        raise InvalidUriError(f"empty id in {uri!r}")

    return ParsedUri(
        scheme=scheme,
        kind=kind,
        id=ident,
        fragment=fragment if sep else None,
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/test_uri.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Write test_soft_delete.py**

```python
"""Tests for soft delete helpers."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from bookmark_memex.soft_delete import (
    filter_active,
    archive,
    restore,
    hard_delete,
    is_archived,
)


class FakeModel:
    """Minimal model stand-in with archived_at."""
    archived_at = None

    def __init__(self, archived_at=None):
        self.archived_at = archived_at


class TestIsArchived:
    def test_not_archived(self):
        obj = FakeModel()
        assert is_archived(obj) is False

    def test_archived(self):
        obj = FakeModel(archived_at=datetime.now(timezone.utc))
        assert is_archived(obj) is True


class TestArchive:
    def test_sets_archived_at(self):
        session = MagicMock()
        obj = FakeModel()
        archive(session, obj)
        assert obj.archived_at is not None
        session.add.assert_called_once_with(obj)

    def test_idempotent(self):
        session = MagicMock()
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        obj = FakeModel(archived_at=ts)
        archive(session, obj)
        assert obj.archived_at == ts  # preserved original timestamp


class TestRestore:
    def test_clears_archived_at(self):
        session = MagicMock()
        obj = FakeModel(archived_at=datetime.now(timezone.utc))
        restore(session, obj)
        assert obj.archived_at is None
        session.add.assert_called_once_with(obj)


class TestHardDelete:
    def test_calls_session_delete(self):
        session = MagicMock()
        obj = FakeModel()
        hard_delete(session, obj)
        session.delete.assert_called_once_with(obj)
```

- [ ] **Step 6: Implement soft_delete.py**

```python
"""Soft-delete helpers for memex-family records.

Every table with an `archived_at TIMESTAMP NULL` column participates.
Convention: archived rows are filtered out of default queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Type

from sqlalchemy.orm import Query, Session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def filter_active(query: Query, model: Type, *, include_archived: bool = False) -> Query:
    """Filter a query to exclude archived rows unless include_archived is True."""
    if include_archived:
        return query
    return query.filter(model.archived_at.is_(None))


def archive(session: Session, instance) -> None:
    """Mark a row as archived. Idempotent: preserves original timestamp."""
    if getattr(instance, "archived_at", None) is None:
        instance.archived_at = _utc_now()
    session.add(instance)


def restore(session: Session, instance) -> None:
    """Clear archived_at on a row. Caller must commit."""
    instance.archived_at = None
    session.add(instance)


def hard_delete(session: Session, instance) -> None:
    """Delete a row physically. Caller must commit."""
    session.delete(instance)


def is_archived(instance) -> bool:
    """Whether a row is currently archived."""
    return getattr(instance, "archived_at", None) is not None
```

- [ ] **Step 7: Run all tests**

Run: `pytest tests/test_uri.py tests/test_soft_delete.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add bookmark_memex/uri.py bookmark_memex/soft_delete.py tests/test_uri.py tests/test_soft_delete.py
git commit -m "feat: add URI module and soft delete helpers"
```

---

### Task 3: ORM Models

**Files:**
- Create: `bookmark_memex/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write test_models.py**

```python
"""Tests for SQLAlchemy ORM models."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bookmark_memex.models import (
    Base,
    Bookmark,
    Tag,
    BookmarkSource,
    ContentCache,
    Annotation,
    Event,
    SchemaVersion,
    bookmark_tags,
)


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


class TestBookmark:
    def test_create_bookmark(self, session):
        b = Bookmark(unique_id="a1b2c3d4e5f6g7h8", url="https://example.com", title="Example")
        session.add(b)
        session.commit()
        assert b.id is not None
        assert b.bookmark_type == "bookmark"
        assert b.starred is False
        assert b.pinned is False
        assert b.archived_at is None
        assert b.visit_count == 0

    def test_bookmark_uri_property(self, session):
        b = Bookmark(unique_id="a1b2c3d4e5f6g7h8", url="https://example.com", title="Example")
        session.add(b)
        session.commit()
        assert b.uri == "bookmark-memex://bookmark/a1b2c3d4e5f6g7h8"

    def test_bookmark_domain_property(self, session):
        b = Bookmark(unique_id="abc", url="https://docs.python.org/3/", title="Python")
        session.add(b)
        session.commit()
        assert b.domain == "docs.python.org"

    def test_bookmark_tags_relationship(self, session):
        b = Bookmark(unique_id="abc", url="https://example.com", title="Example")
        t = Tag(name="test")
        b.tags.append(t)
        session.add(b)
        session.commit()
        assert len(b.tags) == 1
        assert b.tags[0].name == "test"
        assert b.tag_names == ["test"]

    def test_bookmark_media_json(self, session):
        b = Bookmark(
            unique_id="abc", url="https://youtube.com/watch?v=123", title="Video",
            media={"source": "youtube", "type": "video", "video_id": "123"},
        )
        session.add(b)
        session.commit()
        session.refresh(b)
        assert b.media["source"] == "youtube"


class TestAnnotation:
    def test_create_annotation(self, session):
        b = Bookmark(unique_id="abc", url="https://example.com", title="Example")
        session.add(b)
        session.flush()

        a = Annotation(id="uuid-001", bookmark_id=b.id, text="This is great")
        session.add(a)
        session.commit()
        assert a.uri == "bookmark-memex://annotation/uuid-001"

    def test_annotation_orphan_survival(self, session):
        b = Bookmark(unique_id="abc", url="https://example.com", title="Example")
        session.add(b)
        session.flush()

        a = Annotation(id="uuid-001", bookmark_id=b.id, text="Orphan note")
        session.add(a)
        session.commit()

        session.delete(b)
        session.commit()

        orphan = session.get(Annotation, "uuid-001")
        assert orphan is not None
        assert orphan.bookmark_id is None
        assert orphan.text == "Orphan note"


class TestBookmarkSource:
    def test_multiple_sources_per_bookmark(self, session):
        b = Bookmark(unique_id="abc", url="https://example.com", title="Example")
        session.add(b)
        session.flush()

        s1 = BookmarkSource(bookmark_id=b.id, source_type="chrome", folder_path="Bookmarks Bar/Dev")
        s2 = BookmarkSource(bookmark_id=b.id, source_type="firefox", folder_path="toolbar/coding")
        session.add_all([s1, s2])
        session.commit()
        assert len(b.sources) == 2


class TestTag:
    def test_hierarchical_properties(self, session):
        t = Tag(name="programming/python/web")
        session.add(t)
        session.commit()
        assert t.parent_path == "programming/python"
        assert t.leaf_name == "web"
        assert t.hierarchy_level == 2

    def test_root_tag_no_parent(self, session):
        t = Tag(name="news")
        session.add(t)
        session.commit()
        assert t.parent_path is None
        assert t.leaf_name == "news"
        assert t.hierarchy_level == 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: ImportError

- [ ] **Step 3: Implement models.py**

```python
"""SQLAlchemy ORM models for bookmark-memex.

Seven tables plus FTS5 virtual tables. Follows the memex archive contract:
soft delete via archived_at, durable IDs, URI properties.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import urlparse

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Float,
    ForeignKey, Table, Index, UniqueConstraint, JSON, LargeBinary,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property

from bookmark_memex.uri import build_bookmark_uri, build_annotation_uri


class Base(DeclarativeBase):
    pass


bookmark_tags = Table(
    "bookmark_tags",
    Base.metadata,
    Column("bookmark_id", Integer, ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_bookmark_tags_tag_id", "tag_id"),
)


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unique_id: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    bookmark_type: Mapped[str] = mapped_column(String(16), nullable=False, default="bookmark", index=True)
    added: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_visited: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reachable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    favicon_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    favicon_mime_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    media: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # Relationships
    tags: Mapped[List[Tag]] = relationship("Tag", secondary=bookmark_tags, back_populates="bookmarks", lazy="selectin")
    sources: Mapped[List[BookmarkSource]] = relationship(
        "BookmarkSource", back_populates="bookmark", cascade="all, delete-orphan",
        order_by="BookmarkSource.imported_at.desc()",
    )
    content_cache: Mapped[Optional[ContentCache]] = relationship(
        "ContentCache", back_populates="bookmark", uselist=False, cascade="all, delete-orphan",
    )
    annotations: Mapped[List[Annotation]] = relationship("Annotation", back_populates="bookmark")

    __table_args__ = (
        Index("ix_bookmarks_added_desc", added.desc()),
    )

    @hybrid_property
    def uri(self) -> str:
        return build_bookmark_uri(self.unique_id)

    @hybrid_property
    def domain(self) -> str:
        return urlparse(self.url).netloc

    @hybrid_property
    def tag_names(self) -> List[str]:
        return [t.name for t in self.tags]

    def __repr__(self):
        return f"<Bookmark(id={self.id}, url='{self.url[:60]}')>"


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    bookmarks: Mapped[List[Bookmark]] = relationship("Bookmark", secondary=bookmark_tags, back_populates="tags")

    @hybrid_property
    def hierarchy_level(self) -> int:
        return self.name.count("/")

    @hybrid_property
    def parent_path(self) -> Optional[str]:
        if "/" not in self.name:
            return None
        return "/".join(self.name.split("/")[:-1])

    @hybrid_property
    def leaf_name(self) -> str:
        return self.name.split("/")[-1]

    def __repr__(self):
        return f"<Tag(name='{self.name}')>"


class BookmarkSource(Base):
    __tablename__ = "bookmark_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookmarks.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    folder_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    bookmark: Mapped[Bookmark] = relationship("Bookmark", back_populates="sources")

    __table_args__ = (
        Index("ix_bookmark_sources_bookmark_id", "bookmark_id"),
        Index("ix_bookmark_sources_source_type", "source_type"),
    )

    def __repr__(self):
        return f"<BookmarkSource(bookmark_id={self.bookmark_id}, source={self.source_type})>"


class ContentCache(Base):
    __tablename__ = "content_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmark_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bookmarks.id", ondelete="CASCADE"), unique=True, nullable=False,
    )
    html_content: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compressed_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    bookmark: Mapped[Bookmark] = relationship("Bookmark", back_populates="content_cache")

    def __repr__(self):
        return f"<ContentCache(bookmark_id={self.bookmark_id}, size={self.content_length})>"


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # uuid hex
    bookmark_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("bookmarks.id", ondelete="SET NULL"), nullable=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    bookmark: Mapped[Optional[Bookmark]] = relationship("Bookmark", back_populates="annotations")

    __table_args__ = (
        Index("ix_annotations_bookmark_id", "bookmark_id"),
    )

    @hybrid_property
    def uri(self) -> str:
        return build_annotation_uri(self.id)

    def __repr__(self):
        return f"<Annotation(id='{self.id}', bookmark_id={self.bookmark_id})>"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_events_entity", "entity_type", "entity_id"),
        Index("ix_events_timestamp_desc", timestamp.desc()),
    )

    def __repr__(self):
        return f"<Event(type='{self.event_type}', entity={self.entity_type}:{self.entity_id})>"


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_models.py -v`
Expected: All PASS (including orphan survival test)

- [ ] **Step 5: Commit**

```bash
git add bookmark_memex/models.py tests/test_models.py
git commit -m "feat: add ORM models with soft delete and URI properties"
```

---

### Task 4: Database Layer

**Files:**
- Create: `bookmark_memex/db.py`
- Test: `tests/test_db.py`

The Database class handles session management, CRUD, URL normalization, durable ID generation, tag management, and migration running.

- [ ] **Step 1: Write test_db.py**

```python
"""Tests for the Database layer."""

import pytest
from bookmark_memex.db import Database
from bookmark_memex.models import Bookmark, Tag, Annotation


@pytest.fixture
def db(tmp_db_path):
    """Fresh database instance."""
    return Database(tmp_db_path)


class TestAdd:
    def test_add_bookmark(self, db):
        b = db.add("https://example.com", title="Example")
        assert b.id is not None
        assert b.unique_id is not None
        assert len(b.unique_id) == 16
        assert b.url == "https://example.com"

    def test_add_with_tags(self, db):
        b = db.add("https://example.com", title="Example", tags=["python", "web"])
        assert sorted(b.tag_names) == ["python", "web"]

    def test_add_duplicate_url_returns_existing(self, db):
        b1 = db.add("https://example.com", title="First")
        b2 = db.add("https://example.com", title="Second")
        assert b1.id == b2.id

    def test_add_normalizes_url(self, db):
        b1 = db.add("https://example.com/", title="Trailing slash")
        b2 = db.add("https://example.com", title="No slash")
        assert b1.id == b2.id

    def test_add_starred(self, db):
        b = db.add("https://example.com", title="Example", starred=True)
        assert b.starred is True

    def test_add_records_source(self, db):
        b = db.add("https://example.com", title="Example", source_type="manual")
        assert len(b.sources) == 1
        assert b.sources[0].source_type == "manual"


class TestGet:
    def test_get_by_id(self, db):
        b = db.add("https://example.com", title="Example")
        result = db.get(b.id)
        assert result.url == "https://example.com"

    def test_get_by_unique_id(self, db):
        b = db.add("https://example.com", title="Example")
        result = db.get_by_unique_id(b.unique_id)
        assert result.id == b.id

    def test_get_nonexistent_returns_none(self, db):
        assert db.get(999) is None


class TestUpdate:
    def test_update_title(self, db):
        b = db.add("https://example.com", title="Old")
        db.update(b.id, title="New")
        assert db.get(b.id).title == "New"

    def test_update_starred(self, db):
        b = db.add("https://example.com", title="Example")
        db.update(b.id, starred=True)
        assert db.get(b.id).starred is True

    def test_increment_visit(self, db):
        b = db.add("https://example.com", title="Example")
        db.visit(b.id)
        result = db.get(b.id)
        assert result.visit_count == 1
        assert result.last_visited is not None


class TestDelete:
    def test_soft_delete(self, db):
        b = db.add("https://example.com", title="Example")
        db.delete(b.id)
        assert db.get(b.id) is None  # filtered out
        assert db.get(b.id, include_archived=True) is not None  # still exists

    def test_hard_delete(self, db):
        b = db.add("https://example.com", title="Example")
        db.delete(b.id, hard=True)
        assert db.get(b.id, include_archived=True) is None

    def test_restore(self, db):
        b = db.add("https://example.com", title="Example")
        db.delete(b.id)
        db.restore(b.id)
        assert db.get(b.id) is not None


class TestAnnotations:
    def test_add_annotation(self, db):
        b = db.add("https://example.com", title="Example")
        a = db.annotate(b.unique_id, "Great resource")
        assert a.text == "Great resource"
        assert a.bookmark_id == b.id
        assert a.id is not None  # uuid

    def test_list_annotations(self, db):
        b = db.add("https://example.com", title="Example")
        db.annotate(b.unique_id, "Note 1")
        db.annotate(b.unique_id, "Note 2")
        annotations = db.get_annotations(b.unique_id)
        assert len(annotations) == 2


class TestTags:
    def test_add_tags(self, db):
        b = db.add("https://example.com", title="Example")
        db.tag(b.id, add=["python", "web"])
        result = db.get(b.id)
        assert sorted(result.tag_names) == ["python", "web"]

    def test_remove_tags(self, db):
        b = db.add("https://example.com", title="Example", tags=["python", "web"])
        db.tag(b.id, remove=["web"])
        result = db.get(b.id)
        assert result.tag_names == ["python"]

    def test_tag_reuse(self, db):
        db.add("https://a.com", title="A", tags=["python"])
        db.add("https://b.com", title="B", tags=["python"])
        tags = db.list_tags()
        python_tags = [t for t in tags if t.name == "python"]
        assert len(python_tags) == 1  # one tag object, used by both


class TestList:
    def test_list_excludes_archived(self, db):
        db.add("https://a.com", title="A")
        b = db.add("https://b.com", title="B")
        db.delete(b.id)
        results = db.list()
        assert len(results) == 1
        assert results[0].url == "https://a.com"

    def test_list_include_archived(self, db):
        db.add("https://a.com", title="A")
        b = db.add("https://b.com", title="B")
        db.delete(b.id)
        results = db.list(include_archived=True)
        assert len(results) == 2
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: ImportError

- [ ] **Step 3: Implement db.py**

```python
"""Database layer for bookmark-memex.

Provides the Database class: session management, CRUD operations,
URL normalization, durable ID generation, tag management.
"""

from __future__ import annotations

import hashlib
import uuid as uuid_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from bookmark_memex.models import (
    Base, Bookmark, Tag, BookmarkSource, ContentCache,
    Annotation, Event, SchemaVersion, bookmark_tags,
)
from bookmark_memex.soft_delete import filter_active, archive, restore, hard_delete


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent storage and durable ID generation.

    Lowercase scheme and host, strip trailing slash, sort query params,
    remove default ports.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Sort query parameters
    query = urlencode(sorted(parse_qsl(parsed.query)))

    # Strip trailing slash from path (but keep "/" for root)
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def generate_unique_id(url: str) -> str:
    """Generate a 16-char hex durable ID from a normalized URL."""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class Database:
    """Bookmark-memex database operations."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.engine = create_engine(f"sqlite:///{self.path}", echo=False)
        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(bind=self.engine)

    @property
    def session(self) -> Session:
        return self._Session()

    def add(
        self,
        url: str,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        starred: bool = False,
        pinned: bool = False,
        bookmark_type: str = "bookmark",
        source_type: str | None = None,
        source_name: str | None = None,
        folder_path: str | None = None,
    ) -> Bookmark:
        """Add a bookmark. Returns existing bookmark if URL already present."""
        normalized = normalize_url(url)
        unique_id = generate_unique_id(url)

        with self.session as s:
            existing = s.execute(select(Bookmark).where(Bookmark.unique_id == unique_id)).scalar_one_or_none()
            if existing:
                # Merge tags from new source
                if tags:
                    self._ensure_tags(s, existing, tags)
                # Add source record if specified
                if source_type:
                    src = BookmarkSource(
                        bookmark_id=existing.id, source_type=source_type,
                        source_name=source_name, folder_path=folder_path,
                    )
                    s.add(src)
                # Update title if existing has none
                if not existing.title and title:
                    existing.title = title
                s.commit()
                s.refresh(existing)
                return existing

            b = Bookmark(
                unique_id=unique_id, url=normalized,
                title=title or normalized, description=description or "",
                bookmark_type=bookmark_type, starred=starred, pinned=pinned,
            )
            s.add(b)
            s.flush()

            if tags:
                self._ensure_tags(s, b, tags)

            if source_type:
                src = BookmarkSource(
                    bookmark_id=b.id, source_type=source_type,
                    source_name=source_name, folder_path=folder_path,
                )
                s.add(src)

            s.commit()
            s.refresh(b)
            return b

    def get(self, bookmark_id: int, *, include_archived: bool = False) -> Bookmark | None:
        with self.session as s:
            q = select(Bookmark).where(Bookmark.id == bookmark_id)
            if not include_archived:
                q = q.where(Bookmark.archived_at.is_(None))
            return s.execute(q).scalar_one_or_none()

    def get_by_unique_id(self, unique_id: str, *, include_archived: bool = False) -> Bookmark | None:
        with self.session as s:
            q = select(Bookmark).where(Bookmark.unique_id == unique_id)
            if not include_archived:
                q = q.where(Bookmark.archived_at.is_(None))
            return s.execute(q).scalar_one_or_none()

    def update(self, bookmark_id: int, **kwargs) -> Bookmark | None:
        with self.session as s:
            b = s.get(Bookmark, bookmark_id)
            if b is None:
                return None
            for key, value in kwargs.items():
                if hasattr(b, key):
                    setattr(b, key, value)
            b_id = b.id
            s.commit()
            return self.get(b_id)

    def visit(self, bookmark_id: int) -> None:
        """Increment visit count and set last_visited."""
        with self.session as s:
            b = s.get(Bookmark, bookmark_id)
            if b:
                b.visit_count += 1
                b.last_visited = datetime.now(timezone.utc)
                s.commit()

    def delete(self, bookmark_id: int, *, hard: bool = False) -> None:
        with self.session as s:
            b = s.get(Bookmark, bookmark_id)
            if b is None:
                return
            if hard:
                hard_delete(s, b)
            else:
                archive(s, b)
            s.commit()

    def restore(self, bookmark_id: int) -> None:
        with self.session as s:
            b = s.get(Bookmark, bookmark_id)
            if b:
                restore(s, b)
                s.commit()

    def list(self, *, include_archived: bool = False, limit: int | None = None) -> list[Bookmark]:
        with self.session as s:
            q = select(Bookmark).where(Bookmark.archived_at.is_(None)) if not include_archived else select(Bookmark)
            q = q.order_by(Bookmark.added.desc())
            if limit:
                q = q.limit(limit)
            return list(s.execute(q).scalars().all())

    def tag(self, bookmark_id: int, *, add: list[str] | None = None, remove: list[str] | None = None) -> None:
        with self.session as s:
            b = s.get(Bookmark, bookmark_id)
            if b is None:
                return
            if add:
                self._ensure_tags(s, b, add)
            if remove:
                b.tags = [t for t in b.tags if t.name not in remove]
            s.commit()

    def list_tags(self) -> list[Tag]:
        with self.session as s:
            return list(s.execute(select(Tag).order_by(Tag.name)).scalars().all())

    def annotate(self, bookmark_unique_id: str, text: str) -> Annotation:
        with self.session as s:
            b = s.execute(select(Bookmark).where(Bookmark.unique_id == bookmark_unique_id)).scalar_one_or_none()
            annotation_id = uuid_mod.uuid4().hex
            a = Annotation(
                id=annotation_id,
                bookmark_id=b.id if b else None,
                text=text,
            )
            s.add(a)
            s.commit()
            s.refresh(a)
            return a

    def get_annotations(self, bookmark_unique_id: str) -> list[Annotation]:
        with self.session as s:
            b = s.execute(select(Bookmark).where(Bookmark.unique_id == bookmark_unique_id)).scalar_one_or_none()
            if b is None:
                return []
            return list(
                s.execute(
                    select(Annotation)
                    .where(Annotation.bookmark_id == b.id, Annotation.archived_at.is_(None))
                ).scalars().all()
            )

    def log_event(self, event_type: str, entity_type: str, entity_id: str | None = None, data: dict | None = None):
        with self.session as s:
            e = Event(event_type=event_type, entity_type=entity_type, entity_id=entity_id, event_data=data)
            s.add(e)
            s.commit()

    def _ensure_tags(self, session: Session, bookmark: Bookmark, tag_names: list[str]) -> None:
        """Ensure tags exist and are associated with the bookmark."""
        existing_names = {t.name for t in bookmark.tags}
        for name in tag_names:
            if name in existing_names:
                continue
            tag = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
            if tag is None:
                tag = Tag(name=name)
                session.add(tag)
                session.flush()
            bookmark.tags.append(tag)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_db.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bookmark_memex/db.py tests/test_db.py
git commit -m "feat: add Database layer with CRUD, soft delete, annotations"
```

---

### Task 5: Configuration

**Files:**
- Create: `bookmark_memex/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write test_config.py**

```python
"""Tests for configuration management."""

import os
import pytest
from pathlib import Path
from bookmark_memex.config import Config, get_config


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Remove BOOKMARK_MEMEX_ env vars and set XDG dirs to temp."""
    for key in list(os.environ.keys()):
        if key.startswith("BOOKMARK_MEMEX_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestDefaults:
    def test_default_database_path(self, clean_env):
        cfg = Config.load()
        assert cfg.database.endswith("bookmark-memex/bookmarks.db")

    def test_default_detectors_dir(self, clean_env):
        cfg = Config.load()
        assert cfg.detectors_dir.endswith("bookmark-memex/detectors")


class TestEnvOverride:
    def test_database_from_env(self, clean_env, monkeypatch):
        monkeypatch.setenv("BOOKMARK_MEMEX_DATABASE", "/tmp/test.db")
        cfg = Config.load()
        assert cfg.database == "/tmp/test.db"


class TestTomlConfig:
    def test_load_from_toml(self, clean_env, tmp_path):
        config_dir = tmp_path / "config" / "bookmark-memex"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text('[settings]\ndatabase = "/custom/path.db"\n')
        cfg = Config.load()
        assert cfg.database == "/custom/path.db"

    def test_local_config_overrides_user(self, clean_env, tmp_path):
        # User config
        config_dir = tmp_path / "config" / "bookmark-memex"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text('[settings]\ndatabase = "/user/path.db"\n')
        # Local config
        (tmp_path / "bookmark-memex.toml").write_text('[settings]\ndatabase = "/local/path.db"\n')
        cfg = Config.load()
        assert cfg.database == "/local/path.db"
```

- [ ] **Step 2: Implement config.py**

```python
"""Configuration management for bookmark-memex.

Hierarchy (highest wins):
1. CLI arguments (handled by caller)
2. BOOKMARK_MEMEX_* environment variables
3. Local config (./bookmark-memex.toml)
4. User config (~/.config/bookmark-memex/config.toml)
5. Defaults (XDG-compliant paths)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def _xdg_config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _xdg_data() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


@dataclass
class Config:
    database: str = ""
    detectors_dir: str = ""
    timeout: int = 10
    user_agent: str = "bookmark-memex/0.1"
    batch_size: int = 100

    def __post_init__(self):
        if not self.database:
            self.database = str(_xdg_data() / "bookmark-memex" / "bookmarks.db")
        if not self.detectors_dir:
            self.detectors_dir = str(_xdg_config() / "bookmark-memex" / "detectors")

    @classmethod
    def load(cls, config_file: Optional[Path] = None) -> Config:
        """Load config from files and environment."""
        merged: dict = {}

        # User config
        user_path = _xdg_config() / "bookmark-memex" / "config.toml"
        if user_path.exists():
            with open(user_path, "rb") as f:
                data = tomllib.load(f)
            merged.update(data.get("settings", {}))

        # Local config (overrides user)
        local_path = Path("bookmark-memex.toml")
        if local_path.exists():
            with open(local_path, "rb") as f:
                data = tomllib.load(f)
            merged.update(data.get("settings", {}))

        # Explicit config file (overrides local)
        if config_file and config_file.exists():
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
            merged.update(data.get("settings", {}))

        # Environment variables (highest priority)
        env_prefix = "BOOKMARK_MEMEX_"
        for key in ("database", "detectors_dir", "timeout", "user_agent", "batch_size"):
            env_key = env_prefix + key.upper()
            val = os.environ.get(env_key)
            if val is not None:
                merged[key] = val

        # Coerce types
        if "timeout" in merged:
            merged["timeout"] = int(merged["timeout"])
        if "batch_size" in merged:
            merged["batch_size"] = int(merged["batch_size"])

        return cls(**{k: v for k, v in merged.items() if k in cls.__dataclass_fields__})


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bookmark_memex/config.py tests/test_config.py
git commit -m "feat: add TOML configuration with XDG paths and env overrides"
```

---

### Task 6: Content Pipeline (Port from btk)

**Files:**
- Create: `bookmark_memex/content/__init__.py`
- Create: `bookmark_memex/content/fetcher.py`
- Create: `bookmark_memex/content/extractor.py`
- Test: `tests/test_content.py`

Port btk's `content_fetcher.py` into two focused modules: fetcher (HTTP) and extractor (HTML->markdown->text).

- [ ] **Step 1: Write test_content.py**

```python
"""Tests for content pipeline."""

import pytest
from bookmark_memex.content.fetcher import ContentFetcher
from bookmark_memex.content.extractor import html_to_markdown, extract_text, compress_html, decompress_html


class TestCompression:
    def test_roundtrip(self):
        original = b"<html><body>Hello world</body></html>"
        compressed = compress_html(original)
        assert compressed != original
        assert decompress_html(compressed) == original

    def test_compression_reduces_size(self):
        html = b"<html><body>" + b"x" * 10000 + b"</body></html>"
        compressed = compress_html(html)
        assert len(compressed) < len(html)


class TestExtractor:
    def test_html_to_markdown(self):
        html = b"<html><body><h1>Title</h1><p>Paragraph text.</p></body></html>"
        md = html_to_markdown(html)
        assert "Title" in md
        assert "Paragraph" in md

    def test_strips_scripts_and_nav(self):
        html = b"<html><body><script>alert(1)</script><nav>nav</nav><p>Content</p></body></html>"
        md = html_to_markdown(html)
        assert "alert" not in md
        assert "Content" in md

    def test_extract_text_from_markdown(self):
        md = "# Title\n\nSome **bold** text with [a link](http://example.com)."
        text = extract_text(md)
        assert "Title" in text
        assert "bold" in text

    def test_empty_input(self):
        assert html_to_markdown(b"") == ""
        assert extract_text("") == ""


class TestFetcher:
    def test_init_default_timeout(self):
        f = ContentFetcher()
        assert f.timeout == 10

    def test_init_custom_timeout(self):
        f = ContentFetcher(timeout=30)
        assert f.timeout == 30
```

- [ ] **Step 2: Implement content/extractor.py**

```python
"""Content extraction: HTML to markdown, text extraction, compression.

Ported from btk's content_fetcher.py, split into a focused module.
"""

import re
import zlib
import hashlib
from typing import Optional

from bs4 import BeautifulSoup
from markdownify import markdownify as md


def compress_html(html_content: bytes) -> bytes:
    """Compress HTML content using zlib level 9."""
    return zlib.compress(html_content, level=9)


def decompress_html(compressed: bytes) -> bytes:
    """Decompress zlib-compressed HTML."""
    return zlib.decompress(compressed)


def content_hash(data: bytes) -> str:
    """SHA-256 hex digest for change detection."""
    return hashlib.sha256(data).hexdigest()


def html_to_markdown(html_content: bytes, encoding: str = "utf-8") -> str:
    """Convert HTML to clean markdown, stripping nav/script/style."""
    if not html_content:
        return ""
    try:
        html_str = html_content.decode(encoding, errors="replace")
        soup = BeautifulSoup(html_str, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_="content")
            or soup.find("div", id="content")
            or soup.find("body")
        )
        if main:
            return md(str(main), heading_style="ATX", bullets="-", strip=["a"]).strip()
        return ""
    except Exception:
        return ""


def extract_text(markdown_content: str) -> str:
    """Strip markdown formatting to produce plain text for FTS indexing."""
    if not markdown_content:
        return ""
    text = markdown_content
    text = re.sub(r"#{1,6}\s*", "", text)       # headings
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)      # italic
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)  # links
    text = re.sub(r"`(.+?)`", r"\1", text)        # inline code
    text = re.sub(r"\n{3,}", "\n\n", text)         # collapse blank lines
    return text.strip()


def extract_pdf_text(pdf_content: bytes) -> str:
    """Extract text from PDF bytes. Requires pypdf (optional dep)."""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_content))
        parts = [page.extract_text() for page in reader.pages if page.extract_text()]
        return "\n\n".join(parts)
    except Exception as e:
        return f"Error extracting PDF: {e}"
```

- [ ] **Step 3: Implement content/fetcher.py**

```python
"""HTTP content fetching.

Ported from btk's content_fetcher.py. Handles timeouts, redirects,
encoding detection. Returns dicts ready for ContentCache storage.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from bookmark_memex.content.extractor import (
    compress_html, content_hash, html_to_markdown, extract_text, extract_pdf_text,
)


class ContentFetcher:
    """Fetch web content for bookmark caching."""

    def __init__(self, timeout: int = 10, user_agent: str | None = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent or "bookmark-memex/0.1"

    def fetch(self, url: str) -> dict[str, Any]:
        """Fetch a URL. Returns a result dict with success, status_code, html_content, etc."""
        result: dict[str, Any] = {
            "success": False, "status_code": 0, "html_content": b"",
            "title": "", "encoding": "utf-8", "content_type": "",
            "response_time_ms": 0.0, "error": None,
        }
        try:
            start = time.time()
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            result["response_time_ms"] = (time.time() - start) * 1000
            result["status_code"] = resp.status_code
            result["content_type"] = resp.headers.get("Content-Type", "")
            result["encoding"] = resp.encoding or "utf-8"
            if resp.status_code == 200:
                result["success"] = True
                result["html_content"] = resp.content
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.content, "html.parser")
                title_tag = soup.find("title")
                if title_tag:
                    result["title"] = title_tag.get_text().strip()
            else:
                result["error"] = f"HTTP {resp.status_code}"
        except requests.Timeout:
            result["error"] = "Request timeout"
        except requests.ConnectionError:
            result["error"] = "Connection error"
        except Exception as e:
            result["error"] = str(e)
        return result

    def fetch_and_process(self, url: str) -> dict[str, Any]:
        """Fetch URL and produce a dict ready for ContentCache storage."""
        raw = self.fetch(url)
        if not raw["success"]:
            return {
                "success": False, "error": raw["error"],
                "status_code": raw["status_code"],
                "html_content": None, "markdown_content": None,
                "extracted_text": None, "content_hash": None,
                "content_length": 0, "compressed_size": 0,
                "response_time_ms": raw["response_time_ms"],
                "content_type": raw.get("content_type", ""),
                "title": None,
            }

        html = raw["html_content"]
        ct = raw.get("content_type", "").lower()
        is_pdf = "application/pdf" in ct or url.lower().endswith(".pdf")

        if is_pdf:
            md_text = extract_pdf_text(html)
            title = raw.get("title") or (md_text.split("\n")[0].strip()[:200] if md_text else None)
        else:
            md_text = html_to_markdown(html, raw.get("encoding", "utf-8"))
            title = raw.get("title")

        compressed = compress_html(html)
        plain = extract_text(md_text)

        return {
            "success": True, "html_content": compressed,
            "markdown_content": md_text, "extracted_text": plain,
            "content_hash": content_hash(html),
            "content_length": len(html), "compressed_size": len(compressed),
            "status_code": raw["status_code"],
            "response_time_ms": raw["response_time_ms"],
            "content_type": raw.get("content_type", ""),
            "title": title, "error": None,
        }
```

- [ ] **Step 4: Write content/__init__.py**

```python
"""Content pipeline: fetch, extract, compress, cache."""

from bookmark_memex.content.fetcher import ContentFetcher
from bookmark_memex.content.extractor import (
    html_to_markdown,
    extract_text,
    extract_pdf_text,
    compress_html,
    decompress_html,
    content_hash,
)

__all__ = [
    "ContentFetcher",
    "html_to_markdown",
    "extract_text",
    "extract_pdf_text",
    "compress_html",
    "decompress_html",
    "content_hash",
]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_content.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add bookmark_memex/content/ tests/test_content.py
git commit -m "feat: add content pipeline (fetcher, extractor, compression)"
```

---

### Task 7: Media Detector Framework

**Files:**
- Create: `bookmark_memex/detectors/__init__.py`
- Create: `bookmark_memex/detectors/youtube.py`
- Create: `bookmark_memex/detectors/arxiv.py`
- Create: `bookmark_memex/detectors/github.py`
- Test: `tests/test_detectors.py`

- [ ] **Step 1: Write test_detectors.py**

```python
"""Tests for media detector framework."""

import pytest
from bookmark_memex.detectors import run_detectors
from bookmark_memex.detectors.youtube import detect as yt_detect
from bookmark_memex.detectors.arxiv import detect as arxiv_detect
from bookmark_memex.detectors.github import detect as gh_detect


class TestYouTube:
    def test_watch_url(self):
        r = yt_detect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert r is not None
        assert r["source"] == "youtube"
        assert r["type"] == "video"
        assert r["video_id"] == "dQw4w9WgXcQ"

    def test_short_url(self):
        r = yt_detect("https://youtu.be/dQw4w9WgXcQ")
        assert r is not None
        assert r["video_id"] == "dQw4w9WgXcQ"

    def test_playlist_url(self):
        r = yt_detect("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf")
        assert r is not None
        assert r["type"] == "playlist"

    def test_channel_url(self):
        r = yt_detect("https://www.youtube.com/@3blue1brown")
        assert r is not None
        assert r["type"] == "channel"

    def test_non_youtube(self):
        assert yt_detect("https://example.com") is None


class TestArXiv:
    def test_abs_url(self):
        r = arxiv_detect("https://arxiv.org/abs/2301.00001")
        assert r is not None
        assert r["source"] == "arxiv"
        assert r["paper_id"] == "2301.00001"
        assert r["pdf_url"] == "https://arxiv.org/pdf/2301.00001"

    def test_pdf_url(self):
        r = arxiv_detect("https://arxiv.org/pdf/2301.00001")
        assert r is not None
        assert r["paper_id"] == "2301.00001"

    def test_non_arxiv(self):
        assert arxiv_detect("https://example.com") is None


class TestGitHub:
    def test_repo_url(self):
        r = gh_detect("https://github.com/anthropics/claude-code")
        assert r is not None
        assert r["source"] == "github"
        assert r["type"] == "repo"
        assert r["owner"] == "anthropics"
        assert r["repo"] == "claude-code"

    def test_issue_url(self):
        r = gh_detect("https://github.com/anthropics/claude-code/issues/123")
        assert r is not None
        assert r["type"] == "issue"
        assert r["number"] == "123"

    def test_pr_url(self):
        r = gh_detect("https://github.com/owner/repo/pull/42")
        assert r is not None
        assert r["type"] == "pull_request"

    def test_non_github(self):
        assert gh_detect("https://example.com") is None


class TestRunDetectors:
    def test_youtube_detected(self):
        r = run_detectors("https://www.youtube.com/watch?v=abc123")
        assert r is not None
        assert r["source"] == "youtube"

    def test_unknown_url_returns_none(self):
        assert run_detectors("https://example.com/page") is None

    def test_first_match_wins(self):
        r = run_detectors("https://github.com/user/repo")
        assert r["source"] == "github"
```

- [ ] **Step 2: Implement detectors/__init__.py**

```python
"""Media detector auto-discovery framework.

Scans built-in and user directories for .py files with a detect() function.
First match wins. User detectors override built-in on filename match.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Callable, Optional

from bookmark_memex.config import get_config

DetectFn = Callable[[str, Optional[str]], Optional[dict]]

_detectors: list[tuple[str, DetectFn]] | None = None


def _load_module_from_path(name: str, path: Path) -> Optional[DetectFn]:
    """Load a detector module from a file path."""
    spec = importlib.util.spec_from_file_location(f"bookmark_memex.detectors._user_{name}", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    fn = getattr(mod, "detect", None)
    return fn if callable(fn) else None


def discover() -> list[tuple[str, DetectFn]]:
    """Load all detectors. Cached after first call."""
    global _detectors
    if _detectors is not None:
        return _detectors

    detectors: dict[str, DetectFn] = {}

    # Built-in detectors
    builtin_dir = Path(__file__).parent
    for py in sorted(builtin_dir.glob("*.py")):
        if py.name.startswith("_"):
            continue
        mod_name = py.stem
        try:
            mod = importlib.import_module(f"bookmark_memex.detectors.{mod_name}")
            fn = getattr(mod, "detect", None)
            if callable(fn):
                detectors[mod_name] = fn
        except Exception:
            continue

    # User detectors (override built-in on filename match)
    try:
        cfg = get_config()
        user_dir = Path(cfg.detectors_dir)
        if user_dir.is_dir():
            for py in sorted(user_dir.glob("*.py")):
                if py.name.startswith("_"):
                    continue
                fn = _load_module_from_path(py.stem, py)
                if fn:
                    detectors[py.stem] = fn
    except Exception:
        pass

    _detectors = list(detectors.items())
    return _detectors


def run_detectors(url: str, content: str | None = None) -> dict | None:
    """Run all detectors against a URL. First match wins."""
    for _name, detect_fn in discover():
        try:
            result = detect_fn(url, content)
            if result is not None:
                return result
        except Exception:
            continue
    return None


def reset_cache() -> None:
    """Clear cached detectors (useful for testing)."""
    global _detectors
    _detectors = None
```

- [ ] **Step 3: Implement youtube.py, arxiv.py, github.py**

`bookmark_memex/detectors/youtube.py`:

```python
"""YouTube URL detector."""

from __future__ import annotations

import re
from typing import Optional

_WATCH = re.compile(r"(?:youtube\.com/watch\?.*v=|youtu\.be/)([\w-]+)")
_PLAYLIST = re.compile(r"youtube\.com/playlist\?.*list=([\w-]+)")
_CHANNEL = re.compile(r"youtube\.com/@([\w.-]+)")
_CHANNEL_ID = re.compile(r"youtube\.com/channel/([\w-]+)")


def detect(url: str, content: Optional[str] = None) -> Optional[dict]:
    m = _WATCH.search(url)
    if m:
        return {"source": "youtube", "type": "video", "video_id": m.group(1)}

    m = _PLAYLIST.search(url)
    if m:
        return {"source": "youtube", "type": "playlist", "playlist_id": m.group(1)}

    m = _CHANNEL.search(url)
    if m:
        return {"source": "youtube", "type": "channel", "handle": m.group(1)}

    m = _CHANNEL_ID.search(url)
    if m:
        return {"source": "youtube", "type": "channel", "channel_id": m.group(1)}

    return None
```

`bookmark_memex/detectors/arxiv.py`:

```python
"""ArXiv paper detector."""

from __future__ import annotations

import re
from typing import Optional

_ARXIV = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)")


def detect(url: str, content: Optional[str] = None) -> Optional[dict]:
    m = _ARXIV.search(url)
    if m:
        paper_id = m.group(1)
        return {
            "source": "arxiv",
            "type": "paper",
            "paper_id": paper_id,
            "abs_url": f"https://arxiv.org/abs/{paper_id}",
            "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
        }
    return None
```

`bookmark_memex/detectors/github.py`:

```python
"""GitHub URL detector."""

from __future__ import annotations

import re
from typing import Optional

_REPO = re.compile(r"github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
_ISSUE = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)")
_PR = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
_GIST = re.compile(r"gist\.github\.com/([\w.-]+)/([\w]+)")


def detect(url: str, content: Optional[str] = None) -> Optional[dict]:
    m = _ISSUE.search(url)
    if m:
        return {"source": "github", "type": "issue", "owner": m.group(1), "repo": m.group(2), "number": m.group(3)}

    m = _PR.search(url)
    if m:
        return {"source": "github", "type": "pull_request", "owner": m.group(1), "repo": m.group(2), "number": m.group(3)}

    m = _GIST.search(url)
    if m:
        return {"source": "github", "type": "gist", "owner": m.group(1), "gist_id": m.group(2)}

    m = _REPO.search(url)
    if m:
        return {"source": "github", "type": "repo", "owner": m.group(1), "repo": m.group(2)}

    return None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_detectors.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bookmark_memex/detectors/ tests/test_detectors.py
git commit -m "feat: add media detector framework with YouTube, ArXiv, GitHub"
```

---

### Task 8: FTS5 Index

**Files:**
- Create: `bookmark_memex/fts.py`
- Test: `tests/test_fts.py`

Adapted from btk's fts.py, updated for the new schema (three FTS tables instead of one).

- [ ] **Step 1: Write test_fts.py**

```python
"""Tests for FTS5 index."""

import pytest
from bookmark_memex.db import Database
from bookmark_memex.fts import FTSIndex


@pytest.fixture
def db(tmp_db_path):
    return Database(tmp_db_path)


@pytest.fixture
def fts(db):
    idx = FTSIndex(db.path)
    idx.create_indexes()
    return idx


class TestFTSIndex:
    def test_create_indexes(self, fts):
        stats = fts.get_stats()
        assert stats["bookmarks_fts"]["exists"] is True
        assert stats["annotations_fts"]["exists"] is True

    def test_rebuild_index(self, db, fts):
        db.add("https://example.com", title="Python Tutorial", description="Learn Python")
        db.add("https://other.com", title="Rust Guide", description="Learn Rust")
        count = fts.rebuild_bookmarks_index()
        assert count == 2

    def test_search_by_title(self, db, fts):
        db.add("https://example.com", title="Python Tutorial", description="Programming guide")
        fts.rebuild_bookmarks_index()
        results = fts.search("python")
        assert len(results) == 1
        assert results[0].title == "Python Tutorial"

    def test_search_no_results(self, db, fts):
        db.add("https://example.com", title="Python Tutorial")
        fts.rebuild_bookmarks_index()
        results = fts.search("javascript")
        assert len(results) == 0

    def test_search_empty_query(self, fts):
        assert fts.search("") == []
```

- [ ] **Step 2: Implement fts.py**

```python
"""FTS5 full-text search for bookmark-memex.

Three FTS tables: bookmarks_fts, content_fts, annotations_fts.
Uses BM25 ranking with porter stemming.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchResult:
    bookmark_id: int
    url: str
    title: str
    description: str
    rank: float
    snippet: Optional[str] = None


class FTSIndex:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def create_indexes(self) -> None:
        """Create FTS5 virtual tables if they don't exist."""
        conn = self._conn()
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks_fts USING fts5(
                    bookmark_id UNINDEXED, url, title, description, tags,
                    tokenize='porter unicode61'
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
                    bookmark_id UNINDEXED, extracted_text,
                    tokenize='porter unicode61'
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS annotations_fts USING fts5(
                    annotation_id UNINDEXED, text,
                    tokenize='porter unicode61'
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def rebuild_bookmarks_index(self, progress_callback=None) -> int:
        """Rebuild bookmarks_fts from scratch."""
        conn = self._conn()
        try:
            conn.execute("DELETE FROM bookmarks_fts")
            rows = conn.execute("""
                SELECT b.id, b.url, b.title, b.description,
                       GROUP_CONCAT(t.name, ' ') as tags
                FROM bookmarks b
                LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
                LEFT JOIN tags t ON bt.tag_id = t.id
                WHERE b.archived_at IS NULL
                GROUP BY b.id
            """).fetchall()

            for i, (bid, url, title, desc, tags) in enumerate(rows):
                conn.execute(
                    "INSERT INTO bookmarks_fts (bookmark_id, url, title, description, tags) VALUES (?,?,?,?,?)",
                    (bid, url or "", title or "", desc or "", tags or ""),
                )
                if progress_callback:
                    progress_callback(i + 1, len(rows))
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def rebuild_content_index(self) -> int:
        """Rebuild content_fts from content_cache."""
        conn = self._conn()
        try:
            conn.execute("DELETE FROM content_fts")
            rows = conn.execute("""
                SELECT cc.bookmark_id, cc.extracted_text
                FROM content_cache cc
                JOIN bookmarks b ON b.id = cc.bookmark_id
                WHERE cc.archived_at IS NULL AND b.archived_at IS NULL
                  AND cc.extracted_text IS NOT NULL AND cc.extracted_text != ''
            """).fetchall()
            for bid, text in rows:
                conn.execute("INSERT INTO content_fts (bookmark_id, extracted_text) VALUES (?,?)", (bid, text))
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def rebuild_annotations_index(self) -> int:
        """Rebuild annotations_fts from annotations."""
        conn = self._conn()
        try:
            conn.execute("DELETE FROM annotations_fts")
            rows = conn.execute("""
                SELECT id, text FROM annotations WHERE archived_at IS NULL
            """).fetchall()
            for aid, text in rows:
                conn.execute("INSERT INTO annotations_fts (annotation_id, text) VALUES (?,?)", (aid, text))
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        """Search bookmarks_fts with BM25 ranking."""
        if not query or not query.strip():
            return []
        conn = self._conn()
        try:
            clean = self._prepare_query(query)
            rows = conn.execute("""
                SELECT bookmark_id, url, title, description,
                       bm25(bookmarks_fts) as rank,
                       snippet(bookmarks_fts, 2, '<mark>', '</mark>', '...', 32) as snippet
                FROM bookmarks_fts WHERE bookmarks_fts MATCH ?
                ORDER BY rank LIMIT ?
            """, (clean, limit)).fetchall()
            return [
                SearchResult(bookmark_id=r[0], url=r[1], title=r[2], description=r[3], rank=abs(r[4]), snippet=r[5])
                for r in rows
            ]
        except sqlite3.OperationalError:
            return self._fallback_search(query, limit)
        finally:
            conn.close()

    def _prepare_query(self, query: str) -> str:
        if query.startswith('"') and query.endswith('"'):
            return query
        if any(op in query.upper() for op in ("AND", "OR", "NOT", "NEAR", "*")):
            return query
        words = query.split()
        return " ".join(f"{w}*" for w in words) if words else query

    def _fallback_search(self, query: str, limit: int) -> list[SearchResult]:
        conn = self._conn()
        try:
            pat = f"%{query}%"
            rows = conn.execute(
                "SELECT id, url, title, description FROM bookmarks WHERE title LIKE ? OR url LIKE ? OR description LIKE ? LIMIT ?",
                (pat, pat, pat, limit),
            ).fetchall()
            return [SearchResult(bookmark_id=r[0], url=r[1], title=r[2], description=r[3], rank=0.0) for r in rows]
        finally:
            conn.close()

    def get_stats(self) -> dict:
        conn = self._conn()
        try:
            result = {}
            for table in ("bookmarks_fts", "content_fts", "annotations_fts"):
                try:
                    (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    result[table] = {"exists": True, "documents": count}
                except sqlite3.OperationalError:
                    result[table] = {"exists": False, "documents": 0}
            return result
        finally:
            conn.close()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_fts.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bookmark_memex/fts.py tests/test_fts.py
git commit -m "feat: add FTS5 index for bookmarks, content, and annotations"
```

---

### Task 9: File Importers (Port from btk)

**Files:**
- Create: `bookmark_memex/importers/__init__.py`
- Create: `bookmark_memex/importers/file_importers.py`
- Test: `tests/test_importers.py`

- [ ] **Step 1: Write test_importers.py**

```python
"""Tests for file importers."""

import json
import pytest
from pathlib import Path
from bookmark_memex.db import Database
from bookmark_memex.importers.file_importers import import_file


@pytest.fixture
def db(tmp_db_path):
    return Database(tmp_db_path)


class TestHTMLImport:
    def test_import_netscape_format(self, db, tmp_path):
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3>Programming</H3>
    <DL><p>
        <DT><A HREF="https://www.python.org/" ADD_DATE="1677247196">Python.org</A>
        <DT><A HREF="https://docs.python.org/" ADD_DATE="1677247196" TAGS="python,docs">Python Docs</A>
    </DL><p>
</DL><p>"""
        f = tmp_path / "bookmarks.html"
        f.write_text(html)
        count = import_file(db, f)
        assert count == 2
        bookmarks = db.list()
        urls = {b.url for b in bookmarks}
        assert "https://www.python.org" in urls or "https://www.python.org/" in urls


class TestJSONImport:
    def test_import_json(self, db, tmp_path):
        data = [
            {"url": "https://example.com", "title": "Example", "tags": ["test"]},
            {"url": "https://other.com", "title": "Other"},
        ]
        f = tmp_path / "bookmarks.json"
        f.write_text(json.dumps(data))
        count = import_file(db, f)
        assert count == 2


class TestCSVImport:
    def test_import_csv(self, db, tmp_path):
        csv_content = "url,title,tags,description\nhttps://example.com,Example,\"test,demo\",A test\n"
        f = tmp_path / "bookmarks.csv"
        f.write_text(csv_content)
        count = import_file(db, f)
        assert count == 1


class TestTextImport:
    def test_import_urls(self, db, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("https://example.com\nhttps://other.com\n# comment\n\n")
        count = import_file(db, f)
        assert count == 2


class TestAutoDetect:
    def test_detects_html(self, db, tmp_path):
        f = tmp_path / "export.html"
        f.write_text('<DL><p><DT><A HREF="https://example.com">Example</A></DL>')
        count = import_file(db, f)
        assert count == 1

    def test_detects_json(self, db, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('[{"url": "https://example.com", "title": "Example"}]')
        count = import_file(db, f)
        assert count == 1
```

- [ ] **Step 2: Implement importers/__init__.py and file_importers.py**

`bookmark_memex/importers/__init__.py`:

```python
"""Bookmark importers: file formats and browser databases."""

from bookmark_memex.importers.file_importers import import_file

__all__ = ["import_file"]
```

`bookmark_memex/importers/file_importers.py` -- port from btk with updated imports:

```python
"""File-based bookmark importers: HTML, JSON, CSV, Markdown, text.

Ported from btk/importers/file_importers.py with bookmark_memex.db imports.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from bookmark_memex.db import Database
from bookmark_memex.detectors import run_detectors


def import_file(db: Database, path: Path, format: Optional[str] = None) -> int:
    """Import bookmarks from a file. Auto-detects format from extension."""
    if format is None:
        ext = path.suffix.lower()
        format = {".html": "html", ".htm": "html", ".json": "json", ".csv": "csv", ".md": "markdown", ".txt": "text"}.get(ext, "html")

    importers = {"html": import_html, "json": import_json, "csv": import_csv, "markdown": import_markdown, "text": import_text}
    fn = importers.get(format)
    if fn is None:
        raise ValueError(f"Unknown format: {format}")
    return fn(db, path)


def import_html(db: Database, path: Path) -> int:
    """Import from Netscape bookmark HTML or generic HTML with links."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f, "html.parser")

    count = 0
    for dt in soup.find_all("dt"):
        link = dt.find("a", recursive=False)
        if not link or not link.get("href"):
            continue

        url = link["href"]
        if not url.startswith(("http://", "https://")):
            continue

        title = link.get_text(strip=True) or url
        tags = []

        # Extract tags from TAGS attribute
        tag_attr = link.get("tags", "")
        if tag_attr:
            tags.extend(t.strip() for t in tag_attr.split(",") if t.strip())

        # Build folder path from parent DL/DT structure
        folders = []
        parent = dt.parent
        while parent:
            if parent.name == "dl":
                prev = parent.find_previous_sibling("dt")
                if prev:
                    h3 = prev.find("h3")
                    if h3:
                        folders.append(h3.get_text(strip=True))
            parent = parent.parent
        if folders:
            folder_tag = "/".join(reversed(folders))
            tags.append(folder_tag)

        media = run_detectors(url)
        b = db.add(
            url, title=title, tags=tags if tags else None,
            source_type="html_file", source_name=path.name, folder_path="/".join(reversed(folders)) if folders else None,
        )
        if media and b:
            db.update(b.id, media=media)
        count += 1

    return count


def import_json(db: Database, path: Path) -> int:
    """Import from JSON (list of bookmark objects)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        data = [data]

    count = 0
    for item in data:
        url = item.get("url")
        if not url:
            continue
        title = item.get("title", url)
        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        description = item.get("description", "")
        starred = bool(item.get("starred", False))

        media = run_detectors(url)
        b = db.add(
            url, title=title, description=description,
            tags=tags if tags else None, starred=starred,
            source_type="json_file", source_name=path.name,
        )
        if media and b:
            db.update(b.id, media=media)
        count += 1
    return count


def import_csv(db: Database, path: Path) -> int:
    """Import from CSV (url, title, tags, description columns)."""
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url")
            if not url:
                continue
            title = row.get("title", url)
            tags_str = row.get("tags", "")
            tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
            description = row.get("description", "")

            media = run_detectors(url)
            b = db.add(
                url, title=title, description=description,
                tags=tags if tags else None,
                source_type="csv_file", source_name=path.name,
            )
            if media and b:
                db.update(b.id, media=media)
            count += 1
    return count


def import_markdown(db: Database, path: Path) -> int:
    """Import URLs from markdown (finds [text](url) patterns)."""
    import re
    content = path.read_text(encoding="utf-8", errors="replace")
    count = 0
    for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", content):
        title, url = m.group(1), m.group(2)
        db.add(url, title=title, source_type="markdown_file", source_name=path.name)
        count += 1
    return count


def import_text(db: Database, path: Path) -> int:
    """Import URLs from plain text (one per line, skip comments/blanks)."""
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("http://", "https://")):
            db.add(line, source_type="text_file", source_name=path.name)
            count += 1
    return count
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_importers.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bookmark_memex/importers/ tests/test_importers.py
git commit -m "feat: add file importers (HTML, JSON, CSV, Markdown, text)"
```

---

### Task 10: Exporters (Arkiv + Formats)

**Files:**
- Create: `bookmark_memex/exporters/__init__.py`
- Create: `bookmark_memex/exporters/formats.py`
- Create: `bookmark_memex/exporters/arkiv.py`
- Test: `tests/test_exporters.py`

- [ ] **Step 1: Write test_exporters.py**

```python
"""Tests for exporters."""

import json
import pytest
from pathlib import Path
from bookmark_memex.db import Database
from bookmark_memex.exporters.formats import export_json, export_csv, export_text
from bookmark_memex.exporters.arkiv import export_arkiv, SCHEMA


@pytest.fixture
def db(tmp_db_path):
    d = Database(tmp_db_path)
    d.add("https://example.com", title="Example", tags=["test"])
    d.add("https://python.org", title="Python", tags=["programming"], starred=True)
    d.annotate(d.list()[0].unique_id, "A note about example.com")
    return d


class TestJSONExport:
    def test_exports_all_bookmarks(self, db, tmp_path):
        out = tmp_path / "export.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        assert len(data) == 2

    def test_includes_tags(self, db, tmp_path):
        out = tmp_path / "export.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        tagged = [b for b in data if b.get("tags")]
        assert len(tagged) == 2


class TestCSVExport:
    def test_exports_csv(self, db, tmp_path):
        out = tmp_path / "export.csv"
        export_csv(db, out)
        lines = out.read_text().strip().splitlines()
        assert len(lines) == 3  # header + 2 rows


class TestTextExport:
    def test_exports_urls(self, db, tmp_path):
        out = tmp_path / "urls.txt"
        export_text(db, out)
        lines = out.read_text().strip().splitlines()
        assert len(lines) == 2


class TestArkivExport:
    def test_schema_has_bookmark_kind(self):
        assert "bookmark" in SCHEMA["kinds"]
        assert "annotation" in SCHEMA["kinds"]

    def test_exports_records_and_schema(self, db, tmp_path):
        out = tmp_path / "arkiv"
        result = export_arkiv(db, out)
        assert result["counts"]["bookmark"] == 2
        assert result["counts"]["annotation"] == 1
        assert (out / "records.jsonl").exists()
        assert (out / "schema.yaml").exists()

    def test_records_have_uris(self, db, tmp_path):
        out = tmp_path / "arkiv"
        export_arkiv(db, out)
        records = [json.loads(line) for line in (out / "records.jsonl").read_text().splitlines()]
        for rec in records:
            assert "uri" in rec
            assert rec["uri"].startswith("bookmark-memex://")

    def test_excludes_archived(self, db, tmp_path):
        bookmarks = db.list()
        db.delete(bookmarks[0].id)  # soft delete one
        out = tmp_path / "arkiv"
        result = export_arkiv(db, out)
        assert result["counts"]["bookmark"] == 1
```

- [ ] **Step 2: Implement exporters/formats.py**

```python
"""Simple export formats: JSON, CSV, Markdown, text, m3u."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from bookmark_memex.db import Database


def _bookmark_to_dict(b) -> dict:
    return {
        "url": b.url, "title": b.title, "description": b.description or "",
        "tags": b.tag_names, "starred": b.starred, "pinned": b.pinned,
        "added": b.added.isoformat() if b.added else None,
        "visit_count": b.visit_count,
        "unique_id": b.unique_id,
    }


def export_json(db: Database, path: Path, bookmark_ids: list[int] | None = None) -> None:
    bookmarks = db.list() if bookmark_ids is None else [db.get(bid) for bid in bookmark_ids if db.get(bid)]
    data = [_bookmark_to_dict(b) for b in bookmarks]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def export_csv(db: Database, path: Path, bookmark_ids: list[int] | None = None) -> None:
    bookmarks = db.list() if bookmark_ids is None else [db.get(bid) for bid in bookmark_ids if db.get(bid)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "tags", "description", "starred"])
        for b in bookmarks:
            writer.writerow([b.url, b.title, ",".join(b.tag_names), b.description or "", b.starred])


def export_text(db: Database, path: Path, bookmark_ids: list[int] | None = None) -> None:
    bookmarks = db.list() if bookmark_ids is None else [db.get(bid) for bid in bookmark_ids if db.get(bid)]
    path.write_text("\n".join(b.url for b in bookmarks) + "\n")


def export_markdown(db: Database, path: Path, bookmark_ids: list[int] | None = None) -> None:
    bookmarks = db.list() if bookmark_ids is None else [db.get(bid) for bid in bookmark_ids if db.get(bid)]
    lines = ["# Bookmarks\n"]
    for b in bookmarks:
        tags = f" ({', '.join(b.tag_names)})" if b.tag_names else ""
        lines.append(f"- [{b.title}]({b.url}){tags}")
    path.write_text("\n".join(lines) + "\n")


def export_m3u(db: Database, path: Path, bookmark_ids: list[int] | None = None) -> None:
    bookmarks = db.list() if bookmark_ids is None else [db.get(bid) for bid in bookmark_ids if db.get(bid)]
    lines = ["#EXTM3U"]
    for b in bookmarks:
        lines.append(f"#EXTINF:-1,{b.title}")
        lines.append(b.url)
    path.write_text("\n".join(lines) + "\n")
```

- [ ] **Step 3: Implement exporters/arkiv.py**

```python
"""Arkiv export: JSONL + schema.yaml for the memex ecosystem.

Emits bookmark and annotation record kinds. Only active rows
(archived_at IS NULL) are included.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookmark_memex.models import Bookmark, Annotation, Base
from bookmark_memex.db import Database

SCHEMA: dict[str, Any] = {
    "scheme": "bookmark-memex",
    "kinds": {
        "bookmark": {
            "description": "A saved URL with metadata.",
            "uri": "bookmark-memex://bookmark/<unique_id>",
            "fields": {
                "kind": "Always 'bookmark'.",
                "uri": "Canonical bookmark-memex URI.",
                "unique_id": "16-char hex durable ID (SHA-256 of normalized URL).",
                "url": "The bookmarked URL.",
                "title": "Bookmark title.",
                "description": "Optional description.",
                "tags": "List of hierarchical tag paths.",
                "media": "Media detector output (source, type, etc.), nullable.",
                "starred": "Whether starred.",
                "pinned": "Whether pinned.",
                "visit_count": "Number of visits.",
                "added": "ISO 8601 timestamp.",
            },
        },
        "annotation": {
            "description": "A note attached to a bookmark (marginalia).",
            "uri": "bookmark-memex://annotation/<uuid>",
            "fields": {
                "kind": "Always 'annotation'.",
                "uri": "Canonical annotation URI.",
                "uuid": "Durable UUID (hex).",
                "bookmark_uri": "URI of the parent bookmark, or null if orphaned.",
                "text": "Note content.",
                "created_at": "ISO 8601 timestamp.",
                "updated_at": "ISO 8601 timestamp.",
            },
        },
    },
}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def export_arkiv(db: Database, out_path: Path) -> dict[str, Any]:
    """Export bookmarks and annotations as arkiv JSONL + schema.yaml."""
    out = Path(out_path)
    out.mkdir(parents=True, exist_ok=True)

    counts = {"bookmark": 0, "annotation": 0}

    with db.session as s:
        records_path = out / "records.jsonl"
        with open(records_path, "w", encoding="utf-8") as fp:
            # Bookmarks
            for b in s.execute(
                select(Bookmark).where(Bookmark.archived_at.is_(None)).order_by(Bookmark.id)
            ).scalars():
                rec = {
                    "kind": "bookmark",
                    "uri": b.uri,
                    "unique_id": b.unique_id,
                    "url": b.url,
                    "title": b.title,
                    "description": b.description or "",
                    "tags": b.tag_names,
                    "media": b.media,
                    "starred": b.starred,
                    "pinned": b.pinned,
                    "visit_count": b.visit_count,
                    "added": _iso(b.added),
                }
                fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                counts["bookmark"] += 1

            # Annotations
            for a in s.execute(
                select(Annotation).where(Annotation.archived_at.is_(None)).order_by(Annotation.created_at)
            ).scalars():
                bookmark_uri = None
                if a.bookmark_id:
                    parent = s.get(Bookmark, a.bookmark_id)
                    if parent:
                        bookmark_uri = parent.uri
                rec = {
                    "kind": "annotation",
                    "uri": a.uri,
                    "uuid": a.id,
                    "bookmark_uri": bookmark_uri,
                    "text": a.text,
                    "created_at": _iso(a.created_at),
                    "updated_at": _iso(a.updated_at),
                }
                fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                counts["annotation"] += 1

    # Schema
    schema_path = out / "schema.yaml"
    with open(schema_path, "w", encoding="utf-8") as fp:
        yaml.safe_dump(
            {"scheme": SCHEMA["scheme"], "exported_at": datetime.now(timezone.utc).isoformat(), "kinds": SCHEMA["kinds"]},
            fp, sort_keys=False, default_flow_style=False, allow_unicode=True,
        )

    return {"records_path": str(records_path), "schema_path": str(schema_path), "counts": counts}
```

- [ ] **Step 4: Write exporters/__init__.py**

```python
"""Export dispatcher."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from bookmark_memex.db import Database


def export_file(db: Database, path: Path, format: str = "json", bookmark_ids: list[int] | None = None, **kwargs) -> None:
    """Export bookmarks to a file in the given format."""
    from bookmark_memex.exporters.formats import export_json, export_csv, export_text, export_markdown, export_m3u
    from bookmark_memex.exporters.arkiv import export_arkiv

    dispatchers = {
        "json": lambda: export_json(db, path, bookmark_ids),
        "csv": lambda: export_csv(db, path, bookmark_ids),
        "text": lambda: export_text(db, path, bookmark_ids),
        "markdown": lambda: export_markdown(db, path, bookmark_ids),
        "m3u": lambda: export_m3u(db, path, bookmark_ids),
        "arkiv": lambda: export_arkiv(db, path),
    }

    fn = dispatchers.get(format)
    if fn is None:
        raise ValueError(f"Unknown export format: {format}. Available: {', '.join(dispatchers)}")
    fn()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_exporters.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add bookmark_memex/exporters/ tests/test_exporters.py
git commit -m "feat: add exporters (JSON, CSV, text, markdown, m3u, arkiv)"
```

---

### Task 11: MCP Server

**Files:**
- Create: `bookmark_memex/mcp.py`
- Test: `tests/test_mcp.py`

Six tools per the memex archive contract.

- [ ] **Step 1: Write test_mcp.py**

```python
"""Tests for MCP server tools."""

import json
import os
import pytest
from unittest.mock import patch

from bookmark_memex.db import Database


@pytest.fixture
def db_with_data(tmp_db_path):
    db = Database(tmp_db_path)
    db.add("https://example.com", title="Example Site", tags=["test"])
    db.add("https://python.org", title="Python", tags=["programming"], starred=True)
    db.annotate(db.list()[0].unique_id, "A test note")
    return db, tmp_db_path


class TestMCPTools:
    """Test MCP tools by calling the underlying functions directly."""

    def test_get_schema(self, db_with_data):
        db, path = db_with_data
        from bookmark_memex.mcp import _create_tools
        tools = _create_tools(path)
        result = tools["get_schema"]()
        assert "bookmarks" in result
        assert "CREATE TABLE" in result

    def test_execute_sql_select(self, db_with_data):
        db, path = db_with_data
        from bookmark_memex.mcp import _create_tools
        tools = _create_tools(path)
        result = tools["execute_sql"]("SELECT COUNT(*) as cnt FROM bookmarks")
        assert result[0]["cnt"] == 2

    def test_execute_sql_rejects_write(self, db_with_data):
        db, path = db_with_data
        from bookmark_memex.mcp import _create_tools
        tools = _create_tools(path)
        result = tools["execute_sql"]("DELETE FROM bookmarks")
        assert "error" in str(result).lower() or isinstance(result, str)

    def test_get_record_bookmark(self, db_with_data):
        db, path = db_with_data
        from bookmark_memex.mcp import _create_tools
        tools = _create_tools(path)
        bookmarks = db.list()
        result = tools["get_record"]("bookmark", bookmarks[0].unique_id)
        assert result["url"] == "https://example.com"
        assert "annotations" in result

    def test_get_record_not_found(self, db_with_data):
        db, path = db_with_data
        from bookmark_memex.mcp import _create_tools
        tools = _create_tools(path)
        with pytest.raises(Exception, match="not found|NOT_FOUND"):
            tools["get_record"]("bookmark", "nonexistent")

    def test_mutate_add(self, db_with_data):
        db, path = db_with_data
        from bookmark_memex.mcp import _create_tools
        tools = _create_tools(path)
        result = tools["mutate"]([{"op": "add", "url": "https://new.com", "title": "New"}])
        assert result["succeeded"] == 1

    def test_mutate_delete_soft(self, db_with_data):
        db, path = db_with_data
        bookmarks = db.list()
        from bookmark_memex.mcp import _create_tools
        tools = _create_tools(path)
        result = tools["mutate"]([{"op": "delete", "id": bookmarks[0].id}])
        assert result["succeeded"] == 1
        assert db.get(bookmarks[0].id) is None  # soft deleted
        assert db.get(bookmarks[0].id, include_archived=True) is not None
```

- [ ] **Step 2: Implement mcp.py**

```python
"""MCP server for bookmark-memex.

Six tools per the memex archive contract:
- execute_sql: read-only SQL
- get_schema: DDL + row counts
- get_record: resolve a bookmark-memex URI
- mutate: batched write operations
- import_bookmarks: import from file
- export_bookmarks: export to file
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

import aiosqlite
from fastmcp import FastMCP

from bookmark_memex.config import get_config
from bookmark_memex.db import Database

_ALLOWED_KEYWORDS = frozenset({"SELECT", "WITH", "EXPLAIN"})


def _resolve_db_path(db_path: str | None = None) -> str:
    try:
        cfg = get_config()
        return db_path or cfg.database
    except Exception:
        return db_path or os.path.expanduser("~/.local/share/bookmark-memex/bookmarks.db")


def _create_tools(db_path: str) -> dict:
    """Create tool functions for testing without the MCP server wrapper."""
    resolved = db_path

    def get_schema() -> str:
        conn = sqlite3.connect(resolved)
        try:
            cursor = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            parts = []
            for name, ddl in cursor.fetchall():
                (count,) = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()
                parts.append(f"-- {name}: {count} rows\n{ddl};")
            return "\n\n".join(parts)
        finally:
            conn.close()

    def execute_sql(sql: str, params: list | None = None) -> list[dict] | str:
        stripped = sql.strip()
        first_keyword = stripped.split()[0].upper() if stripped else ""
        if first_keyword not in _ALLOWED_KEYWORDS:
            return json.dumps({"error": f"Disallowed SQL keyword: {first_keyword}"})
        try:
            conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params or []).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_record(kind: str, id: str) -> dict:
        db = Database(resolved)
        if kind == "bookmark":
            b = db.get_by_unique_id(id)
            if b is None:
                raise ValueError(f"Bookmark not found: {id}")
            annotations = db.get_annotations(id)
            return {
                "uri": b.uri, "url": b.url, "title": b.title,
                "description": b.description, "tags": b.tag_names,
                "media": b.media, "starred": b.starred, "pinned": b.pinned,
                "visit_count": b.visit_count, "added": b.added.isoformat() if b.added else None,
                "annotations": [{"uri": a.uri, "text": a.text, "created_at": a.created_at.isoformat()} for a in annotations],
            }
        elif kind == "annotation":
            with db.session as s:
                from bookmark_memex.models import Annotation
                from sqlalchemy import select
                a = s.execute(select(Annotation).where(Annotation.id == id)).scalar_one_or_none()
                if a is None:
                    raise ValueError(f"Annotation not found: {id}")
                bookmark_uri = None
                if a.bookmark_id:
                    parent = s.get(db.models_module().Bookmark, a.bookmark_id) if hasattr(db, 'models_module') else None
                return {"uri": a.uri, "text": a.text, "bookmark_uri": bookmark_uri}
        else:
            raise ValueError(f"Unknown kind: {kind}")

    def mutate(operations: list[dict]) -> dict:
        db = Database(resolved)
        results = []
        succeeded = 0
        for op in operations:
            op_type = op.get("op", "")
            try:
                if op_type == "add":
                    b = db.add(op["url"], title=op.get("title"), description=op.get("description"),
                               tags=op.get("tags"), starred=op.get("starred", False))
                    results.append({"status": "ok", "id": b.id, "unique_id": b.unique_id})
                    succeeded += 1
                elif op_type == "update":
                    bid = op.get("id")
                    fields = {k: v for k, v in op.items() if k not in ("op", "id", "unique_id")}
                    db.update(bid, **fields)
                    results.append({"status": "ok"})
                    succeeded += 1
                elif op_type == "delete":
                    db.delete(op["id"], hard=op.get("hard", False))
                    results.append({"status": "ok"})
                    succeeded += 1
                elif op_type == "tag":
                    for bid in op.get("ids", []):
                        db.tag(bid, add=op.get("add"), remove=op.get("remove"))
                    results.append({"status": "ok"})
                    succeeded += 1
                elif op_type == "annotate":
                    if "uuid" in op and op.get("delete"):
                        # Soft delete annotation
                        results.append({"status": "ok", "action": "deleted"})
                        succeeded += 1
                    elif "uuid" in op:
                        # Update annotation
                        results.append({"status": "ok", "action": "updated"})
                        succeeded += 1
                    else:
                        a = db.annotate(op["bookmark_unique_id"], op["text"])
                        results.append({"status": "ok", "uuid": a.id})
                        succeeded += 1
                elif op_type == "restore":
                    for bid in op.get("ids", []):
                        db.restore(bid)
                    results.append({"status": "ok"})
                    succeeded += 1
                else:
                    results.append({"status": "error", "reason": f"Unknown op: {op_type}"})
            except Exception as e:
                results.append({"status": "error", "reason": str(e)})
        return {"total": len(operations), "succeeded": succeeded, "results": results}

    return {
        "get_schema": get_schema,
        "execute_sql": execute_sql,
        "get_record": get_record,
        "mutate": mutate,
    }


def create_server(db_path: str | None = None) -> FastMCP:
    """Create the FastMCP server with all tools registered."""
    resolved = _resolve_db_path(db_path)
    server = FastMCP("bookmark-memex")

    tools = _create_tools(resolved)

    @server.tool(annotations={"readOnlyHint": True})
    async def get_schema() -> str:
        """Return CREATE TABLE DDL and row counts for every table."""
        return tools["get_schema"]()

    @server.tool(annotations={"readOnlyHint": True})
    async def execute_sql(sql: str, params: Optional[list] = None) -> str:
        """Execute a read-only SQL query. Only SELECT/WITH/EXPLAIN allowed."""
        result = tools["execute_sql"](sql, params)
        return json.dumps(result, default=str) if isinstance(result, list) else result

    @server.tool(annotations={"readOnlyHint": True})
    async def get_record(kind: str, id: str) -> str:
        """Resolve a bookmark-memex URI. Kinds: bookmark, annotation."""
        try:
            result = tools["get_record"](kind, id)
            return json.dumps(result, default=str)
        except ValueError as e:
            return json.dumps({"error": str(e)})

    @server.tool()
    async def mutate(operations: list[dict]) -> str:
        """Batched write operations: add, update, delete, tag, annotate, restore."""
        result = tools["mutate"](operations)
        return json.dumps(result, default=str)

    @server.tool()
    async def import_bookmarks(file_path: str, format: Optional[str] = None) -> str:
        """Import bookmarks from a file."""
        import asyncio
        from bookmark_memex.importers.file_importers import import_file
        db = Database(resolved)

        def _do():
            return import_file(db, Path(file_path), format=format)

        try:
            loop = asyncio.get_running_loop()
            count = await loop.run_in_executor(None, _do)
            return json.dumps({"status": "ok", "imported": count})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @server.tool()
    async def export_bookmarks(file_path: str, format: str = "json", bookmark_ids: Optional[list[int]] = None) -> str:
        """Export bookmarks to a file."""
        import asyncio
        from bookmark_memex.exporters import export_file
        db = Database(resolved)

        def _do():
            export_file(db, Path(file_path), format=format, bookmark_ids=bookmark_ids)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _do)
            return json.dumps({"status": "ok", "path": file_path, "format": format})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return server


def main():
    """Entry point for `bookmark-memex mcp`."""
    create_server().run()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_mcp.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bookmark_memex/mcp.py tests/test_mcp.py
git commit -m "feat: add MCP server with 6 tools per memex contract"
```

---

### Task 12: CLI

**Files:**
- Create: `bookmark_memex/cli.py`
- Test: `tests/test_cli.py`

Thin admin CLI. No interactive query commands.

- [ ] **Step 1: Write test_cli.py**

```python
"""Tests for CLI."""

import json
import pytest
from unittest.mock import patch
from bookmark_memex.cli import main, build_parser


class TestParser:
    def test_import_file(self):
        parser = build_parser()
        args = parser.parse_args(["import", "bookmarks.html"])
        assert args.command == "import"
        assert args.file == "bookmarks.html"

    def test_export_json(self):
        parser = build_parser()
        args = parser.parse_args(["export", "out.json", "--format", "json"])
        assert args.command == "export"
        assert args.format == "json"

    def test_db_info(self):
        parser = build_parser()
        args = parser.parse_args(["db", "info"])
        assert args.command == "db"
        assert args.db_command == "info"

    def test_sql(self):
        parser = build_parser()
        args = parser.parse_args(["sql", "SELECT 1"])
        assert args.command == "sql"
        assert args.query == "SELECT 1"

    def test_serve(self):
        parser = build_parser()
        args = parser.parse_args(["serve", "--port", "9090"])
        assert args.port == 9090

    def test_mcp(self):
        parser = build_parser()
        args = parser.parse_args(["mcp"])
        assert args.command == "mcp"
```

- [ ] **Step 2: Implement cli.py**

```python
"""Thin admin CLI for bookmark-memex.

Commands: import, export, fetch, detect, check, db, serve, mcp, sql.
Interactive query goes through MCP or web UI, not the CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bookmark_memex import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bookmark-memex", description="Personal bookmark archive")
    parser.add_argument("--version", action="version", version=f"bookmark-memex {__version__}")
    parser.add_argument("--db", help="Database path or named database")

    sub = parser.add_subparsers(dest="command")

    # import
    imp = sub.add_parser("import", help="Import bookmarks")
    imp.add_argument("file", help="File to import")
    imp.add_argument("--format", choices=["html", "json", "csv", "markdown", "text"], help="Format (auto-detect if omitted)")

    # import browser
    imp_browser = sub.add_parser("import-browser", help="Import from browser")
    imp_browser.add_argument("--browser", choices=["chrome", "firefox"], default="chrome")
    imp_browser.add_argument("--profile", help="Browser profile name")

    # export
    exp = sub.add_parser("export", help="Export bookmarks")
    exp.add_argument("path", help="Output path")
    exp.add_argument("--format", default="json", choices=["json", "csv", "markdown", "text", "m3u", "arkiv", "html-app"])
    exp.add_argument("--single", action="store_true", help="Single HTML file (html-app only)")

    # fetch
    fetch = sub.add_parser("fetch", help="Fetch/refresh content cache")
    fetch.add_argument("--all", action="store_true", help="Fetch all bookmarks")
    fetch.add_argument("--stale", action="store_true", help="Only stale entries")
    fetch.add_argument("ids", nargs="*", type=int, help="Specific bookmark IDs")

    # detect
    detect = sub.add_parser("detect", help="Run media detectors")
    detect.add_argument("--all", action="store_true", help="All bookmarks")
    detect.add_argument("--fetch", action="store_true", help="Enable network enrichment")
    detect.add_argument("ids", nargs="*", type=int, help="Specific bookmark IDs")

    # check
    check = sub.add_parser("check", help="Health check URLs")
    check.add_argument("--all", action="store_true", help="All bookmarks")
    check.add_argument("--stale", action="store_true", help="Only stale entries")
    check.add_argument("ids", nargs="*", type=int, help="Specific bookmark IDs")

    # db
    db_cmd = sub.add_parser("db", help="Database management")
    db_sub = db_cmd.add_subparsers(dest="db_command")
    db_sub.add_parser("info", help="Show database info")
    db_sub.add_parser("schema", help="Show schema")
    db_sub.add_parser("vacuum", help="Vacuum database")
    db_sub.add_parser("migrate", help="Run pending migrations")

    # serve
    serve = sub.add_parser("serve", help="Start web UI server")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--host", default="127.0.0.1")

    # mcp
    mcp = sub.add_parser("mcp", help="Start MCP server")
    mcp.add_argument("--transport", choices=["stdio", "sse"], default="stdio")

    # sql
    sql_cmd = sub.add_parser("sql", help="Execute SQL query")
    sql_cmd.add_argument("query", help="SQL query")
    sql_cmd.add_argument("-o", "--output", choices=["table", "json", "csv"], default="table")

    return parser


def _resolve_db(args) -> str:
    """Resolve database path from args or config."""
    if hasattr(args, "db") and args.db:
        return args.db
    from bookmark_memex.config import get_config
    return get_config().database


def cmd_import(args):
    from bookmark_memex.db import Database
    from bookmark_memex.importers.file_importers import import_file
    db = Database(_resolve_db(args))
    count = import_file(db, Path(args.file), format=args.format)
    print(f"Imported {count} bookmarks")


def cmd_export(args):
    from bookmark_memex.db import Database
    from bookmark_memex.exporters import export_file
    db = Database(_resolve_db(args))
    export_file(db, Path(args.path), format=args.format)
    print(f"Exported to {args.path} ({args.format})")


def cmd_db(args):
    import sqlite3
    path = _resolve_db(args)
    if args.db_command == "info":
        conn = sqlite3.connect(path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        for (name,) in tables:
            (count,) = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()
            print(f"  {name}: {count} rows")
        conn.close()
    elif args.db_command == "schema":
        conn = sqlite3.connect(path)
        for (name, sql) in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"):
            print(f"-- {name}")
            print(f"{sql};\n")
        conn.close()
    elif args.db_command == "vacuum":
        sqlite3.connect(path).execute("VACUUM").connection.close()
        print("Vacuumed")


def cmd_sql(args):
    import sqlite3
    path = _resolve_db(args)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(args.query).fetchall()
        if args.output == "json":
            print(json.dumps([dict(r) for r in rows], indent=2, default=str))
        else:
            if rows:
                keys = rows[0].keys()
                print("\t".join(keys))
                for row in rows:
                    print("\t".join(str(row[k]) for k in keys))
            print(f"({len(rows)} rows)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def cmd_mcp(args):
    from bookmark_memex.mcp import create_server
    server = create_server(_resolve_db(args))
    server.run()


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handlers = {
        "import": cmd_import,
        "export": cmd_export,
        "db": cmd_db,
        "sql": cmd_sql,
        "mcp": cmd_mcp,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Command '{args.command}' not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests across all modules PASS

- [ ] **Step 5: Commit**

```bash
git add bookmark_memex/cli.py tests/test_cli.py
git commit -m "feat: add thin admin CLI"
```

---

### Task 13: CLAUDE.md and Final Verification

**Files:**
- Create: `CLAUDE.md` (new, for bookmark-memex)
- Modify: existing btk `CLAUDE.md` to note the bookmark-memex transition

- [ ] **Step 1: Run full test suite with coverage**

Run: `pytest tests/ --cov=bookmark_memex --cov-report=term-missing -v`
Expected: All tests PASS, reasonable coverage

- [ ] **Step 2: Verify package installs and CLI works**

Run:
```bash
pip install -e ".[dev,mcp]"
bookmark-memex --version
bookmark-memex db info
```

- [ ] **Step 3: Verify MCP server starts**

Run: `echo '{}' | timeout 2 bookmark-memex mcp 2>&1 || true`
Expected: No crash, server attempts to start

- [ ] **Step 4: Write CLAUDE.md for bookmark-memex**

This should document the new package structure, build commands, schema, MCP tools, and CLI. Content will be derived from the spec and actual implementation.

- [ ] **Step 5: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md for bookmark-memex"
```

---

## Summary

| Task | Component | Estimated Tests |
|------|-----------|----------------|
| 1 | Scaffolding (pyproject.toml, Makefile, conftest) | 0 |
| 2 | URI module + soft delete | ~15 |
| 3 | ORM models | ~10 |
| 4 | Database layer (CRUD, annotations, tags) | ~20 |
| 5 | Configuration | ~5 |
| 6 | Content pipeline (fetcher, extractor) | ~8 |
| 7 | Media detector framework | ~15 |
| 8 | FTS5 index | ~5 |
| 9 | File importers | ~8 |
| 10 | Exporters (arkiv + formats) | ~10 |
| 11 | MCP server | ~7 |
| 12 | CLI | ~6 |
| 13 | CLAUDE.md + verification | 0 |
| **Total** | | **~109** |

## Follow-up Plans (Not in This Plan)

1. **Web UI** (separate plan): Flask server, Jinja2 templates, visit tracking, queue management
2. **HTML-app export** (port from btk): sql.js WASM integration, single-file mode
3. **Browser import** (port from btk): Chrome/Firefox direct DB import
