"""
BTK View System - Composable Bookmark Views

A View is a first-class abstraction for selecting, transforming, and
presenting bookmarks. Views follow SICP principles:

1. Primitives: select, order, limit, override, group
2. Means of Combination: pipeline, union, intersect, difference
3. Means of Abstraction: named views, parameterized views
4. Closure: combining views yields a view

Example:
    from btk.views import ViewRegistry

    registry = ViewRegistry.from_yaml("btk-views.yaml")
    view = registry.get("blog_featured")
    result = view.evaluate(db)

    for bookmark in result.bookmarks:
        print(bookmark.title)
"""

from btk.views.core import (
    View,
    ViewResult,
    ViewContext,
    OverriddenBookmark,
)

from btk.views.predicates import (
    Predicate,
    TagsPredicate,
    FieldPredicate,
    TemporalPredicate,
    SearchPredicate,
    CompoundPredicate,
    IdsPredicate,
)

from btk.views.primitives import (
    SelectView,
    OrderView,
    LimitView,
    OffsetView,
    OverrideView,
    GroupView,
    AllView,
)

from btk.views.composites import (
    PipelineView,
    UnionView,
    IntersectView,
    DifferenceView,
    RefView,
)

from btk.views.registry import ViewRegistry
from btk.views.parser import parse_view, parse_views_file

__all__ = [
    # Core
    "View",
    "ViewResult",
    "ViewContext",
    "OverriddenBookmark",
    # Predicates
    "Predicate",
    "TagsPredicate",
    "FieldPredicate",
    "TemporalPredicate",
    "SearchPredicate",
    "CompoundPredicate",
    "IdsPredicate",
    # Primitives
    "SelectView",
    "OrderView",
    "LimitView",
    "OffsetView",
    "OverrideView",
    "GroupView",
    "AllView",
    # Composites
    "PipelineView",
    "UnionView",
    "IntersectView",
    "DifferenceView",
    "RefView",
    # Registry
    "ViewRegistry",
    # Parser
    "parse_view",
    "parse_views_file",
]
