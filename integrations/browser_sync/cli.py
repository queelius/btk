#!/usr/bin/env python3
"""
Command-line interface for BTK browser sync.

Usage:
    btk-browser-sync sync [options]
    btk-browser-sync watch [options]
    btk-browser-sync diff [browser1] [browser2]
    btk-browser-sync export --to [browsers]
    btk-browser-sync migrate --to sqlite
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn
import yaml

from universal_sync import (
    UniversalBrowserSync,
    SyncConfig,
    SyncDirection,
    ConflictStrategy,
    SQLiteBookmarkStore
)

console = Console()


def load_config(config_file: str = None) -> SyncConfig:
    """Load configuration from file or use defaults."""
    config = SyncConfig()

    # Look for config file
    if config_file:
        config_path = Path(config_file)
    else:
        # Check default locations
        for location in ['.btk-sync.yaml', '~/.btk-sync.yaml', '~/.config/btk/sync.yaml']:
            config_path = Path(location).expanduser()
            if config_path.exists():
                break
        else:
            return config  # Use defaults

    if config_path.exists():
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)

            # Parse config
            sync_data = data.get('sync', {})

            # Browsers configuration
            browsers_config = sync_data.get('browsers', [])
            config.browsers = []
            config.browser_profiles = {}

            for browser_item in browsers_config:
                if isinstance(browser_item, dict):
                    for browser_name, browser_data in browser_item.items():
                        config.browsers.append(browser_name)
                        config.browser_profiles[browser_name] = browser_data.get('profiles', [])
                else:
                    config.browsers.append(browser_item)

            # Sync settings
            if 'direction' in sync_data:
                config.direction = SyncDirection[sync_data['direction'].upper()]

            # Conflict resolution
            conflict_data = sync_data.get('conflict_resolution', {})
            if 'strategy' in conflict_data:
                config.conflict_strategy = ConflictStrategy[conflict_data['strategy'].upper()]
            config.backup_before_sync = conflict_data.get('backup_before_sync', True)

            # Monitoring
            monitoring = sync_data.get('monitoring', {})
            config.sync_interval = monitoring.get('watch_interval', 30)
            config.auto_sync = monitoring.get('auto_sync', False)

            # Filters
            config.filters = sync_data.get('rules', {})

            # Storage
            storage = sync_data.get('storage', {})
            config.use_sqlite = storage.get('backend') == 'sqlite'
            config.sqlite_path = storage.get('sqlite_path')

    return config


def cmd_sync(args):
    """Execute sync command."""
    config = load_config(args.config)

    # Override config with CLI arguments
    if args.browsers:
        config.browsers = args.browsers.split(',')
    if args.direction:
        config.direction = SyncDirection[args.direction.upper()]
    if args.conflict:
        config.conflict_strategy = ConflictStrategy[args.conflict.upper()]
    if args.no_backup:
        config.backup_before_sync = False

    # Initialize sync engine
    sync = UniversalBrowserSync(args.library, config)

    # Display sync plan
    console.print(Panel(
        f"[bold]Browser Sync[/bold]\n\n"
        f"Library: {args.library}\n"
        f"Browsers: {', '.join(config.browsers)}\n"
        f"Direction: {config.direction.value}\n"
        f"Conflict Strategy: {config.conflict_strategy.value}\n"
        f"Backup: {'Yes' if config.backup_before_sync else 'No'}",
        title="Sync Configuration",
        border_style="cyan"
    ))

    # Perform sync
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Syncing bookmarks...", total=None)

        result = sync.sync_all()

        progress.update(task, completed=True)

    # Display results
    table = Table(title="Sync Results", show_header=True, header_style="bold magenta")
    table.add_column("Action", style="cyan")
    table.add_column("Count", justify="right", style="yellow")

    table.add_row("Added", str(result.added))
    table.add_row("Modified", str(result.modified))
    table.add_row("Removed", str(result.removed))
    table.add_row("Conflicts Resolved", str(result.conflicts_resolved))
    table.add_row("Total Synced", str(result.total_synced))

    console.print(table)

    if result.errors:
        console.print("\n[red]Errors:[/red]")
        for error in result.errors:
            console.print(f"  • {error}")

    console.print(f"\n[green]✓ Sync completed in {result.duration:.2f}s[/green]")


def cmd_watch(args):
    """Execute watch command."""
    config = load_config(args.config)

    if args.browsers:
        config.browsers = args.browsers.split(',')
    if args.interval:
        config.sync_interval = args.interval
    config.auto_sync = not args.no_auto

    # Initialize sync engine
    sync = UniversalBrowserSync(args.library, config)

    console.print(Panel(
        f"[bold]Watch Mode[/bold]\n\n"
        f"Monitoring: {', '.join(config.browsers)}\n"
        f"Interval: {config.sync_interval}s\n"
        f"Auto-sync: {'Yes' if config.auto_sync else 'No'}\n\n"
        "[dim]Press Ctrl+C to stop[/dim]",
        title="Browser Sync Watch",
        border_style="green"
    ))

    if args.stream:
        # Stream mode - output JSON events
        def stream_callback(changes):
            for change in changes:
                event = {
                    'timestamp': change.timestamp.isoformat(),
                    'source': change.source,
                    'action': change.action,
                    'url': change.bookmark.get('url'),
                    'title': change.bookmark.get('title')
                }
                print(json.dumps(event))
                sys.stdout.flush()

        sync.watch(callback=stream_callback)
    else:
        # Interactive mode
        events = []

        def display_callback(changes):
            for change in changes:
                events.append(f"{change.timestamp.strftime('%H:%M:%S')} - "
                            f"{change.source}: {change.action} "
                            f"{change.bookmark.get('title', 'Untitled')[:50]}")
                if len(events) > 20:
                    events.pop(0)

            # Clear and redraw
            console.clear()
            console.print(Panel(
                '\n'.join(events[-10:]) if events else "Watching for changes...",
                title="Recent Events",
                border_style="green"
            ))

        try:
            sync.watch(callback=display_callback)
        except KeyboardInterrupt:
            console.print("\n[yellow]Watch mode stopped[/yellow]")


def cmd_diff(args):
    """Execute diff command."""
    config = load_config(args.config)

    # Initialize sync engine
    sync = UniversalBrowserSync(args.library, config)

    # If SQLite backend is enabled, use it for efficient queries
    if config.use_sqlite:
        store = sync.store

        # Get bookmarks from each browser
        browser1_bookmarks = set()
        browser2_bookmarks = set()

        if args.browser1:
            for bookmark in store.get_browser_bookmarks(args.browser1):
                browser1_bookmarks.add(bookmark['url'])

        if args.browser2:
            for bookmark in store.get_browser_bookmarks(args.browser2):
                browser2_bookmarks.add(bookmark['url'])

        # Calculate differences
        only_in_1 = browser1_bookmarks - browser2_bookmarks
        only_in_2 = browser2_bookmarks - browser1_bookmarks
        in_both = browser1_bookmarks & browser2_bookmarks

        # Display results
        console.print(Panel(
            f"[bold]Bookmark Differences[/bold]\n\n"
            f"{args.browser1 or 'BTK'}: {len(browser1_bookmarks)} bookmarks\n"
            f"{args.browser2 or 'All Browsers'}: {len(browser2_bookmarks)} bookmarks\n"
            f"Shared: {len(in_both)} bookmarks",
            title="Diff Summary",
            border_style="cyan"
        ))

        if args.output == 'json':
            # JSON output
            diff_data = {
                'only_in_first': list(only_in_1)[:100],
                'only_in_second': list(only_in_2)[:100],
                'shared': len(in_both)
            }
            print(json.dumps(diff_data, indent=2))
        else:
            # Table output
            if only_in_1 and not args.hide_unique:
                console.print(f"\n[yellow]Only in {args.browser1 or 'BTK'}:[/yellow]")
                for url in list(only_in_1)[:20]:
                    console.print(f"  • {url[:80]}")
                if len(only_in_1) > 20:
                    console.print(f"  ... and {len(only_in_1) - 20} more")

            if only_in_2 and not args.hide_unique:
                console.print(f"\n[yellow]Only in {args.browser2 or 'All Browsers'}:[/yellow]")
                for url in list(only_in_2)[:20]:
                    console.print(f"  • {url[:80]}")
                if len(only_in_2) > 20:
                    console.print(f"  ... and {len(only_in_2) - 20} more")


def cmd_migrate(args):
    """Execute migrate command."""
    if args.to == 'sqlite':
        # Migrate from JSON to SQLite
        lib_path = Path(args.library)
        bookmarks_file = lib_path / 'bookmarks.json'

        if not bookmarks_file.exists():
            console.print("[red]No bookmarks.json found[/red]")
            return

        # Load JSON bookmarks
        with open(bookmarks_file, 'r') as f:
            bookmarks = json.load(f)

        # Create SQLite store
        db_path = args.output or str(lib_path / 'bookmarks.db')
        store = SQLiteBookmarkStore(db_path)

        # Migrate bookmarks
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Migrating {len(bookmarks)} bookmarks...", total=len(bookmarks))

            for bookmark in bookmarks:
                store.add_bookmark(bookmark)
                progress.update(task, advance=1)

        console.print(f"[green]✓ Migrated {len(bookmarks)} bookmarks to {db_path}[/green]")

        # Show sample queries
        console.print("\n[bold]Sample Queries:[/bold]")
        console.print("Full-text search: SELECT * FROM bookmarks_fts WHERE bookmarks_fts MATCH 'python'")
        console.print("By health: SELECT * FROM bookmarks WHERE health_score > 0.7 ORDER BY health_score DESC")
        console.print("Cross-browser: SELECT * FROM browser_sync WHERE browser = 'chrome'")


def cmd_export(args):
    """Export bookmarks to browsers."""
    config = load_config(args.config)

    # Override with CLI args
    if args.to:
        if args.to == 'all':
            # Export to all detected browsers
            pass
        else:
            config.browsers = args.to.split(',')

    config.direction = SyncDirection.TO_BROWSER

    # Initialize sync engine
    sync = UniversalBrowserSync(args.library, config)

    # Perform one-way sync to browsers
    result = sync.sync_all()

    console.print(f"[green]✓ Exported {result.total_synced} bookmarks to {', '.join(config.browsers)}[/green]")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='BTK Browser Sync - Synchronize bookmarks across browsers'
    )
    parser.add_argument('--library', '-l', default='.',
                       help='BTK library directory (default: current directory)')
    parser.add_argument('--config', '-c', help='Configuration file path')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Synchronize bookmarks')
    sync_parser.add_argument('--browsers', '-b', help='Comma-separated list of browsers')
    sync_parser.add_argument('--direction', '-d',
                            choices=['to_browser', 'from_browser', 'bidirectional'],
                            help='Sync direction')
    sync_parser.add_argument('--conflict', '-C',
                            choices=['browser_wins', 'btk_wins', 'newest_wins',
                                   'highest_health', 'most_visited', 'merge_all'],
                            help='Conflict resolution strategy')
    sync_parser.add_argument('--no-backup', action='store_true',
                            help='Skip backup before sync')

    # Watch command
    watch_parser = subparsers.add_parser('watch', help='Watch for changes')
    watch_parser.add_argument('--browsers', '-b', help='Comma-separated list of browsers')
    watch_parser.add_argument('--interval', '-i', type=int, default=30,
                             help='Check interval in seconds')
    watch_parser.add_argument('--no-auto', action='store_true',
                             help='Disable auto-sync on changes')
    watch_parser.add_argument('--stream', action='store_true',
                             help='Output JSON events for piping')

    # Diff command
    diff_parser = subparsers.add_parser('diff', help='Show differences between sources')
    diff_parser.add_argument('browser1', nargs='?', help='First browser')
    diff_parser.add_argument('browser2', nargs='?', help='Second browser')
    diff_parser.add_argument('--output', '-o', choices=['table', 'json'],
                            default='table', help='Output format')
    diff_parser.add_argument('--hide-unique', action='store_true',
                            help='Hide unique bookmarks')

    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Migrate storage backend')
    migrate_parser.add_argument('--to', choices=['sqlite', 'json'], required=True,
                               help='Target storage backend')
    migrate_parser.add_argument('--output', '-o', help='Output file path')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export to browsers')
    export_parser.add_argument('--to', required=True,
                              help='Target browsers (comma-separated or "all")')

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    # Execute command
    if args.command == 'sync':
        cmd_sync(args)
    elif args.command == 'watch':
        cmd_watch(args)
    elif args.command == 'diff':
        cmd_diff(args)
    elif args.command == 'migrate':
        cmd_migrate(args)
    elif args.command == 'export':
        cmd_export(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()