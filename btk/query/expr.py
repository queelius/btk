"""
Expression AST and parser for the btk query language.

Expressions are the predicates used in filters. They support:
- Comparisons: >= 10, < 100, != "foo"
- Temporal: within 30 days, before 2024-01-01, after 1 week ago
- Collections: any [a, b], all [x, y], none [z], [a, b] (implicit any)
- String ops: contains "foo", starts_with "bar", matches "regex", under "path/"
- Existence: exists, missing, has [field1, field2]
- Literals: direct value equality

Example YAML usage:
    filter:
        stars: >= 3
        added: within 30 days
        tags: any [ai/*, ml/*]
        title: contains "neural"
        content.has: [transcript, thumbnail]
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, List, Optional, Union, Callable
import re


# =============================================================================
# Expression AST
# =============================================================================

class Expr(ABC):
    """Base class for all expressions."""

    @abstractmethod
    def evaluate(self, value: Any) -> bool:
        """Evaluate this expression against a value."""
        pass

    @abstractmethod
    def to_sql(self, field: str) -> tuple[str, list]:
        """
        Convert to SQL WHERE clause fragment.

        Returns:
            Tuple of (SQL string with ? placeholders, list of parameters)
        """
        pass


@dataclass
class Literal(Expr):
    """Direct value equality."""
    value: Any

    def evaluate(self, value: Any) -> bool:
        if self.value is None:
            return value is None
        return value == self.value

    def to_sql(self, field: str) -> tuple[str, list]:
        if self.value is None:
            return f"{field} IS NULL", []
        return f"{field} = ?", [self.value]

    def __repr__(self):
        return f"Literal({self.value!r})"


@dataclass
class Comparison(Expr):
    """Comparison expression: >=, <=, >, <, =, !="""
    op: str
    value: Any

    _OP_MAP = {
        '>=': ('>=', lambda a, b: a is not None and a >= b),
        '<=': ('<=', lambda a, b: a is not None and a <= b),
        '>': ('>', lambda a, b: a is not None and a > b),
        '<': ('<', lambda a, b: a is not None and a < b),
        '=': ('=', lambda a, b: a == b),
        '==': ('=', lambda a, b: a == b),
        '!=': ('!=', lambda a, b: a != b),
        '<>': ('!=', lambda a, b: a != b),
    }

    def evaluate(self, value: Any) -> bool:
        if self.op not in self._OP_MAP:
            return False
        _, func = self._OP_MAP[self.op]
        return func(value, self.value)

    def to_sql(self, field: str) -> tuple[str, list]:
        sql_op, _ = self._OP_MAP.get(self.op, ('=', None))
        return f"{field} {sql_op} ?", [self.value]

    def __repr__(self):
        return f"Comparison({self.op} {self.value!r})"


@dataclass
class Temporal(Expr):
    """
    Temporal expression for date/time fields.

    Supports:
    - within N days/weeks/months/years
    - before DATE
    - after DATE
    - between DATE and DATE
    """
    op: str  # 'within', 'before', 'after', 'between'
    value: Union[timedelta, datetime, str]
    end_value: Optional[Union[datetime, str]] = None

    def _resolve_datetime(self, v: Union[timedelta, datetime, str], now: datetime) -> datetime:
        """Resolve a value to a datetime."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, timedelta):
            return now - v
        if isinstance(v, str):
            return parse_date(v)
        return now

    def evaluate(self, value: Any) -> bool:
        if value is None:
            return False

        now = datetime.now()

        # Convert value to datetime if needed
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return False

        if not isinstance(value, datetime):
            return False

        if self.op == 'within':
            if isinstance(self.value, timedelta):
                threshold = now - self.value
            else:
                threshold = self._resolve_datetime(self.value, now)
            return value >= threshold

        elif self.op == 'before':
            threshold = self._resolve_datetime(self.value, now)
            return value < threshold

        elif self.op == 'after':
            threshold = self._resolve_datetime(self.value, now)
            return value > threshold

        elif self.op == 'between':
            start = self._resolve_datetime(self.value, now)
            end = self._resolve_datetime(self.end_value, now)
            return start <= value <= end

        return False

    def to_sql(self, field: str) -> tuple[str, list]:
        now = datetime.now()

        if self.op == 'within':
            if isinstance(self.value, timedelta):
                threshold = now - self.value
            else:
                threshold = self._resolve_datetime(self.value, now)
            return f"{field} >= ?", [threshold.isoformat()]

        elif self.op == 'before':
            threshold = self._resolve_datetime(self.value, now)
            return f"{field} < ?", [threshold.isoformat()]

        elif self.op == 'after':
            threshold = self._resolve_datetime(self.value, now)
            return f"{field} > ?", [threshold.isoformat()]

        elif self.op == 'between':
            start = self._resolve_datetime(self.value, now)
            end = self._resolve_datetime(self.end_value, now)
            return f"{field} BETWEEN ? AND ?", [start.isoformat(), end.isoformat()]

        return "1=1", []

    def __repr__(self):
        if self.end_value:
            return f"Temporal({self.op} {self.value!r} and {self.end_value!r})"
        return f"Temporal({self.op} {self.value!r})"


@dataclass
class Collection(Expr):
    """
    Collection expression: any, all, none.

    - any [a, b, c]: matches if value matches any item
    - all [a, b, c]: matches if value matches all items (for multi-value fields)
    - none [a, b, c]: matches if value matches no items
    """
    op: str  # 'any', 'all', 'none'
    values: List[Any]

    def _match_value(self, actual: Any, pattern: Any) -> bool:
        """Check if actual value matches pattern (supports glob patterns)."""
        if isinstance(pattern, str) and ('*' in pattern or '?' in pattern):
            # Glob pattern matching
            import fnmatch
            if isinstance(actual, str):
                return fnmatch.fnmatch(actual, pattern)
            elif isinstance(actual, (list, set, tuple)):
                return any(fnmatch.fnmatch(str(a), pattern) for a in actual)
            return False

        # Direct equality or containment
        if isinstance(actual, (list, set, tuple)):
            return pattern in actual
        return actual == pattern

    def evaluate(self, value: Any) -> bool:
        if self.op == 'any':
            return any(self._match_value(value, p) for p in self.values)
        elif self.op == 'all':
            return all(self._match_value(value, p) for p in self.values)
        elif self.op == 'none':
            return not any(self._match_value(value, p) for p in self.values)
        return False

    def to_sql(self, field: str) -> tuple[str, list]:
        # For simple cases without globs
        has_globs = any('*' in str(v) or '?' in str(v) for v in self.values)

        if has_globs:
            # Use LIKE for glob patterns
            if self.op == 'any':
                conditions = []
                params = []
                for v in self.values:
                    if '*' in str(v) or '?' in str(v):
                        # Convert glob to SQL LIKE
                        like_pattern = str(v).replace('*', '%').replace('?', '_')
                        conditions.append(f"{field} LIKE ?")
                        params.append(like_pattern)
                    else:
                        conditions.append(f"{field} = ?")
                        params.append(v)
                return f"({' OR '.join(conditions)})", params

            elif self.op == 'none':
                conditions = []
                params = []
                for v in self.values:
                    if '*' in str(v) or '?' in str(v):
                        like_pattern = str(v).replace('*', '%').replace('?', '_')
                        conditions.append(f"{field} NOT LIKE ?")
                        params.append(like_pattern)
                    else:
                        conditions.append(f"{field} != ?")
                        params.append(v)
                return f"({' AND '.join(conditions)})", params

        else:
            # Simple IN/NOT IN
            placeholders = ', '.join('?' * len(self.values))
            if self.op == 'any':
                return f"{field} IN ({placeholders})", self.values
            elif self.op == 'none':
                return f"{field} NOT IN ({placeholders})", self.values

        # 'all' is complex for SQL, return tautology and filter in-memory
        return "1=1", []

    def __repr__(self):
        return f"Collection({self.op} {self.values!r})"


@dataclass
class StringOp(Expr):
    """
    String operation expression.

    - contains "substr": substring match
    - starts_with "prefix": prefix match
    - ends_with "suffix": suffix match
    - matches "regex": regex match
    - under "path/": hierarchical containment (for tags)
    """
    op: str  # 'contains', 'starts_with', 'ends_with', 'matches', 'under'
    pattern: str
    case_sensitive: bool = False

    def evaluate(self, value: Any) -> bool:
        if value is None:
            return False

        s = str(value)
        p = self.pattern

        if not self.case_sensitive:
            s = s.lower()
            p = p.lower()

        if self.op == 'contains':
            return p in s
        elif self.op == 'starts_with':
            return s.startswith(p)
        elif self.op == 'ends_with':
            return s.endswith(p)
        elif self.op == 'matches':
            try:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(self.pattern, str(value), flags))
            except re.error:
                return False
        elif self.op == 'under':
            # Hierarchical: value starts with pattern or equals pattern
            # For tags like "ai/ml/transformers" under "ai/"
            path = p.rstrip('/')
            return s == path or s.startswith(path + '/')

        return False

    def to_sql(self, field: str) -> tuple[str, list]:
        if self.op == 'contains':
            if self.case_sensitive:
                return f"{field} LIKE ?", [f"%{self.pattern}%"]
            return f"LOWER({field}) LIKE LOWER(?)", [f"%{self.pattern}%"]

        elif self.op == 'starts_with':
            if self.case_sensitive:
                return f"{field} LIKE ?", [f"{self.pattern}%"]
            return f"LOWER({field}) LIKE LOWER(?)", [f"{self.pattern}%"]

        elif self.op == 'ends_with':
            if self.case_sensitive:
                return f"{field} LIKE ?", [f"%{self.pattern}"]
            return f"LOWER({field}) LIKE LOWER(?)", [f"%{self.pattern}"]

        elif self.op == 'under':
            # Hierarchical match: exact or prefix with /
            path = self.pattern.rstrip('/')
            return f"({field} = ? OR {field} LIKE ?)", [path, f"{path}/%"]

        # 'matches' (regex) not supported in SQL, filter in-memory
        return "1=1", []

    def __repr__(self):
        return f"StringOp({self.op} {self.pattern!r})"


@dataclass
class Existence(Expr):
    """
    Existence check expression.

    - exists: field is not null/empty
    - missing: field is null/empty
    - has [field1, field2]: related entity has these fields populated
    """
    exists: bool
    fields: Optional[List[str]] = None  # For 'has [...]'

    def evaluate(self, value: Any) -> bool:
        if self.fields:
            # Check if value (a dict or object) has these fields populated
            if isinstance(value, dict):
                checks = [bool(value.get(f)) for f in self.fields]
            elif hasattr(value, '__dict__'):
                checks = [bool(getattr(value, f, None)) for f in self.fields]
            else:
                return not self.exists  # Can't check, treat as missing

            return all(checks) if self.exists else not any(checks)

        # Simple existence check
        if self.exists:
            return value is not None and value != '' and value != []
        else:
            return value is None or value == '' or value == []

    def to_sql(self, field: str) -> tuple[str, list]:
        if self.fields:
            # Complex check, handle in-memory
            return "1=1", []

        if self.exists:
            return f"{field} IS NOT NULL AND {field} != ''", []
        else:
            return f"({field} IS NULL OR {field} = '')", []

    def __repr__(self):
        if self.fields:
            return f"Existence(has {self.fields})"
        return f"Existence({'exists' if self.exists else 'missing'})"


@dataclass
class Compound(Expr):
    """
    Compound expression combining multiple expressions.

    - all: AND (all must match)
    - any: OR (at least one must match)
    - not: negate single expression
    """
    op: str  # 'all', 'any', 'not'
    exprs: List[Expr]

    def evaluate(self, value: Any) -> bool:
        if self.op == 'all':
            return all(e.evaluate(value) for e in self.exprs)
        elif self.op == 'any':
            return any(e.evaluate(value) for e in self.exprs)
        elif self.op == 'not' and self.exprs:
            return not self.exprs[0].evaluate(value)
        return False

    def to_sql(self, field: str) -> tuple[str, list]:
        if not self.exprs:
            return "1=1", []

        parts = []
        params = []
        for e in self.exprs:
            sql, p = e.to_sql(field)
            parts.append(f"({sql})")
            params.extend(p)

        if self.op == 'all':
            return ' AND '.join(parts), params
        elif self.op == 'any':
            return ' OR '.join(parts), params
        elif self.op == 'not':
            return f"NOT ({parts[0]})", params

        return "1=1", []

    def __repr__(self):
        return f"Compound({self.op} {self.exprs})"


# =============================================================================
# Parser
# =============================================================================

def parse_date(s: str) -> datetime:
    """Parse a date string into datetime."""
    s = s.strip()

    # Relative expressions: "N days/weeks/months ago"
    match = re.match(r'^(\d+)\s*(day|week|month|year|hour|minute)s?\s*ago$', s, re.I)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()

        if unit == 'day':
            return datetime.now() - timedelta(days=amount)
        elif unit == 'week':
            return datetime.now() - timedelta(weeks=amount)
        elif unit == 'month':
            return datetime.now() - timedelta(days=amount * 30)
        elif unit == 'year':
            return datetime.now() - timedelta(days=amount * 365)
        elif unit == 'hour':
            return datetime.now() - timedelta(hours=amount)
        elif unit == 'minute':
            return datetime.now() - timedelta(minutes=amount)

    # ISO format
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        pass

    # Simple date formats
    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse date: {s}")


def parse_duration(s: str) -> timedelta:
    """Parse a duration string into timedelta."""
    s = s.strip().lower()

    match = re.match(r'^(\d+)\s*(day|week|month|year|hour|minute|second)s?$', s)
    if not match:
        raise ValueError(f"Cannot parse duration: {s}")

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == 'day':
        return timedelta(days=amount)
    elif unit == 'week':
        return timedelta(weeks=amount)
    elif unit == 'month':
        return timedelta(days=amount * 30)
    elif unit == 'year':
        return timedelta(days=amount * 365)
    elif unit == 'hour':
        return timedelta(hours=amount)
    elif unit == 'minute':
        return timedelta(minutes=amount)
    elif unit == 'second':
        return timedelta(seconds=amount)

    raise ValueError(f"Unknown duration unit: {unit}")


def parse_value(s: str) -> Any:
    """Parse a literal value from string."""
    s = s.strip()

    # Boolean
    if s.lower() == 'true':
        return True
    if s.lower() == 'false':
        return False

    # None/null
    if s.lower() in ('none', 'null', 'nil'):
        return None

    # Number
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        pass

    # Quoted string - remove quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]

    # Bare string
    return s


def parse_list(s: str) -> List[Any]:
    """Parse a bracketed list like [a, b, c]."""
    s = s.strip()

    # Remove brackets if present
    if s.startswith('[') and s.endswith(']'):
        s = s[1:-1]

    # Split by comma, respecting quotes
    items = []
    current = []
    in_quotes = False
    quote_char = None

    for char in s:
        if char in '"\'':
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
            current.append(char)
        elif char == ',' and not in_quotes:
            items.append(''.join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        items.append(''.join(current).strip())

    return [parse_value(item) for item in items if item]


def parse_quoted(s: str) -> str:
    """Parse a possibly quoted string."""
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def parse_expr(value: Any) -> Expr:
    """
    Parse a YAML value into an expression.

    This is the main entry point for expression parsing.
    Handles raw YAML values (strings, lists, dicts, scalars).
    """
    # Already an Expr
    if isinstance(value, Expr):
        return value

    # Boolean
    if isinstance(value, bool):
        return Literal(value)

    # Number
    if isinstance(value, (int, float)):
        return Literal(value)

    # None
    if value is None:
        return Literal(None)

    # List -> implicit 'any' collection
    if isinstance(value, list):
        return Collection(op='any', values=value)

    # Dict -> could be structured expression
    if isinstance(value, dict):
        return parse_dict_expr(value)

    # String -> parse as expression
    if isinstance(value, str):
        return parse_string_expr(value)

    # Fallback: literal
    return Literal(value)


def parse_dict_expr(d: dict) -> Expr:
    """Parse a dictionary expression."""
    # Compound expressions
    if 'all' in d:
        return Compound('all', [parse_expr(e) for e in d['all']])
    if 'any' in d:
        return Compound('any', [parse_expr(e) for e in d['any']])
    if 'not' in d:
        return Compound('not', [parse_expr(d['not'])])

    # Comparison with explicit op
    if 'op' in d and 'value' in d:
        op = d['op']
        val = d['value']
        if op in ('>=', '<=', '>', '<', '=', '!=', '==', '<>'):
            return Comparison(op, val)
        elif op == 'contains':
            return StringOp('contains', str(val))
        elif op == 'starts_with':
            return StringOp('starts_with', str(val))
        elif op == 'ends_with':
            return StringOp('ends_with', str(val))
        elif op == 'matches':
            return StringOp('matches', str(val))
        elif op == 'under':
            return StringOp('under', str(val))

    # Collection with explicit mode
    if 'any' in d:
        return Collection('any', d['any'])
    if 'all' in d:
        return Collection('all', d['all'])
    if 'none' in d:
        return Collection('none', d['none'])

    # Temporal expressions
    if 'within' in d:
        return Temporal('within', parse_duration(d['within']))
    if 'before' in d:
        return Temporal('before', parse_date(d['before']))
    if 'after' in d:
        return Temporal('after', parse_date(d['after']))
    if 'between' in d and 'and' in d:
        return Temporal('between', parse_date(d['between']), parse_date(d['and']))

    # Shorthand comparisons: {min: 10} or {max: 100}
    if 'min' in d:
        return Comparison('>=', d['min'])
    if 'max' in d:
        return Comparison('<=', d['max'])
    if 'gt' in d:
        return Comparison('>', d['gt'])
    if 'lt' in d:
        return Comparison('<', d['lt'])
    if 'eq' in d:
        return Comparison('=', d['eq'])
    if 'ne' in d:
        return Comparison('!=', d['ne'])

    # Unknown dict - treat as literal
    return Literal(d)


def parse_string_expr(s: str) -> Expr:
    """Parse a string expression."""
    s = s.strip()

    if not s:
        return Literal('')

    # Comparison operators (must check longer ones first)
    for op in ['>=', '<=', '!=', '<>', '==', '>', '<', '=']:
        if s.startswith(op):
            rest = s[len(op):].strip()
            return Comparison(op, parse_value(rest))

    # Temporal expressions
    if s.startswith('within '):
        duration_str = s[7:].strip()
        return Temporal('within', parse_duration(duration_str))

    if s.startswith('before '):
        return Temporal('before', s[7:].strip())

    if s.startswith('after '):
        return Temporal('after', s[6:].strip())

    # Collection expressions
    if s.startswith('any '):
        return Collection('any', parse_list(s[4:]))

    if s.startswith('all '):
        return Collection('all', parse_list(s[4:]))

    if s.startswith('none '):
        return Collection('none', parse_list(s[5:]))

    # String operations
    if s.startswith('contains '):
        return StringOp('contains', parse_quoted(s[9:]))

    if s.startswith('starts_with '):
        return StringOp('starts_with', parse_quoted(s[12:]))

    if s.startswith('ends_with '):
        return StringOp('ends_with', parse_quoted(s[10:]))

    if s.startswith('matches '):
        return StringOp('matches', parse_quoted(s[8:]))

    if s.startswith('under '):
        return StringOp('under', s[6:].strip())

    # Existence expressions
    if s == 'exists':
        return Existence(exists=True)

    if s == 'missing':
        return Existence(exists=False)

    if s.startswith('has '):
        fields = parse_list(s[4:])
        return Existence(exists=True, fields=[str(f) for f in fields])

    # List literal (implicit any)
    if s.startswith('[') and s.endswith(']'):
        return Collection('any', parse_list(s))

    # Default: literal equality
    return Literal(parse_value(s))


# =============================================================================
# Convenience functions
# =============================================================================

def expr(value: Any) -> Expr:
    """Convenience alias for parse_expr."""
    return parse_expr(value)


def all_of(*exprs) -> Compound:
    """Create an AND compound expression."""
    return Compound('all', [parse_expr(e) for e in exprs])


def any_of(*exprs) -> Compound:
    """Create an OR compound expression."""
    return Compound('any', [parse_expr(e) for e in exprs])


def not_(e) -> Compound:
    """Create a NOT compound expression."""
    return Compound('not', [parse_expr(e)])
