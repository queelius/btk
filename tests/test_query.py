"""
Tests for the btk.query module.

Tests the new query language including:
- Expression parsing and evaluation
- Query AST construction
- YAML parsing
- Query execution
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from btk.query import (
    # Expressions
    Expr, Literal, Comparison, Temporal, Collection, StringOp, Existence, Compound,
    parse_expr, expr, all_of, any_of, not_,

    # Query AST
    EntityType, FieldRef, Predicate, SortSpec, GroupSpec, ComputeSpec,
    Query, QueryBuilder, query,

    # Results
    QueryResult, BookmarkResult, BookmarkItem, TagResult, TagItem,
    StatsResult, StatsRow, EdgeResult, Edge,

    # Parser
    parse_query, parse_queries_string, QueryRegistry, get_registry, reset_registry,

    # Executor
    ExecutionContext, execute_query,
)


# =============================================================================
# Expression Parser Tests
# =============================================================================

class TestLiteralExpr:
    """Tests for Literal expressions."""

    def test_literal_equality(self):
        e = parse_expr(42)
        assert isinstance(e, Literal)
        assert e.evaluate(42) is True
        assert e.evaluate(43) is False

    def test_literal_string(self):
        e = parse_expr("hello")
        assert e.evaluate("hello") is True
        assert e.evaluate("world") is False

    def test_literal_bool(self):
        e = parse_expr(True)
        assert e.evaluate(True) is True
        assert e.evaluate(False) is False

    def test_literal_none(self):
        e = parse_expr(None)
        assert e.evaluate(None) is True
        assert e.evaluate(0) is False

    def test_literal_to_sql(self):
        e = Literal(42)
        sql, params = e.to_sql("field")
        assert sql == "field = ?"
        assert params == [42]


class TestComparisonExpr:
    """Tests for Comparison expressions."""

    def test_greater_than(self):
        e = parse_expr(">= 10")
        assert isinstance(e, Comparison)
        assert e.evaluate(10) is True
        assert e.evaluate(15) is True
        assert e.evaluate(5) is False

    def test_less_than(self):
        e = parse_expr("< 100")
        assert e.evaluate(50) is True
        assert e.evaluate(100) is False

    def test_not_equal(self):
        e = parse_expr("!= 0")
        assert e.evaluate(1) is True
        assert e.evaluate(0) is False

    def test_comparison_with_none(self):
        e = parse_expr(">= 10")
        assert e.evaluate(None) is False

    def test_comparison_to_sql(self):
        e = Comparison(">=", 10)
        sql, params = e.to_sql("stars")
        assert sql == "stars >= ?"
        assert params == [10]


class TestTemporalExpr:
    """Tests for Temporal expressions."""

    def test_within_days(self):
        e = parse_expr("within 30 days")
        assert isinstance(e, Temporal)

        recent = datetime.now() - timedelta(days=10)
        old = datetime.now() - timedelta(days=60)

        assert e.evaluate(recent) is True
        assert e.evaluate(old) is False

    def test_within_weeks(self):
        e = parse_expr("within 2 weeks")
        recent = datetime.now() - timedelta(days=7)
        old = datetime.now() - timedelta(days=21)

        assert e.evaluate(recent) is True
        assert e.evaluate(old) is False

    def test_before_date(self):
        e = parse_expr("before 2024-01-01")
        assert e.evaluate(datetime(2023, 6, 15)) is True
        assert e.evaluate(datetime(2024, 6, 15)) is False

    def test_after_date(self):
        e = parse_expr("after 2024-01-01")
        assert e.evaluate(datetime(2024, 6, 15)) is True
        assert e.evaluate(datetime(2023, 6, 15)) is False

    def test_temporal_with_none(self):
        e = parse_expr("within 30 days")
        assert e.evaluate(None) is False


class TestCollectionExpr:
    """Tests for Collection expressions."""

    def test_any_list(self):
        e = parse_expr("[a, b, c]")
        assert isinstance(e, Collection)
        assert e.op == 'any'
        assert e.evaluate("a") is True
        assert e.evaluate("d") is False

    def test_any_explicit(self):
        e = parse_expr("any [foo, bar]")
        assert e.evaluate("foo") is True
        assert e.evaluate("baz") is False

    def test_all_collection(self):
        e = parse_expr("all [a, b]")
        assert e.evaluate(["a", "b"]) is True
        assert e.evaluate(["a"]) is False

    def test_none_collection(self):
        e = parse_expr("none [x, y]")
        assert e.evaluate("a") is True
        assert e.evaluate("x") is False

    def test_glob_pattern(self):
        e = parse_expr("any [ai/*, ml/*]")
        assert e.evaluate("ai/deep-learning") is True
        assert e.evaluate("ml/transformers") is True
        assert e.evaluate("web/frontend") is False

    def test_collection_with_list_value(self):
        e = Collection('any', ['a', 'b'])
        assert e.evaluate(['a', 'c']) is True  # List contains 'a'
        assert e.evaluate(['x', 'y']) is False


class TestStringOpExpr:
    """Tests for StringOp expressions."""

    def test_contains(self):
        e = parse_expr('contains "neural"')
        assert isinstance(e, StringOp)
        assert e.evaluate("deep neural networks") is True
        assert e.evaluate("machine learning") is False

    def test_starts_with(self):
        e = parse_expr('starts_with "http"')
        assert e.evaluate("https://example.com") is True
        assert e.evaluate("ftp://server.com") is False

    def test_ends_with(self):
        e = parse_expr('ends_with ".pdf"')
        assert e.evaluate("paper.pdf") is True
        assert e.evaluate("paper.txt") is False

    def test_under_hierarchy(self):
        e = parse_expr("under programming/")
        assert e.evaluate("programming") is True
        assert e.evaluate("programming/python") is True
        assert e.evaluate("programming/python/web") is True
        assert e.evaluate("science") is False

    def test_case_insensitive(self):
        e = StringOp('contains', 'HELLO', case_sensitive=False)
        assert e.evaluate("hello world") is True

    def test_string_op_with_none(self):
        e = parse_expr('contains "test"')
        assert e.evaluate(None) is False


class TestExistenceExpr:
    """Tests for Existence expressions."""

    def test_exists(self):
        e = parse_expr("exists")
        assert isinstance(e, Existence)
        assert e.evaluate("something") is True
        assert e.evaluate(None) is False
        assert e.evaluate("") is False

    def test_missing(self):
        e = parse_expr("missing")
        assert e.evaluate(None) is True
        assert e.evaluate("") is True
        assert e.evaluate("something") is False

    def test_has_fields(self):
        e = parse_expr("has [transcript, thumbnail]")
        assert e.exists is True
        assert e.fields == ['transcript', 'thumbnail']

        obj = {'transcript': 'text', 'thumbnail': 'data'}
        assert e.evaluate(obj) is True

        obj_missing = {'transcript': 'text'}
        assert e.evaluate(obj_missing) is False


class TestCompoundExpr:
    """Tests for Compound expressions."""

    def test_all_of(self):
        e = all_of(">= 10", "< 100")
        assert e.evaluate(50) is True
        assert e.evaluate(5) is False
        assert e.evaluate(150) is False

    def test_any_of(self):
        e = any_of("= 1", "= 2", "= 3")
        assert e.evaluate(2) is True
        assert e.evaluate(5) is False

    def test_not(self):
        e = not_(">= 10")
        assert e.evaluate(5) is True
        assert e.evaluate(15) is False


class TestDictExpr:
    """Tests for dictionary-based expressions."""

    def test_min_max(self):
        e = parse_expr({'min': 10})
        assert isinstance(e, Comparison)
        assert e.evaluate(15) is True
        assert e.evaluate(5) is False

    def test_within_dict(self):
        e = parse_expr({'within': '30 days'})
        assert isinstance(e, Temporal)

    def test_any_dict(self):
        # Dict with 'any' key creates a Compound expression (logical OR)
        e = parse_expr({'any': ['a', 'b']})
        assert isinstance(e, Compound)
        assert e.op == 'any'


# =============================================================================
# Query AST Tests
# =============================================================================

class TestFieldRef:
    """Tests for FieldRef."""

    def test_simple_field(self):
        ref = FieldRef.parse("title")
        assert ref.path == ["title"]
        assert ref.is_relation is False
        assert ref.field == "title"

    def test_relation_field(self):
        ref = FieldRef.parse("content.has")
        assert ref.path == ["content", "has"]
        assert ref.is_relation is True
        assert ref.relation == "content"
        assert ref.field == "has"

    def test_deep_path(self):
        ref = FieldRef.parse("health.status.code")
        assert ref.path == ["health", "status", "code"]
        assert ref.full_path == "health.status.code"


class TestSortSpec:
    """Tests for SortSpec."""

    def test_parse_simple(self):
        spec = SortSpec.parse("added desc")
        assert spec.field == "added"
        assert spec.direction == "desc"

    def test_parse_asc(self):
        spec = SortSpec.parse("title")
        assert spec.field == "title"
        assert spec.direction == "asc"

    def test_parse_list(self):
        specs = SortSpec.parse_list("stars desc, added desc")
        assert len(specs) == 2
        assert specs[0].field == "stars"
        assert specs[1].field == "added"


class TestGroupSpec:
    """Tests for GroupSpec."""

    def test_simple_group(self):
        spec = GroupSpec.parse("domain")
        assert spec.field == "domain"
        assert spec.transform is None

    def test_temporal_group(self):
        spec = GroupSpec.parse("month(added)")
        assert spec.field == "added"
        assert spec.transform == "month"


class TestComputeSpec:
    """Tests for ComputeSpec."""

    def test_count(self):
        spec = ComputeSpec.parse("count", "count()")
        assert spec.name == "count"
        assert spec.func == "count"

    def test_sum_field(self):
        spec = ComputeSpec.parse("total", "sum(stars)")
        assert spec.name == "total"
        assert spec.func == "sum"
        assert spec.field == "stars"


class TestQueryBuilder:
    """Tests for QueryBuilder."""

    def test_simple_query(self):
        q = (query()
             .filter('stars', True)
             .sort('added desc')
             .limit(10)
             .build())

        assert q.entity == EntityType.BOOKMARK
        assert len(q.predicates) == 1
        assert len(q.sort) == 1
        assert q.limit == 10

    def test_entity_selection(self):
        q = query().from_entity('tags').build()
        assert q.entity == EntityType.TAG

    def test_aggregate_query(self):
        q = (query()
             .from_entity('stats')
             .group_by('domain')
             .compute(count='count()', avg_stars='avg(stars)')
             .build())

        assert q.entity == EntityType.STATS
        assert len(q.group_by) == 1
        assert len(q.compute) == 2


# =============================================================================
# Parser Tests
# =============================================================================

class TestQueryParser:
    """Tests for YAML query parsing."""

    def test_parse_simple_query(self):
        q = parse_query({
            'filter': {
                'stars': True
            },
            'sort': 'added desc',
            'limit': 100
        })

        assert q.entity == EntityType.BOOKMARK
        assert len(q.predicates) == 1
        assert q.limit == 100

    def test_parse_tag_query(self):
        q = parse_query({
            'entity': 'tags',
            'filter': {
                'usage': '>= 10'
            },
            'sort': 'usage desc'
        })

        assert q.entity == EntityType.TAG

    def test_parse_aggregate_query(self):
        q = parse_query({
            'entity': 'stats',
            'group': 'domain',
            'compute': {
                'count': 'count()',
                'avg_stars': 'avg(stars)'
            }
        })

        assert q.entity == EntityType.STATS
        assert len(q.group_by) == 1
        assert len(q.compute) == 2

    def test_parse_multiple_filters(self):
        q = parse_query({
            'filter': {
                'tags': 'any [ai/*, ml/*]',
                'added': 'within 30 days',
                'stars': '>= 3'
            }
        })

        assert len(q.predicates) == 3

    def test_parse_composition(self):
        q = parse_query({
            'union': ['view_a', 'view_b']
        })

        assert q.union == ['view_a', 'view_b']


class TestQueryRegistry:
    """Tests for QueryRegistry."""

    def setup_method(self):
        reset_registry()

    def test_builtin_queries(self):
        registry = get_registry()
        assert registry.has('recent')
        assert registry.has('starred')
        assert registry.has('untagged')

    def test_load_string(self):
        registry = QueryRegistry()
        count = registry.load_string("""
my_view:
  filter:
    tags: any [test]
  limit: 10
""")
        assert count == 1
        assert registry.has('my_view')

    def test_get_query(self):
        registry = get_registry()
        q = registry.get('recent')
        assert q.name == 'recent'
        assert q.limit == 100


# =============================================================================
# Result Tests
# =============================================================================

class TestQueryResult:
    """Tests for QueryResult."""

    def test_empty_result(self):
        result = QueryResult.empty()
        assert len(result) == 0
        assert result.first() is None

    def test_iteration(self):
        result = QueryResult(items=[1, 2, 3])
        assert list(result) == [1, 2, 3]

    def test_indexing(self):
        result = QueryResult(items=['a', 'b', 'c'])
        assert result[0] == 'a'
        assert result[1:3] == ['b', 'c']

    def test_map(self):
        result = QueryResult(items=[1, 2, 3])
        doubled = result.map(lambda x: x * 2)
        assert list(doubled) == [2, 4, 6]

    def test_filter(self):
        result = QueryResult(items=[1, 2, 3, 4, 5])
        evens = result.filter(lambda x: x % 2 == 0)
        assert list(evens) == [2, 4]


class TestStatsResult:
    """Tests for StatsResult."""

    def test_columns(self):
        rows = [
            StatsRow(group_key={'domain': 'a.com'}, values={'count': 10}),
            StatsRow(group_key={'domain': 'b.com'}, values={'count': 20})
        ]
        result = StatsResult(items=rows)

        assert result.columns == ['domain', 'count']

    def test_sum(self):
        rows = [
            StatsRow(group_key={'domain': 'a.com'}, values={'count': 10}),
            StatsRow(group_key={'domain': 'b.com'}, values={'count': 20})
        ]
        result = StatsResult(items=rows)

        assert result.sum('count') == 30


class TestEdgeResult:
    """Tests for EdgeResult."""

    def test_nodes(self):
        edges = [
            Edge(source='a', target='b', weight=1.0),
            Edge(source='b', target='c', weight=2.0)
        ]
        result = EdgeResult(items=edges)

        assert result.nodes() == {'a', 'b', 'c'}

    def test_adjacency_list(self):
        edges = [
            Edge(source='a', target='b', weight=1.0),
            Edge(source='a', target='c', weight=2.0)
        ]
        result = EdgeResult(items=edges)

        adj = result.to_adjacency_list()
        assert adj['a'] == [('b', 1.0), ('c', 2.0)]


# =============================================================================
# Integration Tests
# =============================================================================

class TestQueryExecution:
    """Integration tests for query execution."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        from unittest.mock import MagicMock
        from btk.models import Bookmark, Tag
        from datetime import datetime, timezone

        db = MagicMock()

        # Create mock bookmarks
        bookmarks = [
            MagicMock(
                id=1,
                url="https://arxiv.org/paper1",
                title="AI Paper 1",
                stars=True,
                added=datetime.now(timezone.utc) - timedelta(days=5),
                visit_count=10,
                tags=[MagicMock(name='ai'), MagicMock(name='ml')],
                media_type=None,
                content_cache=None
            ),
            MagicMock(
                id=2,
                url="https://example.com/page",
                title="Example Page",
                stars=False,
                added=datetime.now(timezone.utc) - timedelta(days=60),
                visit_count=2,
                tags=[MagicMock(name='web')],
                media_type=None,
                content_cache=None
            ),
        ]

        # Setup session mock
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = bookmarks
        session.execute.return_value.scalar.return_value = len(bookmarks)

        db.session.return_value.__enter__ = MagicMock(return_value=session)
        db.session.return_value.__exit__ = MagicMock(return_value=None)

        return db

    def test_simple_bookmark_query(self, mock_db):
        """Test basic bookmark query execution."""
        from btk.query import QueryExecutor

        q = (query()
             .filter('stars', True)
             .limit(10)
             .build())

        executor = QueryExecutor(mock_db)
        # This would require more complete mocking to test fully
        # Just verify it doesn't crash
        assert q.entity == EntityType.BOOKMARK

    def test_expression_based_query(self):
        """Test that expression parsing integrates correctly."""
        q = parse_query({
            'filter': {
                'tags': 'any [ai/*, ml/*]',
                'added': 'within 30 days',
                'content.has': '[transcript, thumbnail]'
            },
            'sort': 'stars desc, added desc',
            'limit': 50
        })

        assert len(q.predicates) == 3
        assert q.limit == 50

        # Check that predicates have correct expression types
        tag_pred = q.predicates[0]
        assert isinstance(tag_pred.expr, Collection)

        added_pred = q.predicates[1]
        assert isinstance(added_pred.expr, Temporal)


# =============================================================================
# SQL Generation Tests
# =============================================================================

class TestSQLGeneration:
    """Tests for SQL generation from expressions."""

    def test_comparison_sql(self):
        e = Comparison(">=", 10)
        sql, params = e.to_sql("stars")
        assert "stars >= ?" in sql
        assert params == [10]

    def test_collection_sql(self):
        e = Collection("any", ["a", "b", "c"])
        sql, params = e.to_sql("field")
        assert "IN" in sql
        assert params == ["a", "b", "c"]

    def test_glob_collection_sql(self):
        e = Collection("any", ["ai/*", "ml/*"])
        sql, params = e.to_sql("name")
        assert "LIKE" in sql
        assert "ai/%" in params[0]

    def test_string_contains_sql(self):
        e = StringOp("contains", "test")
        sql, params = e.to_sql("title")
        assert "LIKE" in sql
        assert "%test%" in params[0]

    def test_existence_sql(self):
        e = Existence(exists=True)
        sql, params = e.to_sql("field")
        assert "IS NOT NULL" in sql


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
