"""
Simplified importers for BTK.

Provides clean, composable import functions for various bookmark formats.
"""
import json
import csv
from pathlib import Path
from datetime import datetime
import re

from bs4 import BeautifulSoup
from btk.db import Database
from typing import Optional


def import_file(db: Database, path: Path, format: Optional[str] = None) -> int:
    """
    Import bookmarks from a file.

    Args:
        db: Database instance
        path: File path to import
        format: Format override (auto-detected if not specified)

    Returns:
        Number of bookmarks imported
    """
    if format is None:
        # Auto-detect format from extension
        ext = path.suffix.lower()
        format_map = {
            ".html": "html",
            ".htm": "html",
            ".json": "json",
            ".csv": "csv",
            ".md": "markdown",
            ".txt": "text",
        }
        format = format_map.get(ext, "html")

    # Choose appropriate importer
    importers = {
        "html": import_html,
        "json": import_json,
        "csv": import_csv,
        "markdown": import_markdown,
        "text": import_text,
    }

    importer = importers.get(format)
    if not importer:
        raise ValueError(f"Unknown format: {format}")

    return importer(db, path)


def import_html(db: Database, path: Path) -> int:
    """Import bookmarks from HTML (Netscape format or generic)."""
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    source_name = path.name
    count = 0
    skipped = 0

    # Try Netscape bookmark format first
    for dt in soup.find_all("dt"):
        link = dt.find("a", recursive=False)
        if link and link.get("href"):
            url = link.get("href")
            title = link.text.strip() or url
            tags = []

            # Build folder path from parent DL/DT structure
            folders = []
            parent = dt.parent
            while parent:
                if parent.name == "dl":
                    prev = parent.find_previous_sibling("dt")
                    if prev and prev.find("h3"):
                        folder_name = prev.find("h3").text.strip()
                        if folder_name:
                            folders.append(folder_name)
                            tags.append(folder_name.lower().replace(" ", "-"))
                parent = parent.parent
            folders.reverse()
            folder_path = "/".join(folders) if folders else None

            # Get add date
            added = None
            add_date = link.get("add_date")
            if add_date:
                try:
                    added = datetime.fromtimestamp(int(add_date))
                except Exception:
                    pass

            # Preserve all Netscape attributes in raw_data for lossless round-trip
            raw_data = {}
            for attr in link.attrs:
                if attr != "href":
                    raw_data[attr] = link[attr]

            result = db.add(
                url=url, title=title, tags=tags, added=added,
                source_type="html_file", source_name=source_name,
                folder_path=folder_path,
                raw_data=raw_data if raw_data else None,
            )
            if result:
                count += 1
            else:
                skipped += 1

    # If no Netscape format bookmarks found, extract all links
    if count == 0 and skipped == 0:
        for link in soup.find_all("a", href=True):
            url = link.get("href")
            if url and url.startswith(("http://", "https://")):
                title = link.text.strip() or url
                result = db.add(
                    url=url, title=title,
                    source_type="html_file", source_name=source_name,
                )
                if result:
                    count += 1
                else:
                    skipped += 1

    if skipped > 0:
        print(f"Imported {count} bookmarks, skipped {skipped} duplicates")

    return count


def import_json(db: Database, path: Path) -> int:
    """Import bookmarks from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both list and dict formats
    if isinstance(data, dict):
        bookmarks = data.get("bookmarks", [])
    else:
        bookmarks = data

    source_name = path.name
    count = 0
    for item in bookmarks:
        if isinstance(item, dict) and "url" in item:
            # Preserve any extra fields not mapped to standard columns
            known_keys = {"url", "title", "description", "tags", "stars"}
            extra = {k: v for k, v in item.items() if k not in known_keys}
            db.add(
                url=item["url"],
                title=item.get("title", item["url"]),
                description=item.get("description", ""),
                tags=item.get("tags", []),
                stars=item.get("stars", False),
                source_type="json_file", source_name=source_name,
                raw_data=extra if extra else None,
            )
            count += 1
        elif isinstance(item, str):
            # Plain URL string
            db.add(
                url=item, title=item,
                source_type="json_file", source_name=source_name,
            )
            count += 1

    return count


def import_csv(db: Database, path: Path) -> int:
    """Import bookmarks from CSV."""
    source_name = path.name
    count = 0

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # If no header, assume url,title,tags,description format
        if reader.fieldnames is None:
            f.seek(0)
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 1:
                    url = row[0]
                    title = row[1] if len(row) > 1 else url
                    tags = row[2].split(",") if len(row) > 2 and row[2] else []
                    description = row[3] if len(row) > 3 else ""

                    db.add(
                        url=url, title=title, tags=tags, description=description,
                        source_type="csv_file", source_name=source_name,
                    )
                    count += 1
        else:
            for row in reader:
                # Try common field names
                url = row.get("url") or row.get("URL") or row.get("link")
                if url:
                    title = row.get("title") or row.get("Title") or row.get("name") or url
                    tags_str = row.get("tags") or row.get("Tags") or ""
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                    description = row.get("description") or row.get("Description") or ""

                    db.add(
                        url=url, title=title, tags=tags, description=description,
                        source_type="csv_file", source_name=source_name,
                    )
                    count += 1

    return count


def import_markdown(db: Database, path: Path) -> int:
    """Import bookmarks from Markdown."""
    source_name = path.name
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract markdown links: [title](url)
    pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    matches = re.findall(pattern, content)

    count = 0
    for title, url in matches:
        if url.startswith(("http://", "https://")):
            db.add(
                url=url, title=title,
                source_type="markdown_file", source_name=source_name,
            )
            count += 1

    # Also extract plain URLs
    url_pattern = r"https?://[^\s<>\"{}|\\^`\[\]]+"
    plain_urls = re.findall(url_pattern, content)

    for url in plain_urls:
        # Skip if already added as markdown link
        if not any(url == match[1] for match in matches):
            db.add(
                url=url, title=url,
                source_type="markdown_file", source_name=source_name,
            )
            count += 1

    return count


def import_text(db: Database, path: Path) -> int:
    """Import URLs from plain text file (one URL per line)."""
    source_name = path.name
    count = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and line.startswith(("http://", "https://")):
                db.add(
                    url=line, title=line,
                    source_type="text_file", source_name=source_name,
                )
                count += 1

    return count