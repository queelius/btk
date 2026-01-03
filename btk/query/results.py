"""
Result types for the btk query language.

Each entity type has its own result container. Results are generic
and support iteration, indexing, and serialization.

Result Types:
- QueryResult[T]: Generic container for any entity type
- BookmarkResult: Query results containing bookmarks
- TagResult: Query results containing tags
- StatsResult: Aggregate query results
- EdgeResult: Graph/relationship query results
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any, Dict, Generic, Iterator, List, Optional,
    TypeVar, Union, Callable
)

# Type variable for generic results
T = TypeVar('T')


# =============================================================================
# Base Result Container
# =============================================================================

@dataclass
class QueryResult(Generic[T]):
    """
    Generic result container for query results.

    Supports:
    - Iteration over items
    - Indexing
    - Length
    - Metadata about the query execution
    """
    items: List[T] = field(default_factory=list)
    total_count: Optional[int] = None  # Total before limit (for pagination)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __getitem__(self, idx: Union[int, slice]) -> Union[T, List[T]]:
        return self.items[idx]

    def __bool__(self) -> bool:
        return len(self.items) > 0

    @property
    def count(self) -> int:
        """Number of items in this result."""
        return len(self.items)

    @property
    def has_more(self) -> bool:
        """Check if there are more results beyond the limit."""
        if self.total_count is None:
            return False
        return len(self.items) < self.total_count

    def map(self, func: Callable[[T], Any]) -> "QueryResult":
        """Apply a function to each item."""
        return QueryResult(
            items=[func(item) for item in self.items],
            total_count=self.total_count,
            metadata=self.metadata
        )

    def filter(self, pred: Callable[[T], bool]) -> "QueryResult[T]":
        """Filter items by predicate."""
        filtered = [item for item in self.items if pred(item)]
        return QueryResult(
            items=filtered,
            total_count=len(filtered),
            metadata=self.metadata
        )

    def first(self) -> Optional[T]:
        """Get the first item, or None if empty."""
        return self.items[0] if self.items else None

    def last(self) -> Optional[T]:
        """Get the last item, or None if empty."""
        return self.items[-1] if self.items else None

    def to_list(self) -> List[T]:
        """Convert to plain list."""
        return list(self.items)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'items': [self._serialize_item(item) for item in self.items],
            'count': len(self.items),
            'total_count': self.total_count,
            'metadata': self.metadata
        }

    def _serialize_item(self, item: T) -> Any:
        """Serialize a single item (override in subclasses)."""
        if hasattr(item, 'to_dict'):
            return item.to_dict()
        if hasattr(item, '__dict__'):
            return item.__dict__
        return item

    @classmethod
    def empty(cls) -> "QueryResult[T]":
        """Create an empty result."""
        return cls(items=[], total_count=0)

    @classmethod
    def from_items(cls, items: List[T], total: Optional[int] = None) -> "QueryResult[T]":
        """Create result from item list."""
        return cls(items=items, total_count=total or len(items))


# =============================================================================
# Bookmark Results
# =============================================================================

@dataclass
class BookmarkItem:
    """
    A bookmark in query results.

    Wraps the actual Bookmark model with additional query-specific data
    like computed fields, overrides, or relevance scores.
    """
    bookmark: Any  # The actual Bookmark model
    score: Optional[float] = None  # Relevance/similarity score
    overrides: Dict[str, Any] = field(default_factory=dict)
    computed: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> int:
        return self.bookmark.id

    @property
    def url(self) -> str:
        return self.bookmark.url

    @property
    def title(self) -> str:
        return self.overrides.get('title', self.bookmark.title)

    @property
    def tags(self) -> List[str]:
        if self.bookmark.tags:
            return [t.name for t in self.bookmark.tags]
        return []

    def __getattr__(self, name: str) -> Any:
        # Check overrides first
        if name in self.overrides:
            return self.overrides[name]
        # Check computed fields
        if name in self.computed:
            return self.computed[name]
        # Fall back to bookmark
        return getattr(self.bookmark, name)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            'id': self.bookmark.id,
            'url': self.bookmark.url,
            'title': self.title,
            'description': self.bookmark.description or '',
            'added': self.bookmark.added.isoformat() if self.bookmark.added else None,
            'tags': self.tags,
            'stars': self.bookmark.stars,
            'pinned': self.bookmark.pinned,
            'archived': self.bookmark.archived,
            'visit_count': self.bookmark.visit_count,
        }

        # Add media fields if present
        if self.bookmark.media_type:
            result['media'] = {
                'type': self.bookmark.media_type,
                'source': self.bookmark.media_source,
                'id': self.bookmark.media_id,
                'author': self.bookmark.author_name,
            }

        # Add score if present
        if self.score is not None:
            result['score'] = self.score

        # Add computed fields
        result.update(self.computed)

        return result


class BookmarkResult(QueryResult[BookmarkItem]):
    """Result container for bookmark queries."""

    @classmethod
    def from_bookmarks(cls, bookmarks: List[Any], total: Optional[int] = None) -> "BookmarkResult":
        """Create result from raw Bookmark models."""
        items = [BookmarkItem(bookmark=b) for b in bookmarks]
        return cls(items=items, total_count=total or len(items))

    def urls(self) -> List[str]:
        """Get just the URLs."""
        return [item.url for item in self.items]

    def ids(self) -> List[int]:
        """Get just the IDs."""
        return [item.id for item in self.items]


# =============================================================================
# Tag Results
# =============================================================================

@dataclass
class TagItem:
    """
    A tag in query results.

    Includes the tag itself plus computed statistics like usage count.
    """
    tag: Any  # The actual Tag model
    usage_count: int = 0
    computed: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> int:
        return self.tag.id

    @property
    def name(self) -> str:
        return self.tag.name

    @property
    def description(self) -> Optional[str]:
        return self.tag.description

    @property
    def color(self) -> Optional[str]:
        return self.tag.color

    @property
    def hierarchy_level(self) -> int:
        """Depth in tag hierarchy (0 for root tags)."""
        return self.name.count('/')

    @property
    def parent_path(self) -> Optional[str]:
        """Parent tag path, or None for root tags."""
        if '/' not in self.name:
            return None
        return '/'.join(self.name.split('/')[:-1])

    @property
    def leaf_name(self) -> str:
        """Just the final component of the tag name."""
        return self.name.split('/')[-1]

    def __getattr__(self, name: str) -> Any:
        if name in self.computed:
            return self.computed[name]
        return getattr(self.tag, name)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            'id': self.tag.id,
            'name': self.name,
            'description': self.description,
            'color': self.color,
            'usage_count': self.usage_count,
            'hierarchy_level': self.hierarchy_level,
            'parent_path': self.parent_path,
            'leaf_name': self.leaf_name,
        }
        result.update(self.computed)
        return result


class TagResult(QueryResult[TagItem]):
    """Result container for tag queries."""

    @classmethod
    def from_tags(cls, tags: List[Any], usage_counts: Optional[Dict[int, int]] = None) -> "TagResult":
        """Create result from raw Tag models with optional usage counts."""
        usage_counts = usage_counts or {}
        items = [
            TagItem(tag=t, usage_count=usage_counts.get(t.id, 0))
            for t in tags
        ]
        return cls(items=items, total_count=len(items))

    def names(self) -> List[str]:
        """Get just the tag names."""
        return [item.name for item in self.items]

    def by_hierarchy(self) -> Dict[int, List[TagItem]]:
        """Group tags by hierarchy level."""
        result: Dict[int, List[TagItem]] = {}
        for item in self.items:
            level = item.hierarchy_level
            if level not in result:
                result[level] = []
            result[level].append(item)
        return result


# =============================================================================
# Stats Results (Aggregates)
# =============================================================================

@dataclass
class StatsRow:
    """
    A row in aggregate query results.

    Contains the grouping key(s) and computed aggregate values.
    """
    group_key: Dict[str, Any]  # Grouping field values
    values: Dict[str, Any]     # Aggregate values

    def __getitem__(self, key: str) -> Any:
        if key in self.group_key:
            return self.group_key[key]
        return self.values.get(key)

    def __getattr__(self, name: str) -> Any:
        if name in ('group_key', 'values'):
            return object.__getattribute__(self, name)
        return self[name]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {**self.group_key, **self.values}


class StatsResult(QueryResult[StatsRow]):
    """Result container for aggregate queries."""

    @property
    def columns(self) -> List[str]:
        """Get column names (group keys + value names)."""
        if not self.items:
            return []
        first = self.items[0]
        return list(first.group_key.keys()) + list(first.values.keys())

    def to_table(self) -> List[Dict[str, Any]]:
        """Convert to list of flat dictionaries."""
        return [row.to_dict() for row in self.items]

    def get_column(self, name: str) -> List[Any]:
        """Get all values for a column."""
        return [row[name] for row in self.items]

    def sum(self, column: str) -> float:
        """Sum a numeric column."""
        return sum(row[column] or 0 for row in self.items)

    def avg(self, column: str) -> float:
        """Average a numeric column."""
        values = [row[column] for row in self.items if row[column] is not None]
        return sum(values) / len(values) if values else 0


# =============================================================================
# Edge Results (Graphs)
# =============================================================================

@dataclass
class Edge:
    """
    An edge in a graph query result.

    Represents a relationship between two entities (e.g., tag co-occurrence).
    """
    source: Any           # Source entity (id or object)
    target: Any           # Target entity (id or object)
    weight: float = 1.0   # Edge weight
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        source_id = self.source if isinstance(self.source, (int, str)) else getattr(self.source, 'id', self.source)
        target_id = self.target if isinstance(self.target, (int, str)) else getattr(self.target, 'id', self.target)

        return {
            'source': source_id,
            'target': target_id,
            'weight': self.weight,
            **self.metadata
        }


class EdgeResult(QueryResult[Edge]):
    """Result container for graph/edge queries."""

    def to_adjacency_list(self) -> Dict[Any, List[tuple]]:
        """Convert to adjacency list format."""
        adj: Dict[Any, List[tuple]] = {}
        for edge in self.items:
            source = edge.source if isinstance(edge.source, (int, str)) else edge.source.id
            target = edge.target if isinstance(edge.target, (int, str)) else edge.target.id

            if source not in adj:
                adj[source] = []
            adj[source].append((target, edge.weight))

        return adj

    def to_networkx(self):
        """Convert to networkx graph (if available)."""
        try:
            import networkx as nx
            G = nx.DiGraph()
            for edge in self.items:
                source = edge.source if isinstance(edge.source, (int, str)) else edge.source.id
                target = edge.target if isinstance(edge.target, (int, str)) else edge.target.id
                G.add_edge(source, target, weight=edge.weight, **edge.metadata)
            return G
        except ImportError:
            raise ImportError("networkx is required for to_networkx()")

    def nodes(self) -> set:
        """Get all unique nodes."""
        result = set()
        for edge in self.items:
            result.add(edge.source if isinstance(edge.source, (int, str)) else edge.source.id)
            result.add(edge.target if isinstance(edge.target, (int, str)) else edge.target.id)
        return result


# =============================================================================
# Result Factory
# =============================================================================

def create_result(entity_type: str, items: List[Any], **kwargs) -> QueryResult:
    """
    Factory function to create appropriate result type.

    Args:
        entity_type: One of 'bookmarks', 'tags', 'stats', 'edges'
        items: List of result items
        **kwargs: Additional arguments for the result constructor
    """
    from .ast import EntityType

    if isinstance(entity_type, str):
        entity_type = EntityType.from_string(entity_type)

    if entity_type == EntityType.BOOKMARK:
        return BookmarkResult.from_bookmarks(items, **kwargs)
    elif entity_type == EntityType.TAG:
        return TagResult.from_tags(items, **kwargs)
    elif entity_type == EntityType.STATS:
        return StatsResult(items=items, **kwargs)
    elif entity_type == EntityType.EDGES:
        return EdgeResult(items=items, **kwargs)
    else:
        return QueryResult(items=items, **kwargs)
