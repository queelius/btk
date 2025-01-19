# Project Directory: btk

## Documentation Files


### README.md


'''markdown
# Bookmark Toolkit (btk)

Bookmark Toolkit (btk) is a command-line tool for managing and analyzing bookmarks. It provides features for importing, searching, editing, and exporting bookmarks, as well as querying them using JMESPath.

## Installation

To install `bookmark-tk`, you can use `pip`:

```sh
pip install bookmark-tk
```

## Usage

It installs a command-line took, `btk`. To see how to use it, type:

```sh
btk --help
```

### Commands

- **import**: Import bookmarks from various formats, e.g., Netscape Bookmark Format HTML file.
  ```sh
  btk import oldbookmarks --format netscape --output bookmarks
  ```

- **search**: Search bookmarks by query.
  ```sh
  btk search mybookmarks "statistics"
  ```

- **list-index**: List the bookmarks with the given indices.
  ```sh
  btk list-index mybookmarks 1 2 3
  ```

- **add**: Add a new bookmark.
  ```sh
  btk add mybookmarks --title "My Bookmark" --url "https://example.com"
  ```

- **edit**: Edit a bookmark by its ID.
  ```sh
  btk edit mybookmarks 1 --title "Updated Title"
  ```

- **remove**: Remove a bookmark by its ID.
  ```sh
  btk remove mybookmarks 2
  ```

- **list**: List all bookmarks (including metadata).
  ```sh
  btk list mybookmarks
  ```

- **visit**: Visit a bookmark by its ID.
  ```sh
  btk visit mybookmarks 103
  ```

- **merge**: Perform merge (set) operations on bookmark libraries.
  ```sh
  btk merge union lib1 lib2 lib3 --output merged
  ```

- **cloud**: Generate a URL mention graph from bookmarks.
  ```sh
  btk cloud mybookmarks --output graph.png
  ```

- **reachable**: Check and mark bookmarks as reachable or not.
  ```sh
  btk reachable mybookmarks
  ```

- **purge**: Remove bookmarks marked as not reachable.
  ```sh
  btk purge mybookmarks --output purged
  ```

- **export**: Export bookmarks to a different format.
  ```sh
  btk export mybookmarks --output bookmarks.csv
  ```

- **jmespath**: Query bookmarks using JMESPath.
  ```sh
  btk jmespath mybookmarks "[?visit_count > \`0\`].title"
  ```

## Example JMESPath Queries

- Get all starred bookmarks:
  ```sh
  btk jmespath mybookmarks "[?stars == \`true\`].title"
  ```
- Get URLs of frequently visited bookmarks:
  ```sh
  btk jmespath mybookmarks "[?visit_count > \`5\`].url"
  ```
- Get bookmarks that contain 'wikipedia' in the URL:
  ```sh
  btk jmespath mybookmarks "[?contains(url, 'wikipedia')].{title: title, url: url}"
  ```

## License

This project is licensed under the MIT License.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue if you have suggestions or improvements.

## Author

Developed by [Alex Towell](https://github.com/queelius).

'''

## Source Files

#### Source File: `btk/btk__init__.py`

```python

```

#### Source File: `btk/cli.py`

```python
import json
import argparse
import os
import logging
import sys
from colorama import init as colorama_init, Fore, Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.json import JSON
import btk.cloud as cloud
import networkx as nx
import btk.utils as utils
import btk.merge as merge
import btk.tools as tools
import btk.llm as llm

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def main():
    parser = argparse.ArgumentParser(description='Bookmark Toolkit (btk) - Manage and analyze bookmarks')
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
    cloud_parser.add_argument('--links-url', action='store_true', default=True, help='Links are URL mentions')
    cloud_parser.add_argument('--links-tag', action='store_true', default=False, help='Links are overlapping tags')
    cloud_parser.add_argument('--links-creation-timestamp', action='store_true', default=False, help='Links are creation timestamps within a threshold')

    cloud_parser.add_argument('--links-creation-timestamp-threshold', type=int, default=30, help='Threshold for links creation timestamp (in days)')

    cloud_parser.add_argument('--links-visit-count', action='store_true', default=False, help='Links are visit counts within a threshold')
    cloud_parser.add_argument('--links-visit-count-threshold', type=int, default=5, help='Threshold for links visit count')

    cloud_parser.add_argument('--links-last-visited', action='store_true', default=False, help='Links are last visited timestamps within a threshold')
    cloud_parser.add_argument('--links-last-visited-threshold', type=int, default=30, help='Threshold for links last visited timestamp (in days)')

    cloud_parser.add_argument('--nodes-bookmarks', action='store_true', default=True, help='Nodes are bookmarks')
    cloud_parser.add_argument('--nodes-tags', action='store_true', default=False, help='Nodes are tags')
 
    # Reachable command
    reachable_parser = subparsers.add_parser('reachable', help='Check and mark bookmarks as reachable or not')
    reachable_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to analyze')
    reachable_parser.add_argument('--timeout', type=int, default=10, help='Timeout for HTTP requests in seconds')
    reachable_parser.add_argument('--concurrency', type=int, default=10, help='Number of concurrent HTTP requests')
    
    # Purge command
    purge_parser = subparsers.add_parser('purge', help='Remove bookmarks marked as not reachable')
    purge_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to purge')
    purge_parser.add_argument('--confirm', action='store_true', help='Ask for confirmation before purging')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export bookmarks to a different format')
    export_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to export')
    export_parser.add_argument('format', type=str, help='Export format (e.g., html, csv, zip)')
    export_parser.add_argument('output', type=str, help='Path to save the exported directory or file')

    # JMESPath command
    jmespath_parser = subparsers.add_parser('jmespath', help='Query bookmarks using JMESPath')
    jmespath_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to query')
    jmespath_parser.add_argument('query', type=str, help='JMESPath query string')
    jmespath_parser.add_argument('--json', action='store_true', help='Output in JSON format')
    jmespath_parser.add_argument('--output', type=str, help='Directory to save the output bookmarks')

    # LLM command
    llm_parser = subparsers.add_parser('llm', help='Query the bookmark library using a Large Language Model')
    llm_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to query')
    llm_parser.add_argument('query', type=str, help='Query string')
    llm_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Let's have a .btkrc file to store information about the toolkit. in particular, the LLM endpoint, OpenAI
    # compatible.
    
    args = parser.parse_args()

    if args.command == 'llm':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)

        # let's get some context about the bookmarks, and things like jmespath queries, etc 

        prompt = f"Query the bookmark library with the following prompt:\n\n{args.query}"

        results = llm.query_llm(prompt)
        if args.json:
            console.print(JSON(json.dumps(results, indent=2)))
        else:
            console.print(results["response"])

    elif args.command == 'export':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        export_format = args.format
        output = args.output
        if export_format == 'html':
            utils.export_to_html(bookmarks, output)
        elif export_format == 'csv':
            utils.export_to_csv(bookmarks, output)
        elif export_format == 'zip':
            utils.export_to_zip(bookmarks, output)
        else:
            logging.error(f"Unknown export format '{export_format}'.")

    elif args.command == 'import':
        lib_dir = args.lib_dir
        utils.ensure_dir(lib_dir)
        utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
        bookmarks = utils.load_bookmarks(lib_dir)
        bookmarks = tools.import_bookmarks(bookmarks, args.html_file, lib_dir)
        utils.save_bookmarks(bookmarks, None, lib_dir)


    elif args.command == 'jmespath':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)

        bookmarks = utils.load_bookmarks(lib_dir)
        results, type = utils.jmespath_query(bookmarks, args.query)

        if type == "filter":
            if args.output:
                utils.save_bookmarks(results, lib_dir, args.output)
            elif args.json:
                console.print(JSON(json.dumps(results, indent=2)))
            else:
                tools.list_bookmarks(results)

        else: # type == "transform":
            if args.output:
                # save the transformed results as JSON
                with open(args.output, 'w') as f:
                    json.dump(results, f, indent=2)
            elif args.json:
                # dump the results as JSON
                console.print(JSON(json.dumps(results, indent=2)))
            elif isinstance(results, list):
                # let's transform the json into a table
                table = Table(title="Transformed Results", show_header=True, header_style="bold magenta")
                for key in results[0].keys():
                    table.add_column(key, style="bold")
                for item in results:
                    table.add_row(*[str(value) for value in item.values()])
                console.print(table)
            elif isinstance(results, dict):
                table = Table(title="Transformed Results", show_header=True, header_style="bold magenta")
                for key in results.keys():
                    table.add_column(key, style="bold")
                table.add_row(*[str(value) for value in results.values()])
                console.print(table)
            else:
                console.print(results)

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

    elif args.command == 'remove':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)
        bookmarks = tools.remove_bookmark(bookmarks, args.id)
        utils.save_bookmarks(bookmarks, lib_dir, lib_dir)

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
            tools.list_bookmarks(bookmarks)

    elif args.command == 'edit':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)

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

        utils.save_bookmarks(bookmarks, None, lib_dir)
      
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
            tools.list_bookmarks([b for b in bookmarks if b['id'] in args.indices])

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
            
            bookmarks = utils.load_bookmarks(lib_dir)
            if not bookmarks:
                logging.error(f"No bookmarks found in '{lib_dir}'.")
                sys.exit(1)
            
            graph = cloud.generate_url_graph(
                bookmarks,
                max_bookmarks=max_bookmarks,
                only_in_library=only_in_library,
                ignore_ssl=ignore_ssl)
            
            if stats:
                cloud.display_graph_stats(graph)
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

```

#### Source File: `btk/cloud.py`

```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import logging
import networkx as nx
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import matplotlib.pyplot as plt
from urllib.parse import urlparse
from pyvis.network import Network
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.table import Table
from rich.console import Console
from colorama import init as colorama_init, Fore, Style

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()

def extract_urls(html_content, base_url, bookmark_urls=None, max_mentions=50):
    """Extract a limited number of absolute URLs from the HTML content.
    
    If bookmark_urls is provided, only include URLs present in this set.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Use 'lxml' parser for robustness
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ('http', 'https'):
            if bookmark_urls is None or full_url in bookmark_urls:
                if full_url != base_url:  # Prevent self-loop by excluding the bookmark's own URL
                    urls.add(full_url)
                    if len(urls) >= max_mentions:
                        break
    return urls


def extract_urls2(html_content, base_url, bookmark_urls=None):
    """Extract all absolute URLs from the HTML content.
    
    If bookmark_urls is provided, only include URLs present in this set.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Try 'lxml' parser first
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ('http', 'https'):
            if bookmark_urls is None or full_url in bookmark_urls:
                urls.add(full_url)
    return urls

def get_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """Configure a requests Session with retry strategy."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_html(url, verify_ssl=True, session=None):
    """Fetch HTML content from a URL with optional SSL verification."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; BookmarkTool/1.0)'
        }
        if session:
            response = session.get(url, headers=headers, timeout=10, verify=verify_ssl)
        else:
            response = requests.get(url, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        return response.text
    except requests.exceptions.SSLError as ssl_err:
        logging.error(f"SSL error fetching {url}: {ssl_err}")
        return None
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error fetching {url}: {http_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        logging.error(f"Error fetching {url}: {req_err}")
        return None
    
def is_valid_url(url):
    """Check if the URL has a valid scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def generate_url_graph(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()  # Assuming get_session is defined elsewhere
    
    success_count = 0
    failure_count = 0
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                if not is_valid_url(bookmark['url']):
                    logging.error(f"Invalid URL '{bookmark['url']}' for bookmark ID {bookmark['id']}. Skipping.")
                    failure_count += 1
                    progress.advance(task)
                    continue
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
                            if only_in_library:
                                if mentioned_url in bookmark_urls:
                                    G.add_edge(bookmark['url'], mentioned_url)
                            else:
                                G.add_edge(bookmark['url'], mentioned_url)
                    success_count += 1
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                    failure_count += 1
                progress.advance(task)
    
    # Additional Safety: Remove any accidental self-loops
    self_loops = list(nx.selfloop_edges(G))
    if self_loops:
        logging.warning(f"Detected {len(self_loops)} self-loop(s). Removing them.")
        G.remove_edges_from(self_loops)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    logging.info(f"Successfully processed {success_count} bookmarks.")
    logging.info(f"Failed to process {failure_count} bookmarks.")
    return G

def generate_url_graph0(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()  # Assuming get_session is defined elsewhere
    
    success_count = 0
    failure_count = 0
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                if not is_valid_url(bookmark['url']):
                    logging.error(f"Invalid URL '{bookmark['url']}' for bookmark ID {bookmark['id']}. Skipping.")
                    failure_count += 1
                    progress.advance(task)
                    continue
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
                            if only_in_library:
                                if mentioned_url in bookmark_urls:
                                    G.add_edge(bookmark['url'], mentioned_url)
                            else:
                                G.add_edge(bookmark['url'], mentioned_url)
                    success_count += 1
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                    failure_count += 1
                progress.advance(task)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    logging.info(f"Successfully processed {success_count} bookmarks.")
    logging.info(f"Failed to process {failure_count} bookmarks.")
    return G

def generate_url_graph2(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        if only_in_library:
                            # Since extract_urls already filters, just add the edge
                            G.add_edge(bookmark['url'], mentioned_url)
                        else:
                            if mentioned_url != bookmark['url']:
                                G.add_edge(bookmark['url'], mentioned_url)
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                progress.advance(task)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    return G

def visualize_graph_pyvis(graph, output_file):
    """Visualize the graph using pyvis and save as an HTML file."""
    net = Network(height='750px', width='100%', directed=True)
    net.from_nx(graph)
    net.show_buttons(filter_=['physics'])

    try:
        # Use write_html to save the HTML file without attempting to open it
        net.write_html(output_file)
        logging.info(f"Interactive graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save interactive graph visualization: {e}")

def visualize_graph_png(graph, output_file):
    # Fallback to matplotlib if not HTML
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(graph, k=0.05, iterations=30)
    nx.draw_networkx_nodes(graph, pos, node_size=10, node_color='blue', alpha=0.5)
    nx.draw_networkx_edges(graph, pos, arrows=False, alpha=0.75)
    plt.title("Bookmark URL Mention Graph")
    plt.axis('off')
    plt.tight_layout()
    try:
        plt.savefig(output_file, format='PNG')
        logging.info(f"Graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save graph visualization: {e}")
    plt.close()

def display_graph_stats(graph, top_n=5):
    """Compute and display detailed statistics of the NetworkX graph."""
    stats = {}
    stats['Number of Nodes'] = graph.number_of_nodes()
    stats['Number of Edges'] = graph.number_of_edges()
    stats['Density'] = nx.density(graph)
    stats['Average Degree'] = sum(dict(graph.degree()).values()) / graph.number_of_nodes() if graph.number_of_nodes() > 0 else 0
    stats['Connected Components'] = nx.number_connected_components(graph.to_undirected())
    stats['Graph Diameter'] = nx.diameter(graph.to_undirected()) if nx.is_connected(graph.to_undirected()) else 'N/A'
    stats['Clustering Coefficient'] = nx.average_clustering(graph.to_undirected())
    
    # Calculate centrality measures
    try:
        degree_centrality = nx.degree_centrality(graph)
        betweenness_centrality = nx.betweenness_centrality(graph)
        stats['Degree Centrality (avg)'] = sum(degree_centrality.values()) / len(degree_centrality) if degree_centrality else 0
        stats['Betweenness Centrality (avg)'] = sum(betweenness_centrality.values()) / len(betweenness_centrality) if betweenness_centrality else 0
    except Exception as e:
        logging.warning(f"Could not compute centrality measures: {e}")
        stats['Degree Centrality (avg)'] = 'N/A'
        stats['Betweenness Centrality (avg)'] = 'N/A'
    
    # Identify top N nodes by Degree Centrality
    try:
        top_degree = sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Top Degree Centrality'] = ', '.join([f"{url} ({centrality:.4f})" for url, centrality in top_degree])
    except:
        stats['Top Degree Centrality'] = 'N/A'
    
    # Identify top N nodes by Betweenness Centrality
    try:
        top_betweenness = sorted(betweenness_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Top Betweenness Centrality'] = ', '.join([f"{url} ({centrality:.4f})" for url, centrality in top_betweenness])
    except:
        stats['Top Betweenness Centrality'] = 'N/A'
    
    # Display the statistics using Rich
    table = Table(title="Graph Statistics", show_header=True, header_style="bold magenta")
    table.add_column("Statistic", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    
    for key, value in stats.items():
        table.add_row(key, str(value))
    
    console.print(table)

```

#### Source File: `btk/llm.py`

```python
import os
import requests
import configparser

def load_btkrc_config():
    """
    Loads configuration from ~/.btkrc.

    Expects a section [llm] with at least 'endpoint' and 'api_key'.
    """
    config_path = os.path.expanduser("~/.btkrc")
    parser = configparser.ConfigParser()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not find config file at {config_path}")

    parser.read(config_path)

    if "llm" not in parser:
        raise ValueError(
            "Config file ~/.btkrc is missing the [llm] section. "
            "Please add it with 'endpoint' and 'api_key' keys."
        )

    endpoint = parser["llm"].get("endpoint", "")
    api_key = parser["llm"].get("api_key", "")
    model = parser["llm"].get("model", "gpt-3.5-turbo")

    if not endpoint or not api_key or not model:
        raise ValueError(
            "Please make sure your [llm] section in ~/.btkrc "
            "includes 'endpoint', 'api_key', and 'model' keys."
        )
    
    #print(f"{endpoint=}, {api_key=}, {model=}, {stream=}")

    return endpoint, api_key, model


def query_llm(prompt):
    """
    Queries an OpenAI-compatible LLM endpoint with the given prompt.

    :param prompt: The user query or conversation prompt text.
    :param model: The OpenAI model name to use, defaults to gpt-3.5-turbo.
    :param temperature: Sampling temperature, defaults to 0.7.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_btkrc_config()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemError(f"Error calling LLM endpoint: {e}")

    return response.json()


```

#### Source File: `btk/merge.py`

```python
import logging
import btk.utils as utils

logging.basicConfig(level=logging.INFO)

def union_libraries(libs, output_dir):
    """Perform set union of multiple bookmark libraries and save to output_dir."""
    all_bookmarks = {}
    for lib in libs:
        bookmarks = utils.load_bookmarks(lib)
        for b in bookmarks:
            all_bookmarks[b['unique_id']] = b
    union_bookmarks = list(all_bookmarks.values())
    utils.save_bookmarks(union_bookmarks, output_dir)
    logging.info(f"Union of {len(libs)} libraries saved to {output_dir} with {len(union_bookmarks)} bookmarks.")

def intersection_libraries(libs, output_dir):
    """Perform set intersection of multiple bookmark libraries and save to output_dir."""
    if not libs:
        logging.error("No libraries provided for intersection.")
        return
    common_unique_ids = None
    bookmark_map = {}
    for lib in libs:
        bookmarks = utils.load_bookmarks(lib)
        unique_ids = set(b['unique_id'] for b in bookmarks)
        if common_unique_ids is None:
            common_unique_ids = unique_ids
        else:
            common_unique_ids &= unique_ids
        # Map unique_id to bookmark (assuming same unique_id implies same bookmark)
        for b in bookmarks:
            bookmark_map[b['unique_id']] = b
    intersection_bookmarks = [bookmark_map[uid] for uid in common_unique_ids]
    utils.save_bookmarks(intersection_bookmarks, output_dir)
    logging.info(f"Intersection of {len(libs)} libraries saved to {output_dir} with {len(intersection_bookmarks)} bookmarks.")

def difference_libraries(libs, output_dir):
    """Perform set difference (first library minus others) and save to output_dir."""
    if len(libs) < 2:
        logging.error("Set difference requires at least two libraries.")
        return
    first_lib = libs[0]
    other_libs = libs[1:]
    first_bookmarks = utils.load_bookmarks(first_lib)
    other_unique_ids = set()
    for lib in other_libs:
        bookmarks = utils.load_bookmarks(lib)
        other_unique_ids.update(b['unique_id'] for b in bookmarks)
    difference_bookmarks = [b for b in first_bookmarks if b['unique_id'] not in other_unique_ids]
    utils.save_bookmarks(difference_bookmarks, output_dir)
    logging.info(f"Difference (from {first_lib} minus others) saved to {output_dir} with {len(difference_bookmarks)} bookmarks.")

```

#### Source File: `btk/tools.py`

```python
import os
import logging
import webbrowser
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from bs4 import BeautifulSoup
import requests
import btk.utils as utils

console = Console()

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
                    'last_visited': None,
                    'reachable': None
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
        'last_visited': None,
        'reachable': None
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
    table.add_column("Description", style="italic")
    table.add_column("Favicon", style="dim")
    table.add_column("Reachable", style="dim")

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
            last_visited.split("T")[0], 
            b.get('description', ""),
            b.get('favicon', ""),
            "✅" if b.get('reachable') else "❌"
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

```

#### Source File: `btk/utils.py`

```python
import os
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from tqdm import tqdm
import logging
import hashlib
import shutil
from datetime import datetime, timezone
import jmespath


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Constants
DEFAULT_LIB_DIR = 'bookmarks'
FAVICON_DIR_NAME = 'favicons'
BOOKMARKS_JSON = 'bookmarks.json'

# Ensure default directory structure exists
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def is_bookmark_json(obj):
    """Check if an object is a valid bookmark dictionary."""

    if not isinstance(obj, list):
        return False 
    
    def check_item(item):
        return isinstance(item, dict) and 'id' in item and 'url' in item and \
            'title' in item and 'unique_id' in item and 'visit_count' in item

    return all(check_item(item) for item in obj)

def jmespath_query(bookmarks, query):
    """Apply a JMESPath query to a list of bookmarks."""
    
    if not query:
        return bookmarks

    try:
        bookmarks_json = json.loads(json.dumps(bookmarks))
        result = jmespath.search(query, bookmarks_json)
        if is_bookmark_json(result):
            return result, "filter"
        else:
            return result, "transform"

    except jmespath.exceptions.JMESPathError as e:
        logging.error(f"JMESPath query error: {e}")
        return [], "error"
    
    except Exception as e:
        logging.error(f"Error applying JMESPath query: {e}")
        return [], "error"  


def load_bookmarks(lib_dir):
    """Load bookmarks from a JSON file within the specified library directory."""
    json_file = os.path.join(lib_dir, BOOKMARKS_JSON)
    if not os.path.exists(json_file):
        logging.debug(f"No existing {json_file} found. Starting with an empty bookmark list.")
        return []
    with open(json_file, 'r', encoding='utf-8') as file:
        try:
            bookmarks = json.load(file)
            logging.debug(f"Loaded {len(bookmarks)} bookmarks from {json_file}.")
            return bookmarks
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {json_file}. Starting with an empty list.")
            return []

def save_bookmarks(bookmarks, src_dir, targ_dir):
    """Save bookmarks to a JSON file within the specified library directory."""
    if not bookmarks:
        logging.warning("No bookmarks to save.")
        return
    
    if not targ_dir:
        logging.error("No target directory provided. Cannot save bookmarks.")
        return
    
    if src_dir is not None and src_dir == targ_dir:
        logging.error("Source and target directories are the same. Cannot save bookmarks.")
        return
    
    if not os.path.exists(src_dir):
        logging.error(f"Source directory '{src_dir}' does not exist. Cannot save bookmarks.")
        return
    
    json_file = os.path.join(targ_dir, BOOKMARKS_JSON)

    # make lib_dir if it doesn't exist
    ensure_dir(targ_dir)

    # iterate over favicons and save them to the favicons directory
    if src_dir is not None:
        for b in bookmarks:
            if 'favicon' in b:
                favicon_path = b['favicon']
                b['favicon'] = copy_local_favicon(favicon_path, src_dir, targ_dir)

    # we save the bookmarks to the json file in the lib_dir
    with open(json_file, 'w', encoding='utf-8') as file:
        json.dump(bookmarks, file, ensure_ascii=False, indent=2)

    logging.debug(f"Saved {len(bookmarks)} bookmarks to {json_file}.")

def get_next_id(bookmarks):
    """Get the next unique integer ID for a new bookmark."""
    if not bookmarks:
        return 1
    return max(b['id'] for b in bookmarks) + 1

def generate_unique_id(url, title):
    """Generate a SHA-256 hash as a unique identifier based on URL and title."""
    unique_string = f"{url}{title}"
    hash = hashlib.sha256(unique_string.encode('utf-8')).hexdigest()
    # let's truncate to 8 characters for brevity
    return hash[:8]

def is_remote_url(url):
    """Determine if a URL is remote (http/https) or local."""
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https')

def generate_unique_filename(url, default_ext='.ico'):
    """Generate a unique filename based on the URL's MD5 hash."""
    hash_object = hashlib.md5(url.encode())
    filename = hash_object.hexdigest()
    parsed = urlparse(url)
    file_ext = os.path.splitext(parsed.path)[1]
    if not file_ext:
        file_ext = default_ext
    return f"{filename}{file_ext}"

def download_favicon(favicon_url, lib_dir):
    """
    Download favicon from the given URL and save it to the specified library's favicons directory.
    Returns the relative path to the saved favicon or None if download fails.
    """
    if not is_remote_url(favicon_url):
        logging.warning(f"Invalid remote favicon URL: {favicon_url}. Skipping download.")
        return None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; BookmarkTool/1.0)'
        }
        response = requests.get(favicon_url, headers=headers, timeout=5)
        response.raise_for_status()
        filename = generate_unique_filename(favicon_url)
        favicon_dir = os.path.join(lib_dir, FAVICON_DIR_NAME)
        ensure_dir(favicon_dir)
        filepath = os.path.join(favicon_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        relative_path = os.path.relpath(filepath, lib_dir)
        logging.debug(f"Downloaded favicon: {favicon_url} -> {filepath}")
        return relative_path
    except requests.RequestException as e:
        logging.error(f"Failed to download favicon from {favicon_url}: {e}")
        return None

def copy_local_favicon(favicon_path, source_dir, lib_dir):
    """
    Copy a local favicon file to the specified library's favicons directory.
    Returns the relative path to the copied favicon or None if copy fails.
    """
    source_favicon_abs = os.path.abspath(os.path.join(source_dir, favicon_path))
    if not os.path.exists(source_favicon_abs):
        logging.error(f"Local favicon file does not exist: {source_favicon_abs}. Skipping copy.")
        return None
    try:
        filename = generate_unique_filename(favicon_path, default_ext=os.path.splitext(favicon_path)[1] or '.ico')
        favicon_dir = os.path.join(lib_dir, FAVICON_DIR_NAME)
        ensure_dir(favicon_dir)
        destination_path = os.path.join(favicon_dir, filename)
        shutil.copy2(source_favicon_abs, destination_path)
        relative_path = os.path.relpath(destination_path, lib_dir)
        logging.debug(f"Copied local favicon: {source_favicon_abs} -> {destination_path}")
        return relative_path
    except Exception as e:
        logging.error(f"Failed to copy local favicon from {source_favicon_abs}: {e}")
        return None

def parse_date(date_str):
    """
    Parse date string into ISO format.
    Supports multiple date formats.
    """
    date_formats = [
        '%B %d, %Y - %I:%M:%S %p',  # e.g., 'February 24, 2023 - 1:59:56 PM'
        '%B %d, %Y %I:%M:%S %p',   # e.g., 'February 24, 2023 1:59:56 PM'
        # Add additional formats here if needed
    ]
    for fmt in date_formats:
        try:
            date = datetime.strptime(date_str, fmt)
            return date.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    logging.warning(f"Unrecognized date format: '{date_str}'. Using current UTC time.")
    return datetime.now(timezone.utc).isoformat()

def is_valid_url(url):
    """Check if the URL has a valid scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def check_url_reachable(url, timeout=10):
    """Check if a URL is reachable."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.RequestException:
        return False

def check_reachable(bookmarks_dir, timeout=10, concurrency=10):
    """Check the reachability of all bookmarks and update their status."""
    bookmarks = load_bookmarks(bookmarks_dir)
    updated = False

    # Prepare a list of bookmarks to check (reachable is None or not)
    to_check = [b for b in bookmarks if b.get('reachable') is None]
    total = len(to_check)
    if total == 0:
        logging.info("All bookmarks have already been checked for reachability.")
        return

    logging.info(f"Checking reachability for {total} bookmarks...")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_bookmark = {executor.submit(check_url_reachable, b['url'], timeout): b for b in to_check}
        
        # Using tqdm for progress bar
        for future in tqdm(as_completed(future_to_bookmark), total=total, desc="Reachability Check"):
            bookmark = future_to_bookmark[future]
            try:
                reachable = future.result()
            except Exception as e:
                logging.error(f"Error checking URL {bookmark['url']}: {e}")
                reachable = False
            bookmark['reachable'] = reachable
            updated = True
            if not reachable:
                logging.warning(f"Bookmark not reachable: {bookmark['url']}")
    
    if updated:
        save_bookmarks(bookmarks, bookmarks_dir, bookmarks_dir)
        logging.info("Reachability status updated successfully.")
    else:
        logging.info("No updates were made to bookmarks.")

def purge_unreachable(bookmarks_dir, confirm=False):
    """Purge all bookmarks marked as not reachable."""
    bookmarks = load_bookmarks(bookmarks_dir)
    unreachable = [b for b in bookmarks if b.get('reachable') == False]
    total_unreachable = len(unreachable)

    if total_unreachable == 0:
        logging.info("No unreachable bookmarks to purge.")
        return

    logging.info(f"Found {total_unreachable} unreachable bookmarks.")
    
    if confirm:
        response = input(f"Are you sure you want to delete {total_unreachable} unreachable bookmarks? [y/N]: ")
        if response.lower() != 'y':
            logging.info("Purge operation canceled by the user.")
            return

    # Remove unreachable bookmarks
    bookmarks = [b for b in bookmarks if b.get('reachable') != False]
    
    save_bookmarks(bookmarks, bookmarks_dir, bookmarks_dir)
    logging.info(f"Purged {total_unreachable} unreachable bookmarks successfully.")

```

