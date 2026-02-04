"""
Core view abstractions.

This module defines the fundamental types for the view system:
- View: Abstract base class for all views
- ViewResult: The result of evaluating a view
- ViewContext: Execution context with parameters and registry
- OverriddenBookmark: A bookmark with view-local field overrides
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterator,
    List,
    Optional,
)
from datetime import datetime

if TYPE_CHECKING:
    from btk.db import Database
    from btk.models import Bookmark
    from btk.views.registry import ViewRegistry


@dataclass
class ViewContext:
    """
    Execution context for view evaluation.

    Contains:
    - Parameter bindings for parameterized views
    - Reference to the view registry for resolving named views
    - Evaluation options (e.g., whether to apply defaults)
    """
    params: Dict[str, Any] = field(default_factory=dict)
    registry: Optional["ViewRegistry"] = None
    apply_defaults: bool = True
    now: datetime = field(default_factory=datetime.now)

    def with_params(self, **params) -> "ViewContext":
        """Create a new context with additional parameters."""
        new_params = {**self.params, **params}
        return ViewContext(
            params=new_params,
            registry=self.registry,
            apply_defaults=self.apply_defaults,
            now=self.now,
        )

    def resolve_param(self, key: str, default: Optional[Any] = None) -> Any:
        """Resolve a parameter value."""
        return self.params.get(key, default)

    def resolve_template(self, template: str) -> str:
        """
        Resolve template variables in a string.

        Supports: {{ param_name }}, {{ now }}, {{ today }}, {{ year }}
        """
        if "{{" not in template:
            return template

        import re

        def replace(match):
            expr = match.group(1).strip()

            # Built-in variables
            if expr == "now":
                return self.now.isoformat()
            elif expr == "today":
                return self.now.strftime("%Y-%m-%d")
            elif expr == "year":
                return str(self.now.year)
            elif expr == "month":
                return str(self.now.month)

            # Relative time expressions like "30 days ago"
            if "days ago" in expr:
                try:
                    days = int(expr.split()[0])
                    from datetime import timedelta
                    date = self.now - timedelta(days=days)
                    return date.strftime("%Y-%m-%d")
                except (ValueError, IndexError):
                    pass

            # Parameter lookup
            if expr in self.params:
                return str(self.params[expr])

            # Nested parameter access (params.key)
            if expr.startswith("params."):
                key = expr[7:]
                if key in self.params:
                    return str(self.params[key])

            return match.group(0)  # Leave unresolved

        return re.sub(r"\{\{\s*(.+?)\s*\}\}", replace, template)


@dataclass
class GroupedResult:
    """A group of bookmarks with a label."""
    key: Any
    label: str
    bookmarks: List["OverriddenBookmark"]

    def __len__(self) -> int:
        return len(self.bookmarks)

    def __iter__(self) -> Iterator["OverriddenBookmark"]:
        return iter(self.bookmarks)


@dataclass
class ViewResult:
    """
    Result of evaluating a view.

    Contains either a flat list of bookmarks or grouped results.
    Bookmarks may have view-local overrides applied.
    """
    bookmarks: List["OverriddenBookmark"] = field(default_factory=list)
    groups: Optional[List[GroupedResult]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_grouped(self) -> bool:
        """Check if result is grouped."""
        return self.groups is not None

    @property
    def count(self) -> int:
        """Total number of bookmarks."""
        return len(self.bookmarks)

    def __len__(self) -> int:
        return self.count

    def __iter__(self) -> Iterator["OverriddenBookmark"]:
        return iter(self.bookmarks)

    @classmethod
    def from_bookmarks(
        cls,
        bookmarks: List["Bookmark"],
        metadata: Optional[Dict[str, Any]] = None
    ) -> "ViewResult":
        """Create result from raw bookmarks (wrapping in OverriddenBookmark)."""
        wrapped = [OverriddenBookmark(b) for b in bookmarks]
        return cls(bookmarks=wrapped, metadata=metadata or {})

    @classmethod
    def empty(cls) -> "ViewResult":
        """Create an empty result."""
        return cls(bookmarks=[], metadata={})


class OverriddenBookmark:
    """
    A bookmark with view-local field overrides.

    Provides transparent access to original bookmark fields while
    allowing views to override specific fields without modifying
    the source data.

    Example:
        ob = OverriddenBookmark(bookmark, {"title": "Custom Title"})
        ob.title  # Returns "Custom Title"
        ob.url    # Returns original bookmark.url
        ob.original.title  # Returns original title
    """

    __slots__ = ("_original", "_overrides", "_extra")

    def __init__(
        self,
        original: "Bookmark",
        overrides: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        object.__setattr__(self, "_original", original)
        object.__setattr__(self, "_overrides", overrides or {})
        object.__setattr__(self, "_extra", extra or {})

    @property
    def original(self) -> "Bookmark":
        """Access the original, unmodified bookmark."""
        return self._original

    @property
    def overrides(self) -> Dict[str, Any]:
        """Get all active overrides."""
        return self._overrides

    @property
    def id(self) -> int:
        """Bookmark ID (never overridden)."""
        return self._original.id

    @property
    def is_hidden(self) -> bool:
        """Check if bookmark is marked hidden by overrides."""
        return self._overrides.get("hidden", False)

    def __getattr__(self, name: str) -> Any:
        # Check overrides first
        if name in self._overrides:
            return self._overrides[name]
        # Check extra computed fields
        if name in self._extra:
            return self._extra[name]
        # Fall back to original
        return getattr(self._original, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._overrides[name] = value

    def with_override(self, **kwargs) -> "OverriddenBookmark":
        """Create a new OverriddenBookmark with additional overrides."""
        new_overrides = {**self._overrides, **kwargs}
        return OverriddenBookmark(self._original, new_overrides, self._extra)

    def with_extra(self, **kwargs) -> "OverriddenBookmark":
        """Create a new OverriddenBookmark with additional extra fields."""
        new_extra = {**self._extra, **kwargs}
        return OverriddenBookmark(self._original, self._overrides, new_extra)

    def get(self, name: str, default: Optional[Any] = None) -> Any:
        """Get a field value with optional default."""
        try:
            return getattr(self, name)
        except AttributeError:
            return default

    def to_dict(self, include_overrides: bool = True) -> Dict[str, Any]:
        """Convert to dictionary."""
        # Start with original fields
        result = {
            "id": self._original.id,
            "url": self._original.url,
            "title": self._original.title,
            "description": self._original.description,
            "added": self._original.added.isoformat() if self._original.added else None,
            "tags": [t.name for t in self._original.tags] if self._original.tags else [],
            "stars": self._original.stars,
            "pinned": self._original.pinned,
            "archived": self._original.archived,
            "visit_count": self._original.visit_count,
            "reachable": self._original.reachable,
        }

        # Apply overrides
        if include_overrides:
            for key, value in self._overrides.items():
                result[key] = value
            for key, value in self._extra.items():
                result[key] = value

        return result

    def __repr__(self) -> str:
        overrides_str = f", overrides={self._overrides}" if self._overrides else ""
        return f"OverriddenBookmark(id={self.id}, url={self.url!r}{overrides_str})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, OverriddenBookmark):
            return self.id == other.id
        if hasattr(other, "id"):
            return self.id == other.id
        return False

    def __hash__(self) -> int:
        return hash(self.id)


class View(ABC):
    """
    Abstract base class for all views.

    A View is a composable function: Database → ViewResult

    Views support algebraic composition via operators:
    - view_a | view_b   → Union (A ∪ B)
    - view_a & view_b   → Intersection (A ∩ B)
    - view_a - view_b   → Difference (A - B)
    - view_a >> view_b  → Pipeline (A then B)

    Subclasses must implement evaluate().
    """

    @abstractmethod
    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        """
        Evaluate this view against a database.

        Args:
            db: The database to query
            context: Optional evaluation context with parameters

        Returns:
            ViewResult containing matching bookmarks
        """
        pass

    def __or__(self, other: "View") -> "View":
        """Union: self | other → bookmarks in either view."""
        from btk.views.composites import UnionView
        return UnionView([self, other])

    def __and__(self, other: "View") -> "View":
        """Intersection: self & other → bookmarks in both views."""
        from btk.views.composites import IntersectView
        return IntersectView([self, other])

    def __sub__(self, other: "View") -> "View":
        """Difference: self - other → bookmarks in self but not other."""
        from btk.views.composites import DifferenceView
        return DifferenceView(self, [other])

    def __rshift__(self, other: "View") -> "View":
        """Pipeline: self >> other → apply self, then apply other to result."""
        from btk.views.composites import PipelineView
        return PipelineView([self, other])

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
