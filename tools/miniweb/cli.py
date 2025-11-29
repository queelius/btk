#!/usr/bin/env python3
"""
MiniWeb CLI - Generate interactive static bookmark sites.

Usage:
    python -m integrations.miniweb.cli <bookmark_library> <output_dir> [options]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import btk.utils as utils
from integrations.miniweb.graph import BookmarkGraph
from integrations.miniweb.generator import MiniWebGenerator, NavigationType


def main():
    parser = argparse.ArgumentParser(
        description='Generate interactive static site from BTK bookmarks'
    )

    parser.add_argument(
        'library',
        help='Path to bookmark library directory'
    )

    parser.add_argument(
        'output',
        help='Output directory for generated site'
    )

    parser.add_argument(
        '--title',
        default='My Bookmarks',
        help='Site title (default: My Bookmarks)'
    )

    parser.add_argument(
        '--nav-type',
        choices=['graph', 'semantic', 'tags', 'hybrid'],
        default='hybrid',
        help='Navigation type (default: hybrid)'
    )

    parser.add_argument(
        '--max-neighbors',
        type=int,
        default=10,
        help='Maximum neighbors per page (default: 10)'
    )

    parser.add_argument(
        '--no-links',
        action='store_true',
        help='Disable link-based edges'
    )

    parser.add_argument(
        '--no-semantic',
        action='store_true',
        help='Disable semantic similarity edges'
    )

    parser.add_argument(
        '--no-tags',
        action='store_true',
        help='Disable tag-based edges'
    )

    parser.add_argument(
        '--semantic-threshold',
        type=float,
        default=0.5,
        help='Semantic similarity threshold (default: 0.5)'
    )

    parser.add_argument(
        '--max-bookmarks',
        type=int,
        help='Limit number of bookmarks to process'
    )

    parser.add_argument(
        '--timeout',
        type=int,
        default=10,
        help='Request timeout in seconds (default: 10)'
    )

    parser.add_argument(
        '--max-workers',
        type=int,
        default=5,
        help='Concurrent workers for fetching (default: 5)'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Verbose logging'
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(levelname)s: %(message)s'
    )

    logger = logging.getLogger(__name__)

    # Load bookmarks
    logger.info(f"Loading bookmarks from {args.library}")
    try:
        bookmarks = utils.load_bookmarks(args.library)
    except Exception as e:
        logger.error(f"Failed to load bookmarks: {e}")
        return 1

    if not bookmarks:
        logger.error("No bookmarks found!")
        return 1

    logger.info(f"Loaded {len(bookmarks)} bookmarks")

    # Limit bookmarks if requested
    if args.max_bookmarks:
        bookmarks = bookmarks[:args.max_bookmarks]
        logger.info(f"Limited to {len(bookmarks)} bookmarks")

    # Build graph
    logger.info("Building bookmark graph...")
    graph_builder = BookmarkGraph(
        timeout=args.timeout,
        max_workers=args.max_workers
    )

    graph = graph_builder.build_graph(
        bookmarks,
        include_links=not args.no_links,
        include_semantic=not args.no_semantic,
        include_tags=not args.no_tags,
        semantic_threshold=args.semantic_threshold
    )

    # Print graph statistics
    stats = graph_builder.get_graph_statistics()
    logger.info(f"Graph statistics:")
    logger.info(f"  Nodes: {stats['nodes']}")
    logger.info(f"  Edges: {stats['edges']}")
    logger.info(f"  Avg Degree: {stats['avg_degree']:.2f}")
    logger.info(f"  Density: {stats['density']:.3f}")
    if 'edge_types' in stats:
        logger.info(f"  Edge Types: {stats['edge_types']}")

    # Generate site
    logger.info(f"Generating site at {args.output}")
    generator = MiniWebGenerator(args.output)

    # Map navigation type
    nav_type_map = {
        'graph': NavigationType.GRAPH_DISTANCE,
        'semantic': NavigationType.SEMANTIC,
        'tags': NavigationType.TAGS,
        'hybrid': NavigationType.HYBRID
    }
    nav_type = nav_type_map[args.nav_type]

    try:
        index_path = generator.generate(
            bookmarks=bookmarks,
            graph=graph_builder.graph,
            title=args.title,
            nav_type=nav_type,
            max_neighbors=args.max_neighbors
        )

        logger.info(f"✓ Site generated successfully!")
        logger.info(f"  Index: {index_path}")
        logger.info(f"  Open in browser: file://{index_path.absolute()}")

        return 0

    except Exception as e:
        logger.error(f"Failed to generate site: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
