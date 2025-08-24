import json
import argparse
import os
import logging
import sys
import subprocess
from colorama import init as colorama_init, Fore, Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.json import JSON
import btk.utils as utils
import btk.merge as merge
import btk.tools as tools
import btk.tag_utils as tag_utils
import btk.dedup as dedup
import btk.bulk_ops as bulk_ops
import btk.auto_tag as auto_tag
import btk.content_extractor  # Import to register plugins
import btk.archiver as archiver
import btk.content_cache as content_cache

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def main():
    """Main entry point for the BTK command-line interface."""
    parser = argparse.ArgumentParser(description='Bookmark Toolkit (btk) - Manage and analyze bookmarks')
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Import command
    import_parser = subparsers.add_parser('import', help='Import bookmarks')
    import_subparsers = import_parser.add_subparsers(dest='type_command', required=True, help='The format of the bookmarks to import')

    # Import nbf (Netscape Bookmark Format HTML file)
    nbf_import = import_subparsers.add_parser('nbf', help='Netscape Bookmark Format HTML file. File ends with .html')
    nbf_import.add_argument('file', type=str, help='Path to the HTML bookmark file')
    nbf_import.add_argument('--lib-dir', type=str, help='Directory to store the imported bookmarks library. If not specified, {file}-btk will be used. If that already exists, we will add _j where j is the smallest integer such that {file}-btk_{j} does not exist.')

    # Import csv (CSV file), format: url, title, tags, description, stars by default, but you can change the order
    csv_import = import_subparsers.add_parser('csv', help='CSV file. File ends with .csv')
    csv_import.add_argument('file', type=str, help='Path to the CSV bookmark file')
    csv_import.add_argument('--lib-dir', type=str, help='Directory to store the imported bookmarks library. If not specified, {file}-btk will be used. If that already exists, we will add _j where j is the smallest integer such that {file}-btk_{j} does not exist.')
    csv_import.add_argument('--fields', type=str, nargs='+', default=['url', 'title', 'tags', 'description', 'stars'], help='Fields in the CSV file. The default order is url, title, tags, description, stars. The available fields are: url, title, tags, description, stars')

    # Import json (JSON file). Looks for a list of dictionaries with an optioal set of fields. By default, it looks for url, title, tags, description, stars
    json_import = import_subparsers.add_parser('json', help='JSON file. File ends with .json')
    json_import.add_argument('file', type=str, help='Path to the JSON bookmark file')
    json_import.add_argument('--lib-dir', type=str, help='Directory to store the imported bookmarks library. If not specified, {file}-btk will be used. If that already exists, we will add _j where j is the smallest integer such that {file}-btk_{j} does not exist.')

    # Import markdown (Markdown file). Extracts all links from the markdown file
    markdown_import = import_subparsers.add_parser('markdown', help='Markdown file. Extracts all links from markdown format')
    markdown_import.add_argument('file', type=str, help='Path to the Markdown file')
    markdown_import.add_argument('--lib-dir', type=str, help='Directory to store the imported bookmarks library. If not specified, {file}-btk will be used. If that already exists, we will add _j where j is the smallest integer such that {file}-btk_{j} does not exist.')

    # Import html (Generic HTML file). Extracts all links from any HTML file
    html_import = import_subparsers.add_parser('html', help='Generic HTML file. Extracts all links from any HTML')
    html_import.add_argument('file', type=str, help='Path to the HTML file')
    html_import.add_argument('--lib-dir', type=str, help='Directory to store the imported bookmarks library. If not specified, {file}-btk will be used. If that already exists, we will add _j where j is the smallest integer such that {file}-btk_{j} does not exist.')

    # Import directory. Recursively imports all supported files from a directory
    dir_import = import_subparsers.add_parser('dir', help='Directory import. Recursively finds and imports all supported files')
    dir_import.add_argument('directory', type=str, help='Path to the directory to scan')
    dir_import.add_argument('--lib-dir', type=str, help='Directory to store the imported bookmarks library')
    dir_import.add_argument('--no-recursive', action='store_true', help='Do not scan subdirectories')
    dir_import.add_argument('--formats', nargs='+', choices=['html', 'markdown', 'json', 'csv', 'nbf'], 
                           help='Specific formats to import (default: all formats)')

    # Merge Operations
    set_parser = subparsers.add_parser('merge', help='Perform merge (set) operations on bookmark libraries')
    set_subparsers = set_parser.add_subparsers(dest='merge_command', required=True, help='Set operation commands')

    # Merge: Union
    union_parser = set_subparsers.add_parser('union', help='Perform set union of multiple bookmark libraries')
    union_parser.add_argument('lib_dirs', type=str, nargs='+', help='Directories of the bookmark libraries to union')
    union_parser.add_argument('--output', type=str, help='Directory to store the union library. If not specified, the union will be saved in `union_{lib_dirs[0]}_{lib_dirs[1]}_...`. If that already exists, we will add `_j` where `j` is the smallest integer such that `union_{lib_dirs[0]}_{lib_dirs[1]}_..._{j}` does not exist.')

    # Merge: Intersection
    intersection_parser = set_subparsers.add_parser('intersection', help='Perform set intersection of multiple bookmark libraries')
    intersection_parser.add_argument('lib_dirs', type=str, nargs='+', help='Directories of the bookmark libraries to intersect')
    intersection_parser.add_argument('--output', type=str, help='Directory to store the intersection library. If not specified, the intersection will be saved in `intersection_{lib_dirs[0]}_{lib_dirs[1]}_...`. If that already exists, we will add `_j` where `j` is the smallest integer such that `intersection_{lib_dirs[0]}_{lib_dirs[1]}_..._{j}` does not exist.')

    # Merge: Difference
    difference_parser = set_subparsers.add_parser('difference', help='Perform set difference (first minus others) of bookmark libraries')
    difference_parser.add_argument('lib_dirs', type=str, nargs='+', help='Directories of the bookmark libraries (first library minus the rest)')
    difference_parser.add_argument('--output', type=str, help='Directory to store the difference library. If not specified, the difference will be saved in `difference_{lib_dirs[0]}_{lib_dirs[1]}_...`. If that already exists, we will add `_j` where `j` is the smallest integer such that `difference_{lib_dirs[0]}_{lib_dirs[1]}_..._{j}` does not exist.')

    # Search command
    SEARCH_FIELDS = ['tags', 'description', 'title', 'url']
    search_parser = subparsers.add_parser('search', help='Search bookmarks by query')
    search_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to search')
    search_parser.add_argument('query', type=str, help='Search query (searches in title and URL)')
    search_parser.add_argument('--json', action='store_true', help='Output in JSON format')
    search_parser.add_argument('--fields', default=['title', 'description', 'tags'],
                               type=str, nargs='+', help=f'Search fields (default: tags, description, title). The available fields are: {", ".join(SEARCH_FIELDS)}')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new bookmark')
    add_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to add to')
    add_parser.add_argument('url', type=str, help='URL of the bookmark')
    add_parser.add_argument('--title', type=str, help='Title of the bookmark. If not specified, the title will be fetched from the URL')
    add_parser.add_argument('--star', action='store_true', help='Mark the bookmark as favorite')
    add_parser.add_argument('--tags', type=str, help='Comma-separated tags for the bookmark')
    add_parser.add_argument('--description', type=str, help='Description or notes for the bookmark')
    add_parser.add_argument('--json', action='store_true', help='Output result in JSON format')

    # Edit command
    edit_parser = subparsers.add_parser('edit', help='Edit a bookmark by its ID')
    edit_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to edit')
    edit_parser.add_argument('id', type=int, help='ID of the bookmark to edit')
    edit_parser.add_argument('--title', type=str, help='New title of the bookmark')
    edit_parser.add_argument('--url', type=str, help='New URL of the bookmark')
    edit_parser.add_argument('--stars', choices=['true', 'false'], help='Set starred status (true/false)')
    edit_parser.add_argument('--tags', type=str, nargs='+', help='Comma-separated tags for the bookmark')
    edit_parser.add_argument('--description', type=str, help='Description or notes for the bookmark')
    edit_parser.add_argument('--json', action='store_true', help='Output result in JSON format')

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a bookmark by its ID')
    remove_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to remove from')
    remove_parser.add_argument('id', type=int, help='ID of the bookmark to remove')
    remove_parser.add_argument('--json', action='store_true', help='Output result in JSON format')

    # List command
    list_parser = subparsers.add_parser('list', help='List all bookmarks with their IDs and unique IDs')
    list_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to list')
    list_parser.add_argument('--json', action='store_true', help='Output in JSON format')
    list_parser.add_argument('--indices', type=int, nargs='*', default=None, help='Indices of the bookmarks to list')

    # Visit command
    visit_parser = subparsers.add_parser('visit', help='Visit a bookmark by its ID')
    visit_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to visit from')
    visit_parser.add_argument('id', type=int, help='ID of the bookmark to visit')
    group = visit_parser.add_mutually_exclusive_group()
    group.add_argument('--browser', action='store_true', help='Visit the bookmark in the default web browser (default)')
    group.add_argument('--console', default=True, action='store_true', help='Display the bookmark content in the console')

 
    # Reachable command
    reachable_parser = subparsers.add_parser('reachable', help='Check and mark bookmarks as reachable or not')
    reachable_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to analyze')
    reachable_parser.add_argument('--timeout', type=int, default=10, help='Timeout for HTTP requests in seconds')
    reachable_parser.add_argument('--concurrency', type=int, default=10, help='Number of concurrent HTTP requests')
    
    # Purge command
    purge_parser = subparsers.add_parser('purge', help='Purge bookmarks flagged as unreachable (see `reachable` command)')
    purge_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to purge')
    purge_parser.add_argument('--unreachable', action='store_true', help='Purge unreachable bookmarks')
    purge_parser.add_argument('--output-purged', type=str, help='Directory to save the purged bookmarks')
    purge_parser.add_argument('--confirm', action='store_true', help='Ask for confirmation before purging')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export bookmarks to a different format')
    export_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to export')
    export_parser.add_argument('format', choices=['html', 'csv', 'json', 'markdown', 'zip', 'hierarchical'], help='Export format')
    export_parser.add_argument('--output', type=str, help='Path to save the exported directory or file')
    export_parser.add_argument('--json', action='store_true', help='Force JSON format regardless of file extension')
    export_parser.add_argument('--hierarchical-format', choices=['markdown', 'json', 'html'], default='markdown',
                              help='Format for hierarchical export (default: markdown)')
    export_parser.add_argument('--tag-separator', type=str, default='/',
                              help='Tag separator for hierarchical export (default: /)')

    # Tag command
    tag_parser = subparsers.add_parser('tag', help='Tag management operations')
    tag_subparsers = tag_parser.add_subparsers(dest='tag_command', required=True, help='Tag operation commands')
    
    # Tag tree
    tag_tree_parser = tag_subparsers.add_parser('tree', help='Display tags in tree structure')
    tag_tree_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    tag_tree_parser.add_argument('--separator', type=str, default='/', help='Tag hierarchy separator (default: /)')
    
    # Tag stats
    tag_stats_parser = tag_subparsers.add_parser('stats', help='Show tag statistics')
    tag_stats_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    tag_stats_parser.add_argument('--separator', type=str, default='/', help='Tag hierarchy separator (default: /)')
    tag_stats_parser.add_argument('--json', action='store_true', help='Output in JSON format')
    
    # Tag rename
    tag_rename_parser = tag_subparsers.add_parser('rename', help='Rename a tag and all its children')
    tag_rename_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    tag_rename_parser.add_argument('old_tag', type=str, help='Tag to rename')
    tag_rename_parser.add_argument('new_tag', type=str, help='New tag name')
    tag_rename_parser.add_argument('--separator', type=str, default='/', help='Tag hierarchy separator (default: /)')
    
    # Tag merge
    tag_merge_parser = tag_subparsers.add_parser('merge', help='Merge multiple tags into one')
    tag_merge_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    tag_merge_parser.add_argument('source_tags', type=str, nargs='+', help='Tags to merge from')
    tag_merge_parser.add_argument('--into', type=str, required=True, help='Tag to merge into')
    
    # Tag filter
    tag_filter_parser = tag_subparsers.add_parser('filter', help='Filter bookmarks by tag prefix')
    tag_filter_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    tag_filter_parser.add_argument('prefix', type=str, help='Tag prefix to filter by')
    tag_filter_parser.add_argument('--separator', type=str, default='/', help='Tag hierarchy separator (default: /)')
    tag_filter_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Deduplicate command
    dedup_parser = subparsers.add_parser('dedupe', help='Find and remove duplicate bookmarks')
    dedup_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    dedup_parser.add_argument('--strategy', choices=['merge', 'keep_first', 'keep_last', 'keep_most_visited'],
                             default='merge', help='Deduplication strategy (default: merge)')
    dedup_parser.add_argument('--key', type=str, default='url', help='Key to use for finding duplicates (default: url)')
    dedup_parser.add_argument('--preview', action='store_true', help='Preview changes without applying them')
    dedup_parser.add_argument('--stats', action='store_true', help='Show duplicate statistics only')
    dedup_parser.add_argument('--output-removed', type=str, help='Save removed bookmarks to this directory')

    # Bulk operations command
    bulk_parser = subparsers.add_parser('bulk', help='Bulk operations on bookmarks')
    bulk_subparsers = bulk_parser.add_subparsers(dest='bulk_command', required=True, help='Bulk operation commands')
    
    # Bulk add
    bulk_add_parser = bulk_subparsers.add_parser('add', help='Bulk add bookmarks from file')
    bulk_add_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    bulk_add_parser.add_argument('--from-file', type=str, required=True, help='File containing URLs (one per line)')
    bulk_add_parser.add_argument('--tags', type=str, help='Comma-separated tags to apply to all bookmarks')
    bulk_add_parser.add_argument('--no-fetch-titles', action='store_true', help='Do not fetch titles from URLs')
    
    # Bulk edit
    bulk_edit_parser = bulk_subparsers.add_parser('edit', help='Bulk edit bookmarks matching criteria')
    bulk_edit_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    bulk_edit_parser.add_argument('--filter-tags', type=str, help='Filter by tag prefix')
    bulk_edit_parser.add_argument('--filter-url', type=str, help='Filter by URL pattern')
    bulk_edit_parser.add_argument('--filter-starred', action='store_true', help='Filter only starred bookmarks')
    bulk_edit_parser.add_argument('--filter-unstarred', action='store_true', help='Filter only unstarred bookmarks')
    bulk_edit_parser.add_argument('--add-tags', type=str, help='Comma-separated tags to add')
    bulk_edit_parser.add_argument('--remove-tags', type=str, help='Comma-separated tags to remove')
    bulk_edit_parser.add_argument('--set-stars', choices=['true', 'false'], help='Set starred status')
    bulk_edit_parser.add_argument('--set-description', type=str, help='Set description')
    bulk_edit_parser.add_argument('--preview', action='store_true', help='Preview changes without applying')
    
    # Bulk remove
    bulk_remove_parser = bulk_subparsers.add_parser('remove', help='Bulk remove bookmarks matching criteria')
    bulk_remove_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    bulk_remove_parser.add_argument('--filter-tags', type=str, help='Filter by tag prefix')
    bulk_remove_parser.add_argument('--filter-url', type=str, help='Filter by URL pattern')
    bulk_remove_parser.add_argument('--filter-visits-min', type=int, help='Filter by minimum visit count')
    bulk_remove_parser.add_argument('--filter-visits-max', type=int, help='Filter by maximum visit count')
    bulk_remove_parser.add_argument('--filter-no-description', action='store_true', help='Filter bookmarks without description')
    bulk_remove_parser.add_argument('--preview', action='store_true', help='Preview removals without applying')
    bulk_remove_parser.add_argument('--output-removed', type=str, help='Save removed bookmarks to this directory')

    # JMESPath command
    jmespath_parser = subparsers.add_parser('jmespath', help='Query bookmarks using JMESPath')
    jmespath_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to query')
    jmespath_parser.add_argument('query', type=str, help='JMESPath query string')
    jmespath_parser.add_argument('--json', action='store_true', help='Output in JSON format')
    jmespath_parser.add_argument('--output', type=str, help='Directory to save the output bookmarks')

    # Auto-tag command
    autotag_parser = subparsers.add_parser('auto-tag', help='Automatically tag bookmarks using AI/NLP')
    autotag_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    autotag_parser.add_argument('--id', type=int, help='Tag specific bookmark by ID')
    autotag_parser.add_argument('--all', action='store_true', help='Tag all bookmarks')
    autotag_parser.add_argument('--untagged', action='store_true', help='Only tag bookmarks without tags')
    autotag_parser.add_argument('--filter-url', type=str, help='Only tag bookmarks matching URL pattern')
    autotag_parser.add_argument('--filter-domain', type=str, help='Only tag bookmarks from domain')
    autotag_parser.add_argument('--replace', action='store_true', help='Replace existing tags instead of appending')
    autotag_parser.add_argument('--dry-run', action='store_true', help='Preview tags without applying')
    autotag_parser.add_argument('--analyze', action='store_true', help='Analyze tagging coverage')
    autotag_parser.add_argument('--enrich', action='store_true', help='Extract content before tagging')

    # Archive command
    archive_parser = subparsers.add_parser('archive', help='Archive bookmark content permanently')
    archive_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    archive_parser.add_argument('--id', type=int, help='Archive specific bookmark by ID')
    archive_parser.add_argument('--all', action='store_true', help='Archive all bookmarks')
    archive_parser.add_argument('--wayback', action='store_true', help='Also save to Wayback Machine')
    archive_parser.add_argument('--summary', action='store_true', help='Show archive summary')
    archive_parser.add_argument('--cache-stats', action='store_true', help='Show cache statistics')
    archive_parser.add_argument('--search', type=str, help='Search in cached content')

    args = parser.parse_args()

    if args.command == 'export':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        export_format = args.format
        output = args.output
        
        # Set default output path if not specified
        if not output:
            if export_format == 'html':
                output = 'bookmarks_export.html'
            elif export_format == 'csv':
                output = 'bookmarks_export.csv'
            elif export_format == 'json':
                output = 'bookmarks_export.json'
            elif export_format == 'markdown':
                output = 'bookmarks_export.md'
            elif export_format == 'zip':
                output = 'bookmarks_export.zip'
        
        if export_format == 'html':
            tools.export_bookmarks_html(bookmarks, output)
        elif export_format == 'csv':
            tools.export_bookmarks_csv(bookmarks, output)
        elif export_format == 'json':
            tools.export_bookmarks_json(bookmarks, output)
        elif export_format == 'markdown':
            tools.export_bookmarks_markdown(bookmarks, output)
        elif export_format == 'zip':
            utils.export_to_zip(bookmarks, output)
        elif export_format == 'hierarchical':
            # Set default output directory if not specified
            if not output:
                output = 'bookmarks_hierarchical_export'
            # Use hierarchical export
            hierarchical_format = args.hierarchical_format if hasattr(args, 'hierarchical_format') else 'markdown'
            tag_separator = args.tag_separator if hasattr(args, 'tag_separator') else '/'
            exported_files = tools.export_bookmarks_hierarchical(
                bookmarks, output, 
                format=hierarchical_format,
                separator=tag_separator
            )
            console.print(f"[green]Exported {len(exported_files)} bookmark files to '{output}'[/green]")
            console.print(f"[green]Index file created at '{output}/index.md'[/green]")
        else:
            logging.error(f"Unknown export format '{export_format}'.")

    elif args.command == 'import':
        
        if args.type_command == 'nbf':
            lib_dir = args.lib_dir
            utils.ensure_dir(lib_dir)
            utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
            bookmarks = utils.load_bookmarks(lib_dir)
            bookmarks = tools.import_bookmarks(args.file, bookmarks, lib_dir)
            utils.save_bookmarks(bookmarks, None, lib_dir)
        elif args.type_command == 'markdown':
            lib_dir = args.lib_dir
            if not lib_dir:
                # Generate default lib_dir based on filename
                base_name = os.path.splitext(os.path.basename(args.file))[0]
                lib_dir = f"{base_name}-btk"
                # Make it unique if needed
                if os.path.exists(lib_dir):
                    i = 1
                    while os.path.exists(f"{lib_dir}_{i}"):
                        i += 1
                    lib_dir = f"{lib_dir}_{i}"
            utils.ensure_dir(lib_dir)
            utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
            bookmarks = utils.load_bookmarks(lib_dir)
            bookmarks = tools.import_bookmarks_markdown(args.file, bookmarks, lib_dir)
            utils.save_bookmarks(bookmarks, None, lib_dir)
        elif args.type_command == 'json':
            lib_dir = args.lib_dir
            if not lib_dir:
                # Generate default lib_dir based on filename
                base_name = os.path.splitext(os.path.basename(args.file))[0]
                lib_dir = f"{base_name}-btk"
                # Make it unique if needed
                if os.path.exists(lib_dir):
                    i = 1
                    while os.path.exists(f"{lib_dir}_{i}"):
                        i += 1
                    lib_dir = f"{lib_dir}_{i}"
            utils.ensure_dir(lib_dir)
            utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
            bookmarks = utils.load_bookmarks(lib_dir)
            bookmarks = tools.import_bookmarks_json(args.file, bookmarks, lib_dir)
            utils.save_bookmarks(bookmarks, None, lib_dir)
        elif args.type_command == 'csv':
            lib_dir = args.lib_dir
            if not lib_dir:
                # Generate default lib_dir based on filename
                base_name = os.path.splitext(os.path.basename(args.file))[0]
                lib_dir = f"{base_name}-btk"
                # Make it unique if needed
                if os.path.exists(lib_dir):
                    i = 1
                    while os.path.exists(f"{lib_dir}_{i}"):
                        i += 1
                    lib_dir = f"{lib_dir}_{i}"
            utils.ensure_dir(lib_dir)
            utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
            bookmarks = utils.load_bookmarks(lib_dir)
            fields = args.fields if hasattr(args, 'fields') else ['url', 'title', 'tags', 'description', 'stars']
            bookmarks = tools.import_bookmarks_csv(args.file, bookmarks, lib_dir, fields)
            utils.save_bookmarks(bookmarks, None, lib_dir)
        elif args.type_command == 'html':
            lib_dir = args.lib_dir
            if not lib_dir:
                # Generate default lib_dir based on filename
                base_name = os.path.splitext(os.path.basename(args.file))[0]
                lib_dir = f"{base_name}-btk"
                # Make it unique if needed
                if os.path.exists(lib_dir):
                    i = 1
                    while os.path.exists(f"{lib_dir}_{i}"):
                        i += 1
                    lib_dir = f"{lib_dir}_{i}"
            utils.ensure_dir(lib_dir)
            utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
            bookmarks = utils.load_bookmarks(lib_dir)
            bookmarks = tools.import_bookmarks_html_generic(args.file, bookmarks, lib_dir)
            utils.save_bookmarks(bookmarks, None, lib_dir)
        elif args.type_command == 'dir':
            lib_dir = args.lib_dir
            if not lib_dir:
                # Generate default lib_dir based on directory name
                dir_name = os.path.basename(os.path.abspath(args.directory))
                lib_dir = f"{dir_name}-btk"
                # Make it unique if needed
                if os.path.exists(lib_dir):
                    i = 1
                    while os.path.exists(f"{lib_dir}_{i}"):
                        i += 1
                    lib_dir = f"{lib_dir}_{i}"
            utils.ensure_dir(lib_dir)
            utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
            bookmarks = utils.load_bookmarks(lib_dir)
            recursive = not args.no_recursive
            formats = args.formats if hasattr(args, 'formats') and args.formats else None
            bookmarks = tools.import_bookmarks_directory(args.directory, bookmarks, lib_dir, 
                                                        recursive=recursive, formats=formats)
            utils.save_bookmarks(bookmarks, None, lib_dir)
        else:
            logging.error(f"No import support for '{args.type_command}'.")

    elif args.command == 'jmespath':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)

        bookmarks = utils.load_bookmarks(lib_dir)
        results, the_type = utils.jmespath_query(bookmarks, args.query)

        if the_type == "filter":
            if args.output:
                utils.save_bookmarks(results, lib_dir, args.output)
            elif args.json:
                console.print(JSON(json.dumps(results, indent=2)))
            else:
                tools.list_bookmarks(results)

        elif the_type == "transform":
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(results, f, indent=2)
            elif args.json:
                console.print(JSON(json.dumps(results, indent=2)))
            elif isinstance(results, list):
                if results and isinstance(results[0], dict):
                    # List of dictionaries
                    table = Table(title="Results", show_header=True, header_style="bold magenta")
                    for key in results[0].keys():
                        table.add_column(key, style="bold")
                    for item in results:
                        table.add_row(*[str(value) for value in item.values()])
                    console.print(table)
                else:
                    # List of strings or other primitives
                    for item in results:
                        console.print(item)
            elif isinstance(results, dict):
                table = Table(title="Results", show_header=True, header_style="bold magenta")
                for key in results.keys():
                    table.add_column(key, style="bold")
                table.add_row(*[str(value) for value in results.values()])
                console.print(table)
            else:
                console.print(results)

        else:
            raise ValueError(f"Unknown JMESPath query type: {the_type}")

    elif args.command == 'auto-tag':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        
        bookmarks = utils.load_bookmarks(lib_dir)
        
        # Analyze mode
        if args.analyze:
            stats = auto_tag.analyze_tagging_coverage(bookmarks)
            console.print(Panel("[bold cyan]Tagging Coverage Analysis[/bold cyan]", expand=False))
            console.print(f"Total bookmarks: {stats['total_bookmarks']}")
            console.print(f"Tagged bookmarks: {stats['tagged_bookmarks']} ({stats['coverage_percentage']:.1f}%)")
            console.print(f"Untagged bookmarks: {stats['untagged_bookmarks']}")
            console.print(f"Unique tags: {stats['total_unique_tags']}")
            console.print(f"Average tags per bookmark: {stats['average_tags_per_bookmark']:.2f}")
            console.print(f"Single-use tags: {stats['single_use_tags']}")
            
            if stats['most_used_tags']:
                console.print("\n[bold]Most used tags:[/bold]")
                for tag, count in stats['most_used_tags'][:10]:
                    console.print(f"  {tag}: {count} bookmarks")
            
            if stats['auto_tag_candidates']:
                console.print(f"\n[bold]Found {stats['total_candidates']} candidates for auto-tagging[/bold]")
                console.print("Top candidates:")
                for candidate in stats['auto_tag_candidates'][:5]:
                    console.print(f"  #{candidate['id']}: {candidate['title'][:50]}...")
                    console.print(f"    Current tags: {candidate['current_tags'] or 'none'}")
            
            sys.exit(0)
        
        # Tag specific bookmark
        if args.id:
            bookmark = utils.find_bookmark(bookmarks, args.id)
            if not bookmark:
                console.print(f"[red]Bookmark with ID {args.id} not found.[/red]")
                sys.exit(1)
            
            if args.enrich:
                bookmark = auto_tag.enrich_bookmark_content(bookmark)
            
            if args.dry_run:
                suggested_tags = auto_tag.suggest_tags_for_bookmark(bookmark)
                console.print(f"[cyan]Suggested tags for bookmark #{args.id}:[/cyan]")
                console.print(f"  Current: {bookmark.get('tags', [])}")
                console.print(f"  Suggested: {suggested_tags}")
                new_tags = [t for t in suggested_tags if t not in bookmark.get('tags', [])]
                if new_tags:
                    console.print(f"  New tags to add: {new_tags}")
            else:
                original_tags = bookmark.get('tags', []).copy()
                bookmark = auto_tag.auto_tag_bookmark(bookmark, replace=args.replace)
                new_tags = [t for t in bookmark.get('tags', []) if t not in original_tags]
                
                if new_tags:
                    utils.save_bookmarks(bookmarks, None, lib_dir)
                    console.print(f"[green]Tagged bookmark #{args.id} with: {new_tags}[/green]")
                else:
                    console.print(f"[yellow]No new tags suggested for bookmark #{args.id}[/yellow]")
        
        # Tag multiple bookmarks
        elif args.all or args.untagged or args.filter_url or args.filter_domain:
            # Create filter
            filter_func = auto_tag.create_filter_for_auto_tag(
                untagged_only=args.untagged,
                url_pattern=args.filter_url,
                domain=args.filter_domain
            )
            
            # Enrich if requested
            if args.enrich:
                console.print("[cyan]Enriching bookmarks with content...[/cyan]")
                for i, bookmark in enumerate(bookmarks):
                    if filter_func(bookmark):
                        bookmarks[i] = auto_tag.enrich_bookmark_content(bookmark)
            
            # Tag bookmarks
            modified_bookmarks, stats = auto_tag.auto_tag_bookmarks(
                bookmarks,
                filter_func=filter_func if not args.all else None,
                replace=args.replace,
                dry_run=args.dry_run
            )
            
            # Display results
            console.print(Panel(f"[bold]{'Preview' if args.dry_run else 'Results'}[/bold]", expand=False))
            console.print(f"Processed: {stats['total_processed']} bookmarks")
            console.print(f"Tagged: {stats['total_tagged']} bookmarks")
            console.print(f"Tags added: {stats['total_tags_added']}")
            
            if stats['most_common_tags']:
                console.print("\n[bold]Most common new tags:[/bold]")
                for tag, count in list(stats['most_common_tags'].items())[:10]:
                    console.print(f"  {tag}: {count} bookmarks")
            
            if not args.dry_run and stats['total_tagged'] > 0:
                utils.save_bookmarks(modified_bookmarks, None, lib_dir)
                console.print(f"\n[green]Successfully auto-tagged {stats['total_tagged']} bookmarks![/green]")
        
        else:
            console.print("[yellow]Please specify --id, --all, --untagged, or a filter option.[/yellow]")
            sys.exit(1)

    elif args.command == 'archive':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        
        bookmarks = utils.load_bookmarks(lib_dir)
        arch = archiver.get_archiver()
        cache = content_cache.get_cache()
        
        # Show cache statistics
        if args.cache_stats:
            stats = cache.get_stats()
            console.print(Panel("[bold cyan]Cache Statistics[/bold cyan]", expand=False))
            console.print(f"Memory items: {stats['memory_items']}")
            console.print(f"Disk items: {stats['disk_items']}")
            console.print(f"Cache hits: {stats['hits']}")
            console.print(f"Cache misses: {stats['misses']}")
            console.print(f"Hit rate: {stats['hit_rate']:.1%}")
            console.print(f"Evictions: {stats['evictions']}")
            console.print(f"Cache directory: {stats['cache_dir']}")
            sys.exit(0)
        
        # Show archive summary
        if args.summary:
            summary = arch.export_archive_summary()
            console.print(summary)
            sys.exit(0)
        
        # Search in cached content
        if args.search:
            results = content_cache.search_cached_content(args.search, bookmarks)
            if results:
                console.print(Panel(f"[bold]Found {len(results)} matches in cached content[/bold]", expand=False))
                for result in results[:10]:
                    bookmark = result['bookmark']
                    console.print(f"\n[bold cyan]#{bookmark['id']}: {bookmark['title']}[/bold cyan]")
                    console.print(f"URL: {bookmark['url']}")
                    console.print(f"Score: {result['score']}, Matches in: {', '.join(result['matches'])}")
                    if result['snippet']:
                        console.print(f"Snippet: ...{result['snippet']}...")
            else:
                console.print("[yellow]No matches found in cached content.[/yellow]")
            sys.exit(0)
        
        # Archive specific bookmark
        if args.id:
            bookmark = utils.find_bookmark(bookmarks, args.id)
            if not bookmark:
                console.print(f"[red]Bookmark with ID {args.id} not found.[/red]")
                sys.exit(1)
            
            console.print(f"[cyan]Archiving bookmark #{args.id}...[/cyan]")
            result = arch.archive_bookmark(bookmark, save_to_wayback=args.wayback)
            
            if result:
                console.print(f"[green]Successfully archived bookmark #{args.id}[/green]")
                console.print(f"Archive key: {result['archive_key']}")
                console.print(f"Timestamp: {result['timestamp']}")
                if result.get('wayback_url'):
                    console.print(f"Wayback URL: {result['wayback_url']}")
            else:
                console.print(f"[red]Failed to archive bookmark #{args.id}[/red]")
        
        # Archive multiple bookmarks
        elif args.all:
            console.print(f"[cyan]Archiving {len(bookmarks)} bookmarks...[/cyan]")
            
            def progress(current, total, url):
                console.print(f"[{current}/{total}] Archiving {url[:50]}...")
            
            stats = arch.bulk_archive(bookmarks, progress_callback=progress)
            
            console.print(Panel("[bold]Archive Results[/bold]", expand=False))
            console.print(f"Total: {stats['total']}")
            console.print(f"Archived: {stats['archived']}")
            console.print(f"Already archived: {stats['already_archived']}")
            console.print(f"Failed: {stats['failed']}")
            if args.wayback:
                console.print(f"Saved to Wayback: {stats['wayback_saved']}")
        
        else:
            console.print("[yellow]Please specify --id, --all, --summary, --cache-stats, or --search.[/yellow]")
            sys.exit(1)

    elif args.command == 'search':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        results = tools.search_bookmarks(bookmarks, args.query)
        if args.json:
            console.print(JSON(bookmarks))
        if results:
            tools.list_bookmarks(results)
        else:
            console.print(f"[red]No bookmarks found matching '{args.query}'.[/red]")

    elif args.command == 'add':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        utils.ensure_dir(lib_dir)
        utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
        bookmarks = utils.load_bookmarks(lib_dir)
        tags = [tag.strip() for tag in args.tags.split(',')] if args.tags else []
        bookmarks = tools.add_bookmark(
            bookmarks,
            title=args.title,
            url=args.url,
            stars=args.star,
            tags=tags,
            description=args.description or "",
            lib_dir=lib_dir
        )
        utils.save_bookmarks(bookmarks, None, lib_dir)
        if args.json:
            # Find the newly added bookmark (it's the last one)
            new_bookmark = bookmarks[-1]
            console.print(JSON(json.dumps(new_bookmark, indent=2)))
        else:
            console.print(f"[green]Bookmark added successfully with ID {bookmarks[-1]['id']}[/green]")

    elif args.command == 'remove':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        removed_bookmark = next((b for b in bookmarks if b['id'] == args.id), None)
        bookmarks = tools.remove_bookmark(bookmarks, args.id)
        utils.save_bookmarks(bookmarks, lib_dir, lib_dir)
        if args.json:
            result = {"removed": removed_bookmark is not None, "bookmark": removed_bookmark}
            console.print(JSON(json.dumps(result, indent=2)))
        else:
            if removed_bookmark:
                console.print(f"[green]Bookmark with ID {args.id} removed successfully[/green]")
            else:
                console.print(f"[red]Bookmark with ID {args.id} not found[/red]")

    elif args.command == 'list':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        if args.indices is not None:
            bookmarks = [b for i, b in enumerate(bookmarks) if i in args.indices]

        if args.json:
            json_data = json.dumps(bookmarks)
            console.print(JSON(json_data))
        else:
            tools.list_bookmarks(bookmarks, args.indices)

    elif args.command == 'edit':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)

        edited_bookmark = None
        for b in bookmarks:
            if b['id'] == args.id:
                edited_bookmark = b.copy()  # Keep original for comparison
                if args.title:
                    b['title'] = args.title
                if args.url:
                    b['url'] = args.url
                if args.stars:
                    b['stars'] = args.stars == 'true'
                if args.tags:
                    b['tags'] = [tag.strip() for tag in args.tags]
                if args.description:
                    b['description'] = args.description
                break

        utils.save_bookmarks(bookmarks, None, lib_dir)
        
        if args.json:
            result = {"edited": edited_bookmark is not None, "bookmark": next((b for b in bookmarks if b['id'] == args.id), None)}
            console.print(JSON(json.dumps(result, indent=2)))
        else:
            if edited_bookmark:
                console.print(f"[green]Bookmark with ID {args.id} updated successfully[/green]")
            else:
                console.print(f"[red]Bookmark with ID {args.id} not found[/red]")
      
    elif args.command == 'visit':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        method = 'browser' if not args.console else 'console'
        bookmarks = utils.load_bookmarks(lib_dir)
        bookmarks = tools.visit_bookmark(bookmarks, args.id, method=method, lib_dir=lib_dir)
        utils.save_bookmarks(bookmarks, None, lib_dir)

    elif args.command == 'merge':
        merge_command = args.merge_command
        lib_dirs = args.lib_dirs
        output_dir = args.output
        utils.ensure_dir(output_dir)

        # Validate all input library directories
        for lib in lib_dirs:
            if not os.path.isdir(lib):
                logging.error(f"The specified library directory '{lib}' does not exist or is not a directory.")
                sys.exit(1)

        if merge_command == 'union':
            merge.union_libraries(libs=lib_dirs, output_dir=output_dir)
        elif merge_command == 'intersection':
            merge.intersection_libraries(libs=lib_dirs, output_dir=output_dir)
        elif merge_command == 'difference':
            merge.difference_libraries(libs=lib_dirs, output_dir=output_dir)
        else:
            logging.error(f"Unknown set command '{merge_command}'.")


    elif args.command == 'reachable':
        utils.check_reachable(bookmarks_dir=args.lib_dir, timeout=args.timeout, concurrency=args.concurrency)
    
    elif args.command == 'purge':
        utils.purge_unreachable(bookmarks_dir=args.lib_dir, confirm=args.confirm)

    elif args.command == 'tag':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        
        bookmarks = utils.load_bookmarks(lib_dir)
        
        if args.tag_command == 'tree':
            # Display tag tree
            tree = tag_utils.get_tag_tree(bookmarks, separator=args.separator)
            if tree:
                console.print(Panel(tag_utils.format_tag_tree(tree), title="Tag Tree", border_style="cyan"))
            else:
                console.print("[yellow]No tags found in the library.[/yellow]")
        
        elif args.tag_command == 'stats':
            # Show tag statistics
            stats = tag_utils.get_tag_statistics(bookmarks, separator=args.separator)
            
            if args.json:
                console.print(JSON(json.dumps(stats, indent=2)))
            else:
                table = Table(title="Tag Statistics", show_header=True, header_style="bold magenta")
                table.add_column("Tag", style="cyan", no_wrap=True)
                table.add_column("Direct", justify="right", style="yellow")
                table.add_column("Total", justify="right", style="green")
                table.add_column("Bookmarks", justify="right", style="blue")
                
                for tag, stat in sorted(stats.items()):
                    table.add_row(
                        tag,
                        str(stat['direct_count']),
                        str(stat['total_count']),
                        str(stat['bookmark_count'])
                    )
                
                console.print(table)
        
        elif args.tag_command == 'rename':
            # Rename tag
            bookmarks, affected = tag_utils.rename_tag_hierarchy(
                bookmarks, args.old_tag, args.new_tag, separator=args.separator
            )
            utils.save_bookmarks(bookmarks, None, lib_dir)
            console.print(f"[green]Renamed tag '{args.old_tag}' to '{args.new_tag}'. {affected} bookmarks affected.[/green]")
        
        elif args.tag_command == 'merge':
            # Merge tags
            bookmarks, affected = tag_utils.merge_tags(bookmarks, args.source_tags, args.into)
            utils.save_bookmarks(bookmarks, None, lib_dir)
            tags_str = ', '.join(args.source_tags)
            console.print(f"[green]Merged tags [{tags_str}] into '{args.into}'. {affected} bookmarks affected.[/green]")
        
        elif args.tag_command == 'filter':
            # Filter by tag prefix
            filtered = tag_utils.filter_bookmarks_by_tag_prefix(
                bookmarks, args.prefix, separator=args.separator
            )
            
            if args.json:
                console.print(JSON(json.dumps(filtered, indent=2)))
            else:
                if filtered:
                    console.print(f"[cyan]Found {len(filtered)} bookmarks with tags starting with '{args.prefix}':[/cyan]")
                    tools.list_bookmarks(filtered)
                else:
                    console.print(f"[yellow]No bookmarks found with tags starting with '{args.prefix}'.[/yellow]")

    elif args.command == 'dedupe':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        
        bookmarks = utils.load_bookmarks(lib_dir)
        
        if args.stats:
            # Show statistics only
            stats = dedup.get_duplicate_stats(bookmarks, key=args.key)
            
            console.print(Panel(
                f"[cyan]Total bookmarks:[/cyan] {stats['total_bookmarks']}\n"
                f"[yellow]Duplicate groups:[/yellow] {stats['duplicate_groups']}\n"
                f"[red]Total duplicates:[/red] {stats['total_duplicates']}\n"
                f"[green]Bookmarks to remove:[/green] {stats['bookmarks_to_remove']}\n"
                f"[magenta]Duplicate percentage:[/magenta] {stats['duplicate_percentage']:.1f}%",
                title="Duplicate Statistics",
                border_style="cyan"
            ))
            
            if stats['most_duplicated']:
                console.print("\n[bold]Most duplicated URLs:[/bold]")
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("URL", style="cyan", no_wrap=True)
                table.add_column("Count", justify="right", style="yellow")
                
                for url, count in stats['most_duplicated']:
                    table.add_row(url[:80] + "..." if len(url) > 80 else url, str(count))
                
                console.print(table)
        
        elif args.preview:
            # Preview deduplication
            deduplicated = dedup.preview_deduplication(bookmarks, strategy=args.strategy, key=args.key)
            removed_count = len(bookmarks) - len(deduplicated)
            
            console.print(f"[cyan]Preview: Would remove {removed_count} duplicate bookmarks[/cyan]")
            console.print(f"[green]Remaining bookmarks: {len(deduplicated)}[/green]")
            
            # Show a few examples of what would be removed
            duplicates = dedup.find_duplicates(bookmarks, key=args.key)
            if duplicates:
                console.print("\n[bold]Example duplicates that would be handled:[/bold]")
                count = 0
                for url, group in list(duplicates.items())[:3]:
                    count += 1
                    console.print(f"\n[yellow]Duplicate group {count}: {url}[/yellow]")
                    for i, bookmark in enumerate(group):
                        console.print(f"  {i+1}. {bookmark.get('title', 'No title')} (visits: {bookmark.get('visit_count', 0)})")
        
        else:
            # Perform deduplication
            deduplicated, removed = dedup.deduplicate_bookmarks(
                bookmarks, strategy=args.strategy, key=args.key
            )
            
            if removed:
                # Save removed bookmarks if requested
                if args.output_removed:
                    utils.ensure_dir(args.output_removed)
                    utils.save_bookmarks(removed, None, args.output_removed)
                    console.print(f"[cyan]Saved {len(removed)} removed bookmarks to '{args.output_removed}'[/cyan]")
                
                # Update the library
                utils.save_bookmarks(deduplicated, None, lib_dir)
                
                console.print(f"[green]Successfully removed {len(removed)} duplicate bookmarks![/green]")
                console.print(f"[cyan]Strategy used: {args.strategy}[/cyan]")
                console.print(f"[cyan]Remaining bookmarks: {len(deduplicated)}[/cyan]")
            else:
                console.print("[yellow]No duplicates found![/yellow]")

    elif args.command == 'bulk':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        
        bookmarks = utils.load_bookmarks(lib_dir)
        
        if args.bulk_command == 'add':
            # Bulk add from file
            tags = [tag.strip() for tag in args.tags.split(',')] if args.tags else []
            
            try:
                bookmarks, success_count, failed_urls = bulk_ops.bulk_add_from_file(
                    args.from_file,
                    bookmarks,
                    lib_dir,
                    default_tags=tags,
                    fetch_titles=not args.no_fetch_titles
                )
                
                if success_count > 0:
                    utils.save_bookmarks(bookmarks, None, lib_dir)
                    console.print(f"[green]Successfully added {success_count} bookmarks![/green]")
                else:
                    console.print("[yellow]No new bookmarks were added.[/yellow]")
                
                if failed_urls:
                    console.print(f"[red]Failed to add {len(failed_urls)} URLs:[/red]")
                    for url in failed_urls[:10]:  # Show first 10
                        console.print(f"  - {url}")
                    if len(failed_urls) > 10:
                        console.print(f"  ... and {len(failed_urls) - 10} more")
                        
            except FileNotFoundError as e:
                console.print(f"[red]Error: {e}[/red]")
                sys.exit(1)
        
        elif args.bulk_command == 'edit':
            # Create filter
            filter_func = bulk_ops.create_filter_from_criteria(
                tag_prefix=args.filter_tags,
                url_pattern=args.filter_url,
                is_starred=True if args.filter_starred else (False if args.filter_unstarred else None)
            )
            
            # Count matching bookmarks
            matching = [b for b in bookmarks if filter_func(b)]
            
            if not matching:
                console.print("[yellow]No bookmarks match the filter criteria.[/yellow]")
                sys.exit(0)
            
            if args.preview:
                # Preview mode
                console.print(f"[cyan]Preview: Would edit {len(matching)} bookmarks:[/cyan]")
                for b in matching[:5]:  # Show first 5
                    console.print(f"  - {b['title']} ({b['url']})")
                if len(matching) > 5:
                    console.print(f"  ... and {len(matching) - 5} more")
                
                # Show what would be changed
                console.print("\n[yellow]Changes to apply:[/yellow]")
                if args.add_tags:
                    console.print(f"  Add tags: {args.add_tags}")
                if args.remove_tags:
                    console.print(f"  Remove tags: {args.remove_tags}")
                if args.set_stars:
                    console.print(f"  Set stars: {args.set_stars}")
                if args.set_description:
                    console.print(f"  Set description: {args.set_description[:50]}...")
            else:
                # Apply edits
                add_tags = [tag.strip() for tag in args.add_tags.split(',')] if args.add_tags else None
                remove_tags = [tag.strip() for tag in args.remove_tags.split(',')] if args.remove_tags else None
                set_stars = True if args.set_stars == 'true' else (False if args.set_stars == 'false' else None)
                
                bookmarks, edited_count = bulk_ops.bulk_edit_bookmarks(
                    bookmarks,
                    filter_func,
                    add_tags=add_tags,
                    remove_tags=remove_tags,
                    set_stars=set_stars,
                    set_description=args.set_description
                )
                
                if edited_count > 0:
                    utils.save_bookmarks(bookmarks, None, lib_dir)
                    console.print(f"[green]Successfully edited {edited_count} bookmarks![/green]")
                else:
                    console.print("[yellow]No bookmarks were edited.[/yellow]")
        
        elif args.bulk_command == 'remove':
            # Create filter
            filter_func = bulk_ops.create_filter_from_criteria(
                tag_prefix=args.filter_tags,
                url_pattern=args.filter_url,
                min_visits=args.filter_visits_min,
                max_visits=args.filter_visits_max,
                has_description=False if args.filter_no_description else None
            )
            
            # Count matching bookmarks
            matching = [b for b in bookmarks if filter_func(b)]
            
            if not matching:
                console.print("[yellow]No bookmarks match the filter criteria.[/yellow]")
                sys.exit(0)
            
            if args.preview:
                # Preview mode
                console.print(f"[red]Preview: Would remove {len(matching)} bookmarks:[/red]")
                for b in matching[:10]:  # Show first 10
                    console.print(f"  - {b['title']} ({b['url']})")
                if len(matching) > 10:
                    console.print(f"  ... and {len(matching) - 10} more")
            else:
                # Apply removals
                remaining, removed = bulk_ops.bulk_remove_bookmarks(bookmarks, filter_func)
                
                if removed:
                    # Save removed bookmarks if requested
                    if args.output_removed:
                        utils.ensure_dir(args.output_removed)
                        utils.save_bookmarks(removed, None, args.output_removed)
                        console.print(f"[cyan]Saved {len(removed)} removed bookmarks to '{args.output_removed}'[/cyan]")
                    
                    # Update the library
                    utils.save_bookmarks(remaining, None, lib_dir)
                    console.print(f"[green]Successfully removed {len(removed)} bookmarks![/green]")
                else:
                    console.print("[yellow]No bookmarks were removed.[/yellow]")

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
