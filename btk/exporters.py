"""
Simplified exporters for BTK.

Provides clean, composable export functions for various bookmark formats.
"""
import html as html_module
import json
import csv
import base64
import shutil
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timezone

from btk.models import Bookmark


def export_file(bookmarks: List[Bookmark], path: Path, format: str, views: Optional[dict] = None, db=None,
                embed: bool = True, include_dbs: Optional[Dict[str, List[Bookmark]]] = None) -> None:
    """
    Export bookmarks to a file.

    Args:
        bookmarks: List of bookmarks to export
        path: Output file path
        format: Export format (json, csv, html, markdown, long-echo)
        views: Optional dict of view definitions for html-app format
        db: Optional database instance for long-echo format
        embed: Whether to embed assets in a single HTML file (html-app only)
        include_dbs: Additional named databases to include (html-app only)
    """
    # Ensure parent directory exists
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # html-app is handled by the btk.html_app module
    if format == "html-app":
        from btk.html_app import export_html_app
        export_html_app(bookmarks, path, views=views, embed=embed, include_dbs=include_dbs)
        return

    exporters = {
        "json": export_json,
        "json-full": export_json_full,
        "csv": export_csv,
        "html": export_html,
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

    if format in ("preservation-html", "json-full"):
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
                lines.append(f'{indent_str}<DT><H3>{html_module.escape(folder_name)}</H3>')
                lines.append(f'{indent_str}<DL><p>')

                # Write bookmarks in this folder
                for b in folder_data['__bookmarks__']:
                    add_date = int(b.added.timestamp()) if b.added else ""
                    lines.append(f'{indent_str}    <DT><A HREF="{html_module.escape(b.url)}" ADD_DATE="{add_date}">{html_module.escape(b.title or "")}</A>')
                    if b.description:
                        lines.append(f'{indent_str}    <DD>{html_module.escape(b.description)}')

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
                lines.append(f'        <DT><A HREF="{html_module.escape(b.url)}" ADD_DATE="{add_date}">{html_module.escape(b.title or "")}</A>')
                if b.description:
                    lines.append(f'        <DD>{html_module.escape(b.description)}')

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
            lines.append(f'    <DT><H3>{html_module.escape(tag_name)}</H3>')
            lines.append('    <DL><p>')

            for b in tag_items:
                add_date = int(b.added.timestamp()) if b.added else ""
                lines.append(f'        <DT><A HREF="{html_module.escape(b.url)}" ADD_DATE="{add_date}">{html_module.escape(b.title or "")}</A>')
                if b.description:
                    lines.append(f'        <DD>{html_module.escape(b.description)}')

            lines.append('    </DL><p>')

        # Export untagged bookmarks
        if untagged:
            lines.append('    <DT><H3>Untagged</H3>')
            lines.append('    <DL><p>')

            for b in untagged:
                add_date = int(b.added.timestamp()) if b.added else ""
                lines.append(f'        <DT><A HREF="{html_module.escape(b.url)}" ADD_DATE="{add_date}">{html_module.escape(b.title or "")}</A>')
                if b.description:
                    lines.append(f'        <DD>{html_module.escape(b.description)}')

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
            lines.append(f'    <DT><A HREF="{html_module.escape(b.url)}" ADD_DATE="{added_ts}">{html_module.escape(title)}</A>')
            if b.description:
                lines.append(f'    <DD>{html_module.escape(b.description)}')
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
# HTML App Export — moved to btk/html_app/
# =============================================================================

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
        tag_spans = [f'<span class="tag">{html_module.escape(t.name)}</span>' for t in bookmark.tags]
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
        desc_html = f'<div class="bookmark-description">{html_module.escape(bookmark.description or "")}</div>'

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
            text = html_module.escape(preservation['transcript_text'])
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
            text = html_module.escape(preservation['extracted_text'])
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
            text = html_module.escape(preservation['markdown_content'])
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
                <a href="{html_module.escape(bookmark.url)}" target="_blank" rel="noopener">{html_module.escape(bookmark.title or "")}</a>
            </h2>
            <div class="bookmark-url">{html_module.escape(bookmark.url)}</div>
            <div class="bookmark-meta">{" ".join(meta_items)}</div>
            {tags_html}
            {desc_html}
        </div>
        {preservation_html}
    </article>
    '''


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