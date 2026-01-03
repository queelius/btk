"""
Query AST for the btk query language.

A Query represents a complete query against the btk database.
Queries are typed by their entity (Bookmark, Tag, Stats, etc.)
and support filtering, sorting, grouping, and composition.

Example query structure:
    Query(
        entity=EntityType.BOOKMARK,
        predicates=[
            Predicate(field=FieldRef(['tags']), expr=Collection('any', ['ai/*'])),
            Predicate(field=FieldRef(['added']), expr=Temporal('within', timedelta(days=30))),
        ],
        sort=[SortSpec('added', 'desc')],
        limit=100
    )
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from .expr import Expr, parse_expr


# =============================================================================
# Entity Types
# =============================================================================

class EntityType(Enum):
    """
    Entity types that can be queried.

    Each entity type has its own schema and valid predicates.
    """
    BOOKMARK = "bookmarks"
    TAG = "tags"
    CONTENT = "content"
    HEALTH = "health"
    STATS = "stats"        # Aggregate queries
    EDGES = "edges"        # Graph/relationship queries

    @classmethod
    def from_string(cls, s: str) -> "EntityType":
        """Parse entity type from string."""
        s = s.lower().strip()
        mapping = {
            'bookmark': cls.BOOKMARK,
            'bookmarks': cls.BOOKMARK,
            'tag': cls.TAG,
            'tags': cls.TAG,
            'content': cls.CONTENT,
            'health': cls.HEALTH,
            'stats': cls.STATS,
            'stat': cls.STATS,
            'aggregate': cls.STATS,
            'edge': cls.EDGES,
            'edges': cls.EDGES,
            'graph': cls.EDGES,
        }
        if s in mapping:
            return mapping[s]
        raise ValueError(f"Unknown entity type: {s}")


# =============================================================================
# Field References
# =============================================================================

@dataclass
class FieldRef:
    """
    Reference to a field, possibly through a relation.

    Examples:
        FieldRef(['title'])           -> bookmark.title
        FieldRef(['content', 'has'])  -> bookmark.content.has (relation)
        FieldRef(['health', 'status']) -> bookmark.health.status (relation)
        FieldRef(['tags'])            -> bookmark.tags (multi-value)
    """
    path: List[str]

    @classmethod
    def parse(cls, s: str) -> "FieldRef":
        """Parse field reference from dot-notation string."""
        return cls(path=s.split('.'))

    @property
    def is_relation(self) -> bool:
        """Check if this field goes through a relation."""
        return len(self.path) > 1

    @property
    def relation(self) -> Optional[str]:
        """Get the relation name if this is a relation field."""
        return self.path[0] if self.is_relation else None

    @property
    def field(self) -> str:
        """Get the terminal field name."""
        return self.path[-1]

    @property
    def full_path(self) -> str:
        """Get the full dot-notation path."""
        return '.'.join(self.path)

    def __repr__(self):
        return f"FieldRef({self.full_path!r})"


# =============================================================================
# Predicates
# =============================================================================

@dataclass
class Predicate:
    """
    A predicate binding a field to an expression.

    Predicates are the building blocks of filters.
    """
    field: FieldRef
    expr: Expr

    @classmethod
    def create(cls, field: str, value: Any) -> "Predicate":
        """Create a predicate from field string and value."""
        return cls(
            field=FieldRef.parse(field),
            expr=parse_expr(value)
        )

    def __repr__(self):
        return f"Predicate({self.field.full_path}: {self.expr})"


# =============================================================================
# Sort Specification
# =============================================================================

@dataclass
class SortSpec:
    """
    Sort specification for ordering results.

    Attributes:
        field: Field to sort by
        direction: 'asc' or 'desc'
        nulls: 'first' or 'last' (where to put nulls)
    """
    field: str
    direction: str = "asc"
    nulls: str = "last"

    @classmethod
    def parse(cls, s: str) -> "SortSpec":
        """Parse sort spec from string like 'field desc' or 'field asc nulls first'."""
        parts = s.lower().split()
        field = parts[0]
        direction = "asc"
        nulls = "last"

        for i, part in enumerate(parts[1:], 1):
            if part in ('asc', 'desc'):
                direction = part
            elif part == 'nulls' and i + 1 < len(parts):
                nulls = parts[i + 1]

        return cls(field=field, direction=direction, nulls=nulls)

    @classmethod
    def parse_list(cls, s: str) -> List["SortSpec"]:
        """Parse comma-separated sort specs."""
        return [cls.parse(part.strip()) for part in s.split(',')]

    def to_sql(self) -> str:
        """Convert to SQL ORDER BY clause fragment."""
        nulls_sql = "NULLS LAST" if self.nulls == "last" else "NULLS FIRST"
        return f"{self.field} {self.direction.upper()} {nulls_sql}"

    def __repr__(self):
        return f"SortSpec({self.field} {self.direction})"


# =============================================================================
# Compute Specification (for aggregates)
# =============================================================================

@dataclass
class ComputeSpec:
    """
    Aggregation function specification.

    Examples:
        ComputeSpec('count', 'count')           -> COUNT(*)
        ComputeSpec('total_stars', 'sum', 'stars') -> SUM(stars) AS total_stars
        ComputeSpec('newest', 'max', 'added')   -> MAX(added) AS newest
    """
    name: str          # Output column name
    func: str          # 'count', 'sum', 'avg', 'min', 'max', 'distinct'
    field: Optional[str] = None  # Field to aggregate (None for count())

    @classmethod
    def parse(cls, name: str, spec: Any) -> "ComputeSpec":
        """Parse compute spec from YAML value."""
        if spec is True or spec == 'count()' or spec == 'count':
            return cls(name=name, func='count')

        if isinstance(spec, str):
            # Parse function call syntax: sum(stars), avg(visit_count)
            import re
            match = re.match(r'(\w+)\((\w*)\)', spec)
            if match:
                func = match.group(1).lower()
                field = match.group(2) or None
                return cls(name=name, func=func, field=field)

            # Just a function name
            return cls(name=name, func=spec.lower())

        if isinstance(spec, dict):
            func = spec.get('func', 'count')
            field = spec.get('field')
            return cls(name=name, func=func, field=field)

        return cls(name=name, func='count')

    def to_sql(self) -> str:
        """Convert to SQL aggregate expression."""
        if self.func == 'count':
            return f"COUNT(*) AS {self.name}"
        elif self.func == 'distinct':
            return f"COUNT(DISTINCT {self.field}) AS {self.name}"
        elif self.func in ('sum', 'avg', 'min', 'max'):
            return f"{self.func.upper()}({self.field}) AS {self.name}"
        return f"COUNT(*) AS {self.name}"

    def __repr__(self):
        if self.field:
            return f"ComputeSpec({self.name}={self.func}({self.field}))"
        return f"ComputeSpec({self.name}={self.func}())"


# =============================================================================
# Group Specification
# =============================================================================

@dataclass
class GroupSpec:
    """
    Grouping specification for aggregate queries.

    Supports:
    - Simple field grouping: 'domain'
    - Temporal grouping: 'month(added)', 'year(published_at)'
    - Hierarchical grouping: 'hierarchy_level' for tags
    """
    field: str
    transform: Optional[str] = None  # 'month', 'year', 'day', 'week', etc.

    @classmethod
    def parse(cls, s: str) -> "GroupSpec":
        """Parse group spec from string like 'domain' or 'month(added)'."""
        import re
        match = re.match(r'(\w+)\((\w+)\)', s)
        if match:
            return cls(field=match.group(2), transform=match.group(1))
        return cls(field=s)

    @classmethod
    def parse_list(cls, spec: Any) -> List["GroupSpec"]:
        """Parse group spec from YAML value (string or list)."""
        if isinstance(spec, str):
            return [cls.parse(spec)]
        if isinstance(spec, list):
            return [cls.parse(s) if isinstance(s, str) else cls.parse(str(s)) for s in spec]
        return []

    def to_sql(self) -> str:
        """Convert to SQL GROUP BY expression."""
        if self.transform:
            if self.transform == 'month':
                return f"strftime('%Y-%m', {self.field})"
            elif self.transform == 'year':
                return f"strftime('%Y', {self.field})"
            elif self.transform == 'day':
                return f"strftime('%Y-%m-%d', {self.field})"
            elif self.transform == 'week':
                return f"strftime('%Y-%W', {self.field})"
        return self.field

    def __repr__(self):
        if self.transform:
            return f"GroupSpec({self.transform}({self.field}))"
        return f"GroupSpec({self.field})"


# =============================================================================
# Query
# =============================================================================

@dataclass
class Query:
    """
    A complete query against the btk database.

    This is the main AST node representing a full query with all its
    components: entity type, filters, sort, limit, grouping, and composition.
    """

    # Entity type determines what kind of results we return
    entity: EntityType = EntityType.BOOKMARK

    # Source: another view name to start from, or None for base table
    source: Optional[str] = None

    # Filter predicates (AND-ed together)
    predicates: List[Predicate] = field(default_factory=list)

    # Sorting
    sort: List[SortSpec] = field(default_factory=list)

    # Pagination
    limit: Optional[int] = None
    offset: Optional[int] = None

    # Aggregation (for STATS entity)
    group_by: List[GroupSpec] = field(default_factory=list)
    compute: List[ComputeSpec] = field(default_factory=list)
    having: List[Predicate] = field(default_factory=list)  # Post-group filter

    # Composition
    union: List[str] = field(default_factory=list)      # View names to union
    intersect: List[str] = field(default_factory=list)  # View names to intersect
    exclude: List[Predicate] = field(default_factory=list)  # Exclusion predicates

    # Parameters for parameterized queries
    params: Dict[str, Any] = field(default_factory=dict)
    param_defaults: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    name: Optional[str] = None
    description: Optional[str] = None

    @property
    def is_aggregate(self) -> bool:
        """Check if this is an aggregate query."""
        return self.entity == EntityType.STATS or bool(self.group_by)

    @property
    def is_composite(self) -> bool:
        """Check if this uses composition (union/intersect/source reference)."""
        return bool(self.union or self.intersect or self.source)

    def add_predicate(self, field: str, value: Any) -> "Query":
        """Add a predicate and return self for chaining."""
        self.predicates.append(Predicate.create(field, value))
        return self

    def add_sort(self, spec: str) -> "Query":
        """Add a sort specification and return self for chaining."""
        self.sort.extend(SortSpec.parse_list(spec))
        return self

    def with_limit(self, n: int) -> "Query":
        """Set limit and return self for chaining."""
        self.limit = n
        return self

    def with_offset(self, n: int) -> "Query":
        """Set offset and return self for chaining."""
        self.offset = n
        return self

    def __repr__(self):
        parts = [f"entity={self.entity.value}"]
        if self.source:
            parts.append(f"source={self.source!r}")
        if self.predicates:
            parts.append(f"predicates={len(self.predicates)}")
        if self.sort:
            parts.append(f"sort={self.sort}")
        if self.limit:
            parts.append(f"limit={self.limit}")
        if self.group_by:
            parts.append(f"group_by={self.group_by}")
        return f"Query({', '.join(parts)})"


# =============================================================================
# Query Builder (Fluent API)
# =============================================================================

class QueryBuilder:
    """
    Fluent builder for constructing queries programmatically.

    Example:
        query = (QueryBuilder()
            .from_entity('bookmarks')
            .filter('tags', 'any [ai/*, ml/*]')
            .filter('added', 'within 30 days')
            .sort('stars desc, added desc')
            .limit(100)
            .build())
    """

    def __init__(self):
        self._query = Query()

    def from_entity(self, entity: Union[str, EntityType]) -> "QueryBuilder":
        """Set the entity type."""
        if isinstance(entity, str):
            entity = EntityType.from_string(entity)
        self._query.entity = entity
        return self

    def from_view(self, view_name: str) -> "QueryBuilder":
        """Set source view (composition)."""
        self._query.source = view_name
        return self

    def filter(self, field: str, value: Any) -> "QueryBuilder":
        """Add a filter predicate."""
        self._query.predicates.append(Predicate.create(field, value))
        return self

    def sort(self, spec: str) -> "QueryBuilder":
        """Add sort specification(s)."""
        self._query.sort.extend(SortSpec.parse_list(spec))
        return self

    def limit(self, n: int) -> "QueryBuilder":
        """Set result limit."""
        self._query.limit = n
        return self

    def offset(self, n: int) -> "QueryBuilder":
        """Set result offset."""
        self._query.offset = n
        return self

    def group_by(self, *specs: str) -> "QueryBuilder":
        """Set grouping for aggregates."""
        for spec in specs:
            self._query.group_by.extend(GroupSpec.parse_list(spec))
        return self

    def compute(self, **specs: Any) -> "QueryBuilder":
        """Add compute specifications for aggregates."""
        for name, spec in specs.items():
            self._query.compute.append(ComputeSpec.parse(name, spec))
        return self

    def having(self, field: str, value: Any) -> "QueryBuilder":
        """Add a post-group filter."""
        self._query.having.append(Predicate.create(field, value))
        return self

    def union(self, *view_names: str) -> "QueryBuilder":
        """Set views to union with."""
        self._query.union.extend(view_names)
        return self

    def intersect(self, *view_names: str) -> "QueryBuilder":
        """Set views to intersect with."""
        self._query.intersect.extend(view_names)
        return self

    def exclude(self, field: str, value: Any) -> "QueryBuilder":
        """Add an exclusion predicate."""
        self._query.exclude.append(Predicate.create(field, value))
        return self

    def param(self, name: str, default: Any = None) -> "QueryBuilder":
        """Define a parameter with optional default."""
        if default is not None:
            self._query.param_defaults[name] = default
        return self

    def name(self, name: str) -> "QueryBuilder":
        """Set query name."""
        self._query.name = name
        return self

    def description(self, desc: str) -> "QueryBuilder":
        """Set query description."""
        self._query.description = desc
        return self

    def build(self) -> Query:
        """Build and return the query."""
        return self._query


def query() -> QueryBuilder:
    """Create a new query builder."""
    return QueryBuilder()
