"""
Graph construction for MiniWeb bookmark network.

Builds a network graph based on:
1. URL mentions (links between pages)
2. Semantic similarity (content-based relationships)
3. Tag overlap (shared categorization)
"""

import logging
import requests
from typing import Dict, Any, List, Set, Tuple, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import networkx as nx
from collections import defaultdict
import re

logger = logging.getLogger(__name__)


class BookmarkGraph:
    """
    Build and analyze a network graph of bookmarks.

    Edges represent relationships:
    - 'link': Page A links to Page B
    - 'semantic': Pages have similar content (cosine similarity)
    - 'tag': Pages share tags
    """

    def __init__(self, timeout: int = 10, max_workers: int = 5):
        """
        Initialize bookmark graph builder.

        Args:
            timeout: Request timeout for fetching pages
            max_workers: Concurrent workers for fetching
        """
        self.timeout = timeout
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MiniWeb/1.0 (Bookmark Network Generator)'
        })

        # Build graph
        self.graph = nx.DiGraph()

    def build_graph(self, bookmarks: List[Dict[str, Any]],
                   include_links: bool = True,
                   include_semantic: bool = True,
                   include_tags: bool = True,
                   semantic_threshold: float = 0.5) -> nx.DiGraph:
        """
        Build complete bookmark network graph.

        Args:
            bookmarks: List of bookmarks
            include_links: Include URL mention edges
            include_semantic: Include semantic similarity edges
            include_tags: Include tag overlap edges
            semantic_threshold: Minimum similarity for semantic edges

        Returns:
            NetworkX directed graph
        """
        logger.info(f"Building graph for {len(bookmarks)} bookmarks")

        # Add all bookmarks as nodes
        for bookmark in bookmarks:
            url = bookmark['url']
            self.graph.add_node(url, **bookmark)

        # Create URL to bookmark mapping
        url_to_bookmark = {b['url']: b for b in bookmarks}

        # Add edges based on URL mentions
        if include_links:
            logger.info("Adding link-based edges...")
            self._add_link_edges(bookmarks, url_to_bookmark)

        # Add edges based on tag overlap
        if include_tags:
            logger.info("Adding tag-based edges...")
            self._add_tag_edges(bookmarks)

        # Add edges based on semantic similarity
        if include_semantic:
            logger.info("Adding semantic similarity edges...")
            self._add_semantic_edges(bookmarks, semantic_threshold)

        logger.info(f"Graph built: {self.graph.number_of_nodes()} nodes, "
                   f"{self.graph.number_of_edges()} edges")

        return self.graph

    def _add_link_edges(self, bookmarks: List[Dict[str, Any]],
                       url_to_bookmark: Dict[str, Dict[str, Any]]):
        """Add edges based on URL mentions in page content."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def fetch_and_extract_links(bookmark):
            """Fetch page and extract links."""
            url = bookmark['url']
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                links = set()

                # Extract all URLs from href attributes
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    # Resolve relative URLs
                    absolute_url = urljoin(url, href)
                    # Normalize URL
                    absolute_url = self._normalize_url(absolute_url)
                    links.add(absolute_url)

                return url, links

            except Exception as e:
                logger.debug(f"Failed to fetch {url}: {e}")
                return url, set()

        # Fetch pages concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_and_extract_links, b): b
                      for b in bookmarks}

            for future in as_completed(futures):
                source_url, extracted_links = future.result()

                # Add edges for links to other bookmarks
                for target_url in extracted_links:
                    if target_url in url_to_bookmark:
                        self.graph.add_edge(
                            source_url,
                            target_url,
                            edge_type='link',
                            weight=1.0
                        )

    def _add_tag_edges(self, bookmarks: List[Dict[str, Any]]):
        """Add edges based on shared tags."""
        # Group bookmarks by tag
        tag_to_urls = defaultdict(set)

        for bookmark in bookmarks:
            url = bookmark['url']
            tags = bookmark.get('tags', [])
            for tag in tags:
                tag_to_urls[tag].add(url)

        # Create edges between bookmarks with shared tags
        for tag, urls in tag_to_urls.items():
            urls_list = list(urls)
            for i, url1 in enumerate(urls_list):
                for url2 in urls_list[i+1:]:
                    # Calculate tag overlap weight
                    tags1 = set(self.graph.nodes[url1].get('tags', []))
                    tags2 = set(self.graph.nodes[url2].get('tags', []))

                    if tags1 and tags2:
                        overlap = len(tags1 & tags2)
                        total = len(tags1 | tags2)
                        weight = overlap / total if total > 0 else 0

                        if weight > 0.2:  # At least 20% overlap
                            # Add bidirectional edges
                            self.graph.add_edge(
                                url1, url2,
                                edge_type='tag',
                                weight=weight
                            )
                            self.graph.add_edge(
                                url2, url1,
                                edge_type='tag',
                                weight=weight
                            )

    def _add_semantic_edges(self, bookmarks: List[Dict[str, Any]],
                           threshold: float):
        """Add edges based on semantic similarity."""
        try:
            # Try to use semantic search integration if available
            from integrations.semantic_search.search import SemanticSearchEngine

            engine = SemanticSearchEngine()
            if not engine.validate():
                logger.warning("Semantic search not available, skipping semantic edges")
                return

            # Create embeddings
            embeddings = engine.create_embeddings(bookmarks)

            # Calculate pairwise similarities
            import numpy as np

            for i, bookmark1 in enumerate(bookmarks):
                url1 = bookmark1['url']

                # Get similar bookmarks
                similarities = engine.cosine_similarity(
                    embeddings[i:i+1],
                    embeddings
                )[0]

                for j, bookmark2 in enumerate(bookmarks):
                    if i == j:
                        continue

                    url2 = bookmark2['url']
                    similarity = float(similarities[j])

                    if similarity >= threshold:
                        self.graph.add_edge(
                            url1, url2,
                            edge_type='semantic',
                            weight=similarity
                        )

        except ImportError:
            logger.warning("semantic_search integration not available, skipping semantic edges")
        except Exception as e:
            logger.error(f"Failed to add semantic edges: {e}")

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison."""
        # Remove fragment
        url = url.split('#')[0]
        # Remove trailing slash
        url = url.rstrip('/')
        # Remove www prefix
        parsed = urlparse(url)
        if parsed.netloc.startswith('www.'):
            url = url.replace('www.', '', 1)
        return url

    def get_neighbors(self, url: str, max_distance: int = 1,
                     edge_types: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """
        Get neighboring bookmarks within max_distance hops.

        Args:
            url: Source bookmark URL
            max_distance: Maximum graph distance
            edge_types: Filter by edge types ('link', 'semantic', 'tag')

        Returns:
            List of neighbor bookmarks with metadata
        """
        if url not in self.graph:
            return []

        neighbors = []

        # BFS to find neighbors within distance
        from collections import deque

        queue = deque([(url, 0)])
        visited = {url}

        while queue:
            current_url, distance = queue.popleft()

            if distance >= max_distance:
                continue

            # Get successors
            for neighbor_url in self.graph.successors(current_url):
                if neighbor_url in visited:
                    continue

                # Check edge type filter
                edge_data = self.graph[current_url][neighbor_url]
                if edge_types and edge_data.get('edge_type') not in edge_types:
                    continue

                visited.add(neighbor_url)

                # Add to neighbors
                neighbor_data = dict(self.graph.nodes[neighbor_url])
                neighbor_data['distance'] = distance + 1
                neighbor_data['edge_type'] = edge_data.get('edge_type')
                neighbor_data['edge_weight'] = edge_data.get('weight', 0)
                neighbors.append(neighbor_data)

                # Add to queue for further exploration
                queue.append((neighbor_url, distance + 1))

        # Sort by distance, then weight
        neighbors.sort(key=lambda n: (n['distance'], -n.get('edge_weight', 0)))

        return neighbors

    def get_graph_statistics(self) -> Dict[str, Any]:
        """Get graph statistics."""
        stats = {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'avg_degree': sum(dict(self.graph.degree()).values()) / max(self.graph.number_of_nodes(), 1),
            'density': nx.density(self.graph),
            'is_connected': nx.is_weakly_connected(self.graph),
        }

        # Count edge types
        edge_types = defaultdict(int)
        for _, _, data in self.graph.edges(data=True):
            edge_types[data.get('edge_type', 'unknown')] += 1
        stats['edge_types'] = dict(edge_types)

        # Get connected components
        if not nx.is_weakly_connected(self.graph):
            components = list(nx.weakly_connected_components(self.graph))
            stats['num_components'] = len(components)
            stats['largest_component_size'] = len(max(components, key=len))

        return stats
