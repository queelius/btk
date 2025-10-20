#!/usr/bin/env python3
"""
BTK - Bookmark Toolkit

A clean, composable command-line interface for bookmark management.
Follows Unix philosophy: do one thing well, compose with pipes.
"""
import sys
import argparse
import json
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn

from btk.config import init_config, get_config
from btk.db import get_db
from btk.models import Bookmark

logger = logging.getLogger(__name__)


console = Console()


def format_bookmark(bookmark: Bookmark, format: str = "plain") -> str:
    """Format a bookmark for output."""
    if format == "json":
        return json.dumps({
            "id": bookmark.id,
            "url": bookmark.url,
            "title": bookmark.title,
            "tags": [t.name for t in bookmark.tags],
            "stars": bookmark.stars,
            "visits": bookmark.visit_count,
            "added": bookmark.added.isoformat() if bookmark.added else None,
        })
    elif format == "csv":
        tags = ",".join(t.name for t in bookmark.tags)
        return f"{bookmark.id},{bookmark.url},{bookmark.title},{tags},{bookmark.stars},{bookmark.visit_count}"
    elif format == "url":
        return bookmark.url
    else:  # plain
        tags = " ".join(f"#{t.name}" for t in bookmark.tags)
        star = "★" if bookmark.stars else ""
        return f"[{bookmark.id}] {star} {bookmark.title}\n    {bookmark.url}\n    {tags}"


def output_bookmarks(bookmarks: List[Bookmark], format: str = "table"):
    """Output bookmarks in the specified format."""
    config = get_config()

    if format == "table":
        table = Table(title="Bookmarks")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("URL", style="blue")
        table.add_column("Tags", style="yellow")
        table.add_column("★", style="red")
        table.add_column("Visits", style="magenta")

        for bookmark in bookmarks:
            tags = ", ".join(t.name for t in bookmark.tags)
            star = "★" if bookmark.stars else ""
            table.add_row(
                str(bookmark.id),
                bookmark.title[:50],
                bookmark.url[:50],
                tags[:30],
                star,
                str(bookmark.visit_count)
            )

        console.print(table)
    elif format == "json":
        data = [{
            "id": b.id,
            "url": b.url,
            "title": b.title,
            "tags": [t.name for t in b.tags],
            "stars": b.stars,
            "visits": b.visit_count,
            "added": b.added.isoformat() if b.added else None,
        } for b in bookmarks]
        print(json.dumps(data, indent=2 if config.export_pretty else None))
    elif format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(["id", "url", "title", "tags", "stars", "visits"])
        for b in bookmarks:
            tags = ",".join(t.name for t in b.tags)
            writer.writerow([b.id, b.url, b.title, tags, b.stars, b.visit_count])
    elif format == "urls":
        for b in bookmarks:
            print(b.url)
    elif format == "details":
        from rich.panel import Panel
        from rich.table import Table as RichTable

        for b in bookmarks:
            # Create a detailed view
            details = RichTable(show_header=False, box=None)
            details.add_column("Field", style="cyan bold")
            details.add_column("Value", style="white")

            details.add_row("ID", str(b.id))
            details.add_row("Unique ID", b.unique_id)
            details.add_row("URL", b.url)
            details.add_row("Title", b.title)
            details.add_row("Description", b.description or "(none)")
            details.add_row("Tags", ", ".join(t.name for t in b.tags) or "(none)")
            details.add_row("Starred", "★ Yes" if b.stars else "No")
            details.add_row("Pinned", "📌 Yes" if b.pinned else "No")
            details.add_row("Archived", "📦 Yes" if b.archived else "No")
            details.add_row("Visit Count", str(b.visit_count))
            details.add_row("Added", b.added.strftime("%Y-%m-%d %H:%M:%S") if b.added else "(unknown)")
            details.add_row("Last Visited", b.last_visited.strftime("%Y-%m-%d %H:%M:%S") if b.last_visited else "(never)")
            details.add_row("Reachable", "✓ Yes" if b.reachable else "✗ No" if b.reachable is False else "? Unknown")
            details.add_row("Favicon", "Yes" if b.favicon_data else "No")

            # Extra data if present
            if b.extra_data:
                details.add_row("Extra Data", json.dumps(b.extra_data, indent=2))

            panel = Panel(details, title=f"Bookmark #{b.id}", border_style="blue")
            console.print(panel)
            print()
    else:  # plain
        for b in bookmarks:
            print(format_bookmark(b, "plain"))
            print()


def cmd_add(args):
    """Add a new bookmark."""
    db = get_db(args.db)

    # Parse tags
    tags = args.tags.split(",") if args.tags else []

    # Add bookmark
    bookmark = db.add(
        url=args.url,
        title=args.title,
        description=args.description,
        tags=tags,
        stars=args.star
    )

    if args.quiet:
        print(bookmark.id)
    else:
        output_bookmarks([bookmark], args.output)


def build_filters(args):
    """Build filter dict from command args. Reusable across commands."""
    filters = {}
    if hasattr(args, 'starred') and args.starred:
        filters['starred'] = True
    if hasattr(args, 'archived') and args.archived:
        filters['archived'] = True
    if hasattr(args, 'unarchived') and args.unarchived:
        filters['archived'] = False
    if hasattr(args, 'pinned') and args.pinned:
        filters['pinned'] = True
    if hasattr(args, 'tags') and args.tags:
        filters['tags'] = args.tags.split(',')
    if hasattr(args, 'untagged') and args.untagged:
        filters['untagged'] = True

    # By default, exclude archived unless explicitly requested
    if 'archived' not in filters and not (hasattr(args, 'include_archived') and args.include_archived):
        filters['archived'] = False

    return filters


def cmd_list(args):
    """List bookmarks."""
    db = get_db(args.db)

    # By default, exclude archived bookmarks
    exclude_archived = not (hasattr(args, 'include_archived') and args.include_archived)

    bookmarks = db.list(
        limit=args.limit,
        offset=args.offset,
        order_by=args.sort,
        exclude_archived=exclude_archived
    )

    output_bookmarks(bookmarks, args.output)


def cmd_search(args):
    """Search bookmarks."""
    db = get_db(args.db)

    filters = build_filters(args)
    bookmarks = db.search(
        args.query if hasattr(args, 'query') else None,
        in_content=args.in_content if hasattr(args, 'in_content') else False,
        **filters
    )

    if args.limit:
        bookmarks = bookmarks[:args.limit]

    output_bookmarks(bookmarks, args.output)


def cmd_get(args):
    """Get a specific bookmark."""
    db = get_db(args.db)

    # Try to parse as ID first, then as unique_id
    try:
        bookmark = db.get(id=int(args.id))
    except ValueError:
        bookmark = db.get(unique_id=args.id)

    if bookmark:
        format = "details" if args.details else args.output
        output_bookmarks([bookmark], format)
    else:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)


def cmd_update(args):
    """Update a bookmark."""
    db = get_db(args.db)

    # Get current bookmark to support adding/removing tags
    bookmark = db.get(int(args.id))
    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    updates = {}
    if args.title:
        updates["title"] = args.title
    if args.description:
        updates["description"] = args.description

    # Handle tags: either full replacement or add/remove operations
    if args.tags:
        updates["tags"] = args.tags.split(",")
    elif args.add_tags or args.remove_tags:
        existing_tags = [t.name for t in bookmark.tags]
        new_tags = set(existing_tags)

        if args.add_tags:
            new_tags.update(args.add_tags.split(","))

        if args.remove_tags:
            tags_to_remove = set(args.remove_tags.split(","))
            new_tags -= tags_to_remove

        updates["tags"] = list(new_tags)

    # Boolean flags
    if args.starred is not None:
        updates["stars"] = args.starred
    if args.archived is not None:
        updates["archived"] = args.archived
    if args.pinned is not None:
        updates["pinned"] = args.pinned
    if args.url:
        updates["url"] = args.url

    success = db.update(int(args.id), **updates)

    if success:
        if not args.quiet:
            console.print(f"[green]Updated bookmark {args.id}[/green]")
    else:
        console.print(f"[red]Failed to update bookmark {args.id}[/red]")
        sys.exit(1)


def cmd_refresh(args):
    """Refresh cached content for bookmarks."""
    db = get_db(args.db)

    if args.id:
        # Refresh specific bookmark
        result = db.refresh_content(
            int(args.id),
            update_metadata=not args.no_update_metadata,
            force=args.force
        )

        if result["success"]:
            console.print(f"[green]✓ Refreshed bookmark {result['bookmark_id']}[/green]")
            console.print(f"  URL: {result['url']}")
            console.print(f"  Status: {result['status_code']}")
            console.print(f"  Content: {result['content_length']:,} bytes → {result['compressed_size']:,} bytes ({result['compression_ratio']:.1f}% compression)")
            if result.get("content_changed"):
                console.print(f"  [yellow]Content changed[/yellow]")
            if result.get("title_updated"):
                console.print(f"  [yellow]Title updated[/yellow]")
        else:
            console.print(f"[red]✗ Failed to refresh: {result['error']}[/red]")
            if result.get("status_code"):
                console.print(f"  Status code: {result['status_code']}")
            sys.exit(1)

    elif args.all:
        # Refresh all bookmarks with parallel processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        bookmarks = db.all()
        max_workers = args.workers

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Refreshing 0/{len(bookmarks)} bookmarks...", total=len(bookmarks))

            success_count = 0
            failed_count = 0
            completed_count = 0
            lock = threading.Lock()

            def refresh_bookmark(bookmark):
                result = db.refresh_content(
                    bookmark.id,
                    update_metadata=not args.no_update_metadata,
                    force=args.force
                )
                return bookmark, result

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                futures = {executor.submit(refresh_bookmark, b): b for b in bookmarks}

                # Process results as they complete
                for future in as_completed(futures):
                    bookmark = futures[future]
                    try:
                        _, result = future.result()

                        with lock:
                            completed_count += 1
                            if result["success"]:
                                success_count += 1
                            else:
                                failed_count += 1
                                if not args.quiet:
                                    console.print(f"[yellow]Failed: {bookmark.url} - {result['error']}[/yellow]")

                            progress.update(task, description=f"Refreshed {completed_count}/{len(bookmarks)} bookmarks (✓ {success_count}, ✗ {failed_count})")
                            progress.advance(task)
                    except Exception as e:
                        with lock:
                            completed_count += 1
                            failed_count += 1
                            if not args.quiet:
                                console.print(f"[red]Error: {bookmark.url} - {str(e)}[/red]")
                            progress.update(task, description=f"Refreshed {completed_count}/{len(bookmarks)} bookmarks (✓ {success_count}, ✗ {failed_count})")
                            progress.advance(task)

        console.print(f"\n[green]✓ Refreshed {success_count} bookmarks[/green]")
        if failed_count > 0:
            console.print(f"[red]✗ Failed {failed_count} bookmarks[/red]")

    elif args.unreachable:
        # Refresh only unreachable bookmarks
        bookmarks = db.search(reachable=False)

        console.print(f"Refreshing {len(bookmarks)} unreachable bookmarks...")

        success_count = 0
        recovered_count = 0

        for bookmark in bookmarks:
            result = db.refresh_content(
                bookmark.id,
                update_metadata=not args.no_update_metadata,
                force=args.force
            )

            if result["success"]:
                recovered_count += 1
                if not args.quiet:
                    console.print(f"[green]✓ Recovered: {bookmark.url}[/green]")
            else:
                success_count += 1

        console.print(f"\n[green]✓ Recovered {recovered_count} bookmarks[/green]")
        if success_count > 0:
            console.print(f"[yellow]Still unreachable: {success_count}[/yellow]")

    else:
        console.print("[red]Error: Must specify --id, --all, or --unreachable[/red]")
        sys.exit(1)


def cmd_view(args):
    """View cached content for a bookmark."""
    db = get_db(args.db)
    from btk.models import ContentCache
    from btk.content_fetcher import ContentFetcher
    from sqlalchemy import select

    # Get bookmark
    try:
        bookmark = db.get(id=int(args.id))
    except ValueError:
        bookmark = db.get(unique_id=args.id)

    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    # Get or fetch content cache
    with db.session() as session:
        cache = session.execute(
            select(ContentCache).where(ContentCache.bookmark_id == bookmark.id)
        ).scalar_one_or_none()

        if not cache or args.fetch:
            # Fetch fresh content
            console.print(f"Fetching content from {bookmark.url}...")
            result = db.refresh_content(bookmark.id)

            if not result["success"]:
                console.print(f"[red]Failed to fetch content: {result['error']}[/red]")
                sys.exit(1)

            # Re-fetch cache
            cache = session.execute(
                select(ContentCache).where(ContentCache.bookmark_id == bookmark.id)
            ).scalar_one_or_none()

        if not cache:
            console.print(f"[yellow]No cached content available[/yellow]")
            sys.exit(1)

        if args.html:
            # Open HTML in browser
            import tempfile
            import webbrowser

            # Decompress HTML
            html_content = ContentFetcher.decompress_html(cache.html_content)

            # Save to temp file
            with tempfile.NamedTemporaryFile(
                mode='wb', suffix='.html', delete=False
            ) as f:
                f.write(html_content)
                temp_path = f.name

            console.print(f"Opening in browser: {temp_path}")
            webbrowser.open(f"file://{temp_path}")

        elif args.raw:
            # Show raw HTML
            html_content = ContentFetcher.decompress_html(cache.html_content)
            print(html_content.decode(cache.encoding or 'utf-8'))

        else:
            # Show markdown in terminal (default)
            from rich.markdown import Markdown
            from rich.panel import Panel

            md = Markdown(cache.markdown_content)
            panel = Panel(
                md,
                title=f"{bookmark.title}",
                subtitle=f"[dim]{bookmark.url}[/dim]",
                border_style="blue"
            )
            console.print(panel)

            # Show metadata
            console.print(f"\n[dim]Fetched: {cache.fetched_at.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            console.print(f"[dim]Size: {cache.content_length:,} bytes (compressed: {cache.compressed_size:,})[/dim]")


def cmd_auto_tag(args):
    """Auto-generate tags for bookmarks using NLP."""
    db = get_db(args.db)
    from btk.models import ContentCache
    from sqlalchemy import select
    import sys
    import os

    # Import the NLP tagger
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'integrations', 'auto_tag_nlp'))
    from nlp_tagger import NLPTagSuggester

    tagger = NLPTagSuggester()

    if args.id:
        # Auto-tag specific bookmark
        bookmark = db.get(id=int(args.id))
        if not bookmark:
            console.print(f"[red]Bookmark not found: {args.id}[/red]")
            sys.exit(1)

        # Get cached content
        cached_content = None
        with db.session() as session:
            cache = session.execute(
                select(ContentCache).where(ContentCache.bookmark_id == bookmark.id)
            ).scalar_one_or_none()
            if cache:
                cached_content = cache.markdown_content

        # Suggest tags
        suggested = tagger.suggest_tags(
            url=bookmark.url,
            title=bookmark.title,
            content=cached_content,
            description=bookmark.description
        )

        console.print(f"\n[cyan]Suggested tags for:[/cyan] {bookmark.title}")
        console.print(f"[dim]{bookmark.url}[/dim]\n")

        for tag in suggested:
            console.print(f"  • {tag}")

        if args.apply:
            # Add suggested tags
            existing_tags = [t.name for t in bookmark.tags]
            new_tags = [t for t in suggested if t not in existing_tags]

            if new_tags:
                db.update(bookmark.id, tags=existing_tags + new_tags)
                console.print(f"\n[green]✓ Added {len(new_tags)} new tags[/green]")
            else:
                console.print(f"\n[yellow]No new tags to add[/yellow]")

    elif args.all:
        # Auto-tag all bookmarks (single-threaded for stability)
        bookmarks = db.all()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Auto-tagging bookmarks...", total=len(bookmarks))

            tagged_count = 0
            processed_count = 0

            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError("Tagging operation timed out")

            for bookmark in bookmarks:
                try:
                    # Skip unreachable bookmarks
                    if not bookmark.reachable:
                        processed_count += 1
                        progress.update(task, description=f"Auto-tagged {processed_count}/{len(bookmarks)} bookmarks (✓ {tagged_count} tagged, skipped)")
                        progress.advance(task)
                        continue

                    # Get cached content
                    cached_content = None
                    with db.session() as session:
                        cache = session.execute(
                            select(ContentCache).where(ContentCache.bookmark_id == bookmark.id)
                        ).scalar_one_or_none()
                        if cache:
                            # Skip if no content or failed fetch
                            if cache.status_code >= 400 or not cache.markdown_content or len(cache.markdown_content.strip()) == 0:
                                processed_count += 1
                                progress.update(task, description=f"Auto-tagged {processed_count}/{len(bookmarks)} bookmarks (✓ {tagged_count} tagged, skipped)")
                                progress.advance(task)
                                continue
                            cached_content = cache.markdown_content

                    # Set a 5-second timeout for the tagging operation
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(5)

                    try:
                        # Suggest tags
                        suggested = tagger.suggest_tags(
                            url=bookmark.url,
                            title=bookmark.title,
                            content=cached_content,
                            description=bookmark.description
                        )

                        if args.apply and suggested:
                            existing_tags = [t.name for t in bookmark.tags]
                            new_tags = [t for t in suggested if t not in existing_tags]

                            if new_tags:
                                db.update(bookmark.id, tags=existing_tags + new_tags)
                                tagged_count += 1
                    finally:
                        signal.alarm(0)  # Cancel the alarm

                except TimeoutError:
                    logger.warning(f"Timeout tagging bookmark {bookmark.id} ({bookmark.url}) - skipping")
                except Exception as e:
                    logger.error(f"Error tagging bookmark {bookmark.id} ({bookmark.url}): {e}")

                processed_count += 1
                progress.update(task, description=f"Auto-tagged {processed_count}/{len(bookmarks)} bookmarks (✓ {tagged_count} tagged)")
                progress.advance(task)

        if args.apply:
            console.print(f"\n[green]✓ Tagged {tagged_count} bookmarks[/green]")
        else:
            console.print(f"\n[yellow]Preview mode - use --apply to save tags[/yellow]")

    else:
        console.print("[red]Error: Must specify --id or --all[/red]")
        sys.exit(1)


def cmd_delete(args):
    """Delete a bookmark."""
    db = get_db(args.db)

    # Handle multiple IDs
    ids = [int(id_str) for id_str in args.ids]
    deleted_count = 0

    for bookmark_id in ids:
        if db.delete(bookmark_id):
            deleted_count += 1
            if not args.quiet:
                console.print(f"[green]Deleted bookmark {bookmark_id}[/green]")
        else:
            console.print(f"[yellow]Bookmark not found: {bookmark_id}[/yellow]")

    if args.quiet:
        print(deleted_count)


def cmd_query(args):
    """Execute SQL-like query."""
    db = get_db(args.db)

    try:
        bookmarks = db.query(sql=args.sql)
        output_bookmarks(bookmarks, args.output)
    except Exception as e:
        console.print(f"[red]Query error: {e}[/red]")
        sys.exit(1)


def cmd_stats(args):
    """Show database statistics."""
    db = get_db(args.db)
    stats = db.stats()

    if args.output == "json":
        print(json.dumps(stats, indent=2))
    else:
        table = Table(title="Database Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in stats.items():
            if key == "database_size":
                value = f"{value / 1024:.1f} KB"
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)


def cmd_db_info(args):
    """Show detailed database information."""
    db = get_db(args.db)
    info = db.info()

    if args.output == "json":
        print(json.dumps(info, indent=2))
    else:
        table = Table(title="Database Information")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        for key, value in info.items():
            if key == "tables":
                value = ", ".join(value)
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)


def cmd_db_schema(args):
    """Show database schema."""
    db = get_db(args.db)
    schema = db.schema()

    if args.output == "json":
        print(json.dumps(schema, indent=2))
    else:
        for table_name, table_info in schema.items():
            table = Table(title=f"Table: {table_name}")
            table.add_column("Column", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Nullable", style="yellow")
            table.add_column("Key", style="red")

            for col in table_info["columns"]:
                key_info = []
                if col["primary_key"]:
                    key_info.append("PK")
                if col["unique"]:
                    key_info.append("UQ")
                key_str = ", ".join(key_info) if key_info else ""

                table.add_row(
                    col["name"],
                    col["type"],
                    "Yes" if col["nullable"] else "No",
                    key_str
                )

            console.print(table)
            console.print()  # Add spacing between tables


def cmd_import(args):
    """Import bookmarks from various formats."""
    from btk.importers import import_file

    db = get_db(args.db)

    # Import based on file extension or specified format
    path = Path(args.file)
    format = args.format or path.suffix[1:]  # Remove the dot

    try:
        count = import_file(db, path, format)
        if not args.quiet:
            console.print(f"[green]Imported {count} bookmarks from {path}[/green]")
    except Exception as e:
        console.print(f"[red]Import error: {e}[/red]")
        sys.exit(1)


def cmd_export(args):
    """Export bookmarks to various formats."""
    from btk.exporters import export_file

    # Determine if we should read from stdin
    # Use stdin ONLY if:
    # 1. stdin is not a TTY AND
    # 2. No --query specified AND
    # 3. No filter args specified (--starred, --pinned, --tags, etc.)
    filters = build_filters(args)
    has_filters = filters and filters != {'archived': False}  # Has filters beyond default
    has_query = hasattr(args, 'query') and args.query

    use_stdin = not sys.stdin.isatty() and not has_query and not has_filters

    if use_stdin and not sys.stdin.isatty():
        # Read JSON from stdin (piped input)
        try:
            data = json.load(sys.stdin)
            # Convert JSON data back to Bookmark objects
            from btk.models import Bookmark, Tag
            bookmarks = []
            for item in data:
                # Create a minimal Bookmark object from JSON
                bookmark = Bookmark(
                    id=item['id'],
                    url=item['url'],
                    title=item['title'],
                    stars=item.get('stars', False),
                    visit_count=item.get('visits', 0),
                    added=datetime.fromisoformat(item['added']) if item.get('added') else datetime.now(timezone.utc),
                    description=item.get('description', ''),
                    unique_id=item.get('unique_id', '')
                )
                # Add tags
                bookmark.tags = [Tag(name=tag_name) for tag_name in item.get('tags', [])]
                bookmarks.append(bookmark)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error parsing JSON from stdin: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            # If stdin reading fails, fall back to database mode
            console.print(f"[yellow]Warning: Failed to read from stdin, using database mode[/yellow]")
            db = get_db(args.db)
            bookmarks = db.list()
    else:
        # Normal mode: query database
        db = get_db(args.db)

        # Get bookmarks to export
        if hasattr(args, 'query') and args.query:
            # SQL query mode
            bookmarks = db.query(sql=args.query)
        else:
            # Use filters if any are specified
            filters = build_filters(args)
            if filters and filters != {'archived': False}:
                # Has actual filters beyond default archived filter
                bookmarks = db.search(**filters)
            else:
                # No filters, export all (respecting archived default)
                bookmarks = db.list(exclude_archived=filters.get('archived') == False)

    try:
        export_file(bookmarks, args.file, args.format)
        if not args.quiet:
            console.print(f"[green]Exported {len(bookmarks)} bookmarks to {args.file}[/green]")
    except Exception as e:
        console.print(f"[red]Export error: {e}[/red]")
        sys.exit(1)


def cmd_tags(args):
    """Manage tags."""
    db = get_db(args.db)

    with db.session() as session:
        from sqlalchemy import select, func
        from btk.models import Tag, Bookmark, bookmark_tags

        # Get tag statistics
        query = (
            select(Tag.name, func.count(bookmark_tags.c.bookmark_id).label("count"))
            .select_from(Tag)
            .join(bookmark_tags, Tag.id == bookmark_tags.c.tag_id)
            .group_by(Tag.name)
            .order_by(func.count(bookmark_tags.c.bookmark_id).desc())
        )

        results = session.execute(query).all()

        if args.output == "json":
            data = [{"tag": name, "count": count} for name, count in results]
            print(json.dumps(data, indent=2))
        else:
            table = Table(title="Tags")
            table.add_column("Tag", style="cyan")
            table.add_column("Count", style="green")

            for name, count in results:
                table.add_row(name, str(count))

            console.print(table)


def cmd_tag_add(args):
    """Add tag to bookmark(s)."""
    db = get_db(args.db)

    from btk.models import Tag, Bookmark

    tag_name = args.tag
    bookmark_ids = [int(id_str) for id_str in args.ids]

    added_count = 0

    with db.session() as session:
        # Get or create tag
        tag = session.query(Tag).filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            session.add(tag)

        # Add to each bookmark
        for bookmark_id in bookmark_ids:
            bookmark = session.get(Bookmark, bookmark_id)
            if not bookmark:
                console.print(f"[yellow]Bookmark {bookmark_id} not found, skipping[/yellow]")
                continue

            if tag not in bookmark.tags:
                bookmark.tags.append(tag)
                added_count += 1

        session.commit()

    console.print(f"[green]✓ Added tag '{tag_name}' to {added_count} bookmark(s)[/green]")


def cmd_tag_remove(args):
    """Remove tag from bookmark(s)."""
    db = get_db(args.db)

    from btk.models import Tag, Bookmark

    tag_name = args.tag
    bookmark_ids = [int(id_str) for id_str in args.ids]

    removed_count = 0

    with db.session() as session:
        tag = session.query(Tag).filter_by(name=tag_name).first()
        if not tag:
            console.print(f"[yellow]Tag '{tag_name}' not found[/yellow]")
            return

        # Remove from each bookmark
        for bookmark_id in bookmark_ids:
            bookmark = session.get(Bookmark, bookmark_id)
            if not bookmark:
                console.print(f"[yellow]Bookmark {bookmark_id} not found, skipping[/yellow]")
                continue

            if tag in bookmark.tags:
                bookmark.tags.remove(tag)
                removed_count += 1

        session.commit()

    console.print(f"[green]✓ Removed tag '{tag_name}' from {removed_count} bookmark(s)[/green]")


def cmd_tag_rename(args):
    """Rename a tag across all bookmarks."""
    db = get_db(args.db)

    from btk.models import Tag, Bookmark

    old_tag = args.old_tag
    new_tag = args.new_tag

    if old_tag == new_tag:
        console.print("[yellow]Tags are the same, nothing to do[/yellow]")
        return

    renamed_count = 0

    with db.session() as session:
        # Find old tag
        old_tag_obj = session.query(Tag).filter_by(name=old_tag).first()
        if not old_tag_obj:
            console.print(f"[yellow]Tag '{old_tag}' not found[/yellow]")
            return

        # Get or create new tag
        new_tag_obj = session.query(Tag).filter_by(name=new_tag).first()
        if not new_tag_obj:
            new_tag_obj = Tag(name=new_tag)
            session.add(new_tag_obj)

        # Get all bookmarks with old tag
        bookmarks = session.query(Bookmark).join(Bookmark.tags).filter(Tag.name == old_tag).all()

        console.print(f"[yellow]Renaming tag '{old_tag}' to '{new_tag}' on {len(bookmarks)} bookmark(s)[/yellow]")

        # Update each bookmark
        for bookmark in bookmarks:
            # Remove old tag
            if old_tag_obj in bookmark.tags:
                bookmark.tags.remove(old_tag_obj)

            # Add new tag if not already present
            if new_tag_obj not in bookmark.tags:
                bookmark.tags.append(new_tag_obj)

            renamed_count += 1

        session.commit()

        # Clean up orphaned old tag
        old_tag_obj = session.query(Tag).filter_by(name=old_tag).first()
        if old_tag_obj:
            bookmark_count = session.query(Bookmark).join(Bookmark.tags).filter(Tag.name == old_tag).count()
            if bookmark_count == 0:
                session.delete(old_tag_obj)
                session.commit()

    console.print(f"[green]✓ Renamed tag '{old_tag}' to '{new_tag}' on {renamed_count} bookmark(s)[/green]")


def cmd_graph(args):
    """Manage bookmark graph."""
    from btk.graph import BookmarkGraph, GraphConfig

    db = get_db(args.db)
    graph = BookmarkGraph(db)

    if args.graph_command == "build":
        # Build graph with specified config
        # Check if there are any bookmarks
        bookmark_count = len(db.all())
        if bookmark_count == 0:
            console.print("[yellow]No bookmarks found in the database.[/yellow]")
            console.print("\n[cyan]To add bookmarks, try:[/cyan]")
            console.print("  btk add <url> --title \"Title\" --tags \"tag1,tag2\"")
            console.print("  btk import html <file.html>")
            console.print("  btk import json <file.json>")
            return

        config = GraphConfig(
            domain_weight=args.domain_weight,
            tag_weight=args.tag_weight,
            direct_link_weight=args.direct_link_weight,
            indirect_link_weight=args.indirect_link_weight,
            min_edge_weight=args.min_edge_weight,
            max_indirect_hops=args.max_hops
        )

        console.print("[cyan]Building bookmark graph...[/cyan]")

        # Create progress bar
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Computing similarities...", total=None)

            def progress_callback(current, total, edges_found):
                if progress.tasks[task].total is None:
                    progress.update(task, total=total)
                progress.update(task, completed=current, description=f"[cyan]Computing similarities (found {edges_found} edges)...")

            stats = graph.build(config, progress_callback=progress_callback)

        # Save to database
        console.print("[cyan]Saving graph to database...[/cyan]")
        graph.save()

        # Display statistics
        console.print(f"\n[green]✓ Graph built successfully![/green]")
        console.print(f"  Bookmarks: {stats['total_bookmarks']}")
        console.print(f"  Edges: {stats['total_edges']}")
        console.print(f"  Avg edge weight: {stats['avg_edge_weight']:.2f}")
        console.print(f"  Max edge weight: {stats['max_edge_weight']:.2f}")
        console.print(f"\n  Components used:")
        console.print(f"    Domain: {stats['components']['domain']} edges")
        console.print(f"    Tags: {stats['components']['tag']} edges")
        console.print(f"    Direct links: {stats['components']['direct_link']} edges")
        if args.indirect_link_weight > 0:
            console.print(f"    Indirect links: {stats['components']['indirect_link']} edges")

    elif args.graph_command == "neighbors":
        # Load existing graph
        try:
            graph.load()
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("\n[cyan]To build the graph, run:[/cyan]")
            console.print("  btk graph build")
            return

        # Get neighbors
        neighbors = graph.get_neighbors(
            int(args.bookmark_id),
            min_weight=args.min_weight,
            limit=args.limit
        )

        if not neighbors:
            console.print(f"[yellow]No neighbors found for bookmark {args.bookmark_id}[/yellow]")
            console.print(f"\n[dim]Tip: Try lowering --min-weight or check if the bookmark exists[/dim]")
            return

        # Display results
        table = Table(title=f"Neighbors of Bookmark {args.bookmark_id}")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Weight", style="green")
        table.add_column("Domain", style="blue")
        table.add_column("Tags", style="yellow")
        table.add_column("Link", style="magenta")

        for neighbor in neighbors:
            bookmark = db.get(neighbor['bookmark_id'])
            if bookmark:
                comps = neighbor['components']
                table.add_row(
                    str(bookmark.id),
                    bookmark.title[:40],
                    f"{neighbor['weight']:.2f}",
                    f"{comps['domain']:.2f}" if comps['domain'] > 0 else "",
                    f"{comps['tag']:.2f}" if comps['tag'] > 0 else "",
                    "✓" if comps['direct_link'] > 0 else ""
                )

        console.print(table)

    elif args.graph_command == "export":
        # Load graph
        try:
            graph.load()
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("\n[cyan]To build the graph, run:[/cyan]")
            console.print("  btk graph build")
            return

        if args.format == "d3":
            graph.export_d3(Path(args.file), min_weight=getattr(args, 'min_weight', 0.0))
            console.print(f"[green]Exported D3.js graph to {args.file}[/green]")

        elif args.format == "svg":
            console.print("[cyan]Generating SVG with force-directed layout...[/cyan]")
            graph.export_svg(
                Path(args.file),
                min_weight=getattr(args, 'min_weight', 0.0),
                width=args.width,
                height=args.height,
                show_labels=args.show_labels
            )
            console.print(f"[green]Exported SVG graph to {args.file}[/green]")

        elif args.format == "png":
            # First generate SVG, then convert to PNG
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False) as tmp:
                tmp_svg = tmp.name

            console.print("[cyan]Generating SVG with force-directed layout...[/cyan]")
            graph.export_svg(
                Path(tmp_svg),
                min_weight=getattr(args, 'min_weight', 0.0),
                width=args.width,
                height=args.height,
                show_labels=args.show_labels
            )

            console.print("[cyan]Converting SVG to PNG...[/cyan]")
            try:
                from cairosvg import svg2png
                svg2png(url=tmp_svg, write_to=args.file)
                console.print(f"[green]Exported PNG graph to {args.file}[/green]")
            except ImportError:
                console.print("[yellow]cairosvg not installed. Attempting with Pillow + svglib...[/yellow]")
                try:
                    from svglib.svglib import svg2rlg
                    from reportlab.graphics import renderPM
                    drawing = svg2rlg(tmp_svg)
                    renderPM.drawToFile(drawing, args.file, fmt='PNG')
                    console.print(f"[green]Exported PNG graph to {args.file}[/green]")
                except ImportError:
                    console.print("[red]Error: PNG export requires either 'cairosvg' or 'svglib+reportlab'[/red]")
                    console.print("[yellow]Install with: pip install cairosvg[/yellow]")
                    console.print(f"[yellow]SVG file saved at: {tmp_svg}[/yellow]")
                    console.print("[yellow]You can manually convert it to PNG using Inkscape or online tools[/yellow]")
                    sys.exit(1)
            finally:
                import os
                if os.path.exists(tmp_svg):
                    os.unlink(tmp_svg)

        elif args.format == "gexf":
            console.print("[cyan]Exporting to GEXF (Gephi native format)...[/cyan]")
            graph.export_gexf(Path(args.file), min_weight=getattr(args, 'min_weight', 0.0))
            console.print(f"[green]Exported GEXF graph to {args.file}[/green]")
            console.print("[cyan]Open this file in Gephi for advanced network analysis[/cyan]")

        elif args.format == "graphml":
            console.print("[cyan]Exporting to GraphML...[/cyan]")
            graph.export_graphml(Path(args.file), min_weight=getattr(args, 'min_weight', 0.0))
            console.print(f"[green]Exported GraphML graph to {args.file}[/green]")
            console.print("[cyan]Compatible with yEd, Gephi, Cytoscape, and NetworkX[/cyan]")

        elif args.format == "gml":
            console.print("[cyan]Exporting to GML (Graph Modeling Language)...[/cyan]")
            graph.export_gml(Path(args.file), min_weight=getattr(args, 'min_weight', 0.0))
            console.print(f"[green]Exported GML graph to {args.file}[/green]")
            console.print("[cyan]Simple text format compatible with many graph tools[/cyan]")

        else:
            console.print(f"[red]Unknown format: {args.format}[/red]")
            sys.exit(1)

    elif args.graph_command == "stats":
        # Load graph and show statistics
        try:
            graph.load()
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("\n[cyan]To build the graph, run:[/cyan]")
            console.print("  btk graph build")
            return

        total_edges = len(graph.edges)
        if total_edges == 0:
            console.print("[yellow]Graph is empty. Run 'btk graph build' first.[/yellow]")
            return

        # Calculate stats
        total_weight = sum(e['weight'] for e in graph.edges.values())
        avg_weight = total_weight / total_edges

        # Component breakdown
        domain_edges = sum(1 for e in graph.edges.values() if e['components']['domain'] > 0)
        tag_edges = sum(1 for e in graph.edges.values() if e['components']['tag'] > 0)
        link_edges = sum(1 for e in graph.edges.values() if e['components']['direct_link'] > 0)

        console.print(f"[cyan]Graph Statistics[/cyan]")
        console.print(f"  Total edges: {total_edges}")
        console.print(f"  Average weight: {avg_weight:.2f}")
        console.print(f"\n  Edges by component:")
        console.print(f"    Domain similarity: {domain_edges}")
        console.print(f"    Tag overlap: {tag_edges}")
        console.print(f"    Direct links: {link_edges}")


def cmd_config(args):
    """Manage configuration."""
    config = get_config()

    if args.action == "show":
        if args.key:
            value = getattr(config, args.key, None)
            if value is not None:
                print(value)
            else:
                console.print(f"[red]Unknown config key: {args.key}[/red]")
                sys.exit(1)
        else:
            # Show all config
            from dataclasses import asdict
            print(json.dumps(asdict(config), indent=2))

    elif args.action == "set":
        setattr(config, args.key, args.value)
        config.save()
        if not args.quiet:
            console.print(f"[green]Set {args.key} = {args.value}[/green]")

    elif args.action == "init":
        # Initialize config file
        config_path = Path.home() / ".config" / "btk" / "config.toml"
        config.save(config_path)
        console.print(f"[green]Created config at {config_path}[/green]")


def cmd_shell(args):
    """Launch interactive bookmark shell."""
    from btk.shell import BookmarkShell

    db_path = args.db if hasattr(args, 'db') else 'btk.db'

    try:
        shell = BookmarkShell(db_path)
        shell.cmdloop()
    except KeyboardInterrupt:
        console.print("\n[cyan]Interrupted. Goodbye![/cyan]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BTK - Bookmark Toolkit: A clean, composable bookmark manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bookmark operations
  btk bookmark add https://example.com --title "Example" --tags "web,demo"
  btk bookmark list --limit 10 --sort visit_count
  btk bookmark search "python"
  btk bookmark get 123
  btk bookmark update 123 --title "New Title" --add-tags "important"
  btk bookmark delete 1 2 3

  # Tag operations
  btk tag list
  btk tag add python 123
  btk tag rename "old-name" "new-name"
  btk tag copy important --starred

  # Content operations
  btk content refresh --id 123
  btk content view 123 --html

  # Import/Export
  btk import html bookmarks.html
  btk export json data.json --starred

  # Database management
  btk db info
  btk db schema
  btk db stats

  # Interactive shell
  btk shell

  # Composable Unix-style pipelines
  btk bookmark list --output urls | xargs -I {} curl -I {}
  btk bookmark search "python" --output json | jq '.[] | .url'

Configuration:
  Default database: ./btk.db or from config
  Config file: ~/.config/btk/config.toml
  Environment: BTK_DATABASE, BTK_OUTPUT_FORMAT
        """
    )

    # Global options
    parser.add_argument("--db", help="Database file (default: btk.db)")
    parser.add_argument("--config", help="Config file path")
    parser.add_argument("-q", "--quiet", action="store_true", help="Minimal output")
    parser.add_argument("-o", "--output", choices=["table", "json", "csv", "plain", "urls"],
                       help="Output format")


    subparsers = parser.add_subparsers(dest="command", required=True, help="Command groups")

    # =================
    # BOOKMARK GROUP
    # =================
    bookmark_parser = subparsers.add_parser("bookmark", help="Bookmark operations")
    bookmark_subparsers = bookmark_parser.add_subparsers(dest="bookmark_command", required=True)

    # bookmark add
    bm_add = bookmark_subparsers.add_parser("add", help="Add a bookmark")
    bm_add.add_argument("url", help="URL to bookmark")
    bm_add.add_argument("--title", help="Bookmark title")
    bm_add.add_argument("--description", help="Description")
    bm_add.add_argument("--tags", help="Comma-separated tags")
    bm_add.add_argument("--star", action="store_true", help="Star this bookmark")
    bm_add.set_defaults(func=cmd_add)

    # bookmark list
    bm_list = bookmark_subparsers.add_parser("list", help="List bookmarks")
    bm_list.add_argument("--limit", type=int, help="Maximum results")
    bm_list.add_argument("--offset", type=int, default=0, help="Skip N results")
    bm_list.add_argument("--sort", choices=["added", "title", "visit_count", "stars"],
                        default="added", help="Sort order")
    bm_list.add_argument("--include-archived", action="store_true", help="Include archived bookmarks")
    bm_list.add_argument("--starred", action="store_true", help="Filter to starred bookmarks")
    bm_list.set_defaults(func=cmd_list)

    # bookmark search
    bm_search = bookmark_subparsers.add_parser("search", help="Search bookmarks")
    bm_search.add_argument("query", nargs='?', default='', help="Search query (optional)")
    bm_search.add_argument("--in-content", action="store_true", help="Search within cached content")
    bm_search.add_argument("--limit", type=int, help="Maximum results")
    bm_search.add_argument("--starred", action="store_true", help="Filter to starred bookmarks")
    bm_search.add_argument("--archived", action="store_true", help="Filter to archived bookmarks")
    bm_search.add_argument("--unarchived", action="store_true", help="Filter to non-archived bookmarks")
    bm_search.add_argument("--include-archived", action="store_true", help="Include archived bookmarks")
    bm_search.add_argument("--pinned", action="store_true", help="Filter to pinned bookmarks")
    bm_search.add_argument("--tags", help="Filter by tags (comma-separated)")
    bm_search.add_argument("--untagged", action="store_true", help="Filter to bookmarks with no tags")
    bm_search.set_defaults(func=cmd_search)

    # bookmark get
    bm_get = bookmark_subparsers.add_parser("get", help="Get a specific bookmark")
    bm_get.add_argument("id", help="Bookmark ID or unique ID")
    bm_get.add_argument("--details", action="store_true", help="Show detailed metadata")
    bm_get.set_defaults(func=cmd_get)

    # bookmark update
    bm_update = bookmark_subparsers.add_parser("update", help="Update a bookmark")
    bm_update.add_argument("id", help="Bookmark ID")
    bm_update.add_argument("--url", help="New URL")
    bm_update.add_argument("--title", help="New title")
    bm_update.add_argument("--description", help="New description")
    bm_update.add_argument("--tags", help="Replace all tags (comma-separated)")
    bm_update.add_argument("--add-tags", help="Add tags (comma-separated)")
    bm_update.add_argument("--remove-tags", help="Remove tags (comma-separated)")
    bm_update.add_argument("--star", action="store_true", dest="starred", default=None, help="Mark as starred")
    bm_update.add_argument("--unstar", action="store_false", dest="starred", help="Remove starred status")
    bm_update.add_argument("--archive", action="store_true", dest="archived", default=None, help="Mark as archived")
    bm_update.add_argument("--unarchive", action="store_false", dest="archived", help="Remove archived status")
    bm_update.add_argument("--pin", action="store_true", dest="pinned", default=None, help="Mark as pinned")
    bm_update.add_argument("--unpin", action="store_false", dest="pinned", help="Remove pinned status")
    bm_update.set_defaults(func=cmd_update)

    # bookmark delete
    bm_delete = bookmark_subparsers.add_parser("delete", help="Delete bookmarks")
    bm_delete.add_argument("ids", nargs="+", help="Bookmark IDs to delete")
    bm_delete.set_defaults(func=cmd_delete)

    # bookmark query
    bm_query = bookmark_subparsers.add_parser("query", help="Execute SQL-like query")
    bm_query.add_argument("sql", help="SQL WHERE clause")
    bm_query.set_defaults(func=cmd_query)

    # =================
    # TAG GROUP
    # =================
    tag_parser = subparsers.add_parser("tag", help="Tag management")
    tag_subparsers = tag_parser.add_subparsers(dest="tag_command", required=True)

    # tag list
    tag_list = tag_subparsers.add_parser("list", help="List all tags")
    tag_list.set_defaults(func=cmd_tags)

    # tag add
    tag_add = tag_subparsers.add_parser("add", help="Add tag(s) to bookmark(s)")
    tag_add.add_argument("tag", help="Tag to add")
    tag_add.add_argument("ids", nargs="+", help="Bookmark IDs")
    tag_add.set_defaults(func=cmd_tag_add)

    # tag remove
    tag_remove = tag_subparsers.add_parser("remove", help="Remove tag(s) from bookmark(s)")
    tag_remove.add_argument("tag", help="Tag to remove")
    tag_remove.add_argument("ids", nargs="+", help="Bookmark IDs")
    tag_remove.set_defaults(func=cmd_tag_remove)

    # tag rename
    tag_rename = tag_subparsers.add_parser("rename", help="Rename a tag")
    tag_rename.add_argument("old_tag", help="Current tag name")
    tag_rename.add_argument("new_tag", help="New tag name")
    tag_rename.set_defaults(func=cmd_tag_rename)

    # tag copy
    tag_copy = tag_subparsers.add_parser("copy", help="Copy tag to bookmarks")
    tag_copy.add_argument("tag", help="Tag to copy")
    tag_copy.add_argument("--to-ids", help="Comma-separated bookmark IDs")
    tag_copy.add_argument("--starred", action="store_true", help="Copy to all starred bookmarks")
    tag_copy.add_argument("--all", action="store_true", help="Copy to all bookmarks")
    tag_copy.set_defaults(func=lambda args: print("tag copy not yet implemented"))

    # tag stats
    tag_stats = tag_subparsers.add_parser("stats", help="Show tag statistics")
    tag_stats.set_defaults(func=lambda args: print("tag stats not yet implemented"))

    # =================
    # CONTENT GROUP
    # =================
    content_parser = subparsers.add_parser("content", help="Content operations")
    content_subparsers = content_parser.add_subparsers(dest="content_command", required=True)

    # content refresh
    content_refresh = content_subparsers.add_parser("refresh", help="Refresh cached content")
    content_refresh.add_argument("--id", type=int, help="Refresh specific bookmark ID")
    content_refresh.add_argument("--all", action="store_true", help="Refresh all bookmarks")
    content_refresh.add_argument("--unreachable", action="store_true", help="Refresh only unreachable bookmarks")
    content_refresh.add_argument("--force", action="store_true", help="Force refresh even if unchanged")
    content_refresh.add_argument("--no-update-metadata", action="store_true",
                                help="Don't update title/description from fetched content")
    content_refresh.set_defaults(func=cmd_refresh)

    # content view
    content_view = content_subparsers.add_parser("view", help="View cached content")
    content_view.add_argument("id", help="Bookmark ID or unique ID")
    content_view.add_argument("--html", action="store_true", help="Open cached HTML in browser")
    content_view.add_argument("--raw", action="store_true", help="Show raw HTML")
    content_view.add_argument("--fetch", action="store_true", help="Fetch fresh content before viewing")
    content_view.set_defaults(func=cmd_view)

    # content auto-tag
    content_autotag = content_subparsers.add_parser("auto-tag", help="Auto-generate tags using NLP")
    content_autotag.add_argument("--id", type=int, help="Auto-tag specific bookmark ID")
    content_autotag.add_argument("--all", action="store_true", help="Auto-tag all bookmarks")
    content_autotag.add_argument("--apply", action="store_true",
                                help="Apply suggested tags (default is preview only)")
    content_autotag.set_defaults(func=cmd_auto_tag)

    # =================
    # IMPORT GROUP
    # =================
    import_parser = subparsers.add_parser("import", help="Import bookmarks")
    import_parser.add_argument("file", help="File to import")
    import_parser.add_argument("--format", help="Force format (auto-detected by default)")
    import_parser.set_defaults(func=cmd_import)

    # =================
    # EXPORT GROUP
    # =================
    export_parser = subparsers.add_parser("export", help="Export bookmarks")
    export_parser.add_argument("file", help="Output file")
    export_parser.add_argument("--format", required=True,
                              choices=["json", "csv", "html", "markdown"],
                              help="Export format")
    export_parser.add_argument("--query", help="SQL query to filter bookmarks")
    export_parser.add_argument("--starred", action="store_true", help="Filter to starred bookmarks")
    export_parser.add_argument("--pinned", action="store_true", help="Filter to pinned bookmarks")
    export_parser.add_argument("--archived", action="store_true", help="Filter to archived bookmarks")
    export_parser.add_argument("--include-archived", action="store_true", help="Include archived bookmarks")
    export_parser.add_argument("--tags", help="Filter by tags (comma-separated)")
    export_parser.set_defaults(func=cmd_export)

    # =================
    # DB GROUP
    # =================
    db_parser = subparsers.add_parser("db", help="Database management")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)

    # db info
    db_info = db_subparsers.add_parser("info", help="Show database information")
    db_info.set_defaults(func=cmd_db_info)

    # db schema
    db_schema = db_subparsers.add_parser("schema", help="Show database schema")
    db_schema.set_defaults(func=cmd_db_schema)

    # db stats
    db_stats = db_subparsers.add_parser("stats", help="Show database statistics")
    db_stats.set_defaults(func=cmd_stats)

    # =================
    # GRAPH GROUP
    # =================
    graph_parser = subparsers.add_parser("graph", help="Analyze bookmark relationships")
    graph_subparsers = graph_parser.add_subparsers(dest="graph_command", required=True)

    # graph build
    graph_build = graph_subparsers.add_parser("build", help="Build bookmark similarity graph")
    graph_build.add_argument("--domain-weight", type=float, default=1.0,
                            help="Weight for domain similarity (default: 1.0)")
    graph_build.add_argument("--tag-weight", type=float, default=2.0,
                            help="Weight for tag similarity (default: 2.0)")
    graph_build.add_argument("--direct-link-weight", type=float, default=5.0,
                            help="Weight for direct links (default: 5.0)")
    graph_build.add_argument("--indirect-link-weight", type=float, default=0.0,
                            help="Weight for indirect links (default: 0.0, off)")
    graph_build.add_argument("--min-edge-weight", type=float, default=0.1,
                            help="Minimum edge weight threshold (default: 0.1)")
    graph_build.add_argument("--max-hops", type=int, default=3,
                            help="Max hops for indirect links (default: 3)")

    # graph neighbors
    graph_neighbors = graph_subparsers.add_parser("neighbors", help="Find similar bookmarks")
    graph_neighbors.add_argument("bookmark_id", help="Bookmark ID to find neighbors for")
    graph_neighbors.add_argument("--min-weight", type=float, default=0.0,
                                help="Minimum edge weight (default: 0.0)")
    graph_neighbors.add_argument("--limit", type=int, default=10,
                                help="Maximum neighbors to show (default: 10)")

    # graph export
    graph_export = graph_subparsers.add_parser("export", help="Export graph visualization")
    graph_export.add_argument("file", help="Output file")
    graph_export.add_argument("--format", choices=["d3", "svg", "png", "gexf", "graphml", "gml"],
                             default="d3",
                             help="Export format: d3 (web), svg/png (images), gexf/graphml/gml (network tools)")
    graph_export.add_argument("--min-weight", type=float, default=0.0,
                             help="Minimum edge weight to include (default: 0.0)")
    graph_export.add_argument("--width", type=int, default=2000,
                             help="Image width for svg/png (default: 2000)")
    graph_export.add_argument("--height", type=int, default=2000,
                             help="Image height for svg/png (default: 2000)")
    graph_export.add_argument("--no-labels", dest="show_labels", action="store_false",
                             help="Hide bookmark labels in svg/png")

    # graph stats
    graph_stats = graph_subparsers.add_parser("stats", help="Show graph statistics")

    graph_parser.set_defaults(func=cmd_graph)

    # =================
    # CONFIG GROUP
    # =================
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument("action", choices=["show", "set", "init"],
                              help="Config action")
    config_parser.add_argument("key", nargs="?", help="Config key")
    config_parser.add_argument("value", nargs="?", help="Config value (for set)")
    config_parser.set_defaults(func=cmd_config)

    # =================
    # SHELL COMMAND
    # =================
    shell_parser = subparsers.add_parser("shell", help="Interactive bookmark shell")
    shell_parser.set_defaults(func=cmd_shell)

    # Parse arguments
    args = parser.parse_args()

    # Initialize configuration with CLI overrides
    config_args = {}
    if args.output:
        config_args["output_format"] = args.output
    if args.config:
        config_args["config_file"] = Path(args.config)

    config = init_config(database=args.db, **config_args)

    # Set default output format if not specified
    if not args.output:
        args.output = config.output_format

    # Execute command
    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()