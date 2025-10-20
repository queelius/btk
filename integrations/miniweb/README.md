# MiniWeb - Network-Aware Bookmark Site Generator

Generate an interactive static website from your bookmarks with intelligent network-based navigation. Pages are embedded in a larger context showing related bookmarks, graph structure, and multiple navigation modes.

## Features

- **Network-Aware Navigation**: Navigate between bookmarks based on:
  - **Graph Distance**: Hops between linked pages
  - **Semantic Similarity**: Content-based relationships (embeddings)
  - **Tag Overlap**: Shared categorization
  - **Hybrid**: Combination of all methods

- **Interactive Graph Visualization**:
  - Zoom in/out between graph overview and page content
  - Visual representation of bookmark relationships
  - Color-coded edge types (links, semantic, tags)
  - Click nodes to navigate

- **Embedded Pages**: Each bookmark page includes:
  - Full page content in iframe
  - Related bookmarks sidebar
  - Metadata display (tags, description, dates)
  - Graph context and statistics

- **Static Site**: No server required, works offline
- **Responsive Design**: Works on desktop and mobile
- **Fast Performance**: Pre-computed relationships

## Installation

```bash
pip install requests beautifulsoup4 networkx
```

Optional dependencies for enhanced features:

```bash
# For semantic similarity navigation
pip install sentence-transformers numpy

# For visualization
pip install pyvis
```

## Usage

### Command Line

```bash
# Basic usage
python -m integrations.miniweb.cli /path/to/library output/

# With options
python -m integrations.miniweb.cli /path/to/library output/ \
    --title "My Bookmarks" \
    --nav-type hybrid \
    --max-neighbors 15 \
    --semantic-threshold 0.6

# Disable specific edge types
python -m integrations.miniweb.cli /path/to/library output/ \
    --no-semantic \
    --max-bookmarks 100
```

### Python API

```python
from integrations.miniweb import MiniWebGenerator, BookmarkGraph, NavigationType
import btk.utils as utils

# Load bookmarks
bookmarks = utils.load_bookmarks('/path/to/library')

# Build graph
graph_builder = BookmarkGraph(timeout=10, max_workers=5)
graph = graph_builder.build_graph(
    bookmarks,
    include_links=True,      # Extract URL mentions
    include_semantic=True,   # Compute semantic similarity
    include_tags=True,       # Use tag overlap
    semantic_threshold=0.5   # Min similarity score
)

# Generate site
generator = MiniWebGenerator('output/')
index = generator.generate(
    bookmarks=bookmarks,
    graph=graph_builder.graph,
    title="My Bookmark Network",
    nav_type=NavigationType.HYBRID,
    max_neighbors=10
)

print(f"Site generated at: {index}")
```

## Navigation Types

- **GRAPH_DISTANCE**: Navigate by link structure
- **SEMANTIC**: Navigate by content similarity (requires sentence-transformers)
- **TAGS**: Navigate by shared tags
- **HYBRID**: Combines all methods (default)

## Generated Site Structure

```
output/
├── index.html              # Main page with graph overview
├── graph-data.json         # Graph data for visualization
├── pages/
│   ├── abc123.html        # Individual bookmark pages
│   └── ...
└── static/
    ├── style.css          # Styles
    ├── graph.js           # Graph visualization
    └── page.js            # Page interactions
```

## Performance

- **Small (<100)**: ~1 minute
- **Medium (100-500)**: ~5 minutes
- **Large (>500)**: 15-20 minutes

Use `--no-semantic` for 5-10x faster generation.

## License

Part of the BTK (Bookmark Toolkit) project.
