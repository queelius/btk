"""
Composite view operations.

These combine multiple views using set operations and sequencing:
- PipelineView: Sequential composition (A >> B >> C)
- UnionView: Set union (A | B)
- IntersectView: Set intersection (A & B)
- DifferenceView: Set difference (A - B)
- RefView: Reference to named view in registry
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Set

from btk.views.core import (
    View,
    ViewResult,
    ViewContext,
    OverriddenBookmark,
)

if TYPE_CHECKING:
    from btk.db import Database


@dataclass
class PipelineView(View):
    """
    Sequential composition of views.

    Evaluates views in order, each receiving the output of the previous.
    This is the >> operator: A >> B >> C

    The pipeline respects closure: the result is a ViewResult just like
    any other view would produce.

    Example:
        select_tagged = SelectView(TagsPredicate(["python"]))
        order_recent = OrderView([OrderSpec("added", "desc")])
        top_10 = LimitView(10)

        pipeline = PipelineView([select_tagged, order_recent, top_10])
        # Equivalent to: select_tagged >> order_recent >> top_10
    """
    stages: List[View]

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        if not self.stages:
            from btk.views.primitives import AllView
            return AllView().evaluate(db, context)

        # Evaluate first stage
        result = self.stages[0].evaluate(db, context)

        # Apply subsequent stages
        for stage in self.stages[1:]:
            if hasattr(stage, "apply"):
                # Stage can transform existing result
                result = stage.apply(result)
            else:
                # Stage needs to re-evaluate with filtered set
                # Create a temporary view that filters to just these IDs
                from btk.views.primitives import SelectFromResultView

                ids = [b.id for b in result.bookmarks]
                if not ids:
                    return ViewResult.empty()

                # Use SelectFromResultView for in-memory filtering
                if hasattr(stage, "predicate"):
                    filtered = SelectFromResultView(
                        predicate=stage.predicate,
                        source=result
                    )
                    result = filtered.evaluate(db, context)
                else:
                    # Fallback: evaluate fresh and intersect
                    stage_result = stage.evaluate(db, context)
                    current_ids = {b.id for b in result.bookmarks}
                    result = ViewResult(
                        bookmarks=[b for b in stage_result.bookmarks if b.id in current_ids],
                        metadata={**result.metadata, **stage_result.metadata}
                    )

        return result

    def __rshift__(self, other: View) -> "PipelineView":
        """Extend pipeline: self >> other."""
        return PipelineView(self.stages + [other])

    def __repr__(self) -> str:
        stages_str = " >> ".join(repr(s) for s in self.stages)
        return f"Pipeline({stages_str})"


@dataclass
class UnionView(View):
    """
    Set union of multiple views.

    Returns bookmarks that appear in ANY of the source views.
    This is the | operator: A | B | C

    Duplicates are eliminated by bookmark ID.

    Example:
        starred = SelectView(FieldPredicate("stars", "gt", 0))
        pinned = SelectView(FieldPredicate("pinned", "eq", True))

        important = UnionView([starred, pinned])
        # Equivalent to: starred | pinned
    """
    views: List[View]

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        if not self.views:
            return ViewResult.empty()

        seen_ids: Set[int] = set()
        all_bookmarks: List[OverriddenBookmark] = []

        for view in self.views:
            result = view.evaluate(db, context)
            for bookmark in result.bookmarks:
                if bookmark.id not in seen_ids:
                    seen_ids.add(bookmark.id)
                    all_bookmarks.append(bookmark)

        return ViewResult(bookmarks=all_bookmarks)

    def __or__(self, other: View) -> "UnionView":
        """Extend union: self | other."""
        if isinstance(other, UnionView):
            return UnionView(self.views + other.views)
        return UnionView(self.views + [other])

    def __repr__(self) -> str:
        return f"Union({len(self.views)} views)"


@dataclass
class IntersectView(View):
    """
    Set intersection of multiple views.

    Returns bookmarks that appear in ALL source views.
    This is the & operator: A & B & C

    Example:
        tagged_python = SelectView(TagsPredicate(["python"]))
        starred = SelectView(FieldPredicate("stars", "gt", 0))

        python_favorites = IntersectView([tagged_python, starred])
        # Equivalent to: tagged_python & starred
    """
    views: List[View]

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        if not self.views:
            return ViewResult.empty()

        # Evaluate all views
        results = [view.evaluate(db, context) for view in self.views]

        if not results:
            return ViewResult.empty()

        # Start with first result's IDs
        common_ids = {b.id for b in results[0].bookmarks}

        # Intersect with remaining results
        for result in results[1:]:
            result_ids = {b.id for b in result.bookmarks}
            common_ids &= result_ids

        if not common_ids:
            return ViewResult.empty()

        # Return bookmarks from first result that are in common
        # (preserving any overrides from first view)
        bookmarks = [b for b in results[0].bookmarks if b.id in common_ids]
        return ViewResult(bookmarks=bookmarks)

    def __and__(self, other: View) -> "IntersectView":
        """Extend intersection: self & other."""
        if isinstance(other, IntersectView):
            return IntersectView(self.views + other.views)
        return IntersectView(self.views + [other])

    def __repr__(self) -> str:
        return f"Intersect({len(self.views)} views)"


@dataclass
class DifferenceView(View):
    """
    Set difference of views.

    Returns bookmarks in the primary view but NOT in any excluded views.
    This is the - operator: A - B - C

    Example:
        all_python = SelectView(TagsPredicate(["python"]))
        archived = SelectView(FieldPredicate("archived", "eq", True))

        active_python = DifferenceView(all_python, [archived])
        # Equivalent to: all_python - archived
    """
    primary: View
    excluded: List[View]

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        # Evaluate primary view
        primary_result = self.primary.evaluate(db, context)

        if not self.excluded:
            return primary_result

        # Collect IDs to exclude
        excluded_ids: Set[int] = set()
        for view in self.excluded:
            result = view.evaluate(db, context)
            excluded_ids.update(b.id for b in result.bookmarks)

        # Filter primary result
        bookmarks = [b for b in primary_result.bookmarks if b.id not in excluded_ids]
        return ViewResult(bookmarks=bookmarks, metadata=primary_result.metadata)

    def __sub__(self, other: View) -> "DifferenceView":
        """Extend difference: self - other."""
        if isinstance(other, DifferenceView):
            return DifferenceView(self.primary, self.excluded + [other.primary] + other.excluded)
        return DifferenceView(self.primary, self.excluded + [other])

    def __repr__(self) -> str:
        return f"Difference(primary={self.primary!r}, excluded={len(self.excluded)})"


@dataclass
class RefView(View):
    """
    Reference to a named view in the registry.

    Allows views to reference other views by name, enabling:
    - Reusable view definitions
    - Composition of named views
    - Parameterized view invocation

    Example YAML:
        blog_featured:
          extends: blog_posts
          select:
            field: stars
            op: gt
            value: 3

    The 'extends' creates a RefView to 'blog_posts'.
    """
    name: str
    params: dict = field(default_factory=dict)

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        if context is None or context.registry is None:
            raise ValueError(f"Cannot resolve view reference '{self.name}': no registry in context")

        # Resolve the referenced view
        view = context.registry.get(self.name)

        # Create context with parameters
        if self.params:
            context = context.with_params(**self.params)

        return view.evaluate(db, context)

    def __repr__(self) -> str:
        if self.params:
            return f"RefView({self.name!r}, params={self.params})"
        return f"RefView({self.name!r})"


@dataclass
class ConditionalView(View):
    """
    Conditional view selection.

    Evaluates a condition and returns one of two views.
    Useful for parameterized views that change behavior based on input.

    Example:
        view = ConditionalView(
            condition=lambda ctx: ctx.resolve_param("include_archived", False),
            if_true=all_view,
            if_false=non_archived_view
        )
    """
    condition: callable  # ViewContext -> bool
    if_true: View
    if_false: View

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        context = context or ViewContext()

        if self.condition(context):
            return self.if_true.evaluate(db, context)
        else:
            return self.if_false.evaluate(db, context)

    def __repr__(self) -> str:
        return f"ConditionalView(if_true={self.if_true!r}, if_false={self.if_false!r})"


@dataclass
class FlattenView(View):
    """
    Flatten grouped results back to a flat list.

    Useful when you want to apply grouping for ordering purposes
    but need a flat result.
    """
    source: View

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        result = self.source.evaluate(db, context)

        # If already flat, return as-is
        if not result.is_grouped:
            return result

        # Flatten groups in order
        all_bookmarks = []
        for group in result.groups:
            all_bookmarks.extend(group.bookmarks)

        return ViewResult(
            bookmarks=all_bookmarks,
            metadata=result.metadata
        )

    def __repr__(self) -> str:
        return f"FlattenView({self.source!r})"
