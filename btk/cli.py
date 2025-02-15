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
import btk.viz as viz
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
    list_parser.add_argument('--indices', type=int, nargs='*', default=None, help='Indices of the bookmarks to list')

    # Visit command
    visit_parser = subparsers.add_parser('visit', help='Visit a bookmark by its ID')
    visit_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to visit from')
    visit_parser.add_argument('id', type=int, help='ID of the bookmark to visit')
    group = visit_parser.add_mutually_exclusive_group()
    group.add_argument('--browser', action='store_true', help='Visit the bookmark in the default web browser (default)')
    group.add_argument('--console', default=True, action='store_true', help='Display the bookmark content in the console')

    # Visulization command
    viz_parser = subparsers.add_parser('viz', help='Generate a URL mention graph from bookmarks')
    viz_parser.add_argument('lib_dir', type=str, help='Directory of the bookmark library to analyze')
    viz_parser.add_argument('--output', type=str, help='Path to save the graph image (e.g., graph.png or graph.html)')
    viz_parser.add_argument('--max-bookmarks', type=int, default=5000, help='Maximum number of bookmarks to process')
    viz_parser.add_argument(
        '--no-only-in-library',
        action='store_false',
        dest='only_in_library',
        help='Include all mentioned URLs as nodes, regardless of their presence in the library')
    viz_parser.add_argument(
        '--ignore-ssl',
        action='store_true',
        help='Ignore SSL certificate verification (not recommended)')
    viz_parser.add_argument('--stats', action='store_true', help='Display graph statistics')
    viz_parser.add_argument('--links-url-mentions', action='store_true', default=True, help='Links are URL mentions')
    viz_parser.add_argument('--links-url-mentions-hops', type=int, default=1, help='Number of URL hops to consider as a link. These hops can go outside of the URLs mentioned in the library, but if `only_in_library` is set, the end of the hop must be in the library.')
    viz_parser.add_argument('--links-bookmarks-creation-timestamp', action='store_true', default=False, help='Links are creation timestamps within a threshold')
    viz_parser.add_argument('--links-bookmarks-creation-timestamp-threshold', type=int, default=30, help='Threshold for links creation timestamp (in days)')
 
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
    export_parser.add_argument('format', choices=['html', 'csv', 'zip'], help='Export format')
    export_parser.add_argument('--output', type=str, help='Path to save the exported directory or file')

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
    llm_parser.add_argument('--json', action='store_true', help='Output in JSON format if no-execute')
    llm_parser.add_argument('--no-execute', action='store_true', help='Do not execute the query')
    llm_parser.add_argument('--no-show-errors', action='store_true', help='Do not show errors')
    llm_parser.add_argument('--max-attempts', type=int, default=5, help='Maximum number of attempts to execute the query')
    args = parser.parse_args()

    if args.command == 'llm':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)

        for i in range(args.max_attempts):
            try:
                results = llm.query_llm(lib_dir, args.query)
                results = json.loads(results['response'])

                if args.no_execute:
                    if args.json:
                        console.print(JSON(json.dumps(results, indent=2)))
                    else:
                        console.print(results)
                    break
                else:
                    proc = ["btk"] + [results["command"]] + results["args"]
                    console.print(f"[bold green]Executing:[/bold green] {' '.join(proc)}")  
                    subprocess.run(proc, check=True)
                    break
            except subprocess.CalledProcessError as e:
                if not args.no_show_errors:
                    console.print(f"[red]Error:[/red] {e}")
                
            except Exception as e:
                if not args.no_show_errors:
                    console.print(f"[red]Error:[/red] {e}")

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
        
        if args.type_command == 'nbf':
            lib_dir = args.lib_dir
            utils.ensure_dir(lib_dir)
            utils.ensure_dir(os.path.join(lib_dir, utils.FAVICON_DIR_NAME))
            bookmarks = utils.load_bookmarks(lib_dir)
            bookmarks = tools.import_bookmarks(bookmarks, args.file, lib_dir)
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
                table = Table(title="Results", show_header=True, header_style="bold magenta")
                for key in results[0].keys():
                    table.add_column(key, style="bold")
                for item in results:
                    table.add_row(*[str(value) for value in item.values()])
                console.print(table)
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
        if args.indices is not None:
            bookmarks = [b for i, b in enumerate(bookmarks) if i in args.indices]

        if args.json:
            json_data = json.dumps(bookmarks)
            console.print(JSON(json_data))
        else:
            indices = args.indices if args.indices is not None else range(len(bookmarks))
            tools.list_bookmarks(bookmarks, indices)

    elif args.command == 'edit':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        bookmarks = utils.load_bookmarks(lib_dir)

        for b in bookmarks:
            if b['id'] == args.id:
                if args.title:
                    b['title'] = args.title
                if args.url:
                    b['url'] = args.url
                if args.stars:
                    b['stars'] = args.stars
                if args.tags:
                    b['tags'] = [tag.strip() for tag in args.tags]
                if args.description:
                    b['description'] = args.description
                break

        utils.save_bookmarks(bookmarks, None, lib_dir)
      
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

    elif args.command == 'viz':
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
            
            graph = viz.generate_url_graph(
                bookmarks,
                max_bookmarks=max_bookmarks,
                only_in_library=only_in_library,
                ignore_ssl=ignore_ssl)
            
            if stats:
                viz.display_graph_stats(graph)
            # Optional: Visualize the graph
            if output_file:
                if output_file.endswith('.html'):
                    # Interactive visualization with pyvis
                    viz.visualize_graph_pyvis(graph, output_file)
                elif output_file.endswith('.json'):
                    graph_json = nx.node_link_data(graph)  # Convert to node-link format
                    console.print(JSON(json.dumps(graph_json, indent=2)))
                else: # file.endswith('.png'):
                    # Static visualization with matplotlib
                    viz.visualize_graph_png(graph, output_file)
            else:
                # If no output file specified, print graph stats
                console.print(f"[bold green]Graph generated successfully![/bold green]")
                console.print(f"Nodes: {graph.number_of_nodes()}")
                console.print(f"Edges: {graph.number_of_edges()}")

    elif args.command == 'reachable':
        utils.check_reachable(bookmarks_dir=args.lib_dir, timeout=args.timeout, concurrency=args.concurrency)
    
    elif args.command == 'purge':
        utils.purge_unreachable(bookmarks_dir=args.lib_dir, confirm=args.confirm)

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
