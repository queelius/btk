"""Tests for bookmark_memex.importers file importers."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from bookmark_memex.db import Database


@pytest.fixture
def db(tmp_db_path):
    return Database(tmp_db_path)


# ---------------------------------------------------------------------------
# HTML import
# ---------------------------------------------------------------------------


def test_import_html_count(db, tmp_path):
    """Netscape HTML with 2 links returns count=2."""
    html = """\
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><A HREF="https://example.com/" ADD_DATE="1677247196">Example</A>
    <DT><A HREF="https://python.org/" ADD_DATE="1677247196" TAGS="python,dev">Python</A>
</DL><p>
"""
    f = tmp_path / "bookmarks.html"
    f.write_text(html)

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 2


def test_import_html_urls_in_db(db, tmp_path):
    """Both URLs appear in the database after HTML import."""
    html = """\
<DL><p>
    <DT><A HREF="https://example.com/">Example</A>
    <DT><A HREF="https://python.org/">Python</A>
</DL><p>
"""
    f = tmp_path / "bookmarks.html"
    f.write_text(html)

    from bookmark_memex.importers import import_file
    import_file(db, f)

    urls = {bm.url for bm in db.list()}
    assert "https://example.com/" in urls
    assert "https://python.org/" in urls


def test_import_html_tags_attribute(db, tmp_path):
    """TAGS attribute is parsed as comma-separated tags."""
    html = '<DL><p><DT><A HREF="https://example.com/" TAGS="foo,bar">X</A></DL>'
    f = tmp_path / "bookmarks.html"
    f.write_text(html)

    from bookmark_memex.importers.file_importers import import_html
    import_html(db, f)

    bm = db.list()[0]
    tag_names = {t.name for t in bm.tags}
    assert "foo" in tag_names
    assert "bar" in tag_names


def test_import_html_folder_as_tag(db, tmp_path):
    """Folder path from H3 hierarchy is added as a tag."""
    html = """\
<DL><p>
    <DT><H3>Programming</H3>
    <DL><p>
        <DT><A HREF="https://rust-lang.org/">Rust</A>
    </DL><p>
</DL><p>
"""
    f = tmp_path / "bookmarks.html"
    f.write_text(html)

    from bookmark_memex.importers.file_importers import import_html
    import_html(db, f)

    bm = db.list()[0]
    tag_names = {t.name for t in bm.tags}
    # Folder name should appear somewhere in tags
    assert any("Programming" in t or "programming" in t for t in tag_names)


def test_import_html_skips_non_http(db, tmp_path):
    """Non-HTTP(S) hrefs are silently skipped."""
    html = """\
<DL><p>
    <DT><A HREF="ftp://files.example.com/">FTP</A>
    <DT><A HREF="https://valid.example.com/">Valid</A>
</DL><p>
"""
    f = tmp_path / "bookmarks.html"
    f.write_text(html)

    from bookmark_memex.importers.file_importers import import_html
    count = import_html(db, f)

    assert count == 1
    assert db.list()[0].url == "https://valid.example.com/"


def test_import_html_source_type(db, tmp_path):
    """Imported bookmarks carry source_type=html_file."""
    html = '<DL><p><DT><A HREF="https://example.com/">X</A></DL>'
    f = tmp_path / "bookmarks.html"
    f.write_text(html)

    from bookmark_memex.importers.file_importers import import_html
    import_html(db, f)

    bm = db.list()[0]
    assert any(s.source_type == "html_file" for s in bm.sources)


# ---------------------------------------------------------------------------
# JSON import
# ---------------------------------------------------------------------------


def test_import_json_count(db, tmp_path):
    """JSON list with 2 objects returns count=2."""
    data = [
        {"url": "https://example.com/", "title": "Example"},
        {"url": "https://python.org/", "title": "Python"},
    ]
    f = tmp_path / "bookmarks.json"
    f.write_text(json.dumps(data))

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 2


def test_import_json_urls_in_db(db, tmp_path):
    """Both URLs appear in the database after JSON import."""
    data = [
        {"url": "https://example.com/", "title": "Example"},
        {"url": "https://python.org/", "title": "Python"},
    ]
    f = tmp_path / "bookmarks.json"
    f.write_text(json.dumps(data))

    from bookmark_memex.importers import import_file
    import_file(db, f)

    urls = {bm.url for bm in db.list()}
    assert "https://example.com/" in urls
    assert "https://python.org/" in urls


def test_import_json_tags_as_list(db, tmp_path):
    """JSON tags given as a list are stored correctly."""
    data = [{"url": "https://example.com/", "tags": ["foo", "bar"]}]
    f = tmp_path / "bookmarks.json"
    f.write_text(json.dumps(data))

    from bookmark_memex.importers.file_importers import import_json
    import_json(db, f)

    bm = db.list()[0]
    tag_names = {t.name for t in bm.tags}
    assert {"foo", "bar"} <= tag_names


def test_import_json_tags_as_comma_string(db, tmp_path):
    """JSON tags given as a comma-separated string are split."""
    data = [{"url": "https://example.com/", "tags": "foo,bar"}]
    f = tmp_path / "bookmarks.json"
    f.write_text(json.dumps(data))

    from bookmark_memex.importers.file_importers import import_json
    import_json(db, f)

    bm = db.list()[0]
    tag_names = {t.name for t in bm.tags}
    assert {"foo", "bar"} <= tag_names


def test_import_json_starred_flag(db, tmp_path):
    """starred field is honoured."""
    data = [{"url": "https://example.com/", "starred": True}]
    f = tmp_path / "bookmarks.json"
    f.write_text(json.dumps(data))

    from bookmark_memex.importers.file_importers import import_json
    import_json(db, f)

    assert db.list()[0].starred is True


def test_import_json_description(db, tmp_path):
    """description field is stored."""
    data = [{"url": "https://example.com/", "description": "hello"}]
    f = tmp_path / "bookmarks.json"
    f.write_text(json.dumps(data))

    from bookmark_memex.importers.file_importers import import_json
    import_json(db, f)

    assert db.list()[0].description == "hello"


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------


def test_import_csv_count(db, tmp_path):
    """CSV with header + 1 row returns count=1."""
    csv_content = "url,title,tags,description\nhttps://example.com/,Example,foo,desc\n"
    f = tmp_path / "bookmarks.csv"
    f.write_text(csv_content)

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 1


def test_import_csv_url_in_db(db, tmp_path):
    """URL from CSV row appears in the database."""
    csv_content = "url,title\nhttps://example.com/,Example\n"
    f = tmp_path / "bookmarks.csv"
    f.write_text(csv_content)

    from bookmark_memex.importers import import_file
    import_file(db, f)

    urls = {bm.url for bm in db.list()}
    assert "https://example.com/" in urls


def test_import_csv_tags_parsed(db, tmp_path):
    """Comma-separated tags in CSV are split correctly."""
    csv_content = "url,tags\nhttps://example.com/,\"foo,bar\"\n"
    f = tmp_path / "bookmarks.csv"
    f.write_text(csv_content)

    from bookmark_memex.importers.file_importers import import_csv
    import_csv(db, f)

    bm = db.list()[0]
    tag_names = {t.name for t in bm.tags}
    assert {"foo", "bar"} <= tag_names


def test_import_csv_description(db, tmp_path):
    """description column is stored."""
    csv_content = "url,description\nhttps://example.com/,my desc\n"
    f = tmp_path / "bookmarks.csv"
    f.write_text(csv_content)

    from bookmark_memex.importers.file_importers import import_csv
    import_csv(db, f)

    assert db.list()[0].description == "my desc"


# ---------------------------------------------------------------------------
# Text import
# ---------------------------------------------------------------------------


def test_import_text_count(db, tmp_path):
    """Text file with 2 URLs + comment + blank returns count=2."""
    text = "https://example.com/\n# comment\n\nhttps://python.org/\n"
    f = tmp_path / "urls.txt"
    f.write_text(text)

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 2


def test_import_text_urls_in_db(db, tmp_path):
    """Both HTTP URLs are stored; non-http lines are skipped."""
    text = "https://example.com/\nhttps://python.org/\nftp://files.example.com/\n"
    f = tmp_path / "urls.txt"
    f.write_text(text)

    from bookmark_memex.importers.file_importers import import_text
    count = import_text(db, f)

    assert count == 2
    urls = {bm.url for bm in db.list()}
    assert "https://example.com/" in urls
    assert "https://python.org/" in urls


def test_import_text_skips_blank_and_comments(db, tmp_path):
    """Blank lines and # comments are not counted."""
    text = "# My URLs\n\nhttps://example.com/\n\n# done\n"
    f = tmp_path / "urls.txt"
    f.write_text(text)

    from bookmark_memex.importers.file_importers import import_text
    count = import_text(db, f)
    assert count == 1


# ---------------------------------------------------------------------------
# Markdown import
# ---------------------------------------------------------------------------


def test_import_markdown_links(db, tmp_path):
    """Markdown [text](url) links are extracted."""
    md = "See [Example](https://example.com/) and [Python](https://python.org/).\n"
    f = tmp_path / "notes.md"
    f.write_text(md)

    from bookmark_memex.importers.file_importers import import_markdown
    count = import_markdown(db, f)
    assert count == 2

    urls = {bm.url for bm in db.list()}
    assert "https://example.com/" in urls
    assert "https://python.org/" in urls


def test_import_markdown_link_title(db, tmp_path):
    """The text part of a markdown link is used as the bookmark title."""
    md = "[My Site](https://example.com/)\n"
    f = tmp_path / "notes.md"
    f.write_text(md)

    from bookmark_memex.importers.file_importers import import_markdown
    import_markdown(db, f)

    bm = db.list()[0]
    assert bm.title == "My Site"


def test_import_markdown_skips_non_http(db, tmp_path):
    """Non-HTTP(S) markdown links are skipped."""
    md = "[FTP](ftp://files.example.com/) [Valid](https://example.com/)\n"
    f = tmp_path / "notes.md"
    f.write_text(md)

    from bookmark_memex.importers.file_importers import import_markdown
    count = import_markdown(db, f)
    assert count == 1


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def test_autodetect_html_extension(db, tmp_path):
    """import_file detects .html extension -> html importer."""
    f = tmp_path / "export.html"
    f.write_text('<DL><p><DT><A HREF="https://example.com/">X</A></DL>')

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 1


def test_autodetect_htm_extension(db, tmp_path):
    """import_file detects .htm extension -> html importer."""
    f = tmp_path / "export.htm"
    f.write_text('<DL><p><DT><A HREF="https://example.com/">X</A></DL>')

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 1


def test_autodetect_json_extension(db, tmp_path):
    """import_file detects .json extension -> json importer."""
    f = tmp_path / "export.json"
    f.write_text('[{"url": "https://example.com/"}]')

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 1


def test_autodetect_csv_extension(db, tmp_path):
    """import_file detects .csv extension -> csv importer."""
    f = tmp_path / "export.csv"
    f.write_text("url\nhttps://example.com/\n")

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 1


def test_autodetect_md_extension(db, tmp_path):
    """import_file detects .md extension -> markdown importer."""
    f = tmp_path / "notes.md"
    f.write_text("[Example](https://example.com/)\n")

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 1


def test_autodetect_txt_extension(db, tmp_path):
    """import_file detects .txt extension -> text importer."""
    f = tmp_path / "urls.txt"
    f.write_text("https://example.com/\nhttps://python.org/\n")

    from bookmark_memex.importers import import_file
    count = import_file(db, f)
    assert count == 2


def test_explicit_format_overrides_extension(db, tmp_path):
    """Explicit format parameter overrides extension-based detection."""
    f = tmp_path / "urls.data"
    f.write_text("https://example.com/\n")

    from bookmark_memex.importers import import_file
    count = import_file(db, f, format="text")
    assert count == 1


def test_unknown_format_raises(db, tmp_path):
    """import_file raises ValueError for unknown format strings."""
    f = tmp_path / "data.xyz"
    f.write_text("")

    from bookmark_memex.importers import import_file
    with pytest.raises(ValueError, match="Unknown format"):
        import_file(db, f, format="xyz")
