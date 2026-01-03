"""
BTK Query Language - A typed, composable query system.

This module provides a powerful query language for btk that supports:
- Multiple entity types (bookmarks, tags, stats, edges)
- Rich predicate expressions
- Query composition (union, intersect, pipeline)
- Aggregation and grouping

Example usage:

    from btk.query import query, execute_query
    from btk.db import Database

    db = Database('btk.db')

    # Fluent query builder
    q = (query()
        .filter('tags', 'any [ai/*, ml/*]')
        .filter('added', 'within 30 days')
        .sort('stars desc')
        .limit(100)
        .build())

    result = execute_query(db, q)

    for item in result:
        print(f"{item.title}: {item.url}")

    # Or from YAML
    from btk.query import parse_query, execute_query

    q = parse_query({
        'filter': {
            'tags': 'any [ai/*, ml/*]',
            'added': 'within 30 days',
        },
        'sort': 'stars desc',
        'limit': 100
    })

    result = execute_query(db, q)

    # Tag queries
    q = (query()
        .from_entity('tags')
        .filter('usage', '>= 10')
        .sort('usage desc')
        .build())

    # Aggregate queries
    q = (query()
        .from_entity('stats')
        .group_by('domain')
        .compute(count='count()', avg_stars='avg(stars)')
        .having('count', '>= 5')
        .sort('count desc')
        .build())
"""

# Expression AST and parser
from .expr import (
    Expr,
    Literal,
    Comparison,
    Temporal,
    Collection,
    StringOp,
    Existence,
    Compound,
    parse_expr,
    expr,
    all_of,
    any_of,
    not_,
)

# Query AST
from .ast import (
    EntityType,
    FieldRef,
    Predicate,
    SortSpec,
    GroupSpec,
    ComputeSpec,
    Query,
    QueryBuilder,
    query,
)

# Result types
from .results import (
    QueryResult,
    BookmarkResult,
    BookmarkItem,
    TagResult,
    TagItem,
    StatsResult,
    StatsRow,
    EdgeResult,
    Edge,
    create_result,
)

# Parser
from .parser import (
    ParseError,
    QueryParser,
    parse_query,
    parse_queries_file,
    parse_queries_string,
    QueryRegistry,
    get_registry,
    reset_registry,
)

# Executor
from .executor import (
    ExecutionContext,
    PredicateEvaluator,
    QueryExecutor,
    execute_query,
    execute_yaml,
)

__all__ = [
    # Expressions
    'Expr',
    'Literal',
    'Comparison',
    'Temporal',
    'Collection',
    'StringOp',
    'Existence',
    'Compound',
    'parse_expr',
    'expr',
    'all_of',
    'any_of',
    'not_',

    # Query AST
    'EntityType',
    'FieldRef',
    'Predicate',
    'SortSpec',
    'GroupSpec',
    'ComputeSpec',
    'Query',
    'QueryBuilder',
    'query',

    # Results
    'QueryResult',
    'BookmarkResult',
    'BookmarkItem',
    'TagResult',
    'TagItem',
    'StatsResult',
    'StatsRow',
    'EdgeResult',
    'Edge',
    'create_result',

    # Parser
    'ParseError',
    'QueryParser',
    'parse_query',
    'parse_queries_file',
    'parse_queries_string',
    'QueryRegistry',
    'get_registry',
    'reset_registry',

    # Executor
    'ExecutionContext',
    'PredicateEvaluator',
    'QueryExecutor',
    'execute_query',
    'execute_yaml',
]
