"""
Comprehensive tests for btk/graph.py

Tests the BookmarkGraph class including:
- Graph building and configuration
- Error handling (table not exists, empty database)
- Similarity computation (domain, tag, link)
- Neighbor discovery
- Graph persistence (save/load)
- Graph export formats (D3, SVG, GEXF, GraphML, GML)
"""
import pytest
import tempfile
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from btk.db import Database
from btk.models import Bookmark, Tag, ContentCache
from btk.graph import BookmarkGraph, GraphConfig
from sqlalchemy import text


class TestGraphConfig:
    """Test GraphConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GraphConfig()

        assert config.domain_weight == 1.0
        assert config.tag_weight == 2.0
        assert config.direct_link_weight == 5.0
        assert config.indirect_link_weight == 0.0
        assert config.min_edge_weight == 0.1
        assert config.max_indirect_hops == 3
        assert config.subdomain_bonus == 0.5
        assert config.path_depth_weight == 0.3

    def test_custom_config(self):
        """Test custom configuration."""
        config = GraphConfig(
            domain_weight=2.0,
            tag_weight=3.0,
            min_edge_weight=0.5
        )

        assert config.domain_weight == 2.0
        assert config.tag_weight == 3.0
        assert config.min_edge_weight == 0.5


class TestBookmarkGraphInit:
    """Test BookmarkGraph initialization."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_init(self, db):
        """Test graph initialization."""
        graph = BookmarkGraph(db)

        assert graph.db is db
        assert isinstance(graph.edges, dict)
        assert len(graph.edges) == 0
        assert isinstance(graph.link_index, dict)
        assert isinstance(graph.url_to_id, dict)


class TestBookmarkGraphBuild:
    """Test graph building functionality."""

    @pytest.fixture
    def db_with_bookmarks(self):
        """Create database with sample bookmarks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add bookmarks with various relationships
            db.add(
                url="https://python.org/docs",
                title="Python Documentation",
                tags=["python", "documentation"]
            )
            db.add(
                url="https://python.org/tutorial",
                title="Python Tutorial",
                tags=["python", "tutorial"]
            )
            db.add(
                url="https://github.com/python",
                title="Python on GitHub",
                tags=["python", "git"]
            )
            db.add(
                url="https://example.com",
                title="Example Site",
                tags=["example"]
            )

            yield db

    def test_build_empty_database(self):
        """Test building graph with empty database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)
            graph = BookmarkGraph(db)

            stats = graph.build()

            assert stats['total_bookmarks'] == 0
            assert stats['total_edges'] == 0
            assert stats['avg_edge_weight'] == 0.0

    def test_build_with_bookmarks(self, db_with_bookmarks):
        """Test building graph with bookmarks."""
        graph = BookmarkGraph(db_with_bookmarks)

        stats = graph.build()

        assert stats['total_bookmarks'] == 4
        assert stats['total_edges'] > 0  # Should find some edges
        assert 'components' in stats
        assert 'domain' in stats['components']
        assert 'tag' in stats['components']

    def test_build_with_custom_config(self, db_with_bookmarks):
        """Test building with custom configuration."""
        graph = BookmarkGraph(db_with_bookmarks)
        config = GraphConfig(
            domain_weight=0.0,  # Disable domain similarity
            tag_weight=5.0,     # High tag weight
            min_edge_weight=1.0  # Higher threshold
        )

        stats = graph.build(config)

        assert stats['total_bookmarks'] == 4
        # Edges should only come from tags
        for edge_data in graph.edges.values():
            assert edge_data['components']['domain'] == 0.0

    def test_build_progress_callback(self, db_with_bookmarks):
        """Test progress callback during build."""
        graph = BookmarkGraph(db_with_bookmarks)
        callback_calls = []

        def progress_callback(current, total, edges_found):
            callback_calls.append({
                'current': current,
                'total': total,
                'edges': edges_found
            })

        stats = graph.build(progress_callback=progress_callback)

        # Should have called progress callback
        assert len(callback_calls) > 0
        # Last call should have current == total
        assert callback_calls[-1]['current'] == callback_calls[-1]['total']

    def test_build_min_edge_weight_filter(self, db_with_bookmarks):
        """Test that min_edge_weight filters out weak edges."""
        graph = BookmarkGraph(db_with_bookmarks)

        # Build with very high threshold
        config = GraphConfig(min_edge_weight=100.0)
        stats = graph.build(config)

        # Should have no edges due to high threshold
        assert stats['total_edges'] == 0


class TestGraphLoadErrorHandling:
    """Test graph.load() error handling - PRIORITY TESTS."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_load_when_table_does_not_exist(self, db):
        """Test load() raises ValueError when bookmark_graph table doesn't exist."""
        graph = BookmarkGraph(db)

        with pytest.raises(ValueError, match="Graph has not been built yet"):
            graph.load()

    def test_load_when_table_exists_but_empty(self, db):
        """Test load() succeeds when table exists but is empty."""
        graph = BookmarkGraph(db)

        # Build and save empty graph
        graph.build()
        graph.save()

        # Now load should succeed
        graph2 = BookmarkGraph(db)
        graph2.load()

        assert len(graph2.edges) == 0

    def test_load_when_table_has_data(self, db):
        """Test load() correctly loads saved graph data."""
        # Add bookmarks
        db.add(url="https://python.org", title="Python", tags=["python"])
        db.add(url="https://python.org/docs", title="Docs", tags=["python"])

        # Build and save
        graph = BookmarkGraph(db)
        graph.build()
        initial_edge_count = len(graph.edges)
        graph.save()

        # Load in new graph instance
        graph2 = BookmarkGraph(db)
        graph2.load()

        assert len(graph2.edges) == initial_edge_count
        assert len(graph2.edges) > 0

    def test_load_error_message_helpful(self, db):
        """Test that error message is helpful."""
        graph = BookmarkGraph(db)

        try:
            graph.load()
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            error_msg = str(e)
            assert "Graph has not been built yet" in error_msg
            assert "btk graph build" in error_msg


class TestGraphSaveLoad:
    """Test graph save and load functionality."""

    @pytest.fixture
    def db_with_graph(self):
        """Create database with built graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add bookmarks
            db.add(url="https://python.org", title="Python", tags=["python", "programming"])
            db.add(url="https://python.org/docs", title="Docs", tags=["python", "docs"])
            db.add(url="https://github.com", title="GitHub", tags=["git"])

            # Build graph
            graph = BookmarkGraph(db)
            graph.build()

            yield db, graph

    def test_save_creates_table(self, db_with_graph):
        """Test that save creates the bookmark_graph table."""
        db, graph = db_with_graph
        graph.save()

        # Check table exists
        with db.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bookmark_graph'"
            ))
            tables = result.fetchall()
            assert len(tables) == 1

    def test_save_and_load_preserves_edges(self, db_with_graph):
        """Test that save/load preserves edge data."""
        db, graph = db_with_graph
        original_edges = dict(graph.edges)

        graph.save()

        # Load in new instance
        graph2 = BookmarkGraph(db)
        graph2.load()

        # Should have same edges
        assert len(graph2.edges) == len(original_edges)

        # Verify edge details
        for key, edge_data in original_edges.items():
            assert key in graph2.edges
            assert graph2.edges[key]['weight'] == edge_data['weight']
            assert graph2.edges[key]['components']['domain'] == edge_data['components']['domain']
            assert graph2.edges[key]['components']['tag'] == edge_data['components']['tag']

    def test_save_clears_existing_data(self, db_with_graph):
        """Test that save clears existing graph data."""
        db, graph = db_with_graph

        # Save first time
        graph.save()

        # Modify graph
        graph.edges.clear()

        # Save again
        graph.save()

        # Load and verify it's empty
        graph2 = BookmarkGraph(db)
        graph2.load()
        assert len(graph2.edges) == 0


class TestDomainSimilarity:
    """Test domain similarity computation."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_same_domain_same_path(self, db):
        """Test similarity for same domain and path."""
        graph = BookmarkGraph(db)
        config = GraphConfig()

        sim = graph._domain_similarity(
            "https://python.org/docs",
            "https://python.org/docs",
            config
        )

        # Should be high: base domain + subdomain + path
        assert sim > 1.0

    def test_same_domain_different_path(self, db):
        """Test similarity for same domain, different paths."""
        graph = BookmarkGraph(db)
        config = GraphConfig()

        sim = graph._domain_similarity(
            "https://python.org/docs",
            "https://python.org/tutorial",
            config
        )

        # Should be base score + subdomain bonus
        assert sim > 1.0
        assert sim < 2.0

    def test_same_base_domain_different_subdomain(self, db):
        """Test similarity for same base domain, different subdomains."""
        graph = BookmarkGraph(db)
        config = GraphConfig()

        sim = graph._domain_similarity(
            "https://docs.python.org",
            "https://www.python.org",
            config
        )

        # Should be base score only (no subdomain bonus) plus path match if any
        # Since both have empty paths, we get base domain score
        assert sim >= 1.0

    def test_different_domain(self, db):
        """Test similarity for different domains."""
        graph = BookmarkGraph(db)
        config = GraphConfig()

        sim = graph._domain_similarity(
            "https://python.org",
            "https://github.com",
            config
        )

        assert sim == 0.0

    def test_path_similarity_matching_segments(self, db):
        """Test path similarity with matching segments."""
        graph = BookmarkGraph(db)
        config = GraphConfig()

        sim = graph._domain_similarity(
            "https://python.org/docs/tutorial/intro",
            "https://python.org/docs/tutorial/advanced",
            config
        )

        # Should get bonus for matching /docs/tutorial/
        assert sim > 1.5


class TestTagSimilarity:
    """Test tag similarity computation."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_identical_tags(self, db):
        """Test similarity for identical tags."""
        b1 = db.add(url="https://a.com", title="A", tags=["python", "programming"])
        b2 = db.add(url="https://b.com", title="B", tags=["python", "programming"])

        graph = BookmarkGraph(db)
        sim = graph._tag_similarity(b1, b2)

        # Jaccard = 2/2 = 1.0
        assert sim == 1.0

    def test_partial_overlap(self, db):
        """Test similarity for partial tag overlap."""
        b1 = db.add(url="https://a.com", title="A", tags=["python", "programming"])
        b2 = db.add(url="https://b.com", title="B", tags=["python", "web"])

        graph = BookmarkGraph(db)
        sim = graph._tag_similarity(b1, b2)

        # Jaccard = 1/3 = 0.333...
        assert 0.3 < sim < 0.4

    def test_no_overlap(self, db):
        """Test similarity for no tag overlap."""
        b1 = db.add(url="https://a.com", title="A", tags=["python"])
        b2 = db.add(url="https://b.com", title="B", tags=["java"])

        graph = BookmarkGraph(db)
        sim = graph._tag_similarity(b1, b2)

        assert sim == 0.0

    def test_one_empty_tags(self, db):
        """Test similarity when one bookmark has no tags."""
        b1 = db.add(url="https://a.com", title="A", tags=["python"])
        b2 = db.add(url="https://b.com", title="B", tags=[])

        # Re-fetch to ensure tags are loaded in session
        b1 = db.get(id=b1.id)
        b2 = db.get(id=b2.id)

        graph = BookmarkGraph(db)
        sim = graph._tag_similarity(b1, b2)

        assert sim == 0.0

    def test_both_empty_tags(self, db):
        """Test similarity when both bookmarks have no tags."""
        b1 = db.add(url="https://a.com", title="A", tags=[])
        b2 = db.add(url="https://b.com", title="B", tags=[])

        # Re-fetch to ensure tags are loaded in session
        b1 = db.get(id=b1.id)
        b2 = db.get(id=b2.id)

        graph = BookmarkGraph(db)
        sim = graph._tag_similarity(b1, b2)

        assert sim == 0.0


class TestDirectLinks:
    """Test direct link detection."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_check_direct_link_with_link(self, db):
        """Test direct link detection when link exists."""
        b1 = db.add(url="https://a.com", title="A")
        b2 = db.add(url="https://b.com", title="B")

        # Create content cache with markdown containing link to b2
        with db.session() as session:
            cache = ContentCache(
                bookmark_id=b1.id,
                html_content=b"<html></html>",
                markdown_content=f"Check out this link: {b2.url}",
                content_hash="test"
            )
            session.add(cache)

        graph = BookmarkGraph(db)
        graph._build_indices([b1, b2])

        has_link = graph._check_direct_link(b1, b2)
        assert has_link is True

    def test_check_direct_link_reverse(self, db):
        """Test direct link detection in reverse direction."""
        b1 = db.add(url="https://a.com", title="A")
        b2 = db.add(url="https://b.com", title="B")

        # b2 links to b1
        with db.session() as session:
            cache = ContentCache(
                bookmark_id=b2.id,
                html_content=b"<html></html>",
                markdown_content=f"Link to {b1.url}",
                content_hash="test"
            )
            session.add(cache)

        graph = BookmarkGraph(db)
        graph._build_indices([b1, b2])

        has_link = graph._check_direct_link(b1, b2)
        assert has_link is True

    def test_check_direct_link_no_link(self, db):
        """Test direct link detection when no link exists."""
        b1 = db.add(url="https://a.com", title="A")
        b2 = db.add(url="https://b.com", title="B")

        graph = BookmarkGraph(db)
        graph._build_indices([b1, b2])

        has_link = graph._check_direct_link(b1, b2)
        assert has_link is False


class TestGetNeighbors:
    """Test neighbor discovery."""

    @pytest.fixture
    def db_with_graph(self):
        """Create database with built graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add bookmarks with clear relationships
            db.add(url="https://python.org", title="Python", tags=["python"])
            db.add(url="https://python.org/docs", title="Docs", tags=["python", "docs"])
            db.add(url="https://github.com", title="GitHub", tags=["git"])

            # Build graph
            graph = BookmarkGraph(db)
            graph.build()

            yield db, graph

    def test_get_neighbors_basic(self, db_with_graph):
        """Test basic neighbor discovery."""
        db, graph = db_with_graph

        neighbors = graph.get_neighbors(1)

        # Should return list
        assert isinstance(neighbors, list)

    def test_get_neighbors_with_limit(self, db_with_graph):
        """Test neighbor limit."""
        db, graph = db_with_graph

        neighbors = graph.get_neighbors(1, limit=1)

        assert len(neighbors) <= 1

    def test_get_neighbors_with_min_weight(self, db_with_graph):
        """Test min_weight filter."""
        db, graph = db_with_graph

        neighbors = graph.get_neighbors(1, min_weight=100.0)

        # Should have no neighbors with such high threshold
        assert len(neighbors) == 0

    def test_get_neighbors_sorted_by_weight(self, db_with_graph):
        """Test that neighbors are sorted by weight descending."""
        db, graph = db_with_graph

        neighbors = graph.get_neighbors(1, limit=10)

        if len(neighbors) > 1:
            # Check descending order
            for i in range(len(neighbors) - 1):
                assert neighbors[i]['weight'] >= neighbors[i + 1]['weight']

    def test_get_neighbors_returns_components(self, db_with_graph):
        """Test that neighbor results include components."""
        db, graph = db_with_graph

        neighbors = graph.get_neighbors(1)

        if neighbors:
            assert 'bookmark_id' in neighbors[0]
            assert 'weight' in neighbors[0]
            assert 'components' in neighbors[0]
            assert 'domain' in neighbors[0]['components']
            assert 'tag' in neighbors[0]['components']


class TestGraphExport:
    """Test graph export functionality."""

    @pytest.fixture
    def db_with_graph(self):
        """Create database with built graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(path=db_path)

            # Add bookmarks
            db.add(url="https://python.org", title="Python", tags=["python"], stars=True)
            db.add(url="https://python.org/docs", title="Docs", tags=["python", "docs"])

            # Build graph
            graph = BookmarkGraph(db)
            graph.build()

            yield db, graph, tmpdir

    def test_export_d3_creates_file(self, db_with_graph):
        """Test D3 export creates valid JSON file."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.json"

        graph.export_d3(output_file)

        assert output_file.exists()

        # Verify JSON structure
        with open(output_file) as f:
            data = json.load(f)
            assert 'nodes' in data
            assert 'links' in data
            assert isinstance(data['nodes'], list)
            assert isinstance(data['links'], list)

    def test_export_d3_with_min_weight(self, db_with_graph):
        """Test D3 export with min_weight filter."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.json"

        # Export with very high threshold
        graph.export_d3(output_file, min_weight=100.0)

        with open(output_file) as f:
            data = json.load(f)
            # Should have nodes but no links
            assert len(data['links']) == 0

    def test_export_svg_creates_file(self, db_with_graph):
        """Test SVG export creates file."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.svg"

        graph.export_svg(output_file)

        assert output_file.exists()

        # Verify SVG content
        content = output_file.read_text()
        assert '<?xml version="1.0"' in content
        assert '<svg' in content
        assert '</svg>' in content

    def test_export_svg_no_labels(self, db_with_graph):
        """Test SVG export without labels."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.svg"

        graph.export_svg(output_file, show_labels=False)

        content = output_file.read_text()
        # Should have circles but fewer text elements
        assert '<circle' in content

    def test_export_svg_custom_size(self, db_with_graph):
        """Test SVG export with custom dimensions."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.svg"

        graph.export_svg(output_file, width=1000, height=1000)

        content = output_file.read_text()
        assert 'width="1000"' in content
        assert 'height="1000"' in content

    def test_export_svg_min_weight_error(self, db_with_graph):
        """Test SVG export raises error when no edges after filtering."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.svg"

        with pytest.raises(ValueError, match="No edges"):
            graph.export_svg(output_file, min_weight=100.0)

    def test_export_gexf_creates_file(self, db_with_graph):
        """Test GEXF export creates valid XML file."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.gexf"

        graph.export_gexf(output_file)

        assert output_file.exists()

        content = output_file.read_text()
        assert '<?xml version' in content
        assert '<gexf' in content
        assert '</gexf>' in content
        assert '<nodes>' in content
        assert '<edges>' in content

    def test_export_graphml_creates_file(self, db_with_graph):
        """Test GraphML export creates valid XML file."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.graphml"

        graph.export_graphml(output_file)

        assert output_file.exists()

        content = output_file.read_text()
        assert '<?xml version' in content
        assert '<graphml' in content
        assert '</graphml>' in content
        assert '<graph' in content

    def test_export_gml_creates_file(self, db_with_graph):
        """Test GML export creates file."""
        db, graph, tmpdir = db_with_graph
        output_file = Path(tmpdir) / "graph.gml"

        graph.export_gml(output_file)

        assert output_file.exists()

        content = output_file.read_text()
        assert 'graph [' in content
        assert 'node [' in content
        assert 'edge [' in content

    def test_export_formats_error_on_no_edges(self, db_with_graph):
        """Test export formats raise error when no edges after filtering."""
        db, graph, tmpdir = db_with_graph

        formats = [
            ('gexf', Path(tmpdir) / "test.gexf"),
            ('graphml', Path(tmpdir) / "test.graphml"),
            ('gml', Path(tmpdir) / "test.gml"),
        ]

        for format_name, output_file in formats:
            with pytest.raises(ValueError, match="No edges"):
                if format_name == 'gexf':
                    graph.export_gexf(output_file, min_weight=100.0)
                elif format_name == 'graphml':
                    graph.export_graphml(output_file, min_weight=100.0)
                elif format_name == 'gml':
                    graph.export_gml(output_file, min_weight=100.0)


class TestHelperMethods:
    """Test helper methods."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_get_base_domain(self, db):
        """Test base domain extraction."""
        graph = BookmarkGraph(db)

        assert graph._get_base_domain("www.python.org") == "python.org"
        assert graph._get_base_domain("docs.python.org") == "python.org"
        assert graph._get_base_domain("api.docs.python.org") == "python.org"
        assert graph._get_base_domain("example.com") == "example.com"
        assert graph._get_base_domain("localhost") == "localhost"

    def test_extract_urls(self, db):
        """Test URL extraction from text."""
        graph = BookmarkGraph(db)

        text = """
        Check out these links:
        https://python.org
        http://github.com
        Visit https://example.com for more info.
        """

        urls = graph._extract_urls(text)

        assert "https://python.org" in urls
        assert "http://github.com" in urls
        assert "https://example.com" in urls
        assert len(urls) == 3

    def test_tag_to_color(self, db):
        """Test tag to color conversion."""
        graph = BookmarkGraph(db)

        color1 = graph._tag_to_color("python")
        color2 = graph._tag_to_color("python")
        color3 = graph._tag_to_color("java")

        # Same tag should produce same color
        assert color1 == color2
        # Different tags should produce different colors (likely)
        assert color1 != color3
        # Color should be hex format
        assert color1.startswith("#")
        assert len(color1) == 7


class TestEdgeComputation:
    """Test edge weight computation."""

    @pytest.fixture
    def db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            yield Database(path=db_path)

    def test_compute_edge_with_all_components(self, db):
        """Test edge computation with all similarity components."""
        b1 = db.add(
            url="https://python.org/docs",
            title="Python Docs",
            tags=["python", "docs"]
        )
        b2 = db.add(
            url="https://python.org/tutorial",
            title="Python Tutorial",
            tags=["python", "tutorial"]
        )

        graph = BookmarkGraph(db)
        config = GraphConfig()

        weight, components = graph._compute_edge(b1, b2, config)

        # Should have domain and tag components
        assert components['domain'] > 0
        assert components['tag'] > 0
        assert weight > 0

    def test_compute_edge_disabled_components(self, db):
        """Test edge computation with disabled components."""
        b1 = db.add(url="https://a.com", title="A", tags=["test"])
        b2 = db.add(url="https://b.com", title="B", tags=["test"])

        graph = BookmarkGraph(db)
        config = GraphConfig(
            domain_weight=0.0,  # Disable
            tag_weight=0.0,     # Disable
            direct_link_weight=0.0  # Disable
        )

        weight, components = graph._compute_edge(b1, b2, config)

        assert components['domain'] == 0.0
        assert components['tag'] == 0.0
        assert components['direct_link'] == 0.0
        assert weight == 0.0

    def test_compute_edge_below_threshold(self, db):
        """Test that edges below threshold are filtered."""
        b1 = db.add(url="https://a.com", title="A", tags=[])
        b2 = db.add(url="https://b.com", title="B", tags=[])

        graph = BookmarkGraph(db)
        config = GraphConfig(min_edge_weight=0.1)

        # Build and check edges
        graph.build(config)

        # No relationship between these bookmarks
        edge_key = (b1.id, b2.id)
        assert edge_key not in graph.edges
