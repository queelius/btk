import json
import argparse
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import os
import requests
import logging
import sys
import webbrowser
from colorama import init as colorama_init, Fore, Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.json import JSON
import cloud
import networkx as nx
import utils
import merge

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def import_bookmarks(bookmarks, html_file, lib_dir):
    """Import bookmarks from a Netscape Bookmark Format HTML file into the specified library directory."""
    if not os.path.exists(html_file):
        logging.error(f"HTML file '{html_file}' does not exist.")
        return bookmarks

    with open(html_file, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # Determine the directory of the HTML file to resolve relative favicon paths
    html_dir = os.path.dirname(os.path.abspath(html_file))

    # Iterate over each fieldset (representing a bookmark window/session)
    fieldsets = soup.find_all('fieldset', class_='window')
    logging.info(f"Found {len(fieldsets)} bookmark windows/sessions to import.")

    for fieldset in fieldsets:
        legend = fieldset.find('legend')
        if legend:
            date_str = legend.get_text(strip=True)
            added = utils.parse_date(date_str)
        else:
            logging.warning("No <legend> tag found in fieldset. Using current UTC time.")
            added = datetime.now(timezone.utc).isoformat()

        # Iterate over each bookmark within the fieldset
        for p in fieldset.find_all('p'):
            a_tags = p.find_all('a', href=True)
            img_tag = p.find('img', src=True)
            favicon_url = img_tag['src'] if img_tag else None

            # Handle favicon
            if favicon_url:
                if utils.is_remote_url(favicon_url):
                    favicon_path = utils.download_favicon(favicon_url, lib_dir)
                else:
                    favicon_path = utils.copy_local_favicon(favicon_url, html_dir, lib_dir)
            else:
                favicon_path = None

            if len(a_tags) >= 2:
                # Assuming the second <a> tag contains the actual bookmark
                url = a_tags[1]['href']
                title = a_tags[1].get_text(strip=True)

                # Check for duplicates based on unique_id
                unique_id = utils.generate_unique_id(url, title)
                if any(b['unique_id'] == unique_id for b in bookmarks):
                    logging.info(f"Duplicate bookmark found for URL '{url}' and Title '{title}'. Skipping.")
                    continue

                # Assign a unique ID
                bookmark_id = utils.get_next_id(bookmarks)

                # Create bookmark entry with default values
                bookmark = {
                    'id': bookmark_id,
                    'unique_id': unique_id,
                    'title': title,
                    'url': url,
                    'added': added,
                    'stars': False,
                    'tags': [],
                    'visit_count': 0,
                    'description': "",
                    'favicon': favicon_path,
                    'last_visited': None
                }

                bookmarks.append(bookmark)
                logging.info(f"Imported bookmark: ID {bookmark_id} - '{title}' - {url}")
            else:
                logging.warning("Insufficient <a> tags found in <p>. Skipping this entry.")

    logging.info(f"Import complete. Total bookmarks: {len(bookmarks)}")
    return bookmarks

def search_bookmarks(bookmarks, query):
    """Search bookmarks by title or URL containing the query (case-insensitive)."""
    results = [b for b in bookmarks if query.lower() in b['title'].lower() or query.lower() in b['url'].lower()]
    logging.info(f"Found {len(results)} bookmarks matching query '{query}'.")
    return results

def add_bookmark(bookmarks, title, url, stars=False, tags=None, description="", lib_dir=None):
    """Add a new bookmark with optional stars, tags, and description."""
    unique_id = utils.generate_unique_id(url, title)
    if any(b['unique_id'] == unique_id for b in bookmarks):
        logging.error(f"A bookmark with URL '{url}' and Title '{title}' already exists.")
        return bookmarks

    if tags is None:
        tags = []

    bookmark_id = utils.get_next_id(bookmarks)

    bookmark = {
        'id': bookmark_id,
        'unique_id': unique_id,
        'title': title,
        'url': url,
        'added': datetime.now(timezone.utc).isoformat(),
        'stars': stars,
        'tags': tags,
        'visit_count': 0,
        'description': description,
        'favicon': None,  # Optional: Can be set manually later
        'last_visited': None
    }

    bookmarks.append(bookmark)
    logging.info(f"Added new bookmark: ID {bookmark_id} - '{title}' - {url}")
    return bookmarks

def remove_bookmark(bookmarks, bookmark_id):
    """Remove a bookmark by its ID."""
    initial_count = len(bookmarks)
    bookmarks = [b for b in bookmarks if b['id'] != bookmark_id]
    final_count = len(bookmarks)
    if final_count < initial_count:
        logging.info(f"Removed bookmark with ID {bookmark_id}.")
    else:
        logging.warning(f"No bookmark found with ID {bookmark_id}.")
    return bookmarks

def list_bookmarks(bookmarks):
    """List all bookmarks with their IDs and unique IDs."""
    if not bookmarks:
        console.print(f"[red]No bookmarks available.[/red]")
        return
    table = Table(title="List of Bookmarks", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Unique ID", style="green")
    table.add_column("Title", style="bold")
    table.add_column("URL", style="underline blue")
    table.add_column("Tags", style="yellow")
    table.add_column("Stars", style="#FFD700")  # Using hex code for gold
    table.add_column("Visits", style="magenta")
    table.add_column("Last Visited", style="dim")
    
    for b in bookmarks:
        stars = "⭐" if b.get('stars') else ""
        tags = ", ".join(b.get('tags', []))
        last_visited = b.get('last_visited') or "-"
        table.add_row(
            str(b['id']),
            b['unique_id'],
            b['title'],
            b['url'],
            tags,
            stars,
            str(b.get('visit_count', 0)),
            last_visited
        )
    
    console.print(table)

def visit_bookmark(bookmarks, bookmark_id, method='browser', lib_dir=None):
    """
    Visit a bookmark either through the browser or console.
    - method: 'browser' or 'console'
    """
    for bookmark in bookmarks:
        if bookmark['id'] == bookmark_id:
            if method == 'browser':
                try:
                    webbrowser.open(bookmark['url'])
                    logging.info(f"Opened '{bookmark['title']}' in the default browser.")
                except Exception as e:
                    logging.error(f"Failed to open URL '{bookmark['url']}' in browser: {e}")
            elif method == 'console':
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (compatible; BookmarkTool/1.0)'
                    }
                    response = requests.get(bookmark['url'], headers=headers, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    text = soup.get_text(separator='\n')
                    # Use rich to display content
                    content = Text(text[:1000] + "...", style="dim")
                    panel = Panel.fit(
                        content,
                        title=bookmark['title'],
                        subtitle=bookmark['url'],
                        border_style="green"
                    )
                    console.print(panel)
                except requests.RequestException as e:
                    logging.error(f"Failed to retrieve content from '{bookmark['url']}': {e}")
                except Exception as e:
                    logging.error(f"Error processing content from '{bookmark['url']}': {e}")
            else:
                logging.error(f"Unknown visit method '{method}'.")
                return bookmarks
            # Increment visit_count and update last_visited
            bookmark['visit_count'] += 1
            bookmark['last_visited'] = datetime.now(timezone.utc).isoformat()
            logging.info(f"Updated visit_count for '{bookmark['title']}' to {bookmark['visit_count']}.")
            return bookmarks
    logging.warning(f"No bookmark found with ID {bookmark_id}.")
    return bookmarks


def main():
    parser = argparse.ArgumentParser(description='Bookmark Management Tool')
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Import command
    import_parser = subparsers.add_parser('import', help='Import bookmarks from a Netscape Bookmark Format HTML file')
    import_parser.add_argument('html_file', type=str, help='Path to the HTML bookmark file')
    import_parser.add_argument('lib_dir', type=str, help='Directory to store the imported bookmarks library')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search bookmarks by query')
    search_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to search')
    search_parser.add_argument('query', type=str, help='Search query (searches in title and URL)')
    search_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # List-Index command
    list_parser = subparsers.add_parser('list-index', help='List the bookmarks with the given indices')
    list_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library')
    list_parser.add_argument('indices', type=int, nargs='+', help='Indices of the bookmarks to list')
    list_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new bookmark')
    add_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to add to')
    add_parser.add_argument('title', type=str, help='Title of the bookmark')
    add_parser.add_argument('url', type=str, help='URL of the bookmark')
    add_parser.add_argument('--star', action='store_true', help='Mark the bookmark as favorite')
    add_parser.add_argument('--tags', type=str, help='Comma-separated tags for the bookmark')
    add_parser.add_argument('--description', type=str, help='Description or notes for the bookmark')

    # Edit command
    edit_parser = subparsers.add_parser('edit', help='Edit a bookmark by its ID')
    edit_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to edit')
    edit_parser.add_argument('id', type=int, help='ID of the bookmark to edit')
    edit_parser.add_argument('--title', type=str, help='New title of the bookmark')
    edit_parser.add_argument('--url', type=str, help='New URL of the bookmark')
    edit_parser.add_argument('--stars', action='store_true', help='Mark the bookmark as favorite')
    edit_parser.add_argument('--tags', type=str, nargs='+', help='Comma-separated tags for the bookmark')
    edit_parser.add_argument('--description', type=str, help='Description or notes for the bookmark')

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a bookmark by its ID')
    remove_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to remove from')
    remove_parser.add_argument('id', type=int, help='ID of the bookmark to remove')

    # List command
    list_parser = subparsers.add_parser('list', help='List all bookmarks with their IDs and unique IDs')
    list_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to list')
    list_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Visit command
    visit_parser = subparsers.add_parser('visit', help='Visit a bookmark by its ID')
    visit_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to visit from')
    visit_parser.add_argument('id', type=int, help='ID of the bookmark to visit')
    group = visit_parser.add_mutually_exclusive_group()
    group.add_argument('--browser', action='store_true', help='Visit the bookmark in the default web browser (default)')
    group.add_argument('--console', action='store_true', help='Display the bookmark content in the console')

    # Set Operations
    set_parser = subparsers.add_parser('merge', help='Perform merge (set) operations on bookmark libraries')
    set_subparsers = set_parser.add_subparsers(dest='merge_command', required=True, help='Set operation commands')

    # Union
    union_parser = set_subparsers.add_parser('union', help='Perform set union of multiple bookmark libraries')
    union_parser.add_argument('lib_dirs', type=str, nargs='+', help='Directories of the bookmark libraries to union')
    union_parser.add_argument('output_dir', type=str, help='Directory to store the union result')

    # Intersection
    intersection_parser = set_subparsers.add_parser('intersection', help='Perform set intersection of multiple bookmark libraries')
    intersection_parser.add_argument('lib_dirs', type=str, nargs='+', help='Directories of the bookmark libraries to intersect')
    intersection_parser.add_argument('output_dir', type=str, help='Directory to store the intersection result')

    # Difference
    difference_parser = set_subparsers.add_parser('difference', help='Perform set difference (first minus others) of bookmark libraries')
    difference_parser.add_argument('lib_dirs', type=str, nargs='+', help='Directories of the bookmark libraries (first library minus the rest)')
    difference_parser.add_argument('output_dir', type=str, help='Directory to store the difference result')

    # Cloud command
    cloud_parser = subparsers.add_parser('cloud', help='Generate a URL mention graph from bookmarks')
    cloud_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to analyze')
    cloud_parser.add_argument('--output-file', type=str, help='Path to save the graph image (e.g., graph.png or graph.html)')
    cloud_parser.add_argument('--max-bookmarks', type=int, default=100, help='Maximum number of bookmarks to process')
    cloud_parser.add_argument(
        '--no-only-in-library',
        action='store_false',
        dest='only_in_library',
        help='Include all mentioned URLs as nodes, regardless of their presence in the library')
    cloud_parser.add_argument(
        '--ignore-ssl',
        action='store_true',
        help='Ignore SSL certificate verification (not recommended)')
    cloud_parser.add_argument('--stats', action='store_true', help='Display graph statistics')


    # Reachable command
    reachable_parser = subparsers.add_parser('reachable', help='Check and mark bookmarks as reachable or not')
    reachable_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to analyze')
    reachable_parser.add_argument('--timeout', type=int, default=10, help='Timeout for HTTP requests in seconds')
    reachable_parser.add_argument('--concurrency', type=int, default=10, help='Number of concurrent HTTP requests')
    
    # Purge command
    purge_parser = subparsers.add_parser('purge', help='Remove bookmarks marked as not reachable')
    purge_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to purge')
    purge_parser.add_argument('--confirm', action='store_true', help='Ask for confirmation before purging')
    
    # Cloud command and others..

    args = parser.parse_args()

    if args.command == 'import':
        lib_dir = args.lib_dir
        utils.ensure_dir(lib_dir)
        utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
        bookmarks = utils.load_bookmarks(lib_dir)
        bookmarks = import_bookmarks(bookmarks, args.html_file, lib_dir)
        utils.save_bookmarks(bookmarks, lib_dir)

    elif args.command == 'search':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        results = search_bookmarks(bookmarks, args.query)
        if args.json:
            console.print(JSON(bookmarks))
        if results:
            table = Table(title=f"Search Results for '{args.query}'", show_header=True, header_style="bold magenta")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Unique ID", style="green")
            table.add_column("Title", style="bold")
            table.add_column("URL", style="underline blue")
            table.add_column("Tags", style="yellow")
            table.add_column("Stars", style="#FFD700")  # Using hex code for gold
            table.add_column("Visits", style="magenta")
            table.add_column("Last Visited", style="dim")
            
            for b in results:
                stars = "⭐" if b.get('stars') else ""
                tags = ", ".join(b.get('tags', []))
                last_visited = b.get('last_visited') or "-"
                table.add_row(
                    str(b['id']),
                    b['unique_id'],
                    b['title'],
                    b['url'],
                    tags,
                    stars,
                    str(b.get('visit_count', 0)),
                    last_visited
                )
            
            console.print(table)
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
        bookmarks = add_bookmark(
            bookmarks,
            title=args.title,
            url=args.url,
            stars=args.star,
            tags=tags,
            description=args.description or "",
            lib_dir=lib_dir
        )
        utils.save_bookmarks(bookmarks, lib_dir)

    elif args.command == 'remove':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        bookmarks = remove_bookmark(bookmarks, args.id)
        utils.save_bookmarks(bookmarks, lib_dir)

    elif args.command == 'list':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        if args.json:
            json_data = json.dumps(bookmarks)
            console.print(JSON(json_data))
        else:
            list_bookmarks(bookmarks)

    elif args.command == 'edit':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)

        print(args.tags)
        
        for b in bookmarks:
            if b['id'] == args.id:
                if args.title is not None:
                    b['title'] = args.title
                if args.url is not None:
                    b['url'] = args.url
                if args.stars is not None:
                    b['stars'] = args.stars
                if args.tags is not None:
                    b['tags'] = [tag.strip() for tag in args.tags]
                if args.description is not None:
                    b['description'] = args.description
                break

        utils.save_bookmarks(bookmarks, lib_dir)
      
    elif args.command == 'list-index':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        if args.json:
            results = [b for b in bookmarks if b['id'] in args.indices]
            json_data = json.dumps(results)
            console.print(JSON(json_data))
        else:
            list_bookmarks([b for b in bookmarks if b['id'] in args.indices])

    elif args.command == 'visit':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        method = 'browser' if not args.console else 'console'
        bookmarks = utils.load_bookmarks(lib_dir)
        bookmarks = visit_bookmark(bookmarks, args.id, method=method, lib_dir=lib_dir)
        utils.save_bookmarks(bookmarks, lib_dir)

    elif args.command == 'merge':
        merge_command = args.set_command
        lib_dirs = args.lib_dirs
        output_dir = args.output_dir
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

    elif args.command == 'cloud':
            lib_dir = args.lib_dir
            output_file = args.output_file
            max_bookmarks = args.max_bookmarks
            only_in_library = args.only_in_library
            ignore_ssl = args.ignore_ssl
            stats = args.stats

            if output_file and not output_file.endswith(('.html', '.png', '.json')):
                logging.error("Output file must be either an HTML file, PNG file, or JSON file.")
                sys.exit(1)

            if not os.path.isdir(lib_dir):
                logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
                sys.exit(1)
            
            bookmarks = merge.load_bookmarks(lib_dir)
            if not bookmarks:
                logging.error(f"No bookmarks found in '{lib_dir}'.")
                sys.exit(1)
            
            graph = cloud.generate_url_graph(
                bookmarks,
                max_bookmarks=max_bookmarks,
                only_in_library=only_in_library,
                ignore_ssl=ignore_ssl)
            
            if stats:
                from cloud import display_graph_stats
                display_graph_stats(graph)
            # Optional: Visualize the graph
            if output_file:
                if output_file.endswith('.html'):
                    # Interactive visualization with pyvis
                    cloud.visualize_graph_pyvis(graph, output_file)
                elif output_file.endswith('.json'):
                    graph_json = nx.node_link_data(graph)  # Convert to node-link format
                    console.print(JSON(json.dumps(graph_json, indent=2)))
                else: # file.endswith('.png'):
                    # Static visualization with matplotlib
                    cloud.visualize_graph_png(graph, output_file)
            else:
                # If no output file specified, print graph stats
                console.print(f"[bold green]Graph generated successfully![/bold green]")
                console.print(f"Nodes: {graph.number_of_nodes()}")
                console.print(f"Edges: {graph.number_of_edges()}")

    elif args.command == 'reachable':
        # Call reachable function
        utils.check_reachable(bookmarks_dir=args.lib_dir, timeout=args.timeout, concurrency=args.concurrency)
    
    elif args.command == 'purge':
        # Call purge function
        utils.purge_unreachable(bookmarks_dir=args.lib_dir, confirm=args.confirm)

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
