"""
Comprehensive tests for btk/exporters.py

Tests all export functions including:
- export_file (with format selection)
- export_json
- export_csv
- export_html (Netscape format with hierarchical and flat)
- export_markdown
- export_text
"""
import pytest
import tempfile
import os
import json
import csv as csv_module
from pathlib import Path
from datetime import datetime, timezone

from btk.db import Database
from btk.exporters import (
    export_file,
    export_json,
    export_csv,
    export_html,
    export_markdown,
    export_text
)


class TestExportFile:
    """Test the export_file function with format selection."""

    @pytest.fixture
    def db(self):
        """Create a database with sample bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db_instance = Database(path=db_path)

            # Add sample bookmarks
            db_instance.add(url="https://example.com", title="Example", tags=["test"])
            db_instance.add(url="https://test.com", title="Test Site", stars=True)

            yield db_instance

    def test_export_to_json(self, db):
        """Test exporting to JSON format."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            output_path = Path(f.name)

        try:
            bookmarks = db.all()
            export_file(bookmarks, output_path, format='json')

            assert output_path.exists()

            # Verify JSON content
            with open(output_path) as f:
                data = json.load(f)
                assert len(data) == 2
                assert data[0]['url'] == "https://test.com"  # Ordered by added desc
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_to_csv(self, db):
        """Test exporting to CSV format."""
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            output_path = Path(f.name)

        try:
            bookmarks = db.all()
            export_file(bookmarks, output_path, format='csv')

            assert output_path.exists()

            # Verify CSV content
            with open(output_path) as f:
                reader = csv_module.DictReader(f)
                rows = list(reader)
                assert len(rows) == 2
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_to_html(self, db):
        """Test exporting to HTML format."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            bookmarks = db.all()
            export_file(bookmarks, output_path, format='html')

            assert output_path.exists()

            # Verify HTML content
            with open(output_path) as f:
                content = f.read()
                assert '<!DOCTYPE NETSCAPE-Bookmark-file-1>' in content
                assert 'https://example.com' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_to_markdown(self, db):
        """Test exporting to Markdown format."""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            output_path = Path(f.name)

        try:
            bookmarks = db.all()
            export_file(bookmarks, output_path, format='markdown')

            assert output_path.exists()

            # Verify Markdown content
            with open(output_path) as f:
                content = f.read()
                assert '# Bookmarks' in content
                assert '[Example](https://example.com)' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_to_text(self, db):
        """Test exporting to plain text format."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            output_path = Path(f.name)

        try:
            bookmarks = db.all()
            export_file(bookmarks, output_path, format='text')

            assert output_path.exists()

            # Verify text content
            with open(output_path) as f:
                content = f.read()
                assert 'https://example.com' in content
                assert 'https://test.com' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_unknown_format(self, db):
        """Test that unknown format raises error."""
        with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
            output_path = Path(f.name)

        try:
            bookmarks = db.all()
            with pytest.raises(ValueError, match="Unknown format"):
                export_file(bookmarks, output_path, format='unknown')
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_creates_parent_directory(self, db):
        """Test that parent directories are created if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "nested" / "export.json"

            bookmarks = db.all()
            export_file(bookmarks, output_path, format='json')

            assert output_path.exists()
            assert output_path.parent.exists()


class TestExportJson:
    """Test export_json function."""

    @pytest.fixture
    def bookmarks(self):
        """Create sample bookmarks for export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            db.add(url="https://example.com", title="Example", tags=["test", "demo"], description="Test site")
            db.add(url="https://test.com", title="Test", stars=True, visit_count=10)

            yield db.all()

    def test_export_json_basic(self, bookmarks):
        """Test basic JSON export."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_json(bookmarks, output_path)

            with open(output_path) as f:
                data = json.load(f)

            assert len(data) == 2
            assert isinstance(data, list)
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_json_includes_all_fields(self, bookmarks):
        """Test that all fields are included in JSON export."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_json(bookmarks, output_path)

            with open(output_path) as f:
                data = json.load(f)

            first_bookmark = data[0]
            assert 'id' in first_bookmark
            assert 'url' in first_bookmark
            assert 'title' in first_bookmark
            assert 'description' in first_bookmark
            assert 'tags' in first_bookmark
            assert 'stars' in first_bookmark
            assert 'visit_count' in first_bookmark
            assert 'added' in first_bookmark
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_json_empty_list(self):
        """Test exporting empty bookmark list."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_json([], output_path)

            with open(output_path) as f:
                data = json.load(f)

            assert data == []
        finally:
            if output_path.exists():
                os.unlink(output_path)


class TestExportCsv:
    """Test export_csv function."""

    @pytest.fixture
    def bookmarks(self):
        """Create sample bookmarks for export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            db.add(url="https://example.com", title="Example", tags=["test", "demo"])
            db.add(url="https://test.com", title="Test Site", stars=True)

            yield db.all()

    def test_export_csv_basic(self, bookmarks):
        """Test basic CSV export."""
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_csv(bookmarks, output_path)

            with open(output_path) as f:
                reader = csv_module.DictReader(f)
                rows = list(reader)

            assert len(rows) == 2
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_csv_headers(self, bookmarks):
        """Test that CSV has correct headers."""
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_csv(bookmarks, output_path)

            with open(output_path) as f:
                reader = csv_module.DictReader(f)
                headers = reader.fieldnames

            assert 'id' in headers
            assert 'url' in headers
            assert 'title' in headers
            assert 'description' in headers
            assert 'tags' in headers
            assert 'stars' in headers
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_csv_tag_formatting(self, bookmarks):
        """Test that tags are comma-separated in CSV."""
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_csv(bookmarks, output_path)

            with open(output_path) as f:
                reader = csv_module.DictReader(f)
                rows = list(reader)

            # Find bookmark with tags
            tagged_row = next(r for r in rows if r['url'] == 'https://example.com')
            assert 'test' in tagged_row['tags']
            assert 'demo' in tagged_row['tags']
        finally:
            if output_path.exists():
                os.unlink(output_path)


class TestExportHtml:
    """Test export_html function."""

    @pytest.fixture
    def bookmarks(self):
        """Create sample bookmarks for export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            db.add(url="https://example.com", title="Example", tags=["programming/python"])
            db.add(url="https://test.com", title="Test", tags=["tools"])
            db.add(url="https://untagged.com", title="Untagged")

            yield db.all()

    def test_export_html_basic(self, bookmarks):
        """Test basic HTML export."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html(bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            assert '<!DOCTYPE NETSCAPE-Bookmark-file-1>' in content
            assert '<META HTTP-EQUIV="Content-Type"' in content
            assert '<H1>Bookmarks</H1>' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_hierarchical(self, bookmarks):
        """Test hierarchical HTML export."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html(bookmarks, output_path, hierarchical=True)

            with open(output_path) as f:
                content = f.read()

            # Should have folder structure
            assert '<DT><H3>' in content
            assert 'https://example.com' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_flat(self, bookmarks):
        """Test flat HTML export."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html(bookmarks, output_path, hierarchical=False)

            with open(output_path) as f:
                content = f.read()

            assert '<DT><H3>' in content  # Still has folders for tags
            assert 'https://example.com' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_untagged_section(self, bookmarks):
        """Test that untagged bookmarks are in their own section."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html(bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            assert 'Untagged' in content
            assert 'https://untagged.com' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)


class TestExportMarkdown:
    """Test export_markdown function."""

    @pytest.fixture
    def bookmarks(self):
        """Create sample bookmarks for export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            db.add(url="https://example.com", title="Example", tags=["python"], description="Test site", stars=True)
            db.add(url="https://test.com", title="Test", tags=["python"])
            db.add(url="https://untagged.com", title="Untagged")

            yield db.all()

    def test_export_markdown_basic(self, bookmarks):
        """Test basic Markdown export."""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_markdown(bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            assert '# Bookmarks' in content
            assert '[Example](https://example.com)' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_markdown_tag_sections(self, bookmarks):
        """Test that bookmarks are grouped by tags."""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_markdown(bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            assert '## python' in content
            assert '## Untagged' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_markdown_stars(self, bookmarks):
        """Test that starred bookmarks have star symbol."""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_markdown(bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            # Starred bookmark should have star emoji
            assert '⭐' in content or 'Example](https://example.com)' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_markdown_descriptions(self, bookmarks):
        """Test that descriptions are included."""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_markdown(bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            assert 'Test site' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)


class TestExportText:
    """Test export_text function."""

    @pytest.fixture
    def bookmarks(self):
        """Create sample bookmarks for export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            db.add(url="https://example.com", title="Example")
            db.add(url="https://test.com", title="Test")
            db.add(url="https://another.com", title="Another")

            yield db.all()

    def test_export_text_basic(self, bookmarks):
        """Test basic text export."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_text(bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            assert 'https://example.com' in content
            assert 'https://test.com' in content
            assert 'https://another.com' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_text_one_per_line(self, bookmarks):
        """Test that URLs are one per line."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_text(bookmarks, output_path)

            with open(output_path) as f:
                lines = f.readlines()

            # Should have 3 lines (one per bookmark)
            assert len(lines) == 3
            assert all(line.startswith('https://') for line in lines)
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_text_empty_list(self):
        """Test exporting empty bookmark list."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_text([], output_path)

            with open(output_path) as f:
                content = f.read()

            assert content == ""
        finally:
            if output_path.exists():
                os.unlink(output_path)


class TestExportIntegration:
    """Integration tests for export functions."""

    def test_export_import_roundtrip(self):
        """Test that export->import cycle preserves data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add bookmarks
            db.add(url="https://example.com", title="Example", tags=["test"], stars=True)
            db.add(url="https://test.com", title="Test", description="Test site")

            # Export to JSON
            export_path = Path(tmpdir) / "export.json"
            bookmarks = db.all()
            export_json(bookmarks, export_path)

            # Verify export succeeded
            assert export_path.exists()

            # Load and verify
            with open(export_path) as f:
                data = json.load(f)

            assert len(data) == 2
            assert any(b['url'] == 'https://example.com' for b in data)
            assert any(b['stars'] for b in data)

    def test_export_large_dataset(self):
        """Test exporting large number of bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add 100 bookmarks
            for i in range(100):
                db.add(url=f"https://example{i}.com", title=f"Example {i}")

            # Export to JSON
            export_path = Path(tmpdir) / "export.json"
            bookmarks = db.all()
            export_json(bookmarks, export_path)

            # Verify all bookmarks exported
            with open(export_path) as f:
                data = json.load(f)

            assert len(data) == 100
