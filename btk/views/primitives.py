"""
Primitive view operations.

These are the building blocks from which all views are composed:
- AllView: All bookmarks (identity)
- SelectView: Filter by predicate
- OrderView: Sort bookmarks
- LimitView: Take first N
- OffsetView: Skip first N
- OverrideView: Apply metadata overrides
- GroupView: Group bookmarks by field
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from datetime import datetime
import re

from btk.views.core import (
    View,
    ViewResult,
    ViewContext,
    OverriddenBookmark,
    GroupedResult,
)
from btk.views.predicates import Predicate

if TYPE_CHECKING:
    from btk.db import Database


@dataclass
class AllView(View):
    """
    Select all bookmarks from the database.

    This is the identity view - the starting point for most view pipelines.
    """

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        bookmarks = db.all()
        return ViewResult.from_bookmarks(bookmarks)

    def __repr__(self) -> str:
        return "AllView()"


@dataclass
class SelectView(View):
    """
    Filter bookmarks by predicate.

    The predicate is evaluated against each bookmark, keeping only
    those that match.
    """
    predicate: Predicate

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        # Try to use SQL for efficiency
        sql, params = self.predicate.to_sql()

        if sql != "1=1":
            # Use database-level filtering
            try:
                bookmarks = db.query(f"SELECT * FROM bookmarks WHERE {sql}", params)
                wrapped = [OverriddenBookmark(b) for b in bookmarks]
                # Still apply predicate for complex conditions not in SQL
                result = [b for b in wrapped if self.predicate.matches(b)]
                return ViewResult(bookmarks=result)
            except Exception:
                # Fall back to in-memory filtering
                pass

        # In-memory filtering
        bookmarks = db.all()
        wrapped = [OverriddenBookmark(b) for b in bookmarks]
        result = [b for b in wrapped if self.predicate.matches(b)]
        return ViewResult(bookmarks=result)

    def __repr__(self) -> str:
        return f"SelectView({self.predicate!r})"


@dataclass
class SelectFromResultView(View):
    """
    Filter already-retrieved bookmarks by predicate.

    Used internally for pipeline composition.
    """
    predicate: Predicate
    source: ViewResult = field(default_factory=ViewResult.empty)

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        result = [b for b in self.source.bookmarks if self.predicate.matches(b)]
        return ViewResult(bookmarks=result, metadata=self.source.metadata)


@dataclass
class OrderSpec:
    """Specification for a single sort field."""
    field: str
    direction: str = "asc"  # 'asc' or 'desc'
    nulls: str = "last"  # 'first' or 'last'
    case_sensitive: bool = False


@dataclass
class OrderView(View):
    """
    Sort bookmarks by one or more fields.

    Supports:
    - Multiple sort keys
    - Ascending/descending
    - Null handling
    - Case sensitivity options
    """
    specs: List[OrderSpec]

    @classmethod
    def from_string(cls, spec_str: str) -> "OrderView":
        """
        Parse order specification from string.

        Examples:
            "added desc"
            "stars desc, title asc"
            "random"
        """
        if spec_str.strip().lower() == "random":
            return RandomOrderView()

        specs = []
        for part in spec_str.split(","):
            part = part.strip()
            if not part:
                continue

            tokens = part.split()
            field_name = tokens[0]
            direction = tokens[1].lower() if len(tokens) > 1 else "asc"

            if direction not in ("asc", "desc"):
                direction = "asc"

            specs.append(OrderSpec(field=field_name, direction=direction))

        return cls(specs)

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        # This view typically operates on existing results
        # When used standalone, it gets all bookmarks first
        bookmarks = db.all()
        wrapped = [OverriddenBookmark(b) for b in bookmarks]
        sorted_bookmarks = self._sort(wrapped)
        return ViewResult(bookmarks=sorted_bookmarks)

    def apply(self, result: ViewResult) -> ViewResult:
        """Apply sorting to an existing result."""
        sorted_bookmarks = self._sort(list(result.bookmarks))
        return ViewResult(bookmarks=sorted_bookmarks, metadata=result.metadata)

    def _sort(self, bookmarks: List[OverriddenBookmark]) -> List[OverriddenBookmark]:
        """Sort bookmarks according to specs."""
        if not self.specs:
            return bookmarks

        def sort_key(bookmark: OverriddenBookmark) -> tuple:
            keys = []
            for spec in self.specs:
                try:
                    value = getattr(bookmark, spec.field)
                except AttributeError:
                    value = None

                # Handle null
                if value is None:
                    if spec.nulls == "first":
                        null_key = (0,)
                    else:
                        null_key = (2,)
                    keys.append((null_key, None))
                    continue

                # Case handling for strings
                if isinstance(value, str) and not spec.case_sensitive:
                    value = value.lower()

                # Handle datetime
                if isinstance(value, datetime):
                    value = value.timestamp()

                # Reverse for descending
                if spec.direction == "desc":
                    if isinstance(value, (int, float)):
                        value = -value
                    elif isinstance(value, str):
                        # Reverse string comparison is tricky; use tuple
                        keys.append(((1,), value))
                        continue

                keys.append(((1,), value))

            return tuple(keys)

        # Custom comparison for mixed desc/asc
        def compare_key(b: OverriddenBookmark) -> tuple:
            keys = []
            for spec in self.specs:
                try:
                    value = getattr(b, spec.field)
                except AttributeError:
                    value = None

                # Null handling
                if value is None:
                    null_sort = 0 if spec.nulls == "first" else 2
                    keys.append((null_sort, ""))
                    continue

                # Normalize value
                if isinstance(value, datetime):
                    value = value.timestamp()
                elif isinstance(value, str) and not spec.case_sensitive:
                    value = value.lower()

                # Apply direction
                if spec.direction == "desc" and isinstance(value, (int, float)):
                    value = -value

                keys.append((1, value))

            return tuple(keys)

        return sorted(bookmarks, key=compare_key)

    def __repr__(self) -> str:
        specs_str = ", ".join(f"{s.field} {s.direction}" for s in self.specs)
        return f"OrderView([{specs_str}])"


@dataclass
class RandomOrderView(View):
    """Randomly shuffle bookmarks."""
    seed: Optional[int] = None

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        import random
        bookmarks = db.all()
        wrapped = [OverriddenBookmark(b) for b in bookmarks]
        if self.seed is not None:
            random.seed(self.seed)
        random.shuffle(wrapped)
        return ViewResult(bookmarks=wrapped)

    def apply(self, result: ViewResult) -> ViewResult:
        """Apply random shuffle to existing result."""
        import random
        bookmarks = list(result.bookmarks)
        if self.seed is not None:
            random.seed(self.seed)
        random.shuffle(bookmarks)
        return ViewResult(bookmarks=bookmarks, metadata=result.metadata)


@dataclass
class LimitView(View):
    """Take first N bookmarks."""
    limit: int

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        bookmarks = db.all()[:self.limit]
        return ViewResult.from_bookmarks(bookmarks)

    def apply(self, result: ViewResult) -> ViewResult:
        """Apply limit to existing result."""
        return ViewResult(
            bookmarks=result.bookmarks[:self.limit],
            metadata=result.metadata
        )

    def __repr__(self) -> str:
        return f"LimitView({self.limit})"


@dataclass
class OffsetView(View):
    """Skip first N bookmarks."""
    offset: int

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        bookmarks = db.all()[self.offset:]
        return ViewResult.from_bookmarks(bookmarks)

    def apply(self, result: ViewResult) -> ViewResult:
        """Apply offset to existing result."""
        return ViewResult(
            bookmarks=result.bookmarks[self.offset:],
            metadata=result.metadata
        )

    def __repr__(self) -> str:
        return f"OffsetView({self.offset})"


@dataclass
class SliceView(View):
    """Slice bookmarks with offset and limit."""
    offset: int = 0
    limit: Optional[int] = None

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        bookmarks = db.all()
        if self.limit is not None:
            bookmarks = bookmarks[self.offset:self.offset + self.limit]
        else:
            bookmarks = bookmarks[self.offset:]
        return ViewResult.from_bookmarks(bookmarks)

    def apply(self, result: ViewResult) -> ViewResult:
        """Apply slice to existing result."""
        if self.limit is not None:
            sliced = result.bookmarks[self.offset:self.offset + self.limit]
        else:
            sliced = result.bookmarks[self.offset:]
        return ViewResult(bookmarks=sliced, metadata=result.metadata)


@dataclass
class OverrideRule:
    """A single override rule."""
    match: Optional[Predicate]  # None means match all
    set_fields: Dict[str, Any]

    def applies_to(self, bookmark: OverriddenBookmark) -> bool:
        """Check if this rule applies to a bookmark."""
        if self.match is None:
            return True
        return self.match.matches(bookmark)

    def apply(self, bookmark: OverriddenBookmark) -> OverriddenBookmark:
        """Apply override to a bookmark."""
        if not self.applies_to(bookmark):
            return bookmark

        new_overrides = dict(bookmark.overrides)

        for key, value in self.set_fields.items():
            if key == "tags_add":
                # Append to existing tags
                existing = list(new_overrides.get("tags", []))
                if not existing and bookmark.original.tags:
                    existing = [t.name for t in bookmark.original.tags]
                existing.extend(value if isinstance(value, list) else [value])
                new_overrides["tags"] = existing
            elif key == "tags_remove":
                # Remove from existing tags
                existing = list(new_overrides.get("tags", []))
                if not existing and bookmark.original.tags:
                    existing = [t.name for t in bookmark.original.tags]
                to_remove = set(value if isinstance(value, list) else [value])
                new_overrides["tags"] = [t for t in existing if t not in to_remove]
            else:
                new_overrides[key] = value

        return OverriddenBookmark(bookmark.original, new_overrides)


@dataclass
class OverrideView(View):
    """
    Apply metadata overrides to bookmarks.

    Overrides are applied in order. Later rules win for the same field.
    Does not modify source data.
    """
    rules: List[OverrideRule]

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        bookmarks = db.all()
        wrapped = [OverriddenBookmark(b) for b in bookmarks]
        result = self._apply_overrides(wrapped)
        return ViewResult(bookmarks=result)

    def apply(self, result: ViewResult) -> ViewResult:
        """Apply overrides to existing result."""
        overridden = self._apply_overrides(list(result.bookmarks))
        # Filter out hidden bookmarks
        visible = [b for b in overridden if not b.is_hidden]
        return ViewResult(bookmarks=visible, metadata=result.metadata)

    def _apply_overrides(
        self,
        bookmarks: List[OverriddenBookmark]
    ) -> List[OverriddenBookmark]:
        """Apply all override rules to bookmarks."""
        result = []
        for bookmark in bookmarks:
            current = bookmark
            for rule in self.rules:
                current = rule.apply(current)
            result.append(current)
        return result

    def __repr__(self) -> str:
        return f"OverrideView({len(self.rules)} rules)"


@dataclass
class GroupSpec:
    """Specification for grouping."""
    field: str
    granularity: Optional[str] = None  # For temporal: 'year', 'month', 'week', 'day'
    strategy: str = "primary"  # For tags: 'primary', 'all'
    order: str = "asc"  # Group order: 'asc', 'desc', 'count'
    min_count: int = 0  # Minimum bookmarks per group


@dataclass
class GroupView(View):
    """
    Group bookmarks by field.

    Transforms flat list into grouped structure.
    """
    spec: GroupSpec

    def evaluate(
        self,
        db: "Database",
        context: Optional[ViewContext] = None
    ) -> ViewResult:
        bookmarks = db.all()
        wrapped = [OverriddenBookmark(b) for b in bookmarks]
        return self._group(wrapped)

    def apply(self, result: ViewResult) -> ViewResult:
        """Apply grouping to existing result."""
        return self._group(list(result.bookmarks))

    def _group(self, bookmarks: List[OverriddenBookmark]) -> ViewResult:
        """Group bookmarks according to spec."""
        groups: Dict[Any, List[OverriddenBookmark]] = {}

        for bookmark in bookmarks:
            keys = self._get_group_keys(bookmark)
            for key in keys:
                if key not in groups:
                    groups[key] = []
                groups[key].append(bookmark)

        # Filter by min_count
        if self.spec.min_count > 0:
            groups = {k: v for k, v in groups.items() if len(v) >= self.spec.min_count}

        # Sort groups
        if self.spec.order == "count":
            sorted_keys = sorted(groups.keys(), key=lambda k: -len(groups[k]))
        elif self.spec.order == "desc":
            sorted_keys = sorted(groups.keys(), reverse=True)
        else:
            sorted_keys = sorted(groups.keys())

        # Build grouped result
        grouped_results = []
        all_bookmarks = []

        for key in sorted_keys:
            group_bookmarks = groups[key]
            label = self._format_label(key)
            grouped_results.append(GroupedResult(
                key=key,
                label=label,
                bookmarks=group_bookmarks
            ))
            all_bookmarks.extend(group_bookmarks)

        return ViewResult(
            bookmarks=all_bookmarks,
            groups=grouped_results
        )

    def _get_group_keys(self, bookmark: OverriddenBookmark) -> List[Any]:
        """Get grouping key(s) for a bookmark."""
        field = self.spec.field

        if field == "tags":
            tags = []
            if hasattr(bookmark, "tags") and bookmark.tags:
                if isinstance(bookmark.tags, list):
                    if bookmark.tags and isinstance(bookmark.tags[0], str):
                        tags = bookmark.tags
                    else:
                        tags = [t.name for t in bookmark.tags if hasattr(t, "name")]
                else:
                    tags = [t.name for t in bookmark.tags if hasattr(t, "name")]

            if not tags:
                return ["Untagged"]

            if self.spec.strategy == "primary":
                return [tags[0]]
            else:  # 'all'
                return tags

        elif field == "domain":
            url = bookmark.url or ""
            match = re.search(r"://([^/]+)", url)
            return [match.group(1) if match else "Unknown"]

        elif field in ("added", "visited", "last_visited"):
            try:
                value = getattr(bookmark, field)
            except AttributeError:
                return ["Unknown"]

            if value is None:
                return ["Unknown"]

            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return ["Unknown"]

            if not isinstance(value, datetime):
                return ["Unknown"]

            granularity = self.spec.granularity or "month"

            if granularity == "year":
                return [value.strftime("%Y")]
            elif granularity == "month":
                return [value.strftime("%Y-%m")]
            elif granularity == "week":
                return [value.strftime("%Y-W%W")]
            elif granularity == "day":
                return [value.strftime("%Y-%m-%d")]
            else:
                return [value.strftime("%Y-%m")]

        else:
            # Generic field grouping
            try:
                value = getattr(bookmark, field)
                return [value if value is not None else "Unknown"]
            except AttributeError:
                return ["Unknown"]

    def _format_label(self, key: Any) -> str:
        """Format group key as human-readable label."""
        if key is None:
            return "Unknown"
        return str(key)

    def __repr__(self) -> str:
        return f"GroupView(by={self.spec.field!r})"
