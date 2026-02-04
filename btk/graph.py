"""
Bookmark graph module for discovering relationships between bookmarks.

Computes similarity edges based on:
1. Domain hierarchy similarity (URL path and subdomain matching)
2. Tag similarity (Jaccard distance, hierarchical tags)
3. Direct links (bookmark1 links to bookmark2)
4. Indirect links (multi-hop paths, optional/expensive)
"""
from typing import Optional, List, Dict, Set, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
import re
from pathlib import Path


@dataclass
class GraphConfig:
    """Configuration for graph computation."""
    # Component weights (0 = disabled)
    domain_weight: float = 1.0
    tag_weight: float = 2.0
    direct_link_weight: float = 5.0
    indirect_link_weight: float = 0.0  # Off by default (expensive)

    # Thresholds
    min_edge_weight: float = 0.1  # Don't create edges below this
    max_indirect_hops: int = 3

    # Domain matching
    subdomain_bonus: float = 0.5  # Extra weight for matching subdomain
    path_depth_weight: float = 0.3  # Weight per matching path segment


class BookmarkGraph:
    """
    Compute and store bookmark similarity graph.

    Edges are weighted by multiple similarity metrics:
    - Domain/URL similarity
    - Tag overlap (Jaccard)
    - Direct hyperlinks
    - Indirect paths (optional)
    """

    def __init__(self, db):
        """Initialize graph with database connection."""
        from btk.db import Database
        self.db: Database = db
        self.edges: Dict[Tuple[int, int], Dict] = {}  # {(id1, id2): {weight, components}}
        self.link_index: Dict[int, Set[str]] = {}  # {bookmark_id: set(linked_urls)}
        self.url_to_id: Dict[str, int] = {}  # {url: bookmark_id}

    def build(self, config: Optional[GraphConfig] = None, progress_callback=None) -> Dict:
        """
        Build the bookmark graph.

        Args:
            config: Graph configuration (defaults if None)
            progress_callback: Optional callback function(current, total, edges_found)

        Returns:
            Statistics about the built graph
        """
        if config is None:
            config = GraphConfig()

        stats = {
            'total_bookmarks': 0,
            'total_edges': 0,
            'avg_edge_weight': 0.0,
            'max_edge_weight': 0.0,
            'components': {
                'domain': 0,
                'tag': 0,
                'direct_link': 0,
                'indirect_link': 0
            }
        }

        # Get all bookmarks
        bookmarks = self.db.all()
        stats['total_bookmarks'] = len(bookmarks)

        # Build URL index and link index
        self._build_indices(bookmarks)

        # Calculate total comparisons for progress
        n = len(bookmarks)
        total_comparisons = n * (n - 1) // 2
        comparisons_done = 0

        # Compute pairwise edges
        for i, b1 in enumerate(bookmarks):
            for b2 in bookmarks[i+1:]:
                weight, components = self._compute_edge(b1, b2, config)

                if weight >= config.min_edge_weight:
                    self.edges[(b1.id, b2.id)] = {
                        'weight': weight,
                        'components': components
                    }
                    stats['total_edges'] += 1
                    stats['max_edge_weight'] = max(stats['max_edge_weight'], weight)

                    # Track component usage
                    for comp_name, comp_value in components.items():
                        if comp_value > 0:
                            stats['components'][comp_name] += 1

                comparisons_done += 1

            # Report progress after each bookmark's comparisons
            if progress_callback:
                progress_callback(comparisons_done, total_comparisons, stats['total_edges'])

        # Calculate average
        if stats['total_edges'] > 0:
            total_weight = sum(e['weight'] for e in self.edges.values())
            stats['avg_edge_weight'] = total_weight / stats['total_edges']

        return stats

    def _build_indices(self, bookmarks):
        """Build URL and link indices from bookmarks."""
        from btk.models import ContentCache
        from sqlalchemy import select

        # URL to ID mapping
        for b in bookmarks:
            self.url_to_id[b.url] = b.id

        # Extract outbound links from cached content
        # Query content_cache separately to avoid lazy loading issues
        with self.db.session() as session:
            bookmark_ids = [b.id for b in bookmarks]
            caches = session.execute(
                select(ContentCache).where(ContentCache.bookmark_id.in_(bookmark_ids))
            ).scalars().all()

            cache_by_id = {c.bookmark_id: c for c in caches}

            for b in bookmarks:
                links = set()
                cache = cache_by_id.get(b.id)
                if cache and cache.markdown_content:
                    # Extract URLs from markdown content
                    urls = self._extract_urls(cache.markdown_content)
                    links.update(urls)
                self.link_index[b.id] = links

    def _extract_urls(self, text: str) -> Set[str]:
        """Extract HTTP(S) URLs from text."""
        # Simple URL regex
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        return set(urls)

    def _compute_edge(self, b1, b2, config: GraphConfig) -> Tuple[float, Dict[str, float]]:
        """
        Compute edge weight between two bookmarks.

        Returns:
            (total_weight, {component_name: component_weight})
        """
        components = {
            'domain': 0.0,
            'tag': 0.0,
            'direct_link': 0.0,
            'indirect_link': 0.0
        }

        # 1. Domain similarity
        if config.domain_weight > 0:
            domain_sim = self._domain_similarity(b1.url, b2.url, config)
            components['domain'] = domain_sim * config.domain_weight

        # 2. Tag similarity
        if config.tag_weight > 0:
            tag_sim = self._tag_similarity(b1, b2)
            components['tag'] = tag_sim * config.tag_weight

        # 3. Direct links
        if config.direct_link_weight > 0:
            direct_link = self._check_direct_link(b1, b2)
            if direct_link:
                components['direct_link'] = config.direct_link_weight

        # 4. Indirect links (expensive, off by default)
        if config.indirect_link_weight > 0:
            indirect_weight = self._compute_indirect_link(b1, b2, config)
            components['indirect_link'] = indirect_weight * config.indirect_link_weight

        total_weight = sum(components.values())
        return total_weight, components

    def _domain_similarity(self, url1: str, url2: str, config: GraphConfig) -> float:
        """
        Compute domain and path similarity.

        Scoring:
        - Matching subdomain: bonus
        - Matching domain: 1.0
        - Matching path segments: incremental bonus
        """
        parsed1 = urlparse(url1)
        parsed2 = urlparse(url2)

        # Parse domains
        domain1 = parsed1.netloc.lower()
        domain2 = parsed2.netloc.lower()

        # No match if different base domains
        base1 = self._get_base_domain(domain1)
        base2 = self._get_base_domain(domain2)

        if base1 != base2:
            return 0.0

        score = 1.0  # Base score for matching domain

        # Subdomain match bonus
        if domain1 == domain2:
            score += config.subdomain_bonus

        # Path similarity
        path1 = parsed1.path.strip('/').split('/')
        path2 = parsed2.path.strip('/').split('/')

        # Count matching path segments (from left)
        common_segments = 0
        for p1, p2 in zip(path1, path2):
            if p1 == p2:
                common_segments += 1
            else:
                break

        score += common_segments * config.path_depth_weight

        return score

    def _get_base_domain(self, netloc: str) -> str:
        """
        Extract base domain (e.g., example.com from api.docs.example.com).

        Simple heuristic: last two parts if more than 2, else as-is.
        """
        parts = netloc.split('.')
        if len(parts) >= 2:
            # Handle special TLDs like .co.uk later if needed
            return '.'.join(parts[-2:])
        return netloc

    def _tag_similarity(self, b1, b2) -> float:
        """
        Compute tag similarity using hierarchical Jaccard.

        For hierarchical tags (e.g., programming/python), we consider
        partial matches weighted by depth.
        """
        tags1 = set(t.name for t in b1.tags)
        tags2 = set(t.name for t in b2.tags)

        if not tags1 or not tags2:
            return 0.0

        # Simple Jaccard for now (can enhance with hierarchy later)
        intersection = len(tags1 & tags2)
        union = len(tags1 | tags2)

        return intersection / union if union > 0 else 0.0

    def _check_direct_link(self, b1, b2) -> bool:
        """Check if b1 links directly to b2 or vice versa."""
        # Check if b2's URL appears in b1's links
        if b1.id in self.link_index:
            if b2.url in self.link_index[b1.id]:
                return True

        # Check reverse
        if b2.id in self.link_index:
            if b1.url in self.link_index[b2.id]:
                return True

        return False

    def _compute_indirect_link(self, b1, b2, config: GraphConfig) -> float:
        """
        Compute indirect link weight via BFS.

        Weight decreases with hop distance: 1/hop²
        """
        # TODO: Implement BFS path finding with hop limit
        # This is expensive and off by default
        # For now, return 0
        return 0.0

    def get_neighbors(self, bookmark_id: int, min_weight: float = 0.0, limit: int = 10) -> List[Dict]:
        """
        Get neighboring bookmarks sorted by edge weight.

        Args:
            bookmark_id: Source bookmark
            min_weight: Minimum edge weight to include
            limit: Maximum number of neighbors

        Returns:
            List of {bookmark_id, weight, components}
        """
        neighbors = []

        for (id1, id2), edge_data in self.edges.items():
            if edge_data['weight'] < min_weight:
                continue

            if id1 == bookmark_id:
                neighbors.append({
                    'bookmark_id': id2,
                    'weight': edge_data['weight'],
                    'components': edge_data['components']
                })
            elif id2 == bookmark_id:
                neighbors.append({
                    'bookmark_id': id1,
                    'weight': edge_data['weight'],
                    'components': edge_data['components']
                })

        # Sort by weight descending
        neighbors.sort(key=lambda x: x['weight'], reverse=True)

        return neighbors[:limit]

    def save(self, db_path: Optional[str] = None):
        """Save graph to database."""
        from sqlalchemy import text

        # Use the existing engine from the database
        engine = self.db.engine

        # Create table if not exists
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bookmark_graph (
                    bookmark1_id INTEGER NOT NULL,
                    bookmark2_id INTEGER NOT NULL,
                    weight REAL NOT NULL,
                    domain_component REAL,
                    tag_component REAL,
                    direct_link_component REAL,
                    indirect_link_component REAL,
                    PRIMARY KEY (bookmark1_id, bookmark2_id)
                )
            """))
            conn.commit()

            # Clear existing data
            conn.execute(text("DELETE FROM bookmark_graph"))
            conn.commit()

            # Insert edges
            for (id1, id2), edge_data in self.edges.items():
                comps = edge_data['components']
                conn.execute(text("""
                    INSERT INTO bookmark_graph VALUES
                    (:id1, :id2, :weight, :domain, :tag, :direct, :indirect)
                """), {
                    'id1': id1,
                    'id2': id2,
                    'weight': edge_data['weight'],
                    'domain': comps['domain'],
                    'tag': comps['tag'],
                    'direct': comps['direct_link'],
                    'indirect': comps['indirect_link']
                })
            conn.commit()

    def load(self, db_path: Optional[str] = None):
        """
        Load graph from database.

        Raises:
            ValueError: If graph table doesn't exist (need to build first)
        """
        from sqlalchemy import text, inspect

        # Use the existing engine from the database
        engine = self.db.engine

        self.edges = {}

        # Check if table exists
        inspector = inspect(engine)
        if not inspector.has_table('bookmark_graph'):
            raise ValueError(
                "Graph has not been built yet. "
                "Please run 'btk graph build' first to create the bookmark graph."
            )

        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT bookmark1_id, bookmark2_id, weight,
                       domain_component, tag_component,
                       direct_link_component, indirect_link_component
                FROM bookmark_graph
            """))

            for row in result:
                id1, id2, weight, domain, tag, direct, indirect = row
                self.edges[(id1, id2)] = {
                    'weight': weight,
                    'components': {
                        'domain': domain,
                        'tag': tag,
                        'direct_link': direct,
                        'indirect_link': indirect
                    }
                }

    def export_d3(self, output_path: Path, min_weight: float = 0.0):
        """Export graph in D3.js force-directed format."""
        import json

        # Filter edges by weight
        filtered_edges = {k: v for k, v in self.edges.items() if v['weight'] >= min_weight}

        # Get all unique bookmark IDs from filtered edges
        bookmark_ids = set()
        for id1, id2 in filtered_edges.keys():
            bookmark_ids.add(id1)
            bookmark_ids.add(id2)

        # Fetch bookmark data
        bookmarks_data = {}
        for bid in bookmark_ids:
            b = self.db.get(bid)
            if b:
                bookmarks_data[bid] = {
                    'id': bid,
                    'title': b.title,
                    'url': b.url,
                    'tags': [t.name for t in b.tags],
                    'stars': b.stars
                }

        # Build D3 format
        d3_data = {
            'nodes': [
                {
                    'id': bid,
                    'title': data['title'],
                    'url': data['url'],
                    'tags': data['tags'],
                    'starred': data['stars']
                }
                for bid, data in bookmarks_data.items()
            ],
            'links': [
                {
                    'source': id1,
                    'target': id2,
                    'weight': edge['weight'],
                    'domain': edge['components']['domain'],
                    'tag': edge['components']['tag'],
                    'direct_link': edge['components']['direct_link']
                }
                for (id1, id2), edge in filtered_edges.items()
            ]
        }

        with open(output_path, 'w') as f:
            json.dump(d3_data, f, indent=2)

    def export_svg(self, output_path: Path, min_weight: float = 0.0,
                   width: int = 2000, height: int = 2000, show_labels: bool = True):
        """
        Export graph as SVG with force-directed layout.

        Args:
            output_path: Path to save SVG file
            min_weight: Minimum edge weight to include
            width: SVG width in pixels
            height: SVG height in pixels
            show_labels: Whether to show bookmark titles
        """
        import math
        import random

        # Filter edges by weight
        filtered_edges = {k: v for k, v in self.edges.items() if v['weight'] >= min_weight}

        if not filtered_edges:
            raise ValueError(f"No edges with weight >= {min_weight}")

        # Get all unique bookmark IDs
        bookmark_ids = set()
        for id1, id2 in filtered_edges.keys():
            bookmark_ids.add(id1)
            bookmark_ids.add(id2)

        # Fetch bookmark data
        nodes = {}
        for bid in bookmark_ids:
            b = self.db.get(bid)
            if b:
                nodes[bid] = {
                    'id': bid,
                    'title': b.title,
                    'url': b.url,
                    'tags': [t.name for t in b.tags],
                    'starred': b.stars,
                    'x': random.uniform(width * 0.2, width * 0.8),
                    'y': random.uniform(height * 0.2, height * 0.8),
                    'vx': 0.0,
                    'vy': 0.0
                }

        # Simple force-directed layout (Fruchterman-Reingold inspired)
        iterations = 100
        k = math.sqrt((width * height) / len(nodes))  # Optimal distance
        temperature = width / 10.0

        for iteration in range(iterations):
            # Repulsive forces between all nodes
            for n1_id in nodes:
                n1 = nodes[n1_id]
                fx, fy = 0.0, 0.0

                for n2_id in nodes:
                    if n1_id == n2_id:
                        continue
                    n2 = nodes[n2_id]

                    dx = n1['x'] - n2['x']
                    dy = n1['y'] - n2['y']
                    dist = math.sqrt(dx*dx + dy*dy) + 0.01  # Avoid division by zero

                    # Repulsive force
                    force = (k * k) / dist
                    fx += (dx / dist) * force
                    fy += (dy / dist) * force

                n1['vx'] = fx
                n1['vy'] = fy

            # Attractive forces along edges
            for (id1, id2), edge in filtered_edges.items():
                n1 = nodes[id1]
                n2 = nodes[id2]

                dx = n2['x'] - n1['x']
                dy = n2['y'] - n1['y']
                dist = math.sqrt(dx*dx + dy*dy) + 0.01

                # Attractive force proportional to edge weight
                force = (dist * dist) / k * (edge['weight'] / 5.0)  # Scale by weight

                n1['vx'] += (dx / dist) * force
                n1['vy'] += (dy / dist) * force
                n2['vx'] -= (dx / dist) * force
                n2['vy'] -= (dy / dist) * force

            # Apply forces with cooling
            t = temperature * (1.0 - iteration / iterations)
            for node in nodes.values():
                disp = math.sqrt(node['vx']**2 + node['vy']**2) + 0.01
                node['x'] += (node['vx'] / disp) * min(disp, t)
                node['y'] += (node['vy'] / disp) * min(disp, t)

                # Keep within bounds
                node['x'] = max(50, min(width - 50, node['x']))
                node['y'] = max(50, min(height - 50, node['y']))

        # Generate SVG
        svg_parts = []
        svg_parts.append('<?xml version="1.0" encoding="UTF-8"?>')
        svg_parts.append(f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">')
        svg_parts.append('<rect width="100%" height="100%" fill="#1a1a1a"/>')

        # Draw edges
        svg_parts.append('<g id="edges">')
        for (id1, id2), edge in filtered_edges.items():
            n1 = nodes[id1]
            n2 = nodes[id2]

            # Edge thickness based on weight
            stroke_width = math.sqrt(edge['weight']) * 0.5
            opacity = min(0.8, edge['weight'] / 10.0)

            svg_parts.append(f'<line x1="{n1["x"]}" y1="{n1["y"]}" x2="{n2["x"]}" y2="{n2["y"]}" '
                           f'stroke="#999" stroke-width="{stroke_width}" opacity="{opacity}"/>')
        svg_parts.append('</g>')

        # Draw nodes
        svg_parts.append('<g id="nodes">')
        for node in nodes.values():
            # Color based on first tag
            color = self._tag_to_color(node['tags'][0] if node['tags'] else "default")

            # Starred nodes get gold stroke
            stroke_color = "#ffd700" if node['starred'] else "#fff"
            stroke_width = 2.5 if node['starred'] else 1.5

            svg_parts.append(f'<circle cx="{node["x"]}" cy="{node["y"]}" r="8" '
                           f'fill="{color}" stroke="{stroke_color}" stroke-width="{stroke_width}"/>')

            # Add label if requested
            if show_labels:
                # Truncate long titles
                title = node['title'][:30] + ("..." if len(node['title']) > 30 else "")
                # Escape XML special characters
                title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

                svg_parts.append(f'<text x="{node["x"] + 12}" y="{node["y"] + 4}" '
                               f'font-family="Arial, sans-serif" font-size="10" fill="#fff">{title}</text>')
        svg_parts.append('</g>')

        svg_parts.append('</svg>')

        with open(output_path, 'w') as f:
            f.write('\n'.join(svg_parts))

    def _tag_to_color(self, tag: str) -> str:
        """Convert tag to consistent color."""
        # Hash string to hue
        hash_val = 0
        for char in tag:
            hash_val = ord(char) + ((hash_val << 5) - hash_val)
        hue = abs(hash_val) % 360

        # Convert HSL to RGB
        import colorsys
        r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.5, 0.7)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def export_gexf(self, output_path: Path, min_weight: float = 0.0):
        """
        Export graph in GEXF format (Gephi's native format).

        Args:
            output_path: Path to save GEXF file
            min_weight: Minimum edge weight to include
        """
        from datetime import datetime
        import xml.etree.ElementTree as ET
        from xml.dom import minidom

        # Filter edges by weight
        filtered_edges = {k: v for k, v in self.edges.items() if v['weight'] >= min_weight}

        if not filtered_edges:
            raise ValueError(f"No edges with weight >= {min_weight}")

        # Get all unique bookmark IDs
        bookmark_ids = set()
        for id1, id2 in filtered_edges.keys():
            bookmark_ids.add(id1)
            bookmark_ids.add(id2)

        # Create GEXF structure
        gexf = ET.Element('gexf', xmlns="http://www.gexf.net/1.2draft", version="1.2")
        meta = ET.SubElement(gexf, 'meta', lastmodifieddate=datetime.now().isoformat())
        ET.SubElement(meta, 'creator').text = 'BTK - Bookmark Toolkit'
        ET.SubElement(meta, 'description').text = 'Bookmark similarity graph'

        graph = ET.SubElement(gexf, 'graph', mode="static", defaultedgetype="undirected")

        # Node attributes
        attributes = ET.SubElement(graph, 'attributes', **{'class': 'node'})
        ET.SubElement(attributes, 'attribute', id="0", title="url", type="string")
        ET.SubElement(attributes, 'attribute', id="1", title="starred", type="boolean")
        ET.SubElement(attributes, 'attribute', id="2", title="tags", type="string")

        # Add nodes
        nodes = ET.SubElement(graph, 'nodes')
        for bid in bookmark_ids:
            b = self.db.get(bid)
            if b:
                node = ET.SubElement(nodes, 'node', id=str(bid), label=b.title)
                attvalues = ET.SubElement(node, 'attvalues')
                ET.SubElement(attvalues, 'attvalue', **{'for': '0', 'value': b.url})
                ET.SubElement(attvalues, 'attvalue', **{'for': '1', 'value': str(b.stars).lower()})
                ET.SubElement(attvalues, 'attvalue', **{'for': '2', 'value': ','.join(t.name for t in b.tags)})

        # Edge attributes
        edge_attributes = ET.SubElement(graph, 'attributes', **{'class': 'edge'})
        ET.SubElement(edge_attributes, 'attribute', id="0", title="domain_weight", type="float")
        ET.SubElement(edge_attributes, 'attribute', id="1", title="tag_weight", type="float")
        ET.SubElement(edge_attributes, 'attribute', id="2", title="direct_link", type="float")

        # Add edges
        edges = ET.SubElement(graph, 'edges')
        for edge_id, ((id1, id2), edge) in enumerate(filtered_edges.items()):
            e = ET.SubElement(edges, 'edge', id=str(edge_id), source=str(id1), target=str(id2), weight=str(edge['weight']))
            attvalues = ET.SubElement(e, 'attvalues')
            ET.SubElement(attvalues, 'attvalue', **{'for': '0', 'value': str(edge['components']['domain'])})
            ET.SubElement(attvalues, 'attvalue', **{'for': '1', 'value': str(edge['components']['tag'])})
            ET.SubElement(attvalues, 'attvalue', **{'for': '2', 'value': str(edge['components']['direct_link'])})

        # Pretty print XML
        xml_str = minidom.parseString(ET.tostring(gexf)).toprettyxml(indent="  ")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_str)

    def export_graphml(self, output_path: Path, min_weight: float = 0.0):
        """
        Export graph in GraphML format.

        Args:
            output_path: Path to save GraphML file
            min_weight: Minimum edge weight to include
        """
        import xml.etree.ElementTree as ET
        from xml.dom import minidom

        # Filter edges by weight
        filtered_edges = {k: v for k, v in self.edges.items() if v['weight'] >= min_weight}

        if not filtered_edges:
            raise ValueError(f"No edges with weight >= {min_weight}")

        # Get all unique bookmark IDs
        bookmark_ids = set()
        for id1, id2 in filtered_edges.keys():
            bookmark_ids.add(id1)
            bookmark_ids.add(id2)

        # Create GraphML structure
        graphml = ET.Element('graphml', xmlns="http://graphml.graphdrawing.org/xmlns",
                            **{'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
                               'xsi:schemaLocation': "http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd"})

        # Define keys (attributes)
        ET.SubElement(graphml, 'key', id="d0", **{'for': 'node', 'attr.name': 'title', 'attr.type': 'string'})
        ET.SubElement(graphml, 'key', id="d1", **{'for': 'node', 'attr.name': 'url', 'attr.type': 'string'})
        ET.SubElement(graphml, 'key', id="d2", **{'for': 'node', 'attr.name': 'starred', 'attr.type': 'boolean'})
        ET.SubElement(graphml, 'key', id="d3", **{'for': 'node', 'attr.name': 'tags', 'attr.type': 'string'})
        ET.SubElement(graphml, 'key', id="d4", **{'for': 'edge', 'attr.name': 'weight', 'attr.type': 'double'})
        ET.SubElement(graphml, 'key', id="d5", **{'for': 'edge', 'attr.name': 'domain_weight', 'attr.type': 'double'})
        ET.SubElement(graphml, 'key', id="d6", **{'for': 'edge', 'attr.name': 'tag_weight', 'attr.type': 'double'})
        ET.SubElement(graphml, 'key', id="d7", **{'for': 'edge', 'attr.name': 'direct_link', 'attr.type': 'double'})

        graph = ET.SubElement(graphml, 'graph', id="G", edgedefault="undirected")

        # Add nodes
        for bid in bookmark_ids:
            b = self.db.get(bid)
            if b:
                node = ET.SubElement(graph, 'node', id=f"n{bid}")
                ET.SubElement(node, 'data', key="d0").text = b.title
                ET.SubElement(node, 'data', key="d1").text = b.url
                ET.SubElement(node, 'data', key="d2").text = str(b.stars).lower()
                ET.SubElement(node, 'data', key="d3").text = ','.join(t.name for t in b.tags)

        # Add edges
        for edge_id, ((id1, id2), edge) in enumerate(filtered_edges.items()):
            e = ET.SubElement(graph, 'edge', id=f"e{edge_id}", source=f"n{id1}", target=f"n{id2}")
            ET.SubElement(e, 'data', key="d4").text = str(edge['weight'])
            ET.SubElement(e, 'data', key="d5").text = str(edge['components']['domain'])
            ET.SubElement(e, 'data', key="d6").text = str(edge['components']['tag'])
            ET.SubElement(e, 'data', key="d7").text = str(edge['components']['direct_link'])

        # Pretty print XML
        xml_str = minidom.parseString(ET.tostring(graphml)).toprettyxml(indent="  ")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_str)

    def export_gml(self, output_path: Path, min_weight: float = 0.0):
        """
        Export graph in GML format (Graph Modeling Language).

        Args:
            output_path: Path to save GML file
            min_weight: Minimum edge weight to include
        """
        # Filter edges by weight
        filtered_edges = {k: v for k, v in self.edges.items() if v['weight'] >= min_weight}

        if not filtered_edges:
            raise ValueError(f"No edges with weight >= {min_weight}")

        # Get all unique bookmark IDs
        bookmark_ids = set()
        for id1, id2 in filtered_edges.keys():
            bookmark_ids.add(id1)
            bookmark_ids.add(id2)

        lines = []
        lines.append("graph [")
        lines.append("  directed 0")

        # Add nodes
        for bid in bookmark_ids:
            b = self.db.get(bid)
            if b:
                lines.append("  node [")
                lines.append(f"    id {bid}")
                # Escape quotes in strings
                title = b.title.replace('"', '\\"')
                url = b.url.replace('"', '\\"')
                tags = ','.join(t.name for t in b.tags).replace('"', '\\"')
                lines.append(f'    label "{title}"')
                lines.append(f'    url "{url}"')
                lines.append(f'    starred {1 if b.stars else 0}')
                lines.append(f'    tags "{tags}"')
                lines.append("  ]")

        # Add edges
        for (id1, id2), edge in filtered_edges.items():
            lines.append("  edge [")
            lines.append(f"    source {id1}")
            lines.append(f"    target {id2}")
            lines.append(f"    weight {edge['weight']}")
            lines.append(f"    domain_weight {edge['components']['domain']}")
            lines.append(f"    tag_weight {edge['components']['tag']}")
            lines.append(f"    direct_link {edge['components']['direct_link']}")
            lines.append("  ]")

        lines.append("]")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
