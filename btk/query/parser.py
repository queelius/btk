"""
YAML parser for btk query definitions.

Parses YAML view definitions into Query AST objects.

Example YAML:

    recent:
      filter:
        added: within 30 days
      sort: added desc
      limit: 100

    ai_papers:
      filter:
        tags: any [ai/*, ml/*]
        domain: [arxiv.org, openreview.net]
        content.has: [transcript, thumbnail]
      sort: stars desc, added desc

    popular_tags:
      entity: tags
      filter:
        usage: >= 10
      sort: usage desc

    domain_stats:
      entity: stats
      from: bookmarks
      group: domain
      compute:
        count: count()
        avg_stars: avg(stars)
      filter:
        count: >= 5
      sort: count desc
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from .ast import (
    Query, EntityType, FieldRef, Predicate,
    SortSpec, GroupSpec, ComputeSpec
)
from .expr import parse_expr


class ParseError(Exception):
    """Error parsing query definition."""
    pass


class QueryParser:
    """
    Parser for YAML query definitions.

    Converts YAML dictionaries into Query AST objects.
    """

    def __init__(self, registry: Optional["QueryRegistry"] = None):
        """
        Initialize parser.

        Args:
            registry: Optional registry for resolving view references
        """
        self.registry = registry

    def parse(self, definition: Dict[str, Any], name: Optional[str] = None) -> Query:
        """
        Parse a single query definition.

        Args:
            definition: Dictionary containing query definition
            name: Optional name for the query

        Returns:
            Parsed Query object
        """
        if not isinstance(definition, dict):
            raise ParseError(f"Query definition must be a dictionary, got {type(definition)}")

        query = Query(name=name)

        # Parse entity type
        if 'entity' in definition:
            query.entity = EntityType.from_string(definition['entity'])

        # Parse source (composition with another view)
        if 'from' in definition:
            from_val = definition['from']
            if isinstance(from_val, str):
                # Could be a view reference or entity type
                try:
                    # Try as entity type first
                    query.entity = EntityType.from_string(from_val)
                except ValueError:
                    # It's a view reference
                    query.source = from_val

        # Parse base (alias for 'from' for composition)
        if 'base' in definition:
            query.source = definition['base']

        # Parse filters
        if 'filter' in definition:
            query.predicates = self._parse_filter(definition['filter'])

        # Legacy 'where' support
        if 'where' in definition:
            query.predicates.extend(self._parse_filter(definition['where']))

        # Parse sorting
        if 'sort' in definition:
            query.sort = self._parse_sort(definition['sort'])

        # Legacy 'order' support
        if 'order' in definition:
            query.sort = self._parse_sort(definition['order'])

        # Parse limit and offset
        if 'limit' in definition:
            query.limit = int(definition['limit'])

        if 'offset' in definition:
            query.offset = int(definition['offset'])

        # Parse aggregation
        if 'group' in definition or 'group_by' in definition:
            group_val = definition.get('group') or definition.get('group_by')
            query.group_by = GroupSpec.parse_list(group_val)
            # If grouping, default to stats entity
            if query.entity == EntityType.BOOKMARK:
                query.entity = EntityType.STATS

        if 'compute' in definition:
            query.compute = self._parse_compute(definition['compute'])

        if 'having' in definition:
            query.having = self._parse_filter(definition['having'])

        # Parse composition
        if 'union' in definition:
            query.union = self._parse_view_list(definition['union'])

        if 'intersect' in definition:
            query.intersect = self._parse_view_list(definition['intersect'])

        if 'exclude' in definition:
            query.exclude = self._parse_filter(definition['exclude'])

        # Parse parameters
        if 'params' in definition:
            query.params, query.param_defaults = self._parse_params(definition['params'])

        # Metadata
        if 'description' in definition:
            query.description = definition['description']

        return query

    def _parse_filter(self, filter_def: Any) -> List[Predicate]:
        """Parse filter definition into predicates."""
        predicates = []

        if isinstance(filter_def, dict):
            for field, value in filter_def.items():
                predicates.append(Predicate(
                    field=FieldRef.parse(field),
                    expr=parse_expr(value)
                ))

        elif isinstance(filter_def, list):
            # List of filter conditions
            for item in filter_def:
                if isinstance(item, dict):
                    predicates.extend(self._parse_filter(item))
                else:
                    raise ParseError(f"Invalid filter item: {item}")

        else:
            raise ParseError(f"Invalid filter definition: {filter_def}")

        return predicates

    def _parse_sort(self, sort_def: Any) -> List[SortSpec]:
        """Parse sort definition."""
        if isinstance(sort_def, str):
            return SortSpec.parse_list(sort_def)

        if isinstance(sort_def, list):
            result = []
            for item in sort_def:
                if isinstance(item, str):
                    result.extend(SortSpec.parse_list(item))
                elif isinstance(item, dict):
                    field = item.get('field', item.get('by', ''))
                    direction = item.get('direction', item.get('dir', 'asc'))
                    nulls = item.get('nulls', 'last')
                    result.append(SortSpec(field=field, direction=direction, nulls=nulls))
            return result

        if isinstance(sort_def, dict):
            field = sort_def.get('field', sort_def.get('by', ''))
            direction = sort_def.get('direction', sort_def.get('dir', 'asc'))
            nulls = sort_def.get('nulls', 'last')
            return [SortSpec(field=field, direction=direction, nulls=nulls)]

        return []

    def _parse_compute(self, compute_def: Any) -> List[ComputeSpec]:
        """Parse compute/aggregate definition."""
        specs = []

        if isinstance(compute_def, dict):
            for name, value in compute_def.items():
                specs.append(ComputeSpec.parse(name, value))

        elif isinstance(compute_def, list):
            for item in compute_def:
                if isinstance(item, str):
                    # Parse "count()" or "sum(field)" syntax
                    specs.append(ComputeSpec.parse(item, item))
                elif isinstance(item, dict):
                    for name, value in item.items():
                        specs.append(ComputeSpec.parse(name, value))

        return specs

    def _parse_view_list(self, view_def: Any) -> List[str]:
        """Parse a list of view references."""
        if isinstance(view_def, str):
            return [view_def]
        if isinstance(view_def, list):
            return [str(v) for v in view_def]
        return []

    def _parse_params(self, params_def: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Parse parameter definitions."""
        params = {}
        defaults = {}

        if isinstance(params_def, dict):
            for name, spec in params_def.items():
                if isinstance(spec, dict):
                    params[name] = spec.get('type', 'string')
                    if 'default' in spec:
                        defaults[name] = spec['default']
                else:
                    # Just a type or default value
                    if spec in ('string', 'int', 'float', 'bool', 'date'):
                        params[name] = spec
                    else:
                        defaults[name] = spec

        elif isinstance(params_def, list):
            for name in params_def:
                params[str(name)] = 'string'

        return params, defaults


def parse_query(definition: Dict[str, Any], name: Optional[str] = None) -> Query:
    """
    Parse a single query definition.

    Convenience function that creates a parser and parses.
    """
    parser = QueryParser()
    return parser.parse(definition, name)


def parse_queries_file(path: Union[str, Path]) -> Dict[str, Query]:
    """
    Parse a YAML file containing multiple query definitions.

    Args:
        path: Path to YAML file

    Returns:
        Dictionary mapping query names to Query objects
    """
    path = Path(path)

    if not path.exists():
        raise ParseError(f"Queries file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ParseError(f"Queries file must contain a dictionary, got {type(data)}")

    parser = QueryParser()
    queries = {}

    for name, definition in data.items():
        if isinstance(definition, dict):
            queries[name] = parser.parse(definition, name)

    return queries


def parse_queries_string(yaml_string: str) -> Dict[str, Query]:
    """
    Parse a YAML string containing multiple query definitions.

    Args:
        yaml_string: YAML content as string

    Returns:
        Dictionary mapping query names to Query objects
    """
    data = yaml.safe_load(yaml_string)

    if not isinstance(data, dict):
        raise ParseError(f"YAML must contain a dictionary, got {type(data)}")

    parser = QueryParser()
    queries = {}

    for name, definition in data.items():
        if isinstance(definition, dict):
            queries[name] = parser.parse(definition, name)

    return queries


# =============================================================================
# Query Registry
# =============================================================================

class QueryRegistry:
    """
    Registry for named queries.

    Stores query definitions and supports loading from files.
    """

    def __init__(self):
        self._queries: Dict[str, Query] = {}
        self._sources: Dict[str, Path] = {}  # Track where queries came from

    def register(self, name: str, query: Query, source: Optional[Path] = None) -> None:
        """Register a query."""
        query.name = name
        self._queries[name] = query
        if source:
            self._sources[name] = source

    def get(self, name: str) -> Query:
        """Get a query by name."""
        if name not in self._queries:
            raise KeyError(f"Unknown query: {name}")
        return self._queries[name]

    def has(self, name: str) -> bool:
        """Check if a query exists."""
        return name in self._queries

    def list(self) -> List[str]:
        """List all query names."""
        return list(self._queries.keys())

    def all(self) -> Dict[str, Query]:
        """Get all queries."""
        return dict(self._queries)

    def load_file(self, path: Union[str, Path]) -> int:
        """
        Load queries from a YAML file.

        Returns number of queries loaded.
        """
        path = Path(path)
        queries = parse_queries_file(path)

        for name, query in queries.items():
            self.register(name, query, source=path)

        return len(queries)

    def load_string(self, yaml_string: str, source_name: str = "<string>") -> int:
        """
        Load queries from a YAML string.

        Returns number of queries loaded.
        """
        queries = parse_queries_string(yaml_string)

        for name, query in queries.items():
            self.register(name, query)

        return len(queries)

    def load_builtin(self) -> None:
        """Load built-in queries."""
        builtin = """
# Built-in queries

all:
  description: "All bookmarks"
  sort: added desc

recent:
  description: "Recently added bookmarks"
  filter:
    added: within 30 days
  sort: added desc
  limit: 100

starred:
  description: "Starred bookmarks"
  filter:
    stars: true
  sort: added desc

pinned:
  description: "Pinned bookmarks"
  filter:
    pinned: true
  sort: added desc

archived:
  description: "Archived bookmarks"
  filter:
    archived: true
  sort: added desc

unread:
  description: "Never visited bookmarks"
  filter:
    visit_count: 0
  sort: added desc

popular:
  description: "Frequently visited bookmarks"
  filter:
    visit_count: ">= 5"
  sort: visit_count desc

broken:
  description: "Unreachable bookmarks"
  filter:
    reachable: false
  sort: added desc

untagged:
  description: "Bookmarks without tags"
  filter:
    tags: missing
  sort: added desc

videos:
  description: "Video bookmarks"
  filter:
    media_type: video
  sort: added desc

pdfs:
  description: "PDF documents"
  filter:
    url: ends_with ".pdf"
  sort: added desc

preserved:
  description: "Bookmarks with preserved content"
  filter:
    content.has: [transcript, thumbnail]
  sort: added desc
"""
        self.load_string(builtin, source_name="<builtin>")

    def clear(self) -> None:
        """Remove all registered queries."""
        self._queries.clear()
        self._sources.clear()


# Global registry instance
_default_registry: Optional[QueryRegistry] = None


def get_registry() -> QueryRegistry:
    """Get the default query registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = QueryRegistry()
        _default_registry.load_builtin()
    return _default_registry


def reset_registry() -> None:
    """Reset the default registry."""
    global _default_registry
    _default_registry = None
