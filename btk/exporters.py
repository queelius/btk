"""
Simplified exporters for BTK.

Provides clean, composable export functions for various bookmark formats.
"""
import json
import csv
from pathlib import Path
from typing import List
from datetime import datetime

from btk.models import Bookmark


def export_file(bookmarks: List[Bookmark], path: Path, format: str) -> None:
    """
    Export bookmarks to a file.

    Args:
        bookmarks: List of bookmarks to export
        path: Output file path
        format: Export format (json, csv, html, markdown)
    """
    exporters = {
        "json": export_json,
        "csv": export_csv,
        "html": export_html,
        "markdown": export_markdown,
        "text": export_text,
    }

    exporter = exporters.get(format)
    if not exporter:
        raise ValueError(f"Unknown format: {format}")

    # Ensure parent directory exists
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    exporter(bookmarks, path)


def export_json(bookmarks: List[Bookmark], path: Path) -> None:
    """Export bookmarks to JSON."""
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
    from pathlib import Path

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

    else:
        # Plain text - just URLs
        return '\n'.join(b.url for b in bookmarks)