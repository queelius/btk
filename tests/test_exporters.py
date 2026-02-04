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
    export_html_app,
    export_markdown,
    export_text,
    export_m3u,
    _serialize_bookmark_for_app,
    _get_tag_stats,
    _get_export_stats
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


class TestExportM3u:
    """Test export_m3u function for media playlists."""

    @pytest.fixture
    def media_bookmarks(self):
        """Create sample media bookmarks for export."""
        from btk.models import Bookmark
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add media bookmarks
            b1 = db.add(url="https://youtube.com/watch?v=abc123", title="Video 1")
            b2 = db.add(url="https://youtube.com/watch?v=def456", title="Video 2")
            b3 = db.add(url="https://example.com/page", title="Non-media")

            # Set media attributes directly on the model
            with db.session() as session:
                bm1 = session.get(Bookmark, b1.id)
                bm1.media_type = 'video'
                bm1.media_source = 'youtube'
                bm1.author_name = 'Test Channel'

                bm2 = session.get(Bookmark, b2.id)
                bm2.media_type = 'audio'
                bm2.media_source = 'youtube'

            yield db.all()

    def test_export_m3u_basic(self, media_bookmarks):
        """Test basic M3U export."""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_m3u(media_bookmarks, output_path)

            with open(output_path) as f:
                content = f.read()

            # Should have EXTM3U header
            assert '#EXTM3U' in content
            # Should have YouTube URLs
            assert 'youtube.com/watch?v=abc123' in content
            assert 'youtube.com/watch?v=def456' in content
            # Should NOT have non-media URL
            assert 'example.com/page' not in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_m3u_extinf_format(self, media_bookmarks):
        """Test M3U EXTINF line format."""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_m3u(media_bookmarks, output_path, extended=True)

            with open(output_path) as f:
                content = f.read()

            # Should have EXTINF lines (duration is always -1 since we don't track it)
            assert '#EXTINF:-1,' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_m3u_non_extended(self, media_bookmarks):
        """Test non-extended M3U export."""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_m3u(media_bookmarks, output_path, extended=False)

            with open(output_path) as f:
                content = f.read()

            # Should NOT have EXTM3U header in non-extended mode
            assert '#EXTM3U' not in content
            # Should still have URLs
            assert 'youtube.com' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_m3u_author_in_title(self, media_bookmarks):
        """Test that author name is included in EXTINF title."""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_m3u(media_bookmarks, output_path, extended=True)

            with open(output_path) as f:
                content = f.read()

            # Should have "Author - Title" format for first video
            assert 'Test Channel - Video 1' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_m3u_file_format_alias(self, media_bookmarks):
        """Test that m3u8 alias works in export_file."""
        with tempfile.NamedTemporaryFile(suffix='.m3u8', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_file(media_bookmarks, output_path, format='m3u8')

            with open(output_path) as f:
                content = f.read()

            assert '#EXTM3U' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_m3u_empty_list(self):
        """Test exporting empty bookmark list to M3U."""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_m3u([], output_path)

            with open(output_path) as f:
                content = f.read()

            # Should just have header
            assert content.strip() == '#EXTM3U'
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_m3u_no_media_bookmarks(self):
        """Test M3U export with no media-type bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add non-media bookmarks only
            db.add(url="https://example.com", title="Regular Site")
            db.add(url="https://another.com", title="Another Site")

            bookmarks = db.all()

            with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
                output_path = Path(f.name)

            try:
                export_m3u(bookmarks, output_path)

                with open(output_path) as f:
                    lines = f.readlines()

                # Should just have header, no URLs
                assert len(lines) == 1
                assert '#EXTM3U' in lines[0]
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


class TestExportHtmlApp:
    """Test export_html_app function for interactive HTML viewer."""

    @pytest.fixture
    def sample_bookmarks(self):
        """Create sample bookmarks for export."""
        from btk.models import Bookmark
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add various bookmarks
            b1 = db.add(url="https://example.com", title="Example Site",
                       description="A test site", tags=["test", "web"], stars=True)
            b2 = db.add(url="https://youtube.com/watch?v=abc123", title="Video",
                       tags=["media"])
            b3 = db.add(url="https://arxiv.org/abs/1234.5678", title="Paper",
                       tags=["research", "ml"])

            # Set media attributes on video bookmark
            with db.session() as session:
                bm2 = session.get(Bookmark, b2.id)
                bm2.media_type = 'video'
                bm2.media_source = 'youtube'
                bm2.author_name = 'Test Channel'
                bm2.thumbnail_url = 'https://img.youtube.com/vi/abc123/0.jpg'

            yield db.all()

    def test_export_html_app_basic(self, sample_bookmarks):
        """Test basic HTML app export creates valid file."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)

            assert output_path.exists()
            content = output_path.read_text()

            # Should be valid HTML5
            assert '<!DOCTYPE html>' in content
            assert '<html lang="en"' in content
            assert '</html>' in content

            # Should have embedded CSS and JS
            assert '<style>' in content
            assert '</style>' in content
            assert '<script>' in content
            assert '</script>' in content

            # Should have embedded JSON data
            assert 'id="bookmark-data"' in content
            assert 'type="application/json"' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_contains_all_bookmarks(self, sample_bookmarks):
        """Test that all bookmarks are in embedded JSON."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # All bookmark URLs should be present
            assert 'example.com' in content
            assert 'youtube.com' in content
            assert 'arxiv.org' in content

            # Titles should be present
            assert 'Example Site' in content
            assert 'Video' in content
            assert 'Paper' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_tag_stats(self, sample_bookmarks):
        """Test that tag statistics are computed correctly."""
        tag_stats = _get_tag_stats(sample_bookmarks)

        # Should have unique tags
        tag_names = [t['name'] for t in tag_stats]
        assert 'test' in tag_names
        assert 'media' in tag_names
        assert 'research' in tag_names

        # Should have counts
        for stat in tag_stats:
            assert 'count' in stat
            assert stat['count'] >= 1

    def test_export_html_app_media_fields(self, sample_bookmarks):
        """Test that media metadata is included."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Media fields should be present
            assert 'media_type' in content
            assert 'youtube' in content
            assert 'Test Channel' in content
            assert 'thumbnail_url' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_no_external_resources(self, sample_bookmarks):
        """Test that no external CSS/JS resources are referenced."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Should NOT have external stylesheet links
            assert 'rel="stylesheet"' not in content
            # Should NOT have external script sources (except data:)
            # The only src attributes should be for favicons/images
            lines = content.split('\n')
            for line in lines:
                if '<script' in line and 'src=' in line:
                    # No external JS files
                    assert False, f"Found external script: {line}"
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_empty_list(self):
        """Test exporting empty bookmark list."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app([], output_path)

            assert output_path.exists()
            content = output_path.read_text()

            # Should still be valid HTML
            assert '<!DOCTYPE html>' in content
            assert '"bookmarks": []' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_special_characters(self):
        """Test handling of special characters in titles/descriptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add bookmark with special characters
            db.add(url="https://example.com",
                   title='Test with "quotes" & ampersand',
                   description='Line 1\nLine 2\tTabbed')

            bookmarks = db.all()

            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
                output_path = Path(f.name)

            try:
                export_html_app(bookmarks, output_path)

                # File should be created without error
                assert output_path.exists()

                content = output_path.read_text()
                # Title should be in the JSON data
                assert 'Test with' in content
                # JSON should be parseable (quotes escaped)
                assert '"quotes"' not in content or '\\"quotes\\"' in content or "quotes" in content
            finally:
                if output_path.exists():
                    os.unlink(output_path)

    def test_serialize_bookmark_for_app(self, sample_bookmarks):
        """Test bookmark serialization helper."""
        bookmark = sample_bookmarks[0]
        data = _serialize_bookmark_for_app(bookmark)

        # Should have all required fields
        assert 'id' in data
        assert 'url' in data
        assert 'title' in data
        assert 'tags' in data
        assert 'stars' in data
        assert 'media_type' in data

        # Tags should be list of strings
        assert isinstance(data['tags'], list)

    def test_export_html_app_large_dataset(self):
        """Test with larger number of bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add 500 bookmarks
            for i in range(500):
                db.add(url=f"https://example{i}.com", title=f"Example {i}",
                      tags=[f"tag{i % 10}"])

            bookmarks = db.all()

            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
                output_path = Path(f.name)

            try:
                export_html_app(bookmarks, output_path)

                assert output_path.exists()
                # File should be reasonable size (< 5MB for 500 bookmarks)
                size_mb = output_path.stat().st_size / (1024 * 1024)
                assert size_mb < 5, f"File too large: {size_mb:.2f}MB"

                content = output_path.read_text()
                # Spot check some bookmarks are present
                assert 'example0.com' in content
                assert 'example499.com' in content
            finally:
                if output_path.exists():
                    os.unlink(output_path)

    def test_export_html_app_view_modes(self, sample_bookmarks):
        """Test that view mode UI elements are present."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Should have view switcher buttons
            assert 'view-switcher' in content
            assert 'data-view="grid"' in content
            assert 'data-view="list"' in content
            assert 'data-view="table"' in content
            assert 'data-view="gallery"' in content

            # Should have view mode CSS classes defined
            assert '.view-grid' in content
            assert '.view-list' in content
            assert '.view-table' in content
            assert '.view-gallery' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_smart_collections(self, sample_bookmarks):
        """Test that smart collections are present."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Should have collections list container
            assert 'collections-list' in content

            # Should have smart collections defined in JS
            assert 'SMART_COLLECTIONS' in content
            assert "'all'" in content or '"all"' in content
            assert "'unread'" in content or '"unread"' in content
            assert "'starred'" in content or '"starred"' in content
            assert "'queue'" in content or '"queue"' in content
            assert "'broken'" in content or '"broken"' in content
            assert "'untagged'" in content or '"untagged"' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_keyboard_shortcuts(self, sample_bookmarks):
        """Test that keyboard shortcuts are defined."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Should have shortcuts button and modal
            assert 'shortcuts-toggle' in content
            assert 'shortcuts-modal' in content

            # Should have keyboard shortcuts object
            assert 'KEYBOARD_SHORTCUTS' in content
            # Should have common shortcuts defined
            assert "'j'" in content or '"j"' in content  # Navigation
            assert "'k'" in content or '"k"' in content  # Navigation
            assert "'/'" in content or '"\/"' in content or "'/" in content  # Search
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_stats_dashboard(self, sample_bookmarks):
        """Test that statistics dashboard is present."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Should have stats button and modal
            assert 'stats-toggle' in content
            assert 'stats-modal' in content
            assert 'stats-dashboard' in content

            # Should have stats in the JSON data
            assert '"stats"' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_stats_computation(self, sample_bookmarks):
        """Test that statistics are computed correctly."""
        stats = _get_export_stats(sample_bookmarks)

        # Should have basic counts
        assert 'total' in stats
        assert stats['total'] == len(sample_bookmarks)
        assert 'starred' in stats
        assert 'unread' in stats
        assert 'tag_count' in stats

        # Should have health stats
        assert 'reachable' in stats
        assert 'broken' in stats
        assert 'unchecked' in stats

        # Should have media breakdown
        assert 'media_breakdown' in stats
        assert isinstance(stats['media_breakdown'], dict)

        # Should have top domains
        assert 'top_domains' in stats
        assert isinstance(stats['top_domains'], dict)

        # Should have timeline (dict with month keys)
        assert 'timeline' in stats
        assert isinstance(stats['timeline'], dict)

    def test_serialize_bookmark_reading_queue_fields(self):
        """Test that reading queue fields are serialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add bookmark with reading queue fields in extra_data
            b = db.add(url="https://example.com", title="Test")
            from btk.models import Bookmark
            with db.session() as session:
                bm = session.get(Bookmark, b.id)
                bm.extra_data = {
                    "reading_queue": True,
                    "reading_progress": 50,
                    "reading_priority": 2,
                    "queued_at": "2024-01-15T10:30:00",
                    "estimated_read_time": 15
                }

            bookmarks = db.all()
            data = _serialize_bookmark_for_app(bookmarks[0])

            # Should have reading queue fields
            assert 'reading_queue' in data
            assert data['reading_queue'] == True
            assert 'reading_progress' in data
            assert data['reading_progress'] == 50
            assert 'reading_priority' in data
            assert data['reading_priority'] == 2
            assert 'queued_at' in data
            assert 'estimated_read_time' in data
            assert data['estimated_read_time'] == 15

    def test_export_html_app_localstorage_state(self, sample_bookmarks):
        """Test that localStorage state management code is present."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Should have localStorage functions
            assert 'loadState' in content
            assert 'saveState' in content
            assert 'localStorage' in content

            # Should save view mode state
            assert 'viewMode' in content
            assert 'activeCollection' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_with_views(self, sample_bookmarks):
        """Test that views are included in HTML-app export."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            # Create views data
            views = {
                'starred': {
                    'description': 'Starred bookmarks',
                    'bookmark_ids': [sample_bookmarks[0].id],
                    'builtin': True
                },
                'python_posts': {
                    'description': 'Python-related bookmarks',
                    'bookmark_ids': [b.id for b in sample_bookmarks],
                    'builtin': False
                }
            }

            export_html_app(sample_bookmarks, output_path, views=views)
            content = output_path.read_text()

            # Should have views section in HTML
            assert 'views-section' in content
            assert 'Curated Views' in content

            # Should have views in JSON data
            assert '"views"' in content
            assert 'starred' in content
            assert 'python_posts' in content
            assert 'Starred bookmarks' in content
            assert 'Python-related bookmarks' in content

            # Should have JavaScript for views
            assert 'setActiveView' in content
            assert 'renderViewsSidebar' in content
            assert 'activeView' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_html_app_without_views(self, sample_bookmarks):
        """Test that export works without views (backwards compatibility)."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            # Export without views parameter
            export_html_app(sample_bookmarks, output_path)
            content = output_path.read_text()

            # Should still have views infrastructure (but empty)
            assert 'views-section' in content
            assert '"views": {}' in content or '"views":{}' in content.replace(' ', '')
        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_export_file_with_views(self, sample_bookmarks):
        """Test that export_file passes views to html-app exporter."""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            views = {
                'test_view': {
                    'description': 'Test view',
                    'bookmark_ids': [sample_bookmarks[0].id],
                    'builtin': False
                }
            }

            export_file(sample_bookmarks, output_path, 'html-app', views=views)
            content = output_path.read_text()

            # Should have the view data
            assert 'test_view' in content
            assert 'Test view' in content
        finally:
            if output_path.exists():
                os.unlink(output_path)
