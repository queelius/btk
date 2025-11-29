#!/usr/bin/env python3
"""
BTK Visualization Tool - Generate network graphs from bookmark collections
"""

import argparse
import logging
import sys
import os
from pathlib import Path

# Add BTK to path if needed
btk_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(btk_path))

import btk.utils as utils
from viz_btk import generate_url_graph, visualize_graph, display_graph_stats

def main():
    parser = argparse.ArgumentParser(
        description='Generate visualization graphs from BTK bookmark libraries'
    )
    parser.add_argument('lib_dir', help='Directory of the bookmark library')
    parser.add_argument(
        '--output', '-o',
        help='Output file (*.html for interactive, *.png for static, *.json for data)'
    )
    parser.add_argument(
        '--max-bookmarks', 
        type=int, 
        default=None,
        help='Maximum number of bookmarks to visualize'
    )
    parser.add_argument(
        '--only-in-library',
        action='store_true',
        help='Only show links between bookmarks in the library'
    )
    parser.add_argument(
        '--ignore-ssl',
        action='store_true',
        help='Ignore SSL certificate errors when fetching pages'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Display graph statistics instead of visualization'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    # Validate library directory
    if not os.path.isdir(args.lib_dir):
        logging.error(f"Library directory '{args.lib_dir}' does not exist")
        return 1
    
    # Load bookmarks
    bookmarks = utils.load_bookmarks(args.lib_dir)
    if not bookmarks:
        logging.error(f"No bookmarks found in '{args.lib_dir}'")
        return 1
    
    logging.info(f"Loaded {len(bookmarks)} bookmarks from '{args.lib_dir}'")
    
    # Generate the graph
    try:
        graph = generate_url_graph(
            bookmarks,
            max_bookmarks=args.max_bookmarks,
            only_in_library=args.only_in_library,
            ignore_ssl=args.ignore_ssl
        )
    except Exception as e:
        logging.error(f"Failed to generate graph: {e}")
        return 1
    
    # Display stats or visualize
    if args.stats:
        display_graph_stats(graph, bookmarks)
    elif args.output:
        try:
            visualize_graph(graph, bookmarks, output_file=args.output)
            logging.info(f"Visualization saved to '{args.output}'")
        except Exception as e:
            logging.error(f"Failed to save visualization: {e}")
            return 1
    else:
        # Just display stats if no output specified
        display_graph_stats(graph, bookmarks)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())