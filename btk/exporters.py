"""
Simplified exporters for BTK.

Provides clean, composable export functions for various bookmark formats.
"""
import json
import csv
import base64
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone
from collections import Counter

from btk.models import Bookmark


def export_file(bookmarks: List[Bookmark], path: Path, format: str, views: Optional[dict] = None, db=None) -> None:
    """
    Export bookmarks to a file.

    Args:
        bookmarks: List of bookmarks to export
        path: Output file path
        format: Export format (json, csv, html, markdown, long-echo)
        views: Optional dict of view definitions for html-app format
        db: Optional database instance for long-echo format
    """
    exporters = {
        "json": export_json,
        "json-full": export_json_full,
        "csv": export_csv,
        "html": export_html,
        "html-app": export_html_app,
        "markdown": export_markdown,
        "text": export_text,
        "m3u": export_m3u,
        "m3u8": export_m3u,  # Alias - m3u8 is UTF-8 m3u
        "preservation-html": export_preservation_html,
        "echo": export_echo,
    }

    exporter = exporters.get(format)
    if not exporter:
        raise ValueError(f"Unknown format: {format}")

    # Ensure parent directory exists
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # html-app supports views parameter
    if format == "html-app" and views:
        exporter(bookmarks, path, views=views)
    elif format in ("preservation-html", "json-full"):
        exporter(bookmarks, path, db=db)
    elif format == "echo":
        # ECHO export needs db for database copy
        exporter(bookmarks, path, db=db)
    else:
        exporter(bookmarks, path)


def export_json(bookmarks: List[Bookmark], path: Path) -> None:
    """Export bookmarks to JSON (lightweight format)."""
    data = []
    for b in bookmarks:
        data.append({
            "id": b.id,
            "url": b.url,
            "title": b.title,
            "description": b.description or "",
            "tags": [t.name for t in b.tags],
            "stars": b.stars,
            "visit_count": b.visit_count,
            "added": b.added.isoformat() if b.added else None,
            "last_visited": b.last_visited.isoformat() if b.last_visited else None,
        })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def export_json_full(bookmarks: List[Bookmark], path: Path, db=None) -> None:
    """
    Export bookmarks to comprehensive JSON format.

    Includes all bookmark fields, media metadata, preservation data,
    and cached content. Suitable for import into longecho or other tools.

    Args:
        bookmarks: List of bookmarks to export
        path: Output file path
        db: Database instance (optional, for accessing cached content)
    """
    data = {
        "version": "1.0",
        "format": "btk-full",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "bookmark_count": len(bookmarks),
        "bookmarks": []
    }

    # Build cache lookup if db available
    cache_lookup = {}
    if db:
        try:
            from .models import ContentCache
            with db.session() as session:
                for b in bookmarks:
                    cache = session.query(ContentCache).filter_by(bookmark_id=b.id).first()
                    if cache:
                        cache_data = {
                            "markdown_content": cache.markdown_content,
                            # html_content is zlib-compressed bytes - include as base64 if present
                            "html_content_compressed": base64.b64encode(cache.html_content).decode('ascii') if cache.html_content else None,
                            "content_hash": cache.content_hash,
                            "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
                        }
                        # Preservation fields
                        if cache.preservation_type:
                            cache_data["preservation"] = {
                                "type": cache.preservation_type,
                                "preserved_at": cache.preserved_at.isoformat() if cache.preserved_at else None,
                                "transcript_text": cache.transcript_text,
                                "extracted_text": cache.extracted_text,
                                # Thumbnail as base64 if present
                                "thumbnail": {
                                    "data": base64.b64encode(cache.thumbnail_data).decode('ascii') if cache.thumbnail_data else None,
                                    "mime": cache.thumbnail_mime,
                                    "width": cache.thumbnail_width,
                                    "height": cache.thumbnail_height,
                                } if cache.thumbnail_data else None
                            }
                        cache_lookup[b.id] = cache_data
        except Exception:
            pass  # Continue without cache data

    for b in bookmarks:
        bookmark_data = {
            # Core fields
            "id": b.id,
            "unique_id": b.unique_id,
            "url": b.url,
            "title": b.title,
            "description": b.description or "",

            # Status flags
            "stars": b.stars,
            "archived": b.archived,
            "pinned": b.pinned,
            "reachable": b.reachable,

            # Timestamps
            "added": b.added.isoformat() if b.added else None,
            "last_visited": b.last_visited.isoformat() if b.last_visited else None,
            "visit_count": b.visit_count,

            # Media fields
            "media": {
                "type": b.media_type,
                "source": b.media_source,
                "id": b.media_id,
                "author_name": b.author_name,
                "author_url": b.author_url,
                "thumbnail_url": b.thumbnail_url,
                "published_at": b.published_at.isoformat() if b.published_at else None,
            } if b.media_type else None,

            # Tags with full info
            "tags": [
                {
                    "name": t.name,
                    "description": t.description,
                    "color": t.color,
                } for t in b.tags
            ],

            # Favicon (base64 if present)
            "favicon": {
                "data": base64.b64encode(b.favicon_data).decode('ascii') if b.favicon_data else None,
                "mime": b.favicon_mime_type,
                "path": b.favicon_path,
            } if b.favicon_data or b.favicon_path else None,

            # Extra metadata
            "extra_data": b.extra_data,
        }

        # Add cached content if available
        if b.id in cache_lookup:
            bookmark_data["content_cache"] = cache_lookup[b.id]

        data["bookmarks"].append(bookmark_data)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def export_csv(bookmarks: List[Bookmark], path: Path) -> None:
    """Export bookmarks to CSV."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "url", "title", "description", "tags", "stars", "visits", "added"])

        for b in bookmarks:
            tags = ",".join(t.name for t in b.tags)
            writer.writerow([
                b.id,
                b.url,
                b.title,
                b.description or "",
                tags,
                b.stars,
                b.visit_count,
                b.added.isoformat() if b.added else ""
            ])


def export_html(bookmarks: List[Bookmark], path: Path, hierarchical: bool = True) -> None:
    """Export bookmarks to Netscape HTML format (browser-compatible)."""
    lines = [
        '<!DOCTYPE NETSCAPE-Bookmark-file-1>',
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        '<TITLE>Bookmarks</TITLE>',
        '<H1>Bookmarks</H1>',
        '<DL><p>'
    ]

    if hierarchical:
        # Build hierarchical folder structure from tags
        folder_tree = {}
        untagged = []

        for b in bookmarks:
            if b.tags:
                for tag in b.tags:
                    # Skip parent tags, only use leaf tags
                    if not any(t.name.startswith(tag.name + '/') for t in b.tags):
                        parts = tag.name.split('/')
                        current = folder_tree

                        # Build nested structure
                        for i, part in enumerate(parts):
                            if part not in current:
                                current[part] = {'__bookmarks__': [], '__children__': {}}

                            # Add bookmark to leaf folder
                            if i == len(parts) - 1:
                                current[part]['__bookmarks__'].append(b)

                            current = current[part]['__children__']
            else:
                untagged.append(b)

        # Recursive function to write folders
        def write_folder(folder_dict, indent=1):
            indent_str = '    ' * indent

            for folder_name in sorted(folder_dict.keys()):
                folder_data = folder_dict[folder_name]

                # Write folder header
                lines.append(f'{indent_str}<DT><H3>{folder_name}</H3>')
                lines.append(f'{indent_str}<DL><p>')

                # Write bookmarks in this folder
                for b in folder_data['__bookmarks__']:
                    add_date = int(b.added.timestamp()) if b.added else ""
                    lines.append(f'{indent_str}    <DT><A HREF="{b.url}" ADD_DATE="{add_date}">{b.title}</A>')
                    if b.description:
                        lines.append(f'{indent_str}    <DD>{b.description}')

                # Write subfolders recursively
                if folder_data['__children__']:
                    write_folder(folder_data['__children__'], indent + 1)

                lines.append(f'{indent_str}</DL><p>')

        write_folder(folder_tree)

        # Export untagged bookmarks
        if untagged:
            lines.append('    <DT><H3>Untagged</H3>')
            lines.append('    <DL><p>')

            for b in untagged:
                add_date = int(b.added.timestamp()) if b.added else ""
                lines.append(f'        <DT><A HREF="{b.url}" ADD_DATE="{add_date}">{b.title}</A>')
                if b.description:
                    lines.append(f'        <DD>{b.description}')

            lines.append('    </DL><p>')

    else:
        # Flat structure (original behavior)
        tag_bookmarks = {}
        untagged = []

        for b in bookmarks:
            if b.tags:
                for tag in b.tags:
                    if tag.name not in tag_bookmarks:
                        tag_bookmarks[tag.name] = []
                    tag_bookmarks[tag.name].append(b)
            else:
                untagged.append(b)

        # Export tagged bookmarks in folders
        for tag_name, tag_items in sorted(tag_bookmarks.items()):
            lines.append(f'    <DT><H3>{tag_name}</H3>')
            lines.append('    <DL><p>')

            for b in tag_items:
                add_date = int(b.added.timestamp()) if b.added else ""
                lines.append(f'        <DT><A HREF="{b.url}" ADD_DATE="{add_date}">{b.title}</A>')
                if b.description:
                    lines.append(f'        <DD>{b.description}')

            lines.append('    </DL><p>')

        # Export untagged bookmarks
        if untagged:
            lines.append('    <DT><H3>Untagged</H3>')
            lines.append('    <DL><p>')

            for b in untagged:
                add_date = int(b.added.timestamp()) if b.added else ""
                lines.append(f'        <DT><A HREF="{b.url}" ADD_DATE="{add_date}">{b.title}</A>')
                if b.description:
                    lines.append(f'        <DD>{b.description}')

            lines.append('    </DL><p>')

    lines.append('</DL><p>')

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def export_markdown(bookmarks: List[Bookmark], path: Path) -> None:
    """Export bookmarks to Markdown format."""
    lines = ["# Bookmarks", ""]

    # Group by tag
    tag_bookmarks = {}
    untagged = []

    for b in bookmarks:
        if b.tags:
            for tag in b.tags:
                if tag.name not in tag_bookmarks:
                    tag_bookmarks[tag.name] = []
                tag_bookmarks[tag.name].append(b)
        else:
            untagged.append(b)

    # Export by tag
    for tag_name, tag_items in sorted(tag_bookmarks.items()):
        lines.append(f"## {tag_name}")
        lines.append("")

        for b in tag_items:
            star = " ⭐" if b.stars else ""
            lines.append(f"- [{b.title}]({b.url}){star}")
            if b.description:
                lines.append(f"  - {b.description}")
        lines.append("")

    # Export untagged
    if untagged:
        lines.append("## Untagged")
        lines.append("")

        for b in untagged:
            star = " ⭐" if b.stars else ""
            lines.append(f"- [{b.title}]({b.url}){star}")
            if b.description:
                lines.append(f"  - {b.description}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def export_text(bookmarks: List[Bookmark], path: Path) -> None:
    """Export bookmarks as plain text URLs (one per line)."""
    with open(path, "w", encoding="utf-8") as f:
        for b in bookmarks:
            f.write(f"{b.url}\n")


def export_m3u(bookmarks: List[Bookmark], path: Path, extended: bool = True) -> None:
    """
    Export media bookmarks as M3U/M3U8 playlist.

    Only exports bookmarks with media_type in ('video', 'audio').
    Uses extended M3U format by default with title info.

    Args:
        bookmarks: List of bookmarks to export
        path: Output file path
        extended: If True, include #EXTINF metadata lines
    """
    with open(path, "w", encoding="utf-8") as f:
        if extended:
            f.write("#EXTM3U\n")

        for b in bookmarks:
            # Only include video/audio media types
            if b.media_type not in ('video', 'audio'):
                continue

            if extended:
                # Title: prefer "author - title" format
                if b.author_name:
                    title = f"{b.author_name} - {b.title or 'Untitled'}"
                else:
                    title = b.title or b.url
                # Clean title (remove commas as they're delimiters in EXTINF)
                title = title.replace(',', ' -')
                f.write(f"#EXTINF:-1,{title}\n")

            f.write(f"{b.url}\n")


def export_to_string(bookmarks: List[Bookmark], format: str) -> str:
    """
    Export bookmarks to a string in the specified format.

    Args:
        bookmarks: List of bookmarks to export
        format: Export format (json, html, csv, markdown)

    Returns:
        Exported content as string
    """
    import io

    if format == 'json':
        # JSON export to string
        result = []
        for b in bookmarks:
            result.append({
                "url": b.url,
                "title": b.title,
                "description": b.description,
                "added": b.added.isoformat() if b.added else None,
                "tags": [t.name for t in b.tags],
                "stars": b.stars,
                "visit_count": b.visit_count
            })
        import json
        return json.dumps(result, indent=2, default=str)

    elif format == 'csv':
        output = io.StringIO()
        output.write("url,title,description,tags,added,stars\n")
        for b in bookmarks:
            tags = ";".join(t.name for t in b.tags)
            title = (b.title or "").replace('"', '""')
            desc = (b.description or "").replace('"', '""')
            added = b.added.isoformat() if b.added else ""
            output.write(f'"{b.url}","{title}","{desc}","{tags}","{added}",{b.stars}\n')
        return output.getvalue()

    elif format == 'html':
        lines = [
            '<!DOCTYPE NETSCAPE-Bookmark-file-1>',
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            '<TITLE>Bookmarks</TITLE>',
            '<H1>Bookmarks</H1>',
            '<DL><p>'
        ]
        for b in bookmarks:
            title = b.title or b.url
            added_ts = int(b.added.timestamp()) if b.added else ""
            lines.append(f'    <DT><A HREF="{b.url}" ADD_DATE="{added_ts}">{title}</A>')
            if b.description:
                lines.append(f'    <DD>{b.description}')
        lines.append('</DL><p>')
        return '\n'.join(lines)

    elif format == 'markdown':
        lines = ['# Bookmarks', '']
        for b in bookmarks:
            title = b.title or b.url
            star = ' :star:' if b.stars else ''
            lines.append(f'- [{title}]({b.url}){star}')
            if b.description:
                lines.append(f'  > {b.description}')
        return '\n'.join(lines)

    elif format in ('m3u', 'm3u8'):
        lines = ['#EXTM3U']
        for b in bookmarks:
            if b.media_type not in ('video', 'audio'):
                continue
            if b.author_name:
                title = f"{b.author_name} - {b.title or 'Untitled'}"
            else:
                title = b.title or b.url
            title = title.replace(',', ' -')
            lines.append(f"#EXTINF:-1,{title}")
            lines.append(b.url)
        return '\n'.join(lines)

    else:
        # Plain text - just URLs
        return '\n'.join(b.url for b in bookmarks)


# =============================================================================
# HTML App Export (Interactive Viewer)
# =============================================================================

def _serialize_bookmark_for_app(bookmark: Bookmark) -> dict:
    """Serialize a bookmark with all fields for HTML app export."""
    # Get extra_data for reading queue fields
    extra = bookmark.extra_data or {}

    result = {
        "id": bookmark.id,
        "unique_id": bookmark.unique_id,
        "url": bookmark.url,
        "title": bookmark.title,
        "description": bookmark.description or "",
        "tags": [t.name for t in bookmark.tags],
        "added": bookmark.added.isoformat() if bookmark.added else None,
        "last_visited": bookmark.last_visited.isoformat() if bookmark.last_visited else None,
        "visit_count": bookmark.visit_count or 0,
        "stars": bookmark.stars,
        "pinned": bookmark.pinned,
        "archived": bookmark.archived,
        "reachable": bookmark.reachable,
        "media_type": bookmark.media_type,
        "media_source": bookmark.media_source,
        "author_name": bookmark.author_name,
        "author_url": bookmark.author_url,
        "thumbnail_url": bookmark.thumbnail_url,
        "favicon_data": None,
        "favicon_mime_type": None,
        # Reading queue fields
        "reading_queue": extra.get("reading_queue", False),
        "reading_progress": extra.get("reading_progress", 0),
        "reading_priority": extra.get("reading_priority", 3),
        "queued_at": extra.get("queued_at"),
        "estimated_read_time": extra.get("estimated_read_time"),
    }

    # Encode favicon as base64 if available
    if bookmark.favicon_data:
        result["favicon_data"] = base64.b64encode(bookmark.favicon_data).decode('ascii')
        result["favicon_mime_type"] = bookmark.favicon_mime_type or "image/png"

    return result


def _get_tag_stats(bookmarks: List[Bookmark]) -> List[dict]:
    """Compute tag statistics for tag cloud display."""
    tag_counts = Counter()
    tag_colors = {}

    for b in bookmarks:
        for tag in b.tags:
            tag_counts[tag.name] += 1
            if tag.color and tag.name not in tag_colors:
                tag_colors[tag.name] = tag.color

    return [
        {"name": name, "count": count, "color": tag_colors.get(name)}
        for name, count in tag_counts.most_common()
    ]


def _get_export_stats(bookmarks: List[Bookmark]) -> dict:
    """Compute comprehensive statistics for the statistics dashboard."""
    from urllib.parse import urlparse

    total = len(bookmarks)
    starred = sum(1 for b in bookmarks if b.stars)
    pinned = sum(1 for b in bookmarks if b.pinned)
    archived = sum(1 for b in bookmarks if b.archived)
    unread = sum(1 for b in bookmarks if (b.visit_count or 0) == 0)

    # Health stats
    reachable = sum(1 for b in bookmarks if b.reachable is True)
    broken = sum(1 for b in bookmarks if b.reachable is False)
    unchecked = sum(1 for b in bookmarks if b.reachable is None)

    # Media breakdown
    media_counts = Counter(b.media_type for b in bookmarks if b.media_type)

    # Media source breakdown
    source_counts = Counter(b.media_source for b in bookmarks if b.media_source)

    # Domain breakdown
    domain_counts = Counter()
    for b in bookmarks:
        try:
            domain = urlparse(b.url).netloc
            if domain:
                domain_counts[domain] += 1
        except Exception:
            pass

    # Timeline data (bookmarks per month)
    timeline = Counter()
    for b in bookmarks:
        if b.added:
            key = b.added.strftime("%Y-%m")
            timeline[key] += 1

    # Reading queue stats
    queue_count = sum(1 for b in bookmarks if (b.extra_data or {}).get('reading_queue'))
    queue_in_progress = sum(
        1 for b in bookmarks
        if (b.extra_data or {}).get('reading_queue')
        and 0 < (b.extra_data or {}).get('reading_progress', 0) < 100
    )

    # Tag count
    all_tags = set()
    for b in bookmarks:
        for tag in b.tags:
            all_tags.add(tag.name)

    return {
        "total": total,
        "starred": starred,
        "pinned": pinned,
        "archived": archived,
        "unread": unread,
        "reachable": reachable,
        "broken": broken,
        "unchecked": unchecked,
        "tag_count": len(all_tags),
        "media_breakdown": dict(media_counts.most_common(10)),
        "source_breakdown": dict(source_counts.most_common(10)),
        "top_domains": dict(domain_counts.most_common(20)),
        "timeline": dict(sorted(timeline.items())),
        "queue_count": queue_count,
        "queue_in_progress": queue_in_progress,
    }


# CSS for the HTML app
_HTML_APP_CSS = '''
/* CSS Variables for theming */
:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --bg-card: #ffffff;
    --bg-hover: #f0f0f0;
    --text-primary: #212529;
    --text-secondary: #6c757d;
    --text-muted: #adb5bd;
    --border-color: #dee2e6;
    --accent-color: #0d6efd;
    --accent-hover: #0b5ed7;
    --tag-bg: #e7f1ff;
    --tag-text: #0d6efd;
    --star-color: #ffc107;
    --success-color: #198754;
    --danger-color: #dc3545;
    --warning-color: #fd7e14;
    --shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
    --shadow-hover: 0 3px 6px rgba(0,0,0,0.16), 0 3px 6px rgba(0,0,0,0.23);
    /* View mode specific */
    --list-row-height: 48px;
    --table-header-bg: #f1f3f4;
    --table-row-hover: #f8f9fa;
    --table-border: #e0e0e0;
    /* Progress & priority */
    --progress-bg: #e9ecef;
    --progress-fill: #0d6efd;
    --priority-1: #dc3545;
    --priority-2: #fd7e14;
    --priority-3: #ffc107;
    --priority-4: #198754;
    --priority-5: #6c757d;
    /* Gallery */
    --gallery-gap: 16px;
    --thumbnail-height: 180px;
}

[data-theme="dark"] {
    --bg-primary: #1a1d21;
    --bg-secondary: #212529;
    --bg-card: #2b3035;
    --bg-hover: #343a40;
    --text-primary: #f8f9fa;
    --text-secondary: #adb5bd;
    --text-muted: #6c757d;
    --border-color: #495057;
    --accent-color: #6ea8fe;
    --accent-hover: #8bb9fe;
    --tag-bg: #1e3a5f;
    --tag-text: #6ea8fe;
    --star-color: #ffda6a;
    --success-color: #75b798;
    --danger-color: #ea868f;
    --warning-color: #ffb454;
    --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.4);
    --shadow-hover: 0 3px 6px rgba(0,0,0,0.4), 0 3px 6px rgba(0,0,0,0.5);
    --table-header-bg: #2b3035;
    --table-row-hover: #343a40;
    --table-border: #495057;
    --progress-bg: #495057;
}

/* Reset and base */
*, *::before, *::after { box-sizing: border-box; }
body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    background: var(--bg-primary);
    color: var(--text-primary);
}

/* Layout */
.app-container {
    display: grid;
    grid-template-areas:
        "header header"
        "sidebar main";
    grid-template-columns: 280px 1fr;
    grid-template-rows: auto 1fr;
    min-height: 100vh;
}

#app-header {
    grid-area: header;
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 1.5rem;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    position: sticky;
    top: 0;
    z-index: 100;
}

.header-brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--accent-color);
}

.header-brand svg { width: 24px; height: 24px; }

.search-container {
    flex: 1;
    max-width: 500px;
    position: relative;
}

#search-input {
    width: 100%;
    padding: 0.5rem 1rem 0.5rem 2.5rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 14px;
}

#search-input:focus {
    outline: none;
    border-color: var(--accent-color);
    box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.15);
}

.search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
}

.header-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.bookmark-count {
    color: var(--text-secondary);
    font-size: 0.875rem;
}

/* View switcher */
.view-switcher {
    display: flex;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 2px;
}

.view-btn {
    background: none;
    border: none;
    padding: 0.375rem 0.625rem;
    cursor: pointer;
    color: var(--text-secondary);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s ease;
}

.view-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.view-btn.active { background: var(--accent-color); color: white; }
.view-btn svg { width: 18px; height: 18px; }

/* Header buttons */
.header-btn {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.5rem;
    cursor: pointer;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
}

.header-btn:hover { background: var(--bg-hover); }

#theme-toggle {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.5rem;
    cursor: pointer;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    justify-content: center;
}

#theme-toggle:hover { background: var(--bg-hover); }

/* Sidebar */
#sidebar {
    grid-area: sidebar;
    padding: 1rem;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    overflow-y: auto;
    height: calc(100vh - 60px);
    position: sticky;
    top: 60px;
}

.sidebar-section {
    margin-bottom: 1.5rem;
}

.sidebar-section h3 {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin: 0 0 0.75rem 0;
}

#sort-select {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 13px;
}

.filter-checkboxes label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0;
    cursor: pointer;
    font-size: 13px;
}

.filter-checkboxes input[type="checkbox"] {
    width: 16px;
    height: 16px;
    accent-color: var(--accent-color);
}

/* Tag cloud */
#tag-cloud {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
}

.tag-filter {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s ease;
}

.tag-filter:hover {
    border-color: var(--accent-color);
    color: var(--accent-color);
}

.tag-filter.selected {
    background: var(--accent-color);
    border-color: var(--accent-color);
    color: white;
}

.tag-filter .count {
    color: var(--text-muted);
    font-size: 11px;
}

.tag-filter.selected .count { color: rgba(255,255,255,0.8); }

.clear-filters {
    width: 100%;
    margin-top: 0.75rem;
    padding: 0.375rem;
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
}

.clear-filters:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
}

/* Smart Collections */
.collections-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.collection-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    font-size: 13px;
}

.collection-item:hover { background: var(--bg-hover); }
.collection-item.active {
    background: var(--accent-color);
    color: white;
}

.collection-item .icon {
    font-size: 14px;
    width: 20px;
    text-align: center;
}

.collection-item .name { flex: 1; }

.collection-item .count {
    background: var(--bg-primary);
    padding: 0.125rem 0.5rem;
    border-radius: 10px;
    font-size: 11px;
    color: var(--text-secondary);
}

.collection-item.active .count {
    background: rgba(255,255,255,0.2);
    color: white;
}

.collection-item.hidden-col {
    opacity: 0.5;
}

/* Collection customization */
.customize-btn {
    width: 100%;
    margin-top: 0.5rem;
    padding: 0.375rem;
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 11px;
    cursor: pointer;
    text-align: center;
}

.customize-btn:hover { color: var(--accent-color); }

/* Curated Views */
.views-section h3 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.views-section h3::before {
    content: '📑';
    font-size: 14px;
}

.view-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    border-left: 3px solid transparent;
}

.view-item:hover {
    background: var(--bg-hover);
    border-left-color: var(--accent-color);
}

.view-item.active {
    background: var(--accent-color);
    color: white;
    border-left-color: transparent;
}

.view-item .view-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.view-item .view-name {
    flex: 1;
    font-size: 13px;
    font-weight: 500;
}

.view-item .view-count {
    background: var(--bg-primary);
    padding: 0.125rem 0.5rem;
    border-radius: 10px;
    font-size: 11px;
    color: var(--text-secondary);
}

.view-item.active .view-count {
    background: rgba(255,255,255,0.2);
    color: white;
}

.view-item .view-description {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.view-item.active .view-description {
    color: rgba(255,255,255,0.8);
}

/* Main content */
#main-content {
    grid-area: main;
    padding: 1.5rem;
    overflow-y: auto;
}

/* View modes - Grid (default) */
.view-grid #bookmark-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1rem;
}

#bookmark-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1rem;
}

/* View modes - List */
.view-list #bookmark-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.view-list .bookmark-card {
    display: none;
}

.bookmark-list-item {
    display: none;
}

.view-list .bookmark-list-item {
    display: flex;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    gap: 1rem;
    cursor: pointer;
    transition: all 0.15s ease;
}

.view-list .bookmark-list-item:hover {
    border-color: var(--accent-color);
    background: var(--bg-hover);
}

.view-list .bookmark-list-item:focus {
    outline: 2px solid var(--accent-color);
    outline-offset: 2px;
}

.list-favicon {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    flex-shrink: 0;
}

.list-title {
    flex: 1;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
}

.list-domain {
    color: var(--text-secondary);
    font-size: 12px;
    width: 150px;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.list-tags {
    display: flex;
    gap: 0.25rem;
    width: 180px;
    flex-shrink: 0;
    overflow: hidden;
}

.list-tags .tag {
    font-size: 10px;
    padding: 0.125rem 0.375rem;
}

.list-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100px;
    flex-shrink: 0;
    justify-content: flex-end;
    font-size: 12px;
    color: var(--text-muted);
}

.list-star { color: var(--star-color); }

/* View modes - Table */
.view-table #bookmark-list {
    display: block;
    overflow-x: auto;
}

.view-table .bookmark-card,
.view-table .bookmark-list-item {
    display: none;
}

.bookmark-table {
    display: none;
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.view-table .bookmark-table {
    display: table;
}

.bookmark-table th {
    position: sticky;
    top: 0;
    background: var(--table-header-bg);
    padding: 0.75rem;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid var(--border-color);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
}

.bookmark-table th:hover { background: var(--bg-hover); }
.bookmark-table th.sorted-asc::after { content: ' ↑'; color: var(--accent-color); }
.bookmark-table th.sorted-desc::after { content: ' ↓'; color: var(--accent-color); }

.bookmark-table td {
    padding: 0.625rem 0.75rem;
    border-bottom: 1px solid var(--table-border);
    vertical-align: middle;
}

.bookmark-table tbody tr {
    cursor: pointer;
    transition: background 0.1s;
}

.bookmark-table tbody tr:hover { background: var(--table-row-hover); }
.bookmark-table tbody tr:focus { outline: 2px solid var(--accent-color); outline-offset: -2px; }

.table-title-cell {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    max-width: 300px;
}

.table-title-cell img {
    width: 16px;
    height: 16px;
    border-radius: 2px;
}

.table-title-cell span {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.table-url {
    color: var(--accent-color);
    text-decoration: none;
    max-width: 200px;
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.table-url:hover { text-decoration: underline; }

/* View modes - Gallery */
.view-gallery #bookmark-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: var(--gallery-gap);
}

.view-gallery .bookmark-card,
.view-gallery .bookmark-list-item,
.view-gallery .bookmark-table {
    display: none;
}

.gallery-card {
    display: none;
    position: relative;
    border-radius: 12px;
    overflow: hidden;
    background: var(--bg-card);
    box-shadow: var(--shadow);
    cursor: pointer;
    transition: all 0.2s ease;
}

.view-gallery .gallery-card {
    display: block;
}

.gallery-card:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-hover);
}

.gallery-thumbnail {
    width: 100%;
    height: var(--thumbnail-height);
    object-fit: cover;
    background: var(--bg-secondary);
}

.gallery-placeholder {
    width: 100%;
    height: var(--thumbnail-height);
    background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-hover) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 48px;
    color: var(--text-muted);
}

.gallery-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: linear-gradient(transparent, rgba(0,0,0,0.85));
    padding: 2rem 1rem 1rem;
    color: white;
}

.gallery-title {
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 0.25rem;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.gallery-author {
    font-size: 12px;
    opacity: 0.8;
}

.gallery-badge {
    position: absolute;
    top: 0.75rem;
    left: 0.75rem;
    background: rgba(0,0,0,0.7);
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
}

.play-button {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 56px;
    height: 56px;
    background: rgba(0,0,0,0.7);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.2s;
    color: white;
    font-size: 24px;
}

.gallery-card:hover .play-button { opacity: 1; }

/* Bookmark cards */
.bookmark-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: var(--shadow);
}

.bookmark-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-hover);
    border-color: var(--accent-color);
}

.card-header {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
}

.favicon {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    flex-shrink: 0;
    background: var(--bg-secondary);
}

.card-title {
    flex: 1;
    font-size: 15px;
    font-weight: 600;
    margin: 0;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.card-star {
    color: var(--star-color);
    font-size: 16px;
    flex-shrink: 0;
}

.card-url {
    display: block;
    color: var(--text-secondary);
    font-size: 12px;
    text-decoration: none;
    margin-bottom: 0.75rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.card-url:hover { color: var(--accent-color); }

.card-thumbnail {
    width: 100%;
    height: 160px;
    object-fit: cover;
    border-radius: 6px;
    margin-bottom: 0.75rem;
    background: var(--bg-secondary);
}

.card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    margin-bottom: 0.75rem;
}

.tag {
    padding: 0.125rem 0.5rem;
    background: var(--tag-bg);
    color: var(--tag-text);
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
}

.card-meta {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--text-muted);
}

.card-badges {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.5rem;
}

.badge {
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
}

.badge-media {
    background: #e0cffc;
    color: #6f42c1;
}

.badge-pinned {
    background: #d1e7dd;
    color: #198754;
}

/* Modal */
.modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
}

.modal[hidden] { display: none; }

.modal-content {
    background: var(--bg-card);
    border-radius: 12px;
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
}

.modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 1.25rem;
    border-bottom: 1px solid var(--border-color);
}

.modal-header h2 {
    margin: 0;
    font-size: 1.25rem;
    line-height: 1.3;
    padding-right: 1rem;
}

.modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0;
    line-height: 1;
}

.modal-close:hover { color: var(--text-primary); }

.modal-body { padding: 1.25rem; }

.modal-section {
    margin-bottom: 1.25rem;
}

.modal-section:last-child { margin-bottom: 0; }

.modal-section h4 {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin: 0 0 0.5rem 0;
}

.modal-url {
    color: var(--accent-color);
    word-break: break-all;
}

.modal-description {
    color: var(--text-secondary);
    white-space: pre-wrap;
}

.modal-thumbnail {
    width: 100%;
    max-height: 300px;
    object-fit: contain;
    border-radius: 8px;
    background: var(--bg-secondary);
}

.modal-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.modal-tags .tag {
    cursor: pointer;
}

.modal-tags .tag:hover {
    background: var(--accent-color);
    color: white;
}

.modal-meta-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
}

.meta-item {
    display: flex;
    flex-direction: column;
}

.meta-label {
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 0.125rem;
}

.meta-value {
    font-size: 13px;
    color: var(--text-primary);
}

.meta-value.success { color: var(--success-color); }
.meta-value.danger { color: var(--danger-color); }

.modal-actions {
    display: flex;
    gap: 0.75rem;
    padding: 1.25rem;
    border-top: 1px solid var(--border-color);
}

.btn {
    padding: 0.625rem 1.25rem;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.15s ease;
}

.btn-primary {
    background: var(--accent-color);
    color: white;
    border: none;
}

.btn-primary:hover { background: var(--accent-hover); }

.btn-secondary {
    background: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
}

.btn-secondary:hover { background: var(--bg-hover); }

/* Reading Progress */
.reading-progress {
    height: 4px;
    background: var(--progress-bg);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 0.5rem;
}

.reading-progress-fill {
    height: 100%;
    background: var(--progress-fill);
    border-radius: 2px;
    transition: width 0.3s ease;
}

.reading-progress-fill.in-progress { background: var(--warning-color); }
.reading-progress-fill.complete { background: var(--success-color); }

/* Priority Badges */
.priority-badge {
    display: inline-flex;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    color: white;
    flex-shrink: 0;
}

.priority-1 { background: var(--priority-1); }
.priority-2 { background: var(--priority-2); }
.priority-3 { background: var(--priority-3); color: #333; }
.priority-4 { background: var(--priority-4); }
.priority-5 { background: var(--priority-5); }

/* Queue card extras */
.queue-meta {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-top: 0.5rem;
    font-size: 11px;
    color: var(--text-muted);
}

.queue-meta .progress-text { color: var(--accent-color); font-weight: 500; }
.queue-meta .read-time { display: flex; align-items: center; gap: 0.25rem; }

/* Statistics Dashboard */
.stats-dashboard {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1100;
    padding: 1rem;
    backdrop-filter: blur(4px);
}

.stats-dashboard[hidden] { display: none; }

.stats-content {
    background: var(--bg-card);
    border-radius: 16px;
    max-width: 900px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.4);
}

.stats-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
}

.stats-header h2 { margin: 0; font-size: 1.25rem; }

.stats-body { padding: 1.5rem; }

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
}

.stat-card {
    background: var(--bg-secondary);
    border-radius: 12px;
    padding: 1.25rem 1rem;
    text-align: center;
}

.stat-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent-color);
    line-height: 1;
    margin-bottom: 0.25rem;
}

.stat-label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.stats-section {
    margin-bottom: 2rem;
}

.stats-section:last-child { margin-bottom: 0; }

.stats-section h3 {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 1rem 0;
}

/* Timeline chart */
.chart-timeline {
    display: flex;
    align-items: flex-end;
    height: 120px;
    gap: 4px;
    padding: 0.5rem 0;
}

.chart-bar {
    flex: 1;
    background: var(--accent-color);
    border-radius: 4px 4px 0 0;
    min-width: 16px;
    position: relative;
    transition: background 0.2s;
}

.chart-bar:hover { background: var(--accent-hover); }

.chart-bar .tooltip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    background: var(--text-primary);
    color: var(--bg-primary);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 11px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s;
}

.chart-bar:hover .tooltip { opacity: 1; }

.chart-labels {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    font-size: 10px;
    color: var(--text-muted);
}

/* Domain/media lists in stats */
.stats-list {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0.5rem;
}

.stats-list-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    background: var(--bg-secondary);
    border-radius: 6px;
    font-size: 13px;
}

.stats-list-item .name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.stats-list-item .count {
    color: var(--text-muted);
    font-size: 12px;
    flex-shrink: 0;
    margin-left: 0.5rem;
}

/* Keyboard Shortcuts Help */
.shortcuts-modal .modal-content {
    max-width: 500px;
}

.shortcuts-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
}

.shortcut-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem;
    background: var(--bg-secondary);
    border-radius: 6px;
}

.shortcut-key {
    display: inline-flex;
    min-width: 28px;
    height: 28px;
    align-items: center;
    justify-content: center;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-family: ui-monospace, monospace;
    font-size: 12px;
    font-weight: 600;
    box-shadow: 0 2px 0 var(--border-color);
}

.shortcut-desc {
    font-size: 13px;
    color: var(--text-secondary);
}

/* Customize Collections Modal */
.customize-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.customize-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--bg-secondary);
    border-radius: 8px;
    cursor: grab;
}

.customize-item:active { cursor: grabbing; }

.customize-item.dragging { opacity: 0.5; }

.customize-item .drag-handle {
    color: var(--text-muted);
    cursor: grab;
}

.customize-item .icon { font-size: 16px; }

.customize-item .name { flex: 1; font-size: 14px; }

.customize-item .toggle {
    width: 40px;
    height: 22px;
    background: var(--bg-hover);
    border-radius: 11px;
    position: relative;
    cursor: pointer;
    transition: background 0.2s;
}

.customize-item .toggle.active { background: var(--accent-color); }

.customize-item .toggle::after {
    content: '';
    position: absolute;
    width: 18px;
    height: 18px;
    background: white;
    border-radius: 50%;
    top: 2px;
    left: 2px;
    transition: transform 0.2s;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}

.customize-item .toggle.active::after { transform: translateX(18px); }

/* Focus states for keyboard nav */
.bookmark-card:focus,
.bookmark-list-item:focus,
.gallery-card:focus {
    outline: 2px solid var(--accent-color);
    outline-offset: 2px;
}

.focused {
    outline: 2px solid var(--accent-color);
    outline-offset: 2px;
}

/* Empty state */
.empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--text-secondary);
}

.empty-state svg {
    width: 64px;
    height: 64px;
    color: var(--text-muted);
    margin-bottom: 1rem;
}

.empty-state h3 {
    margin: 0 0 0.5rem 0;
    color: var(--text-primary);
}

/* Mobile sidebar toggle */
#sidebar-toggle {
    display: none;
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.5rem;
    cursor: pointer;
    color: var(--text-primary);
}

/* Responsive */
@media (max-width: 1024px) {
    .app-container { grid-template-columns: 240px 1fr; }
    #bookmark-list { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
    .view-gallery #bookmark-list { grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
    .list-domain { width: 120px; }
    .list-tags { width: 140px; }
}

@media (max-width: 768px) {
    .app-container {
        grid-template-areas: "header" "main";
        grid-template-columns: 1fr;
    }

    #sidebar {
        position: fixed;
        left: -280px;
        top: 60px;
        width: 280px;
        height: calc(100vh - 60px);
        z-index: 200;
        transition: left 0.3s ease;
    }

    #sidebar.open { left: 0; }

    .sidebar-overlay {
        position: fixed;
        top: 60px;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.5);
        z-index: 150;
    }

    .sidebar-overlay[hidden] { display: none; }

    #sidebar-toggle { display: flex; }

    .header-brand span { display: none; }

    #bookmark-list { grid-template-columns: 1fr; }

    .modal-meta-grid { grid-template-columns: 1fr; }

    /* Hide view switcher text, show icons only */
    .view-switcher { padding: 2px; }

    /* List view compact on mobile */
    .view-list .bookmark-list-item { flex-wrap: wrap; }
    .list-domain, .list-tags { display: none; }
    .list-title { width: 100%; }

    /* Stats dashboard mobile */
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
    .shortcuts-grid { grid-template-columns: 1fr; }
}

@media (max-width: 480px) {
    #app-header { padding: 0.5rem 1rem; gap: 0.5rem; }
    #main-content { padding: 1rem; }
    .modal-content { border-radius: 0; max-height: 100vh; }
    .view-switcher { display: none; }
    .bookmark-count { display: none; }
    .stats-grid { grid-template-columns: 1fr; }
}

/* Animations */
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.bookmark-card {
    animation: fadeIn 0.3s ease;
}
'''


# JavaScript for the HTML app
_HTML_APP_JS = '''
// State management
const AppState = {
    bookmarks: [],
    tags: [],
    stats: null,
    searchQuery: '',
    selectedTags: new Set(),
    sortBy: 'added-desc',
    filterStarred: false,
    filterPinned: false,
    theme: 'light',
    searchIndex: null,
    // New: View modes
    viewMode: 'grid',  // grid, list, table, gallery
    // New: Smart collections
    activeCollection: 'all',
    collectionOrder: ['all', 'unread', 'starred', 'queue', 'popular', 'media', 'broken', 'untagged', 'pdfs'],
    hiddenCollections: new Set(),
    // New: Curated views
    views: {},
    activeView: null,
    // New: Table sorting
    tableSortColumn: 'added',
    tableSortDirection: 'desc',
    // New: Keyboard navigation
    selectedIndex: -1
};

// Smart Collections definitions
const SMART_COLLECTIONS = {
    all: { name: 'All Bookmarks', icon: '📚', filter: () => true },
    unread: { name: 'Unread', icon: '📖', filter: b => (b.visit_count || 0) === 0 },
    starred: { name: 'Starred', icon: '⭐', filter: b => b.stars },
    queue: { name: 'Reading Queue', icon: '📋', filter: b => b.reading_queue },
    popular: { name: 'Popular', icon: '🔥', filter: b => (b.visit_count || 0) > 5, sort: (a, b) => (b.visit_count || 0) - (a.visit_count || 0), limit: 100 },
    media: { name: 'Media', icon: '🎬', filter: b => b.media_type !== null },
    broken: { name: 'Broken', icon: '🔗', filter: b => b.reachable === false },
    untagged: { name: 'Untagged', icon: '🏷️', filter: b => (b.tags || []).length === 0 },
    pdfs: { name: 'PDFs', icon: '📄', filter: b => (b.url || '').toLowerCase().endsWith('.pdf') }
};

// Keyboard shortcuts
const KEYBOARD_SHORTCUTS = {
    'j': { action: 'next', desc: 'Next bookmark' },
    'k': { action: 'prev', desc: 'Previous bookmark' },
    '/': { action: 'search', desc: 'Focus search' },
    'Enter': { action: 'open', desc: 'Open selected' },
    'Escape': { action: 'close', desc: 'Close modal' },
    'g': { action: 'view-grid', desc: 'Grid view' },
    'l': { action: 'view-list', desc: 'List view' },
    't': { action: 'view-table', desc: 'Table view' },
    'm': { action: 'view-gallery', desc: 'Gallery view' },
    'd': { action: 'toggle-theme', desc: 'Toggle dark mode' },
    's': { action: 'toggle-stats', desc: 'Statistics' },
    '?': { action: 'show-help', desc: 'Show shortcuts' },
    '1': { action: 'col-all', desc: 'All bookmarks' },
    '2': { action: 'col-unread', desc: 'Unread' },
    '3': { action: 'col-starred', desc: 'Starred' },
    '4': { action: 'col-queue', desc: 'Reading queue' },
    '5': { action: 'col-popular', desc: 'Popular' },
    '6': { action: 'col-media', desc: 'Media' }
};

// Search index for fast full-text search
class SearchIndex {
    constructor(bookmarks) {
        this.index = new Map();
        this.bookmarkIds = new Map();
        bookmarks.forEach((b, idx) => {
            this.bookmarkIds.set(b.id, idx);
            const text = [
                b.title || '',
                b.url || '',
                b.description || '',
                ...(b.tags || []),
                b.author_name || ''
            ].join(' ').toLowerCase();

            const words = text.match(/\\w+/g) || [];
            words.forEach(word => {
                if (!this.index.has(word)) this.index.set(word, new Set());
                this.index.get(word).add(b.id);
            });
        });
    }

    search(query) {
        if (!query.trim()) return null;
        const terms = query.toLowerCase().match(/\\w+/g) || [];
        if (terms.length === 0) return null;

        let results = null;
        terms.forEach(term => {
            const matches = new Set();
            this.index.forEach((ids, word) => {
                if (word.startsWith(term) || word.includes(term)) {
                    ids.forEach(id => matches.add(id));
                }
            });

            if (results === null) {
                results = matches;
            } else {
                results = new Set([...results].filter(id => matches.has(id)));
            }
        });

        return results;
    }
}

// Utility functions
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric'
    });
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

function truncateUrl(url, maxLen = 50) {
    try {
        const u = new URL(url);
        let display = u.hostname + u.pathname;
        if (display.length > maxLen) {
            display = display.substring(0, maxLen - 3) + '...';
        }
        return display;
    } catch {
        return url.length > maxLen ? url.substring(0, maxLen - 3) + '...' : url;
    }
}

function getFaviconUrl(bookmark) {
    if (bookmark.favicon_data && bookmark.favicon_mime_type) {
        return `data:${bookmark.favicon_mime_type};base64,${bookmark.favicon_data}`;
    }
    try {
        const hostname = new URL(bookmark.url).hostname;
        return `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`;
    } catch {
        return '';
    }
}

// State persistence
function loadState() {
    try {
        const saved = localStorage.getItem('btk-viewer-state');
        if (saved) {
            const state = JSON.parse(saved);
            AppState.theme = state.theme || 'light';
            AppState.sortBy = state.sortBy || 'added-desc';
            AppState.selectedTags = new Set(state.selectedTags || []);
            AppState.filterStarred = state.filterStarred || false;
            AppState.filterPinned = state.filterPinned || false;
            // New state properties
            AppState.viewMode = state.viewMode || 'grid';
            AppState.activeCollection = state.activeCollection || 'all';
            if (state.collectionOrder) AppState.collectionOrder = state.collectionOrder;
            AppState.hiddenCollections = new Set(state.hiddenCollections || []);
            AppState.tableSortColumn = state.tableSortColumn || 'added';
            AppState.tableSortDirection = state.tableSortDirection || 'desc';
        }
    } catch (e) {
        console.warn('Failed to load state:', e);
    }
}

function saveState() {
    try {
        localStorage.setItem('btk-viewer-state', JSON.stringify({
            theme: AppState.theme,
            sortBy: AppState.sortBy,
            selectedTags: [...AppState.selectedTags],
            filterStarred: AppState.filterStarred,
            filterPinned: AppState.filterPinned,
            // New state properties
            viewMode: AppState.viewMode,
            activeCollection: AppState.activeCollection,
            collectionOrder: AppState.collectionOrder,
            hiddenCollections: [...AppState.hiddenCollections],
            tableSortColumn: AppState.tableSortColumn,
            tableSortDirection: AppState.tableSortDirection
        }));
    } catch (e) {
        console.warn('Failed to save state:', e);
    }
}

// Filtering and sorting
function getFilteredBookmarks() {
    let results = [...AppState.bookmarks];

    // Collection filter (applied first)
    if (AppState.activeCollection && AppState.activeCollection !== 'all') {
        const collection = SMART_COLLECTIONS[AppState.activeCollection];
        if (collection) {
            results = results.filter(collection.filter);
            if (collection.sort) results.sort(collection.sort);
            if (collection.limit) results = results.slice(0, collection.limit);
        }
    }

    // View filter (filters to specific bookmark IDs from curated view)
    if (AppState.activeView) {
        const view = AppState.views[AppState.activeView];
        if (view && view.bookmark_ids) {
            const viewIds = new Set(view.bookmark_ids);
            results = results.filter(b => viewIds.has(b.id));
        }
    }

    // Search filter
    if (AppState.searchQuery) {
        const matchIds = AppState.searchIndex.search(AppState.searchQuery);
        if (matchIds) {
            results = results.filter(b => matchIds.has(b.id));
        }
    }

    // Tag filter (AND logic)
    if (AppState.selectedTags.size > 0) {
        results = results.filter(b =>
            [...AppState.selectedTags].every(tag => (b.tags || []).includes(tag))
        );
    }

    // Starred/pinned filters
    if (AppState.filterStarred) results = results.filter(b => b.stars);
    if (AppState.filterPinned) results = results.filter(b => b.pinned);

    // Sorting (unless collection has its own sort)
    const collection = SMART_COLLECTIONS[AppState.activeCollection];
    if (!collection || !collection.sort) {
        const sortFns = {
            'added-desc': (a, b) => new Date(b.added || 0) - new Date(a.added || 0),
            'added-asc': (a, b) => new Date(a.added || 0) - new Date(b.added || 0),
            'title-asc': (a, b) => (a.title || '').localeCompare(b.title || ''),
            'title-desc': (a, b) => (b.title || '').localeCompare(a.title || ''),
            'visits-desc': (a, b) => (b.visit_count || 0) - (a.visit_count || 0),
            'visited-desc': (a, b) => new Date(b.last_visited || 0) - new Date(a.last_visited || 0),
            'stars-desc': (a, b) => (b.stars || 0) - (a.stars || 0)
        };
        results.sort(sortFns[AppState.sortBy] || sortFns['added-desc']);
    }

    return results;
}

// Get domain from URL
function getDomain(url) {
    try {
        return new URL(url).hostname;
    } catch {
        return url;
    }
}

// Rendering
function renderBookmarkCard(b) {
    const favicon = getFaviconUrl(b);
    const hasThumbnail = b.thumbnail_url && b.media_type;

    return `
        <article class="bookmark-card" data-id="${b.id}">
            <div class="card-header">
                ${favicon ? `<img class="favicon" src="${escapeHtml(favicon)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ''}
                <h3 class="card-title">${escapeHtml(b.title)}</h3>
                ${b.stars ? '<span class="card-star">★</span>' : ''}
            </div>
            <a class="card-url" href="${escapeHtml(b.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">
                ${escapeHtml(truncateUrl(b.url))}
            </a>
            ${hasThumbnail ? `<img class="card-thumbnail" src="${escapeHtml(b.thumbnail_url)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ''}
            ${(b.tags || []).length > 0 ? `
                <div class="card-tags">
                    ${b.tags.slice(0, 4).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}
                    ${b.tags.length > 4 ? `<span class="tag">+${b.tags.length - 4}</span>` : ''}
                </div>
            ` : ''}
            <div class="card-meta">
                <span>${formatDate(b.added)}</span>
                ${b.visit_count ? `<span>${b.visit_count} visits</span>` : ''}
            </div>
            ${(b.media_type || b.pinned) ? `
                <div class="card-badges">
                    ${b.media_type ? `<span class="badge badge-media">${escapeHtml(b.media_source || b.media_type)}</span>` : ''}
                    ${b.pinned ? '<span class="badge badge-pinned">Pinned</span>' : ''}
                </div>
            ` : ''}
        </article>
    `;
}

// List view item renderer
function renderListItem(b) {
    const favicon = getFaviconUrl(b);
    const domain = getDomain(b.url);
    const tags = (b.tags || []).slice(0, 3);

    return `
        <div class="bookmark-list-item" data-id="${b.id}" tabindex="0">
            ${favicon ? `<img class="list-favicon" src="${escapeHtml(favicon)}" alt="" loading="lazy" onerror="this.style.display='none'">` : '<div class="list-favicon"></div>'}
            <span class="list-title">${b.stars ? '<span class="list-star">★</span> ' : ''}${escapeHtml(b.title)}</span>
            <span class="list-domain">${escapeHtml(domain)}</span>
            <div class="list-tags">${tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
            <span class="list-meta">${b.visit_count ? b.visit_count + ' visits' : formatDate(b.added)}</span>
        </div>
    `;
}

// Table view renderer
function renderTable(bookmarks) {
    const headers = [
        { key: 'title', label: 'Title', sortable: true },
        { key: 'url', label: 'URL', sortable: false },
        { key: 'tags', label: 'Tags', sortable: false },
        { key: 'added', label: 'Added', sortable: true },
        { key: 'visit_count', label: 'Visits', sortable: true }
    ];

    const sortClass = (key) => {
        if (AppState.tableSortColumn !== key) return '';
        return AppState.tableSortDirection === 'asc' ? 'sorted-asc' : 'sorted-desc';
    };

    const headerHtml = headers.map(h =>
        `<th class="${sortClass(h.key)} ${h.sortable ? 'sortable' : ''}" data-sort="${h.key}">${h.label}</th>`
    ).join('');

    const rowsHtml = bookmarks.map(b => {
        const favicon = getFaviconUrl(b);
        const domain = getDomain(b.url);
        const tags = (b.tags || []).slice(0, 2).join(', ');

        return `
            <tr data-id="${b.id}" tabindex="0">
                <td>
                    <div class="table-title-cell">
                        ${favicon ? `<img src="${escapeHtml(favicon)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ''}
                        <span>${b.stars ? '★ ' : ''}${escapeHtml((b.title || '').substring(0, 60))}</span>
                    </div>
                </td>
                <td><a class="table-url" href="${escapeHtml(b.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(domain)}</a></td>
                <td>${escapeHtml(tags)}</td>
                <td>${formatDate(b.added)}</td>
                <td>${b.visit_count || 0}</td>
            </tr>
        `;
    }).join('');

    return `
        <table class="bookmark-table">
            <thead><tr>${headerHtml}</tr></thead>
            <tbody>${rowsHtml}</tbody>
        </table>
    `;
}

// Gallery view card renderer
function renderGalleryCard(b) {
    const isMedia = b.media_type && b.thumbnail_url;
    const icon = b.media_type === 'video' ? '▶' : b.media_type === 'audio' ? '♪' : '📄';

    if (!b.thumbnail_url) {
        // No thumbnail - show placeholder with domain initial
        const domain = getDomain(b.url);
        const initial = domain.charAt(0).toUpperCase();
        return `
            <div class="gallery-card" data-id="${b.id}" tabindex="0">
                <div class="gallery-placeholder">${initial}</div>
                ${b.media_type ? `<span class="gallery-badge">${escapeHtml(b.media_source || b.media_type)}</span>` : ''}
                <div class="gallery-overlay">
                    <div class="gallery-title">${escapeHtml(b.title)}</div>
                    ${b.author_name ? `<div class="gallery-author">${escapeHtml(b.author_name)}</div>` : ''}
                </div>
            </div>
        `;
    }

    return `
        <div class="gallery-card" data-id="${b.id}" tabindex="0">
            <img class="gallery-thumbnail" src="${escapeHtml(b.thumbnail_url)}" alt="" loading="lazy" onerror="this.parentElement.querySelector('.gallery-placeholder')?.remove(); this.style.display='none'">
            ${b.media_type ? `<span class="gallery-badge">${escapeHtml(b.media_source || b.media_type)}</span>` : ''}
            ${b.media_type === 'video' ? '<div class="play-button">▶</div>' : ''}
            <div class="gallery-overlay">
                <div class="gallery-title">${escapeHtml(b.title)}</div>
                ${b.author_name ? `<div class="gallery-author">${escapeHtml(b.author_name)}</div>` : ''}
            </div>
        </div>
    `;
}

// Collections sidebar renderer
function renderCollectionsSidebar() {
    const container = document.getElementById('collections-list');
    if (!container) return;

    const html = AppState.collectionOrder
        .filter(id => !AppState.hiddenCollections.has(id))
        .map(id => {
            const col = SMART_COLLECTIONS[id];
            if (!col) return '';
            const count = AppState.bookmarks.filter(col.filter).length;
            const active = AppState.activeCollection === id ? 'active' : '';
            return `
                <div class="collection-item ${active}" data-collection="${id}">
                    <span class="icon">${col.icon}</span>
                    <span class="name">${col.name}</span>
                    <span class="count">${count}</span>
                </div>
            `;
        }).join('');

    container.innerHTML = html;
}

// Curated views sidebar renderer
function renderViewsSidebar() {
    const section = document.getElementById('views-section');
    const container = document.getElementById('views-list');
    if (!section || !container) return;

    const viewNames = Object.keys(AppState.views);
    if (viewNames.length === 0) {
        section.hidden = true;
        return;
    }

    section.hidden = false;
    const bookmarkIdSet = new Set(AppState.bookmarks.map(b => b.id));

    const html = viewNames.map(name => {
        const view = AppState.views[name];
        const validIds = (view.bookmark_ids || []).filter(id => bookmarkIdSet.has(id));
        const count = validIds.length;
        const active = AppState.activeView === name ? 'active' : '';
        const description = view.description || '';

        return `
            <div class="view-item ${active}" data-view="${escapeHtml(name)}" title="${escapeHtml(description)}">
                <div class="view-header">
                    <span class="view-name">${escapeHtml(name)}</span>
                    <span class="view-count">${count}</span>
                </div>
                ${description ? `<div class="view-description">${escapeHtml(description)}</div>` : ''}
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// Set active view filter
function setActiveView(viewName) {
    if (viewName === AppState.activeView) {
        // Toggle off
        AppState.activeView = null;
    } else {
        AppState.activeView = viewName;
        // Clear collection filter when selecting a view
        AppState.activeCollection = 'all';
    }
    renderCollectionsSidebar();
    renderViewsSidebar();
    renderBookmarkList();
    saveState();
}

// Main render function dispatches to appropriate view
function renderBookmarkList() {
    const container = document.getElementById('bookmark-list');
    const bookmarks = getFilteredBookmarks();
    AppState.selectedIndex = -1;  // Reset keyboard selection

    if (bookmarks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                </svg>
                <h3>No bookmarks found</h3>
                <p>Try adjusting your search or filters</p>
            </div>
        `;
        updateCount(0);
        return;
    }

    // Render based on view mode
    let html = '';
    switch (AppState.viewMode) {
        case 'list':
            html = bookmarks.map(renderListItem).join('');
            break;
        case 'table':
            html = renderTable(bookmarks);
            break;
        case 'gallery':
            html = bookmarks.map(renderGalleryCard).join('');
            break;
        case 'grid':
        default:
            html = bookmarks.map(renderBookmarkCard).join('');
            break;
    }

    container.innerHTML = html;
    updateCount(bookmarks.length);
}

function renderTagCloud() {
    const container = document.getElementById('tag-cloud');
    const tags = AppState.tags.slice(0, 50);

    container.innerHTML = tags.map(t => `
        <button class="tag-filter ${AppState.selectedTags.has(t.name) ? 'selected' : ''}"
                data-tag="${escapeHtml(t.name)}">
            ${escapeHtml(t.name)}
            <span class="count">${t.count}</span>
        </button>
    `).join('');
}

function updateCount(shown) {
    const el = document.getElementById('bookmark-count');
    el.textContent = shown === AppState.bookmarks.length
        ? `${shown} bookmarks`
        : `${shown} of ${AppState.bookmarks.length}`;
}

// Modal
function showBookmarkDetail(bookmarkId) {
    const bookmark = AppState.bookmarks.find(b => b.id === parseInt(bookmarkId));
    if (!bookmark) return;

    const modal = document.getElementById('bookmark-modal');
    const body = document.getElementById('modal-body');

    body.innerHTML = `
        <div class="modal-section">
            <h4>URL</h4>
            <a class="modal-url" href="${escapeHtml(bookmark.url)}" target="_blank" rel="noopener">
                ${escapeHtml(bookmark.url)}
            </a>
        </div>

        ${bookmark.description ? `
            <div class="modal-section">
                <h4>Description</h4>
                <p class="modal-description">${escapeHtml(bookmark.description)}</p>
            </div>
        ` : ''}

        ${bookmark.thumbnail_url ? `
            <div class="modal-section">
                <img class="modal-thumbnail" src="${escapeHtml(bookmark.thumbnail_url)}" alt="">
            </div>
        ` : ''}

        ${(bookmark.tags || []).length > 0 ? `
            <div class="modal-section">
                <h4>Tags</h4>
                <div class="modal-tags">
                    ${bookmark.tags.map(t => `
                        <span class="tag" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>
                    `).join('')}
                </div>
            </div>
        ` : ''}

        <div class="modal-section">
            <h4>Details</h4>
            <div class="modal-meta-grid">
                <div class="meta-item">
                    <span class="meta-label">Added</span>
                    <span class="meta-value">${formatDateTime(bookmark.added)}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">Last Visited</span>
                    <span class="meta-value">${formatDateTime(bookmark.last_visited)}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">Visit Count</span>
                    <span class="meta-value">${bookmark.visit_count || 0}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">Status</span>
                    <span class="meta-value ${bookmark.reachable === false ? 'danger' : bookmark.reachable === true ? 'success' : ''}">
                        ${bookmark.reachable === true ? '✓ Reachable' : bookmark.reachable === false ? '✗ Unreachable' : 'Unknown'}
                    </span>
                </div>
                ${bookmark.media_type ? `
                    <div class="meta-item">
                        <span class="meta-label">Media Type</span>
                        <span class="meta-value">${escapeHtml(bookmark.media_type)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Source</span>
                        <span class="meta-value">${escapeHtml(bookmark.media_source || '-')}</span>
                    </div>
                ` : ''}
                ${bookmark.author_name ? `
                    <div class="meta-item">
                        <span class="meta-label">Author</span>
                        <span class="meta-value">
                            ${bookmark.author_url
                                ? `<a href="${escapeHtml(bookmark.author_url)}" target="_blank" rel="noopener">${escapeHtml(bookmark.author_name)}</a>`
                                : escapeHtml(bookmark.author_name)}
                        </span>
                    </div>
                ` : ''}
            </div>
        </div>

        <div class="modal-section">
            <h4>Flags</h4>
            <div style="display: flex; gap: 1rem;">
                <span>${bookmark.stars ? '★ Starred' : '☆ Not starred'}</span>
                <span>${bookmark.pinned ? '📌 Pinned' : ''}</span>
                <span>${bookmark.archived ? '📦 Archived' : ''}</span>
            </div>
        </div>
    `;

    document.getElementById('modal-title').textContent = bookmark.title;
    document.getElementById('modal-open-link').href = bookmark.url;
    modal.hidden = false;

    // Handle tag clicks in modal
    body.querySelectorAll('.modal-tags .tag').forEach(el => {
        el.addEventListener('click', () => {
            const tag = el.dataset.tag;
            AppState.selectedTags.add(tag);
            saveState();
            modal.hidden = true;
            render();
        });
    });
}

function hideModal() {
    document.getElementById('bookmark-modal').hidden = true;
}

// Theme
function setTheme(theme) {
    AppState.theme = theme;
    document.documentElement.dataset.theme = theme;
    document.getElementById('theme-toggle').innerHTML = theme === 'dark'
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    saveState();
}

// View mode switching
function setViewMode(mode) {
    AppState.viewMode = mode;
    document.body.className = `view-${mode}`;

    // Update view switcher buttons
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === mode);
    });

    saveState();
    render();
}

// Collection selection
function setActiveCollection(id) {
    AppState.activeCollection = id;
    AppState.activeView = null;  // Clear active view when switching collections
    saveState();
    renderCollectionsSidebar();
    renderViewsSidebar();
    render();
}

// Statistics dashboard
function renderStatsDashboard() {
    const stats = AppState.stats;
    if (!stats) return;

    const container = document.getElementById('stats-body');
    if (!container) return;

    // Summary grid
    const summaryHtml = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">${stats.total}</div>
                <div class="stat-label">Total</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.tag_count}</div>
                <div class="stat-label">Tags</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${Object.keys(stats.top_domains).length}</div>
                <div class="stat-label">Domains</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.starred}</div>
                <div class="stat-label">Starred</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.unread}</div>
                <div class="stat-label">Unread</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.broken}</div>
                <div class="stat-label">Broken</div>
            </div>
        </div>
    `;

    // Timeline chart
    const timelineData = Object.entries(stats.timeline || {}).slice(-12);
    const maxCount = Math.max(...timelineData.map(([,v]) => v), 1);
    const timelineHtml = timelineData.length > 0 ? `
        <div class="stats-section">
            <h3>Bookmarks Added Over Time</h3>
            <div class="chart-timeline">
                ${timelineData.map(([month, count]) => {
                    const height = Math.max(5, (count / maxCount) * 100);
                    return `<div class="chart-bar" style="height: ${height}%">
                        <div class="tooltip">${month}: ${count}</div>
                    </div>`;
                }).join('')}
            </div>
            <div class="chart-labels">
                <span>${timelineData[0]?.[0] || ''}</span>
                <span>${timelineData[timelineData.length-1]?.[0] || ''}</span>
            </div>
        </div>
    ` : '';

    // Top domains
    const domainsHtml = `
        <div class="stats-section">
            <h3>Top Domains</h3>
            <div class="stats-list">
                ${Object.entries(stats.top_domains).slice(0, 10).map(([domain, count]) => `
                    <div class="stats-list-item">
                        <span class="name">${escapeHtml(domain)}</span>
                        <span class="count">${count}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    // Media breakdown
    const mediaHtml = Object.keys(stats.media_breakdown || {}).length > 0 ? `
        <div class="stats-section">
            <h3>Media Types</h3>
            <div class="stats-list">
                ${Object.entries(stats.media_breakdown).map(([type, count]) => `
                    <div class="stats-list-item">
                        <span class="name">${escapeHtml(type)}</span>
                        <span class="count">${count}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    ` : '';

    container.innerHTML = summaryHtml + timelineHtml + domainsHtml + mediaHtml;
}

function toggleStatsDashboard() {
    const modal = document.getElementById('stats-modal');
    if (modal) {
        const isHidden = modal.hidden;
        modal.hidden = !isHidden;
        if (isHidden) renderStatsDashboard();
    }
}

// Keyboard shortcuts help
function renderShortcutsHelp() {
    const container = document.getElementById('shortcuts-body');
    if (!container) return;

    container.innerHTML = `
        <div class="shortcuts-grid">
            ${Object.entries(KEYBOARD_SHORTCUTS).map(([key, {desc}]) => `
                <div class="shortcut-item">
                    <span class="shortcut-key">${key === 'Enter' ? '↵' : key === 'Escape' ? 'Esc' : key}</span>
                    <span class="shortcut-desc">${desc}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function toggleShortcutsModal() {
    const modal = document.getElementById('shortcuts-modal');
    if (modal) {
        const isHidden = modal.hidden;
        modal.hidden = !isHidden;
        if (isHidden) renderShortcutsHelp();
    }
}

// Keyboard navigation
function navigateBookmarks(delta) {
    const items = document.querySelectorAll('.bookmark-card, .bookmark-list-item, .gallery-card, .bookmark-table tbody tr');
    if (items.length === 0) return;

    // Remove previous focus
    items.forEach(el => el.classList.remove('focused'));

    // Update index
    AppState.selectedIndex = Math.max(0, Math.min(items.length - 1, AppState.selectedIndex + delta));

    // Focus new item
    const item = items[AppState.selectedIndex];
    if (item) {
        item.classList.add('focused');
        item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        item.focus();
    }
}

function openSelectedBookmark() {
    const items = document.querySelectorAll('.bookmark-card, .bookmark-list-item, .gallery-card, .bookmark-table tbody tr');
    const item = items[AppState.selectedIndex];
    if (item && item.dataset.id) {
        showBookmarkDetail(item.dataset.id);
    }
}

function handleKeyboard(e) {
    // Ignore if typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        if (e.key === 'Escape') e.target.blur();
        return;
    }

    const shortcut = KEYBOARD_SHORTCUTS[e.key];
    if (!shortcut) return;

    e.preventDefault();

    switch (shortcut.action) {
        case 'next': navigateBookmarks(1); break;
        case 'prev': navigateBookmarks(-1); break;
        case 'search': document.getElementById('search-input').focus(); break;
        case 'open': openSelectedBookmark(); break;
        case 'close':
            hideModal();
            document.getElementById('stats-dashboard')?.setAttribute('hidden', '');
            document.getElementById('shortcuts-modal')?.setAttribute('hidden', '');
            break;
        case 'view-grid': setViewMode('grid'); break;
        case 'view-list': setViewMode('list'); break;
        case 'view-table': setViewMode('table'); break;
        case 'view-gallery': setViewMode('gallery'); break;
        case 'toggle-theme': setTheme(AppState.theme === 'dark' ? 'light' : 'dark'); break;
        case 'toggle-stats': toggleStatsDashboard(); break;
        case 'show-help': toggleShortcutsModal(); break;
        case 'col-all': setActiveCollection('all'); break;
        case 'col-unread': setActiveCollection('unread'); break;
        case 'col-starred': setActiveCollection('starred'); break;
        case 'col-queue': setActiveCollection('queue'); break;
        case 'col-popular': setActiveCollection('popular'); break;
        case 'col-media': setActiveCollection('media'); break;
    }
}

// Render all
function render() {
    renderBookmarkList();
    renderTagCloud();
    renderCollectionsSidebar();
}

// Event binding
function bindEvents() {
    // Search
    let searchTimeout;
    document.getElementById('search-input').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            AppState.searchQuery = e.target.value;
            render();
        }, 200);
    });

    // Sort
    document.getElementById('sort-select').addEventListener('change', (e) => {
        AppState.sortBy = e.target.value;
        saveState();
        render();
    });

    // Filters
    document.getElementById('filter-starred').addEventListener('change', (e) => {
        AppState.filterStarred = e.target.checked;
        saveState();
        render();
    });

    document.getElementById('filter-pinned').addEventListener('change', (e) => {
        AppState.filterPinned = e.target.checked;
        saveState();
        render();
    });

    // Tag cloud
    document.getElementById('tag-cloud').addEventListener('click', (e) => {
        const btn = e.target.closest('.tag-filter');
        if (btn) {
            const tag = btn.dataset.tag;
            if (AppState.selectedTags.has(tag)) {
                AppState.selectedTags.delete(tag);
            } else {
                AppState.selectedTags.add(tag);
            }
            saveState();
            render();
        }
    });

    // Clear filters
    document.getElementById('clear-filters').addEventListener('click', () => {
        AppState.selectedTags.clear();
        AppState.filterStarred = false;
        AppState.filterPinned = false;
        document.getElementById('filter-starred').checked = false;
        document.getElementById('filter-pinned').checked = false;
        saveState();
        render();
    });

    // Theme toggle
    document.getElementById('theme-toggle').addEventListener('click', () => {
        setTheme(AppState.theme === 'dark' ? 'light' : 'dark');
    });

    // Bookmark items (grid cards, list items, gallery cards)
    document.getElementById('bookmark-list').addEventListener('click', (e) => {
        const card = e.target.closest('.bookmark-card, .bookmark-list-item, .gallery-card');
        const row = e.target.closest('.bookmark-table tbody tr');
        const target = card || row;
        if (target && !e.target.closest('a')) {
            showBookmarkDetail(target.dataset.id);
        }

        // Table header sorting
        const th = e.target.closest('.bookmark-table th[data-sort]');
        if (th && th.classList.contains('sortable')) {
            const col = th.dataset.sort;
            if (AppState.tableSortColumn === col) {
                AppState.tableSortDirection = AppState.tableSortDirection === 'desc' ? 'asc' : 'desc';
            } else {
                AppState.tableSortColumn = col;
                AppState.tableSortDirection = 'desc';
            }
            saveState();
            render();
        }
    });

    // View switcher
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => setViewMode(btn.dataset.view));
    });

    // Collections sidebar
    const collectionsContainer = document.getElementById('collections-list');
    if (collectionsContainer) {
        collectionsContainer.addEventListener('click', (e) => {
            const item = e.target.closest('.collection-item');
            if (item) {
                setActiveCollection(item.dataset.collection);
            }
        });
    }

    // Views sidebar click handler
    const viewsContainer = document.getElementById('views-list');
    if (viewsContainer) {
        viewsContainer.addEventListener('click', (e) => {
            const item = e.target.closest('.view-item');
            if (item) {
                setActiveView(item.dataset.view);
            }
        });
    }

    // Stats toggle
    const statsToggle = document.getElementById('stats-toggle');
    if (statsToggle) {
        statsToggle.addEventListener('click', toggleStatsDashboard);
    }

    // Stats dashboard close
    const statsClose = document.getElementById('stats-close');
    if (statsClose) {
        statsClose.addEventListener('click', () => {
            document.getElementById('stats-modal').hidden = true;
        });
    }
    document.getElementById('stats-modal')?.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) {
            document.getElementById('stats-modal').hidden = true;
        }
    });

    // Shortcuts toggle
    const shortcutsToggle = document.getElementById('shortcuts-toggle');
    if (shortcutsToggle) {
        shortcutsToggle.addEventListener('click', toggleShortcutsModal);
    }

    // Shortcuts modal close
    const shortcutsClose = document.getElementById('shortcuts-close');
    if (shortcutsClose) {
        shortcutsClose.addEventListener('click', () => {
            document.getElementById('shortcuts-modal').hidden = true;
        });
    }
    document.getElementById('shortcuts-modal')?.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) {
            document.getElementById('shortcuts-modal').hidden = true;
        }
    });

    // Modal
    document.getElementById('modal-close').addEventListener('click', hideModal);
    document.getElementById('bookmark-modal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) hideModal();
    });

    // Keyboard handler (replaces simple escape handler)
    document.addEventListener('keydown', handleKeyboard);

    // Mobile sidebar
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.hidden = !sidebar.classList.contains('open');
        });

        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.hidden = true;
        });
    }
}

// Initialize
function init() {
    // Load data
    const dataEl = document.getElementById('bookmark-data');
    const data = JSON.parse(dataEl.textContent);
    AppState.bookmarks = data.bookmarks;
    AppState.tags = data.tags;
    AppState.stats = data.stats || null;
    AppState.views = data.views || {};

    // Build search index
    AppState.searchIndex = new SearchIndex(AppState.bookmarks);

    // Load saved state
    loadState();

    // Apply state to UI
    document.getElementById('sort-select').value = AppState.sortBy;
    document.getElementById('filter-starred').checked = AppState.filterStarred;
    document.getElementById('filter-pinned').checked = AppState.filterPinned;
    setTheme(AppState.theme);

    // Apply view mode
    setViewMode(AppState.viewMode, false);

    // Apply active collection
    setActiveCollection(AppState.activeCollection, false);

    // Render views sidebar
    renderViewsSidebar();

    // Bind events and render
    bindEvents();
    render();
}

// Start
document.addEventListener('DOMContentLoaded', init);
'''


def export_html_app(bookmarks: List[Bookmark], path: Path, views: Optional[dict] = None) -> None:
    """
    Export bookmarks as interactive HTML application.

    Creates a single self-contained HTML file with embedded CSS, JavaScript,
    and JSON data that works offline as an interactive bookmark viewer.

    Args:
        bookmarks: List of bookmarks to export
        path: Output file path
        views: Optional dict of view definitions with format:
               {"view_name": {"description": "...", "bookmark_ids": [1, 2, 3]}}
    """
    # Serialize data
    serialized_bookmarks = [_serialize_bookmark_for_app(b) for b in bookmarks]
    data = {
        "metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "bookmark_count": len(bookmarks)
        },
        "bookmarks": serialized_bookmarks,
        "tags": _get_tag_stats(bookmarks),
        "stats": _get_export_stats(bookmarks),
        "views": views or {}
    }

    json_data = json.dumps(data, ensure_ascii=False)

    # Generate HTML
    html = f'''<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bookmark Viewer</title>
    <style>{_HTML_APP_CSS}</style>
</head>
<body class="view-grid">
    <div class="app-container">
        <header id="app-header">
            <button id="sidebar-toggle" aria-label="Toggle sidebar">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 12h18M3 6h18M3 18h18"/>
                </svg>
            </button>
            <div class="header-brand">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
                </svg>
                <span>Bookmarks</span>
            </div>
            <div class="search-container">
                <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                </svg>
                <input type="search" id="search-input" placeholder="Search bookmarks... (press /)" autocomplete="off">
            </div>
            <div class="view-switcher">
                <button class="view-btn active" data-view="grid" aria-label="Grid view" title="Grid view (g)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                        <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                    </svg>
                </button>
                <button class="view-btn" data-view="list" aria-label="List view" title="List view (l)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>
                        <line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>
                        <line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
                    </svg>
                </button>
                <button class="view-btn" data-view="table" aria-label="Table view" title="Table view (t)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                        <line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/>
                        <line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>
                    </svg>
                </button>
                <button class="view-btn" data-view="gallery" aria-label="Gallery view" title="Gallery view (m)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                        <circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
                    </svg>
                </button>
            </div>
            <div class="header-actions">
                <span id="bookmark-count" class="bookmark-count">{len(bookmarks)} bookmarks</span>
                <button id="stats-toggle" aria-label="Show statistics" title="Statistics (s)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>
                        <line x1="6" y1="20" x2="6" y2="14"/>
                    </svg>
                </button>
                <button id="shortcuts-toggle" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="2" y="4" width="20" height="16" rx="2" ry="2"/>
                        <line x1="6" y1="8" x2="6.01" y2="8"/><line x1="10" y1="8" x2="10.01" y2="8"/>
                        <line x1="14" y1="8" x2="14.01" y2="8"/><line x1="18" y1="8" x2="18.01" y2="8"/>
                        <line x1="8" y1="12" x2="8.01" y2="12"/><line x1="12" y1="12" x2="12.01" y2="12"/>
                        <line x1="16" y1="12" x2="16.01" y2="12"/>
                        <line x1="7" y1="16" x2="17" y2="16"/>
                    </svg>
                </button>
                <button id="theme-toggle" aria-label="Toggle theme" title="Toggle theme (d)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                    </svg>
                </button>
            </div>
        </header>

        <div id="sidebar-overlay" class="sidebar-overlay" hidden></div>

        <aside id="sidebar">
            <div class="sidebar-section collections-section">
                <h3>Collections</h3>
                <div id="collections-list">
                    <!-- Rendered by JavaScript -->
                </div>
            </div>

            <div class="sidebar-section views-section" id="views-section" hidden>
                <h3>Curated Views</h3>
                <div id="views-list">
                    <!-- Rendered by JavaScript -->
                </div>
            </div>

            <div class="sidebar-section">
                <h3>Sort By</h3>
                <select id="sort-select">
                    <option value="added-desc">Date Added (newest)</option>
                    <option value="added-asc">Date Added (oldest)</option>
                    <option value="title-asc">Title (A-Z)</option>
                    <option value="title-desc">Title (Z-A)</option>
                    <option value="visits-desc">Most Visited</option>
                    <option value="visited-desc">Last Visited</option>
                    <option value="stars-desc">Most Stars</option>
                </select>
            </div>

            <div class="sidebar-section">
                <h3>Filters</h3>
                <div class="filter-checkboxes">
                    <label>
                        <input type="checkbox" id="filter-starred">
                        <span>★ Starred only</span>
                    </label>
                    <label>
                        <input type="checkbox" id="filter-pinned">
                        <span>📌 Pinned only</span>
                    </label>
                </div>
            </div>

            <div class="sidebar-section">
                <h3>Tags</h3>
                <div id="tag-cloud"></div>
                <button id="clear-filters" class="clear-filters">Clear all filters</button>
            </div>
        </aside>

        <main id="main-content">
            <div id="bookmark-list"></div>
        </main>
    </div>

    <div id="bookmark-modal" class="modal" hidden>
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modal-title">Bookmark Details</h2>
                <button id="modal-close" class="modal-close">&times;</button>
            </div>
            <div id="modal-body"></div>
            <div class="modal-actions">
                <a id="modal-open-link" href="#" target="_blank" rel="noopener" class="btn btn-primary">
                    Open Link →
                </a>
                <button onclick="hideModal()" class="btn btn-secondary">Close</button>
            </div>
        </div>
    </div>

    <div id="stats-modal" class="modal" hidden>
        <div class="modal-content stats-dashboard">
            <div class="modal-header">
                <h2>Statistics</h2>
                <button id="stats-close" class="modal-close">&times;</button>
            </div>
            <div id="stats-body">
                <!-- Rendered by JavaScript -->
            </div>
        </div>
    </div>

    <div id="shortcuts-modal" class="modal" hidden>
        <div class="modal-content shortcuts-content">
            <div class="modal-header">
                <h2>Keyboard Shortcuts</h2>
                <button id="shortcuts-close" class="modal-close">&times;</button>
            </div>
            <div id="shortcuts-body">
                <!-- Rendered by JavaScript -->
            </div>
        </div>
    </div>

    <script id="bookmark-data" type="application/json">{json_data}</script>
    <script>{_HTML_APP_JS}</script>
</body>
</html>'''

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


# =============================================================================
# Preservation HTML Export Format
# =============================================================================

_PRESERVATION_HTML_CSS = """
:root {
    --bg: #fafafa;
    --text: #333;
    --text-secondary: #666;
    --border: #e0e0e0;
    --card-bg: #fff;
    --link: #0066cc;
    --accent: #4a90d9;
    --tag-bg: #f0f4f8;
    --success: #4caf50;
    --warning: #ff9800;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg: #1a1a2e;
        --text: #e0e0e0;
        --text-secondary: #a0a0a0;
        --border: #3a3a4a;
        --card-bg: #252540;
        --link: #6ab0ff;
        --accent: #6ab0ff;
        --tag-bg: #2a2a3e;
        --success: #66bb6a;
        --warning: #ffb74d;
    }
}

* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    margin: 0;
    padding: 0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

header {
    text-align: center;
    padding: 40px 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 40px;
}

header h1 {
    margin: 0 0 10px;
    font-size: 2.5em;
    font-weight: 300;
}

header .subtitle {
    color: var(--text-secondary);
    font-size: 1.1em;
}

header .stats {
    margin-top: 20px;
    display: flex;
    justify-content: center;
    gap: 30px;
    flex-wrap: wrap;
}

header .stat {
    text-align: center;
}

header .stat-value {
    font-size: 2em;
    font-weight: 600;
    color: var(--accent);
}

header .stat-label {
    font-size: 0.9em;
    color: var(--text-secondary);
}

.bookmark {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 30px;
    overflow: hidden;
}

.bookmark-header {
    padding: 20px;
    border-bottom: 1px solid var(--border);
}

.bookmark-title {
    font-size: 1.4em;
    font-weight: 600;
    margin: 0 0 8px;
}

.bookmark-title a {
    color: var(--link);
    text-decoration: none;
}

.bookmark-title a:hover {
    text-decoration: underline;
}

.bookmark-url {
    font-size: 0.85em;
    color: var(--text-secondary);
    word-break: break-all;
}

.bookmark-meta {
    margin-top: 12px;
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    font-size: 0.85em;
    color: var(--text-secondary);
}

.bookmark-meta .meta-item {
    display: flex;
    align-items: center;
    gap: 5px;
}

.bookmark-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
}

.tag {
    background: var(--tag-bg);
    color: var(--text);
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 0.8em;
}

.bookmark-body {
    padding: 20px;
}

.bookmark-description {
    margin-bottom: 20px;
    color: var(--text-secondary);
    font-style: italic;
}

.preservation-section {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid var(--border);
}

.preservation-section h4 {
    margin: 0 0 15px;
    color: var(--text-secondary);
    font-size: 0.9em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.thumbnail {
    max-width: 100%;
    border-radius: 8px;
    margin-bottom: 15px;
}

.transcript, .extracted-text {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 15px;
    max-height: 400px;
    overflow-y: auto;
    font-size: 0.9em;
    line-height: 1.8;
    white-space: pre-wrap;
}

.preservation-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: var(--success);
    color: white;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.75em;
    font-weight: 500;
}

.content-cached {
    margin-top: 20px;
}

.cached-markdown {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 15px;
    max-height: 500px;
    overflow-y: auto;
}

footer {
    text-align: center;
    padding: 40px 20px;
    margin-top: 40px;
    border-top: 1px solid var(--border);
    color: var(--text-secondary);
    font-size: 0.9em;
}

.noscript-note {
    background: var(--tag-bg);
    border: 1px solid var(--border);
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 30px;
    text-align: center;
}

@media (max-width: 600px) {
    .container { padding: 10px; }
    header { padding: 20px 10px; }
    header h1 { font-size: 1.8em; }
    .bookmark-header, .bookmark-body { padding: 15px; }
}
"""

def export_preservation_html(bookmarks: List[Bookmark], path: Path, db=None) -> None:
    """
    Export bookmarks as self-contained HTML with embedded preservation data.

    Creates a single HTML file with embedded thumbnails, transcripts,
    and extracted text. Works offline and without JavaScript.

    This is a simple preservation export format, not the full Long Echo
    archive system (see github.com/queelius/longecho for that).

    Args:
        bookmarks: List of bookmarks to export
        path: Output file path
        db: Database instance (optional, for accessing preservation data)
    """
    from datetime import datetime, timezone

    # Build HTML content
    html_parts = []

    # Calculate stats
    preserved_count = 0
    with_thumbnail = 0
    with_transcript = 0
    with_extracted = 0

    # Build bookmark cards
    bookmark_cards = []
    for b in bookmarks:
        preservation_data = None

        # Try to get preservation data if db is available
        if db:
            try:
                from .models import ContentCache
                with db.session() as session:
                    cache = session.query(ContentCache).filter_by(bookmark_id=b.id).first()
                    if cache and cache.preservation_type:
                        preserved_count += 1
                        preservation_data = {
                            'type': cache.preservation_type,
                            'thumbnail_data': cache.thumbnail_data,
                            'thumbnail_mime': cache.thumbnail_mime,
                            'transcript_text': cache.transcript_text,
                            'extracted_text': cache.extracted_text,
                            'preserved_at': cache.preserved_at,
                            'markdown_content': cache.markdown_content,
                        }
                        if cache.thumbnail_data:
                            with_thumbnail += 1
                        if cache.transcript_text:
                            with_transcript += 1
                        if cache.extracted_text:
                            with_extracted += 1
            except Exception:
                pass

        # Build card HTML
        card = _build_long_echo_card(b, preservation_data)
        bookmark_cards.append(card)

    # Generate full HTML
    export_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bookmark Archive</title>
    <meta name="description" content="Self-contained bookmark archive with preserved content">
    <style>{_PRESERVATION_HTML_CSS}</style>
</head>
<body>
    <noscript>
        <div class="noscript-note">
            This archive works without JavaScript. All content is embedded directly in the HTML.
        </div>
    </noscript>

    <header>
        <h1>Bookmark Archive</h1>
        <p class="subtitle">Preserved bookmarks with embedded content</p>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{len(bookmarks)}</div>
                <div class="stat-label">Bookmarks</div>
            </div>
            <div class="stat">
                <div class="stat-value">{preserved_count}</div>
                <div class="stat-label">Preserved</div>
            </div>
            <div class="stat">
                <div class="stat-value">{with_thumbnail}</div>
                <div class="stat-label">Thumbnails</div>
            </div>
            <div class="stat">
                <div class="stat-value">{with_transcript + with_extracted}</div>
                <div class="stat-label">Text Extracts</div>
            </div>
        </div>
    </header>

    <div class="container">
        {"".join(bookmark_cards)}
    </div>

    <footer>
        <p>Exported: {export_date}</p>
        <p>Generated by <a href="https://github.com/queelius/btk">BTK - Bookmark Toolkit</a></p>
    </footer>
</body>
</html>'''

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def _build_long_echo_card(bookmark: Bookmark, preservation: Optional[dict] = None) -> str:
    """Build HTML card for a single bookmark."""

    # Tags
    tags_html = ""
    if bookmark.tags:
        tag_spans = [f'<span class="tag">{t.name}</span>' for t in bookmark.tags]
        tags_html = f'<div class="bookmark-tags">{" ".join(tag_spans)}</div>'

    # Meta info
    added_str = bookmark.added.strftime("%Y-%m-%d") if bookmark.added else "Unknown"
    stars = "★" if bookmark.stars else ""

    meta_items = [f'<span class="meta-item">Added: {added_str}</span>']
    if bookmark.visit_count:
        meta_items.append(f'<span class="meta-item">Visits: {bookmark.visit_count}</span>')
    if stars:
        meta_items.append(f'<span class="meta-item">{stars} Starred</span>')

    # Description
    desc_html = ""
    if bookmark.description:
        desc_html = f'<div class="bookmark-description">{_escape_html(bookmark.description)}</div>'

    # Preservation content
    preservation_html = ""
    if preservation:
        parts = []

        # Preservation badge
        ptype = preservation.get('type', 'unknown')
        preserved_at = preservation.get('preserved_at')
        preserved_date = preserved_at.strftime("%Y-%m-%d") if preserved_at else ""
        parts.append(f'<span class="preservation-badge">Preserved ({ptype}) {preserved_date}</span>')

        # Thumbnail
        if preservation.get('thumbnail_data'):
            mime = preservation.get('thumbnail_mime', 'image/jpeg')
            b64 = base64.b64encode(preservation['thumbnail_data']).decode('ascii')
            parts.append(f'<img class="thumbnail" src="data:{mime};base64,{b64}" alt="Thumbnail">')

        # Transcript
        if preservation.get('transcript_text'):
            text = _escape_html(preservation['transcript_text'])
            # Truncate very long transcripts for display
            if len(text) > 5000:
                text = text[:5000] + "... [truncated]"
            parts.append(f'''
                <div class="preservation-section">
                    <h4>Transcript</h4>
                    <div class="transcript">{text}</div>
                </div>
            ''')

        # Extracted text (PDF, etc.)
        if preservation.get('extracted_text'):
            text = _escape_html(preservation['extracted_text'])
            if len(text) > 5000:
                text = text[:5000] + "... [truncated]"
            parts.append(f'''
                <div class="preservation-section">
                    <h4>Extracted Content</h4>
                    <div class="extracted-text">{text}</div>
                </div>
            ''')

        # Cached markdown content (from regular content caching)
        if preservation.get('markdown_content') and not preservation.get('transcript_text') and not preservation.get('extracted_text'):
            # Only show if we don't have transcript/extracted text
            text = _escape_html(preservation['markdown_content'])
            if len(text) > 3000:
                text = text[:3000] + "... [truncated]"
            parts.append(f'''
                <div class="content-cached">
                    <h4>Cached Content</h4>
                    <div class="cached-markdown">{text}</div>
                </div>
            ''')

        if parts:
            preservation_html = f'<div class="bookmark-body">{"".join(parts)}</div>'

    return f'''
    <article class="bookmark">
        <div class="bookmark-header">
            <h2 class="bookmark-title">
                <a href="{_escape_html(bookmark.url)}" target="_blank" rel="noopener">{_escape_html(bookmark.title)}</a>
            </h2>
            <div class="bookmark-url">{_escape_html(bookmark.url)}</div>
            <div class="bookmark-meta">{" ".join(meta_items)}</div>
            {tags_html}
            {desc_html}
        </div>
        {preservation_html}
    </article>
    '''


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def export_echo(bookmarks: List[Bookmark], path: Path, db=None) -> None:
    """
    Export bookmarks to ECHO-compliant directory structure.

    Creates:
    - README.md explaining the archive
    - bookmarks.db (SQLite database copy, if db provided)
    - bookmarks.jsonl (one bookmark per line)
    - by-tag/ directory with markdown files organized by tag hierarchy

    Args:
        bookmarks: List of bookmarks to export
        path: Output directory path
        db: Database instance (for copying the SQLite database)
    """
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy database if available
    db_included = False
    if db and hasattr(db, 'path') and db.path and Path(db.path).exists():
        shutil.copy2(db.path, output_dir / "bookmarks.db")
        db_included = True

    # Export JSONL
    jsonl_path = output_dir / "bookmarks.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for b in bookmarks:
            record = {
                "id": b.id,
                "unique_id": b.unique_id,
                "url": b.url,
                "title": b.title,
                "description": b.description or "",
                "tags": [t.name for t in b.tags],
                "stars": b.stars,
                "archived": b.archived,
                "visit_count": b.visit_count,
                "added": b.added.isoformat() if b.added else None,
                "last_visited": b.last_visited.isoformat() if b.last_visited else None,
            }
            # Add media fields if present
            if b.media_type:
                record["media"] = {
                    "type": b.media_type,
                    "source": b.media_source,
                    "id": b.media_id,
                    "author": b.author_name,
                }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Export by-tag markdown files
    by_tag_dir = output_dir / "by-tag"
    by_tag_dir.mkdir(exist_ok=True)

    # Build tag hierarchy
    tag_bookmarks = {}
    for b in bookmarks:
        if b.tags:
            for tag in b.tags:
                if tag.name not in tag_bookmarks:
                    tag_bookmarks[tag.name] = []
                tag_bookmarks[tag.name].append(b)

    # Create markdown files for each tag
    for tag_name, tag_items in sorted(tag_bookmarks.items()):
        # Create directory structure for hierarchical tags
        parts = tag_name.split("/")
        if len(parts) > 1:
            tag_dir = by_tag_dir / "/".join(parts[:-1])
            tag_dir.mkdir(parents=True, exist_ok=True)
            md_path = tag_dir / f"{parts[-1]}.md"
        else:
            md_path = by_tag_dir / f"{tag_name}.md"

        lines = [f"# {tag_name}", "", f"Bookmarks tagged with `{tag_name}`", ""]

        for b in sorted(tag_items, key=lambda x: x.added or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
            added_str = b.added.strftime("%Y-%m-%d") if b.added else ""
            stars = " ⭐" if b.stars else ""
            lines.append(f"## [{b.title}]({b.url}){stars}")
            lines.append("")
            if added_str:
                lines.append(f"Added: {added_str}")
            if b.description:
                lines.append("")
                lines.append(b.description)
            lines.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # Generate README
    readme_content = _generate_echo_readme(
        total_bookmarks=len(bookmarks),
        total_tags=len(tag_bookmarks),
        db_included=db_included
    )
    (output_dir / "README.md").write_text(readme_content, encoding="utf-8")


def _generate_echo_readme(total_bookmarks: int, total_tags: int, db_included: bool) -> str:
    """Generate ECHO-compliant README for bookmark archive."""
    db_section = ""
    if db_included:
        db_section = """
### SQLite Database

The `bookmarks.db` file is a copy of the source database.

Key tables:
- `bookmarks`: id, url, title, description, added, stars, visit_count, ...
- `tags`: id, name, description, color
- `bookmark_tags`: bookmark_id, tag_id (many-to-many)

Query examples:
```sql
-- List starred bookmarks
sqlite3 bookmarks.db "SELECT title, url FROM bookmarks WHERE stars = 1"

-- List bookmarks by tag
sqlite3 bookmarks.db "SELECT b.title, b.url FROM bookmarks b
  JOIN bookmark_tags bt ON b.id = bt.bookmark_id
  JOIN tags t ON bt.tag_id = t.id
  WHERE t.name = 'programming'"
```
"""

    return f"""# Bookmark Archive

Personal bookmark collection.

Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
Total bookmarks: {total_bookmarks}
Total tags: {total_tags}

## Format

This is an ECHO-compliant archive. All data is in durable, open formats.

### Directory Structure

```
├── README.md            # This file
├── bookmarks.jsonl      # One bookmark per line
{"├── bookmarks.db        # SQLite database" if db_included else ""}
└── by-tag/              # Markdown files by tag
    ├── programming/
    │   └── python.md
    └── ...
```

### bookmarks.jsonl

Each line is a JSON object:

```json
{{"id": 1, "url": "https://...", "title": "...", "tags": ["tag1", "tag2"], ...}}
```

Fields:
- `id`: Internal ID
- `unique_id`: 8-char hash for external references
- `url`: Bookmark URL
- `title`: Page title
- `description`: User description
- `tags`: Array of tag names
- `stars`: Boolean (starred/favorite)
- `visit_count`: Number of visits
- `added`: ISO timestamp when added
- `media`: Optional media info (type, source, author)
{db_section}
### by-tag/ Directory

Markdown files organized by tag hierarchy. Each file lists bookmarks
with that tag, sorted by date.

## Exploring

1. **Browse tags**: Look in `by-tag/` directory
2. **Search**: `grep -r "search term" by-tag/`
3. **Parse**: Process `bookmarks.jsonl` with any JSON tool
4. **Query**: Use SQLite browser on `bookmarks.db` (if included)

## About ECHO

ECHO is a philosophy for durable personal data archives.
Learn more: https://github.com/alextowell/longecho

---

*Generated by btk (Bookmark Toolkit)*
"""