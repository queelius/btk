"""
Query execution engine for btk.

Executes Query AST against the database, producing typed results.
Supports bookmark queries, tag queries, aggregate queries, and graph queries.

The executor handles:
- SQL generation for database-level filtering
- In-memory predicate evaluation for complex predicates
- Composition (union, intersect, from reference)
- Aggregation and grouping
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from sqlalchemy import func, select, and_, or_, not_, text
from sqlalchemy.orm import Session

from .ast import Query, EntityType, Predicate, SortSpec, GroupSpec, ComputeSpec
from .expr import (
    Expr, Literal, Comparison, Temporal, Collection,
    StringOp, Existence, Compound
)
from .results import (
    QueryResult, BookmarkResult, BookmarkItem,
    TagResult, TagItem, StatsResult, StatsRow,
    EdgeResult, Edge
)

if TYPE_CHECKING:
    from btk.db import Database
    from btk.models import Bookmark, Tag


# =============================================================================
# Execution Context
# =============================================================================

@dataclass
class ExecutionContext:
    """
    Context for query execution.

    Contains:
    - Parameter values for parameterized queries
    - Registry reference for resolving view references
    - Execution options
    """
    params: Dict[str, Any] = field(default_factory=dict)
    registry: Optional["QueryRegistry"] = None
    now: datetime = field(default_factory=datetime.now)
    debug: bool = False

    def resolve_param(self, name: str, default: Any = None) -> Any:
        """Resolve a parameter value."""
        return self.params.get(name, default)


# =============================================================================
# Predicate Evaluator
# =============================================================================

class PredicateEvaluator:
    """
    Evaluates predicates against entities.

    Handles both in-memory evaluation and SQL generation.
    """

    def __init__(self, entity_type: EntityType):
        self.entity_type = entity_type

    def evaluate(self, predicate: Predicate, entity: Any) -> bool:
        """Evaluate a predicate against an entity."""
        value = self._get_field_value(predicate.field.path, entity)
        return predicate.expr.evaluate(value)

    def _get_field_value(self, path: List[str], entity: Any) -> Any:
        """Get field value, traversing relations if needed."""
        current = entity

        for i, part in enumerate(path):
            if current is None:
                return None

            # Handle special relation cases
            if part == 'content' and hasattr(current, 'content_cache'):
                current = current.content_cache
            elif part == 'health' and hasattr(current, 'health'):
                current = current.health
            elif part == 'tags' and hasattr(current, 'tags'):
                # Tags is a collection
                if i == len(path) - 1:
                    # Return tag names for predicate evaluation
                    return [t.name for t in current.tags] if current.tags else []
                # Otherwise continue traversing
                current = current.tags
            elif part == 'has':
                # Special 'has' for existence checks on relations
                # Return the parent object for Existence predicate to check
                return current
            else:
                # Normal attribute access
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return None

        return current

    def to_sql_bookmark(self, predicates: List[Predicate], session: Session) -> tuple:
        """
        Generate SQL for bookmark predicates.

        Returns (conditions, params) for use in WHERE clause.
        """
        from btk.models import Bookmark, Tag, bookmark_tags

        conditions = []
        params = []

        for pred in predicates:
            field_path = pred.field.path

            # Handle relation fields specially
            if field_path[0] == 'tags':
                sql, p = self._tags_to_sql(pred.expr, session)
                if sql != "1=1":
                    conditions.append(text(sql))
                    params.extend(p)

            elif field_path[0] == 'content':
                # Content relation - join with content_cache
                sql, p = self._content_to_sql(field_path[1:], pred.expr)
                if sql != "1=1":
                    conditions.append(text(sql))
                    params.extend(p)

            elif field_path[0] == 'health':
                # Health relation - join with bookmark_health
                sql, p = self._health_to_sql(field_path[1:], pred.expr)
                if sql != "1=1":
                    conditions.append(text(sql))
                    params.extend(p)

            else:
                # Direct field on bookmark
                field_name = field_path[0]
                sql, p = pred.expr.to_sql(field_name)
                if sql != "1=1":
                    conditions.append(text(sql))
                    params.extend(p)

        return conditions, params

    def _tags_to_sql(self, expr: Expr, session: Session) -> tuple[str, list]:
        """Generate SQL for tag predicates."""
        if isinstance(expr, Collection):
            if expr.op == 'any':
                # Check if any of the patterns match
                tag_conditions = []
                tag_params = []
                for pattern in expr.values:
                    if '*' in str(pattern) or '?' in str(pattern):
                        like_pattern = str(pattern).replace('*', '%').replace('?', '_')
                        tag_conditions.append("t.name LIKE ?")
                        tag_params.append(like_pattern)
                    else:
                        tag_conditions.append("t.name = ?")
                        tag_params.append(str(pattern))

                sql = f"""
                    EXISTS (
                        SELECT 1 FROM bookmark_tags bt
                        JOIN tags t ON bt.tag_id = t.id
                        WHERE bt.bookmark_id = bookmarks.id
                        AND ({' OR '.join(tag_conditions)})
                    )
                """
                return sql, tag_params

            elif expr.op == 'all':
                # All tags must be present
                tag_conditions = []
                tag_params = []
                for pattern in expr.values:
                    if '*' in str(pattern) or '?' in str(pattern):
                        like_pattern = str(pattern).replace('*', '%').replace('?', '_')
                        tag_conditions.append(f"""
                            EXISTS (
                                SELECT 1 FROM bookmark_tags bt
                                JOIN tags t ON bt.tag_id = t.id
                                WHERE bt.bookmark_id = bookmarks.id AND t.name LIKE ?
                            )
                        """)
                        tag_params.append(like_pattern)
                    else:
                        tag_conditions.append(f"""
                            EXISTS (
                                SELECT 1 FROM bookmark_tags bt
                                JOIN tags t ON bt.tag_id = t.id
                                WHERE bt.bookmark_id = bookmarks.id AND t.name = ?
                            )
                        """)
                        tag_params.append(str(pattern))

                return f"({' AND '.join(tag_conditions)})", tag_params

            elif expr.op == 'none':
                # None of the tags should be present
                tag_conditions = []
                tag_params = []
                for pattern in expr.values:
                    if '*' in str(pattern) or '?' in str(pattern):
                        like_pattern = str(pattern).replace('*', '%').replace('?', '_')
                        tag_conditions.append("t.name LIKE ?")
                        tag_params.append(like_pattern)
                    else:
                        tag_conditions.append("t.name = ?")
                        tag_params.append(str(pattern))

                sql = f"""
                    NOT EXISTS (
                        SELECT 1 FROM bookmark_tags bt
                        JOIN tags t ON bt.tag_id = t.id
                        WHERE bt.bookmark_id = bookmarks.id
                        AND ({' OR '.join(tag_conditions)})
                    )
                """
                return sql, tag_params

        elif isinstance(expr, Existence):
            if expr.exists:
                # Has tags
                return """
                    EXISTS (
                        SELECT 1 FROM bookmark_tags bt
                        WHERE bt.bookmark_id = bookmarks.id
                    )
                """, []
            else:
                # Missing tags (untagged)
                return """
                    NOT EXISTS (
                        SELECT 1 FROM bookmark_tags bt
                        WHERE bt.bookmark_id = bookmarks.id
                    )
                """, []

        return "1=1", []

    def _content_to_sql(self, path: List[str], expr: Expr) -> tuple[str, list]:
        """Generate SQL for content cache predicates."""
        if not path:
            # Just 'content: exists' or 'content: missing'
            if isinstance(expr, Existence):
                if expr.exists:
                    return """
                        EXISTS (
                            SELECT 1 FROM content_cache cc
                            WHERE cc.bookmark_id = bookmarks.id
                        )
                    """, []
                else:
                    return """
                        NOT EXISTS (
                            SELECT 1 FROM content_cache cc
                            WHERE cc.bookmark_id = bookmarks.id
                        )
                    """, []

        field = path[0] if path else ''

        if field == 'has':
            # content.has: [transcript, thumbnail]
            if isinstance(expr, Existence) and expr.fields:
                conditions = []
                for f in expr.fields:
                    if f == 'transcript':
                        conditions.append("cc.transcript_text IS NOT NULL AND cc.transcript_text != ''")
                    elif f == 'thumbnail':
                        conditions.append("cc.thumbnail_data IS NOT NULL")
                    elif f == 'markdown':
                        conditions.append("cc.markdown_content IS NOT NULL AND cc.markdown_content != ''")
                    elif f == 'html':
                        conditions.append("cc.html_content IS NOT NULL")

                if conditions:
                    return f"""
                        EXISTS (
                            SELECT 1 FROM content_cache cc
                            WHERE cc.bookmark_id = bookmarks.id
                            AND {' AND '.join(conditions)}
                        )
                    """, []

            elif isinstance(expr, Collection):
                # content.has: [transcript, thumbnail] as list
                conditions = []
                for f in expr.values:
                    if f == 'transcript':
                        conditions.append("cc.transcript_text IS NOT NULL AND cc.transcript_text != ''")
                    elif f == 'thumbnail':
                        conditions.append("cc.thumbnail_data IS NOT NULL")
                    elif f == 'markdown':
                        conditions.append("cc.markdown_content IS NOT NULL AND cc.markdown_content != ''")
                    elif f == 'html':
                        conditions.append("cc.html_content IS NOT NULL")

                if conditions:
                    joiner = ' AND ' if expr.op == 'all' else ' OR '
                    return f"""
                        EXISTS (
                            SELECT 1 FROM content_cache cc
                            WHERE cc.bookmark_id = bookmarks.id
                            AND ({joiner.join(conditions)})
                        )
                    """, []

        elif field == 'type':
            # content.type: youtube
            sql, params = expr.to_sql('cc.preservation_type')
            return f"""
                EXISTS (
                    SELECT 1 FROM content_cache cc
                    WHERE cc.bookmark_id = bookmarks.id
                    AND {sql}
                )
            """, params

        return "1=1", []

    def _health_to_sql(self, path: List[str], expr: Expr) -> tuple[str, list]:
        """Generate SQL for health predicates."""
        if not path:
            return "1=1", []

        field = path[0]

        if field == 'status':
            sql, params = expr.to_sql('bh.status_code')
            return f"""
                EXISTS (
                    SELECT 1 FROM bookmark_health bh
                    WHERE bh.bookmark_id = bookmarks.id
                    AND {sql}
                )
            """, params

        elif field == 'checked':
            sql, params = expr.to_sql('bh.last_check')
            return f"""
                EXISTS (
                    SELECT 1 FROM bookmark_health bh
                    WHERE bh.bookmark_id = bookmarks.id
                    AND {sql}
                )
            """, params

        elif field == 'response_time':
            sql, params = expr.to_sql('bh.response_time_ms')
            return f"""
                EXISTS (
                    SELECT 1 FROM bookmark_health bh
                    WHERE bh.bookmark_id = bookmarks.id
                    AND {sql}
                )
            """, params

        return "1=1", []


# =============================================================================
# Query Executor
# =============================================================================

class QueryExecutor:
    """
    Executes queries against the btk database.

    Handles all entity types and query compositions.
    """

    def __init__(self, db: "Database"):
        self.db = db

    def execute(self, query: Query, context: Optional[ExecutionContext] = None) -> QueryResult:
        """
        Execute a query and return results.

        Args:
            query: The query to execute
            context: Optional execution context

        Returns:
            Typed QueryResult based on query entity type
        """
        context = context or ExecutionContext()

        # Handle composition first
        if query.source and context.registry:
            # Execute source query first
            source_query = context.registry.get(query.source)
            base_result = self.execute(source_query, context)
            # Apply additional filters to base result
            return self._refine_result(base_result, query, context)

        if query.union and context.registry:
            return self._execute_union(query, context)

        if query.intersect and context.registry:
            return self._execute_intersect(query, context)

        # Execute based on entity type
        if query.entity == EntityType.BOOKMARK:
            return self._execute_bookmark_query(query, context)
        elif query.entity == EntityType.TAG:
            return self._execute_tag_query(query, context)
        elif query.entity == EntityType.STATS:
            return self._execute_stats_query(query, context)
        elif query.entity == EntityType.EDGES:
            return self._execute_edge_query(query, context)
        else:
            raise ValueError(f"Unsupported entity type: {query.entity}")

    def _execute_bookmark_query(self, query: Query, context: ExecutionContext) -> BookmarkResult:
        """Execute a bookmark query."""
        from btk.models import Bookmark, Tag, bookmark_tags
        from sqlalchemy.orm import selectinload

        with self.db.session() as session:
            # Build base query with eager loading to avoid DetachedInstanceError
            stmt = select(Bookmark).options(selectinload(Bookmark.tags))

            # Apply simple SQL-level filters for direct bookmark fields
            for pred in query.predicates:
                if not pred.field.is_relation:
                    # Simple field on bookmark - try to apply at SQL level
                    field_name = pred.field.path[0]
                    col = getattr(Bookmark, field_name, None)

                    if col is not None:
                        sql_cond = self._expr_to_sqlalchemy(pred.expr, col)
                        if sql_cond is not None:
                            stmt = stmt.where(sql_cond)

            # Apply sorting
            for sort_spec in query.sort:
                col = getattr(Bookmark, sort_spec.field, None)
                if col is not None:
                    if sort_spec.direction == 'desc':
                        col = col.desc()
                    if sort_spec.nulls == 'last':
                        col = col.nullslast()
                    else:
                        col = col.nullsfirst()
                    stmt = stmt.order_by(col)

            # Get total count before limit (for pagination)
            # Use a simpler count that doesn't have parameter issues
            count_stmt = select(func.count(Bookmark.id))
            for pred in query.predicates:
                if not pred.field.is_relation:
                    field_name = pred.field.path[0]
                    col = getattr(Bookmark, field_name, None)
                    if col is not None:
                        sql_cond = self._expr_to_sqlalchemy(pred.expr, col)
                        if sql_cond is not None:
                            count_stmt = count_stmt.where(sql_cond)

            total_count = session.execute(count_stmt).scalar() or 0

            # Apply limit and offset
            if query.offset:
                stmt = stmt.offset(query.offset)
            if query.limit:
                stmt = stmt.limit(query.limit)

            # Execute
            bookmarks = list(session.execute(stmt).scalars().all())

            # Apply in-memory filters for complex predicates (relations, etc.)
            evaluator = PredicateEvaluator(EntityType.BOOKMARK)
            if query.predicates:
                filtered = []
                for b in bookmarks:
                    matches = all(evaluator.evaluate(p, b) for p in query.predicates)
                    if matches:
                        filtered.append(b)
                bookmarks = filtered

            # Apply exclusions
            if query.exclude:
                for exclude_pred in query.exclude:
                    bookmarks = [b for b in bookmarks if not evaluator.evaluate(exclude_pred, b)]

            # Detach objects from session while preserving loaded data
            # This prevents DetachedInstanceError when accessing attributes later
            from sqlalchemy.orm import make_transient

            for b in bookmarks:
                # Force load all scalar attributes we need
                _ = (b.id, b.url, b.title, b.description, b.added, b.stars,
                     b.pinned, b.archived, b.visit_count, b.last_visited,
                     b.reachable, b.media_type, b.media_source, b.media_id,
                     b.author_name, b.thumbnail_url)
                # Load tag attributes too
                if b.tags:
                    for t in b.tags:
                        _ = (t.id, t.name, t.description, t.color)
                        make_transient(t)
                make_transient(b)

            return BookmarkResult.from_bookmarks(bookmarks, total=total_count)

    def _expr_to_sqlalchemy(self, expr: Expr, col):
        """Convert an expression to a SQLAlchemy condition."""
        if isinstance(expr, Literal):
            return col == expr.value

        elif isinstance(expr, Comparison):
            if expr.op in ('>=', 'gte'):
                return col >= expr.value
            elif expr.op in ('<=', 'lte'):
                return col <= expr.value
            elif expr.op in ('>', 'gt'):
                return col > expr.value
            elif expr.op in ('<', 'lt'):
                return col < expr.value
            elif expr.op in ('=', '==', 'eq'):
                return col == expr.value
            elif expr.op in ('!=', '<>', 'ne'):
                return col != expr.value

        elif isinstance(expr, StringOp):
            if expr.op == 'contains':
                return col.ilike(f'%{expr.pattern}%')
            elif expr.op == 'starts_with':
                return col.ilike(f'{expr.pattern}%')
            elif expr.op == 'ends_with':
                return col.ilike(f'%{expr.pattern}')

        elif isinstance(expr, Existence):
            if not expr.fields:
                if expr.exists:
                    return and_(col.isnot(None), col != '')
                else:
                    return or_(col.is_(None), col == '')

        elif isinstance(expr, Collection):
            # For simple equality collections without globs
            has_globs = any('*' in str(v) or '?' in str(v) for v in expr.values)
            if not has_globs:
                if expr.op == 'any':
                    return col.in_(expr.values)
                elif expr.op == 'none':
                    return col.notin_(expr.values)

        elif isinstance(expr, Temporal):
            from datetime import datetime, timedelta
            now = datetime.now()

            if expr.op == 'within':
                if isinstance(expr.value, timedelta):
                    threshold = now - expr.value
                else:
                    threshold = now - timedelta(days=30)  # Default
                return col >= threshold

            elif expr.op == 'before':
                if isinstance(expr.value, datetime):
                    return col < expr.value
                elif isinstance(expr.value, str):
                    try:
                        dt = datetime.fromisoformat(expr.value.replace('Z', '+00:00'))
                        return col < dt
                    except ValueError:
                        pass

            elif expr.op == 'after':
                if isinstance(expr.value, datetime):
                    return col > expr.value
                elif isinstance(expr.value, str):
                    try:
                        dt = datetime.fromisoformat(expr.value.replace('Z', '+00:00'))
                        return col > dt
                    except ValueError:
                        pass

        # Can't convert to SQLAlchemy, will filter in-memory
        return None

    def _execute_tag_query(self, query: Query, context: ExecutionContext) -> TagResult:
        """Execute a tag query."""
        from btk.models import Tag, bookmark_tags

        with self.db.session() as session:
            # Get tags with usage counts
            stmt = (
                select(Tag, func.count(bookmark_tags.c.bookmark_id).label('usage_count'))
                .outerjoin(bookmark_tags, Tag.id == bookmark_tags.c.tag_id)
                .group_by(Tag.id)
            )

            # Apply predicates
            evaluator = PredicateEvaluator(EntityType.TAG)

            for pred in query.predicates:
                field = pred.field.path[0]

                if field == 'usage' or field == 'usage_count':
                    # Filter by usage count - handled in HAVING
                    sql, params = pred.expr.to_sql('usage_count')
                    # Can't easily do this in SQLAlchemy, filter in-memory
                    pass
                elif field == 'name':
                    sql, params = pred.expr.to_sql('tags.name')
                    stmt = stmt.where(text(sql))
                elif field == 'pattern':
                    # Pattern matching on tag name
                    if isinstance(pred.expr, StringOp):
                        sql, params = pred.expr.to_sql('tags.name')
                        stmt = stmt.where(text(sql))

            # Apply sorting
            for sort_spec in query.sort:
                if sort_spec.field == 'usage' or sort_spec.field == 'usage_count':
                    col = text('usage_count')
                else:
                    col = getattr(Tag, sort_spec.field, text(sort_spec.field))

                if sort_spec.direction == 'desc':
                    stmt = stmt.order_by(col.desc() if hasattr(col, 'desc') else text(f'{sort_spec.field} DESC'))
                else:
                    stmt = stmt.order_by(col if not hasattr(col, 'asc') else col.asc())

            # Apply limit
            if query.limit:
                stmt = stmt.limit(query.limit)

            # Execute
            results = session.execute(stmt).all()

            # Build tag items with usage counts
            items = []
            for row in results:
                tag = row[0]
                usage = row[1]

                # Apply in-memory filters
                matches = True
                for pred in query.predicates:
                    if pred.field.path[0] in ('usage', 'usage_count'):
                        if not pred.expr.evaluate(usage):
                            matches = False
                            break

                if matches:
                    items.append(TagItem(tag=tag, usage_count=usage))

            return TagResult(items=items, total_count=len(items))

    def _execute_stats_query(self, query: Query, context: ExecutionContext) -> StatsResult:
        """Execute an aggregate query."""
        from btk.models import Bookmark

        with self.db.session() as session:
            # Build group expressions
            group_cols = []
            group_labels = []

            for group_spec in query.group_by:
                if group_spec.transform:
                    # Temporal grouping
                    if group_spec.transform == 'month':
                        col = func.strftime('%Y-%m', getattr(Bookmark, group_spec.field))
                    elif group_spec.transform == 'year':
                        col = func.strftime('%Y', getattr(Bookmark, group_spec.field))
                    elif group_spec.transform == 'day':
                        col = func.strftime('%Y-%m-%d', getattr(Bookmark, group_spec.field))
                    else:
                        col = getattr(Bookmark, group_spec.field)
                elif group_spec.field == 'domain':
                    # Extract domain from URL
                    # SQLite doesn't have easy domain extraction, use LIKE patterns
                    col = Bookmark.url  # Simplified - would need custom function
                else:
                    col = getattr(Bookmark, group_spec.field, text(group_spec.field))

                group_cols.append(col)
                label = f"{group_spec.transform}_{group_spec.field}" if group_spec.transform else group_spec.field
                group_labels.append(label)

            # Build compute expressions
            agg_cols = []
            agg_labels = []

            for compute_spec in query.compute:
                if compute_spec.func == 'count':
                    col = func.count()
                elif compute_spec.func == 'sum':
                    col = func.sum(getattr(Bookmark, compute_spec.field))
                elif compute_spec.func == 'avg':
                    col = func.avg(getattr(Bookmark, compute_spec.field))
                elif compute_spec.func == 'min':
                    col = func.min(getattr(Bookmark, compute_spec.field))
                elif compute_spec.func == 'max':
                    col = func.max(getattr(Bookmark, compute_spec.field))
                elif compute_spec.func == 'distinct':
                    col = func.count(func.distinct(getattr(Bookmark, compute_spec.field)))
                else:
                    col = func.count()

                agg_cols.append(col.label(compute_spec.name))
                agg_labels.append(compute_spec.name)

            # Build the query
            select_cols = group_cols + agg_cols
            stmt = select(*select_cols).select_from(Bookmark)

            # Apply filters
            evaluator = PredicateEvaluator(EntityType.BOOKMARK)
            conditions, params = evaluator.to_sql_bookmark(query.predicates, session)
            for cond in conditions:
                stmt = stmt.where(cond)

            # Group by
            if group_cols:
                stmt = stmt.group_by(*group_cols)

            # Apply having (post-group filters)
            # This is simplified - proper implementation would translate having predicates
            for having_pred in query.having:
                sql, params = having_pred.expr.to_sql(having_pred.field.path[0])
                stmt = stmt.having(text(sql))

            # Sorting
            for sort_spec in query.sort:
                if sort_spec.field in agg_labels:
                    idx = agg_labels.index(sort_spec.field)
                    col = agg_cols[idx]
                elif sort_spec.field in group_labels:
                    idx = group_labels.index(sort_spec.field)
                    col = group_cols[idx]
                else:
                    col = text(sort_spec.field)

                if sort_spec.direction == 'desc':
                    stmt = stmt.order_by(col.desc() if hasattr(col, 'desc') else text(f'{sort_spec.field} DESC'))
                else:
                    stmt = stmt.order_by(col)

            # Limit
            if query.limit:
                stmt = stmt.limit(query.limit)

            # Execute
            results = session.execute(stmt).all()

            # Build stats rows
            items = []
            for row in results:
                group_key = {}
                for i, label in enumerate(group_labels):
                    group_key[label] = row[i]

                values = {}
                for i, label in enumerate(agg_labels):
                    values[label] = row[len(group_labels) + i]

                items.append(StatsRow(group_key=group_key, values=values))

            return StatsResult(items=items, total_count=len(items))

    def _execute_edge_query(self, query: Query, context: ExecutionContext) -> EdgeResult:
        """Execute a graph/edge query (e.g., tag co-occurrence)."""
        from btk.models import Tag, bookmark_tags

        with self.db.session() as session:
            # Tag co-occurrence query
            bt1 = bookmark_tags.alias('bt1')
            bt2 = bookmark_tags.alias('bt2')
            t1 = Tag.__table__.alias('t1')
            t2 = Tag.__table__.alias('t2')

            # Find tags that co-occur on the same bookmarks
            stmt = (
                select(
                    t1.c.name.label('source'),
                    t2.c.name.label('target'),
                    func.count().label('weight')
                )
                .select_from(bt1)
                .join(bt2, and_(
                    bt1.c.bookmark_id == bt2.c.bookmark_id,
                    bt1.c.tag_id < bt2.c.tag_id  # Avoid duplicates
                ))
                .join(t1, bt1.c.tag_id == t1.c.id)
                .join(t2, bt2.c.tag_id == t2.c.id)
                .group_by(t1.c.name, t2.c.name)
            )

            # Apply predicates (e.g., minimum weight)
            for pred in query.predicates:
                if pred.field.path[0] == 'weight':
                    sql, params = pred.expr.to_sql('weight')
                    stmt = stmt.having(text(sql))

            # Sorting
            for sort_spec in query.sort:
                col = text(sort_spec.field)
                if sort_spec.direction == 'desc':
                    stmt = stmt.order_by(text(f'{sort_spec.field} DESC'))
                else:
                    stmt = stmt.order_by(col)

            # Limit
            if query.limit:
                stmt = stmt.limit(query.limit)

            # Execute
            results = session.execute(stmt).all()

            # Build edges
            items = [
                Edge(source=row.source, target=row.target, weight=row.weight)
                for row in results
            ]

            return EdgeResult(items=items, total_count=len(items))

    def _execute_union(self, query: Query, context: ExecutionContext) -> QueryResult:
        """Execute a union of multiple queries."""
        if not context.registry:
            return BookmarkResult.empty()

        all_items: Dict[int, Any] = {}  # Dedupe by id

        for view_name in query.union:
            sub_query = context.registry.get(view_name)
            result = self.execute(sub_query, context)

            for item in result.items:
                item_id = getattr(item, 'id', id(item))
                if item_id not in all_items:
                    all_items[item_id] = item

        items = list(all_items.values())

        # Apply sorting to combined results
        if query.sort:
            items = self._sort_items(items, query.sort)

        # Apply limit
        if query.limit:
            items = items[:query.limit]

        return BookmarkResult(items=items, total_count=len(items))

    def _execute_intersect(self, query: Query, context: ExecutionContext) -> QueryResult:
        """Execute an intersection of multiple queries."""
        if not context.registry:
            return BookmarkResult.empty()

        result_sets: List[Set[int]] = []

        for view_name in query.intersect:
            sub_query = context.registry.get(view_name)
            result = self.execute(sub_query, context)
            result_sets.append({getattr(item, 'id', id(item)) for item in result.items})

        # Intersect all sets
        if not result_sets:
            return BookmarkResult.empty()

        common_ids = result_sets[0]
        for s in result_sets[1:]:
            common_ids &= s

        # Get the actual items (from first query)
        first_query = context.registry.get(query.intersect[0])
        first_result = self.execute(first_query, context)

        items = [item for item in first_result.items if getattr(item, 'id', id(item)) in common_ids]

        # Apply sorting
        if query.sort:
            items = self._sort_items(items, query.sort)

        # Apply limit
        if query.limit:
            items = items[:query.limit]

        return BookmarkResult(items=items, total_count=len(items))

    def _refine_result(self, base_result: QueryResult, query: Query, context: ExecutionContext) -> QueryResult:
        """Apply additional filters to an existing result."""
        evaluator = PredicateEvaluator(query.entity)

        items = list(base_result.items)

        # Apply predicates
        for pred in query.predicates:
            items = [item for item in items if evaluator.evaluate(pred, item)]

        # Apply exclusions
        for exclude_pred in query.exclude:
            items = [item for item in items if not evaluator.evaluate(exclude_pred, item)]

        # Apply sorting
        if query.sort:
            items = self._sort_items(items, query.sort)

        # Apply limit
        if query.limit:
            items = items[:query.limit]

        # Return same type as input
        return type(base_result)(items=items, total_count=len(items))

    def _sort_items(self, items: List[Any], sort_specs: List[SortSpec]) -> List[Any]:
        """Sort items by sort specifications."""
        if not sort_specs:
            return items

        def sort_key(item):
            keys = []
            for spec in sort_specs:
                val = getattr(item, spec.field, None)
                # Handle None values
                if val is None:
                    val = '' if spec.nulls == 'first' else '\uffff'
                keys.append(val)
            return tuple(keys)

        reverse = sort_specs[0].direction == 'desc'
        return sorted(items, key=sort_key, reverse=reverse)


# =============================================================================
# Convenience Functions
# =============================================================================

def execute_query(db: "Database", query: Query, context: Optional[ExecutionContext] = None) -> QueryResult:
    """Execute a query against a database."""
    executor = QueryExecutor(db)
    return executor.execute(query, context)


def execute_yaml(db: "Database", yaml_def: Dict[str, Any], context: Optional[ExecutionContext] = None) -> QueryResult:
    """Execute a query from YAML definition."""
    from .parser import parse_query
    query = parse_query(yaml_def)
    return execute_query(db, query, context)
