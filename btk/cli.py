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
from typing import List
from rich.console import Console
from rich.table import Table
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

    # Auto-detect media type unless disabled
    if not getattr(args, 'no_media_detect', False):
        from btk.media_detector import MediaDetector
        detector = MediaDetector()
        media_info = detector.detect(args.url)

        if media_info:
            # Update bookmark with detected media info
            updates = {
                'media_type': media_info.media_type,
                'media_source': media_info.source,
                'media_id': media_info.media_id,
            }

            # Optionally fetch full metadata
            if getattr(args, 'fetch_metadata', False):
                try:
                    from btk.media_fetcher import MediaFetcher
                    fetcher = MediaFetcher()
                    metadata = fetcher.fetch(args.url, media_info)

                    if metadata:
                        if metadata.title and not args.title:
                            updates['title'] = metadata.title
                        if metadata.description:
                            updates['description'] = metadata.description
                        if metadata.author_name:
                            updates['author_name'] = metadata.author_name
                        if metadata.author_url:
                            updates['author_url'] = metadata.author_url
                        if metadata.thumbnail_url:
                            updates['thumbnail_url'] = metadata.thumbnail_url
                        if metadata.published_at:
                            updates['published_at'] = metadata.published_at
                        if metadata.tags and not args.tags:
                            # Add fetched tags
                            for tag in metadata.tags[:5]:
                                db.tag_bookmark(bookmark.id, tag)
                except Exception as e:
                    if not args.quiet:
                        print(f"Warning: Could not fetch metadata: {e}", file=sys.stderr)

            # Apply media updates
            db.update(bookmark.id, **updates)
            bookmark = db.get(bookmark.id)  # Refresh

            if not args.quiet:
                print(f"Detected: {media_info.source} {media_info.media_type}", file=sys.stderr)

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
                console.print("  [yellow]Content changed[/yellow]")
            if result.get("title_updated"):
                console.print("  [yellow]Title updated[/yellow]")
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

        still_unreachable = 0
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
                still_unreachable += 1

        console.print(f"\n[green]✓ Recovered {recovered_count} bookmarks[/green]")
        if still_unreachable > 0:
            console.print(f"[yellow]Still unreachable: {still_unreachable}[/yellow]")

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

        if not cache and not args.fetch:
            console.print("[yellow]No cached content available[/yellow]")
            return

        if args.fetch:
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
            console.print("[yellow]No cached content available[/yellow]")
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
    import os
    from btk.models import ContentCache
    from sqlalchemy import select
    # Import the NLP tagger
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'auto_tag_nlp'))
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
                console.print("\n[yellow]No new tags to add[/yellow]")

    elif args.all:
        # Auto-tag all bookmarks (single-threaded for stability)
        bookmarks = db.all()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Auto-tagging bookmarks...", total=len(bookmarks))

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
            console.print("\n[yellow]Preview mode - use --apply to save tags[/yellow]")

    else:
        console.print("[red]Error: Must specify --id or --all[/red]")
        sys.exit(1)


def cmd_preserve(args):
    """Preserve media content (thumbnails, transcripts, PDF text) for Long Echo."""
    from btk.preservation import (
        PreservationManager, preserve_bookmark
    )

    db = get_db(args.db)
    manager = PreservationManager()

    if args.id:
        # Preserve specific bookmark
        bookmark = db.get(id=int(args.id))
        if not bookmark:
            console.print(f"[red]Bookmark not found: {args.id}[/red]")
            sys.exit(1)

        if args.dry_run:
            preserver = manager.get_preserver_for_url(bookmark.url)
            if preserver:
                console.print(f"[cyan]Would preserve:[/cyan] {bookmark.title}")
                console.print(f"  URL: {bookmark.url}")
                console.print(f"  Preserver: {preserver.metadata.name}")
            else:
                console.print(f"[yellow]No preserver available for:[/yellow] {bookmark.url}")
            return

        console.print(f"[cyan]Preserving:[/cyan] {bookmark.title}")
        result = preserve_bookmark(db, bookmark.id, manager)

        if result and result.success:
            console.print("[green]✓ Preserved successfully[/green]")
            if result.transcript_text:
                console.print(f"  Transcript: {len(result.transcript_text)} chars")
            if result.thumbnail_data:
                console.print(f"  Thumbnail: {len(result.thumbnail_data)} bytes")
            if result.extracted_text:
                console.print(f"  Extracted text: {result.word_count} words")
        elif result:
            console.print(f"[red]✗ Failed: {result.error_message}[/red]")
        else:
            console.print("[yellow]No preserver available for this URL[/yellow]")

    elif args.all:
        # Preserve all preservable bookmarks
        media_types = [args.type] if args.type else None

        # Get bookmarks - extract needed data within session
        from btk.models import Bookmark
        with db.session(expire_on_commit=False) as session:
            query = session.query(Bookmark)
            if media_types:
                type_map = {'video': 'video', 'pdf': 'document', 'image': 'image'}
                db_type = type_map.get(args.type, args.type)
                query = query.filter(Bookmark.media_type == db_type)
            bookmarks = query.all()
            # Extract what we need before leaving session
            bookmark_data = [
                {'id': b.id, 'url': b.url, 'title': b.title}
                for b in bookmarks
            ]

        preservable = [b for b in bookmark_data if manager.can_preserve(b['url'])]
        if args.limit:
            preservable = preservable[:args.limit]

        if args.dry_run:
            console.print(f"\n[cyan]Would preserve {len(preservable)} bookmarks:[/cyan]\n")
            by_type = {}
            for b in preservable[:20]:
                preserver = manager.get_preserver_for_url(b['url'])
                ptype = preserver.metadata.name if preserver else 'unknown'
                by_type[ptype] = by_type.get(ptype, 0) + 1
                console.print(f"  • {b['title'][:60]}... ({ptype})")

            if len(preservable) > 20:
                console.print(f"  ... and {len(preservable) - 20} more")

            console.print("\n[cyan]By preserver type:[/cyan]")
            for ptype, count in sorted(by_type.items()):
                console.print(f"  {ptype}: {count}")
            return

        # Preserve with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Preserving...", total=len(preservable))
            success_count = 0
            fail_count = 0

            for bm_data in preservable:
                progress.update(task, description=f"Preserving: {bm_data['title'][:40]}...")
                try:
                    result = preserve_bookmark(db, bm_data['id'], manager)
                    if result and result.success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    console.print(f"[red]Error preserving {bm_data['id']}: {e}[/red]")
                progress.advance(task)

        console.print(f"\n[green]✓ Preserved {success_count} bookmarks[/green]")
        if fail_count > 0:
            console.print(f"[yellow]✗ Failed: {fail_count}[/yellow]")

    else:
        console.print("[red]Error: Must specify --id or --all[/red]")
        sys.exit(1)


def cmd_preserve_status(args):
    """Show preservation statistics."""
    from btk.preservation import PreservationManager
    from btk.models import Bookmark, ContentCache

    db = get_db(args.db)
    manager = PreservationManager()

    with db.session() as session:
        # Total counts
        total_bookmarks = session.query(Bookmark).count()
        with_content = session.query(ContentCache).count()

        # Count preservable URLs
        bookmarks = session.query(Bookmark).all()
        preservable_count = sum(1 for b in bookmarks if manager.can_preserve(b.url))

        # Count by type
        by_type = {}
        for b in bookmarks:
            if manager.can_preserve(b.url):
                preserver = manager.get_preserver_for_url(b.url)
                if preserver:
                    ptype = preserver.metadata.name
                    by_type[ptype] = by_type.get(ptype, 0) + 1

        # Count with transcripts (have markdown content that includes "Transcript")
        with_transcript = session.query(ContentCache).filter(
            ContentCache.markdown_content.like('%## Transcript%')
        ).count()

    console.print("\n[bold cyan]Preservation Status[/bold cyan]\n")
    console.print(f"Total bookmarks:     {total_bookmarks:,}")
    console.print(f"With cached content: {with_content:,} ({100*with_content/total_bookmarks:.1f}%)")
    console.print(f"Preservable URLs:    {preservable_count:,} ({100*preservable_count/total_bookmarks:.1f}%)")
    console.print(f"With transcripts:    {with_transcript:,}")

    console.print("\n[cyan]Preservable by type:[/cyan]")
    for ptype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        console.print(f"  {ptype}: {count:,}")

    console.print("\n[cyan]Available preservers:[/cyan]")
    for p in manager.list_preservers():
        console.print(f"  • {p['name']}: {p['description']}")


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


def cmd_query_flags(args):
    """
    Composable flag-based bookmark query.

    Combines filters with AND logic. Use --no-* flags for negation.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_, or_
    from btk.models import Bookmark, Tag

    db = get_db(args.db)

    # Start with all bookmarks (or from a view if specified)
    filters = []

    # Handle view base if specified
    if args.view:
        from btk.views import ViewRegistry, ViewContext
        from pathlib import Path

        # Create registry and load built-in views
        registry = ViewRegistry()

        # Try to load custom views from default locations
        config = get_config()
        default_paths = [
            Path("btk-views.yaml"),
            Path("btk-views.yml"),
            Path(config.database).parent / "btk-views.yaml",
            Path.home() / ".config" / "btk" / "views.yaml",
        ]
        for path in default_paths:
            if path.exists():
                try:
                    registry.load_file(path)
                except Exception:
                    pass

        if not registry.has(args.view):
            console.print(f"[red]View not found: {args.view}[/red]")
            console.print("[dim]Use 'btk view list' to see available views[/dim]")
            sys.exit(1)
        view = registry.get(args.view)
        ctx = ViewContext(registry=registry)
        result = view.evaluate(db, ctx)
        base_ids = [b.id for b in result.bookmarks]
        if not base_ids:
            # View returned empty, output accordingly
            output_bookmarks([], args.output)
            return
        filters.append(Bookmark.id.in_(base_ids))

    # Starred filter
    if args.starred:
        filters.append(Bookmark.stars == True)
    elif args.no_starred:
        filters.append(Bookmark.stars == False)

    # Recent filter (added in last 7 days)
    if args.recent:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        filters.append(Bookmark.added >= cutoff)
    elif args.no_recent:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        filters.append(Bookmark.added < cutoff)

    # Unread filter (never visited)
    if args.unread:
        filters.append(Bookmark.visit_count == 0)
    elif args.no_unread:
        filters.append(Bookmark.visit_count > 0)

    # Archived filter
    if args.archived:
        filters.append(Bookmark.archived == True)
    elif args.no_archived:
        filters.append(Bookmark.archived == False)

    # Pinned filter
    if args.pinned:
        filters.append(Bookmark.pinned == True)
    elif args.no_pinned:
        filters.append(Bookmark.pinned == False)

    # Tagged filter (comma-separated tags, matches ANY)
    if args.tagged:
        tag_names = [t.strip() for t in args.tagged.split(',')]
        filters.append(Bookmark.tags.any(Tag.name.in_(tag_names)))
    elif args.no_tagged:
        tag_names = [t.strip() for t in args.no_tagged.split(',')]
        filters.append(~Bookmark.tags.any(Tag.name.in_(tag_names)))

    # Domain filter
    if args.domain:
        # Match bookmarks where URL contains the domain
        domain = args.domain.lower()
        filters.append(Bookmark.url.ilike(f'%{domain}%'))
    elif args.no_domain:
        domain = args.no_domain.lower()
        filters.append(~Bookmark.url.ilike(f'%{domain}%'))

    # Full-text search
    search_term = args.search
    if search_term:
        search_pattern = f'%{search_term}%'
        filters.append(or_(
            Bookmark.title.ilike(search_pattern),
            Bookmark.url.ilike(search_pattern),
            Bookmark.description.ilike(search_pattern)
        ))

    # Build query
    with db.session(expire_on_commit=False) as session:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        query = select(Bookmark).options(selectinload(Bookmark.tags))

        # Apply all filters with AND
        if filters:
            query = query.where(and_(*filters))

        # Exclude archived by default unless explicitly requested
        if not args.archived and not args.no_archived:
            query = query.where(Bookmark.archived == False)

        # Order by
        order_field = args.order or 'added'
        order_map = {
            'added': Bookmark.added.desc(),
            'title': Bookmark.title.asc(),
            'visits': Bookmark.visit_count.desc(),
            'visited': Bookmark.last_visited.desc(),
            'stars': Bookmark.stars.desc(),
        }
        if order_field in order_map:
            query = query.order_by(order_map[order_field])

        # Apply limit and offset
        if args.offset:
            query = query.offset(args.offset)
        limit = args.limit if args.limit else 20  # Default limit
        query = query.limit(limit)

        # Execute query
        bookmarks = list(session.scalars(query).all())

        # Force load tags before session closes
        for b in bookmarks:
            _ = [t.name for t in b.tags]

        # Output results within session context
        output_bookmarks(bookmarks, args.output)


def cmd_add_shortcut(args):
    """Add a bookmark (shortcut for 'btk bookmark add')."""
    db = get_db(args.db)

    tags = [t.strip() for t in args.tags.split(',')] if args.tags else []

    try:
        bookmark = db.add(
            url=args.url,
            title=args.title,
            description=args.description,
            tags=tags,
            stars=args.star
        )
        if bookmark:
            console.print(f"[green]✓[/green] Added bookmark: {bookmark.id} - {bookmark.title[:50]}")
            if tags:
                console.print(f"  Tags: {', '.join(tags)}")
        else:
            console.print("[yellow]Bookmark already exists (duplicate URL)[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def _resolve_bookmark(db, identifier):
    """Look up a bookmark by numeric ID or unique_id string."""
    try:
        return db.get(id=int(identifier))
    except ValueError:
        return db.get(unique_id=identifier)


def cmd_open_shortcut(args):
    """Open a bookmark in browser (shortcut)."""
    import webbrowser
    from datetime import datetime, timezone

    db = get_db(args.db)
    bookmark = _resolve_bookmark(db, args.id)

    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    # Open in browser
    webbrowser.open(bookmark.url)
    console.print(f"[green]Opened:[/green] {bookmark.title[:60]}")

    # Update visit count and last_visited
    db.update(
        bookmark.id,
        visit_count=bookmark.visit_count + 1,
        last_visited=datetime.now(timezone.utc)
    )


def cmd_star_shortcut(args):
    """Star a bookmark (shortcut)."""
    db = get_db(args.db)
    bookmark = _resolve_bookmark(db, args.id)

    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    if bookmark.stars:
        console.print(f"[yellow]Already starred:[/yellow] {bookmark.title[:50]}")
    else:
        db.update(bookmark.id, stars=True)
        console.print(f"[green]★ Starred:[/green] {bookmark.title[:50]}")


def cmd_unstar_shortcut(args):
    """Unstar a bookmark (shortcut)."""
    db = get_db(args.db)
    bookmark = _resolve_bookmark(db, args.id)

    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    if not bookmark.stars:
        console.print(f"[yellow]Not starred:[/yellow] {bookmark.title[:50]}")
    else:
        db.update(bookmark.id, stars=False)
        console.print(f"[dim]☆ Unstarred:[/dim] {bookmark.title[:50]}")


def cmd_tag_shortcut(args):
    """Add tags to a bookmark (shortcut)."""
    db = get_db(args.db)
    bookmark = _resolve_bookmark(db, args.id)

    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    new_tags = [t.strip() for t in args.tags.split(',')]
    existing_tags = [t.name for t in bookmark.tags]
    merged_tags = list(set(existing_tags + new_tags))

    db.update(bookmark.id, tags=merged_tags)
    console.print(f"[green]Tagged:[/green] {bookmark.title[:50]}")
    console.print(f"  Tags: {', '.join(merged_tags)}")


def cmd_untag_shortcut(args):
    """Remove tags from a bookmark (shortcut)."""
    db = get_db(args.db)
    bookmark = _resolve_bookmark(db, args.id)

    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    tags_to_remove = set(t.strip() for t in args.tags.split(','))
    existing_tags = [t.name for t in bookmark.tags]
    remaining_tags = [t for t in existing_tags if t not in tags_to_remove]

    db.update(bookmark.id, tags=remaining_tags)
    console.print(f"[green]Untagged:[/green] {bookmark.title[:50]}")
    if remaining_tags:
        console.print(f"  Remaining tags: {', '.join(remaining_tags)}")


def cmd_rm_shortcut(args):
    """Delete a bookmark (shortcut for 'btk bookmark delete')."""
    db = get_db(args.db)
    bookmark = _resolve_bookmark(db, args.id)

    if not bookmark:
        console.print(f"[red]Bookmark not found: {args.id}[/red]")
        sys.exit(1)

    title = bookmark.title
    if db.delete(bookmark.id):
        console.print(f"[green]✓[/green] Deleted: {title[:50]}")
    else:
        console.print("[red]Failed to delete bookmark[/red]")
        sys.exit(1)


def cmd_activity(args):
    """Show activity log from events table."""
    from btk.models import Event
    from sqlalchemy import select

    db = get_db(args.db)
    limit = args.limit if args.limit else 20

    with db.session() as session:
        query = select(Event).order_by(Event.timestamp.desc()).limit(limit)
        events = list(session.scalars(query).all())

        if not events:
            console.print("[yellow]No activity found[/yellow]")
            return

        if args.output == 'json':
            import json
            data = [{
                'id': e.id,
                'event_type': e.event_type,
                'entity_type': e.entity_type,
                'entity_id': e.entity_id,
                'entity_url': e.entity_url,
                'timestamp': e.timestamp.isoformat(),
                'data': e.event_data
            } for e in events]
            print(json.dumps(data, indent=2))
        else:
            from rich.table import Table
            table = Table(title="Recent Activity")
            table.add_column("Time", style="dim")
            table.add_column("Event", style="cyan")
            table.add_column("Entity")
            table.add_column("Details", style="dim")

            for e in events:
                time_str = e.timestamp.strftime("%Y-%m-%d %H:%M")
                entity_str = f"{e.entity_type}#{e.entity_id}" if e.entity_id else e.entity_type
                details = ""
                if e.entity_url:
                    details = e.entity_url[:40] + "..." if len(e.entity_url) > 40 else e.entity_url
                table.add_row(time_str, e.event_type, entity_str, details)

            console.print(table)


def cmd_stats(args):
    """Show quick database statistics."""
    db = get_db(args.db)
    stats = db.stats()

    if args.output == 'json':
        import json
        print(json.dumps(stats, indent=2, default=str))
    else:
        from rich.table import Table
        table = Table(title="Database Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Total Bookmarks", str(stats.get('total_bookmarks', 0)))
        table.add_row("Total Tags", str(stats.get('total_tags', 0)))
        table.add_row("Starred", str(stats.get('starred_count', 0)))
        table.add_row("Total Visits", str(stats.get('total_visits', 0)))
        if 'database_size' in stats:
            size_mb = stats['database_size'] / 1024 / 1024
            table.add_row("Database Size", f"{size_mb:.1f} MB")
        if 'database_path' in stats:
            table.add_row("Database", stats['database_path'])

        console.print(table)


def cmd_health(args):
    """Check health of bookmark URLs."""
    from btk.health_checker import run_health_check, summarize_results

    db = get_db(args.db)

    # Determine which bookmarks to check
    if args.id:
        bookmarks = []
        for bid in args.id:
            try:
                bookmark = db.get(id=int(bid))
            except ValueError:
                bookmark = db.get(unique_id=bid)
            if bookmark:
                bookmarks.append(bookmark)
            else:
                console.print(f"[yellow]Warning: Bookmark not found: {bid}[/yellow]")
    elif args.broken:
        bookmarks = db.search(reachable=False)
        if not bookmarks:
            console.print("[green]No broken bookmarks found![/green]")
            return
    elif args.unchecked:
        # Get bookmarks that have never been checked (reachable is None)
        with db.session() as session:
            from sqlalchemy import select
            stmt = select(Bookmark).where(Bookmark.reachable.is_(None))
            bookmarks = list(session.scalars(stmt).all())
        if not bookmarks:
            console.print("[green]All bookmarks have been checked![/green]")
            return
    else:
        bookmarks = db.all()

    if not bookmarks:
        console.print("[yellow]No bookmarks to check[/yellow]")
        return

    console.print(f"Checking {len(bookmarks)} bookmark(s)...")

    # Prepare bookmark list for health checker
    bookmark_list = [(b.id, b.url) for b in bookmarks]

    # Progress callback
    def progress_callback(completed, total):
        pass  # We'll use rich progress instead

    # Run health check with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"Checking 0/{len(bookmark_list)} URLs...", total=len(bookmark_list))

        checked = [0]

        def update_progress(completed, total):
            checked[0] = completed
            progress.update(task, description=f"Checking {completed}/{total} URLs...")
            progress.update(task, completed=completed)

        results = run_health_check(
            bookmark_list,
            concurrency=args.concurrency,
            timeout=args.timeout,
            progress_callback=update_progress
        )

    # Update database with results
    if not args.dry_run:
        updated_count = 0
        for result in results:
            db.update(result.bookmark_id, reachable=result.is_reachable)
            updated_count += 1

    # Generate summary
    summary = summarize_results(results)

    # Output results
    if args.output == "json":
        output_data = {
            "summary": summary,
            "results": [r.to_dict() for r in results] if args.verbose else []
        }
        print(json.dumps(output_data, indent=2, default=str))
    else:
        # Display summary table
        table = Table(title="Health Check Results")
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green")

        for status, count in summary["by_status"].items():
            style = "green" if status in ("ok", "redirect") else "red"
            table.add_row(status, str(count), style=style)

        table.add_row("─" * 15, "─" * 5)
        table.add_row("Reachable", str(summary["reachable"]), style="green")
        table.add_row("Unreachable", str(summary["unreachable"]), style="red")

        if summary["avg_response_time_ms"]:
            table.add_row("Avg Response", f"{summary['avg_response_time_ms']:.0f}ms")

        console.print(table)

        # Show broken bookmarks
        if summary["broken_bookmarks"] and (args.verbose or len(summary["broken_bookmarks"]) <= 10):
            console.print("\n[red]Broken Bookmarks:[/red]")
            for broken in summary["broken_bookmarks"]:
                console.print(f"  [{broken['id']}] {broken['url'][:60]}")
                console.print(f"       Status: {broken['status']}, Error: {broken.get('error', 'N/A')}")

        # Show redirected bookmarks if verbose
        if args.verbose and summary["redirected_bookmarks"]:
            console.print("\n[yellow]Redirected Bookmarks:[/yellow]")
            for redir in summary["redirected_bookmarks"]:
                console.print(f"  [{redir['id']}] {redir['url'][:50]}")
                console.print(f"       → {redir['redirect_url'][:50]}")

        if not args.dry_run:
            console.print(f"\n[green]✓ Updated {updated_count} bookmarks in database[/green]")
        else:
            console.print("\n[yellow]Dry run - no changes made to database[/yellow]")


def cmd_queue(args):
    """Manage reading queue."""
    from btk.reading_queue import (
        get_queue, get_queue_stats, get_next_to_read,
        add_to_queue, remove_from_queue, update_progress, set_priority
    )

    db = get_db(args.db)
    cmd = args.queue_command

    if cmd == "list":
        sort_by = args.sort or 'priority'
        queue = get_queue(db, include_completed=args.all, sort_by=sort_by)

        if not queue:
            console.print("[yellow]Reading queue is empty[/yellow]")
            return

        if args.output == "json":
            data = [item.to_dict() for item in queue]
            print(json.dumps(data, indent=2))
        else:
            table = Table(title="Reading Queue")
            table.add_column("ID", style="cyan")
            table.add_column("Title", style="green")
            table.add_column("Progress", style="blue")
            table.add_column("Pri", style="yellow")
            table.add_column("Queued", style="magenta")

            for item in queue:
                progress_bar = f"[{'█' * (item.progress // 10)}{'░' * (10 - item.progress // 10)}] {item.progress}%"
                queued = item.queued_at.strftime("%Y-%m-%d") if item.queued_at else "N/A"
                table.add_row(
                    str(item.bookmark.id),
                    item.bookmark.title[:40],
                    progress_bar,
                    str(item.priority),
                    queued
                )

            console.print(table)

    elif cmd == "add":
        for bid in args.ids:
            try:
                bookmark_id = int(bid)
            except ValueError:
                bookmark = db.get(unique_id=bid)
                bookmark_id = bookmark.id if bookmark else None

            if bookmark_id and add_to_queue(db, bookmark_id, priority=args.priority):
                console.print(f"[green]✓ Added bookmark {bid} to reading queue[/green]")
            else:
                console.print(f"[red]✗ Failed to add bookmark {bid}[/red]")

    elif cmd == "remove":
        for bid in args.ids:
            try:
                bookmark_id = int(bid)
            except ValueError:
                bookmark = db.get(unique_id=bid)
                bookmark_id = bookmark.id if bookmark else None

            if bookmark_id and remove_from_queue(db, bookmark_id):
                console.print(f"[green]✓ Removed bookmark {bid} from reading queue[/green]")
            else:
                console.print(f"[red]✗ Failed to remove bookmark {bid}[/red]")

    elif cmd == "progress":
        try:
            bookmark_id = int(args.id)
        except ValueError:
            bookmark = db.get(unique_id=args.id)
            bookmark_id = bookmark.id if bookmark else None

        if bookmark_id and update_progress(db, bookmark_id, args.percent):
            console.print(f"[green]✓ Updated progress to {args.percent}%[/green]")
            if args.percent >= 100:
                console.print("[blue]Item marked as complete and removed from queue[/blue]")
        else:
            console.print("[red]✗ Failed to update progress[/red]")

    elif cmd == "priority":
        try:
            bookmark_id = int(args.id)
        except ValueError:
            bookmark = db.get(unique_id=args.id)
            bookmark_id = bookmark.id if bookmark else None

        if bookmark_id and set_priority(db, bookmark_id, args.level):
            console.print(f"[green]✓ Set priority to {args.level}[/green]")
        else:
            console.print("[red]✗ Failed to set priority[/red]")

    elif cmd == "next":
        item = get_next_to_read(db)
        if item:
            if args.output == "json":
                print(json.dumps(item.to_dict(), indent=2))
            else:
                console.print("[bold green]Next to read:[/bold green]")
                console.print(f"  [{item.bookmark.id}] {item.bookmark.title}")
                console.print(f"  URL: {item.bookmark.url}")
                console.print(f"  Progress: {item.progress}% | Priority: {item.priority}")
        else:
            console.print("[yellow]Reading queue is empty[/yellow]")

    elif cmd == "stats":
        stats = get_queue_stats(db)

        if args.output == "json":
            print(json.dumps(stats, indent=2))
        else:
            table = Table(title="Reading Queue Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total in Queue", str(stats['total']))
            table.add_row("Not Started", str(stats['not_started']))
            table.add_row("In Progress", str(stats['in_progress']))
            table.add_row("Completed", str(stats['completed']))
            table.add_row("Average Progress", f"{stats['avg_progress']}%")

            if stats['estimated_remaining_time']:
                hours = stats['estimated_remaining_time'] // 60
                mins = stats['estimated_remaining_time'] % 60
                table.add_row("Est. Remaining Time", f"{hours}h {mins}m")

            console.print(table)

            if stats['by_priority']:
                console.print("\n[bold]By Priority:[/bold]")
                for p, count in sorted(stats['by_priority'].items()):
                    console.print(f"  Priority {p}: {count} items")

    elif cmd == "estimate-times":
        from btk.reading_queue import auto_estimate_queue_times

        console.print("Estimating reading times from cached content...")

        estimates = auto_estimate_queue_times(db, overwrite=args.overwrite if hasattr(args, 'overwrite') else False)

        if estimates:
            if args.output == "json":
                print(json.dumps(estimates, indent=2))
            else:
                table = Table(title="Reading Time Estimates")
                table.add_column("ID", style="cyan")
                table.add_column("Est. Time", style="green")

                for bid, minutes in estimates.items():
                    hours = minutes // 60
                    mins = minutes % 60
                    time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                    table.add_row(str(bid), time_str)

                console.print(table)
                console.print(f"\n[green]✓ Updated {len(estimates)} items[/green]")
        else:
            console.print("[yellow]No items to estimate (all have estimates or no cached content)[/yellow]")


def cmd_media(args):
    """Media detection and management operations."""
    from btk.media_detector import MediaDetector
    from btk.media_fetcher import MediaFetcher, YtDlpNotAvailableError, MediaFetchError

    db = get_db(args.db)
    cmd = args.media_command
    detector = MediaDetector()

    if cmd == "detect":
        # Detect media in bookmarks
        if hasattr(args, 'id') and args.id:
            bookmarks = [db.get(args.id)]
            if not bookmarks[0]:
                console.print(f"[red]Bookmark {args.id} not found[/red]")
                return
        elif hasattr(args, 'undetected') and args.undetected:
            all_bookmarks = db.list()
            bookmarks = [b for b in all_bookmarks if b.media_type is None]
        else:
            bookmarks = db.list()

        detected_count = 0
        for bookmark in bookmarks:
            info = detector.detect(bookmark.url)
            if info:
                db.update(bookmark.id,
                         media_type=info.media_type,
                         media_source=info.source,
                         media_id=info.media_id)
                detected_count += 1
                if args.output != "json":
                    console.print(f"[green]✓[/green] [{bookmark.id}] {info.source}/{info.media_type}: {bookmark.title[:40]}")

        if args.output == "json":
            print(json.dumps({"detected": detected_count, "total": len(bookmarks)}))
        else:
            console.print(f"\n[green]✓ Detected {detected_count}/{len(bookmarks)} media bookmarks[/green]")

    elif cmd == "refresh":
        # Refresh media metadata using fetcher
        fetcher = MediaFetcher()

        if not fetcher.yt_dlp_available:
            console.print("[yellow]Note: yt-dlp not available. Some metadata may be incomplete.[/yellow]")
            console.print("[dim]Install with: pip install yt-dlp[/dim]\n")

        # Get bookmarks to refresh
        if hasattr(args, 'id') and args.id:
            bookmarks = [db.get(args.id)]
            if not bookmarks[0]:
                console.print(f"[red]Bookmark {args.id} not found[/red]")
                return
        elif hasattr(args, 'source') and args.source:
            all_bookmarks = db.list()
            bookmarks = [b for b in all_bookmarks if b.media_source == args.source]
        else:
            all_bookmarks = db.list()
            bookmarks = [b for b in all_bookmarks if b.media_type is not None]

        refreshed_count = 0
        for bookmark in bookmarks:
            try:
                info = detector.detect(bookmark.url)
                if info:
                    metadata = fetcher.fetch(bookmark.url, info)
                    updates = {}
                    if metadata.author_name:
                        updates['author_name'] = metadata.author_name
                    if metadata.author_url:
                        updates['author_url'] = metadata.author_url
                    if metadata.thumbnail_url:
                        updates['thumbnail_url'] = metadata.thumbnail_url
                    if metadata.published_at:
                        updates['published_at'] = metadata.published_at

                    if updates:
                        db.update(bookmark.id, **updates)
                        refreshed_count += 1
                        if args.output != "json":
                            console.print(f"[green]✓[/green] [{bookmark.id}] {bookmark.title[:40]}")
            except Exception as e:
                if args.output != "json":
                    console.print(f"[red]✗[/red] [{bookmark.id}] Error: {e}")

        if args.output == "json":
            print(json.dumps({"refreshed": refreshed_count, "total": len(bookmarks)}))
        else:
            console.print(f"\n[green]✓ Refreshed {refreshed_count}/{len(bookmarks)} media bookmarks[/green]")

    elif cmd == "list":
        # List media bookmarks with filters
        all_bookmarks = db.list()

        # Apply filters
        bookmarks = [b for b in all_bookmarks if b.media_type is not None]

        if hasattr(args, 'type') and args.type:
            bookmarks = [b for b in bookmarks if b.media_type == args.type]

        if hasattr(args, 'source') and args.source:
            bookmarks = [b for b in bookmarks if b.media_source == args.source]

        # Apply limit
        limit = getattr(args, 'limit', 50) or 50
        bookmarks = bookmarks[:limit]

        if args.output == "json":
            data = [{
                'id': b.id,
                'title': b.title,
                'url': b.url,
                'media_type': b.media_type,
                'media_source': b.media_source,
                'author_name': b.author_name,
            } for b in bookmarks]
            print(json.dumps(data, indent=2))
        else:
            table = Table(title="Media Bookmarks")
            table.add_column("ID", style="cyan")
            table.add_column("Type", style="blue")
            table.add_column("Source", style="magenta")
            table.add_column("Title", style="white")

            for b in bookmarks:
                table.add_row(
                    str(b.id),
                    b.media_type or "-",
                    b.media_source or "-",
                    b.title[:50]
                )

            console.print(table)
            console.print(f"\n[dim]Showing {len(bookmarks)} media bookmarks[/dim]")

    elif cmd == "import-playlist":
        # Import from playlist URL
        fetcher = MediaFetcher()

        if not fetcher.yt_dlp_available:
            console.print("[red]Error: yt-dlp is required for playlist import[/red]")
            console.print("[dim]Install with: pip install yt-dlp[/dim]")
            return

        url = args.url
        tags = args.tags.split(',') if hasattr(args, 'tags') and args.tags else []
        limit = getattr(args, 'limit', None)

        console.print(f"[blue]Importing playlist: {url}[/blue]")

        try:
            items = fetcher.fetch_playlist(url)
            if limit:
                items = items[:limit]

            imported_count = 0
            for item in items:
                if item.original_url:
                    try:
                        info = detector.detect(item.original_url)
                        bookmark_id = db.add(
                            url=item.original_url,
                            title=item.title or "Untitled",
                            description=item.description,
                            tags=tags,
                            skip_duplicates=True
                        )
                        if bookmark_id and info:
                            db.update(bookmark_id,
                                     media_type=info.media_type,
                                     media_source=info.source,
                                     media_id=info.media_id,
                                     author_name=item.author_name,
                                     author_url=item.author_url,
                                     thumbnail_url=item.thumbnail_url,
                                     published_at=item.published_at)
                            imported_count += 1
                            console.print(f"[green]✓[/green] {item.title[:50]}")
                    except Exception as e:
                        console.print(f"[red]✗[/red] {item.title[:50] if item.title else 'Unknown'}: {e}")

            console.print(f"\n[green]✓ Imported {imported_count}/{len(items)} items from playlist[/green]")

        except YtDlpNotAvailableError as e:
            console.print(f"[red]Error: {e}[/red]")
        except MediaFetchError as e:
            console.print(f"[red]Error fetching playlist: {e}[/red]")

    elif cmd == "import-channel":
        # Import from channel URL
        fetcher = MediaFetcher()

        if not fetcher.yt_dlp_available:
            console.print("[red]Error: yt-dlp is required for channel import[/red]")
            console.print("[dim]Install with: pip install yt-dlp[/dim]")
            return

        url = args.url
        tags = args.tags.split(',') if hasattr(args, 'tags') and args.tags else []
        limit = getattr(args, 'limit', None)

        console.print(f"[blue]Importing channel: {url}[/blue]")

        try:
            items = fetcher.fetch_channel(url, limit=limit)

            imported_count = 0
            for item in items:
                if item.original_url:
                    try:
                        info = detector.detect(item.original_url)
                        bookmark_id = db.add(
                            url=item.original_url,
                            title=item.title or "Untitled",
                            description=item.description,
                            tags=tags,
                            skip_duplicates=True
                        )
                        if bookmark_id and info:
                            db.update(bookmark_id,
                                     media_type=info.media_type,
                                     media_source=info.source,
                                     media_id=info.media_id,
                                     author_name=item.author_name,
                                     author_url=item.author_url,
                                     thumbnail_url=item.thumbnail_url,
                                     published_at=item.published_at)
                            imported_count += 1
                            console.print(f"[green]✓[/green] {item.title[:50]}")
                    except Exception as e:
                        console.print(f"[red]✗[/red] {item.title[:50] if item.title else 'Unknown'}: {e}")

            console.print(f"\n[green]✓ Imported {imported_count}/{len(items)} items from channel[/green]")

        except YtDlpNotAvailableError as e:
            console.print(f"[red]Error: {e}[/red]")
        except MediaFetchError as e:
            console.print(f"[red]Error fetching channel: {e}[/red]")

    elif cmd == "import-podcast":
        # Import from podcast RSS feed
        fetcher = MediaFetcher()

        feed_url = args.feed_url
        tags = args.tags.split(',') if hasattr(args, 'tags') and args.tags else []
        limit = getattr(args, 'limit', None)

        console.print(f"[blue]Importing podcast feed: {feed_url}[/blue]")

        try:
            episodes = fetcher.fetch_podcast_rss(feed_url, limit=limit)

            imported_count = 0
            for episode in episodes:
                if episode.original_url:
                    try:
                        bookmark_id = db.add(
                            url=episode.original_url,
                            title=episode.title or "Untitled Episode",
                            description=episode.description,
                            tags=tags + ['podcast'],
                            skip_duplicates=True
                        )
                        if bookmark_id:
                            db.update(bookmark_id,
                                     media_type='audio',
                                     media_source='podcast',
                                     author_name=episode.author_name,
                                     thumbnail_url=episode.thumbnail_url,
                                     published_at=episode.published_at)
                            imported_count += 1
                            console.print(f"[green]✓[/green] {episode.title[:50]}")
                    except Exception as e:
                        console.print(f"[red]✗[/red] {episode.title[:50] if episode.title else 'Unknown'}: {e}")

            console.print(f"\n[green]✓ Imported {imported_count}/{len(episodes)} podcast episodes[/green]")

        except MediaFetchError as e:
            console.print(f"[red]Error fetching podcast: {e}[/red]")

    elif cmd == "stats":
        # Show media statistics
        all_bookmarks = db.list()
        media_bookmarks = [b for b in all_bookmarks if b.media_type is not None]

        # Gather statistics
        by_type = {}
        by_source = {}

        for b in media_bookmarks:
            by_type[b.media_type] = by_type.get(b.media_type, 0) + 1
            if b.media_source:
                by_source[b.media_source] = by_source.get(b.media_source, 0) + 1

        stats = {
            'total_media': len(media_bookmarks),
            'total_bookmarks': len(all_bookmarks),
            'media_percentage': round(len(media_bookmarks) / len(all_bookmarks) * 100, 1) if all_bookmarks else 0,
            'by_type': by_type,
            'by_source': by_source,
        }

        if args.output == "json":
            print(json.dumps(stats, indent=2))
        else:
            console.print("\n[bold]Media Statistics[/bold]")
            console.print(f"  Total media bookmarks: [green]{stats['total_media']}[/green] ({stats['media_percentage']}%)\n")

            if by_type:
                console.print("[bold]By Type:[/bold]")
                for media_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
                    console.print(f"  {media_type}: {count}")

            if by_source:
                console.print("\n[bold]By Source:[/bold]")
                for source, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True):
                    console.print(f"  {source}: {count}")


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


def cmd_sql(args):
    """Execute raw SQL queries against the database."""
    import sqlite3
    from btk.config import get_config

    config = get_config()
    db_path = args.db or config.database

    # Read query from args or stdin
    if args.query:
        query = args.query
    elif not sys.stdin.isatty():
        query = sys.stdin.read().strip()
    else:
        console.print("[red]Error: No query provided. Use -e 'query' or pipe SQL via stdin.[/red]")
        sys.exit(1)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(query)

        # Check if this is a SELECT query (returns results)
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            if args.output == "json":
                data = [dict(row) for row in rows]
                print(json.dumps(data, indent=2, default=str))
            elif args.output == "csv":
                writer = csv.writer(sys.stdout)
                writer.writerow(columns)
                for row in rows:
                    writer.writerow(list(row))
            elif args.output == "plain":
                for row in rows:
                    print("\t".join(str(v) if v is not None else "" for v in row))
            else:  # table (default)
                table = Table()
                for col in columns:
                    table.add_column(col, style="cyan")

                for row in rows:
                    table.add_row(*[str(v) if v is not None else "" for v in row])

                console.print(table)
                if not args.quiet:
                    console.print(f"\n[dim]{len(rows)} rows[/dim]")
        else:
            # Non-SELECT query (INSERT, UPDATE, DELETE, etc.)
            conn.commit()
            if not args.quiet:
                console.print(f"[green]Query executed. Rows affected: {cursor.rowcount}[/green]")

        conn.close()

    except sqlite3.Error as e:
        console.print(f"[red]SQL Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# =============================================================================
# Claude Code Skill
# =============================================================================

BTK_SKILL = '''---
name: btk
description: Use this skill when working with btk (Bookmark Toolkit) - a CLI for managing bookmarks with SQLite storage, hierarchical tags, and a typed query DSL. Invoke for bookmark operations, queries, imports/exports, or btk shell navigation.
---

# BTK - Bookmark Toolkit

A CLI tool for managing bookmarks with SQLite storage, hierarchical tags, and a typed query DSL.

## Quick Reference

```bash
# Common operations
btk bookmark add https://example.com --tags "web,tool"
btk bookmark list --limit 10
btk bookmark search "python"
btk query run --name starred --limit 10
btk shell  # Interactive mode
```

## Command Groups

| Command | Purpose |
|---------|---------|
| `btk bookmark` | CRUD operations on bookmarks |
| `btk tag` | Tag management (list, add, remove, rename, copy, stats) |
| `btk query` | Typed query DSL for complex searches |
| `btk import` | Import from HTML, JSON, CSV, YouTube, browser |
| `btk export` | Export to HTML, JSON, CSV, html-app |
| `btk shell` | Interactive filesystem-like navigation |
| `btk serve` | REST API server with web UI |
| `btk sql` | Execute raw SQL queries with `-o json/csv/table/plain` |

## Query DSL (`btk query`)

The query command uses a typed expression language:

### Filter Expressions
```yaml
# Exact match
stars: true
visit_count: 0

# Comparisons
visit_count: ">= 5"
stars: "!= 0"

# Temporal
added: "within 30 days"
added: "before 2024-01-01"

# Collections (with glob support)
tags: "any [ai/*, ml/*]"
tags: "all [python, web]"
domain: [github.com, gitlab.com]

# String matching
url: "contains github"
url: "ends_with .pdf"
title: "starts_with How"
```

### Query Examples
```bash
# Run a named query
btk query run --name starred --limit 10

# Inline YAML query
btk query run --inline '{filter: {url: "contains arxiv"}, sort: "added desc", limit: 5}'

# List available queries
btk query list

# Export results
btk query export recent output.json --format json
```

### Built-in Queries
`all`, `recent`, `starred`, `pinned`, `archived`, `unread`, `popular`, `broken`, `untagged`, `videos`, `pdfs`, `preserved`

## Output Formats

`btk sql` supports `-o` output format:
- `table` (default): Rich formatted table
- `json`: JSON for parsing/piping
- `csv`: CSV format
- `plain`: Raw values, one per line

```bash
btk sql -e "SELECT * FROM bookmarks LIMIT 10" -o json | jq '.[] | .url'
btk sql -e "SELECT url FROM bookmarks WHERE stars=1" -o plain
```

## Shell Mode

`btk shell` provides filesystem-like navigation:

```
/                          # Root
/tags/programming/python/  # Browse by hierarchical tag
/starred/                  # Starred bookmarks
/recent/today/added/       # Time-based navigation
/untagged/                 # Smart collection
/domains/github.com/       # Browse by domain
```

Commands: `ls`, `cd`, `cat <id>`, `open <id>`, `tag <id> <tags>`, `star <id>`

## Database

SQLite at `btk.db` (override with `--db`).

Key tables:
- `bookmarks`: id, url, title, description, added, stars, visit_count, pinned, archived
- `tags`: id, name, description, color
- `bookmark_tags`: bookmark_id, tag_id (many-to-many)
- `content_cache`: Cached page content, transcripts, thumbnails

### SQL Examples
```bash
btk sql -e "SELECT COUNT(*) FROM bookmarks"
btk sql -e "SELECT name, COUNT(*) as c FROM tags t JOIN bookmark_tags bt ON t.id=bt.tag_id GROUP BY name ORDER BY c DESC LIMIT 10"
```

## Import/Export

```bash
# Import
btk import html bookmarks.html
btk import json data.json
btk browser import chrome  # From browser

# Export (syntax: btk export FILE --format FORMAT [filters])
btk export output.json --format json --starred
btk export site/ --format html-app  # Interactive web app
btk query export starred out.json --format json
```

## Tips

1. Use `btk sql -o json` when parsing output programmatically
2. Query DSL supports globs: `tags: "any [ai/*]"` matches ai/ml, ai/nlp, etc.
3. Use `btk shell` for interactive exploration
4. `btk serve` starts a REST API at http://localhost:8000
5. Tags are hierarchical: `programming/python/web`
6. Use `btk examples <topic>` to see detailed examples for any command group
'''


# Examples organized by command group
CLI_EXAMPLES = {
    "bookmark": """
  btk bookmark add https://example.com --title "Example" --tags "web,demo"
  btk bookmark add https://arxiv.org/abs/2301.00001 --tags "ai,papers" --star
  btk bookmark list --limit 10 --sort visit_count
  btk bookmark list --starred              # Filter to starred bookmarks
  btk bookmark search "python tutorial"
  btk bookmark get 123                     # Get bookmark details
  btk bookmark update 123 --title "New Title" --add-tags "important"
  btk bookmark update 123 --star           # Star a bookmark
  btk bookmark update 123 --unstar         # Remove star
  btk bookmark update 123 --archive        # Archive a bookmark
  btk bookmark delete 1 2 3
  btk bookmark health 123                  # Check URL reachability
""",
    "tag": """
  btk tag list                              # List all tags
  btk tag stats                             # Show tag statistics
  btk tag add python 123 456                # Add tag to multiple bookmarks
  btk tag remove python 123                 # Remove tag from bookmark
  btk tag rename "old-name" "new-name"      # Rename a tag
  btk tag copy important --starred          # Copy tag to starred bookmarks
""",
    "queue": """
  btk queue list                            # Show reading queue
  btk queue add 123 456                     # Add bookmarks to queue
  btk queue remove 123                      # Remove from queue
  btk queue next                            # Get next item to read
  btk queue stats                           # Queue statistics
  btk queue priority 123 1                  # Set priority (1=highest, 5=lowest)
  btk queue progress 123 50                 # Update reading progress (50%)
  btk queue estimate-times                  # Auto-estimate reading times
""",
    "content": """
  btk content view 123                      # View cached content (markdown)
  btk content view 123 --html               # View as HTML
  btk content refresh --id 123              # Refresh cached content
  btk content refresh --all                 # Refresh all content
  btk content auto-tag --id 123             # Auto-generate tags with NLP

  # Long Echo preservation (thumbnails, transcripts, PDF text)
  btk content preserve --id 123             # Preserve specific bookmark
  btk content preserve --all --type video   # Preserve all YouTube videos
  btk content preserve --all --limit 50     # Preserve first 50 preservable
  btk content preserve --all --dry-run      # Preview what would be preserved
  btk content preserve-status               # Show preservation statistics
""",
    "import": """
  # File imports
  btk import html bookmarks.html            # Import Netscape HTML
  btk import json data.json                 # Import JSON
  btk import csv bookmarks.csv              # Import CSV
  btk import markdown links.md              # Import Markdown
  btk import text urls.txt                  # Import plain URLs
  btk import html bookmarks.html --dry-run  # Preview import
  btk import json data.json -t work -t ref  # Add custom tags

  # Service imports (see 'btk examples youtube' for more)
  btk import youtube auth                   # Set up YouTube OAuth
  btk import youtube library                # Import liked videos
  btk import youtube playlist PLxxxxxx      # Import a playlist
""",
    "export": """
  btk export data.json --format json        # Export to JSON
  btk export bookmarks.html --format html   # Export Netscape HTML
  btk export bookmarks.csv --format csv     # Export CSV
  btk export links.md --format markdown     # Export Markdown
  btk export output/ --format html-app      # Export interactive HTML app
  btk export - --format json --starred      # Export starred to stdout
  btk export data.json --format json --tags python  # Export by tag
""",
    "db": """
  btk db info                               # Database overview
  btk db stats                              # Detailed statistics
  btk db schema                             # Show database schema
  btk db build-index                        # Build full-text search index
  btk db index-stats                        # Show FTS index statistics
  btk db cleanup                            # Auto-cleanup stale/broken bookmarks
""",
    "view": """
  btk view list                             # List all views
  btk view show videos                      # Show view definition
  btk view eval videos --limit 10           # Evaluate view
  btk view export starred out.json --format json  # Export view results
  btk view create --starred --limit 20      # Ad-hoc view with filters
  btk view create --tags "ai,ml" --order "added desc"
""",
    "query": """
  # List and inspect queries
  btk query list                            # List all registered queries
  btk query show starred                    # Show query definition

  # Run named queries
  btk query run --name starred --limit 10   # Run a built-in query
  btk query run --name recent               # Recent bookmarks
  btk query run --name untagged -o json     # Untagged as JSON

  # Inline YAML queries
  btk query run --inline '{filter: {stars: true}}'
  btk query run --inline '{filter: {url: "contains github"}, sort: "added desc"}'
  btk query run --inline '{filter: {added: "within 30 days"}, limit: 20}'
  btk query run --inline '{filter: {tags: "any [ai/*, ml/*]"}}'

  # Export query results
  btk query export starred out.json --format json
  btk query export recent out.csv --format csv

  # Query DSL expressions:
  #   stars: true                    # Exact match
  #   visit_count: ">= 5"            # Comparison
  #   added: "within 30 days"        # Temporal
  #   tags: "any [python, web]"      # Collection
  #   url: "contains arxiv"          # String matching
  #   tags: missing                  # Existence check
""",
    "sql": """
  btk sql -e "SELECT COUNT(*) FROM bookmarks"
  btk sql -e "SELECT title, url FROM bookmarks WHERE stars = 1" -o csv
  btk sql -e "SELECT name, COUNT(*) as cnt FROM tags t JOIN bookmark_tags bt ON t.id = bt.tag_id GROUP BY name ORDER BY cnt DESC LIMIT 10"
  echo "SELECT * FROM bookmarks LIMIT 5" | btk sql
""",
    "shell": """
  btk shell                                 # Start interactive shell

  # Inside the shell:
  cd /tags/programming/python               # Navigate to tag
  ls                                        # List bookmarks
  cat 123                                   # View bookmark details
  star 123                                  # Star a bookmark
  open 123                                  # Open in browser
""",
    "graph": """
  btk graph build                           # Build similarity graph
  btk graph neighbors 123                   # Find similar bookmarks
  btk graph stats                           # Show graph statistics
  btk graph export graph.html               # Export graph visualization
""",
    "browser": """
  btk browser list                          # List detected browser profiles
  btk browser import chrome                 # Import from Chrome
  btk browser import firefox                # Import from Firefox
""",
    "pipelines": """
  # Unix-style composable pipelines with SQL output
  btk sql -e "SELECT url FROM bookmarks" -o plain | xargs -I {} curl -I {}
  btk sql -e "SELECT url FROM bookmarks WHERE stars=1" -o plain | wc -l
  btk sql -e "SELECT * FROM bookmarks LIMIT 10" -o json | jq '.[] | .url'
""",
    "youtube": """
  # Authentication (required for user-specific imports)
  btk import youtube auth                   # Set up OAuth (opens browser)
  btk import youtube auth -c ~/creds.json   # Use custom credentials file

  # User library imports (require OAuth)
  btk import youtube library                # Import liked videos
  btk import youtube library --limit 50     # Import last 50 liked videos
  btk import youtube subscriptions          # Import subscribed channels
  btk import youtube subscriptions -n 20    # Limit to 20 subscriptions
  btk import youtube playlists --list       # List your playlists
  btk import youtube playlists              # Import playlists as bookmarks
  btk import youtube playlists --import-all # Import all videos from all playlists

  # Public content (API key or OAuth)
  btk import youtube playlist PLxxxxxx      # Import playlist by ID
  btk import youtube playlist "https://youtube.com/playlist?list=PLxxxxxx"
  btk import youtube channel UCxxxxxx       # Import channel videos by ID
  btk import youtube channel @username      # Import by handle
  btk import youtube video dQw4w9WgXcQ      # Import single video
  btk import youtube video "https://youtu.be/xxx"

  # Options
  btk import youtube library --dry-run      # Preview without importing
  btk import youtube channel @3b1b -n 10    # Limit videos
  btk import youtube playlist PLxxx -t math # Add custom tags
""",
    "media": """
  btk media detect                            # Detect media types for all bookmarks
  btk media detect --undetected               # Only scan bookmarks without media_type
  btk media detect --id 123                   # Detect for specific bookmark
  btk media stats                             # Show media type statistics
  btk media list --type video                 # List video bookmarks
  btk media list --type document --limit 20   # List documents with limit
  btk media list --source youtube             # List YouTube videos
""",
    "config": """
  btk config show                             # Show current configuration
  btk config set database ~/bookmarks.db      # Set database path
  btk config set default_browser firefox      # Set default browser
  btk config set page_size 50                 # Change default page size
  btk config init                             # Initialize config file
""",
    "serve": """
  btk serve                                   # Start server on default port (8000)
  btk serve --port 8080                       # Start on custom port
  btk serve --host 0.0.0.0                    # Allow external connections

  # API endpoints (once running):
  # GET  /api/bookmarks                       # List bookmarks
  # GET  /api/bookmarks/<id>                  # Get bookmark
  # GET  /api/tags                            # List tags
  # GET  /api/search?q=...                    # Full-text search
""",
    "claude": """
  btk claude status                           # Check skill installation status
  btk claude install                          # Install global skill (~/.claude/skills/btk/)
  btk claude install --local                  # Install in current project only
  btk claude show                             # Print skill content
  btk claude uninstall                        # Remove global skill
  btk claude uninstall --local                # Remove local skill
""",
    "plugin": """
  btk plugin list                             # List registered plugins
  btk plugin info <name>                      # Show plugin details
  btk plugin types                            # List available plugin types
""",
}


def cmd_examples(args):
    """Show examples for BTK commands."""
    from rich.panel import Panel

    topic = args.topic

    if topic == "all" or topic is None:
        # Show all examples
        console.print(Panel("[bold]BTK Examples[/bold]", style="blue"))
        console.print()
        for group, examples in CLI_EXAMPLES.items():
            console.print(f"[bold cyan]# {group}[/bold cyan]")
            console.print(examples.strip())
            console.print()
    elif topic in CLI_EXAMPLES:
        console.print(f"[bold cyan]# {topic} examples[/bold cyan]")
        console.print(CLI_EXAMPLES[topic].strip())
    else:
        console.print(f"[yellow]No examples for '{topic}'. Available topics:[/yellow]")
        console.print(", ".join(sorted(CLI_EXAMPLES.keys())))


def cmd_claude(args):
    """Manage Claude Code integration (skill installation)."""
    from pathlib import Path
    import shutil

    command = args.claude_command

    # Skills require a directory with SKILL.md inside
    # Structure: .claude/skills/btk/SKILL.md
    if getattr(args, 'local', False):
        skills_base = Path.cwd() / ".claude" / "skills"
        location = "local"
    else:
        skills_base = Path.home() / ".claude" / "skills"
        location = "global"

    skill_dir = skills_base / "btk"
    skill_path = skill_dir / "SKILL.md"

    if command == "install":
        # Create directory if needed
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write skill file
        skill_path.write_text(BTK_SKILL)

        console.print(f"[green]Installed btk skill to {skill_path}[/green]")
        console.print(f"[dim]Location: {location}[/dim]")
        console.print()
        console.print("[dim]Restart Claude Code to load the skill.[/dim]")

    elif command == "show":
        # Just print the skill content
        print(BTK_SKILL)

    elif command == "uninstall":
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            console.print(f"[green]Removed btk skill from {skill_dir}[/green]")
        else:
            console.print(f"[yellow]No skill found at {skill_dir}[/yellow]")

    elif command == "status":
        # Check installation status
        global_path = Path.home() / ".claude" / "skills" / "btk" / "SKILL.md"
        local_path = Path.cwd() / ".claude" / "skills" / "btk" / "SKILL.md"

        console.print("[bold]BTK Claude Skill Status[/bold]")
        console.print()

        if global_path.exists():
            console.print(f"[green]Global:[/green] {global_path}")
        else:
            console.print("[dim]Global:[/dim] not installed")

        if local_path.exists():
            console.print(f"[green]Local:[/green]  {local_path}")
        else:
            console.print("[dim]Local:[/dim]  not installed")


def cmd_fts_build(args):
    """Build or rebuild the FTS search index."""
    from btk.fts import get_fts_index
    from btk.config import get_config

    config = get_config()
    fts = get_fts_index(config.database)

    console.print("Building full-text search index...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Indexing bookmarks...", total=None)

        def update_progress(current, total):
            progress.update(task, description=f"Indexed {current}/{total} bookmarks...")

        count = fts.rebuild_index(progress_callback=update_progress)

    console.print(f"[green]✓ Indexed {count} bookmarks[/green]")


def cmd_fts_stats(args):
    """Show FTS index statistics."""
    from btk.fts import get_fts_index
    from btk.config import get_config

    config = get_config()
    fts = get_fts_index(config.database)

    stats = fts.get_stats()

    if args.output == "json":
        print(json.dumps(stats, indent=2))
    else:
        if stats.get('exists'):
            console.print("[green]FTS Index Status: Active[/green]")
            console.print(f"  Documents indexed: {stats['documents']}")
            console.print(f"  Table: {stats['table_name']}")
        else:
            console.print("[yellow]FTS Index Status: Not built[/yellow]")
            console.print("  Run 'btk db build-index' to create the search index")


# =============================================================================
# YOUTUBE IMPORT COMMANDS
# =============================================================================

def _get_youtube_importer(args, require_oauth: bool = False):
    """Get YouTube importer with appropriate authentication."""
    try:
        from btk.importers.youtube import YouTubeImporter, HAS_YOUTUBE_API
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Install with: pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    if not HAS_YOUTUBE_API:
        console.print("[red]YouTube API libraries not installed.[/red]")
        console.print("Install with: pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    try:
        importer = YouTubeImporter()
        if require_oauth:
            credentials_file = getattr(args, 'credentials', None)
            if credentials_file:
                from pathlib import Path
                credentials_file = Path(credentials_file)
            importer.authenticate(credentials_file=credentials_file)
        return importer
    except Exception as e:
        console.print(f"[red]Failed to initialize YouTube importer: {e}[/red]")
        sys.exit(1)


def _import_youtube_results(args, results, db, description: str):
    """Common import logic for YouTube results."""
    imported = 0
    skipped = 0
    extra_tags = args.tags or []

    for result in results:
        # Add extra tags
        if extra_tags:
            result.tags = list(set(result.tags + extra_tags))

        if args.dry_run:
            console.print(f"[dim]Would import:[/dim] {result.title[:60]}")
            console.print(f"  URL: {result.url}")
            console.print(f"  Tags: {', '.join(result.tags)}")
            imported += 1
        else:
            # Check if already exists
            existing = db.search(url=result.url)
            if existing:
                skipped += 1
                if not args.quiet:
                    console.print(f"[yellow]Skipped (exists):[/yellow] {result.title[:50]}")
                continue

            # Import
            try:
                bookmark_data = result.to_bookmark_dict()
                db.add(**bookmark_data)
                imported += 1
                if not args.quiet:
                    console.print(f"[green]Imported:[/green] {result.title[:50]}")
            except Exception as e:
                console.print(f"[red]Failed to import {result.title[:30]}: {e}[/red]")

    # Summary
    if args.dry_run:
        console.print(f"\n[cyan]Dry run: Would import {imported} {description}[/cyan]")
    else:
        console.print(f"\n[green]Imported {imported} {description}[/green]")
        if skipped:
            console.print(f"[yellow]Skipped {skipped} (already exist)[/yellow]")


def cmd_youtube_auth(args):
    """Authenticate with YouTube OAuth."""
    from pathlib import Path

    try:
        from btk.importers.youtube import YouTubeImporter, DEFAULT_CREDENTIALS_PATH
    except ImportError:
        console.print("[red]YouTube API libraries not installed.[/red]")
        console.print("Install with: pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    credentials_file = Path(args.credentials) if args.credentials else DEFAULT_CREDENTIALS_PATH

    if not credentials_file.exists():
        console.print(f"[red]Credentials file not found: {credentials_file}[/red]")
        console.print("\n[bold]Setup Instructions:[/bold]")
        console.print("1. Go to https://console.cloud.google.com/apis/credentials")
        console.print("2. Create a project (or select existing)")
        console.print("3. Enable the YouTube Data API v3")
        console.print("4. Create OAuth 2.0 Client ID (Desktop app)")
        console.print(f"5. Download JSON and save to: {credentials_file}")
        sys.exit(1)

    console.print("Authenticating with YouTube...")
    console.print("(A browser window will open for OAuth authorization)")

    try:
        importer = YouTubeImporter()
        if importer.authenticate(credentials_file=credentials_file):
            console.print("[green]✓ Authentication successful![/green]")
            console.print("You can now use: btk youtube library, btk youtube subscriptions, etc.")
        else:
            console.print("[red]Authentication failed[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        sys.exit(1)


def cmd_youtube_library(args):
    """Import user's liked videos."""
    importer = _get_youtube_importer(args, require_oauth=True)
    db = get_db(args.db)

    console.print("[bold]Importing liked videos...[/bold]")
    results = importer.import_library(limit=args.limit)
    _import_youtube_results(args, results, db, "videos")


def cmd_youtube_subscriptions(args):
    """Import user's subscriptions as channel bookmarks."""
    importer = _get_youtube_importer(args, require_oauth=True)
    db = get_db(args.db)

    console.print("[bold]Importing subscriptions...[/bold]")
    results = importer.import_subscriptions(limit=args.limit)
    _import_youtube_results(args, results, db, "subscriptions")


def cmd_youtube_playlists(args):
    """List or import user's playlists."""
    importer = _get_youtube_importer(args, require_oauth=True)
    db = get_db(args.db)

    if getattr(args, 'list', False):
        # Just list playlists
        console.print("[bold]Your playlists:[/bold]\n")
        for result in importer.import_playlists(limit=args.limit):
            video_count = result.extra_data.get('video_count', '?')
            console.print(f"  [cyan]{result.media_id}[/cyan]  {result.title} ({video_count} videos)")
        return

    if getattr(args, 'import_all', False):
        # Import videos from all playlists
        console.print("[bold]Importing videos from all playlists...[/bold]")
        total_imported = 0
        for playlist in importer.import_playlists(limit=args.limit):
            console.print(f"\n[bold]{playlist.title}[/bold]")
            results = importer.import_playlist_with_videos(playlist.media_id, limit=None)
            _import_youtube_results(args, results, db, "videos")
        return

    # Default: import playlists as bookmarks
    console.print("[bold]Importing playlists as bookmarks...[/bold]")
    results = importer.import_playlists(limit=args.limit)
    _import_youtube_results(args, results, db, "playlists")


def cmd_youtube_playlist(args):
    """Import a specific playlist's videos."""
    importer = _get_youtube_importer(args, require_oauth=False)
    db = get_db(args.db)

    console.print(f"[bold]Importing playlist: {args.playlist_id}[/bold]")
    results = importer.import_playlist(args.playlist_id, limit=args.limit)
    _import_youtube_results(args, results, db, "videos")


def cmd_youtube_channel(args):
    """Import videos from a channel."""
    importer = _get_youtube_importer(args, require_oauth=False)
    db = get_db(args.db)

    console.print(f"[bold]Importing channel: {args.channel_id}[/bold]")
    results = importer.import_channel(args.channel_id, limit=args.limit)
    _import_youtube_results(args, results, db, "videos")


def cmd_youtube_video(args):
    """Import a single video."""
    importer = _get_youtube_importer(args, require_oauth=False)
    db = get_db(args.db)

    console.print(f"[bold]Importing video: {args.video_id}[/bold]")
    result = importer.import_video(args.video_id)

    # Add extra tags
    extra_tags = args.tags or []
    if extra_tags:
        result.tags = list(set(result.tags + extra_tags))

    if args.dry_run:
        console.print(f"[dim]Would import:[/dim] {result.title}")
        console.print(f"  URL: {result.url}")
        console.print(f"  Author: {result.author_name}")
        console.print(f"  Tags: {', '.join(result.tags)}")
    else:
        existing = db.get(url=result.url)
        if existing:
            console.print("[yellow]Video already exists in database[/yellow]")
        else:
            bookmark_data = result.to_bookmark_dict()
            db.add(**bookmark_data)
            console.print(f"[green]Imported:[/green] {result.title}")


def cmd_youtube_user(args):
    """Import another user's public content."""
    importer = _get_youtube_importer(args, require_oauth=False)
    db = get_db(args.db)

    user_id = args.user_id
    import_videos = args.videos
    import_playlists = args.playlists

    # Default to both if neither specified
    if not import_videos and not import_playlists:
        import_videos = True
        import_playlists = True

    console.print(f"[bold]Importing from user: {user_id}[/bold]")

    if import_videos:
        console.print("\n[cyan]Channel Videos:[/cyan]")
        results = importer.import_channel(user_id, limit=args.limit)
        _import_youtube_results(args, results, db, "videos")

    if import_playlists:
        console.print("\n[cyan]Public Playlists:[/cyan]")
        results = importer.import_user_playlists(user_id, limit=args.limit)
        _import_youtube_results(args, results, db, "playlists")


def cmd_cleanup(args):
    """Auto-cleanup stale and broken bookmarks."""
    from btk.cleanup import cleanup_all, get_cleanup_preview

    db = get_db(args.db)

    # Parse options
    broken = not args.no_broken
    stale_days = args.stale_days if hasattr(args, 'stale_days') else 365
    unvisited_days = args.unvisited_days if hasattr(args, 'unvisited_days') else 90
    dry_run = not args.apply if hasattr(args, 'apply') else True

    if args.preview:
        # Show preview
        preview = get_cleanup_preview(db, broken, stale_days, unvisited_days)

        if args.output == "json":
            print(json.dumps(preview, indent=2, default=str))
        else:
            console.print("[bold]Cleanup Preview[/bold]\n")

            if preview['broken']:
                console.print(f"[red]Broken URLs ({len(preview['broken'])}):[/red]")
                for item in preview['broken'][:10]:
                    console.print(f"  [{item['id']}] {item['title'][:40]}")
                if len(preview['broken']) > 10:
                    console.print(f"  ... and {len(preview['broken']) - 10} more")

            if preview['stale']:
                console.print(f"\n[yellow]Stale ({len(preview['stale'])}, not visited in {stale_days}+ days):[/yellow]")
                for item in preview['stale'][:10]:
                    console.print(f"  [{item['id']}] {item['title'][:40]}")
                if len(preview['stale']) > 10:
                    console.print(f"  ... and {len(preview['stale']) - 10} more")

            if preview['unvisited']:
                console.print(f"\n[cyan]Unvisited ({len(preview['unvisited'])}, added {unvisited_days}+ days ago):[/cyan]")
                for item in preview['unvisited'][:10]:
                    console.print(f"  [{item['id']}] {item['title'][:40]}")
                if len(preview['unvisited']) > 10:
                    console.print(f"  ... and {len(preview['unvisited']) - 10} more")

            console.print(f"\n[bold]Total: {preview['total']} bookmarks would be archived[/bold]")
            console.print("\nRun with --apply to archive these bookmarks")
    else:
        # Run cleanup
        summary = cleanup_all(db, broken, stale_days, unvisited_days, dry_run)

        if args.output == "json":
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            if dry_run:
                console.print("[yellow]Dry run - no changes made[/yellow]\n")
                console.print(f"Would archive: {summary.skipped} bookmarks")
                console.print("\nRun with --apply to execute cleanup")
            else:
                console.print(f"[green]✓ Archived {summary.archived} bookmarks[/green]")

            if args.verbose and summary.results:
                console.print("\n[bold]Details:[/bold]")
                for result in summary.results[:20]:
                    console.print(f"  [{result.bookmark_id}] {result.title[:40]} - {result.reason}")
                if len(summary.results) > 20:
                    console.print(f"  ... and {len(summary.results) - 20} more")


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

    if use_stdin:
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
        except Exception:
            # If stdin reading fails, fall back to database mode
            console.print("[yellow]Warning: Failed to read from stdin, using database mode[/yellow]")
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
            if filters and filters != {'archived': False}:
                # Has actual filters beyond default archived filter
                bookmarks = db.search(**filters)
            else:
                # No filters, export all (respecting archived default)
                bookmarks = db.list(exclude_archived=filters.get('archived') == False)

    # Build views data for html-app format
    views_data = None
    if args.format == 'html-app':
        try:
            from btk.views import ViewRegistry, ViewContext
            from pathlib import Path as ViewPath

            registry = ViewRegistry()

            # Try to load views from default locations
            config = get_config()
            default_paths = [
                ViewPath("btk-views.yaml"),
                ViewPath("btk-views.yml"),
                ViewPath(config.database).parent / "btk-views.yaml",
                ViewPath.home() / ".config" / "btk" / "views.yaml",
            ]
            for path in default_paths:
                if path.exists():
                    try:
                        registry.load_file(path)
                    except Exception:
                        pass

            # Build views data: evaluate each view to get bookmark IDs
            views_data = {}
            for name in registry.list():
                try:
                    meta = registry.get_metadata(name)
                    view = registry.get(name)
                    context = ViewContext(registry=registry)
                    result = view.evaluate(db, context)
                    bookmark_ids = [ob.original.id for ob in result.bookmarks]
                    views_data[name] = {
                        'description': meta.get('description', ''),
                        'bookmark_ids': bookmark_ids,
                        'builtin': meta.get('builtin', False)
                    }
                except Exception:
                    pass  # Skip views that fail to evaluate
        except ImportError:
            pass  # Views module not available

    try:
        # preservation-html and json-full need db access for cached content
        if args.format in ('preservation-html', 'json-full', 'echo'):
            # Ensure we have db access (might not if using stdin)
            try:
                db
            except NameError:
                db = get_db(args.db)
            export_file(bookmarks, args.file, args.format, views=views_data, db=db)
        else:
            export_file(bookmarks, args.file, args.format, views=views_data)
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
        from btk.models import Tag, bookmark_tags

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
        console.print("\n[green]✓ Graph built successfully![/green]")
        console.print(f"  Bookmarks: {stats['total_bookmarks']}")
        console.print(f"  Edges: {stats['total_edges']}")
        console.print(f"  Avg edge weight: {stats['avg_edge_weight']:.2f}")
        console.print(f"  Max edge weight: {stats['max_edge_weight']:.2f}")
        console.print("\n  Components used:")
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
            console.print("\n[dim]Tip: Try lowering --min-weight or check if the bookmark exists[/dim]")
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

        console.print("[cyan]Graph Statistics[/cyan]")
        console.print(f"  Total edges: {total_edges}")
        console.print(f"  Average weight: {avg_weight:.2f}")
        console.print("\n  Edges by component:")
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


def cmd_browser(args):
    """Browser bookmark operations."""
    from btk.browser_import import (
        list_browser_profiles,
        import_from_browser,
        auto_import_all_browsers
    )

    if args.browser_command == "list":
        # List all detected browser profiles
        profiles = list_browser_profiles()

        if not profiles:
            console.print("[yellow]No browser profiles detected[/yellow]")
            return

        if args.output == "json":
            print(json.dumps(profiles, indent=2))
        else:
            from rich.table import Table
            table = Table(title="Detected Browser Profiles")
            table.add_column("Browser", style="cyan")
            table.add_column("Profile", style="white")
            table.add_column("Path", style="dim")
            table.add_column("Default", style="green")

            for profile in profiles:
                table.add_row(
                    profile["browser"],
                    profile["profile_name"],
                    str(profile["path"]),
                    "✓" if profile.get("is_default") else ""
                )

            console.print(table)
            console.print(f"\n[dim]Total: {len(profiles)} profiles[/dim]")

    elif args.browser_command == "import":
        db = get_db(args.db)
        browser = args.browser
        include_history = args.history
        history_limit = args.history_limit
        update_existing = args.update

        # Import bookmarks
        if browser == "all":
            console.print("[cyan]Importing from all detected browsers...[/cyan]")
            all_bookmarks = auto_import_all_browsers(
                include_history=include_history,
                history_limit=history_limit
            )
            bookmarks = []
            for browser_name, browser_bookmarks in all_bookmarks.items():
                if browser_bookmarks:
                    console.print(f"  Found {len(browser_bookmarks)} bookmarks in {browser_name}")
                    bookmarks.extend(browser_bookmarks)
        else:
            console.print(f"[cyan]Importing from {browser}...[/cyan]")
            bookmarks = import_from_browser(
                browser=browser,
                profile_path=args.profile,
                include_history=include_history,
                history_limit=history_limit
            )

        if not bookmarks:
            console.print("[yellow]No bookmarks found[/yellow]")
            return

        # Import into database with merge logic
        added = 0
        updated = 0
        skipped = 0

        for bm in bookmarks:
            url = bm.get("url")
            if not url:
                continue

            # Check if bookmark already exists
            existing = db.search(url=url)

            if existing:
                if update_existing:
                    # Update existing bookmark
                    updates = {}
                    if bm.get("title") and bm["title"] != existing[0].title:
                        updates["title"] = bm["title"]
                    if bm.get("tags"):
                        # Merge tags
                        existing_tags = [t.name for t in existing[0].tags]
                        new_tags = bm.get("tags", [])
                        merged_tags = list(set(existing_tags + new_tags))
                        if merged_tags != existing_tags:
                            updates["tags"] = merged_tags

                    if updates:
                        db.update(existing[0].id, **updates)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
            else:
                # Add new bookmark
                tags = bm.get("tags", [])
                # Add browser source tag
                if browser != "all":
                    tags.append(f"imported/{browser}")

                # Convert ISO date string to datetime if needed
                added_date = bm.get("added")
                if added_date and isinstance(added_date, str):
                    from datetime import datetime
                    try:
                        added_date = datetime.fromisoformat(added_date.replace('Z', '+00:00'))
                    except ValueError:
                        added_date = None

                db.add(
                    url=url,
                    title=bm.get("title", url),
                    tags=tags,
                    added=added_date
                )
                added += 1

        # Summary
        console.print("\n[green]Import complete![/green]")
        console.print(f"  Added: {added}")
        if update_existing:
            console.print(f"  Updated: {updated}")
        console.print(f"  Skipped (duplicates): {skipped}")


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


def cmd_serve(args):
    """Start the BTK REST API server."""
    from btk.serve import run_server

    db_path = args.db if hasattr(args, 'db') else 'btk.db'
    port = args.port if hasattr(args, 'port') else 8000
    host = args.host if hasattr(args, 'host') else '127.0.0.1'

    run_server(db_path=db_path, port=port, host=host)


def cmd_views(args):
    """View management operations."""
    from btk.views import ViewRegistry, ViewContext
    from pathlib import Path

    db = get_db(args.db)

    # Initialize registry
    registry = ViewRegistry()

    # Load views from file if specified
    views_file = getattr(args, 'views_file', None)
    if views_file:
        try:
            registry.load_file(views_file)
        except Exception as e:
            console.print(f"[red]Error loading views file: {e}[/red]")
            return
    else:
        # Try to load from default locations
        config = get_config()
        default_paths = [
            Path("btk-views.yaml"),
            Path("btk-views.yml"),
            Path(config.database).parent / "btk-views.yaml",
            Path.home() / ".config" / "btk" / "views.yaml",
        ]
        for path in default_paths:
            if path.exists():
                try:
                    registry.load_file(path)
                except Exception:
                    pass

    if args.view_command == "list":
        # List all views
        include_builtin = not getattr(args, 'no_builtin', False)
        views = registry.list(include_builtin=include_builtin)

        if args.output == "json":
            info = registry.info()
            print(json.dumps(info, indent=2))
        else:
            from rich.table import Table

            table = Table(title="Views")
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="white")
            table.add_column("Type", style="yellow")
            table.add_column("Params", style="magenta")

            for name in views:
                meta = registry.get_metadata(name)
                view_type = "built-in" if meta.get("builtin") else "custom"
                has_params = "yes" if meta.get("params") else ""
                table.add_row(
                    name,
                    meta.get("description", "")[:50],
                    view_type,
                    has_params
                )

            console.print(table)
            console.print(f"\n[dim]Total: {len(views)} views[/dim]")

    elif args.view_command == "show":
        # Show view details
        name = args.name
        if not registry.has(name):
            console.print(f"[red]View not found: {name}[/red]")
            return

        meta = registry.get_metadata(name)
        view = registry.get(name)

        if args.output == "json":
            data = {
                "name": name,
                "metadata": meta,
                "repr": repr(view)
            }
            print(json.dumps(data, indent=2))
        else:
            from rich.panel import Panel
            from rich.table import Table as RichTable

            details = RichTable(show_header=False, box=None)
            details.add_column("Field", style="cyan bold")
            details.add_column("Value", style="white")

            details.add_row("Name", name)
            details.add_row("Description", meta.get("description", "(none)"))
            details.add_row("Type", "built-in" if meta.get("builtin") else "custom")
            if meta.get("params"):
                params_str = ", ".join(f"{k}={v}" for k, v in meta["params"].items())
                details.add_row("Parameters", params_str)
            details.add_row("View", repr(view))

            panel = Panel(details, title=f"View: {name}", border_style="blue")
            console.print(panel)

    elif args.view_command == "eval":
        # Evaluate a view and show results
        name = args.name
        if not registry.has(name):
            console.print(f"[red]View not found: {name}[/red]")
            return

        # Parse parameters
        params = {}
        if hasattr(args, 'param') and args.param:
            for p in args.param:
                if '=' in p:
                    k, v = p.split('=', 1)
                    # Try to parse as JSON for complex values
                    try:
                        params[k] = json.loads(v)
                    except json.JSONDecodeError:
                        params[k] = v

        # Evaluate view
        context = ViewContext(params=params, registry=registry)
        try:
            view = registry.get(name, **params)
            result = view.evaluate(db, context)
        except Exception as e:
            console.print(f"[red]Error evaluating view: {e}[/red]")
            return

        # Convert to bookmarks for output
        bookmarks = []
        for ob in result.bookmarks:
            bookmarks.append(ob.original)

        limit = getattr(args, 'limit', None)
        if limit:
            bookmarks = bookmarks[:limit]

        console.print(f"[dim]View '{name}' returned {len(result.bookmarks)} bookmarks[/dim]\n")
        output_bookmarks(bookmarks, args.output)

    elif args.view_command == "export":
        # Export view results to file
        name = args.name
        if not registry.has(name):
            console.print(f"[red]View not found: {name}[/red]")
            return

        # Parse parameters
        params = {}
        if hasattr(args, 'param') and args.param:
            for p in args.param:
                if '=' in p:
                    k, v = p.split('=', 1)
                    try:
                        params[k] = json.loads(v)
                    except json.JSONDecodeError:
                        params[k] = v

        # Evaluate view
        context = ViewContext(params=params, registry=registry)
        try:
            view = registry.get(name, **params)
            result = view.evaluate(db, context)
        except Exception as e:
            console.print(f"[red]Error evaluating view: {e}[/red]")
            return

        # Convert to regular bookmarks
        bookmarks = [ob.original for ob in result.bookmarks]

        # Export
        output_path = args.output_file
        export_format = getattr(args, 'format', 'html')

        from btk.exporters import export_file

        # For single view export, include this view's metadata
        view_meta = registry.get_metadata(name)
        views_data = {
            name: {
                'description': view_meta.get('description', ''),
                'bookmark_ids': [b.id for b in bookmarks],
                'builtin': view_meta.get('builtin', False)
            }
        } if export_format == 'html-app' else None

        try:
            export_file(bookmarks, output_path, export_format, views=views_data)
            console.print(f"[green]✓ Exported {len(bookmarks)} bookmarks to {output_path}[/green]")
        except Exception as e:
            console.print(f"[red]Error exporting: {e}[/red]")

    elif args.view_command == "create":
        # Create a simple view from CLI args (not YAML)
        from btk.views import SelectView, OrderView, LimitView, PipelineView
        from btk.views.predicates import TagsPredicate, FieldPredicate, SearchPredicate
        from btk.views.primitives import AllView

        stages = [AllView()]

        # Tags filter
        if hasattr(args, 'tags') and args.tags:
            tags = args.tags.split(',')
            stages.append(SelectView(TagsPredicate(tags=tags, mode='any')))

        # Search filter
        if hasattr(args, 'search') and args.search:
            stages.append(SelectView(SearchPredicate(query=args.search)))

        # Field filters
        if hasattr(args, 'starred') and args.starred:
            stages.append(SelectView(FieldPredicate('stars', 'gt', 0)))

        if hasattr(args, 'pinned') and args.pinned:
            stages.append(SelectView(FieldPredicate('pinned', 'eq', True)))

        # Order
        order = getattr(args, 'order', 'added desc')
        if order:
            stages.append(OrderView.from_string(order))

        # Limit
        limit = getattr(args, 'limit', None)
        if limit:
            stages.append(LimitView(int(limit)))

        # Build pipeline
        if len(stages) == 1:
            view = stages[0]
        else:
            view = PipelineView(stages)

        # Evaluate
        context = ViewContext(registry=registry)
        result = view.evaluate(db, context)

        bookmarks = [ob.original for ob in result.bookmarks]
        console.print(f"[dim]Query returned {len(bookmarks)} bookmarks[/dim]\n")
        output_bookmarks(bookmarks, args.output)


def cmd_plugin(args):
    """Plugin management operations."""
    from btk.plugins import create_default_registry

    registry = create_default_registry()

    if args.plugin_command == "list":
        # List all registered plugins
        info = registry.get_plugin_info()

        if args.output == "json":
            print(json.dumps(info, indent=2))
        else:
            from rich.table import Table
            from rich.panel import Panel

            # Show plugin types and their plugins
            has_plugins = False
            for plugin_type, plugins in info.items():
                if plugins:
                    has_plugins = True
                    table = Table(title=f"Plugin Type: {plugin_type}")
                    table.add_column("Name", style="cyan")
                    table.add_column("Version", style="green")
                    table.add_column("Priority", style="yellow")
                    table.add_column("Enabled", style="magenta")
                    table.add_column("Description", style="white")

                    for plugin in plugins:
                        table.add_row(
                            plugin["name"],
                            plugin["version"],
                            str(plugin["priority"]),
                            "✓" if plugin["enabled"] else "✗",
                            plugin["description"][:50] if plugin["description"] else ""
                        )

                    console.print(table)
                    console.print()

            if not has_plugins:
                console.print("[yellow]No plugins registered[/yellow]")
                console.print("\n[dim]Plugins can be loaded from the plugins/ directory.[/dim]")
                console.print("[dim]Create a plugin module with a register_plugins(registry) function.[/dim]")

            # Show available plugin types
            console.print("\n[cyan]Available plugin types:[/cyan]")
            for ptype in registry.PLUGIN_INTERFACES.keys():
                console.print(f"  • {ptype}")

    elif args.plugin_command == "info":
        # Show info about a specific plugin
        plugin_name = args.name

        # Search across all plugin types
        found = False
        info = registry.get_plugin_info()

        for plugin_type, plugins in info.items():
            for plugin in plugins:
                if plugin["name"] == plugin_name:
                    found = True

                    if args.output == "json":
                        print(json.dumps({
                            "type": plugin_type,
                            **plugin
                        }, indent=2))
                    else:
                        from rich.panel import Panel
                        from rich.table import Table as RichTable

                        details = RichTable(show_header=False, box=None)
                        details.add_column("Field", style="cyan bold")
                        details.add_column("Value", style="white")

                        details.add_row("Name", plugin["name"])
                        details.add_row("Type", plugin_type)
                        details.add_row("Version", plugin["version"])
                        details.add_row("Author", plugin["author"] or "(not specified)")
                        details.add_row("Description", plugin["description"] or "(not specified)")
                        details.add_row("Priority", str(plugin["priority"]))
                        details.add_row("Enabled", "Yes" if plugin["enabled"] else "No")

                        if plugin["dependencies"]:
                            details.add_row("Dependencies", ", ".join(plugin["dependencies"]))

                        panel = Panel(details, title=f"Plugin: {plugin_name}", border_style="blue")
                        console.print(panel)
                    break

            if found:
                break

        if not found:
            console.print(f"[red]Plugin not found: {plugin_name}[/red]")
            console.print("\n[dim]Use 'btk plugin list' to see available plugins.[/dim]")

    elif args.plugin_command == "types":
        # List available plugin types
        if args.output == "json":
            print(json.dumps(list(registry.PLUGIN_INTERFACES.keys()), indent=2))
        else:
            console.print("[cyan]Available plugin types:[/cyan]")
            for ptype, interface in registry.PLUGIN_INTERFACES.items():
                console.print(f"  • [green]{ptype}[/green]: {interface.__doc__ or 'No description'}")


# Command categories for help output
COMMAND_CATEGORIES = {
    "Bookmark Commands": ["add", "get", "update", "rm", "open", "star", "unstar", "health"],
    "Query & Browse": ["query", "sql", "shell"],
    "Management": ["tag", "queue", "content", "media", "view"],
    "Data": ["import", "export", "browser"],
    "System": ["db", "config", "serve", "plugin", "claude", "graph"],
    "Info": ["activity", "stats", "examples"],
}


class CategorizedHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter that groups subcommands into categories."""

    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction):
            # Custom formatting for subparsers with categories
            parts = []

            # Get help text from action choices
            choice_helps = {}
            for choice_action in action._choices_actions:
                choice_helps[choice_action.dest] = choice_action.help or ""

            # Format each category
            for category, commands in COMMAND_CATEGORIES.items():
                category_cmds = []
                for cmd in commands:
                    if cmd in action.choices:
                        help_text = choice_helps.get(cmd, "")
                        category_cmds.append(f"    {cmd:<14} {help_text}")

                if category_cmds:
                    parts.append(f"\n  {category}:")
                    parts.extend(category_cmds)

            return "\n".join(parts) + "\n"

        return super()._format_action(action)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BTK - Bookmark Toolkit: A clean, composable bookmark manager",
        formatter_class=CategorizedHelpFormatter,
        epilog="""
Quick Start:
  btk add https://example.com --tags "web"
  btk query --limit 10                # List recent bookmarks
  btk query --starred                 # Show starred bookmarks
  btk shell                           # Interactive mode
  btk examples                        # See all examples

Configuration:
  Database: ./btk.db (or BTK_DATABASE env, or --db flag)
  Config: ~/.config/btk/config.toml
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
    # TOP-LEVEL SHORTCUTS
    # =================

    # btk add <url>
    add_parser = subparsers.add_parser("add", help="Add a bookmark (shortcut)")
    add_parser.add_argument("url", help="URL to bookmark")
    add_parser.add_argument("--title", "-t", help="Bookmark title")
    add_parser.add_argument("--description", "-d", help="Description")
    add_parser.add_argument("--tags", help="Comma-separated tags")
    add_parser.add_argument("--star", "-s", action="store_true", help="Star this bookmark")
    add_parser.set_defaults(func=cmd_add_shortcut)

    # btk open <id>
    open_parser = subparsers.add_parser("open", help="Open bookmark in browser")
    open_parser.add_argument("id", help="Bookmark ID or unique_id")
    open_parser.set_defaults(func=cmd_open_shortcut)

    # btk star <id>
    star_parser = subparsers.add_parser("star", help="Star a bookmark")
    star_parser.add_argument("id", help="Bookmark ID or unique_id")
    star_parser.set_defaults(func=cmd_star_shortcut)

    # btk unstar <id>
    unstar_parser = subparsers.add_parser("unstar", help="Unstar a bookmark")
    unstar_parser.add_argument("id", help="Bookmark ID or unique_id")
    unstar_parser.set_defaults(func=cmd_unstar_shortcut)

    # NOTE: btk tag is a group command (tag add/remove/rename)
    # For quick tagging, use: btk tag add <id> <tags>

    # btk rm <id>
    rm_parser = subparsers.add_parser("rm", help="Delete a bookmark (shortcut)")
    rm_parser.add_argument("id", help="Bookmark ID or unique_id")
    rm_parser.set_defaults(func=cmd_rm_shortcut)

    # btk activity
    activity_parser = subparsers.add_parser("activity", help="Show activity log")
    activity_parser.add_argument("--limit", "-l", type=int, help="Max events to show (default: 20)")
    activity_parser.set_defaults(func=cmd_activity)

    # btk stats
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # btk get <id>
    get_parser = subparsers.add_parser("get", help="Get bookmark details")
    get_parser.add_argument("id", help="Bookmark ID or unique_id")
    get_parser.add_argument("--details", action="store_true", help="Show detailed metadata")
    get_parser.set_defaults(func=cmd_get)

    # btk update <id>
    update_parser = subparsers.add_parser("update", help="Update a bookmark")
    update_parser.add_argument("id", help="Bookmark ID")
    update_parser.add_argument("--url", help="New URL")
    update_parser.add_argument("--title", help="New title")
    update_parser.add_argument("--description", help="New description")
    update_parser.add_argument("--tags", help="Replace all tags (comma-separated)")
    update_parser.add_argument("--add-tags", help="Add tags (comma-separated)")
    update_parser.add_argument("--remove-tags", help="Remove tags (comma-separated)")
    update_parser.add_argument("--star", action="store_true", dest="starred", default=None, help="Mark as starred")
    update_parser.add_argument("--unstar", action="store_false", dest="starred", help="Remove starred status")
    update_parser.add_argument("--archive", action="store_true", dest="archived", default=None, help="Mark as archived")
    update_parser.add_argument("--unarchive", action="store_false", dest="archived", help="Remove archived status")
    update_parser.add_argument("--pin", action="store_true", dest="pinned", default=None, help="Mark as pinned")
    update_parser.add_argument("--unpin", action="store_false", dest="pinned", help="Remove pinned status")
    update_parser.set_defaults(func=cmd_update)

    # btk health
    health_parser = subparsers.add_parser("health", help="Check URL reachability")
    health_parser.add_argument("--id", nargs="+", help="Check specific bookmark IDs")
    health_parser.add_argument("--broken", action="store_true",
                               help="Re-check only previously broken bookmarks")
    health_parser.add_argument("--unchecked", action="store_true",
                               help="Check only bookmarks that have never been checked")
    health_parser.add_argument("--concurrency", type=int, default=10,
                               help="Number of concurrent requests (default: 10)")
    health_parser.add_argument("--timeout", type=float, default=10.0,
                               help="Request timeout in seconds (default: 10)")
    health_parser.add_argument("--dry-run", action="store_true",
                               help="Show what would be checked without checking")
    health_parser.add_argument("--verbose", "-v", action="store_true",
                               help="Show detailed progress")
    health_parser.set_defaults(func=cmd_health)

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
    # QUEUE GROUP
    # =================
    queue_parser = subparsers.add_parser("queue", help="Reading queue management")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_command", required=True)

    # queue list
    queue_list = queue_subparsers.add_parser("list", help="List reading queue")
    queue_list.add_argument("--sort", choices=["priority", "queued_at", "progress", "title"],
                           default="priority", help="Sort order (default: priority)")
    queue_list.add_argument("--all", action="store_true", help="Include completed items")
    queue_list.set_defaults(func=cmd_queue)

    # queue add
    queue_add = queue_subparsers.add_parser("add", help="Add bookmarks to reading queue")
    queue_add.add_argument("ids", nargs="+", help="Bookmark IDs to add")
    queue_add.add_argument("--priority", "-p", type=int, default=3, choices=[1, 2, 3, 4, 5],
                          help="Priority level (1=highest, default: 3)")
    queue_add.set_defaults(func=cmd_queue)

    # queue remove
    queue_remove = queue_subparsers.add_parser("remove", help="Remove bookmarks from reading queue")
    queue_remove.add_argument("ids", nargs="+", help="Bookmark IDs to remove")
    queue_remove.set_defaults(func=cmd_queue)

    # queue progress
    queue_progress = queue_subparsers.add_parser("progress", help="Update reading progress")
    queue_progress.add_argument("id", help="Bookmark ID")
    queue_progress.add_argument("percent", type=int, help="Progress percentage (0-100)")
    queue_progress.set_defaults(func=cmd_queue)

    # queue priority
    queue_priority = queue_subparsers.add_parser("priority", help="Set item priority")
    queue_priority.add_argument("id", help="Bookmark ID")
    queue_priority.add_argument("level", type=int, choices=[1, 2, 3, 4, 5],
                               help="Priority level (1=highest)")
    queue_priority.set_defaults(func=cmd_queue)

    # queue next
    queue_next = queue_subparsers.add_parser("next", help="Get next item to read")
    queue_next.set_defaults(func=cmd_queue)

    # queue stats
    queue_stats = queue_subparsers.add_parser("stats", help="Show queue statistics")
    queue_stats.set_defaults(func=cmd_queue)

    # queue estimate-times
    queue_estimate = queue_subparsers.add_parser("estimate-times",
                                                  help="Auto-estimate reading times from content")
    queue_estimate.add_argument("--overwrite", action="store_true",
                               help="Overwrite existing estimates")
    queue_estimate.set_defaults(func=cmd_queue)

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

    # content preserve - Long Echo preservation
    content_preserve = content_subparsers.add_parser(
        "preserve",
        help="Preserve media content (thumbnails, transcripts, PDF text) for Long Echo"
    )
    content_preserve.add_argument("--id", type=int, help="Preserve specific bookmark ID")
    content_preserve.add_argument("--all", action="store_true",
                                 help="Preserve all preservable bookmarks")
    content_preserve.add_argument("--type", choices=["video", "pdf", "image"],
                                 help="Only preserve specific media type")
    content_preserve.add_argument("--limit", type=int, help="Maximum bookmarks to preserve")
    content_preserve.add_argument("--dry-run", action="store_true",
                                 help="Show what would be preserved without doing it")
    content_preserve.set_defaults(func=cmd_preserve)

    # content preserve-status - Show preservation statistics
    content_preserve_status = content_subparsers.add_parser(
        "preserve-status",
        help="Show preservation statistics"
    )
    content_preserve_status.set_defaults(func=cmd_preserve_status)

    # =================
    # MEDIA GROUP
    # =================
    media_parser = subparsers.add_parser("media", help="Media detection and management")
    media_subparsers = media_parser.add_subparsers(dest="media_command", required=True)

    # media detect
    media_detect = media_subparsers.add_parser("detect", help="Detect media URLs in bookmarks")
    media_detect.add_argument("--all", action="store_true", help="Scan all bookmarks (default)")
    media_detect.add_argument("--id", type=int, help="Detect for specific bookmark ID")
    media_detect.add_argument("--undetected", action="store_true",
                             help="Only bookmarks without media_type")
    media_detect.set_defaults(func=cmd_media)

    # media refresh
    media_refresh = media_subparsers.add_parser("refresh", help="Refresh media metadata")
    media_refresh.add_argument("--all", action="store_true", help="Refresh all media bookmarks")
    media_refresh.add_argument("--source", help="Only refresh specific source (youtube, spotify, etc)")
    media_refresh.add_argument("--id", type=int, help="Refresh specific bookmark ID")
    media_refresh.set_defaults(func=cmd_media)

    # media list
    media_list = media_subparsers.add_parser("list", help="List media bookmarks")
    media_list.add_argument("--type", choices=["video", "audio", "document", "image", "code"],
                           help="Filter by media type")
    media_list.add_argument("--source", help="Filter by source (youtube, spotify, arxiv, etc)")
    media_list.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    media_list.set_defaults(func=cmd_media)

    # media import-playlist
    media_import_playlist = media_subparsers.add_parser("import-playlist",
                                                        help="Import from playlist URL")
    media_import_playlist.add_argument("url", help="Playlist URL (YouTube, Spotify)")
    media_import_playlist.add_argument("--tags", help="Tags to apply (comma-separated)")
    media_import_playlist.add_argument("--limit", type=int, help="Max items to import")
    media_import_playlist.set_defaults(func=cmd_media)

    # media import-channel
    media_import_channel = media_subparsers.add_parser("import-channel",
                                                       help="Import from channel/profile")
    media_import_channel.add_argument("url", help="Channel URL")
    media_import_channel.add_argument("--tags", help="Tags to apply (comma-separated)")
    media_import_channel.add_argument("--limit", type=int, help="Max items to import")
    media_import_channel.set_defaults(func=cmd_media)

    # media import-podcast
    media_import_podcast = media_subparsers.add_parser("import-podcast",
                                                       help="Import from podcast RSS feed")
    media_import_podcast.add_argument("feed_url", help="Podcast RSS feed URL")
    media_import_podcast.add_argument("--tags", help="Tags to apply (comma-separated)")
    media_import_podcast.add_argument("--limit", type=int, help="Max episodes to import")
    media_import_podcast.set_defaults(func=cmd_media)

    # media stats
    media_stats = media_subparsers.add_parser("stats", help="Show media statistics")
    media_stats.set_defaults(func=cmd_media)

    # =================
    # IMPORT GROUP
    # =================
    import_parser = subparsers.add_parser("import", help="Import bookmarks")
    import_subparsers = import_parser.add_subparsers(dest="import_source", required=True)

    # File imports
    for fmt in ['html', 'json', 'csv', 'markdown', 'text']:
        fmt_parser = import_subparsers.add_parser(fmt, help=f"Import from {fmt.upper()} file")
        fmt_parser.add_argument("file", help="File to import")
        fmt_parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
        fmt_parser.add_argument("--tag", "-t", action="append", dest="tags", help="Additional tags")
        fmt_parser.set_defaults(func=cmd_import, format=fmt)

    # YouTube imports
    yt_parser = import_subparsers.add_parser("youtube", help="Import from YouTube")
    yt_subparsers = yt_parser.add_subparsers(dest="youtube_command", required=True)

    # youtube auth
    yt_auth = yt_subparsers.add_parser("auth", help="Authenticate with YouTube (OAuth)")
    yt_auth.add_argument("--credentials", "-c", help="Path to OAuth credentials JSON")
    yt_auth.set_defaults(func=cmd_youtube_auth)

    # youtube library
    yt_library = yt_subparsers.add_parser("library", help="Import liked videos")
    yt_library.add_argument("--limit", "-n", type=int, help="Maximum videos to import")
    yt_library.add_argument("--dry-run", action="store_true", help="Preview without importing")
    yt_library.add_argument("--tag", "-t", action="append", dest="tags", help="Additional tags")
    yt_library.set_defaults(func=cmd_youtube_library)

    # youtube subscriptions
    yt_subs = yt_subparsers.add_parser("subscriptions", help="Import subscribed channels")
    yt_subs.add_argument("--limit", "-n", type=int, help="Maximum subscriptions to import")
    yt_subs.add_argument("--dry-run", action="store_true", help="Preview without importing")
    yt_subs.add_argument("--tag", "-t", action="append", dest="tags", help="Additional tags")
    yt_subs.set_defaults(func=cmd_youtube_subscriptions)

    # youtube playlists
    yt_playlists = yt_subparsers.add_parser("playlists", help="List/import your playlists")
    yt_playlists.add_argument("--list", "-l", action="store_true", help="List playlists only")
    yt_playlists.add_argument("--import-all", action="store_true", help="Import all playlist videos")
    yt_playlists.add_argument("--limit", "-n", type=int, help="Maximum playlists to process")
    yt_playlists.add_argument("--dry-run", action="store_true", help="Preview without importing")
    yt_playlists.set_defaults(func=cmd_youtube_playlists)

    # youtube playlist
    yt_playlist = yt_subparsers.add_parser("playlist", help="Import a specific playlist")
    yt_playlist.add_argument("playlist_id", help="Playlist ID or URL")
    yt_playlist.add_argument("--limit", "-n", type=int, help="Maximum videos to import")
    yt_playlist.add_argument("--dry-run", action="store_true", help="Preview without importing")
    yt_playlist.add_argument("--tag", "-t", action="append", dest="tags", help="Additional tags")
    yt_playlist.set_defaults(func=cmd_youtube_playlist)

    # youtube channel
    yt_channel = yt_subparsers.add_parser("channel", help="Import videos from a channel")
    yt_channel.add_argument("channel_id", help="Channel ID, handle (@name), or URL")
    yt_channel.add_argument("--limit", "-n", type=int, help="Maximum videos to import")
    yt_channel.add_argument("--dry-run", action="store_true", help="Preview without importing")
    yt_channel.add_argument("--tag", "-t", action="append", dest="tags", help="Additional tags")
    yt_channel.set_defaults(func=cmd_youtube_channel)

    # youtube video
    yt_video = yt_subparsers.add_parser("video", help="Import a single video")
    yt_video.add_argument("video_id", help="Video ID or URL")
    yt_video.add_argument("--dry-run", action="store_true", help="Preview without importing")
    yt_video.add_argument("--tag", "-t", action="append", dest="tags", help="Additional tags")
    yt_video.set_defaults(func=cmd_youtube_video)

    # youtube user (other user's public content)
    yt_user = yt_subparsers.add_parser("user", help="Import another user's public content")
    yt_user.add_argument("user_id", help="Channel ID, handle (@name), or URL")
    yt_user.add_argument("--videos", action="store_true", help="Import channel videos")
    yt_user.add_argument("--playlists", action="store_true", help="Import public playlists")
    yt_user.add_argument("--limit", "-n", type=int, help="Maximum items to import")
    yt_user.add_argument("--dry-run", action="store_true", help="Preview without importing")
    yt_user.add_argument("--tag", "-t", action="append", dest="tags", help="Additional tags")
    yt_user.set_defaults(func=cmd_youtube_user)

    import_parser.set_defaults(func=lambda args: import_parser.print_help())

    # =================
    # EXPORT GROUP
    # =================
    export_parser = subparsers.add_parser("export", help="Export bookmarks")
    export_parser.add_argument("file", help="Output file")
    export_parser.add_argument("--format", required=True,
                              choices=["json", "json-full", "csv", "html", "html-app", "markdown", "m3u", "preservation-html", "echo"],
                              help="Export format (json-full for comprehensive export, html-app for interactive viewer, preservation-html for archived content, echo for ECHO-compliant archive)")
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

    # db build-index
    db_build_index = db_subparsers.add_parser("build-index",
                                              help="Build full-text search index")
    db_build_index.set_defaults(func=cmd_fts_build)

    # db index-stats
    db_index_stats = db_subparsers.add_parser("index-stats",
                                              help="Show full-text search index statistics")
    db_index_stats.set_defaults(func=cmd_fts_stats)

    # db cleanup
    db_cleanup = db_subparsers.add_parser("cleanup",
                                           help="Auto-cleanup stale and broken bookmarks")
    db_cleanup.add_argument("--preview", action="store_true",
                           help="Show what would be cleaned up without making changes")
    db_cleanup.add_argument("--apply", action="store_true",
                           help="Actually archive bookmarks (default is dry-run)")
    db_cleanup.add_argument("--no-broken", action="store_true",
                           help="Skip broken/unreachable bookmarks")
    db_cleanup.add_argument("--stale-days", type=int, default=365,
                           help="Days threshold for stale bookmarks (default: 365, 0 to skip)")
    db_cleanup.add_argument("--unvisited-days", type=int, default=90,
                           help="Days threshold for unvisited bookmarks (default: 90, 0 to skip)")
    db_cleanup.add_argument("-v", "--verbose", action="store_true",
                           help="Show detailed results")
    db_cleanup.add_argument("-o", "--output", choices=["table", "json"], default="table",
                           help="Output format")
    db_cleanup.set_defaults(func=cmd_cleanup)

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
    # BROWSER GROUP
    # =================
    browser_parser = subparsers.add_parser("browser", help="Browser bookmark operations")
    browser_subparsers = browser_parser.add_subparsers(dest="browser_command", required=True)

    # browser list
    browser_list = browser_subparsers.add_parser("list", help="List detected browser profiles")
    browser_list.set_defaults(func=cmd_browser)

    # browser import
    browser_import = browser_subparsers.add_parser("import", help="Import bookmarks from browser")
    browser_import.add_argument("browser",
                                choices=["chrome", "firefox", "safari", "edge", "brave", "chromium", "all"],
                                help="Browser to import from (or 'all')")
    browser_import.add_argument("--profile", "-p", help="Specific profile path to import from")
    browser_import.add_argument("--history", "-H", action="store_true",
                                help="Also import browsing history as bookmarks")
    browser_import.add_argument("--history-limit", type=int, default=1000,
                                help="Maximum history entries to import (default: 1000)")
    browser_import.add_argument("--update", "-u", action="store_true",
                                help="Update existing bookmarks if browser version differs")
    browser_import.set_defaults(func=cmd_browser)

    browser_parser.set_defaults(func=cmd_browser)

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

    # =================
    # SERVE COMMAND
    # =================
    serve_parser = subparsers.add_parser("serve", help="Start REST API server with web UI")
    serve_parser.add_argument("--port", "-p", type=int, default=8000,
                              help="Port to listen on (default: 8000)")
    serve_parser.add_argument("--host", "-H", default="127.0.0.1",
                              help="Host to bind to (default: 127.0.0.1)")
    serve_parser.set_defaults(func=cmd_serve)

    # =================
    # SQL COMMAND
    # =================
    sql_parser = subparsers.add_parser("sql", help="Execute raw SQL queries")
    sql_parser.add_argument("-e", "--query", help="SQL query to execute")
    sql_parser.add_argument("-o", "--output", choices=["table", "json", "csv", "plain"],
                           default="table", help="Output format (default: table)")
    sql_parser.set_defaults(func=cmd_sql)

    # =================
    # EXAMPLES COMMAND
    # =================
    examples_parser = subparsers.add_parser("examples", help="Show usage examples")
    examples_parser.add_argument("topic", nargs="?", default="all",
                                 choices=list(CLI_EXAMPLES.keys()) + ["all"],
                                 help="Topic to show examples for (default: all)")
    examples_parser.set_defaults(func=cmd_examples)

    # =================
    # CLAUDE COMMAND GROUP
    # =================
    claude_parser = subparsers.add_parser("claude", help="Claude Code integration")
    claude_subparsers = claude_parser.add_subparsers(dest="claude_command", required=True)

    # claude install
    claude_install = claude_subparsers.add_parser("install", help="Install btk skill for Claude Code")
    claude_install.add_argument("--local", action="store_true",
                                help="Install to current directory instead of global ~/.claude/")
    claude_install.set_defaults(func=cmd_claude)

    # claude show
    claude_show = claude_subparsers.add_parser("show", help="Show the btk skill content")
    claude_show.set_defaults(func=cmd_claude)

    # claude uninstall
    claude_uninstall = claude_subparsers.add_parser("uninstall", help="Remove btk skill")
    claude_uninstall.add_argument("--local", action="store_true",
                                  help="Remove from current directory instead of global")
    claude_uninstall.set_defaults(func=cmd_claude)

    # claude status
    claude_status = claude_subparsers.add_parser("status", help="Check skill installation status")
    claude_status.set_defaults(func=cmd_claude)

    claude_parser.set_defaults(func=cmd_claude)

    # =================
    # QUERY COMMAND (Flag-based composable query)
    # =================
    query_parser = subparsers.add_parser(
        "query",
        help="Composable bookmark query with flags",
        description="""
Query bookmarks using composable flags. Filters combine with AND logic.
Use --no-* prefix for negation.

Examples:
  btk query                          # Recent bookmarks (default)
  btk query --starred                # Starred only
  btk query --starred --recent       # Starred AND recent
  btk query --tagged python,ai       # Tagged with python OR ai
  btk query --domain github.com      # From github.com
  btk query --search "machine learning"  # Full-text search
  btk query --no-starred --unread    # Not starred AND unread
  btk query --view arxiv --starred   # Starred bookmarks from arxiv view
"""
    )

    # Filters (positive)
    query_parser.add_argument("--starred", action="store_true", help="Only starred bookmarks")
    query_parser.add_argument("--recent", action="store_true", help="Added in last 7 days")
    query_parser.add_argument("--unread", action="store_true", help="Never visited (visit_count=0)")
    query_parser.add_argument("--archived", action="store_true", help="Only archived bookmarks")
    query_parser.add_argument("--pinned", action="store_true", help="Only pinned bookmarks")
    query_parser.add_argument("--tagged", metavar="TAGS", help="Has any of these tags (comma-separated)")
    query_parser.add_argument("--domain", metavar="DOMAIN", help="From this domain")
    query_parser.add_argument("--search", "-s", metavar="TERM", help="Full-text search in title/url/description")

    # Filters (negation)
    query_parser.add_argument("--no-starred", action="store_true", help="Exclude starred")
    query_parser.add_argument("--no-recent", action="store_true", help="Older than 7 days")
    query_parser.add_argument("--no-unread", action="store_true", help="Has been visited")
    query_parser.add_argument("--no-archived", action="store_true", help="Exclude archived (default)")
    query_parser.add_argument("--no-pinned", action="store_true", help="Exclude pinned")
    query_parser.add_argument("--no-tagged", metavar="TAGS", help="Exclude these tags (comma-separated)")
    query_parser.add_argument("--no-domain", metavar="DOMAIN", help="Exclude this domain")

    # View integration
    query_parser.add_argument("--view", "-v", metavar="NAME", help="Start from a named view")

    # Output control
    query_parser.add_argument("--limit", "-l", type=int, help="Max results (default: 20)")
    query_parser.add_argument("--offset", type=int, help="Skip first N results")
    query_parser.add_argument("--order", choices=["added", "title", "visits", "visited", "stars"],
                              default="added", help="Sort order (default: added)")

    query_parser.set_defaults(func=cmd_query_flags)

    # =================
    # VIEW GROUP
    # =================
    view_parser = subparsers.add_parser("view", help="View management (composable bookmark queries)")
    view_parser.add_argument("--views-file", "-f", help="Path to views YAML file")
    view_subparsers = view_parser.add_subparsers(dest="view_command", required=True)

    # view list
    view_list = view_subparsers.add_parser("list", help="List available views")
    view_list.add_argument("--no-builtin", action="store_true",
                           help="Exclude built-in views")
    view_list.set_defaults(func=cmd_views)

    # view show
    view_show = view_subparsers.add_parser("show", help="Show view details")
    view_show.add_argument("name", help="View name")
    view_show.set_defaults(func=cmd_views)

    # view eval
    view_eval = view_subparsers.add_parser("eval", help="Evaluate a view and show results")
    view_eval.add_argument("name", help="View name")
    view_eval.add_argument("--param", "-p", action="append",
                           help="View parameter (key=value)")
    view_eval.add_argument("--limit", "-l", type=int,
                           help="Limit number of results")
    view_eval.set_defaults(func=cmd_views)

    # view export
    view_export = view_subparsers.add_parser("export", help="Export view results to file")
    view_export.add_argument("name", help="View name")
    view_export.add_argument("output_file", help="Output file path")
    view_export.add_argument("--format", choices=["html", "html-app", "json", "csv", "markdown"],
                             default="html", help="Export format (default: html)")
    view_export.add_argument("--param", "-p", action="append",
                             help="View parameter (key=value)")
    view_export.add_argument("--title", "-t", help="Export title")
    view_export.add_argument("--hierarchical", action="store_true",
                             help="Export with hierarchical tag structure")
    view_export.set_defaults(func=cmd_views)

    # view create (ad-hoc view from CLI)
    view_create = view_subparsers.add_parser("create",
                                              help="Create and evaluate an ad-hoc view")
    view_create.add_argument("--tags", help="Filter by tags (comma-separated)")
    view_create.add_argument("--search", "-s", help="Full-text search query")
    view_create.add_argument("--starred", action="store_true", help="Only starred bookmarks")
    view_create.add_argument("--pinned", action="store_true", help="Only pinned bookmarks")
    view_create.add_argument("--order", default="added desc",
                              help="Sort order (default: added desc)")
    view_create.add_argument("--limit", "-l", type=int, help="Limit results")
    view_create.set_defaults(func=cmd_views)

    view_parser.set_defaults(func=cmd_views)

    # =================
    # PLUGIN GROUP
    # =================
    plugin_parser = subparsers.add_parser("plugin", help="Plugin management")
    plugin_subparsers = plugin_parser.add_subparsers(dest="plugin_command", required=True)

    # plugin list
    plugin_list = plugin_subparsers.add_parser("list", help="List registered plugins")
    plugin_list.set_defaults(func=cmd_plugin)

    # plugin info
    plugin_info = plugin_subparsers.add_parser("info", help="Show info about a plugin")
    plugin_info.add_argument("name", help="Plugin name")
    plugin_info.set_defaults(func=cmd_plugin)

    # plugin types
    plugin_types = plugin_subparsers.add_parser("types", help="List available plugin types")
    plugin_types.set_defaults(func=cmd_plugin)

    plugin_parser.set_defaults(func=cmd_plugin)

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