"""
Static site generator for MiniWeb.

Generates an interactive static website where bookmark pages are embedded
within a network-aware interface showing related bookmarks and graph structure.
"""

import logging
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from enum import Enum
from urllib.parse import urlparse, quote
from datetime import datetime

logger = logging.getLogger(__name__)


class NavigationType(Enum):
    """Navigation method between bookmarks."""
    GRAPH_DISTANCE = "graph"      # Navigate by graph hops
    SEMANTIC = "semantic"          # Navigate by content similarity
    TAGS = "tags"                  # Navigate by shared tags
    HYBRID = "hybrid"              # Combination of all methods


class MiniWebGenerator:
    """
    Generate static website with network-aware bookmark navigation.

    The generated site includes:
    - Embedded bookmark pages in iframes
    - Interactive graph visualization
    - Related bookmarks sidebar
    - Zoom in/out between graph and content
    - Multiple navigation modes
    """

    def __init__(self, output_dir: str):
        """
        Initialize MiniWeb generator.

        Args:
            output_dir: Directory to output generated site
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, bookmarks: List[Dict[str, Any]],
                graph,
                title: str = "My Bookmarks",
                nav_type: NavigationType = NavigationType.HYBRID,
                max_neighbors: int = 10):
        """
        Generate complete static site.

        Args:
            bookmarks: List of bookmarks
            graph: BookmarkGraph instance
            title: Site title
            nav_type: Navigation type
            max_neighbors: Maximum neighbors to show per page

        Returns:
            Path to generated index.html
        """
        logger.info(f"Generating MiniWeb site at {self.output_dir}")

        # Create directory structure
        (self.output_dir / 'pages').mkdir(exist_ok=True)
        (self.output_dir / 'static').mkdir(exist_ok=True)

        # Generate main index page
        self._generate_index(bookmarks, graph, title)

        # Generate individual bookmark pages
        for bookmark in bookmarks:
            self._generate_bookmark_page(
                bookmark, graph, bookmarks, nav_type, max_neighbors
            )

        # Generate graph visualization
        self._generate_graph_viz(bookmarks, graph)

        # Generate static assets
        self._generate_static_assets()

        # Generate graph data JSON
        self._generate_graph_data(bookmarks, graph)

        logger.info(f"Site generated successfully at {self.output_dir / 'index.html'}")

        return self.output_dir / 'index.html'

    def _generate_index(self, bookmarks: List[Dict[str, Any]],
                       graph, title: str):
        """Generate main index page with graph overview."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="static/style.css">
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <link href="https://unpkg.com/vis-network/styles/vis-network.css" rel="stylesheet" />
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <p>{len(bookmarks)} bookmarks · {graph.number_of_edges()} connections</p>
        </header>

        <div class="main-content">
            <div class="sidebar">
                <h2>Bookmarks</h2>
                <div class="bookmark-list">
                    {''.join(self._bookmark_list_item(b) for b in sorted(bookmarks, key=lambda x: x.get('title', '')))}
                </div>
            </div>

            <div class="graph-container">
                <div id="network-graph"></div>
                <div class="graph-controls">
                    <button onclick="zoomIn()">Zoom In</button>
                    <button onclick="zoomOut()">Zoom Out</button>
                    <button onclick="fitGraph()">Fit</button>
                    <button onclick="togglePhysics()">Toggle Physics</button>
                </div>
                <div class="graph-stats">
                    {self._format_stats(graph.get_graph_statistics())}
                </div>
            </div>
        </div>
    </div>

    <script src="static/graph.js"></script>
    <script>
        // Load graph data and initialize
        fetch('graph-data.json')
            .then(response => response.json())
            .then(data => {{
                initializeGraph(data);
            }});
    </script>
</body>
</html>"""

        with open(self.output_dir / 'index.html', 'w') as f:
            f.write(html)

    def _bookmark_list_item(self, bookmark: Dict[str, Any]) -> str:
        """Generate HTML for bookmark list item."""
        url = bookmark['url']
        title = bookmark.get('title', url)
        page_id = self._url_to_page_id(url)

        tags = ' '.join(f'<span class="tag">{t}</span>'
                       for t in bookmark.get('tags', [])[:3])

        return f"""
        <div class="bookmark-item">
            <a href="pages/{page_id}.html" class="bookmark-link">
                <div class="bookmark-title">{self._escape_html(title)}</div>
                <div class="bookmark-url">{self._escape_html(self._truncate(url, 50))}</div>
                <div class="bookmark-tags">{tags}</div>
            </a>
        </div>
        """

    def _generate_bookmark_page(self, bookmark: Dict[str, Any],
                                graph, all_bookmarks: List[Dict[str, Any]],
                                nav_type: NavigationType, max_neighbors: int):
        """Generate individual bookmark page with embedded content and navigation."""
        url = bookmark['url']
        title = bookmark.get('title', url)
        page_id = self._url_to_page_id(url)

        # Get neighbors based on navigation type
        neighbors = self._get_neighbors_for_nav_type(
            url, graph, nav_type, max_neighbors
        )

        # Build neighbor HTML
        neighbor_html = self._build_neighbor_sidebar(neighbors)

        # Get bookmark metadata
        metadata_html = self._build_metadata_section(bookmark)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self._escape_html(title)}</title>
    <link rel="stylesheet" href="../static/style.css">
</head>
<body class="page-view">
    <div class="page-container">
        <nav class="top-nav">
            <a href="../index.html" class="home-link">← Back to Index</a>
            <div class="page-title">{self._escape_html(title)}</div>
            <button onclick="toggleSidebar()" class="toggle-sidebar">☰</button>
        </nav>

        <div class="content-wrapper">
            <aside class="neighbors-sidebar" id="sidebar">
                <h3>Related Bookmarks</h3>
                {neighbor_html}
            </aside>

            <main class="page-content">
                <div class="metadata-section">
                    {metadata_html}
                </div>

                <div class="iframe-container">
                    <iframe src="{url}" frameborder="0" sandbox="allow-scripts allow-same-origin allow-popups"></iframe>
                </div>

                <div class="page-actions">
                    <a href="{url}" target="_blank" class="action-btn">Open Original ↗</a>
                    <button onclick="zoomGraph()" class="action-btn">View in Graph</button>
                </div>
            </main>
        </div>
    </div>

    <script src="../static/page.js"></script>
</body>
</html>"""

        page_path = self.output_dir / 'pages' / f'{page_id}.html'
        with open(page_path, 'w') as f:
            f.write(html)

    def _build_neighbor_sidebar(self, neighbors: List[Dict[str, Any]]) -> str:
        """Build HTML for neighbors sidebar."""
        if not neighbors:
            return '<p class="no-neighbors">No related bookmarks found.</p>'

        html_parts = []

        for neighbor in neighbors:
            url = neighbor['url']
            title = neighbor.get('title', url)
            page_id = self._url_to_page_id(url)
            distance = neighbor.get('distance', 0)
            edge_type = neighbor.get('edge_type', 'unknown')
            weight = neighbor.get('edge_weight', 0)

            # Icon based on edge type
            icon = {
                'link': '🔗',
                'semantic': '🧠',
                'tag': '🏷️'
            }.get(edge_type, '·')

            html_parts.append(f"""
            <div class="neighbor-item" data-distance="{distance}" data-type="{edge_type}">
                <a href="{page_id}.html">
                    <span class="neighbor-icon">{icon}</span>
                    <div class="neighbor-info">
                        <div class="neighbor-title">{self._escape_html(self._truncate(title, 40))}</div>
                        <div class="neighbor-meta">
                            {edge_type} · distance: {distance} · score: {weight:.2f}
                        </div>
                    </div>
                </a>
            </div>
            """)

        return '<div class="neighbors-list">' + ''.join(html_parts) + '</div>'

    def _build_metadata_section(self, bookmark: Dict[str, Any]) -> str:
        """Build metadata section for bookmark."""
        parts = []

        # URL
        parts.append(f'<div class="meta-item"><strong>URL:</strong> <a href="{bookmark["url"]}" target="_blank">{self._truncate(bookmark["url"], 60)}</a></div>')

        # Tags
        if bookmark.get('tags'):
            tags = ' '.join(f'<span class="tag">{t}</span>' for t in bookmark['tags'])
            parts.append(f'<div class="meta-item"><strong>Tags:</strong> {tags}</div>')

        # Description
        if bookmark.get('description'):
            parts.append(f'<div class="meta-item"><strong>Description:</strong> {self._escape_html(bookmark["description"])}</div>')

        # Added date
        if bookmark.get('added'):
            parts.append(f'<div class="meta-item"><strong>Added:</strong> {bookmark["added"]}</div>')

        # Stars
        if bookmark.get('stars'):
            stars = '⭐' * bookmark['stars']
            parts.append(f'<div class="meta-item"><strong>Rating:</strong> {stars}</div>')

        return '<div class="metadata">' + ''.join(parts) + '</div>'

    def _get_neighbors_for_nav_type(self, url: str, graph,
                                    nav_type: NavigationType,
                                    max_neighbors: int) -> List[Dict[str, Any]]:
        """Get neighbors based on navigation type."""
        if nav_type == NavigationType.GRAPH_DISTANCE:
            return graph.get_neighbors(url, max_distance=2, edge_types={'link'})[:max_neighbors]
        elif nav_type == NavigationType.SEMANTIC:
            return graph.get_neighbors(url, max_distance=1, edge_types={'semantic'})[:max_neighbors]
        elif nav_type == NavigationType.TAGS:
            return graph.get_neighbors(url, max_distance=1, edge_types={'tag'})[:max_neighbors]
        else:  # HYBRID
            # Get neighbors from all types
            neighbors = graph.get_neighbors(url, max_distance=2)
            # Sort by weight and distance
            neighbors.sort(key=lambda n: (-n.get('edge_weight', 0), n.get('distance', 0)))
            return neighbors[:max_neighbors]

    def _generate_graph_data(self, bookmarks: List[Dict[str, Any]], graph):
        """Generate JSON data for graph visualization."""
        nodes = []
        edges = []

        # Convert nodes
        for url in graph.nodes():
            node_data = dict(graph.nodes[url])
            nodes.append({
                'id': url,
                'label': self._truncate(node_data.get('title', url), 30),
                'title': node_data.get('title', url),
                'url': url,
                'page_id': self._url_to_page_id(url),
                'tags': node_data.get('tags', []),
                'group': self._get_domain(url)
            })

        # Convert edges
        for source, target, data in graph.edges(data=True):
            edges.append({
                'from': source,
                'to': target,
                'label': data.get('edge_type', ''),
                'weight': data.get('weight', 1.0),
                'color': self._edge_color(data.get('edge_type'))
            })

        graph_data = {
            'nodes': nodes,
            'edges': edges,
            'generated_at': datetime.now().isoformat()
        }

        with open(self.output_dir / 'graph-data.json', 'w') as f:
            json.dump(graph_data, f, indent=2)

    def _generate_static_assets(self):
        """Generate CSS and JS files."""
        # Generate CSS
        css = self._get_css()
        with open(self.output_dir / 'static' / 'style.css', 'w') as f:
            f.write(css)

        # Generate graph JS
        graph_js = self._get_graph_js()
        with open(self.output_dir / 'static' / 'graph.js', 'w') as f:
            f.write(graph_js)

        # Generate page JS
        page_js = self._get_page_js()
        with open(self.output_dir / 'static' / 'page.js', 'w') as f:
            f.write(page_js)

    def _generate_graph_viz(self, bookmarks: List[Dict[str, Any]], graph):
        """Generate interactive graph visualization data."""
        # This is handled by graph-data.json and graph.js
        pass

    def _url_to_page_id(self, url: str) -> str:
        """Convert URL to safe page ID."""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc

    def _edge_color(self, edge_type: str) -> str:
        """Get color for edge type."""
        colors = {
            'link': '#3498db',      # Blue
            'semantic': '#9b59b6',  # Purple
            'tag': '#2ecc71'        # Green
        }
        return colors.get(edge_type, '#95a5a6')

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))

    def _truncate(self, text: str, length: int) -> str:
        """Truncate text to length."""
        return text if len(text) <= length else text[:length-3] + '...'

    def _format_stats(self, stats: Dict[str, Any]) -> str:
        """Format graph statistics as HTML."""
        return f"""
        <div class="stats">
            <div class="stat-item">Nodes: {stats['nodes']}</div>
            <div class="stat-item">Edges: {stats['edges']}</div>
            <div class="stat-item">Avg Degree: {stats['avg_degree']:.2f}</div>
            <div class="stat-item">Density: {stats['density']:.3f}</div>
        </div>
        """

    def _get_css(self) -> str:
        """Get CSS styles."""
        return """
/* MiniWeb Styles */

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f5f5f5;
    color: #333;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
}

header {
    background: white;
    padding: 30px;
    border-radius: 8px;
    margin-bottom: 20px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

header h1 {
    font-size: 2em;
    margin-bottom: 10px;
}

header p {
    color: #666;
}

.main-content {
    display: grid;
    grid-template-columns: 300px 1fr;
    gap: 20px;
}

.sidebar {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    max-height: 80vh;
    overflow-y: auto;
}

.sidebar h2 {
    margin-bottom: 15px;
    font-size: 1.2em;
}

.bookmark-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.bookmark-item {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    transition: all 0.2s;
}

.bookmark-item:hover {
    border-color: #3498db;
    box-shadow: 0 2px 8px rgba(52,152,219,0.2);
}

.bookmark-link {
    display: block;
    padding: 10px;
    text-decoration: none;
    color: inherit;
}

.bookmark-title {
    font-weight: 600;
    margin-bottom: 4px;
}

.bookmark-url {
    font-size: 0.85em;
    color: #666;
    margin-bottom: 6px;
}

.bookmark-tags {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
}

.tag {
    background: #e8f4f8;
    color: #2980b9;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.75em;
}

.graph-container {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

#network-graph {
    width: 100%;
    height: 600px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
}

.graph-controls {
    margin-top: 10px;
    display: flex;
    gap: 10px;
}

.graph-controls button {
    padding: 8px 16px;
    border: 1px solid #ddd;
    background: white;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s;
}

.graph-controls button:hover {
    background: #f0f0f0;
    border-color: #3498db;
}

.graph-stats {
    margin-top: 15px;
    padding: 15px;
    background: #f8f9fa;
    border-radius: 4px;
}

.stats {
    display: flex;
    gap: 20px;
}

.stat-item {
    font-size: 0.9em;
    color: #666;
}

/* Page View Styles */

.page-view {
    margin: 0;
    padding: 0;
}

.page-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
}

.top-nav {
    background: white;
    padding: 15px 20px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex;
    align-items: center;
    gap: 20px;
}

.home-link {
    text-decoration: none;
    color: #3498db;
    font-weight: 600;
}

.page-title {
    flex: 1;
    font-weight: 600;
    font-size: 1.1em;
}

.toggle-sidebar {
    padding: 8px 16px;
    border: 1px solid #ddd;
    background: white;
    border-radius: 4px;
    cursor: pointer;
}

.content-wrapper {
    display: flex;
    flex: 1;
    overflow: hidden;
}

.neighbors-sidebar {
    width: 300px;
    background: white;
    border-right: 1px solid #e0e0e0;
    overflow-y: auto;
    padding: 20px;
}

.neighbors-sidebar.hidden {
    display: none;
}

.neighbors-sidebar h3 {
    margin-bottom: 15px;
}

.neighbors-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.neighbor-item {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    transition: all 0.2s;
}

.neighbor-item:hover {
    border-color: #3498db;
    box-shadow: 0 2px 8px rgba(52,152,219,0.2);
}

.neighbor-item a {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px;
    text-decoration: none;
    color: inherit;
}

.neighbor-icon {
    font-size: 1.5em;
}

.neighbor-info {
    flex: 1;
}

.neighbor-title {
    font-weight: 600;
    margin-bottom: 4px;
}

.neighbor-meta {
    font-size: 0.75em;
    color: #666;
}

.page-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.metadata-section {
    background: #f8f9fa;
    padding: 15px 20px;
    border-bottom: 1px solid #e0e0e0;
}

.metadata {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    font-size: 0.9em;
}

.meta-item {
    color: #666;
}

.meta-item strong {
    color: #333;
}

.iframe-container {
    flex: 1;
    overflow: hidden;
}

.iframe-container iframe {
    width: 100%;
    height: 100%;
}

.page-actions {
    padding: 15px 20px;
    background: white;
    border-top: 1px solid #e0e0e0;
    display: flex;
    gap: 10px;
}

.action-btn {
    padding: 8px 16px;
    border: 1px solid #ddd;
    background: white;
    border-radius: 4px;
    text-decoration: none;
    color: #333;
    cursor: pointer;
    transition: all 0.2s;
}

.action-btn:hover {
    background: #f0f0f0;
    border-color: #3498db;
    color: #3498db;
}

@media (max-width: 768px) {
    .main-content {
        grid-template-columns: 1fr;
    }

    .sidebar {
        max-height: 400px;
    }

    .neighbors-sidebar {
        width: 250px;
    }
}
"""

    def _get_graph_js(self) -> str:
        """Get graph visualization JavaScript."""
        return """
// Graph visualization using vis-network

let network = null;
let graphData = null;

function initializeGraph(data) {
    graphData = data;

    const container = document.getElementById('network-graph');

    // Prepare data for vis-network
    const nodes = new vis.DataSet(data.nodes.map(n => ({
        id: n.id,
        label: n.label,
        title: n.title,
        group: n.group
    })));

    const edges = new vis.DataSet(data.edges.map(e => ({
        from: e.from,
        to: e.to,
        arrows: 'to',
        color: { color: e.color },
        value: e.weight
    })));

    const options = {
        nodes: {
            shape: 'dot',
            size: 16,
            font: {
                size: 12,
                color: '#333'
            },
            borderWidth: 2,
            shadow: true
        },
        edges: {
            width: 1,
            smooth: {
                type: 'continuous'
            }
        },
        physics: {
            stabilization: false,
            barnesHut: {
                gravitationalConstant: -2000,
                springConstant: 0.001,
                springLength: 200
            }
        },
        interaction: {
            hover: true,
            navigationButtons: true,
            keyboard: true
        }
    };

    network = new vis.Network(container, { nodes, edges }, options);

    // Handle node clicks
    network.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = data.nodes.find(n => n.id === nodeId);
            if (node) {
                window.location.href = `pages/${node.page_id}.html`;
            }
        }
    });
}

function zoomIn() {
    const scale = network.getScale() * 1.2;
    network.moveTo({ scale: scale });
}

function zoomOut() {
    const scale = network.getScale() * 0.8;
    network.moveTo({ scale: scale });
}

function fitGraph() {
    network.fit();
}

function togglePhysics() {
    const options = network.physics.options.enabled
        ? { physics: { enabled: false } }
        : { physics: { enabled: true } };
    network.setOptions(options);
}
"""

    def _get_page_js(self) -> str:
        """Get page interaction JavaScript."""
        return """
// Page interactions

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('hidden');
}

function zoomGraph() {
    // Navigate to main graph view
    window.location.href = '../index.html';
}

// Handle keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // ESC to toggle sidebar
    if (e.key === 'Escape') {
        toggleSidebar();
    }
    // G to go to graph
    if (e.key === 'g' || e.key === 'G') {
        zoomGraph();
    }
});
"""
