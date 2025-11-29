# BTK Visualization Tools

Visualization integration for Bookmark Toolkit (BTK) that creates network graphs and visual representations of bookmark data.

## Features

- Generate URL mention graphs showing relationships between bookmarks
- Export visualizations as HTML (interactive), PNG (static), or JSON (data)
- Customizable graph layouts and styling
- Support for filtering by bookmark library scope

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### As a Command Line Tool

```bash
# Generate an interactive HTML visualization
python viz.py /path/to/bookmarks --output graph.html

# Generate a static PNG image
python viz.py /path/to/bookmarks --output graph.png

# Export graph data as JSON
python viz.py /path/to/bookmarks --output graph.json

# Limit to bookmarks within the library only
python viz.py /path/to/bookmarks --output graph.html --only-in-library

# Limit the number of bookmarks visualized
python viz.py /path/to/bookmarks --output graph.html --max-bookmarks 100
```

### As a Python Module

```python
from viz_btk import generate_url_graph, visualize_graph

# Load bookmarks (using BTK's utils)
import btk.utils as utils
bookmarks = utils.load_bookmarks('/path/to/bookmarks')

# Generate the graph
graph = generate_url_graph(bookmarks, max_bookmarks=100)

# Visualize it
visualize_graph(graph, bookmarks, output_file='graph.html')
```

## Requirements

- Python 3.8+
- BTK installed (`pip install bookmark-tk`)
- See requirements.txt for visualization dependencies

## How It Works

1. **URL Extraction**: Fetches each bookmark's content and extracts mentioned URLs
2. **Graph Building**: Creates a directed graph where:
   - Nodes are bookmarks
   - Edges represent URL mentions (bookmark A links to bookmark B)
3. **Visualization**: Renders the graph using:
   - PyVis for interactive HTML
   - Matplotlib/NetworkX for static images
   - JSON export for custom processing

## Configuration

The visualization can be customized through parameters:
- `max_bookmarks`: Limit the number of bookmarks to process
- `only_in_library`: Only show links between bookmarks in your library
- `ignore_ssl`: Skip SSL verification for problematic sites
- `max_mentions`: Limit URLs extracted per page (default: 50)

## Performance Notes

- Large bookmark collections may take time to process
- Uses concurrent fetching for better performance
- Progress bars show current status
- Failed fetches are logged but don't stop the process