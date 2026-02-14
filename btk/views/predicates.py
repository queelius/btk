"""
Predicate system for view selection.

Predicates are composable boolean functions over bookmarks.
They support both in-memory evaluation and SQL generation
for database-level optimization.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, List, Optional, Tuple
import re
import fnmatch

from btk.views.core import OverriddenBookmark


class Predicate(ABC):
    """
    Abstract base for predicates.

    A predicate is a function: Bookmark → bool
    Predicates can be combined with &, |, ~ operators.
    """

    @abstractmethod
    def matches(self, bookmark: OverriddenBookmark) -> bool:
        """Test if a bookmark matches this predicate."""
        pass

    def to_sql(self) -> Tuple[str, List[Any]]:
        """
        Convert to SQL WHERE clause.

        Returns:
            Tuple of (SQL string with ? placeholders, list of parameter values)

        Default implementation returns a tautology; subclasses should override
        for database-level filtering optimization.
        """
        return ("1=1", [])

    def __and__(self, other: "Predicate") -> "Predicate":
        """Logical AND: self & other"""
        return CompoundPredicate("all", [self, other])

    def __or__(self, other: "Predicate") -> "Predicate":
        """Logical OR: self | other"""
        return CompoundPredicate("any", [self, other])

    def __invert__(self) -> "Predicate":
        """Logical NOT: ~self"""
        return CompoundPredicate("not", [self])


@dataclass
class TruePredicate(Predicate):
    """Always matches."""

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        return True

    def to_sql(self) -> Tuple[str, List[Any]]:
        return ("1=1", [])


@dataclass
class FalsePredicate(Predicate):
    """Never matches."""

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        return False

    def to_sql(self) -> Tuple[str, List[Any]]:
        return ("1=0", [])


@dataclass
class TagsPredicate(Predicate):
    """
    Match bookmarks by tags.

    Modes:
    - 'all': bookmark must have ALL specified tags
    - 'any': bookmark must have ANY of the specified tags
    - 'none': bookmark must have NONE of the specified tags
    - 'match': at least one tag matches the glob pattern
    """
    tags: List[str]
    mode: str = "all"  # 'all', 'any', 'none', 'match'

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        # Get tag names from bookmark
        bookmark_tags = set()
        if hasattr(bookmark, "tags") and bookmark.tags:
            if isinstance(bookmark.tags, list):
                if bookmark.tags and isinstance(bookmark.tags[0], str):
                    bookmark_tags = set(bookmark.tags)
                else:
                    bookmark_tags = {t.name for t in bookmark.tags if hasattr(t, "name")}
            else:
                bookmark_tags = {t.name for t in bookmark.tags if hasattr(t, "name")}

        if self.mode == "all":
            return all(t in bookmark_tags for t in self.tags)
        elif self.mode == "any":
            return any(t in bookmark_tags for t in self.tags)
        elif self.mode == "none":
            if not self.tags:
                return len(bookmark_tags) == 0
            return not any(t in bookmark_tags for t in self.tags)
        elif self.mode == "match":
            # Glob pattern matching
            pattern = self.tags[0] if self.tags else "*"
            return any(fnmatch.fnmatch(t, pattern) for t in bookmark_tags)
        else:
            return False

    def to_sql(self) -> Tuple[str, List[Any]]:
        if not self.tags:
            if self.mode == "none":
                return ("NOT EXISTS (SELECT 1 FROM bookmark_tags bt WHERE bt.bookmark_id = bookmarks.id)", [])
            return ("1=1", [])

        if self.mode == "all":
            # All tags must be present
            placeholders = ", ".join("?" * len(self.tags))
            sql = f"""
                (SELECT COUNT(DISTINCT t.name) FROM bookmark_tags bt
                 JOIN tags t ON bt.tag_id = t.id
                 WHERE bt.bookmark_id = bookmarks.id AND t.name IN ({placeholders})) = ?
            """
            return (sql, self.tags + [len(self.tags)])

        elif self.mode == "any":
            placeholders = ", ".join("?" * len(self.tags))
            sql = f"""
                EXISTS (SELECT 1 FROM bookmark_tags bt
                        JOIN tags t ON bt.tag_id = t.id
                        WHERE bt.bookmark_id = bookmarks.id AND t.name IN ({placeholders}))
            """
            return (sql, self.tags)

        elif self.mode == "none":
            placeholders = ", ".join("?" * len(self.tags))
            sql = f"""
                NOT EXISTS (SELECT 1 FROM bookmark_tags bt
                            JOIN tags t ON bt.tag_id = t.id
                            WHERE bt.bookmark_id = bookmarks.id AND t.name IN ({placeholders}))
            """
            return (sql, self.tags)

        return ("1=1", [])


@dataclass
class FieldPredicate(Predicate):
    """
    Match bookmarks by field value.

    Operators:
    - 'eq', 'ne': equality
    - 'gt', 'gte', 'lt', 'lte': comparison
    - 'contains': substring match (case-insensitive)
    - 'prefix', 'suffix': string prefix/suffix
    - 'matches': glob pattern
    - 'regex': regular expression
    - 'is_null', 'is_not_null': null checks
    """
    field: str
    operator: str
    value: Any

    # Field name mapping for SQL
    FIELD_MAP = {
        "starred": "stars",
        "stars_count": "stars",
    }

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        # Get field value
        try:
            actual = getattr(bookmark, self.field)
        except AttributeError:
            actual = None

        op = self.operator
        expected = self.value

        if op == "eq":
            return actual == expected
        elif op == "ne":
            return actual != expected
        elif op == "gt":
            return actual is not None and actual > expected
        elif op == "gte":
            return actual is not None and actual >= expected
        elif op == "lt":
            return actual is not None and actual < expected
        elif op == "lte":
            return actual is not None and actual <= expected
        elif op == "contains":
            if actual is None:
                return False
            return str(expected).lower() in str(actual).lower()
        elif op == "prefix":
            if actual is None:
                return False
            return str(actual).lower().startswith(str(expected).lower())
        elif op == "suffix":
            if actual is None:
                return False
            return str(actual).lower().endswith(str(expected).lower())
        elif op == "matches":
            if actual is None:
                return False
            return fnmatch.fnmatch(str(actual), str(expected))
        elif op == "regex":
            if actual is None:
                return False
            return bool(re.search(str(expected), str(actual)))
        elif op == "is_null":
            return actual is None
        elif op == "is_not_null":
            return actual is not None
        else:
            return False

    def to_sql(self) -> Tuple[str, List[Any]]:
        field = self.FIELD_MAP.get(self.field, self.field)
        op = self.operator
        value = self.value

        if op == "eq":
            return (f"{field} = ?", [value])
        elif op == "ne":
            return (f"{field} != ?", [value])
        elif op == "gt":
            return (f"{field} > ?", [value])
        elif op == "gte":
            return (f"{field} >= ?", [value])
        elif op == "lt":
            return (f"{field} < ?", [value])
        elif op == "lte":
            return (f"{field} <= ?", [value])
        elif op == "contains":
            return (f"LOWER({field}) LIKE ?", [f"%{value.lower()}%"])
        elif op == "prefix":
            return (f"LOWER({field}) LIKE ?", [f"{value.lower()}%"])
        elif op == "suffix":
            return (f"LOWER({field}) LIKE ?", [f"%{value.lower()}"])
        elif op == "matches":
            # Convert glob to SQL LIKE
            sql_pattern = value.replace("*", "%").replace("?", "_")
            return (f"{field} LIKE ?", [sql_pattern])
        elif op == "is_null":
            return (f"{field} IS NULL", [])
        elif op == "is_not_null":
            return (f"{field} IS NOT NULL", [])
        else:
            return ("1=1", [])


@dataclass
class TemporalPredicate(Predicate):
    """
    Match bookmarks by date/time fields.

    Supports:
    - ISO date strings: "2024-01-01"
    - Relative expressions: "30 days ago", "1 week ago"
    """
    field: str  # 'added', 'visited', 'last_visited'
    after: Optional[str] = None
    before: Optional[str] = None
    within: Optional[str] = None

    def __post_init__(self):
        """Convert 'within' to an 'after' relative expression."""
        if self.within and not self.after:
            # "30 days" -> "30 days ago"
            w = self.within.strip()
            self.after = f"{w} ago" if "ago" not in w else w

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None

        # Relative time
        if "ago" in date_str:
            parts = date_str.split()
            try:
                amount = int(parts[0])
                unit = parts[1].rstrip("s")  # Remove plural 's'

                if unit == "day":
                    return datetime.now() - timedelta(days=amount)
                elif unit == "week":
                    return datetime.now() - timedelta(weeks=amount)
                elif unit == "month":
                    return datetime.now() - timedelta(days=amount * 30)
                elif unit == "year":
                    return datetime.now() - timedelta(days=amount * 365)
            except (ValueError, IndexError):
                pass

        # ISO date
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Simple date
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            pass

        return None

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        try:
            field_value = getattr(bookmark, self.field)
        except AttributeError:
            return False

        if field_value is None:
            return False

        # Convert to datetime if string
        if isinstance(field_value, str):
            field_value = self._parse_date(field_value)

        if not isinstance(field_value, datetime):
            return False

        if self.after:
            after_dt = self._parse_date(self.after)
            if after_dt and field_value < after_dt:
                return False

        if self.before:
            before_dt = self._parse_date(self.before)
            if before_dt and field_value >= before_dt:
                return False

        return True

    def to_sql(self) -> Tuple[str, List[Any]]:
        conditions = []
        params = []

        field = "last_visited" if self.field == "visited" else self.field

        if self.after:
            after_dt = self._parse_date(self.after)
            if after_dt:
                conditions.append(f"{field} >= ?")
                params.append(after_dt.isoformat())

        if self.before:
            before_dt = self._parse_date(self.before)
            if before_dt:
                conditions.append(f"{field} < ?")
                params.append(before_dt.isoformat())

        if not conditions:
            return ("1=1", [])

        return (" AND ".join(conditions), params)


@dataclass
class DomainPredicate(Predicate):
    """Match bookmarks by URL domain."""
    domains: List[str]
    mode: str = "any"  # 'any', 'none', 'match'

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        import re
        match = re.search(r"://([^/]+)", url)
        return match.group(1).lower() if match else ""

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        domain = self._extract_domain(bookmark.url or "")

        if self.mode == "any":
            return any(d.lower() in domain for d in self.domains)
        elif self.mode == "none":
            return not any(d.lower() in domain for d in self.domains)
        elif self.mode == "match":
            pattern = self.domains[0] if self.domains else "*"
            return fnmatch.fnmatch(domain, pattern.lower())
        return False

    def to_sql(self) -> Tuple[str, List[Any]]:
        if self.mode == "any":
            conditions = []
            params = []
            for domain in self.domains:
                conditions.append("url LIKE ?")
                params.append(f"%{domain}%")
            return ("(" + " OR ".join(conditions) + ")", params)
        elif self.mode == "none":
            conditions = []
            params = []
            for domain in self.domains:
                conditions.append("url NOT LIKE ?")
                params.append(f"%{domain}%")
            return ("(" + " AND ".join(conditions) + ")", params)
        return ("1=1", [])


@dataclass
class SearchPredicate(Predicate):
    """Full-text search predicate."""
    query: str
    fields: List[str] = field(default_factory=lambda: ["title", "description", "url"])

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        query_lower = self.query.lower()
        query_terms = query_lower.split()

        for field_name in self.fields:
            try:
                value = getattr(bookmark, field_name)
                if value:
                    value_lower = str(value).lower()
                    if all(term in value_lower for term in query_terms):
                        return True
            except AttributeError:
                continue

        return False

    def to_sql(self) -> Tuple[str, List[Any]]:
        # Simple LIKE-based search
        conditions = []
        params = []
        query_pattern = f"%{self.query}%"

        for field_name in self.fields:
            conditions.append(f"LOWER({field_name}) LIKE LOWER(?)")
            params.append(query_pattern)

        return ("(" + " OR ".join(conditions) + ")", params)


@dataclass
class IdsPredicate(Predicate):
    """Match bookmarks by explicit ID list."""
    ids: List[int]

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        return bookmark.id in self.ids

    def to_sql(self) -> Tuple[str, List[Any]]:
        if not self.ids:
            return ("1=0", [])
        placeholders = ", ".join("?" * len(self.ids))
        return (f"id IN ({placeholders})", list(self.ids))


@dataclass
class CompoundPredicate(Predicate):
    """
    Logical combination of predicates.

    Operators:
    - 'all': AND (all must match)
    - 'any': OR (at least one must match)
    - 'not': NOT (negate single predicate)
    """
    operator: str  # 'all', 'any', 'not'
    predicates: List[Predicate]

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        if self.operator == "all":
            return all(p.matches(bookmark) for p in self.predicates)
        elif self.operator == "any":
            return any(p.matches(bookmark) for p in self.predicates)
        elif self.operator == "not":
            if self.predicates:
                return not self.predicates[0].matches(bookmark)
            return True
        return False

    def to_sql(self) -> Tuple[str, List[Any]]:
        if not self.predicates:
            return ("1=1", [])

        sql_parts = []
        all_params = []

        for pred in self.predicates:
            sql, params = pred.to_sql()
            sql_parts.append(f"({sql})")
            all_params.extend(params)

        if self.operator == "all":
            return (" AND ".join(sql_parts), all_params)
        elif self.operator == "any":
            return (" OR ".join(sql_parts), all_params)
        elif self.operator == "not":
            return (f"NOT ({sql_parts[0]})", all_params)

        return ("1=1", [])


@dataclass
class CustomPredicate(Predicate):
    """
    Custom predicate with user-defined function.

    Useful for complex predicates that can't be expressed declaratively.
    """
    func: Callable[[OverriddenBookmark], bool]
    description: str = "custom predicate"

    def matches(self, bookmark: OverriddenBookmark) -> bool:
        return self.func(bookmark)

    def to_sql(self) -> Tuple[str, List[Any]]:
        # Custom predicates can't be converted to SQL
        return ("1=1", [])


# Predicate builder helpers
def tags(*tag_list: str, mode: str = "all") -> TagsPredicate:
    """Create a tags predicate."""
    return TagsPredicate(list(tag_list), mode)


def tags_any(*tag_list: str) -> TagsPredicate:
    """Create a tags predicate with 'any' mode."""
    return TagsPredicate(list(tag_list), "any")


def tags_none(*tag_list: str) -> TagsPredicate:
    """Create a tags predicate with 'none' mode."""
    return TagsPredicate(list(tag_list), "none")


def field_eq(field: str, value: Any) -> FieldPredicate:
    """Create an equality predicate."""
    return FieldPredicate(field, "eq", value)


def field_contains(field: str, value: str) -> FieldPredicate:
    """Create a contains predicate."""
    return FieldPredicate(field, "contains", value)


def added_after(date: str) -> TemporalPredicate:
    """Create a temporal predicate for added date."""
    return TemporalPredicate("added", after=date)


def added_before(date: str) -> TemporalPredicate:
    """Create a temporal predicate for added date."""
    return TemporalPredicate("added", before=date)


def domain(*domains: str) -> DomainPredicate:
    """Create a domain predicate."""
    return DomainPredicate(list(domains), "any")


def search(query: str) -> SearchPredicate:
    """Create a search predicate."""
    return SearchPredicate(query)


def ids(*id_list: int) -> IdsPredicate:
    """Create an IDs predicate."""
    return IdsPredicate(list(id_list))
