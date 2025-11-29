#!/usr/bin/env python3
"""
MiniWeb Example - Generate a network-aware bookmark site.

This example demonstrates how to use MiniWeb to create an interactive
static website from your BTK bookmarks with intelligent navigation.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import btk.utils as utils
from integrations.miniweb.graph import BookmarkGraph
from integrations.miniweb.generator import MiniWebGenerator, NavigationType


def main():
    print("MiniWeb Example - Bookmark Network Generator")
    print("=" * 50)

    # Configuration
    library_path = 'path/to/bookmark/library'  # Change this
    output_path = 'miniweb-output'

    # Customize these settings
    site_title = "My Bookmark Network"
    nav_type = NavigationType.HYBRID
    max_neighbors = 10
    semantic_threshold = 0.5

    # Step 1: Load bookmarks
    print(f"\n1. Loading bookmarks from {library_path}...")
    try:
        bookmarks = utils.load_bookmarks(library_path)
        print(f"   ✓ Loaded {len(bookmarks)} bookmarks")
    except Exception as e:
        print(f"   ✗ Error loading bookmarks: {e}")
        print(f"   Please update library_path in this script to your bookmark library")
        return

    # For demo, limit to first 50 bookmarks
    if len(bookmarks) > 50:
        print(f"   Limiting to first 50 bookmarks for demo...")
        bookmarks = bookmarks[:50]

    # Step 2: Build graph
    print(f"\n2. Building bookmark network graph...")
    print(f"   - Extracting URL links...")
    print(f"   - Computing tag overlaps...")
    print(f"   - Calculating semantic similarities (if available)...")

    graph_builder = BookmarkGraph(timeout=10, max_workers=5)

    graph = graph_builder.build_graph(
        bookmarks,
        include_links=True,
        include_semantic=True,  # Requires sentence-transformers
        include_tags=True,
        semantic_threshold=semantic_threshold
    )

    # Print graph statistics
    stats = graph_builder.get_graph_statistics()
    print(f"   ✓ Graph built successfully:")
    print(f"     - Nodes: {stats['nodes']}")
    print(f"     - Edges: {stats['edges']}")
    print(f"     - Average degree: {stats['avg_degree']:.2f}")
    print(f"     - Density: {stats['density']:.3f}")

    if 'edge_types' in stats:
        print(f"     - Edge types: {stats['edge_types']}")

    # Step 3: Generate static site
    print(f"\n3. Generating static website at {output_path}...")

    generator = MiniWebGenerator(output_path)

    index_path = generator.generate(
        bookmarks=bookmarks,
        graph=graph_builder.graph,
        title=site_title,
        nav_type=nav_type,
        max_neighbors=max_neighbors
    )

    print(f"   ✓ Site generated successfully!")
    print(f"\n" + "=" * 50)
    print("DONE!")
    print(f"\nYour bookmark network site is ready:")
    print(f"  📁 Location: {output_path}/")
    print(f"  🌐 Index: {index_path}")
    print(f"  🔗 Open: file://{index_path.absolute()}")
    print(f"\nFeatures:")
    print(f"  • Interactive graph visualization")
    print(f"  • {len(bookmarks)} bookmarks with {stats['edges']} connections")
    print(f"  • Network-aware navigation ({nav_type.value} mode)")
    print(f"  • Related bookmarks sidebar on each page")
    print(f"\nNavigation:")
    print(f"  • Click nodes in graph to view pages")
    print(f"  • Use related bookmarks sidebar to discover connections")
    print(f"  • Press 'Esc' on any page to toggle sidebar")
    print(f"  • Press 'G' to return to graph view")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
